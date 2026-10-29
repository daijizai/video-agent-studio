"""Real image-provider adapters for material assets, with durable image reservations.

No text-model calls, no generation on reads/previews, no automatic unknown retry.
Asset image jobs live in the image ledger with kind=asset_image and NEVER shot_id.
"""
import base64
import copy
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal

import asset_library as library
import asset_templates
import generation_scope
import image_provider
import providers
import secret_store

MODELS = {'doubao-seedream-5-0-flash-260915': 'Seedream 5.0 Flash',
          'qwen-image-3.0-pro': 'Qwen Image3.0 Pro', 'qwen-image-3.0': 'Qwen Image3.0'}
LIVE = ('submitting', 'uploading', 'queued', 'running', 'unknown', 'archive_pending')
MASTER = {'character': 'portrait', 'object': 'main'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def download_image(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or not parsed.hostname or not any(
            parsed.hostname.endswith('.'+domain) for domain in ('aliyuncs.com', 'alicdn.com', 'qianwenaiapi.com', 'volces.com', 'byteimg.com')):
        raise ValueError('生成图片不在已允许的供应商下载域名')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError('不允许生成图片下载重定向')
    with urllib.request.build_opener(NoRedirect).open(url, timeout=30) as response:
        data = response.read(library.MAX_BYTES+1)
    library.inspect_image(data)
    return data


def prepare_storyboard(asset_service, shot, settings):
    """Use pinned material originals as real image inputs; never silently omit them.

    The manifest is durable/reconstructable without duplicating base64 pixels in
    every SQLite revision. The submitted payload's hash binds the exact bytes.
    """
    model=shot.get('image_model') or settings.get('image_model') or image_provider.DEFAULT_IMAGE_MODEL
    provider=image_provider.for_model(model)
    refs=shot.get('asset_references') or []
    project_id=shot.get('_material_project_id')
    if not refs and type(project_id) is not int:return provider.prepare(shot,settings)
    if type(project_id) is not int:raise ValueError('素材参考缺少项目绑定')
    with asset_service.lock,asset_service._connect() as con:
        con.execute('BEGIN');state=asset_service._load(con,project_id)
        by_id={a['id']:a for a in library.assets(state)}
        for ref in refs:
            asset=by_id.get(ref.get('asset_id'))
            if asset is None:raise ValueError('素材不属于当前项目')
            pinned=library._version(asset,ref.get('version'))
            asset_templates.verify_skill_source(asset_service.root,pinned.get('design_profile',{}),asset['kind'])
            expected=asset_templates.review_record(state,asset,pinned)
            if ref.get('production_review')!=expected:
                raise ValueError('素材设计或制作配方已变化，请按当前规范审阅并显式更新镜头引用；历史请求不改写')
    style=copy.deepcopy(state.get('project_style') or {})
    if not refs and not style:return provider.prepare(shot,settings)
    inputs=[];replacements={}
    for ref in refs:
        for view in ref['views']:
            data,info=asset_service._checked_view(project_id,view)
            minimum,maximum=(384,3072) if model.startswith('qwen') else (15,6000)
            if info['bytes']>10*1024*1024 or min(info['width'],info['height'])<minimum or max(info['width'],info['height'])>maximum:
                raise ValueError('所选素材不满足模型参考图尺寸或10MB限制')
            placeholder='https://material-reference.invalid/'+info['sha256']+'.'+info['extension']
            replacements[placeholder]='data:'+info['mime']+';base64,'+base64.b64encode(data).decode()
            inputs.append({'asset_id':ref['asset_id'],'version':ref['version'],'view_id':view['id'],'sha256':info['sha256'],'url':view['url']})
    spec=copy.deepcopy(shot)
    if style.get('prompt') or style.get('description'):spec['image_prompt']=(spec.get('image_prompt') or spec.get('prompt') or '')+'\n项目统一视觉风格：'+(style.get('prompt') or style['description'])
    style_ref=style.get('reference')
    if style_ref:
        data,info=asset_service._checked_view(project_id,style_ref)
        minimum,maximum=(384,3072) if model.startswith('qwen') else (15,6000)
        if info['bytes']>10*1024*1024 or min(info['width'],info['height'])<minimum or max(info['width'],info['height'])>maximum:raise ValueError('风格参考图不满足所选模型的尺寸或10MB限制')
        matching=next((i for i,item in enumerate(inputs) if item['sha256']==info['sha256']),None)
        if matching is None:
            marker='https://style-reference.invalid/'+info['sha256']+'.'+info['extension']
            replacements[marker]='data:'+info['mime']+';base64,'+base64.b64encode(data).decode()
            instruction='最后一张参考图仅参考色彩、光线和画面质感，不复制其中的人物、物品或构图。'
        else:
            instruction='第%d张参考图同时作为已绑定主体和视觉风格参考；只保持该主体本身及色彩光线，不复制无关背景或构图。'%(len(shot.get('reference_images') or [])+matching+1)
        spec['image_prompt']=(spec.get('image_prompt') or spec.get('prompt') or '')+'\n'+instruction
    spec['reference_images']=list(shot.get('reference_images') or [])+list(replacements)
    prepared=provider.prepare(spec,settings)
    def replace(value,manifest=False):
        if isinstance(value,str) and value in replacements:
            return ('material:sha256:'+value.rsplit('/',1)[1].split('.')[0]) if manifest else replacements[value]
        if isinstance(value,dict):return {k:replace(v,manifest) for k,v in value.items()}
        if isinstance(value,list):return [replace(v,manifest) for v in value]
        return value
    prepared['request_manifest']=replace(prepared['payload'],True)
    prepared['payload']=replace(prepared['payload'])
    prepared['material_reference_snapshot']=inputs
    prepared['style_snapshot']=style
    prepared['request_sha256']=digest(prepared['payload'])
    return prepared


class AssetGeneration:
    def __init__(self, asset_service, provider_factory=None, downloader=None, clock=None):
        self.lib = asset_service
        self.provider_factory = provider_factory or image_provider.for_model
        self.downloader = downloader or download_image
        self.clock = clock or time.time

    def _state(self, project_id):
        with self.lib.lock, self.lib._connect() as con:
            con.execute('BEGIN')
            return self.lib._load(con, project_id)

    def _update(self, project_id, fn, revision=None, selected=False):
        with self.lib.lock, self.lib._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            state = self.lib._load(con, project_id, revision, require_selected=selected)
            result = fn(state)
            state.pop('_write_revision', None); state.pop('workflow', None)
            body = json.dumps(state, ensure_ascii=False)
            con.execute('INSERT INTO revisions(body,project_id) VALUES (?,?)', (body, project_id))
            con.execute('UPDATE state SET body=? WHERE id=?', (body, project_id))
            return copy.deepcopy(result)

    def catalog(self, project_id):
        state = self._state(project_id); result = self.lib._public(state)
        adopted_urls={view['url'] for asset in result['assets'] if asset.get('adopted_version')
            for view in library._version(asset,asset['adopted_version']).get('views',[])}
        scope = generation_scope.read().get(str(project_id), {})
        bound = scope.get('database') == str(self.lib.database.resolve())
        grant = scope.get('budget_grants', {}).get('image') if bound else None
        paused = bool(bound and scope.get('paused'))
        budget = generation_scope.budget_summary(state, self.lib.database)['image']
        result.update(models=MODELS, default_model=state.get('settings', {}).get('image_model', image_provider.DEFAULT_IMAGE_MODEL),
            generation_enabled=bool(bound and not paused and grant and (budget.get('remaining_cny') or 0)>0 and generation_scope.active(project_id, self.lib.database)),
            allowed_models=list(scope.get('models',[])) if bound else [],
            generation_paused=paused, image_budget=budget,
            tasks=[{**{k: copy.deepcopy(t.get(k)) for k in ('id', 'batch_id', 'asset_id', 'asset_kind', 'asset_version', 'target_view',
                'view_label', 'name', 'model', 'status', 'estimate', 'actual_cost_cny', 'error', 'result_issue', 'download_error',
                'archived_version', 'next_eligible_at')},'currently_adopted':t.get('local_artifact') in adopted_urls} for t in state.get('image_tasks', []) if t.get('kind') == 'asset_image'],
            batches=copy.deepcopy(state.get('asset_generation_batches', [])))
        return result

    def _job(self, state, item, model):
        asset = next((a for a in library.assets(state) if a['id'] == item.get('asset_id')), None)
        if asset is None or type(item.get('version')) is not int:
            raise ValueError('请明确选择当前项目素材及版本')
        version = library._version(asset, item['version']); tag = item.get('view_tag')
        if tag not in library.VIEWS[asset['kind']]:
            raise ValueError('生成视图与素材类型不匹配')
        asset_templates.verify_skill_source(self.lib.root,version.get('design_profile',{}),asset['kind'])
        bundle=asset_templates.contract(state,asset,version,tag,model)
        selected=asset_templates.select_reference_views(state,asset,version,tag,model,item.get('reference_version'),item.get('reference_view_id'))
        references=[]
        for view in selected:
            _,info=self.lib._checked_view(state['project_id'],view)
            minimum,maximum=(384,3072) if model.startswith('qwen') else (15,6000)
            if info['bytes']>10*1024*1024 or min(info['width'],info['height'])<minimum or max(info['width'],info['height'])>maximum:
                raise ValueError('母版图片不满足所选模型的参考尺寸或10MB限制，请选择合适母版')
            references.append({'asset_id':asset['id'],'version':item['reference_version'],**copy.deepcopy(view)})
        bundle.pop('contract_hash')
        bundle['reference_bindings']=[{'asset_id':r['asset_id'],'version':r['version'],'view_id':r['id'],'tag':r['tag'],'sha256':r['sha256']} for r in references]
        bundle['reference_review']=copy.deepcopy(next((r for r in reversed(asset.get('production_reviews',[])) if references and r.get('asset_version')==item['reference_version']),None))
        bundle['contract_hash']=digest(bundle)
        name=version['name'];label=library.VIEWS[asset['kind']][tag]
        style=copy.deepcopy(state.get('project_style') or {})
        bundle['project_style']=style
        description=asset_templates.render_prompt(bundle)
        if style.get('prompt') or style.get('description'):description+='\n项目统一视觉风格（优先用于画风、光线和材质，不改变主体身份）：'+(style.get('prompt') or style['description'])
        if references:description+='\n仅使用绑定的已采用身份/全身/物品母版；保持同一外观，不重新设计。'
        markers = ['https://material-reference.invalid/'+v['sha256']+'.'+v['extension'] for v in references]
        style_ref=style.get('reference')
        if style_ref:
            _,info=self.lib._checked_view(state['project_id'],style_ref)
            minimum,maximum=(384,3072) if model.startswith('qwen') else (15,6000)
            if info['bytes']>10*1024*1024 or min(info['width'],info['height'])<minimum or max(info['width'],info['height'])>maximum:raise ValueError('风格参考图不满足所选模型的尺寸或10MB限制')
            matching=next((i for i,item in enumerate(references) if item['sha256']==info['sha256']),None)
            if matching is None:
                markers.append('https://style-reference.invalid/'+info['sha256']+'.'+info['extension'])
                description+='\n最后一张参考图仅参考色彩、光线和画面质感，不复制其中的人物、物品或构图。'
            else:description+='\n第%d张参考图同时作为该主体的已采用母版和项目风格参考；不要复制无关背景或构图。'%(matching+1)
        spec = {'image_prompt': description, 'reference_images': markers, 'image_model': model,
                'image_size':bundle['template']['size']}
        prepared = self.provider_factory(model).prepare(spec, {'image_model': model})
        payload = copy.deepcopy(prepared['payload'])
        bundle['concrete_mapping']=asset_templates.concrete_mapping(payload)
        bundle['provider_mapping_hash']=digest(bundle['concrete_mapping'])
        bundle.pop('contract_hash');bundle['contract_hash']=digest(bundle)
        def replace(value):
            if isinstance(value, str) and value in markers:
                return ('style:sha256:' if value.startswith('https://style-reference.invalid/') else 'material:sha256:')+value.rsplit('/',1)[1].split('.')[0]
            if isinstance(value, dict):return {k:replace(v) for k,v in value.items()}
            if isinstance(value, list):return [replace(v) for v in value]
            return value
        return {'asset_id': asset['id'], 'asset_kind': asset['kind'], 'asset_version': version['version'],
            'asset_snapshot': copy.deepcopy(version), 'target_view': tag, 'view_label': label,
            'name': name+' · '+label, 'model': model, 'provider': prepared['provider'],
            'request': replace(payload), 'reference_inputs': references, 'style_reference':style_ref, 'estimate': prepared['estimated_cny'],'production_contract':bundle,
            'is_identity_master':tag==bundle['blueprint']['master_plan']['identity_tag']}

    def _plan(self, state, items, model):
        if model not in MODELS or not isinstance(items, list) or not 1 <= len(items) <= 8:
            raise ValueError('请选择已接入图片模型及1–8张必要视图')
        jobs = [self._job(state, item, model) for item in items]
        pairs = [(j['asset_id'], j['target_view']) for j in jobs]
        if len(pairs) != len(set(pairs)):
            raise ValueError('同一素材的同一视图不能重复选择')
        if any(j['is_identity_master'] and any(
            k['asset_id'] == j['asset_id'] and k['target_view'] != j['target_view'] for k in jobs) for j in jobs):
            raise ValueError('请先审阅采用母版，再单独选择扩展视图')
        if any(j['asset_kind']=='character' and j['target_view']=='body_front' and any(
            k['asset_id']==j['asset_id'] and k['target_view']!='body_front' for k in jobs) for j in jobs):
            raise ValueError('请先单独生成并审阅全身正面母版，再补其它视图')
        total = float(sum((Decimal(str(j['estimate'])) for j in jobs), Decimal('0')))
        return {'jobs': jobs, 'estimated_cny': total, 'fingerprint': digest(jobs)}

    def preview(self, project_id, items, model):
        state = self._state(project_id); plan = self._plan(state, items, model)
        note='系统设计草案待审阅；每项1张独立图片。先采用身份母版，再建立并采用全身正面，之后才补独立侧背视图。预估不含自动重试。'
        if model=='doubao-seedream-5-0-flash-260915' and any(len(str(j['request'].get('prompt','')))>300 for j in plan['jobs']):
            note+=' 本次提示较长；Seedream官方建议中文约300字以内，过长可能使部分细节被忽略。这是建议，不会自动删减或阻止预览。'
        return {'project_id': project_id, 'revision': state['revision'], 'fingerprint': plan['fingerprint'],
            'estimated_cny': plan['estimated_cny'], 'network_called': False,
            'items': [{k:j[k] for k in ('asset_id','asset_kind','asset_version','target_view','view_label','name','estimate')} for j in plan['jobs']],
            'designs':[{'asset_id':j['asset_id'],'asset_version':j['asset_version'],**asset_templates.public_design(j['production_contract']['blueprint'])} for j in plan['jobs']],
            'note':note}

    def _authorize(self, state, estimate, model):
        pid = state['project_id']
        if generation_scope.is_paused(pid, self.lib.database):
            raise ValueError('当前项目已暂停新生成，素材制作不会自动恢复授权')
        scope = generation_scope.read().get(str(pid), {})
        if scope.get('budget_mode') != 'separate_v1':
            raise ValueError('素材生成需要明确的图片分类预算；不会挪用视频额度或旧镜头增量授权')
        return generation_scope.check(state, self.lib.database, 'image', estimate, model)

    def submit(self, project_id, revision, items, model, fingerprint, request_id):
        if not re.fullmatch(r'[a-f0-9]{32}', str(request_id)):
            raise ValueError('生成计划编号无效')
        def reserve(state):
            existing = next((b for b in state.get('asset_generation_batches', []) if b['id'] == request_id), None)
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise ValueError('计划编号已用于其他内容')
                return False
            plan = self._plan(state, items, model)
            if plan['fingerprint'] != fingerprint:
                raise ValueError('素材设定或引用已变化，请重新预览本次计划')
            targets = {(j['asset_id'], j['target_view']) for j in plan['jobs']}
            if any(t.get('status') in LIVE+('reserved',) and (t.get('asset_id'), t.get('target_view')) in targets for t in state.get('image_tasks', [])):
                raise ValueError('该素材视图已有在途或未知任务，请核对原任务，禁止重复提交')
            authorization = self._authorize(state, plan['estimated_cny'], model)
            # Credential presence is checked before a reservation; this makes no API call.
            self.provider_factory(model).headers()
            scope = copy.deepcopy(generation_scope.read()[str(project_id)])
            for job in plan['jobs']:
                task = {'id': uuid.uuid4().hex, 'batch_id': request_id, 'kind': 'asset_image',
                    'status': 'reserved', 'provider_task_id': None, 'submitted_epoch': 0,
                    'content_revision': state['revision'], 'authorization_id': authorization,
                    'authorization_scope_snapshot': scope, 'quality': 'unreviewed', **copy.deepcopy(job)}
                task['content_snapshot'] = {'project_id':project_id,'revision':state['revision'],
                    'asset_id':job['asset_id'],'kind':job['asset_kind'],'asset_version':job['asset_version'],
                    'asset':copy.deepcopy(job['asset_snapshot']),'reference_inputs':copy.deepcopy(job['reference_inputs']),
                    'production_contract':copy.deepcopy(job['production_contract']),
                    'story_title':state.get('title','')}
                state.setdefault('image_tasks', []).append(task)
            state.setdefault('asset_generation_batches', []).append({'id': request_id, 'fingerprint': fingerprint,
                'estimated_cny': plan['estimated_cny'], 'model': model, 'created_at': library._now(), 'user_confirmed': True})
            return True
        # A repeated request must not fail on its own newer reservation revision or re-submit.
        state = self._state(project_id)
        existing = next((b for b in state.get('asset_generation_batches', []) if b['id'] == request_id), None)
        if existing:
            if existing['fingerprint'] != fingerprint:raise ValueError('计划编号已用于其他内容')
            return self.catalog(project_id)
        created = self._update(project_id, reserve, revision=revision, selected=True)
        if created:self.advance(project_id, request_id)
        return self.catalog(project_id)

    def _hydrate(self, project_id, task):
        data_urls = {}
        for view in task['reference_inputs']:
            data, info = self.lib._checked_view(project_id, view)
            data_urls['material:sha256:'+info['sha256']] = 'data:'+info['mime']+';base64,'+base64.b64encode(data).decode()
        if task.get('style_reference'):
            data,info=self.lib._checked_view(project_id,task['style_reference'])
            data_urls['style:sha256:'+info['sha256']]='data:'+info['mime']+';base64,'+base64.b64encode(data).decode()
        def replace(value):
            if isinstance(value, str) and value.startswith(('material:sha256:','style:sha256:')):
                if value not in data_urls:raise ValueError('母版引用记录不完整')
                return data_urls[value]
            if isinstance(value, dict):return {k:replace(v) for k,v in value.items()}
            if isinstance(value, list):return [replace(v) for v in value]
            return value
        payload = replace(task['request'])
        return {'payload': payload, 'provider': task['provider'], 'estimated_cny': task['estimate']}

    def _validate_reserved_contract(self,state,task):
        saved=task.get('production_contract')
        if not saved:raise ValueError('旧计划没有当前素材制作配方，请取消未提交项并重新预览')
        if (saved.get('project_style') or {})!=(state.get('project_style') or {}):raise ValueError('项目风格已变化，请重新预览')
        asset=next(a for a in library.assets(state) if a['id']==task['asset_id'])
        latest=library._version(asset)
        if asset_templates.blueprint(state,asset,latest)['design_hash']!=saved['blueprint']['design_hash']:
            raise ValueError('设计已变化，请取消旧计划并重新预览')
        current=asset_templates.recipe(asset['kind'],task['target_view'],task['model'],latest.get('design_profile'))
        if current['recipe_hash']!=saved['recipe_hash']:
            raise ValueError('制作配方或模型映射已变化，请重新预览，不能沿用旧审批')
        item={'asset_id':task['asset_id'],'version':task['asset_version'],'view_tag':task['target_view']}
        if task['reference_inputs']:
            item.update(reference_version=task['reference_inputs'][0]['version'],reference_view_id=task['reference_inputs'][-1]['id'])
        concrete=self._job(state,item,task['model'])['production_contract']
        if concrete.get('provider_mapping_hash')!=saved.get('provider_mapping_hash'):
            raise ValueError('供应商实际参数映射已变化，请重新预览')
        if task['reference_inputs']:
            number=task['reference_inputs'][0]['version']
            refs=asset_templates.select_reference_views(state,asset,library._version(asset,task['asset_version']),task['target_view'],task['model'],number,None)
            saved_ids={r['id'] for r in task['reference_inputs']}
            if not {r['id'] for r in refs}.issubset(saved_ids):raise ValueError('母版引用已变化，请重新预览')

    def advance(self, project_id, batch_id):
        # This starts only a previously user-confirmed, durably reserved job.
        state = self._state(project_id)
        if not any(b['id'] == batch_id and b.get('user_confirmed') for b in state.get('asset_generation_batches', [])):
            raise ValueError('生成计划不存在或未确认')
        task = next((t for t in state.get('image_tasks', []) if t.get('batch_id') == batch_id and t.get('status') == 'reserved'), None)
        if task is None:return self.catalog(project_id)
        interval = 12.2 if task['model'].endswith('-pro') else 3.2
        last = max((float(t.get('submitted_epoch',0)) for t in state['image_tasks'] if t['status'] != 'rejected'), default=0)
        if self.clock()-last < interval:return self.catalog(project_id)
        self._validate_reserved_contract(state,task)
        prepared = self._hydrate(project_id, task); provider = self.provider_factory(task['model']); provider.headers()
        def begin(latest):
            current = next(t for t in latest['image_tasks'] if t['id'] == task['id'])
            if current['status'] != 'reserved':return False
            # Recheck the provider pacing window under the reservation transaction.
            last = max((float(t.get('submitted_epoch',0)) for t in latest['image_tasks'] if t['status'] != 'rejected'), default=0)
            if self.clock()-last < interval:return False
            other = copy.deepcopy(latest); other['image_tasks'] = [t for t in other['image_tasks'] if t['id'] != current['id']]
            authorization=self._authorize(other, current['estimate'], current['model'])
            current.update(status='submitting',submitted_epoch=self.clock(),request_sha256=digest(prepared['payload']),submitted_at=library._now(),
                execution_authorization_id=authorization,execution_scope_snapshot=copy.deepcopy(generation_scope.read()[str(project_id)]))
            return True
        if not self._update(project_id, begin, selected=True):return self.catalog(project_id)
        try:
            result = provider.submit(prepared, authorized=True)
        except Exception as error:
            def unknown(latest):
                current = next(t for t in latest['image_tasks'] if t['id'] == task['id'])
                # HTTP rejection is explicit; transport/timeouts remain unknown and reserved.
                rejected = isinstance(error, providers.ProviderHTTPError) and error.details.get('http_status') in (400,401,403,404,422)
                current.update(status='rejected' if rejected else 'unknown',error='供应商未受理' if rejected else '提交结果待核对；不会自动重提')
                if rejected:current['actual_cost_cny'] = 0
            self._update(project_id, unknown)
        else:
            def received(latest):
                current = next(t for t in latest['image_tasks'] if t['id'] == task['id'])
                if isinstance(result, str) and re.fullmatch(r'[A-Za-z0-9_-]+', result):
                    current.update(provider_task_id=result,status='queued')
                elif isinstance(result, dict):
                    current.update({k:copy.deepcopy(result.get(k)) for k in ('status','image_urls','usage','actual_cost_cny','provider_request_id')})
                    if current['status'] not in ('queued','running','completed','failed','cancelled','unknown'):
                        current.update(status='unknown',error='供应商返回了无法确认的状态，请核对原请求')
                else:current.update(status='unknown',error='供应商未返回可核对的任务编号或结果')
            self._update(project_id, received)
            self._archive(project_id, task['id'])
        return self.catalog(project_id)

    def _archive(self, project_id, task_id):
        with self.lib.lock, self.lib._connect() as con:
            state = self.lib._load(con, project_id, require_selected=False)
        task = next(t for t in state['image_tasks'] if t['id'] == task_id)
        if task['status'] != 'completed' or task.get('archived_version'):
            return
        urls = task.get('image_urls') or []
        if len(urls) != 1:
            self._update(project_id, lambda s:next(t for t in s['image_tasks'] if t['id']==task_id).update(result_issue='供应商未返回唯一单图；保留原结果待核对，不自动重做',quality='needs_review'))
            return
        try:
            data = self.downloader(urls[0]); info = library.inspect_image(data)
        except Exception:
            self._update(project_id, lambda s:next(t for t in s['image_tasks'] if t['id']==task_id).update(download_error='生成已完成，原图尚未归档；只重试下载，不重新生成'))
            return
        def archive(latest):
            current = next(t for t in latest['image_tasks'] if t['id']==task_id)
            if current.get('archived_version'):return
            asset = self.lib._asset(latest, current['asset_id'])
            siblings = [v for v in asset['versions'] if v.get('batch_id') == current['batch_id']]
            version = copy.deepcopy(siblings[-1] if siblings else current['asset_snapshot'])
            if current.get('is_identity_master',current['target_view']==MASTER[asset['kind']]):version['views']=[]
            image_id = current['id']; folder = self.lib._folder(project_id,create=True)
            file = folder/(image_id+'.'+info['extension'])
            try:
                if file.exists():
                    if file.is_symlink():raise ValueError('归档文件不可为符号链接')
                    with file.open('rb') as saved:existing=saved.read(library.MAX_BYTES+1)
                    if hashlib.sha256(existing).hexdigest()!=info['sha256']:
                        raise ValueError('归档文件冲突，保留原文件待核对')
                else:
                    with file.open('xb') as out:out.write(data);file.chmod(0o600)
                view = {'id':image_id,'tag':current['target_view'],'label':current['view_label'],
                    'url':f'/asset-media/{project_id}/{image_id}.{info["extension"]}', 'imported_at':library._now(),
                    'origin':{'type':'generated','task_id':task_id,'provider_url':urls[0],'model':current['model']},**info}
                if current.get('production_contract'):
                    view['production_binding']={key:current['production_contract'].get(key) for key in ('schema_version','contract_hash','reference_bindings')}
                    view['production_binding'].update(design_hash=current['production_contract']['blueprint']['design_hash'],recipe_hash=current['production_contract']['recipe_hash'],mapping_hash=current['production_contract']['mapping_hash'],provider_mapping_hash=current['production_contract']['provider_mapping_hash'])
                version.update(views=[v for v in version.get('views',[]) if v['tag']!=current['target_view']]+[view],
                    origin='generation',batch_id=current['batch_id'],base_version=current['asset_version'])
                if current.get('production_contract'):version['production_contract']=copy.deepcopy(current['production_contract'])
                appended=library._append(asset,version)
                current.update(archived_version=appended['version'],local_artifact=view['url'],quality='unreviewed')
                current.pop('download_error',None)
            except Exception:
                # Keep a durable original if the state commit fails; retry can use
                # the task-bound filename, and never overwrite another original.
                raise
        self._update(project_id,archive)

    def poll(self, project_id, task_id):
        state = self._state(project_id)
        task = next((t for t in state.get('image_tasks',[]) if t['id']==task_id and t.get('kind')=='asset_image'),None)
        if task is None:raise ValueError('当前项目没有该素材任务')
        if task['status']=='completed':
            if task.get('download_error'):self._archive(project_id,task_id)
            return self.catalog(project_id)
        if not task.get('provider_task_id') or task['status'] not in ('queued','running','unknown'):
            return self.catalog(project_id)
        try:
            result = self.provider_factory(task['model']).status(task['provider_task_id'])
        except Exception:
            self._update(project_id,lambda s:next(t for t in s['image_tasks'] if t['id']==task_id).update(error='原任务查询暂失败；不会重新提交'))
        else:
            def received(latest):
                current=next(t for t in latest['image_tasks'] if t['id']==task_id)
                if current['status'] in ('completed','failed','cancelled','rejected'):return
                current.update({k:copy.deepcopy(result.get(k)) for k in ('status','image_urls','usage','actual_cost_cny')})
                if current['status'] not in ('queued','running','completed','failed','cancelled','unknown'):
                    current['status']='unknown'
                current.pop('error',None)
            self._update(project_id,received);self._archive(project_id,task_id)
        return self.catalog(project_id)

    def cancel_reserved(self, project_id, batch_id):
        def cancel(state):
            for task in state.get('image_tasks',[]):
                if task.get('batch_id')==batch_id and task.get('status')=='reserved':
                    task.update(status='cancelled',actual_cost_cny=0,estimate=0,error='用户取消未提交的计划项；未调用供应商')
        self._update(project_id,cancel,selected=True)
        return self.catalog(project_id)
