import sys,unittest,copy
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import video_segments as vs
class SegmentTests(unittest.TestCase):
 def setUp(self):
  self.s={'shots':[{'id':'s','name':'first','duration':16,'material_video_prompt':'opening','asset_references':[]}],'tasks':[{'id':'t','shot_id':'s','name':'old test','request':{'duration':6,'content':[{'type':'text','text':'original actual prompt'}]}}]};self.server=Mock()
 def test_opening_candidate_is_stored_without_generation_or_approval(self):
  import tempfile,base64,hashlib
  from test_asset_library import png
  with tempfile.TemporaryDirectory() as tmp:
   self.server.ROOT=Path(tmp);self.s['project_id']=4;vs.initialize(self.s);seg=self.s['video_segments'][0];before=copy.deepcopy(self.s['tasks'])
   result=vs.operate(self.server,self.s,'add-opening-candidate',{'segment_id':seg['id'],'base64':base64.b64encode(png()).decode()})
   frame=result['candidate'];file=Path(tmp)/'assets'/'4'/Path(frame['url']).name
   self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),frame['sha256']);self.assertEqual(frame['status'],'candidate')
   self.assertEqual(self.s['tasks'],before);self.assertNotIn('material_video_approval',seg)
   with self.assertRaises(ValueError):vs.operate(self.server,self.s,'add-opening-candidate',{'segment_id':seg['id'],'base64':'not valid'})
 def test_opening_from_accepted_video_is_exact_last_frame_and_source_bound(self):
  import tempfile,hashlib,subprocess,shutil
  if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('ffmpeg unavailable')
  with tempfile.TemporaryDirectory() as tmp:
   self.server.ROOT=Path(tmp);self.s['project_id']=4;vs.initialize(self.s);seg=self.s['video_segments'][0]
   folder=Path(tmp)/'assets'/'4';folder.mkdir(parents=True);video=folder/'prior.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=384x512:rate=2:duration=1','-c:v','mpeg4','-y',str(video)],check=True,capture_output=True)
   task={'id':'prior','segment_id':'other','status':'completed','local_video':'/media/4/prior.mp4','accepted_video_sha256':hashlib.sha256(video.read_bytes()).hexdigest()};self.s['tasks'].append(task)
   with self.assertRaisesRegex(ValueError,'审阅采用'):vs.operate(self.server,self.s,'extract-opening-from-video',{'segment_id':seg['id'],'source_task_id':'prior'})
   task['review_status']='accepted'
   frame=vs.operate(self.server,self.s,'extract-opening-from-video',{'segment_id':seg['id'],'source_task_id':'prior'})['candidate']
   self.assertEqual(frame['source_task_id'],'prior');self.assertEqual(frame['source_frame_index'],1);self.assertEqual(frame['status'],'candidate')
   expected=subprocess.run(['ffmpeg','-v','error','-i',str(video),'-vf','select=eq(n\\,1)','-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],check=True,capture_output=True).stdout
   self.assertEqual((folder/Path(frame['url']).name).read_bytes(),expected)
   vs.operate(self.server,self.s,'approve-opening',{'segment_id':seg['id'],'frame_id':frame['id']})
   video.write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'已变化'):vs.read_opening(self.server.ROOT,self.s,seg,frame['id'])
 def test_migration_preserves_actual_input_and_is_idempotent(self):
  old=copy.deepcopy(self.s['tasks']);self.assertTrue(vs.initialize(self.s));self.assertEqual(self.s['tasks'],old);self.assertEqual(len(self.s['video_segments']),2);self.assertFalse(vs.initialize(self.s));self.assertFalse(self.s['video_segments'][1]['include_in_playlist'])
 def test_draft_changes_do_not_rewrite_historical_video(self):
  vs.initialize(self.s);old=copy.deepcopy(self.s['tasks']);seg=self.s['video_segments'][1];seg['material_video_approval']={'fingerprint':'old'}
  vs.operate(self.server,self.s,'save-segment',{'segment_id':seg['id'],'draft':{'material_video_prompt':'new draft','duration':15}})
  self.assertEqual(self.s['tasks'],old);self.assertNotIn('material_video_approval',seg);self.assertEqual(seg['draft_revision'],2)
 def test_candidate_cannot_cross_segments_and_duration_is_bounded(self):
  vs.initialize(self.s);sid=self.s['video_segments'][0]['id']
  with self.assertRaises(ValueError):vs.operate(self.server,self.s,'save-segment',{'segment_id':sid,'draft':{'selected_task_id':'t'}})
  with self.assertRaises(ValueError):vs.operate(self.server,self.s,'save-segment',{'segment_id':sid,'draft':{'duration':90}})
 def test_first_approved_segment_creates_shared_audio_without_claiming_speaker_identification(self):
  import tempfile,wave,hashlib
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'assets'/'4';folder.mkdir(parents=True);media=folder/'sample.mp4'
   with wave.open(str(media),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*17600)
   self.s.update(project_id=4,characters=[{'name':'机器人'},{'name':'考官'}]);vs.initialize(self.s);segment=self.s['video_segments'][0]
   self.s['tasks'].append({'id':'first-video','segment_id':segment['id'],'status':'completed','local_video':'/media/4/sample.mp4'})
   self.server.ROOT=root
   result=vs.operate(self.server,self.s,'accept-segment',{'segment_id':segment['id'],'task_id':'first-video'})
   ref=result['voice_reference'];self.assertEqual(ref['expected_speakers'],['机器人','考官']);self.assertIn('待核对',ref['mapping_status']);self.assertFalse(ref['enabled'])
   self.assertEqual(ref['source_video_sha256'],hashlib.sha256(media.read_bytes()).hexdigest());self.assertTrue((folder/ref['relative_path']).exists())
 def test_rejected_candidate_retains_video_and_input_but_is_not_selected(self):
  vs.initialize(self.s);seg=self.s['video_segments'][1];seg['selected_task_id']='t';task=self.s['tasks'][0];task['status']='completed';task['local_video']='/media/4/t.mp4';before=copy.deepcopy(task['request'])
  vs.operate(self.server,self.s,'reject-candidate',{'segment_id':seg['id'],'task_id':'t','reason':'机器人接触按钮'})
  self.assertEqual(task['review_status'],'rejected_quality');self.assertEqual(task['request'],before);self.assertEqual(task['local_video'],'/media/4/t.mp4');self.assertNotIn('selected_task_id',seg)
if __name__=='__main__':unittest.main()
