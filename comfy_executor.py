"""Independent masked-repair service. Host integration is deliberately explicit.
No import-time IO, background worker, model installation, or auto generation.
"""
import contextlib
import copy
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import comfy_assets as assets
import comfy_templates as templates
import generation_scope
import workflow_state

LIVE = {'submitting', 'uploading', 'queued', 'running', 'unknown', 'archive_pending'}

class LocalTransport:
    def __init__(self, base):
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('仅允许本机ComfyUI HTTP地址')
        self.base = base.rstrip('/')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): raise ValueError('禁止重定向')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)

    def request(self, route, payload=None, raw=False, body=None, content_type=None):
        if not route.startswith('/') or route.startswith('//'): raise ValueError('路由无效')
        data = body if body is not None else json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base+route, data=data, headers={'Content-Type': content_type or 'application/json'})
        with self.opener.open(req, timeout=20) as response: result = response.read(assets.MAX_BYTES+1)
        if len(result) > assets.MAX_BYTES: raise ValueError('响应超过大小限制')
        return result if raw else json.loads(result)

    def upload(self, name, data):
        boundary = 'studio'+uuid.uuid4().hex
        body = ('--'+boundary+'\r\nContent-Disposition: form-data; name="image"; filename="'+name+'"\r\nContent-Type: image/png\r\n\r\n').encode()+data+('\r\n--'+boundary+'\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\nfalse\r\n--'+boundary+'--\r\n').encode()
        answer = self.request('/upload/image', body=body, content_type='multipart/form-data; boundary='+boundary)
        if answer.get('name') != name or answer.get('subfolder', '') != '' or answer.get('type', 'input') != 'input':
            raise ValueError('上传返回的素材位置不匹配')
        return name

class RepairService:
    """Uses the existing state/revisions schema and image_tasks budget ledger.

    profile is trusted operator configuration, never browser request data:
    checkpoint_path/sha256, architecture='sd15', comfy_root/core_nodes_sha256,
    comfy_version. Reviewing a new profile is a separate integration decision.
    """
    def __init__(self, root, database, transport, profile, authorize=None, paused=None, lock=None, selected=None):
        self.root = Path(root).resolve(); self.database = Path(database).resolve()
        self.lock = lock or contextlib.nullcontext()
        self.selected = selected
        self.transport = transport; self.profile = copy.deepcopy(profile)
        self.uses_default_authorization = authorize is None
        self.authorize = authorize or generation_scope.check
        self.paused = paused or generation_scope.is_paused

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            con = sqlite3.connect(self.database, timeout=30)
            try:
                con.execute('BEGIN IMMEDIATE')
                yield con
                con.commit()
            except BaseException:
                con.rollback(); raise
            finally: con.close()

    def state(self, con, project_id, revision=None):
        if type(project_id) is not int or project_id < 1: raise ValueError('项目无效')
        row = con.execute('SELECT body FROM state WHERE id=?', (project_id,)).fetchone()
        if not row: raise ValueError('项目不存在')
        state = json.loads(row[0]); state['project_id'] = project_id
        state['revision'] = con.execute('SELECT COALESCE(MAX(id),0) FROM revisions WHERE project_id=?', (project_id,)).fetchone()[0]
        if revision is not None and revision != state['revision']: raise ValueError('内容版本已变化，请刷新')
        return state

    def save(self, con, state):
        body = json.dumps(state, ensure_ascii=False)
        con.execute('INSERT INTO revisions(body,project_id) VALUES (?,?)', (body, state['project_id']))
        con.execute('UPDATE state SET body=? WHERE id=?', (body, state['project_id']))

    def task(self, state, task_id):
        task = next((t for t in state.get('image_tasks', []) if t['id'] == task_id and t.get('provider') == 'comfy-masked-repair'), None)
        if not task or task.get('project_id') != state['project_id']: raise ValueError('任务不属于当前项目')
        return task

    def write_asset(self, project_id, name, data):
        if not re.fullmatch(r'[a-f0-9]{32}_(source|mask|candidate)\.png', name): raise ValueError('归档名称无效')
        base = self.root/'assets'; folder = base/str(project_id)
        if base.is_symlink() or folder.is_symlink(): raise ValueError('素材目录不能为符号链接')
        folder.mkdir(parents=True, exist_ok=True)
        if folder.resolve().parent != base.resolve(): raise ValueError('素材目录越界')
        fd, temp = tempfile.mkstemp(dir=folder, prefix='.repair-')
        try:
            with os.fdopen(fd, 'wb') as out: out.write(data); out.flush(); os.fsync(out.fileno())
            os.replace(temp, folder/name)
        finally:
            if os.path.exists(temp): os.unlink(temp)
        return '/media/'+str(project_id)+'/'+name

    def preflight(self):
        issues = []; profile = self.profile
        try:
            if profile.get('architecture') != 'sd15': raise ValueError('尚未配置审阅过的SD1.x模型档案')
            checkpoint = Path(profile['checkpoint_path']); comfy = Path(profile['comfy_root'])
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.safetensors', checkpoint.name) or '..' in checkpoint.name: raise ValueError('模型文件名不受支持')
            if checkpoint.resolve().parent != (comfy/'models'/'checkpoints').resolve(): raise ValueError('模型须位于审阅的checkpoints目录')
            for file, expected in ((checkpoint, profile.get('checkpoint_sha256')), (comfy/'nodes.py', profile.get('core_nodes_sha256'))):
                if not expected or not re.fullmatch(r'[a-f0-9]{64}', expected): raise ValueError('缺少审阅文件摘要')
                h = hashlib.sha256()
                with file.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
                if h.hexdigest() != expected: raise ValueError('模型或节点文件与审阅版本不符')
            info = self.transport.request('/object_info'); stats = self.transport.request('/system_stats')
            if not profile.get('comfy_version') or stats.get('system', {}).get('comfyui_version') != profile['comfy_version']: raise ValueError('执行器版本与审阅档案不符')
            missing = templates.NODES-set(info)
            if missing: raise ValueError('缺少节点：'+', '.join(sorted(missing)))
            probe = templates.manifest()['graph_spec']
            for node in probe.values():
                definition = info[node['class_type']]; required = definition.get('input', {}).get('required', {})
                optional = definition.get('input', {}).get('optional', {})
                if set(required)-set(node['inputs']) or set(node['inputs'])-(set(required)|set(optional)):
                    raise ValueError('节点输入契约与审阅模板不符：'+node['class_type'])
                module = definition.get('python_module', 'nodes')
                if module != 'nodes': raise ValueError('模板节点被非核心实现替换')
            choices = info['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0]
            if checkpoint.name not in choices: raise ValueError('执行器未发现已审阅模型')
        except Exception as exc: issues.append(str(exc))
        return {'ready': not issues, 'issues': issues, 'template': templates.manifest(), 'quality_verified': False, 'network_generation_called': False}

    def public_preflight(self):
        """Product surface; detailed diagnostics remain developer-only."""
        result = self.preflight()
        return {'ready': result['ready'], 'message': '可以制作局部修复候选' if result['ready'] else '局部修复暂不可用',
                'quality_verified': False, 'generation_called': False}

    def begin(self, project_id, revision, shot_id, source_url, mask_url, values, request_id):
        values = templates.parameters(values)
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9]{32}', request_id): raise ValueError('请求编号无效')
        # Early local gates before read-only remote inspection; repeat under transaction.
        with self.transaction() as con:
            state = self.state(con, project_id, revision)
            self.gate(state, shot_id, source_url)
        source = assets.asset(self.root, project_id, source_url); mask = assets.asset(self.root, project_id, mask_url)
        assets.inputs(source, mask)
        health = self.preflight()
        if not health['ready']: raise ValueError('增强未就绪：'+'；'.join(health['issues']))
        task_id = uuid.uuid4().hex
        source_name = task_id+'_source.png'; mask_name = task_id+'_mask.png'
        request = templates.graph(Path(self.profile['checkpoint_path']).name, source_name, mask_name, values, task_id)
        with self.transaction() as con:
            state = self.state(con, project_id, revision); shot = self.gate(state, shot_id, source_url)
            if assets.sha(source) != shot.get('storyboard_sha256'): raise ValueError('原图文件已变化，请重新审阅')
            if any(t.get('request_id') == request_id or t.get('status') in LIVE for t in state.get('image_tasks', [])):
                raise ValueError('存在原请求或在途/未知图片任务，禁止重提')
            authorization_id = self.authorize(state, self.database, 'image', 0, templates.MODEL_SCOPE, shot_id=shot_id)
            archived_source = self.write_asset(project_id, source_name, source)
            archived_mask = self.write_asset(project_id, mask_name, mask)
            task = {'id': task_id, 'project_id': project_id, 'shot_id': shot_id, 'name': shot['name'],
                    'provider': 'comfy-masked-repair', 'kind': 'image', 'cost_category': 'image',
                    'request_id': request_id, 'status': 'submitting', 'provider_task_id': None,
                    'estimate': 0, 'actual_cost_cny': 0, 'cost_note': '本机执行无外部模型调用费；不含设备成本',
                    'authorization_id': authorization_id,
                    'authorization_scope_snapshot': copy.deepcopy(generation_scope.read().get(str(project_id), {})) if self.uses_default_authorization else {'id': authorization_id, 'source': 'host authorization adapter'},
                    'content_revision': state['revision'],
                    'approval_snapshot': copy.deepcopy(shot['approval_snapshot']),
                    'source_url': source_url, 'source_sha256': assets.sha(source),
                    'archived_source': archived_source, 'archived_mask': archived_mask,
                    'mask_sha256': assets.sha(mask), 'parameters': values, 'request': request,
                    'request_sha256': templates.digest(request), 'template': templates.manifest(),
                    'dependency_snapshot': copy.deepcopy(self.profile), 'quality_verified': False}
            state.setdefault('image_tasks', []).append(task); self.save(con, state)
        return copy.deepcopy(task)

    def import_mask(self, project_id, revision, shot_id, data):
        """Host accepts a bounded PNG upload. Does not submit or resume generation."""
        if not isinstance(data, bytes) or len(data) > assets.MAX_BYTES: raise ValueError('遮罩过大')
        with self.transaction() as con:
            state = self.state(con, project_id, revision)
            if self.selected and self.selected()!=project_id:raise ValueError('当前项目已切换')
            shot = next((s for s in state['shots'] if s['id'] == shot_id), None)
            if not shot: raise ValueError('镜头不属于当前项目')
            source = assets.asset(self.root, project_id, shot.get('storyboard_local'))
            assets.inputs(source, data)
            return {'local_url': self.write_asset(project_id, uuid.uuid4().hex+'_mask.png', data), 'sha256': assets.sha(data), 'generation_called': False}

    def gate(self, state, shot_id, source_url):
        if self.selected and self.selected()!=state['project_id']:raise ValueError('当前项目已切换')
        if self.paused(state['project_id'], self.database): raise ValueError('项目已暂停新生成')
        shot = next((s for s in state['shots'] if s['id'] == shot_id), None)
        if not shot or not workflow_state.valid_approval(state, shot): raise ValueError('须先审阅并批准当前原图与分镜')
        if shot.get('storyboard_local') != source_url: raise ValueError('原图不是当前批准图片')
        if assets.sha(assets.asset(self.root, state['project_id'], source_url)) != shot.get('storyboard_sha256'):
            raise ValueError('原图文件已变化，请重新审阅')
        return shot

    def execute(self, project_id, task_id):
        # Claim exactly once, with no network while holding the database transaction.
        with self.transaction() as con:
            state = self.state(con, project_id); task = self.task(state, task_id)
            if task['status'] != 'submitting': raise ValueError('原提交已领取，禁止自动重提')
            self.gate(state, task['shot_id'], task['source_url'])
            authorization_state = copy.deepcopy(state)
            authorization_state['image_tasks'] = [t for t in authorization_state['image_tasks'] if t['id'] != task_id]
            if self.authorize(authorization_state, self.database, 'image', 0, templates.MODEL_SCOPE, shot_id=task['shot_id']) != task['authorization_id']:
                raise ValueError('图片授权版本已变化')
            task['status'] = 'uploading'; self.save(con, state); task = copy.deepcopy(task)
        posted = False
        try:
            if templates.digest(task['request']) != task['request_sha256'] or task['template'] != templates.manifest() or task['dependency_snapshot'] != self.profile:
                raise ValueError('持久化执行契约已变化')
            source = assets.asset(self.root, project_id, task['archived_source']); mask = assets.asset(self.root, project_id, task['archived_mask'])
            if assets.sha(source) != task['source_sha256'] or assets.sha(mask) != task['mask_sha256']: raise ValueError('归档输入摘要不匹配')
            health = self.preflight()
            if not health['ready']: raise ValueError('执行依赖已变化')
            self.transport.upload(task_id+'_source.png', source); self.transport.upload(task_id+'_mask.png', mask)
            with self.transaction() as con:
                state = self.state(con, project_id); current = self.task(state, task_id)
                if current['status'] != 'uploading': raise ValueError('任务领取状态已变化')
                shot = self.gate(state, task['shot_id'], task['source_url'])
                if shot['approval_snapshot'] != task['approval_snapshot']: raise ValueError('原图审批已变化')
                authorization_state = copy.deepcopy(state)
                authorization_state['image_tasks'] = [t for t in authorization_state['image_tasks'] if t['id'] != task_id]
                if self.authorize(authorization_state, self.database, 'image', 0, templates.MODEL_SCOPE, shot_id=task['shot_id']) != task['authorization_id']:
                    raise ValueError('图片授权版本已变化')
            posted = True
            result = self.transport.request('/prompt', {'prompt': task['request'], 'client_id': task_id, 'extra_data': {'studio_task_id': task_id}})
            if result.get('error') and not result.get('prompt_id'):
                self.update(project_id, task_id, status='rejected', error='执行器明确拒绝工作流'); return self.get(project_id, task_id)
            prompt_id = result.get('prompt_id')
            if not isinstance(prompt_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', prompt_id): raise ValueError('未取得有效prompt_id')
            self.update(project_id, task_id, provider_task_id=prompt_id, status='queued')
        except Exception as exc:
            self.update(project_id, task_id, status='unknown' if posted else 'failed', error=str(exc))
        return self.get(project_id, task_id)

    def get(self, project_id, task_id):
        with self.transaction() as con: return copy.deepcopy(self.task(self.state(con, project_id), task_id))

    def update(self, project_id, task_id, **fields):
        with self.transaction() as con:
            state = self.state(con, project_id); task = self.task(state, task_id)
            if task['status'] in ('adopted', 'completed', 'failed', 'rejected'): return
            task.update(fields); self.save(con, state)

    def poll(self, project_id, task_id):
        task = self.get(project_id, task_id)
        if task['status'] in ('completed', 'adopted', 'failed', 'rejected'): return task
        if not task.get('provider_task_id'): raise ValueError('缺少原prompt_id，须核对，禁止重提')
        if task['status'] == 'archive_pending': return self.archive(project_id, task_id)
        try:
            history = self.transport.request('/history/'+task['provider_task_id']); entry = history.get(task['provider_task_id'])
            if not entry:
                queue = self.transport.request('/queue')
                status = 'running' if any(row[1] == task['provider_task_id'] for row in queue.get('queue_running', []) if len(row) > 1) else 'queued' if any(row[1] == task['provider_task_id'] for row in queue.get('queue_pending', []) if len(row) > 1) else 'unknown'
                self.update(project_id, task_id, status=status)
            elif entry.get('status', {}).get('status_str') == 'error': self.update(project_id, task_id, status='failed', error='工作流执行失败')
            elif entry.get('status', {}).get('completed'):
                images = entry.get('outputs', {}).get('9', {}).get('images', [])
                if len(images) != 1: raise ValueError('输出须为单张候选PNG')
                ref = images[0]
                if ref.get('type') != 'output' or ref.get('subfolder', '') != '' or not re.fullmatch(r'repair_'+task_id+r'_[A-Za-z0-9_-]+\.png', ref.get('filename', '')): raise ValueError('输出引用不符合模板约定')
                self.update(project_id, task_id, status='archive_pending', output_ref=ref)
                return self.archive(project_id, task_id)
            else: self.update(project_id, task_id, status='running')
        except Exception as exc: self.update(project_id, task_id, poll_error=str(exc))
        return self.get(project_id, task_id)

    def reconcile(self, project_id, task_id, prompt_id):
        """Explicit recovery using an existing ID, only with executor-side identity proof."""
        task = self.get(project_id, task_id)
        if task.get('provider_task_id') or task['status'] not in ('submitting', 'uploading', 'unknown'):
            raise ValueError('任务无需补关联')
        if not isinstance(prompt_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', prompt_id): raise ValueError('prompt_id无效')
        history = self.transport.request('/history/'+prompt_id)
        row = history.get(prompt_id, {}).get('prompt')
        if not row:
            queue = self.transport.request('/queue')
            rows = queue.get('queue_running', [])+queue.get('queue_pending', [])
            row = next((r for r in rows if len(r) > 3 and r[1] == prompt_id), None)
        if not row or len(row) < 4 or row[1] != prompt_id or row[3].get('studio_task_id') != task_id or templates.digest(row[2]) != task['request_sha256']:
            raise ValueError('执行器记录不能证明为原请求，继续锁定')
        with self.transaction() as con:
            state = self.state(con, project_id); current = self.task(state, task_id)
            if current.get('provider_task_id') or current['status'] not in ('submitting', 'uploading', 'unknown'):
                raise ValueError('任务关联状态已变化')
            current.update(provider_task_id=prompt_id, status='queued', recovery_source='matched executor graph and studio_task_id')
            self.save(con, state)
        return self.get(project_id, task_id)

    def archive(self, project_id, task_id):
        task = self.get(project_id, task_id)
        if task['status'] != 'archive_pending': raise ValueError('任务尚无可归档输出')
        try:
            result = self.transport.request('/view?'+urllib.parse.urlencode(task['output_ref']), raw=True)
            source = assets.asset(self.root, project_id, task['archived_source']); mask = assets.asset(self.root, project_id, task['archived_mask'])
            if assets.sha(source) != task['source_sha256'] or assets.sha(mask) != task['mask_sha256']: raise ValueError('归档输入已变化')
            candidate = assets.composite(source, mask, result)
            local = self.write_asset(project_id, task_id+'_candidate.png', candidate)
            self.update(project_id, task_id, status='completed', candidate_local=local, candidate_sha256=assets.sha(candidate), generated_sha256=assets.sha(result), review_status='pending', poll_error=None)
        except Exception as exc: self.update(project_id, task_id, poll_error=str(exc))
        return self.get(project_id, task_id)

    def adopt(self, project_id, revision, task_id, candidate_sha256, source):
        if not isinstance(source, str) or not source.strip() or len(source) > 500: raise ValueError('须记录人工采用来源')
        with self.transaction() as con:
            state = self.state(con, project_id, revision); task = self.task(state, task_id)
            if self.selected and self.selected()!=project_id:raise ValueError('当前项目已切换')
            if task['status'] != 'completed' or candidate_sha256 != task.get('candidate_sha256'): raise ValueError('请审阅当前候选版本')
            shot = next((s for s in state['shots'] if s['id'] == task['shot_id']), None)
            if not shot or shot.get('storyboard_local') != task['source_url'] or not workflow_state.valid_approval(state, shot) or shot.get('approval_snapshot') != task['approval_snapshot']:
                raise ValueError('当前镜头或原图审批已变化，不能覆盖')
            if assets.sha(assets.asset(self.root, project_id, task['source_url'])) != task['source_sha256']:
                raise ValueError('原图文件已变化，不能覆盖')
            candidate = assets.asset(self.root, project_id, task['candidate_local'])
            if assets.sha(candidate) != candidate_sha256: raise ValueError('候选文件已变化')
            shot.setdefault('image_review_history', []).append({'image_task_id': shot.get('storyboard_task_id'), 'local': shot['storyboard_local'], 'sha256': shot.get('storyboard_sha256'), 'approval_snapshot': copy.deepcopy(shot.get('approval_snapshot')), 'quality': shot.get('image_quality')})
            shot.update(storyboard_local=task['candidate_local'], storyboard_image=task['candidate_local'], storyboard_task_id=task_id, storyboard_sha256=candidate_sha256, approved=False, approved_image_task_id=None, approval_snapshot=None, image_quality='unreviewed', status='待检查')
            task.update(status='adopted', review_status='adopted_pending_approval', adoption_source=source.strip())
            self.save(con, state)
        return self.get(project_id, task_id)
