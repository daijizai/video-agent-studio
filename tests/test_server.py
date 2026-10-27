import unittest, tempfile, sys, threading, json, urllib.request, urllib.error, copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();server.DATA=Path(cls.tmp.name);server.init()
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.url='http://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start();cls.initial=server.read()
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
    def setUp(self):
        with server.db() as c:c.execute('UPDATE workspace SET current_project=1 WHERE id=1')
        server.save(copy.deepcopy(self.initial))
    def post(self,path,p):
        req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(p).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def prepare(self):
        s=server.read();s['shots'][0]['approved']=True;s['settings']['comfy_url']='http://127.0.0.1:8188';s['settings']['workflow']=json.dumps({'1':{'class_type':'CLIPTextEncode','inputs':{'text':'{{prompt}}'}}});server.save(s);return s['shots'][0]['id']
    def test_approval_gate(self):
        status,r=self.post('submit',{'shot_id':server.read()['shots'][0]['id']});self.assertEqual(status,400);self.assertIn('先确认',r['error']);self.assertEqual(server.read()['tasks'],[])
    def test_budget_gate(self):
        sid=self.prepare();self.post('save',{'budget':1});self.assertEqual(self.post('submit',{'shot_id':sid})[0],400);self.assertEqual(server.read()['tasks'],[])
    def test_submit_poll_and_duplicate(self):
        sid=self.prepare()
        with patch.object(server,'remote',return_value={'prompt_id':'real-test-id'}) as mock:
            self.assertEqual(self.post('submit',{'shot_id':sid})[0],200)
            self.assertEqual(mock.call_args[0][2]['prompt']['1']['inputs']['text'],server.read()['shots'][0]['prompt'])
            self.assertEqual(self.post('submit',{'shot_id':sid})[0],400);self.assertEqual(mock.call_count,1)
        t=server.read()['tasks'][0];self.assertEqual(t['content_snapshot']['shot']['prompt'],server.read()['shots'][0]['prompt']);self.assertIn('content_revision',t);self.assertEqual(t['content_snapshot']['shot']['status'],'待确认');self.assertEqual(t['provider_task_id'],'real-test-id')
        with patch.object(server,'remote',return_value={'real-test-id':{'status':{'completed':True},'outputs':{}}}):
            self.assertEqual(self.post('poll',{'task_id':t['id']})[1]['tasks'][0]['status'],'completed')
    def test_timeout_locks_retry(self):
        sid=self.prepare()
        with patch.object(server,'remote',side_effect=TimeoutError('timeout')) as mock:
            self.assertEqual(self.post('submit',{'shot_id':sid})[0],400)
            self.assertEqual(server.read()['tasks'][0]['status'],'unknown')
            self.post('submit',{'shot_id':sid});self.assertEqual(mock.call_count,1)
    def test_paid_node_blocked(self):
        sid=self.prepare();s=server.read();s['settings']['workflow']='{"1":{"class_type":"PaidVideoAPI","inputs":{}}}';server.save(s)
        self.assertEqual(self.post('submit',{'shot_id':sid})[0],400);self.assertEqual(server.read()['tasks'],[])
    def test_duration_validation_and_persistence(self):
        s=server.read();s['shots'][0]['duration']=301
        self.assertEqual(self.post('save',{'shots':s['shots']})[0],400)
        self.assertEqual(self.post('save',{'script':'edited'})[0],200);self.assertEqual(server.read()['script'],'edited')
        with server.db() as c:self.assertGreater(c.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],0)
    def test_project_isolation_and_selection(self):
        old=server.read();old['script']='original-project';server.save(old)
        code,new=self.post('projects/new',{'title':'Independent film'})
        self.assertEqual(code,200);self.assertFalse(new['demo']);self.assertEqual(new['shots'],[])
        pid=new['project_id'];self.post('save',{'script':'new-project','budget':12,'project_id':pid})
        self.assertEqual(server.read()['script'],'new-project');self.assertEqual(server.current_project(),pid)
        # Simulate stale browser tab writing into the newly selected project.
        self.assertEqual(self.post('save',{'script':'bad','project_id':1})[0],400)
        self.post('projects/switch',{'project_id':1})
        self.assertEqual(server.read()['script'],'original-project');self.assertEqual(len(server.read()['shots']),4)
        self.post('projects/switch',{'project_id':pid});server.init()
        self.assertEqual(server.current_project(),pid);self.assertEqual(server.read()['budget'],12)
    def test_provider_http_preview_and_paid_gate(self):
        s=server.read();s['shots'][0]['reference_images']=['https://example.com/role.png'];s['shots'][0]['duration']=5;server.save(s)
        with patch('providers.transport',side_effect=AssertionError('network forbidden')):
            code,result=self.post('provider/preview',{'shot_id':s['shots'][0]['id']})
            self.assertEqual(code,200);self.assertFalse(result['network_called']);self.assertEqual(result['estimated_cny'],3.0)
            self.assertEqual(self.post('provider/submit',{'shot_id':s['shots'][0]['id']})[0],400)
    def test_credentials_not_in_database_export_or_logs(self):
        import contextlib,io,os
        token='fake-private-key-for-http-test'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(Path(tmp)/'credentials.json')}):
            logs=io.StringIO()
            with contextlib.redirect_stderr(logs):
                code,response=self.post('credentials',{'provider':'wan3','value':token})
                self.assertEqual(code,200);self.assertNotIn(token,json.dumps(response))
                with urllib.request.urlopen(self.url+'/api/export') as r:self.assertNotIn(token,r.read().decode())
            self.assertNotIn(token,logs.getvalue())
            with server.db() as c:
                for row in c.execute('SELECT body FROM state UNION ALL SELECT body FROM revisions'):
                    self.assertNotIn(token,row[0])
    def test_optimistic_revision_guard(self):
        stale=server.read()
        code,fresh=self.post('save',{'script':'first edit','project_id':stale['project_id'],'revision':stale['revision']})
        self.assertEqual(code,200);self.assertGreater(fresh['revision'],stale['revision'])
        code,_=self.post('save',{'script':'stale overwrite','project_id':stale['project_id'],'revision':stale['revision']})
        self.assertEqual(code,400);self.assertEqual(server.read()['script'],'first edit')
    def test_demo_target_does_not_limit_series(self):
        self.assertEqual(server.read()['target_duration'],30)
        code,new=self.post('projects/new',{'title':'Longer series'})
        self.assertEqual(code,200);self.assertEqual(new['target_duration'],120)
        shots=[{'id':'longer','name':'series segment','duration':31,'estimate':0,'prompt':'draft','approved':False}]
        self.assertEqual(self.post('save',{'shots':shots})[0],200)
        self.assertEqual(server.read()['shots'][0]['duration'],31)
    def test_historical_image_poll_does_not_replace_current_or_clear_approval(self):
        s=server.read();shot=s['shots'][0];shot.update(storyboard_task_id='new',storyboard_local='/media/1/new.png',storyboard_image='https://example.aliyuncs.com/new.png',approved=True,image_quality='approved')
        s['image_tasks']=[{'id':'old','shot_id':shot['id'],'provider_task_id':'old-provider','status':'completed','estimate':.2},{'id':'new','shot_id':shot['id'],'provider_task_id':'new-provider','status':'completed','estimate':.2}];server.save(s)
        result={'status':'completed','image_urls':['https://example.aliyuncs.com/old.png'],'usage':{},'actual_cost_cny':None}
        with patch.object(server.image_provider.ImageProvider,'status',return_value=result),patch.object(server,'cache_image',return_value='/media/1/old.png'):
            code,response=self.post('image/poll',{'task_id':'old'})
        self.assertEqual(code,200);self.assertEqual(response['shots'][0]['storyboard_local'],'/media/1/new.png');self.assertTrue(response['shots'][0]['approved']);self.assertEqual(response['shots'][0]['image_quality'],'approved')
    def test_remote_host_restriction(self):
        for url in ['http://localhost.evil.test','http://127.0.0.1.evil.test','https://localhost','http://user@localhost','http://localhost/path']:
            with self.assertRaises(ValueError):server.remote(url,'/system_stats')
if __name__=='__main__':unittest.main()
