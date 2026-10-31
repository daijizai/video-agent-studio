import unittest
from unittest.mock import Mock,patch
import providers
from video_costing import public_estimate,record_screenshot
class CostTests(unittest.TestCase):
 def task(self):return {'status':'completed','request':{'model':'doubao-seedance-2-5-260628','resolution':'720p','content':[{'type':'text','text':'x'},{'type':'video_url'}]},'usage':{'completion_tokens':500000}}
 def test_video_reference_price_is_estimate_not_settlement(self):
  result=public_estimate(self.task());self.assertEqual(result['amount_cny'],21);self.assertEqual(result['rate_cny_per_million'],42);self.assertEqual(result['kind'],'published_list_price_estimate')
 def test_no_video_and_missing_usage(self):
  t=self.task();t['request']['content'].pop();self.assertEqual(public_estimate(t)['amount_cny'],35);t['usage']={};self.assertIsNone(public_estimate(t))
 def test_unknown_models_or_pending_never_guess(self):
  t=self.task();t['status']='running';self.assertIsNone(public_estimate(t));t=self.task();t['request']['model']='other';self.assertIsNone(public_estimate(t))
 def test_provider_returns_real_status_and_safe_metadata_not_fake_percentage(self):
  request=Mock(return_value={'status':'running','created_at':100,'updated_at':120,'resolution':'720p','usage':{},'unexpected_secret':'do-not-persist'})
  with patch.object(providers.Provider,'headers',return_value={}),patch.object(providers.Provider,'base_url',return_value='https://example.test'):
   result=providers.Provider('seedance25',request).status('task_123')
  self.assertEqual(result['status'],'running');self.assertEqual(result['provider_metadata']['created_at'],100)
  self.assertNotIn('progress',result);self.assertNotIn('unexpected_secret',str(result));self.assertIsNone(result['actual_cost_cny'])
 def test_screenshot_matching_records_reported_values_without_claiming_settlement(self):
  a=self.task();a['id']='first';b=self.task();b['id']='second';pending={'id':'unknown','status':'unknown','request':{'model':'doubao-seedance-2-5-260628'}}
  state={'tasks':[a,b,pending]};summary=record_screenshot(state,['21.000000','21.000000'])
  self.assertEqual(summary['total_cny'],'42.000000');self.assertEqual(summary['count'],2)
  self.assertEqual(a['screenshot_cost']['same_amount_count'],2)
  self.assertEqual(a['screenshot_cost']['amount_type'],'截图未显示列名，待核对')
  self.assertNotIn('actual_cost_cny',a);self.assertNotIn('screenshot_cost',pending)
 def test_screenshot_mismatch_is_atomic(self):
  task=self.task();state={'tasks':[task]}
  with self.assertRaisesRegex(ValueError,'未保存'):record_screenshot(state,['20.00'])
  self.assertNotIn('screenshot_cost',task);self.assertNotIn('video_screenshot_cost_summary',state)
if __name__=='__main__':unittest.main()
