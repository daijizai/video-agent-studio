"""Pinned Ark contract tests: fake credentials, no network or paid generation."""
import copy,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ark_provider as a,providers,image_provider,workflow_state

class ArkContracts(unittest.TestCase):
 def test_seedance_reference_mode_and_price_basis(self):
  shot={'duration':30,'prompt':'a still room','storyboard_image':'https://example.com/current.png','reference_images':['https://example.com/other.png']}
  for resolution,width,height,rate in [('480p',480,854,.07),('720p',720,1280,.07),('1080p',1080,1920,.077)]:
   r=a.prepare_video(shot,{'resolution':resolution,'ratio':'9:16','audio':True})
   self.assertEqual(r['payload']['model'],a.VIDEO_MODEL);self.assertEqual(r['payload']['omni_reference_task_type'],'reference')
   self.assertEqual(r['payload']['content'][1]['image_url']['url'],shot['storyboard_image'])
   self.assertEqual(r['payload']['content'][1]['role'],'reference_image');self.assertTrue(r['payload']['generate_audio']);self.assertFalse(r['network_called'])
   basis=r['estimate_basis'];self.assertEqual((basis['width'],basis['height']),(width,height));self.assertEqual(basis['reserved_seconds'],31)
   self.assertGreaterEqual(r['estimated_cny'],width*height*24*30/1024*rate/1000)
  self.assertEqual(a.prepare_video(shot,{'resolution':'480p','ratio':'1:1'})['estimate_basis']['width'],640)
 def test_seedance_validates_supported_subset(self):
  shot={'duration':5,'prompt':'scene'}
  for change in [{'duration':3},{'duration':31},{'duration':4.5},{'prompt':''},{'reference_images':['oss://dashscope-instant/a']},{'reference_images':['https://example.com/video.mp4']},{'reference_images':[None]},{'reference_images':['https://example.com/a']*31}]:
   with self.subTest(change=change),self.assertRaises(ValueError):a.prepare_video({**shot,**change},{})
  for config in [{'resolution':'4k'},{'ratio':'adaptive'},{'audio':'true'}]:
   with self.assertRaises(ValueError):a.prepare_video(shot,config)
 def test_seedance_submit_query_and_error_normalization(self):
  request=Mock(return_value={'id':'cgt-test'});p=providers.Provider('seedance25',request=request)
  prepared=p.prepare({'duration':5,'prompt':'scene'},{})
  with patch('secret_store.get_key',return_value='fake-ark-contract-key'):
   with self.assertRaises(ValueError):p.submit(prepared,'intent')
   request.assert_not_called();self.assertEqual(p.submit(prepared,'intent',authorized=True),'cgt-test')
   self.assertTrue(request.call_args.args[1].endswith('/api/v3/contents/generations/tasks'))
   for raw,normalized in [('queued','queued'),('running','running'),('succeeded','completed'),('failed','failed'),('expired','failed'),('cancelled','cancelled')]:
    request.return_value={'status':raw,'content':{'video_url':'https://example.volces.com/a.mp4'},'usage':{'completion_tokens':100},'error':{'code':'Example'}}
    result=p.status('cgt-test');self.assertEqual(result['status'],normalized);self.assertIsNone(result['actual_cost_cny']);self.assertNotIn('X-DashScope-Async',request.call_args.args[2])
 def test_seedream_single_png_and_no_unsupported_group_parameter(self):
  p=a.SeedreamProvider();r=p.prepare({'prompt':'single object','reference_images':['https://example.com/a.png']})
  self.assertEqual(r['payload']['model'],a.IMAGE_MODEL);self.assertEqual(r['payload']['size'],'2K');self.assertEqual(r['payload']['output_format'],'png');self.assertFalse(r['payload']['stream'])
  self.assertEqual(r['estimated_cny'],.12);self.assertNotIn('sequential_image_generation',r['payload']);self.assertIn('720:1280',r['payload']['prompt'])
  self.assertIsInstance(image_provider.for_model(a.IMAGE_MODEL),a.SeedreamProvider)
  request=Mock(return_value={'data':[{'url':'https://example.byteimg.com/a.png'}],'usage':{'generated_images':1}});p=a.SeedreamProvider(request)
  with patch('secret_store.get_key',return_value='fake-ark-contract-key'):
   with self.assertRaises(ValueError):p.submit(r)
   request.assert_not_called();result=p.submit(r,authorized=True);self.assertEqual(result['status'],'completed');self.assertNotIn('provider_task_id',result)
   request.return_value={'data':[]}
   with self.assertRaises(RuntimeError):p.submit(r,authorized=True)
 def test_new_reference_binding_does_not_rewrite_legacy_approval(self):
  shot={'storyboard_task_id':'img','storyboard_sha256':'a'*64,'storyboard_image':'https://example.com/a.png'}
  with self.assertRaises(ValueError):a.require_reference_approval(shot)
  shot['ark_reference_approval']=a.reference_binding(shot);a.require_reference_approval(shot)
  shot['storyboard_image']='https://example.com/changed.png'
  with self.assertRaises(ValueError):a.require_reference_approval(shot)

if __name__=='__main__':unittest.main()
