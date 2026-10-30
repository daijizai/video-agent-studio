import hashlib,subprocess,tempfile,unittest
from pathlib import Path
import voice_assets
class VoiceAssetsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);folder=self.root/'assets'/'4';folder.mkdir(parents=True)
  self.media=folder/'source.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=5','-c:a','aac','-vn','-y',str(self.media)],check=True)
  self.task={'id':'accepted','status':'completed','review_status':'accepted','local_video':'/media/4/source.mp4','accepted_video_sha256':hashlib.sha256(self.media.read_bytes()).hexdigest(),'media_info':{'duration':5}}
  self.state={'project_id':4,'characters':[{'name':'机器人'}],'tasks':[self.task]}
 def tearDown(self):self.temp.cleanup()
 def create(self):voice_assets.operate(self.state,self.root,'create',{'name':'机器人','source_task_id':'accepted','start':1,'end':4})
 def test_candidate_preview_and_explicit_approval(self):
  self.create();asset=self.state['voice_assets'][0];v=asset['versions'][0]
  self.assertEqual(v['review_status'],'candidate');self.assertIsNone(asset['adopted_version']);self.assertGreater(len(voice_assets.audio_data(self.state,self.root,4,v['id'])),0)
  voice_assets.operate(self.state,self.root,'adopt',{'asset_id':asset['id'],'version':1});self.assertEqual(asset['adopted_version'],1)
 def test_reject_unapproved_source_and_cross_project_access(self):
  self.task['review_status']='pending'
  with self.assertRaisesRegex(ValueError,'已验收'):self.create()
  self.task['review_status']='accepted';self.create();v=self.state['voice_assets'][0]['versions'][0]
  with self.assertRaises(ValueError):voice_assets.audio_data(self.state,self.root,5,v['id'])
 def test_changed_audio_rejected_and_source_preserved(self):
  source_hash=hashlib.sha256(self.media.read_bytes()).hexdigest();self.create();a=self.state['voice_assets'][0];v=a['versions'][0];(self.root/'assets'/'4'/'voice'/(v['id']+'.wav')).write_bytes(b'changed')
  with self.assertRaises(ValueError):voice_assets.operate(self.state,self.root,'adopt',{'asset_id':a['id'],'version':1})
  self.assertEqual(hashlib.sha256(self.media.read_bytes()).hexdigest(),source_hash)
if __name__=='__main__':unittest.main()
