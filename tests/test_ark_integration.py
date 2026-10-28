"""HTTP integration for new adapters, isolated SQLite/assets/secrets and mock transport."""
import copy,json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,ark_provider as ark,secret_store,generation_scope

class ArkWorkbench(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);(root/'data').mkdir();(root/'assets').mkdir()
  self.patches=[patch.object(server,'DATA',root/'data'),patch.object(server,'ROOT',root),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'private'/'credentials.json')})]
  for p in self.patches:p.start()
  server.init();self.state=server.read();self.sid=self.state['shots'][0]['id']
  self.state['settings'].update(image_model=ark.IMAGE_MODEL,provider='seedance25',resolution='480p',ratio='9:16',audio=True)
  self.state['shots'][0].update(duration=5,estimate=0,reference_images=[])
  server.save(self.state);secret_store.write_key('ARK_API_KEY','fake-ark-integration-key')
  generation_scope.authorize_budgets(1,server.DATA/'studio.db',.24,10,'test explicit model budget',1,models=[ark.IMAGE_MODEL,ark.VIDEO_MODEL])
  self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.http.server_port)
 def tearDown(self):
  self.http.shutdown();self.http.server_close()
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def post(self,path,payload):
  r=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(r) as response:return response.status,json.load(response)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def image(self):return {'status':'completed','image_urls':['https://example.byteimg.com/a.png'],'usage':{'generated_images':1},'actual_cost_cny':None}
 def approve(self):
  s=server.read();shot=s['shots'][0];asset=server.ROOT/'assets'/'1'/'approved.png';asset.parent.mkdir(exist_ok=True);asset.write_bytes(b'fixture-approval-image')
  shot.update(storyboard_task_id='approved',storyboard_local='/media/1/approved.png',storyboard_image='https://example.com/approved.png');server.save(s)
  code,s=self.post('approvals/shot',{'shot_id':self.sid,'image_task_id':'approved'});self.assertEqual(code,200);return s
 def test_sync_result_persisted_before_cache_failure_then_only_downloads(self):
  provider=ark.SeedreamProvider(request=Mock(return_value={'data':[{'url':'https://example.byteimg.com/a.png'}]}))
  with patch.object(server.image_provider,'for_model',return_value=provider),patch.object(server,'cache_image',side_effect=OSError('cache unavailable')):
   code,s=self.post('image/submit',{'shot_id':self.sid});self.assertEqual(code,200)
  task=s['image_tasks'][-1];self.assertEqual(task['status'],'completed');self.assertIsNone(task['provider_task_id']);self.assertIn('download_error',task)
  self.assertEqual(provider.request.call_count,1);self.assertFalse(s['shots'][0]['approved'])
  with patch('providers.transport',side_effect=AssertionError('no supplier retry')),patch.object(server,'cache_image',return_value='/media/1/recovered.png'):
   code,s=self.post('image/poll',{'task_id':task['id']});self.assertEqual(code,200);self.assertNotIn('download_error',s['image_tasks'][-1]);self.assertEqual(s['shots'][0]['storyboard_local'],'/media/1/recovered.png')
  self.assertEqual(provider.request.call_count,1)
 def test_recovery_after_crash_and_historical_cache_preserves_new_approval(self):
  s=server.read();task={'id':'sync','shot_id':self.sid,'name':'fixture','provider':'seedream','status':'completed','provider_task_id':None,'estimate':.12,**self.image()};s['image_tasks']=[task];server.save(s)
  with patch.object(server,'cache_image',return_value='/media/1/sync.png'):
   code,s=self.post('image/poll',{'task_id':'sync'});self.assertEqual(code,200);self.assertEqual(s['shots'][0]['storyboard_task_id'],'sync')
  s=self.approve();shot=s['shots'][0];s['image_tasks'].append({**task,'id':'newer'});shot['approved']=True
  shot['approved_image_task_id']='approved';server.save(s)
  with patch.object(server,'cache_image',return_value='/media/1/old.png'):
   code,s=self.post('image/poll',{'task_id':'sync'});self.assertEqual(code,200);self.assertEqual(s['shots'][0]['storyboard_local'],'/media/1/approved.png');self.assertTrue(s['shots'][0]['approved'])
 def test_unknown_sync_submit_blocks_second_charge(self):
  provider=ark.SeedreamProvider(request=Mock(side_effect=TimeoutError('timed out')))
  with patch.object(server.image_provider,'for_model',return_value=provider):
   self.assertEqual(self.post('image/submit',{'shot_id':self.sid})[0],400)
   self.assertEqual(server.read()['image_tasks'][0]['status'],'unknown')
   self.assertEqual(self.post('image/submit',{'shot_id':self.sid,'redo':True})[0],400)
   self.assertEqual(self.post('image/poll',{'task_id':server.read()['image_tasks'][0]['id']})[0],400)
  self.assertEqual(provider.request.call_count,1)
 def test_pause_and_model_allowlist_gate_no_remote_call(self):
  scope=generation_scope.read();scope['1']['paused']=True;generation_scope.path().write_text(json.dumps(scope))
  with patch('providers.transport',side_effect=AssertionError('network forbidden')):
   for action in ['image/submit','provider/submit','submit']:
    code,r=self.post(action,{'shot_id':self.sid});self.assertEqual(code,400);self.assertIn('暂停',r['error'])
   self.assertEqual(self.post('image/prepare',{'shot_id':self.sid})[0],200)
  self.post('budgets/authorize',{'image_limit':.24,'video_limit':3,'models':[ark.IMAGE_MODEL],'source':'test budget edit'})
  self.assertTrue(generation_scope.is_paused(1,server.DATA/'studio.db'))
  scope=generation_scope.read();scope['1']['paused']=False;scope['1']['models']=[];generation_scope.path().write_text(json.dumps(scope))
  with patch('providers.transport',side_effect=AssertionError('network forbidden')):self.assertEqual(self.post('image/submit',{'shot_id':self.sid})[0],400)
 def test_image_budget_cannot_borrow_video_balance(self):
  generation_scope.authorize_budgets(1,server.DATA/'studio.db',.11,100,'test independent budget',1)
  with patch.object(ark.SeedreamProvider,'submit') as submit:
   code,r=self.post('image/submit',{'shot_id':self.sid});self.assertEqual(code,400);self.assertIn('独立预算不足',r['error']);submit.assert_not_called()
 def test_seedance_http_approval_reference_mutation_and_unknown(self):
  s=self.approve();self.assertTrue(server.workflow_state.valid_approval(s,s['shots'][0]))
  s['shots'][0]['storyboard_image']='https://example.com/swapped.png';server.save(s)
  with patch.object(server.providers.Provider,'submit') as submit:
   code,r=self.post('provider/submit',{'shot_id':self.sid});self.assertEqual(code,400);self.assertIn('参考图绑定',r['error']);submit.assert_not_called()
  s=self.approve()
  with patch.object(server.providers.Provider,'submit',side_effect=TimeoutError('uncertain')) as submit:
   self.assertEqual(self.post('provider/submit',{'shot_id':self.sid})[0],400)
   self.assertEqual(server.read()['tasks'][-1]['status'],'unknown');self.assertEqual(self.post('provider/submit',{'shot_id':self.sid})[0],400);self.assertEqual(submit.call_count,1)
 def test_seedance_status_routes_and_stage_derivation(self):
  s=self.approve()
  with patch.object(server.providers.Provider,'submit',return_value='ark-video-test'):
   code,s=self.post('provider/submit',{'shot_id':self.sid});self.assertEqual(code,200)
  # Approve the remaining fixture shots so the stage is not held at storyboard review.
  s['shots']=s['shots'][:1];server.save(s)
  self.assertEqual(server.read()['workflow']['code'],'VIDEO_GENERATING')
  with patch.object(server.providers.Provider,'status',return_value={'status':'completed','video_url':'https://example.volces.com/a.mp4','actual_cost_cny':None,'usage':{'completion_tokens':10}}),patch.object(server.media_files,'cache_video',return_value=('/media/1/result.mp4',{'has_audio':True})):
   code,s=self.post('provider/poll',{'task_id':s['tasks'][-1]['id']});self.assertEqual(code,200);self.assertEqual(s['workflow']['code'],'VIDEO_REVIEW')

if __name__=='__main__':unittest.main()
