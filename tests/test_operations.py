"""Operations data stays project-local and preserves unknown and historical values."""
import json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class OperationsHTTP(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);self.data=root/'data';self.data.mkdir()
  self.patches=[patch.object(server,'ROOT',root),patch.object(server,'DATA',self.data),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'secret.json')})]
  for p in self.patches:p.start()
  server.init();self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start();self.url=f'http://127.0.0.1:{self.http.server_port}/api/'
 def tearDown(self):
  self.http.shutdown();self.http.server_close()
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def post(self,path,p):
  s=server.read();p={'project_id':s['project_id'],'revision':s['revision'],**p}
  req=urllib.request.Request(self.url+path,json.dumps(p).encode(),{'Content-Type':'application/json'})
  with urllib.request.urlopen(req) as r:return json.load(r)
 def test_publish_snapshot_edit_isolation_and_unknown(self):
  s=self.post('operations/save-publication',{'data':{'platform':'抖音','published_at':'2026-11-01T04:00:00+08:00','url':'https://example.com/v'}});rec=s['publications'][0]
  payload={'observed_at':'2026-11-01T05:00:00+08:00','views':0,'likes':None,'ad_spend':20.5}
  s=self.post('operations/save-snapshot',{'publication_id':rec['id'],'data':payload});row=s['publications'][0]['snapshots'][0];self.assertEqual(row['views'],0);self.assertIsNone(row['likes']);self.assertEqual(row['ad_spend'],20.5)
  s=self.post('operations/save-snapshot',{'publication_id':rec['id'],'data':{'observed_at':'2026-11-01T06:00:00+08:00','views':500,'comments':8}});self.assertEqual(len(s['publications'][0]['snapshots']),2)
  s=self.post('operations/save-snapshot',{'publication_id':rec['id'],'snapshot_id':row['id'],'data':{**payload,'views':10}});self.assertEqual(s['publications'][0]['snapshots'][0]['views'],10)
  self.post('projects/new',{'title':'另一个项目'});self.assertNotIn('publications',server.read());self.assertEqual(len(server.read(1)['publications']),1)
 def test_reject_invalid_url_metrics_and_time(self):
  with self.assertRaises(urllib.error.HTTPError):self.post('operations/save-publication',{'data':{'platform':'抖音','url':'javascript:alert(1)'}})
  s=self.post('operations/save-publication',{'data':{'platform':'抖音','published_at':'2026-11-01T04:00:00+08:00'}});id=s['publications'][0]['id']
  for data in ({'observed_at':'2026-11-01T03:00:00+08:00','views':10},{'observed_at':'2026-11-01T05:00:00+08:00','views':-1},{'observed_at':'2026-11-01T05:00:00','views':10},{'observed_at':'2026-11-01T05:00:00+08:00'}):
   with self.assertRaises(urllib.error.HTTPError):self.post('operations/save-snapshot',{'publication_id':id,'data':data})
  self.assertEqual(server.read()['publications'][0]['snapshots'],[])
if __name__=='__main__':unittest.main()
