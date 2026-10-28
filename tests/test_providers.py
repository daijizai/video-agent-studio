import unittest, os, sys
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import providers
class ProviderContracts(unittest.TestCase):
    def setUp(self):
        self.shot={'prompt':'character1 walks through fog','duration':5,'reference_images':['https://example.com/role.png']}
    def test_wan_contract_and_price(self):
        transport=Mock(return_value={'output':{'task_id':'wan-123'}})
        p=providers.Provider('wan',transport);prepared=p.prepare(self.shot,{'audio':False})
        self.assertEqual(prepared['estimated_cny'],.75)
        self.assertEqual(prepared['payload']['input']['reference_urls'],self.shot['reference_images'])
        self.assertEqual(prepared['payload']['parameters']['size'],'1280*720')
        transport.assert_not_called()
        with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'test-secret','WAN_WORKSPACE_ID':'workspace-test','STUDIO_ENABLE_PAID_GENERATION':'true'}):
            self.assertEqual(p.submit(prepared,'local-id',authorized=True),'wan-123')
            args=transport.call_args[0]
            self.assertEqual(args[0],'POST');self.assertIn('workspace-test.cn-beijing.maas.aliyuncs.com',args[1]);self.assertEqual(args[2]['X-DashScope-Async'],'enable')
    def test_wan3_official_contract(self):
        request=Mock(return_value={'output':{'task_id':'wan3-123'}})
        p=providers.Provider('wan3',request);r=p.prepare(self.shot,{'resolution':'480p','audio':True})
        self.assertEqual(r['estimated_cny'],1.5)
        self.assertEqual(r['payload']['model'],'wan3.0-video')
        self.assertEqual(r['payload']['input']['media'],[{'type':'reference_image','url':'https://example.com/role.png'}])
        self.assertNotIn('reference_urls',r['payload']['input']);self.assertNotIn('size',r['payload']['parameters'])
        self.assertEqual(r['payload']['parameters']['resolution'],'480P')
        with patch.dict(os.environ,{'WAN3_API_KEY':'fake-wan3-secret','STUDIO_ENABLE_PAID_GENERATION':'true'}):
            self.assertEqual(p.submit(r,'local-intent',authorized=True),'wan3-123')
        self.assertTrue(request.call_args[0][1].startswith('https://cn-beijing.maas.qianwenaiapi.com/api/v1/'))
        t2v=p.prepare({**self.shot,'reference_images':[],'duration':30},{'resolution':'720p'})
        self.assertNotIn('media',t2v['payload']['input']);self.assertEqual(t2v['estimated_cny'],18)
    def test_seedance_contract(self):
        p=providers.Provider('seedance');r=p.prepare(self.shot,{'audio':True})
        self.assertEqual(r['estimated_cny'],2.49)
        self.assertEqual(r['payload']['content'][1]['role'],'reference_image')
        self.assertTrue(r['payload']['generate_audio'])
    def test_paid_disabled(self):
        request=Mock();p=providers.Provider('wan',request)
        with patch.dict(os.environ,{'STUDIO_ENABLE_PAID_GENERATION':'false'}):
            with self.assertRaises(ValueError):p.submit(p.prepare(self.shot,{}),'local-id')
        request.assert_not_called()
    def test_invalid_reference_and_duration(self):
        for override in [{'duration':11},{'duration':2.5},{'reference_images':[]},{'reference_images':['file:///private/key']},{'reference_images':['https://example.com/role.mp4']}]:
            with self.assertRaises(ValueError):providers.Provider('wan').prepare({**self.shot,**override},{})
    def test_status_normalization(self):
        request=Mock(return_value={'output':{'task_status':'SUCCEEDED','video_url':'https://example.com/result.mp4'},'usage':{'duration':5}})
        with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'test-secret','WAN_WORKSPACE_ID':'test'}):
            result=providers.Provider('wan',request).status('wan-123')
        self.assertEqual(result['status'],'completed');self.assertIsNone(result['actual_cost_cny']);self.assertEqual(request.call_args[0][0],'GET')
    def test_no_key_leak(self):
        with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'test-secret'}):
            self.assertNotIn('test-secret',str(providers.config_status()))
    def test_prime_minimum_quality_audio_and_prices(self):
        p=providers.Provider('wan3-prime');shot={'duration':30,'prompt':'single approved sequence','reference_images':['https://example.com/approved.png']}
        for resolution,price in [('480p',13.5),('720p',27),('1080p',54)]:
            r=p.prepare(shot,{'resolution':resolution,'audio':True,'ratio':'9:16'});self.assertEqual(r['estimated_cny'],price);self.assertEqual(r['payload']['model'],'wan3.0-video-prime');self.assertTrue(r['payload']['parameters']['audio']);self.assertEqual(r['payload']['parameters']['duration'],30)
