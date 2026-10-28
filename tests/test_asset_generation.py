import copy
import os
from unittest.mock import Mock, patch

import asset_generation as gen
import asset_library as lib
import generation_scope
import image_provider
import providers
from test_asset_library import AssetFixture,png


class GenerationTests(AssetFixture):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(self.root/'private'/'credentials.json')});self.env.start()
        self.addCleanup(self.env.stop)
        self.provider=image_provider.ImageProvider();self.provider.headers=Mock(return_value={})
        self.provider.submit=Mock(return_value='provider-task');self.provider.status=Mock(return_value={'status':'completed','image_urls':['https://example.aliyuncs.com/image.png'],'usage':{},'actual_cost_cny':None})
        self.now=1000.;self.downloader=Mock(return_value=png())
        self.generation=gen.AssetGeneration(self.service,lambda _:self.provider,self.downloader,lambda:self.now)
        self.asset=self.create()

    def authorize(self,limit=3,paused=False):
        generation_scope.authorize_budgets(1,self.database,limit,9,'explicit mock fixture',self.state()['revision'])
        scope=generation_scope.read();scope['1']['paused']=paused;generation_scope.path().write_text(__import__('json').dumps(scope))

    def plan(self,asset=None,tag='main',**extra):
        asset=asset or self.asset
        items=[{'asset_id':asset['id'],'version':asset['latest_version'],'view_tag':tag,**extra}]
        model='qwen-image-3.0-pro'
        return items,self.generation.preview(1,items,model)

    def submit_plan(self,items,preview,request_id='a'*32):
        return self.generation.submit(1,preview['revision'],items,'qwen-image-3.0-pro',preview['fingerprint'],request_id)

    def test_zero_network_plan_and_paused_or_unbudgeted_refusal(self):
        items,preview=self.plan();self.assertEqual(preview['estimated_cny'],.25)
        self.assertFalse(preview['network_called']);self.assertEqual(self.state()['image_tasks'],[])
        with self.assertRaises(ValueError):self.submit_plan(items,preview)
        self.authorize(paused=True)
        with self.assertRaisesRegex(ValueError,'暂停'):self.submit_plan(items,preview)
        self.provider.submit.assert_not_called();self.assertEqual(self.state()['image_tasks'],[])

    def test_async_intent_before_network_cache_version_and_manual_adoption(self):
        self.authorize();items,preview=self.plan()
        def submit(prepared,authorized):
            task=self.state()['image_tasks'][0]
            self.assertEqual(task['kind'],'asset_image');self.assertNotIn('shot_id',task)
            self.assertEqual(task['status'],'submitting');self.assertTrue(authorized)
            self.assertEqual(task['request_sha256'],gen.digest(prepared['payload']))
            return 'provider-task'
        self.provider.submit.side_effect=submit
        self.submit_plan(items,preview)
        task=self.state()['image_tasks'][0];self.assertEqual(task['provider_task_id'],'provider-task')
        self.generation.poll(1,task['id']);self.generation.poll(1,task['id'])
        self.assertEqual(self.provider.status.call_count,1);self.assertEqual(self.downloader.call_count,1)
        current=self.service.catalog(1)['assets'][-1]
        self.assertEqual(current['latest_version'],2);self.assertIsNone(current['adopted_version'])
        self.assertTrue(self.state()['shots'][0]['approved']);self.assertEqual(self.state()['tasks'],[])
        self.assertEqual(generation_scope.category_ledger(self.state(),'image',3)['committed_cny'],.25)

    def test_unknown_has_no_id_and_never_resubmits(self):
        self.authorize();items,preview=self.plan();self.provider.submit.side_effect=TimeoutError('uncertain')
        self.submit_plan(items,preview)
        task=self.state()['image_tasks'][0];self.assertEqual(task['status'],'unknown')
        self.submit_plan(items,preview);self.generation.advance(1,'a'*32);self.generation.poll(1,task['id'])
        self.assertEqual(self.provider.submit.call_count,1);self.provider.status.assert_not_called()
        self.assertEqual(generation_scope.category_ledger(self.state(),'image',3)['committed_cny'],.25)

    def test_download_failure_retains_original_result_and_only_downloads_again(self):
        self.authorize();self.provider.submit.return_value={'status':'completed','image_urls':['https://example.aliyuncs.com/image.png'],'usage':{},'actual_cost_cny':None}
        self.downloader.side_effect=ValueError('network')
        items,preview=self.plan();self.submit_plan(items,preview)
        task=self.state()['image_tasks'][0];self.assertIn('download_error',task);self.assertEqual(task['status'],'completed')
        self.downloader.side_effect=None;self.generation.poll(1,task['id'])
        self.assertEqual(self.provider.submit.call_count,1);self.assertEqual(self.provider.status.call_count,0)
        self.assertEqual(self.state()['image_tasks'][0]['archived_version'],2)

    def test_multiple_outputs_remain_anomaly_not_accepted_or_retried(self):
        self.authorize();self.provider.submit.return_value={'status':'completed','image_urls':['https://example.aliyuncs.com/1.png','https://example.aliyuncs.com/2.png']}
        items,preview=self.plan();self.submit_plan(items,preview)
        task=self.state()['image_tasks'][0];self.assertIn('result_issue',task);self.downloader.assert_not_called()
        self.assertEqual(self.service.catalog(1)['assets'][-1]['latest_version'],1)

    def test_only_adopted_master_can_expand_and_payload_uses_exact_local_original(self):
        with self.assertRaises(ValueError):self.plan(tag='side')
        asset=self.upload(self.asset);view=asset['versions'][-1]['views'][0]
        self.action('adopt',asset_id=asset['id'],version=2);self.authorize()
        items,preview=self.plan(asset,tag='side',reference_version=2,reference_view_id=view['id'])
        self.submit_plan(items,preview)
        payload=self.provider.submit.call_args[0][0]['payload']
        image=payload['input']['messages'][0]['content'][0]['image']
        self.assertEqual(image,'data:image/png;base64,'+__import__('base64').b64encode(png()).decode())
        task=self.state()['image_tasks'][0]
        self.assertIn('material:sha256:',str(task['request']));self.assertNotIn('base64,',str(task['request']))
        self.assertEqual(task['reference_inputs'][0]['version'],2)

    def test_total_budget_model_scope_serial_rate_and_cancel_unsubmitted(self):
        second=self.create(name='手机');items=[{'asset_id':a['id'],'version':1,'view_tag':'main'} for a in [self.asset,second]]
        self.authorize(limit=.4);preview=self.generation.preview(1,items,'qwen-image-3.0-pro')
        with self.assertRaises(ValueError):self.submit_plan(items,preview)
        self.authorize(limit=1);preview=self.generation.preview(1,items,'qwen-image-3.0-pro');self.submit_plan(items,preview)
        self.assertEqual(len(self.state()['image_tasks']),2);self.assertEqual(self.provider.submit.call_count,1)
        self.assertEqual(generation_scope.category_ledger(self.state(),'image',1)['inflight_reserved_cny'],.5)
        self.generation.poll(1,self.state()['image_tasks'][0]['id'])
        self.generation.advance(1,'a'*32);self.assertEqual(self.provider.submit.call_count,1)
        self.generation.cancel_reserved(1,'a'*32)
        self.assertEqual(self.state()['image_tasks'][1]['status'],'cancelled')
        self.assertEqual(generation_scope.category_ledger(self.state(),'image',1)['committed_cny'],.25)

    def test_explicit_rejection_releases_reservation_and_never_retries(self):
        self.authorize();self.provider.submit.side_effect=providers.ProviderHTTPError(400,'InvalidParameter','bad',{})
        items,preview=self.plan();self.submit_plan(items,preview)
        self.assertEqual(self.state()['image_tasks'][0]['status'],'rejected')
        self.assertEqual(generation_scope.category_ledger(self.state(),'image',3)['committed_cny'],0)

    def test_result_archives_to_original_project_after_selected_project_switches(self):
        self.authorize()
        def submit(*args,**kwargs):
            with self.service._connect() as con:con.execute('UPDATE workspace SET current_project=2')
            return {'status':'completed','image_urls':['https://example.aliyuncs.com/1.png']}
        self.provider.submit.side_effect=submit;items,preview=self.plan()
        with self.assertRaises(ValueError):self.submit_plan(items,preview)
        self.assertEqual(self.state(1)['image_tasks'][0]['archived_version'],2)
        self.assertEqual(self.state(2)['image_tasks'],[])

    def test_real_seedream_adapter_sync_contract_and_model_scope(self):
        import ark_provider
        transport=Mock(return_value={'data':[{'url':'https://example.byteimg.com/output.png'}],'usage':{'generated_images':1}})
        adapter=ark_provider.SeedreamProvider(request=transport);adapter.headers=Mock(return_value={})
        service=gen.AssetGeneration(self.service,lambda _:adapter,self.downloader,lambda:self.now)
        items=[{'asset_id':self.asset['id'],'version':1,'view_tag':'main'}]
        self.authorize();preview=service.preview(1,items,ark_provider.IMAGE_MODEL)
        with self.assertRaises(ValueError):service.submit(1,preview['revision'],items,ark_provider.IMAGE_MODEL,preview['fingerprint'],'b'*32)
        transport.assert_not_called();self.assertEqual(self.state()['image_tasks'],[])
        generation_scope.authorize_budgets(1,self.database,1,9,'explicit mock Seedream',self.state()['revision'],models=[ark_provider.IMAGE_MODEL])
        result=service.submit(1,preview['revision'],items,ark_provider.IMAGE_MODEL,preview['fingerprint'],'b'*32)
        payload=transport.call_args[0][3]
        self.assertEqual(payload['model'],ark_provider.IMAGE_MODEL);self.assertEqual(payload['output_format'],'png')
        self.assertEqual(payload['response_format'],'url');self.assertNotIn('sequential_image_generation',payload)
        task=self.state()['image_tasks'][0];self.assertEqual(task['provider'],'seedream');self.assertIsNone(task['provider_task_id'])
        self.assertEqual(task['status'],'completed');self.assertEqual(task['archived_version'],2)
        self.assertEqual(task['content_snapshot']['asset_version'],1)

    def test_storyboard_consumes_pinned_originals_not_latest_candidate(self):
        asset=self.upload(self.asset);view=asset['versions'][-1]['views'][0]
        self.action('adopt',asset_id=asset['id'],version=2)
        self.action('bind',shot_id='s1',asset_id=asset['id'],version=2,view_ids=[view['id']])
        self.upload(asset,data=png(color=(1,2,3)))
        shot={**self.state()['shots'][0],'_material_project_id':1}
        prepared=gen.prepare_storyboard(self.service,shot,{'image_model':'qwen-image-3.0-pro'})
        uri=prepared['payload']['input']['messages'][0]['content'][0]['image']
        self.assertEqual(uri,'data:image/png;base64,'+__import__('base64').b64encode(png()).decode())
        self.assertEqual(prepared['material_reference_snapshot'][0]['version'],2)
        self.assertEqual(prepared['request_sha256'],gen.digest(prepared['payload']))
        self.assertNotIn('base64,',str(prepared['request_manifest']))
