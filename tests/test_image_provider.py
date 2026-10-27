import os,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import image_provider
class ImageContracts(unittest.TestCase):
 def test_reference_payload_and_estimate(self):
  p=image_provider.ImageProvider();r=p.prepare({'prompt':'same fictional adult in a room','reference_images':['https://example.com/face.png','https://example.com/room.png']})
  self.assertEqual(r['estimated_cny'],.22);self.assertEqual(r['payload']['parameters']['n'],1);self.assertEqual(r['payload']['parameters']['size'],'720*1280')
  self.assertEqual(r['payload']['input']['messages'][0]['content'][0],{'image':'https://example.com/face.png'})
  self.assertFalse(r['network_called'])
 def test_task_id_and_status(self):
  request=Mock(return_value={'output':{'task_id':'img-123'}});p=image_provider.ImageProvider(request)
  with patch.dict(os.environ,{'STUDIO_ENABLE_PAID_GENERATION':'true','WAN3_API_KEY':'fake-image-test-key'}):
   task=p.submit(p.prepare({'prompt':'cinematic keyframe'}),authorized=True);self.assertEqual(task,'img-123')
   self.assertIn('/services/aigc/image-generation/generation',request.call_args[0][1])
   request.return_value={'output':{'task_status':'SUCCEEDED','choices':[{'message':{'content':[{'image':'https://example.com/image.png'}]}}]},'usage':{'output_image_count':1}}
   result=p.status(task);self.assertEqual(result['status'],'completed');self.assertEqual(len(result['image_urls']),1);self.assertNotIn('X-DashScope-Async',request.call_args[0][2])
 def test_static_prompt_preflight_regression(self):
  p=image_provider.ImageProvider();r=p.prepare({'prompt':'00:04 她先看钥匙，然后转头，再问你是谁'})
  self.assertTrue(r['warnings']);self.assertIn('不画分格',r['payload']['input']['messages'][0]['content'][-1]['text'])
  r=p.prepare({'prompt':'一幅特写：右手握黄铜钥匙，右后方门保持关闭。'})
  self.assertEqual(r['warnings'],[]);self.assertIn('右手握黄铜钥匙',r['payload']['input']['messages'][0]['content'][-1]['text'])
 def test_limit_and_paid_gate(self):
  p=image_provider.ImageProvider(Mock())
  with self.assertRaises(ValueError):p.prepare({'prompt':'x','reference_images':['https://example.com/a.png']*4})
  with patch.dict(os.environ,{'STUDIO_ENABLE_PAID_GENERATION':'false'}):
   with self.assertRaises(ValueError):p.submit(p.prepare({'prompt':'x'}))
