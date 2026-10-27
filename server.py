#!/usr/bin/env python3
"""Local, dependency-free production workspace. No paid generation is enabled."""
import providers
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
            s={'title':'雾港来信','episode':'EP 01 · 消失的第七分钟','demo':True,'budget':120,'script':'雨夜，旧港口的钟楼突然停在 23:53。\n\n林雾收到一封来自七分钟后的语音。电话里，是她自己的声音：不要登上最后一班渡轮。\n\n陈渡在码头等她。他手中的船票，印着明天的日期。','continuity':'林雾始终佩戴银色旧手表；陈渡不知道语音的来源。港口时间停在 23:53。','characters':[{'id':'lin','name':'林雾','role':'主角 / 调查记者','version':1,'notes':'28 岁，黑色齐肩短发，灰色风衣，左腕银色旧手表。冷静、敏锐，右眉有细小伤疤。','color':'#729c9b'},{'id':'chen','name':'陈渡','role':'主角 / 渡轮驾驶员','version':1,'notes':'32 岁，深蓝工作夹克，短发，左手旧烧伤。说话克制，始终随身携带黄铜钥匙。','color':'#ac9071'}],'shots':[],'tasks':[],'settings':{'comfy_url':'','workflow':''},'events':['已载入示例策划内容；没有生成媒体或产生费用。']}
            for i,(name,frame,duration,prompt) in enumerate([('雾中的钟楼','远景 · 缓慢推进',8,'雨夜的旧港口，钟楼停在23:53，低饱和青绿色，电影光影'),('七分钟后的来电','近景 · 固定机位',6,'林雾站在雨棚下看手机，灰风衣，银色旧手表，冷光映在脸上'),('最后一班渡轮','全景 · 横向跟随',8,'陈渡站在渡轮入口，深蓝工作夹克，手持纸船票，海雾'),('明天的船票','特写 · 缓慢拉近',5,'湿润的纸船票与黄铜钥匙，背景虚化的港口灯光')]):
                s['shots'].append({'id':str(uuid.uuid4()),'name':name,'frame':frame,'duration':duration,'prompt':prompt,'approved':False,'status':'待确认','estimate':8,'review':'','asset':''})
            c.execute('INSERT INTO state VALUES (1,?)',(json.dumps(s,ensure_ascii=False),))
def current_project():
    with db() as c:return c.execute('SELECT current_project FROM workspace WHERE id=1').fetchone()[0]
def read(project_id=None):
    project_id=project_id or current_project()
    with db() as c:
        c.execute('BEGIN')
        row=c.execute('SELECT body FROM state WHERE id=?',(project_id,)).fetchone()
        if not row:raise ValueError('项目不存在')
        s=json.loads(row[0]);s['project_id']=project_id;s['revision']=c.execute('SELECT COALESCE(MAX(id),0) FROM revisions WHERE project_id=?',(project_id,)).fetchone()[0];return s
def save(s):
    project_id=s.get('project_id',current_project())
    with db() as c:
        body=json.dumps(secret_store.redact(s),ensure_ascii=False)
        c.execute('INSERT INTO revisions(body,project_id) VALUES (?,?)',(body,project_id))
        c.execute('UPDATE state SET body=? WHERE id=?',(body,project_id))
def project_list():
    with db() as c:
        items=[]
        for r in c.execute('SELECT id,body FROM state ORDER BY id'):
            s=json.loads(r['body']);items.append({'id':r['id'],'title':s['title'],'demo':s.get('demo',False)})
        return {'current_project':current_project(),'projects':items}
def create_project(title):
    title=str(title).strip()
    if not title or len(title)>80:raise ValueError('项目名称须为 1–80 个字符')
    s={'title':title,'episode':'','demo':False,'budget':0,'script':'','continuity':'','characters':[],'shots':[],'tasks':[],
       'settings':{'comfy_url':'','workflow':'','provider':'wan3','resolution':'720p','audio':False},'events':['新项目已创建；尚无生成任务。']}
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
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT/'static'),**kw)
    def reply(self,data,status=200):
        b=json.dumps(secret_store.redact(data),ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if self.path=='/api/projects':return self.reply(project_list())
        if self.path=='/api/state':return self.reply(read())
        if self.path=='/api/health':return self.reply({'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),'paid_generation':providers.paid_enabled()})
        if self.path=='/api/providers':return self.reply(providers.config_status())
        if self.path=='/api/export':return self.reply(read())
        if self.path=='/api/revisions':
            with db() as c:return self.reply([dict(r) for r in c.execute('SELECT id,created,body FROM revisions WHERE project_id=? ORDER BY id DESC LIMIT 30',(current_project(),))])
        return super().do_GET()
    def do_POST(self):
        try:
            if self.headers.get('Origin') and self.headers['Origin'] != 'http://'+self.headers.get('Host',''):raise ValueError('拒绝跨站写入')
            n=int(self.headers.get('Content-Length','0'))
            if n>2000000:raise ValueError('请求过大')
            p=json.loads(self.rfile.read(n) or b'{}')
            with LOCK:
                action=self.path
                if action=='/api/projects/new':return self.reply(create_project(p.get('title','')))
                if action=='/api/projects/switch':
                    project_id=int(p['project_id']);result=read(project_id)
                    with db() as c:c.execute('UPDATE workspace SET current_project=? WHERE id=1',(project_id,))
                    return self.reply(result)
                s=read()
                if 'project_id' in p and int(p['project_id'])!=s['project_id']:raise ValueError('当前项目已切换，请刷新页面后再保存')
                if 'revision' in p and int(p['revision'])!=s['revision']:raise ValueError('项目已被其他窗口或CLI修改，请刷新后重试')
                if action=='/api/save':
                    for key in ['title','episode','script','continuity','characters','shots','budget']:
                        if key in p:s[key]=p[key]
                    if not 0<=float(s['budget'])<=100000:raise ValueError('预算必须为 0–100000')
                    if any(not 0<=float(x['estimate'])<=100000 for x in s['shots']):raise ValueError('估价必须为 0–100000')
                    if any(not 1<=float(x['duration'])<=300 for x in s['shots']):raise ValueError('镜头时长须为 1–300 秒')
                    if sum(float(x['duration']) for x in s['shots'])>300:raise ValueError('单集总时长不可超过 5 分钟')
                elif action=='/api/settings':
                    s['settings']={**s['settings'], **{k:p[k] for k in ('comfy_url','workflow','provider','resolution','audio') if k in p}}
                elif action=='/api/credentials':
                    name=providers.CATALOG.get(p.get('provider'),{}).get('key_env')
                    secret_store.write_key(name,p.get('value'))
                    return self.reply({'saved':True,'credential_present':True,'connection':'unverified'})
                elif action=='/api/provider/preview':
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    return self.reply(providers.Provider(s['settings'].get('provider','wan3')).prepare(shot,s['settings']))
                elif action=='/api/provider/submit':
                    if not providers.paid_enabled():raise ValueError('付费生成未授权，当前仅允许零请求预览')
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    if not shot['approved']:raise ValueError('请先确认该镜头分镜')
                    if any(t['shot_id']==shot['id'] for t in s['tasks']):raise ValueError('该镜头已有任务记录，禁止自动重试或重复提交')
                    provider=providers.Provider(s['settings'].get('provider','wan3'))
                    prepared=provider.prepare(shot,s['settings'])
                    estimate=max(float(shot['estimate']),prepared['estimated_cny'])
                    if sum(t['estimate'] for t in s['tasks'])+estimate>float(s['budget']):raise ValueError('供应商估算将超过本集预算')
                    provider.headers();provider.base_url() # Validate credentials/config before durable submission intent.
                    task={'id':str(uuid.uuid4()),'shot_id':shot['id'],'name':shot['name'],'provider':provider.id,'provider_task_id':None,'status':'submitting','estimate':estimate,'request':prepared['payload']}
                    s['tasks'].append(task);save(s)
                    try:
                        task['provider_task_id']=provider.submit(prepared,task['id']);task['status']='queued';shot['status']='排队中'
                    except Exception:
                        task['status']='unknown';save(s);raise ValueError('供应商提交结果不确定，已锁定重试。请在供应商控制台核对')
                elif action=='/api/provider/poll':
                    task=next(t for t in s['tasks'] if t['id']==p['task_id'])
                    if not task.get('provider_task_id'):raise ValueError('缺少任务编号，禁止自动重试')
                    result=providers.Provider(task['provider']).status(task['provider_task_id'])
                    task.update(result)
                    next(x for x in s['shots'] if x['id']==task['shot_id'])['status']='待检查' if result['status']=='completed' else result['status']
                elif action=='/api/connect':
                    r=remote(s['settings']['comfy_url'],'/system_stats');return self.reply({'connected':True,'system':r})
                elif action=='/api/submit':
                    shot=next(x for x in s['shots'] if x['id']==p['shot_id'])
                    if not shot['approved']:raise ValueError('请先确认该镜头分镜')
                    if any(t['shot_id']==shot['id'] and t['status'] not in ['failed','cancelled'] for t in s['tasks']):raise ValueError('已有执行记录，请查询原任务，禁止重复提交')
                    reserved=sum(t['estimate'] for t in s['tasks'] if t['status']!='cancelled')
                    if reserved+float(shot['estimate'])>float(s['budget']):raise ValueError('预占金额将超过本集预算')
                    workflow=json.loads(s['settings']['workflow'])
                    if not isinstance(workflow,dict) or not workflow:raise ValueError('请导入 ComfyUI API 格式工作流')
                    # Hard gate: arbitrary workflows can call paid nodes. V1 permits a small local-only allowlist.
                    allowed={'CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','SaveImage','LoadImage','PreviewImage'}
                    if any(node.get('class_type') not in allowed for node in workflow.values()):raise ValueError('工作流含未审计节点；第一版禁止外部付费与自定义节点')
                    for node in workflow.values():
                        if node.get('class_type')=='CLIPTextEncode':node['inputs']['text']=node['inputs'].get('text','').replace('{{prompt}}',shot['prompt'])
                    task={'id':str(uuid.uuid4()),'shot_id':shot['id'],'name':shot['name'],'provider':'ComfyUI / 本机','provider_task_id':None,'status':'submitting','estimate':float(shot['estimate'])}
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
