"""Offline MiniMax contracts and durable execution guards; no real model calls."""
import copy,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import providers,minimax_provider as mm,material_video as mv,secret_store,generation_scope

class MiniMaxContracts(unittest.TestCase):
 def setUp(self):
  self.request=Mock();self.provider=providers.Provider('minimax',self.request)
  self.shot={'id':'s','name':'test','duration':6,'prompt':'camera moves','reference_images':[]}
  self.cfg={'provider':'minimax','resolution':'768P','ratio':'16:9'}
 def test_offline_text_and_material_contract_and_prices(self):
  r=self.provider.prepare(self.shot,self.cfg);self.assertEqual(r['estimated_cny'],3)
  self.assertEqual(r['payload']['model'],'MiniMax-H3');self.assertNotIn('generate_audio',r['payload'])
  self.shot['reference_images']=['https://example.com/%s.png'%i for i in range(9)]
  r=self.provider.prepare(self.shot,self.cfg);self.assertEqual(r['estimated_cny'],3.8)
  self.assertTrue(all(x['role']=='reference_image' for x in r['payload']['content'][1:]));self.request.assert_not_called()
 def test_variants_prices_and_no_silent_resolution_mapping(self):
  for model,price in [('MiniMax-H3-Highspeed',2.4),('MiniMax-H3-Lite',1.56),('MiniMax-H3-Max',3)]:
   self.assertEqual(self.provider.prepare(self.shot,{**self.cfg,'minimax_model':model})['estimated_cny'],price)
  for cfg in [{'resolution':'720p'},{'minimax_model':'MiniMax-H3-Lite','resolution':'2K'},{'ratio':'adaptive'},{'minimax_model':'invented'}]:
   with self.assertRaises(ValueError):self.provider.prepare(self.shot,{**self.cfg,**cfg})
 def test_invalid_duration_prompt_and_reference_count(self):
  for value in [True,3,16,5.5,float('nan')]:
   with self.assertRaises(ValueError):self.provider.prepare({**self.shot,'duration':value},self.cfg)
  for change in [{'prompt':'x'*7001},{'prompt':''},{'reference_images':['http://localhost/img.png']},{'reference_images':['https://u:p@example.com/x']},{'reference_images':['https://example.com/x']*10}]:
   with self.assertRaises(ValueError):self.provider.prepare({**self.shot,**change},self.cfg)
 def test_reference_video_pricing_and_limits(self):
  payload=self.provider.prepare(self.shot,self.cfg)['payload'];payload['content'] += [{'type':'video_url','video_url':{'url':'https://example.com/x.mp4'},'role':'reference_video'}]
  self.assertEqual(mm.estimate(payload,5.1)['estimated_cny'],6)
  for seconds in [15.1,-1]:
   with self.assertRaises(ValueError):mm.estimate(payload,seconds)
  with self.assertRaises(ValueError):mm.estimate(payload,0,16)
 def test_submit_requires_authorization_and_preserves_id(self):
  r=self.provider.prepare(self.shot,self.cfg)
  with self.assertRaises(ValueError):self.provider.submit(r,'local')
  self.request.assert_not_called();self.request.return_value={'task_id':'12345'}
  with patch.object(secret_store,'get_key',return_value='offline-fake-key'):
   self.assertEqual(self.provider.submit(r,'local',authorized=True),'12345')
  self.assertEqual(self.request.call_count,1);self.assertEqual(self.request.call_args.args[1],'https://api.minimax.cn/v2/video_generation')
 def test_missing_id_and_timeout_never_retry(self):
  for result in [{},TimeoutError('timeout')]:
   self.request.reset_mock();self.request.side_effect=result if isinstance(result,Exception) else None;self.request.return_value=result
   with patch.object(secret_store,'get_key',return_value='offline-fake-key'),self.assertRaises((RuntimeError,TimeoutError)):self.provider.submit(self.provider.prepare(self.shot,self.cfg),'local',True)
   self.assertEqual(self.request.call_count,1)
 def test_status_mapping_and_original_identity(self):
  for status,expected in [('queued','queued'),('running','running'),('succeeded','completed'),('failed','failed'),('cancelled','cancelled'),('future','unknown')]:
   self.request.return_value={'task':{'id':'123','status':status,'content':{'url':'https://cdn.hailuoai.com/movie.mp4'},'usage':{'output_seconds':6}}}
   with patch.object(secret_store,'get_key',return_value='offline-fake-key'):r=self.provider.status('123')
   self.assertEqual(r['status'],expected);self.assertIsNone(r['actual_cost_cny']);self.assertEqual(r['usage']['output_seconds'],6)
   self.assertTrue(self.request.call_args.args[1].endswith('/v2/query/video_generation/123'))
  self.request.return_value={'task':{'id':'other'}}
  with patch.object(secret_store,'get_key',return_value='offline-fake-key'),self.assertRaises(RuntimeError):self.provider.status('123')
 def test_key_storage_is_private_and_redacted(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'STUDIO_SECRET_FILE':tmp+'/credentials.json'}):
   secret_store.write_key('MINIMAX_API_KEY','offline-fake-minimax-key')
   self.assertEqual(secret_store.secret_path().stat().st_mode&0o777,0o600)
   self.assertEqual(secret_store.redact('offline-fake-minimax-key'),'[REDACTED]')

class MiniMaxMaterialExecution(unittest.TestCase):
 def setUp(self):
  self.shot={'id':'s','name':'test','duration':6,'prompt':'walk','asset_references':[{'asset_id':'a','version':1,'name':'robot','views':[{'id':'v'}]}]}
  self.state={'project_id':4,'shots':[self.shot],'tasks':[],'script':'story','settings':{'provider':'minimax','resolution':'768P','ratio':'16:9','audio':False}}
  self.lib=Mock();self.lib._checked_view.return_value=(b'original',{'width':1000,'height':1000,'mime':'image/png','sha256':'a'*64,'extension':'png'})
  self.server=Mock();self.server.DATA=Path('/tmp');self.server.material_service.return_value=self.lib
  self.patches=[patch.object(mv.asset_library,'validate_references'),patch.object(mv.asset_library,'assets',return_value=[{'id':'a','adopted_version':1}])]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def approve(self):
  r=mv.operate(self.server,self.state,'preview',{'shot_id':'s'});mv.operate(self.server,self.state,'approve',{'shot_id':'s','fingerprint':r['fingerprint']});return r
 def test_preview_binds_model_and_material_without_base64_history(self):
  prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
  self.assertEqual(prepared['provider'],'minimax');self.assertNotIn('data:image',str(snapshot))
  self.assertTrue(prepared['payload']['content'][1]['image_url']['url'].startswith('data:image'))
  self.approve();self.state['settings']['minimax_model']='MiniMax-H3-Lite'
  with self.assertRaisesRegex(ValueError,'确认'):mv.operate(self.server,self.state,'submit',{'shot_id':'s'})
 def test_pause_and_budget_error_precede_network_and_reservation(self):
  self.approve()
  for reason in ['paused','budget','model not authorized']:
   with patch.object(mv.generation_scope,'check',side_effect=ValueError(reason)),patch.object(providers.Provider,'submit') as submit,self.assertRaises(ValueError):mv.operate(self.server,self.state,'submit',{'shot_id':'s'})
   submit.assert_not_called();self.assertEqual(self.state['tasks'],[])
 def test_durable_submit_routes_minimax_and_blocks_duplicate(self):
  self.approve()
  def submit(provider,prepared,key,authorized=False):
   self.assertEqual(provider.id,'minimax');self.assertEqual(self.state['tasks'][0]['status'],'submitting');return 'remote-1'
  with patch.object(mv.generation_scope,'check',return_value='grant') as check,patch.object(providers.Provider,'headers',return_value={}),patch.object(providers.Provider,'submit',submit):
   mv.operate(self.server,self.state,'submit',{'shot_id':'s'})
  self.assertEqual(check.call_args.args[4],'MiniMax-H3');self.assertEqual(self.state['tasks'][0]['provider'],'minimax')
  with self.assertRaisesRegex(ValueError,'在途'):mv.operate(self.server,self.state,'submit',{'shot_id':'s','redo':True})
 def test_timeout_retains_unknown_and_reservation(self):
  self.approve()
  with patch.object(mv.generation_scope,'check',return_value='grant'),patch.object(providers.Provider,'headers',return_value={}),patch.object(providers.Provider,'submit',side_effect=TimeoutError()),self.assertRaisesRegex(ValueError,'未知'):mv.operate(self.server,self.state,'submit',{'shot_id':'s'})
  self.assertEqual(self.state['tasks'][0]['status'],'unknown');self.assertEqual(self.state['tasks'][0]['estimate'],3)
 def test_minimax_parent_reference_uses_own_url_and_price(self):
  import hashlib
  with tempfile.TemporaryDirectory() as tmp:
   self.lib.root=Path(tmp);folder=Path(tmp)/'assets'/'4';folder.mkdir(parents=True);(folder/'parent.mp4').write_bytes(b'video')
   parent={'id':'parent','provider':'minimax','provider_task_id':'remote','status':'completed','review_status':'accepted','local_video':'/media/4/parent.mp4','video_url':'https://cdn.hailuoai.com/parent.mp4','accepted_video_sha256':hashlib.sha256(b'video').hexdigest(),'request':{'duration':6},'media_info':{'duration':6,'width':1280,'height':768}}
   self.state['tasks']=[parent];self.shot['material_video_parent_task_id']='parent'
   prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
   self.assertEqual(prepared['estimated_cny'],6);self.assertNotIn('omni_reference_task_type',prepared['payload'])
   self.assertEqual(prepared['payload']['ratio'],'16:9');self.assertEqual(snapshot['parent_video']['task_id'],'parent')
   parent['media_info']['duration']=16
   with self.assertRaisesRegex(ValueError,'15秒'):mv.prepare(self.state,self.shot,self.lib)
 def test_reference_media_total_bound_and_max_input_price(self):
  cfg={**self.state['settings'],'minimax_model':'MiniMax-H3-Max'}
  payload=mm.prepare_video({'duration':6,'prompt':'test','reference_images':['https://example.com/a.png']*3},cfg)['payload']
  self.assertEqual(mm.estimate(payload,2)['estimated_cny'],5.44)
  payload['content'] += [{'type':'audio_url'}]*4
  with self.assertRaisesRegex(ValueError,'数量'):mm.estimate(payload)
 def test_text_only_does_not_reuse_storyboard(self):
  self.shot['asset_references']=[];self.shot['storyboard_image']='https://example.com/old.png'
  prepared,snapshot=mv.prepare(self.state,self.shot,self.lib);self.assertEqual(len(prepared['payload']['content']),1)

if __name__=='__main__':unittest.main()
