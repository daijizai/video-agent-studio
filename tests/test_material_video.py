import copy,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import material_video as mv
class MaterialVideoTests(unittest.TestCase):
 def setUp(self):
  self.shot={'id':'s','name':'hand','duration':6,'prompt':'robot hand stops above button','storyboard_image':'https://old.invalid/keyframe.png','asset_references':[{'asset_id':'a','version':1,'name':'robot','views':[{'id':'v'}]}]}
  self.state={'project_id':4,'shots':[self.shot],'tasks':[],'script':'original','settings':{'ratio':'16:9','resolution':'720p','audio':False},'project_style':{'prompt':'grey cinematic'}}
  self.lib=Mock();self.lib._checked_view.return_value=(b'original',{'width':1000,'height':1000,'mime':'image/png','sha256':'a'*64,'extension':'png'})
  self.server=Mock();self.server.DATA=Path('/tmp');self.server.material_service.return_value=self.lib
  self.p1=patch.object(mv.asset_library,'validate_references');self.p2=patch.object(mv.asset_library,'assets',return_value=[{'id':'a','adopted_version':1}]);self.p1.start();self.p2.start()
 def tearDown(self):self.p1.stop();self.p2.stop()
 def test_payload_uses_material_not_keyframe_and_does_not_persist_base64(self):
  prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
  self.assertEqual(prepared['payload']['content'][1]['role'],'reference_image')
  self.assertTrue(prepared['payload']['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
  self.assertNotIn('old.invalid',str(prepared));self.assertNotIn('data:image',str(snapshot))
 def test_accepted_first_video_voice_reference_is_sent_and_bound(self):
  import tempfile,hashlib,wave
  with tempfile.TemporaryDirectory() as tmp:
   self.lib.root=Path(tmp);folder=Path(tmp)/'assets'/'4'/'audio';folder.mkdir(parents=True);file=folder/'opening.wav'
   with wave.open(str(file),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*16000)
   sha=hashlib.sha256(file.read_bytes()).hexdigest();self.state['tasks'].append({'id':'first','status':'completed','review_status':'accepted'})
   self.state['project_brief']={'voice_reference':{'enabled':True,'source_task_id':'first','relative_path':'audio/opening.wav','sha256':sha,'duration':2,'expected_speakers':['机器人','考官'],'mapping_status':'待核对'}}
   self.shot['material_video_audio']=True
   prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
   audio=next(x for x in prepared['payload']['content'] if x['type']=='audio_url');self.assertEqual(audio['role'],'reference_audio');self.assertTrue(audio['audio_url']['url'].startswith('data:audio/wav;base64,'))
   self.assertNotIn('data:audio',str(snapshot));self.assertEqual(snapshot['voice_reference']['sha256'],sha)
   file.write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'已变化'):mv.prepare(self.state,self.shot,self.lib)
 def test_approved_per_character_voices_override_mixed_reference_without_embedding_in_history(self):
  import tempfile,hashlib,wave
  with tempfile.TemporaryDirectory() as tmp:
   self.lib.root=Path(tmp);folder=Path(tmp)/'assets'/'4'/'voice';folder.mkdir(parents=True)
   self.state['tasks'].append({'id':'first','status':'completed','review_status':'accepted','accepted_video_sha256':'source'})
   self.shot['material_video_audio']=True;self.state['voice_assets']=[]
   for i,name in enumerate(('机器人','考官')):
    id=str(i)*32;file=folder/(id+'.wav')
    with wave.open(str(file),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*16000)
    v={'version':1,'id':id,'source_task_id':'first','source_video_sha256':'source','sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'duration':2,'review_status':'accepted'}
    self.state['voice_assets'].append({'id':'voice-'+str(i),'character_name':name,'adopted_version':1,'versions':[v]})
   self.state['project_brief']={'voice_reference':{'enabled':True,'expected_speakers':['机器人','考官']}}
   prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
   audio=[x for x in prepared['payload']['content'] if x['type']=='audio_url'];self.assertEqual(len(audio),2)
   self.assertEqual([x['expected_speakers'] for x in snapshot['voice_references']],[['机器人'],['考官']]);self.assertNotIn('data:audio',str(snapshot))
 def test_changed_content_requires_new_approval(self):
  p=mv.operate(self.server,self.state,'preview',{'shot_id':'s'})
  mv.operate(self.server,self.state,'approve',{'shot_id':'s','fingerprint':p['fingerprint']})
  self.shot['prompt']='changed'
  with self.assertRaisesRegex(ValueError,'确认'):mv.operate(self.server,self.state,'submit',{'shot_id':'s'})
 def test_segment_submit_snapshots_draft_and_does_not_change_when_edited(self):
  seg=copy.deepcopy(self.shot);seg['id']='seg';seg['draft_revision']=3;self.state['video_segments']=[seg]
  preview=mv.operate(self.server,self.state,'preview',{'segment_id':'seg'})
  mv.operate(self.server,self.state,'approve',{'segment_id':'seg','fingerprint':preview['fingerprint']})
  with patch.object(mv.generation_scope,'check',return_value='grant'),patch.object(mv.providers,'Provider') as factory:
   factory.return_value.submit.return_value='provider-id'
   result=mv.operate(self.server,self.state,'submit',{'segment_id':'seg'})
  task=self.state['tasks'][0];self.assertEqual(task['segment_id'],'seg');self.assertEqual(task['segment_draft_revision'],3)
  original=copy.deepcopy(task['request']);seg['prompt']='later draft';self.assertEqual(task['request'],original)
  self.assertEqual(result['provider_task_id'],'provider-id')
 def test_explicit_http_rejection_is_recorded_without_unknown_reservation(self):
  preview=mv.operate(self.server,self.state,'preview',{'shot_id':'s'})
  mv.operate(self.server,self.state,'approve',{'shot_id':'s','fingerprint':preview['fingerprint']})
  with patch.object(mv.generation_scope,'check',return_value='grant'),patch.object(mv.providers,'Provider') as provider:
   provider.return_value.submit.side_effect=mv.providers.ProviderHTTPError(400,'InvalidParameter','bad input',{'X-Request-Id':'test-id'})
   with self.assertRaisesRegex(ValueError,'明确拒绝'):mv.operate(self.server,self.state,'submit',{'shot_id':'s'})
  task=self.state['tasks'][0]
  self.assertEqual(task['status'],'rejected');self.assertEqual(task['actual_cost_cny'],0)
  self.assertEqual(task['submission_diagnostics']['provider_code'],'InvalidParameter')
 def test_unknown_retry_requires_exact_explicit_confirmation_and_preserves_old(self):
  p=mv.operate(self.server,self.state,'preview',{'shot_id':'s'})
  mv.operate(self.server,self.state,'approve',{'shot_id':'s','fingerprint':p['fingerprint']})
  old={'id':'old','shot_id':'s','status':'unknown','provider_task_id':None,'estimate':25}
  self.state['tasks'].append(old)
  with self.assertRaisesRegex(ValueError,'逐次明确确认'):mv.operate(self.server,self.state,'submit',{'shot_id':'s','redo':True})
  with patch.object(mv.generation_scope,'check',return_value='grant'),patch.object(mv.providers,'Provider') as provider:
   provider.return_value.submit.return_value='new-id'
   mv.operate(self.server,self.state,'submit',{'shot_id':'s','redo':True,'retry_unknown_task_id':'old','retry_risk_confirmed':True})
  self.assertEqual(old['status'],'unknown');self.assertEqual(old['estimate'],25)
  self.assertEqual(self.state['tasks'][-1]['retry_of_unknown_task_id'],'old')
 def test_extension_references_exact_accepted_parent_and_binds_bytes(self):
  import tempfile,hashlib
  with tempfile.TemporaryDirectory() as tmp:
   self.lib.root=Path(tmp);folder=Path(tmp)/'assets'/'4';folder.mkdir(parents=True);file=folder/'parent.mp4';file.write_bytes(b'original-video')
   parent={'id':'parent','provider':'seedance25','provider_task_id':'provider-parent','status':'completed','review_status':'accepted','local_video':'/media/4/parent.mp4','video_url':'https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/original.mp4','accepted_video_sha256':hashlib.sha256(b'original-video').hexdigest(),'request':{'duration':16},'media_info':{'duration':16.064,'width':1280,'height':720}}
   self.state['tasks']=[parent];self.shot['material_video_parent_task_id']='parent'
   prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
   self.assertEqual(prepared['payload']['ratio'],'adaptive');self.assertEqual(prepared['payload']['omni_reference_task_type'],'extend')
   self.assertEqual(prepared['payload']['content'][-1]['role'],'reference_video');self.assertEqual(snapshot['parent_video']['task_id'],'parent')
   self.assertGreater(prepared['estimated_cny'],10)
   self.state['settings']['resolution']='1080p'
   larger,_=mv.prepare(self.state,self.shot,self.lib)
   self.assertGreater(larger['estimated_cny'],prepared['estimated_cny']*2)
   file.write_bytes(b'replaced')
   with self.assertRaisesRegex(ValueError,'重新验收'):mv.prepare(self.state,self.shot,self.lib)
 def test_tail_mode_never_silently_substitutes_full_video(self):
  self.shot['material_video_parent_task_id']='parent'
  self.shot['material_video_reference_mode']='tail'
  with self.assertRaisesRegex(ValueError,'不能将原视频冒充片尾'):
   mv.prepare(self.state,self.shot,self.lib)
 def test_baseline_and_parent_are_sent_in_order_and_snapshot_bound(self):
  import tempfile,hashlib
  with tempfile.TemporaryDirectory() as tmp:
   self.lib.root=Path(tmp);folder=Path(tmp)/'assets'/'4';folder.mkdir(parents=True)
   tasks=[]
   for name,length in (('baseline',12),('parent',15)):
    file=folder/(name+'.mp4');file.write_bytes(name.encode())
    tasks.append({'id':name,'provider':'seedance25','provider_task_id':'p-'+name,'status':'completed','review_status':'accepted',
      'local_video':'/media/4/'+name+'.mp4','video_url':'https://example.volces.com/'+name+'.mp4',
      'accepted_video_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
      'request':{'duration':length},'media_info':{'duration':length,'width':1280,'height':720}})
   self.state['tasks']=tasks;self.state['project_brief']={'video_quality':{'enabled':True,'baseline_task_id':'baseline','baseline_sha256':tasks[0]['accepted_video_sha256'],'prompt':'重点清晰'}}
   self.shot['material_video_parent_task_id']='parent'
   prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
   videos=[x['video_url']['url'] for x in prepared['payload']['content'] if x['type']=='video_url']
   self.assertEqual(videos,['https://example.volces.com/parent.mp4','https://example.volces.com/baseline.mp4'])
   self.assertIn('视频2仅作为画质参考',prepared['payload']['content'][0]['text'])
   self.assertEqual(snapshot['quality_reference']['status'],'sent')
   tasks[0]['media_info']['duration']=16
   prepared,snapshot=mv.prepare(self.state,self.shot,self.lib)
   self.assertEqual(len([x for x in prepared['payload']['content'] if x['type']=='video_url']),1)
   self.assertEqual(snapshot['quality_reference']['status'],'not_sent');self.assertTrue(snapshot['quality_warnings'])
 def test_budget_and_pause_gate_before_network(self):
  p=mv.operate(self.server,self.state,'preview',{'shot_id':'s'})
  mv.operate(self.server,self.state,'approve',{'shot_id':'s','fingerprint':p['fingerprint']})
  with patch.object(mv.generation_scope,'check',side_effect=ValueError('paused')),patch.object(mv.providers,'Provider') as provider:
   with self.assertRaisesRegex(ValueError,'paused'):mv.operate(self.server,self.state,'submit',{'shot_id':'s'})
   provider.assert_not_called();self.assertEqual(self.state['tasks'],[])
if __name__=='__main__':unittest.main()
