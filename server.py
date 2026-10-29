#!/usr/bin/env python3
"""Local, dependency-free production workspace. No paid generation is enabled."""
import providers
import image_provider
import generation_scope
import media_files
import workflow_state
import storyboard_contract
import asset_library
import asset_generation
import base64
import comfy_executor
import seedream_edit
import re
import copy
from datetime import datetime,timezone
import time
import secret_store
import json, sqlite3, uuid, urllib.request, urllib.error, urllib.parse, os, threading, shutil, math
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
LOCK=threading.RLock()
def db():
    c=sqlite3.connect(DATA/'studio.db',timeout=30); c.execute('PRAGMA busy_timeout=30000'); c.row_factory=sqlite3.Row; return c
def init():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS revisions (id INTEGER PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP, body TEXT, project_id INTEGER DEFAULT 1)')
        if 'project_id' not in [r[1] for r in c.execute('PRAGMA table_info(revisions)')]:c.execute('ALTER TABLE revisions ADD COLUMN project_id INTEGER DEFAULT 1')
        c.execute('CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY, current_project INTEGER)')
        c.execute('INSERT OR IGNORE INTO workspace VALUES (1,1)')
        if not c.execute('SELECT 1 FROM state').fetchone():
            s={'title':'雾港来信','episode':'EP 01 · 消失的第七分钟','demo':True,'target_duration':30,'budget':120,'script':'雨夜，旧港口的钟楼突然停在 23:53。\n\n林雾收到一封来自七分钟后的语音。电话里，是她自己的声音：不要登上最后一班渡轮。\n\n陈渡在码头等她。他手中的船票，印着明天的日期。','continuity':'林雾始终佩戴银色旧手表；陈渡不知道语音的来源。港口时间停在 23:53。','characters':[{'id':'lin','name':'林雾','role':'主角 / 调查记者','version':1,'notes':'28 岁，黑色齐肩短发，灰色风衣，左腕银色旧手表。冷静、敏锐，右眉有细小伤疤。','color':'#729c9b'},{'id':'chen','name':'陈渡','role':'主角 / 渡轮驾驶员','version':1,'notes':'32 岁，深蓝工作夹克，短发，左手旧烧伤。说话克制，始终随身携带黄铜钥匙。','color':'#ac9071'}],'shots':[],'tasks':[],'settings':{'comfy_url':'','workflow':'','provider':'seedance25','resolution':'720p','audio':False,'image_model':image_provider.DEFAULT_IMAGE_MODEL},'events':['已载入示例策划内容；没有生成媒体或产生费用。']}
            for i,(name,frame,duration,prompt) in enumerate([('雾中的钟楼','远景 · 缓慢推进',8,'雨夜的旧港口，钟楼停在23:53，低饱和青绿色，电影光影'),('七分钟后的来电','近景 · 固定机位',6,'林雾站在雨棚下看手机，灰风衣，银色旧手表，冷光映在脸上'),('最后一班渡轮','全景 · 横向跟随',8,'陈渡站在渡轮入口，深蓝工作夹克，手持纸船票，海雾'),('明天的船票','特写 · 缓慢拉近',5,'湿润的纸船票与黄铜钥匙，背景虚化的港口灯光')]):
                s['shots'].append({'id':str(uuid.uuid4()),'name':name,'frame':frame,'duration':duration,'prompt':prompt,'approved':False,'status':'待确认','estimate':8,'review':'','asset':''})
            c.execute('INSERT INTO state VALUES (1,?)',(json.dumps(s,ensure_ascii=False),))
def cache_image(project_id,task_id,url):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password or not parsed.hostname or not any(parsed.hostname.endswith('.'+d) for d in ('aliyuncs.com','alicdn.com','qianwenaiapi.com','volces.com','byteimg.com')):raise ValueError('不支持的模型图片下载域名')
    path=ROOT/'assets'/str(project_id)/(task_id+'.png');path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kw):raise ValueError('不允许图片下载重定向')
        with urllib.request.build_opener(NoRedirect).open(url,timeout=30) as r:
            data=r.read(20*1024*1024+1)
            if len(data)>20*1024*1024 or not data.startswith((b'\x89PNG',b'\xff\xd8',b'RIFF')):raise ValueError('输出不是支持的图片或超过20MB')
        temp=path.with_suffix('.part')
        try:temp.write_bytes(data);temp.replace(path)
        finally:
            if temp.exists():temp.unlink()
    return '/media/'+str(project_id)+'/'+task_id+'.png'
def cache_sync_image(s,task):
    """Recover a durable sync result without submitting again or overwriting newer art."""
    shot=next(x for x in s['shots'] if x['id']==task['shot_id'])
    latest=next((t for t in reversed(s['image_tasks']) if t.get('shot_id')==shot['id'] and t['status']!='rejected' and (t.get('provider') not in ('comfy-masked-repair','seedream-edit') or t.get('status')=='adopted')),None)
    is_current=latest is not None and latest['id']==task['id']
    frozen=workflow_state.valid_approval(s,shot) and task['id']!=shot.get('approved_image_task_id')
    local=None
    try:
        local=cache_image(s['project_id'],task['id'],task['image_urls'][0]);task['local_artifact']=local;task.pop('download_error',None)
    except Exception:task['download_error']='图片已完成，本地缓存未完成；保留原结果，仅重试下载，不重新生成'
    if is_current and frozen:
        shot['pending_storyboard']={'task_id':task['id'],'local_artifact':local,'note':'已批准图冻结，新到候选不得静默替换或继承审批'}
    elif is_current:
        if shot.get('storyboard_task_id')!=task['id']:
            shot['approved']=False;shot['image_quality']='unreviewed';shot.pop('storyboard_local',None)
        shot['storyboard_task_id']=task['id'];shot['storyboard_image']=task['image_urls'][0];shot['image_status']='completed'
        if local:shot['storyboard_local']=local
def material_service():return asset_library.AssetLibrary(ROOT,DATA/'studio.db',LOCK)
def material_generation():return asset_generation.AssetGeneration(material_service())

def current_project():
    with db() as c:return c.execute('SELECT current_project FROM workspace WHERE id=1').fetchone()[0]
def read(project_id=None):
    project_id=project_id or current_project()
    with db() as c:
        c.execute('BEGIN')
        row=c.execute('SELECT body FROM state WHERE id=?',(project_id,)).fetchone()
        if not row:raise ValueError('项目不存在')
        s=json.loads(row[0]);s.setdefault('image_tasks',[]);s.setdefault('target_duration',30 if s.get('demo') else 120);s['project_id']=project_id;s['revision']=c.execute('SELECT COALESCE(MAX(id),0) FROM revisions WHERE project_id=?',(project_id,)).fetchone()[0];s['workflow']=workflow_state.derive(s);return s
def save(s):
    project_id=s.get('project_id',current_project())
    with LOCK, db() as c:
        c.execute('BEGIN IMMEDIATE')
        actual=c.execute('SELECT COALESCE(MAX(id),0) FROM revisions WHERE project_id=?',(project_id,)).fetchone()[0]
        if '_write_revision' in s and s['_write_revision']!=actual:raise ValueError('项目版本已变化，请刷新后重试')
        body=json.dumps(secret_store.redact({k:v for k,v in s.items() if k!='_write_revision'}),ensure_ascii=False)
        result=c.execute('INSERT INTO revisions(body,project_id) VALUES (?,?)',(body,project_id))
        c.execute('UPDATE state SET body=? WHERE id=?',(body,project_id))
        if '_write_revision' in s:s['_write_revision']=result.lastrowid

def project_list():
    with db() as c:
        items=[]
        for r in c.execute('SELECT id,body FROM state ORDER BY id'):
            s=json.loads(r['body']);items.append({'id':r['id'],'title':s['title'],'demo':s.get('demo',False)})
        return {'current_project':current_project(),'projects':items}
def create_project(title):
    title=str(title).strip()
    if not title or len(title)>80:raise ValueError('项目名称须为 1–80 个字符')
    s={'title':title,'episode':'','demo':False,'target_duration':120,'budget':0,'script':'','continuity':'','characters':[],'shots':[],'tasks':[],'image_tasks':[],
       'settings':{'comfy_url':'','workflow':'','provider':'seedance25','resolution':'720p','image_model':image_provider.DEFAULT_IMAGE_MODEL,'audio':False},'events':['新项目已创建；尚无生成任务。']}
    with db() as c:
        result=c.execute('INSERT INTO state(body) VALUES (?)',(json.dumps(secret_store.redact(s),ensure_ascii=False),));pid=result.lastrowid
        c.execute('UPDATE workspace SET current_project=? WHERE id=1',(pid,))
    return read(pid)
def remote(base,path,payload=None):
    parsed=urllib.parse.urlparse(base)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:raise ValueError('第一版仅允许本机 ComfyUI HTTP 地址。')
    req=urllib.request.Request(base.rstrip('/')+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('不允许 ComfyUI 重定向')
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect).open(req,timeout=6) as r:return json.load(r)
def content_snapshot(s,shot):
    return copy.deepcopy({'project_id':s['project_id'],'revision':s['revision'],'shot':shot,'characters':s['characters'],'continuity':s['continuity'],'settings':s['settings'],'sources':s.get('source_manifest',[]),'project_brief':s.get('project_brief','')})
def seedream_edit_service():
    return seedream_edit.SeedreamEditService(ROOT,DATA/'studio.db',lock=LOCK,selected=current_project)

def repair_service():
    """Operator-only profile. Browser settings cannot select models or files."""
    profile={}
    location=os.getenv('STUDIO_COMFY_PROFILE')
    if location:
        with open(location,'rb') as file:data=file.read(65537)
        if len(data)>65536:raise ValueError('增强配置过大')
        profile=json.loads(data)
        if not isinstance(profile,dict):raise ValueError('增强配置无效')
    return comfy_executor.RepairService(ROOT,DATA/'studio.db',comfy_executor.LocalTransport(profile.get('comfy_url','http://127.0.0.1:8188')),profile,lock=LOCK,selected=current_project)

def versioned_html(path):
    """Fingerprint local UI assets from their bytes, never a manually edited version."""
    import hashlib
    root=(ROOT/'static').resolve()
    def replace(match):
        name=match.group(2).split('?',1)[0]
        asset=(path.parent/name).resolve()
        if not asset.is_relative_to(root) or not asset.is_file():return match.group(0)
        stamp=hashlib.sha256(asset.read_bytes()).hexdigest()[:16]
        return match.group(1)+name+'?v='+stamp+match.group(3)
    return re.sub(r'((?:src|href)=")([^"?#]+\.(?:js|css)(?:\?[^"#]*)?)(")',replace,path.read_text()).encode('utf-8')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT/'static'),**kw)
    def end_headers(self):
        route=urllib.parse.urlsplit(self.path).path
        if route=='/' or route.endswith(('.html','.js','.css')):
            self.send_header('Cache-Control','no-cache, must-revalidate')
        super().end_headers()
    def send_head(self):
        import io
        route=urllib.parse.urlsplit(self.path).path
        if route in ('/','/index.html','/workspace.html'):
            content=versioned_html(ROOT/'static'/('workspace.html' if route=='/workspace.html' else 'index.html'))
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(content)))
            self.end_headers()
            return io.BytesIO(content)
        return super().send_head()
    def reply(self,data,status=200):
        b=json.dumps(secret_store.redact(data),ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def serve_media(self,head=False):
        if not re.fullmatch(r'/media/[0-9]+/[A-Za-z0-9_-]+\.(png|mp4|webm)',self.path):return self.reply({'error':'非法媒体路径'},400)
        base=(ROOT/'assets').resolve();path=(base/self.path.removeprefix('/media/')).resolve()
        if not path.is_relative_to(base) or not path.is_file():return self.reply({'error':'媒体不存在'},404)
        size=path.stat().st_size;start=0;end=size-1;status=200
        header=self.headers.get('Range')
        if header:
            match=re.fullmatch(r'bytes=([0-9]*)-([0-9]*)',header)
            valid=bool(match and (match[1] or match[2]) and size)
            if valid:
                if match[1]:start=int(match[1]);end=min(int(match[2]),size-1) if match[2] else size-1
                else:
                    suffix=int(match[2]);start=max(0,size-suffix);end=size-1;valid=suffix>0
                valid=valid and start<size and start<=end
            if not valid:
                self.send_response(416);self.send_header('Content-Range','bytes */'+str(size));self.send_header('Content-Length','0');self.end_headers();return
            status=206
        self.send_response(status);self.send_header('Content-Type',{'.png':'image/png','.mp4':'video/mp4','.webm':'video/webm'}[path.suffix]);self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','private, max-age=3600');self.send_header('Content-Length',str(max(0,end-start+1)))
        if status==206:self.send_header('Content-Range','bytes '+str(start)+'-'+str(end)+'/'+str(size))
        self.end_headers()
        if head:return
        try:
            with open(path,'rb') as f:
                f.seek(start);remaining=end-start+1
                while remaining>0:
                    chunk=f.read(min(65536,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):return
    def serve_material(self,head=False):
        try:
            match=re.fullmatch(r'/asset-media/([1-9][0-9]*)/[a-f0-9]{32}\.(png|jpg|webp)',self.path)
            if not match:raise ValueError('素材地址无效')
            data,info=material_service().media(int(match[1]),self.path)
            self.send_response(200);self.send_header('Content-Type',info['mime']);self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','private, max-age=3600');self.end_headers()
            if not head:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):return
        except Exception:return self.reply({'error':'素材图片不可用或不属于当前项目'},404)

    def handle_material(self,p):
        try:
            pid=p.get('project_id');action=self.path.removeprefix('/api/assets/')
            if action.startswith('generation/'):
                service=material_generation();action=action.removeprefix('generation/')
                if action=='preview':result=service.preview(pid,p.get('items'),p.get('model'))
                elif action=='submit':result=service.submit(pid,p.get('revision'),p.get('items'),p.get('model'),p.get('fingerprint'),p.get('request_id'))
                elif action=='poll':result=service.poll(pid,p.get('task_id'))
                elif action=='advance':result=service.advance(pid,p.get('batch_id'))
                elif action=='cancel':result=service.cancel_reserved(pid,p.get('batch_id'))
                else:raise ValueError('未知素材生成操作')
            else:result=material_service().mutate(pid,p.get('revision'),action,p)
            return self.reply(result)
        except ValueError as error:return self.reply({'error':secret_store.redact(str(error))},400)
        except Exception:return self.reply({'error':'素材操作未完成，请刷新并核对原记录；不会自动重新生成'},400)

    def do_HEAD(self):
        if self.path.startswith('/asset-media/'):return self.serve_material(head=True)
        if self.path.startswith('/media/'):return self.serve_media(head=True)
        return super().do_HEAD()
    def do_GET(self):
        if self.path.startswith('/asset-media/'):return self.serve_material()
        if self.path in ('/api/assets','/api/assets/propose'):
            try:
                pid=current_project()
                return self.reply(material_service().propose(pid) if self.path.endswith('/propose') else material_generation().catalog(pid))
            except Exception:return self.reply({'error':'素材库暂不可用，请刷新当前项目'},400)
        if self.path.startswith('/media/'):return self.serve_media()
        if self.path=='/api/projects':return self.reply(project_list())
        if self.path=='/api/state':return self.reply(read())
        if self.path=='/api/health':
            s=read();active=generation_scope.active(s['project_id'],DATA/'studio.db');scope=generation_scope.read().get(str(s['project_id']),{});scope=scope if scope.get('database')==str((DATA/'studio.db').resolve()) else {}
            budgets=generation_scope.budget_summary(s,DATA/'studio.db');separate=scope.get('budget_mode')=='separate_v1'
            image_count=sum(t['status']!='rejected' for t in s['image_tasks']);video_count=sum(t['status']!='rejected' for t in s['tasks'])
            return self.reply({'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),'paid_generation':active,'generation_paused':bool(scope.get('paused')),'wan3_credential_present':bool(secret_store.get_key('WAN3_API_KEY')),'image_generation':active and (budgets['image']['authorized'] and budgets['image']['remaining_cny']>0 if separate else image_count<scope.get('image_limit',0)),'video_generation':active and (budgets['video']['authorized'] and budgets['video']['remaining_cny']>0 if separate else video_count<scope.get('video_limit',0)),'budgets':budgets,'budget_mode':scope.get('budget_mode','legacy'),'image_limit':scope.get('image_limit',0),'video_limit':scope.get('video_limit',0)})
        if self.path=='/api/budgets':return self.reply(generation_scope.budget_summary(read(),DATA/'studio.db'))
        if self.path=='/api/repair/preflight':
            try:
                result=seedream_edit_service().preflight();state=read()
                try:
                    generation_scope.check(state,DATA/'studio.db','image',seedream_edit.PRICE,seedream_edit.MODEL)
                    result['execution_allowed']=True
                except Exception:result['execution_allowed']=False
                result['resumable_task_ids']=[]
                for task in state['image_tasks']:
                    if task.get('provider')!='seedream-edit' or task.get('kind')=='asset_image' or task.get('status')!='submitting':continue
                    scoped=copy.deepcopy(state);scoped['image_tasks']=[t for t in scoped['image_tasks'] if t['id']!=task['id']]
                    try:
                        if generation_scope.check(scoped,DATA/'studio.db','image',task['estimate'],task['request_model'],shot_id=task['shot_id'])==task['authorization_id']:result['resumable_task_ids'].append(task['id'])
                    except Exception:pass
                result['backend']='seedream';return self.reply(result)
            except Exception:return self.reply({'ready':False,'execution_allowed':False,'backend':'seedream','api_verified':False,'quality_verified':False})
        if self.path=='/api/comfy/preflight':
            try:return self.reply(repair_service().public_preflight())
            except Exception:return self.reply({'ready':False,'message':'局部修复暂不可用','quality_verified':False,'generation_called':False})
        if self.path=='/api/comfy/diagnostics':
            try:return self.reply(repair_service().preflight())
            except Exception as error:return self.reply({'ready':False,'issues':[str(error)],'quality_verified':False})
        if self.path=='/api/providers':return self.reply(providers.config_status(read()))
        if self.path=='/api/export':return self.reply(read())
        if self.path=='/api/revisions':
            with db() as c:return self.reply([dict(r) for r in c.execute('SELECT id,created,body FROM revisions WHERE project_id=? ORDER BY id DESC LIMIT 30',(current_project(),))])
        return super().do_GET()
    def handle_edit(self,p,action=None,state_response=False):
        action=action or self.path.removeprefix('/api/repair/')
        try:
            with LOCK:
                state=read();pid=p.get('project_id')
                if type(pid) is not int or pid!=state['project_id']:raise ValueError('项目已切换')
                if action in ('begin','adopt') and p.get('revision')!=state['revision']:raise ValueError('项目版本已变化')
                if action=='begin':
                    backend=p.get('backend','seedream')
                    if backend not in ('seedream','local'):raise ValueError('未知执行方式')
                else:
                    task=next((t for t in state['image_tasks'] if t.get('id')==p.get('task_id')),None)
                    if not task or task.get('kind')=='asset_image' or task.get('provider') not in ('seedream-edit','comfy-masked-repair'):raise ValueError('不是镜头修复任务')
                    backend='seedream' if task['provider']=='seedream-edit' else 'local'
            if backend=='local':return self.handle_repair(p,action=action,state_response=state_response)
            service=seedream_edit_service()
            if action=='begin':result=service.begin(pid,p['revision'],p['shot_id'],p['source_url'],p['region'],p['description'],p['request_id'])
            elif action=='execute':result=service.execute(pid,p['task_id'])
            elif action=='poll':result=service.poll(pid,p['task_id'])
            elif action=='adopt':result=service.adopt(pid,p['revision'],p['task_id'],p['candidate_sha256'],secret_store.redact(p.get('source','')))
            else:raise ValueError('未知编辑操作')
            return self.reply(read(pid) if state_response else result)
        except Exception:
            return self.reply({'error':'图片编辑未完成。请核对当前画面、图片预算和执行许可；结果不明时请勿重复提交。'},400)

    def handle_repair(self,p,action=None,state_response=False):
        action=action or self.path.removeprefix('/api/comfy/')
        try:
            with LOCK:
                state=read();pid=p.get('project_id')
                if type(pid) is not int or pid!=state['project_id']:raise ValueError('当前项目已切换，请刷新')
                if action in ('mask','begin','adopt') and p.get('revision')!=state['revision']:raise ValueError('项目版本已变化，请刷新')
            service=repair_service()
            if action=='mask':
                value=p.get('png_base64')
                if not isinstance(value,str) or len(value)>28*1024*1024:raise ValueError('遮罩无效')
                result=service.import_mask(pid,p['revision'],p['shot_id'],base64.b64decode(value,validate=True))
            elif action=='begin':result=service.begin(pid,p['revision'],p['shot_id'],p['source_url'],p['mask_url'],p['values'],p['request_id'])
            elif action=='execute':result=service.execute(pid,p['task_id'])
            elif action=='poll':result=service.poll(pid,p['task_id'])
            elif action=='adopt':result=service.adopt(pid,p['revision'],p['task_id'],p['candidate_sha256'],secret_store.redact(p.get('source','')))
            elif action=='reconcile':result=service.reconcile(pid,p['task_id'],p['prompt_id'])
            else:raise ValueError('未知修复操作')
            return self.reply(read(pid) if state_response else result)
        except Exception:
            # Raw graph, filesystem and dependency errors belong to diagnostics only.
            return self.reply({'error':'局部修复操作未完成。请刷新并核对原任务；当前画面、审批、暂停与授权仍须有效。'},400)

    def do_POST(self):
        try:
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://'+self.headers.get('Host',''):raise ValueError('拒绝跨站写入')
            n=int(self.headers.get('Content-Length','0'))
            if n<0 or n>(28*1024*1024 if self.path=='/api/comfy/mask' else 17*1024*1024 if self.path in ('/api/assets/upload','/api/assets/style') else 2000000):raise ValueError('请求过大')
            p=json.loads(self.rfile.read(n) or b'{}')
            if not isinstance(p,dict):raise ValueError('请求须为对象')
            if self.path.startswith('/api/assets/'):
                return self.handle_material(p)
            if self.path.startswith('/api/comfy/'):
                return self.handle_repair(p)
            if self.path.startswith('/api/repair/'):
                return self.handle_edit(p)
            # Route repair image polling before the legacy global-lock handler.
            if self.path=='/api/image/poll':
                with LOCK:
                    snapshot=read()
                    is_material=any(t['id']==p.get('task_id') and t.get('kind')=='asset_image' for t in snapshot['image_tasks'])
                    is_repair=any(t['id']==p.get('task_id') and t.get('provider') in ('comfy-masked-repair','seedream-edit') and t.get('kind')!='asset_image' for t in snapshot['image_tasks'])
                if is_material:
                    try:
                        material_generation().poll(p.get('project_id'),p.get('task_id'));return self.reply(read(p.get('project_id')))
                    except Exception:return self.reply({'error':'素材原任务查询未完成，请在素材库核对'},400)
                if is_repair:return self.handle_edit(p,action='poll',state_response=True)
            with LOCK:
                action=self.path
                if action=='/api/projects/new':return self.reply(create_project(p.get('title','')))
                if action=='/api/projects/switch':
                    project_id=int(p['project_id']);result=read(project_id)
                    with db() as c:c.execute('UPDATE workspace SET current_project=? WHERE id=1',(project_id,))
                    return self.reply(result)
                s=read();s['_write_revision']=s['revision']
                if action in ('/api/submit','/api/image/submit','/api/provider/submit','/api/sequence/submit') and generation_scope.is_paused(s['project_id'],DATA/'studio.db'):raise ValueError('用户已暂停本项目新生成；预算和历史保留，不能提交新媒体')
                if 'project_id' in p and int(p['project_id'])!=s['project_id']:raise ValueError('当前项目已切换，请刷新页面后再保存')
                if 'revision' in p and int(p['revision'])!=s['revision']:raise ValueError('项目已被其他窗口或CLI修改，请刷新后重试')
                if action=='/api/save':
                    previous_shots=copy.deepcopy(s['shots'])
                    for key in ['title','episode','script','continuity','characters','shots','budget','target_duration','production_demo','sequence_prompt','authorization_note','source_manifest','project_brief','quality_lessons','final_video','budget_authorizations']:
                        if key in p:s[key]=p[key]
                    if not 1<=float(s.get('target_duration',120))<=300:raise ValueError('项目目标时长须为1–300秒')
                    if not 0<=float(s['budget'])<=100000:raise ValueError('预算必须为 0–100000')
                    if any(not 0<=float(x['estimate'])<=100000 for x in s['shots']):raise ValueError('估价必须为 0–100000')
                    if any(not 1<=float(x['duration'])<=300 for x in s['shots']):raise ValueError('镜头时长须为 1–300 秒')
                    if sum(float(x['duration']) for x in s['shots'])>300:raise ValueError('单集总时长不可超过 5 分钟')
                    previous_by_id={shot['id']:shot for shot in previous_shots}
                    if any((shot.get('asset_references') or [])!=(previous_by_id.get(shot['id'],{}).get('asset_references') or []) for shot in s['shots']):raise ValueError('请通过镜头的素材选择入口更改版本引用，不能直接覆盖引用记录')
                    storyboard_contract.validate_shots(s['shots'])
                    storyboard_contract.invalidate_changed(previous_shots,s['shots'])
                elif action=='/api/approvals/shot':
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    if p.get('approved',True):
                        if p.get('image_task_id')!=shot.get('storyboard_task_id'):raise ValueError('当前图片已变化，请重读后审阅')
                        local=shot.get('storyboard_local','')
                        if not re.fullmatch(r'/media/'+str(s['project_id'])+r'/[A-Za-z0-9_-]+\.png',local):raise ValueError('当前图片必须已下载本机')
                        asset=(ROOT/'assets'/local.removeprefix('/media/')).resolve()
                        if not asset.is_relative_to((ROOT/'assets').resolve()) or not asset.is_file():raise ValueError('当前图片尚不可审阅')
                        shot['storyboard_sha256']=__import__('hashlib').sha256(asset.read_bytes()).hexdigest()
                        asset_library.validate_references(s,shot,material_service())
                        shot['approval_snapshot']=workflow_state.record_approval(s,shot,secret_store.redact(str(p.get('source','用户明确审阅当前分镜图片与内容'))[:500]),datetime.now(timezone.utc).isoformat())
                        shot['approved_image_task_id']=shot['storyboard_task_id'];shot['approved']=True;shot['image_quality']='approved'
                        if s['settings'].get('provider')=='seedance25':
                            import ark_provider
                            shot['ark_reference_approval']=ark_provider.reference_binding(shot)
                    else:shot['approved']=False;shot['image_quality']='unreviewed'
                elif action=='/api/budgets/authorize':
                    source=str(p.get('source','local user confirmation'))[:500]
                    record=generation_scope.authorize_budgets(s['project_id'],DATA/'studio.db',p.get('image_limit'),p.get('video_limit'),source,s['revision'],models=p.get('models'),local_repair_limit=p.get('local_repair_limit'))
                    s['budget_authorizations']=generation_scope.read()[str(s['project_id'])]['budget_authorization_history']
                elif action=='/api/settings':
                    s['settings']={**s['settings'], **{k:p[k] for k in ('comfy_url','workflow','provider','resolution','audio','ratio','image_model') if k in p}}
                elif action=='/api/credentials':
                    name=providers.CATALOG.get(p.get('provider'),{}).get('key_env')
                    secret_store.write_key(name,p.get('value'))
                    return self.reply({'saved':True,'credential_present':True,'connection':'unverified'})
                elif action=='/api/image/prepare':
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    prepared=asset_generation.prepare_storyboard(material_service(),{**shot,'_material_project_id':s['project_id']},s['settings'])
                    return self.reply({**prepared,'payload':prepared.get('request_manifest',prepared['payload'])})
                elif action=='/api/image/submit':
                    if not generation_scope.active(s['project_id'],DATA/'studio.db'):raise ValueError('当前项目无图像生成授权')
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    previous=[t for t in s['image_tasks'] if t.get('shot_id')==shot['id']]
                    if any(t['status'] in tuple(comfy_executor.LIVE)+('reserved',) for t in previous):raise ValueError('该镜头已有在途或未知图像任务，请查询原任务，禁止重复提交')
                    if previous and not p.get('redo'):raise ValueError('重生成须明确指定redo；历史图像保留')
                    interval=12.2 if (shot.get('image_model') or s['settings'].get('image_model') or image_provider.DEFAULT_IMAGE_MODEL).endswith('-pro') else 3.2
                    if any(time.time()-float(t.get('submitted_epoch',0))<interval for t in s['image_tasks'] if t['status']!='rejected'):raise ValueError('图片提交尚未满足该模型平滑间隔，请稍后提交；未发起模型请求')
                    provider=image_provider.for_model(shot.get('image_model') or s['settings'].get('image_model'));prepared=asset_generation.prepare_storyboard(material_service(),{**shot,'_material_project_id':s['project_id']},s['settings']);provider.headers()
                    task={'id':str(uuid.uuid4()),'submitted_at':datetime.now(timezone.utc).isoformat(),'submitted_epoch':time.time(),'shot_id':shot['id'],'name':shot['name'],'provider_task_id':None,'status':'submitting','estimate':prepared['estimated_cny'],'request':prepared.get('request_manifest',prepared['payload'])}
                    if prepared.get('style_snapshot'):task['style_snapshot']=prepared['style_snapshot'];task['request_sha256']=prepared['request_sha256']
                    if prepared.get('material_reference_snapshot'):
                        task['material_reference_snapshot']=prepared['material_reference_snapshot'];task['request_sha256']=prepared['request_sha256']
                    task['provider']=prepared['provider']
                    task['content_revision']=s['revision'];task['content_snapshot']=content_snapshot(s,shot)
                    task['authorization_id']=generation_scope.check(s,DATA/'studio.db','image',task['estimate'],prepared['payload']['model'],shot_id=shot['id'])
                    task['authorization_scope_snapshot']=copy.deepcopy(generation_scope.read()[str(s['project_id'])])
                    if shot.get('storyboard_local') or shot.get('storyboard_image'):
                        old=previous[-1] if previous else {}
                        shot.setdefault('image_review_history',[]).append({'image_task_id':shot.get('storyboard_task_id',old.get('id')),'quality':shot.get('image_quality'),'user_feedback':shot.get('user_feedback'),'review':shot.get('review')})
                    shot.pop('user_feedback',None);shot['review']='本次新图尚未审阅；历史反馈绑定旧图保留。';shot['image_quality']='generating';shot['current_image_task_id']=task['id']
                    s['image_tasks'].append(task);shot['approved']=False;save(s)
                    try:
                        result=provider.submit(prepared,authorized=True)
                        if isinstance(result,dict):
                            task.update(result)
                            # Synchronous Ark response is durable before attempting downloads.
                            save(s)
                            cache_sync_image(s,task)
                        else:task['provider_task_id']=result;task['status']='queued'
                    except Exception as error:task['status']='unknown';task['error']=str(error);task['error_details']=getattr(error,'details',{});save(s);raise ValueError('图像提交结果已记录：'+str(error))
                    shot['image_status']=task['status']
                elif action=='/api/image/reconcile-rate-limit':
                    task=next(t for t in s['image_tasks'] if t['id']==p['task_id'])
                    if task.get('provider_task_id') or 'HTTP 429 / Throttling.RateQuota' not in task.get('error',''):raise ValueError('仅可核对明确429且未取得任务编号的拒绝请求')
                    if not re.fullmatch(r'[A-Za-z0-9_-]+',p.get('request_id','')):raise ValueError('请提供官方调用日志requestId')
                    task['rejected_estimate']=task['estimate'];task['estimate']=0;task['status']='rejected'
                    task['rejection_evidence']={'request_id':p['request_id'],'source':'official CLI usage logs','http_status':429,'usages':[],'note':'已核对调用记录：请求未受理，不是超时未知任务；原记录保留，未自动重试'}
                    next(x for x in s['shots'] if x['id']==task['shot_id'])['image_status']='rejected'
                elif action=='/api/image/poll':
                    task=next(t for t in s['image_tasks'] if t['id']==p['task_id'])
                    if task.get('provider')=='seedream':
                        if task.get('status')!='completed':raise ValueError('方舟同步图像请求结果待核对；没有异步任务可查询，禁止重提')
                        # Retry only local caching; no supplier generation/status call exists for sync images.
                        task['last_checked_at']=datetime.now(timezone.utc).isoformat()
                        cache_sync_image(s,task)
                        save(s);return self.reply(read())
                    if not task['provider_task_id']:raise ValueError('缺少图像任务ID，请人工核对')
                    task['last_checked_at']=datetime.now(timezone.utc).isoformat()
                    try:
                        result=image_provider.ImageProvider().status(task['provider_task_id']);task.update(result);task.pop('poll_error',None)
                    except Exception as error:
                        task['poll_error']=str(error);save(s);return self.reply(read())
                    shot=next(x for x in s['shots'] if x['id']==task['shot_id'])
                    latest=next((t for t in reversed(s['image_tasks']) if t.get('shot_id')==shot['id'] and t['status']!='rejected' and (t.get('provider') not in ('comfy-masked-repair','seedream-edit') or t.get('status')=='adopted')),None)
                    is_current=latest is not None and latest['id']==task['id']
                    frozen=workflow_state.valid_approval(s,shot) and task['id']!=shot.get('approved_image_task_id')
                    if is_current and not frozen:shot['image_status']=result['status']
                    if result['status']=='completed' and result['image_urls']:
                        local=None
                        try:local=cache_image(s['project_id'],task['id'],result['image_urls'][0]);task['local_artifact']=local;task.pop('download_error',None)
                        except Exception:task['download_error']='图片已生成，但本地下载未完成；可再次查询原任务，不会重新生成'
                        if is_current and frozen:shot['pending_storyboard']={'task_id':task['id'],'local_artifact':local,'note':'已批准图冻结，新到候选不得静默替换或继承审批'}
                        if is_current and not frozen:
                            if shot.get('storyboard_task_id')!=task['id']:
                                shot['approved']=False;shot['image_quality']='unreviewed'
                            shot['storyboard_task_id']=task['id'];shot['storyboard_image']=result['image_urls'][0]
                            if local:shot['storyboard_local']=local
                elif action=='/api/provider/preview':
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    return self.reply(providers.Provider(s['settings'].get('provider','seedance25')).prepare(shot,s['settings']))
                elif action=='/api/provider/submit':
                    if not generation_scope.active(s['project_id'],DATA/'studio.db'):raise ValueError('付费生成未授权，当前仅允许零请求预览')
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    if not workflow_state.valid_approval(s,shot):raise ValueError('请先批准当前图片和内容版本；旧审批或文字确认不能替代')
                    previous=[t for t in s['tasks'] if t.get('shot_id')==shot['id']]
                    if any(t['status'] in ('submitting','queued','running','unknown') for t in previous):raise ValueError('该镜头有在途或未知任务，禁止重复提交')
                    if previous and not p.get('redo'):raise ValueError('已有终态任务；语义上需要重做时明确指定redo，仍检查本类别预算')
                    provider=providers.Provider(s['settings'].get('provider','seedance25'))
                    if provider.id=='seedance25':
                        import ark_provider
                        ark_provider.require_reference_approval(shot)
                    prepared=provider.prepare(shot,s['settings'])
                    estimate=max(float(shot['estimate']),prepared['estimated_cny'])
                    provider.headers();provider.base_url() # Validate credentials/config before durable submission intent.
                    task={'id':str(uuid.uuid4()),'shot_id':shot['id'],'name':shot['name'],'provider':provider.id,'provider_task_id':None,'status':'submitting','estimate':estimate,'request':prepared['payload']}
                    task['content_revision']=s['revision'];task['content_snapshot']=content_snapshot(s,shot)
                    task['authorization_id']=generation_scope.check(s,DATA/'studio.db','video',estimate,prepared['payload']['model'])
                    s['tasks'].append(task);save(s)
                    try:
                        task['provider_task_id']=provider.submit(prepared,task['id'],authorized=True);task['status']='queued';shot['status']='排队中'
                    except Exception:
                        task['status']='unknown';save(s);raise ValueError('供应商提交结果不确定，已锁定重试。请在供应商控制台核对')
                elif action=='/api/provider/poll':
                    task=next(t for t in s['tasks'] if t['id']==p['task_id'])
                    if not task.get('provider_task_id'):raise ValueError('缺少任务编号，禁止自动重试')
                    task['last_checked_at']=datetime.now(timezone.utc).isoformat()
                    try:
                        result=providers.Provider(task['provider']).status(task['provider_task_id']);task.pop('poll_error',None)
                    except Exception as error:
                        task['poll_error']=str(error);save(s);return self.reply(read())
                    task.update(result)
                    if result['status']=='completed' and result.get('video_url'):
                        try:task['local_video'],task['media_info']=media_files.cache_video(ROOT,s['project_id'],task['id'],result['video_url']);task.pop('download_error',None)
                        except Exception:task['download_error']='视频已生成，本地下载未完成；可再次查询原任务，不会重生成'
                    if task.get('kind')=='sequence':
                        if task.get('local_video'):
                            prior=s.get('final_video') or {};kept=prior if prior.get('task_id')==task['id'] else {}
                            s['final_video']={**kept,'local_url':task['local_video'],'task_id':task['id'],'media_info':task.get('media_info',{}),'review_status':kept.get('review_status','pending'),'approval_snapshot':task.get('approval_snapshot',[])}
                    else:next(x for x in s['shots'] if x['id']==task['shot_id'])['status']='待检查' if result['status']=='completed' else result['status']
                elif action=='/api/connect':
                    r=remote(s['settings']['comfy_url'],'/system_stats');return self.reply({'connected':True,'system':r})
                elif action=='/api/submit':
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    if not (shot.get('text_approved') or shot['approved']):raise ValueError('请先确认该镜头文字分镜')
                    if any(t.get('shot_id')==shot['id'] and t['status'] not in ['failed','cancelled'] for t in s['tasks']):raise ValueError('已有执行记录，请查询原任务，禁止重复提交')
                    reserved=sum(t['estimate'] for t in s['tasks']+s.get('image_tasks',[]) if t['status']!='cancelled')
                    if reserved+float(shot['estimate'])>float(s['budget']):raise ValueError('预占金额将超过本集预算')
                    workflow=json.loads(s['settings']['workflow'])
                    if not isinstance(workflow,dict) or not workflow:raise ValueError('请导入 ComfyUI API 格式工作流')
                    project_style=s.get('project_style') or {}
                    if project_style.get('reference'):raise ValueError('该本机工作流暂不支持项目风格参考图，请使用已支持的图片生成方式')
                    if (project_style.get('prompt') or project_style.get('description')) and not any(n.get('class_type')=='CLIPTextEncode' and '{{prompt}}' in n.get('inputs',{}).get('text','') for n in workflow.values()):raise ValueError('该工作流缺少可绑定项目风格的提示入口')
                    # Hard gate: arbitrary workflows can call paid nodes. V1 permits a small local-only allowlist.
                    allowed={'CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','SaveImage','LoadImage','PreviewImage'}
                    if any(node.get('class_type') not in allowed for node in workflow.values()):raise ValueError('工作流含未审计节点；第一版禁止外部付费与自定义节点')
                    for node in workflow.values():
                        if node.get('class_type')=='CLIPTextEncode':node['inputs']['text']=node['inputs'].get('text','').replace('{{prompt}}',shot['prompt']+('\n项目统一视觉风格：'+(project_style.get('prompt') or project_style['description']) if project_style.get('prompt') or project_style.get('description') else ''))
                    task={'id':str(uuid.uuid4()),'shot_id':shot['id'],'name':shot['name'],'provider':'ComfyUI / 本机','provider_task_id':None,'status':'submitting','estimate':float(shot['estimate'])}
                    if project_style:task['style_snapshot']=copy.deepcopy(project_style)
                    task['content_revision']=s['revision'];task['content_snapshot']=content_snapshot(s,shot);task['request']=copy.deepcopy(workflow)
                    s['tasks'].append(task);save(s) # Persist intent before network; unknown outcomes never auto-retry.
                    try:
                        r=remote(s['settings']['comfy_url'],'/prompt',{'prompt':workflow,'client_id':task['id']})
                        if not r.get('prompt_id'):raise ValueError('未返回 prompt_id：'+str(r))
                        task.update(provider_task_id=r['prompt_id'],status='queued');shot['status']='排队中'
                    except Exception as e:
                        task['status']='unknown';save(s);raise ValueError('提交结果不确定，已锁定重试。请在 ComfyUI 核对：'+str(e))
                    s['events'].insert(0,'已提交本机工作流：'+task['id'])
                elif action=='/api/poll':
                    task=next(t for t in s['tasks'] if t['id']==p['task_id'])
                    if not task['provider_task_id']:raise ValueError('缺少供应商编号，请在 ComfyUI 手动核对；禁止自动重试')
                    task['last_checked_at']=datetime.now(timezone.utc).isoformat()
                    r=remote(s['settings']['comfy_url'],'/history/'+task['provider_task_id']);entry=r.get(task['provider_task_id'])
                    if entry:
                        task['status']='failed' if entry.get('status',{}).get('status_str')=='error' else ('completed' if entry.get('status',{}).get('completed') else 'running')
                        task['outputs']=entry.get('outputs',{})
                        next(x for x in s['shots'] if x['id']==task['shot_id'])['status']='待检查' if task['status']=='completed' else task['status']
                else:return self.reply({'error':'未知操作'},404)
                save(s);return self.reply(read())
        except Exception as e:self.reply({'error':str(e)},400)
if __name__=='__main__':
    init(); port=int(os.getenv('PORT','8765')); print('Frame Studio → http://127.0.0.1:'+str(port),flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
