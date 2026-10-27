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
    def setUp(self):server.save(copy.deepcopy(self.initial))
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
        t=server.read()['tasks'][0];self.assertEqual(t['provider_task_id'],'real-test-id')
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
    def test_remote_host_restriction(self):
        for url in ['http://localhost.evil.test','http://127.0.0.1.evil.test','https://localhost','http://user@localhost','http://localhost/path']:
            with self.assertRaises(ValueError):server.remote(url,'/system_stats')
if __name__=='__main__':unittest.main()
