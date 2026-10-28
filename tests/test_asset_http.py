import base64
import copy
import json
import os
import threading
import urllib.error
import urllib.request
from unittest.mock import Mock,patch

import asset_generation
import generation_scope
import image_provider
import server
import workflow_state
from test_asset_library import AssetFixture,png


class AssetHTTPTests(AssetFixture):
    def setUp(self):
        super().setUp();self.service.lock=server.LOCK
        self.provider=image_provider.ImageProvider();self.provider.headers=Mock(return_value={});self.provider.submit=Mock(return_value='asset-provider-id')
        self.provider.status=Mock(return_value={'status':'completed','image_urls':['https://example.aliyuncs.com/image.png'],'usage':{},'actual_cost_cny':None})
        self.generation=asset_generation.AssetGeneration(self.service,lambda _:self.provider,lambda _:png())
        self.patches=[patch.object(server,'ROOT',self.root),patch.object(server,'DATA',self.root),patch.object(server,'material_service',return_value=self.service),
            patch.object(server,'material_generation',return_value=self.generation),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(self.root/'private'/'credentials.json')})]
        for item in self.patches:item.start()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=self.http.serve_forever,daemon=True).start();self.url=f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown();self.http.server_close()
        for item in reversed(self.patches):item.stop()
        super().tearDown()

    def api(self,path,payload=None):
        if payload is not None:payload={'project_id':1,'revision':self.state()['revision'],**payload}
        request=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def test_manage_upload_adopt_and_media_http_is_project_scoped(self):
        code,result=self.api('assets');self.assertEqual(code,200);self.assertEqual(len(result['assets']),1)
        original=copy.deepcopy(self.state())
        code,result=self.api('assets/create',{'kind':'object','name':'钥匙','summary':'黄铜'})
        self.assertEqual(code,200);asset=result['assets'][-1]
        code,result=self.api('assets/upload',{'asset_id':asset['id'],'filename':'image.png','view_tag':'main','base64':base64.b64encode(png()).decode()})
        self.assertEqual(code,200);view=result['assets'][-1]['versions'][-1]['views'][0]
        with urllib.request.urlopen(self.url+view['url']) as response:
            self.assertEqual(response.headers['Content-Type'],'image/png');self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(response.read(),png())
        self.assertEqual(self.state()['characters'],original['characters']);self.assertEqual(self.state()['shots'],original['shots'])
        self.assertEqual(self.api('assets/adopt',{'asset_id':asset['id'],'version':2})[0],200)
        with self.service._connect() as con:con.execute('UPDATE workspace SET current_project=2')
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+view['url'])
        self.assertEqual(error.exception.code,404)
        self.assertEqual(self.api('assets/edit',{'asset_id':asset['id'],'name':'越界'})[0],400)

    def test_real_routes_preview_paused_and_image_poll_dispatch_without_video_jobs(self):
        asset=self.create();items=[{'asset_id':asset['id'],'version':1,'view_tag':'main'}]
        code,preview=self.api('assets/generation/preview',{'items':items,'model':'qwen-image-3.0-pro'})
        self.assertEqual(code,200);self.assertFalse(preview['network_called'])
        generation_scope.authorize_budgets(1,self.database,2,9,'explicit mock fixture',self.state()['revision'])
        scope=generation_scope.read();scope['1']['paused']=True;generation_scope.path().write_text(json.dumps(scope))
        payload={'items':items,'model':'qwen-image-3.0-pro','fingerprint':preview['fingerprint'],'request_id':'b'*32}
        self.assertEqual(self.api('assets/generation/submit',payload)[0],400);self.provider.submit.assert_not_called()
        scope['1']['paused']=False;generation_scope.path().write_text(json.dumps(scope))
        self.assertEqual(self.api('assets/generation/submit',payload)[0],200)
        task=self.state()['image_tasks'][0];self.assertNotIn('shot_id',task)
        code,result=self.api('image/poll',{'task_id':task['id']})
        self.assertEqual(code,200);self.assertEqual(result['image_tasks'][0]['archived_version'],2)
        self.assertEqual(result['tasks'],[]);self.assertEqual(self.provider.submit.call_count,1)
        self.assertEqual(self.api('assets/generation/submit',payload)[0],200);self.assertEqual(self.provider.submit.call_count,1)

    def test_reference_pin_snapshots_and_approval_invalidation_are_content_bound(self):
        asset=self.upload(self.create());view=asset['versions'][-1]['views'][0];self.action('adopt',asset_id=asset['id'],version=2)
        code,result=self.api('assets/bind',{'shot_id':'s1','asset_id':asset['id'],'version':2,'view_ids':[view['id']]})
        self.assertEqual(code,200);state=server.read();shot=state['shots'][0]
        self.assertFalse(shot['approved'])
        shot.update(storyboard_task_id='board',storyboard_local='/media/1/board.png',storyboard_sha256='a'*64,approved=True,approved_image_task_id='board')
        shot['approval_snapshot']=workflow_state.record_approval(state,shot,'fixture','time')
        self.assertTrue(workflow_state.valid_approval(state,shot))
        snapshot=server.content_snapshot(state,shot)
        self.assertEqual(snapshot['shot']['asset_references'][0]['version'],2)
        shot['asset_references'][0]['version']=3
        self.assertFalse(workflow_state.valid_approval(state,shot));self.assertEqual(snapshot['shot']['asset_references'][0]['version'],2)

    def test_invalid_upload_and_cross_origin_do_not_create_records(self):
        asset=self.create();before=self.state()
        self.assertEqual(self.api('assets/upload',{'asset_id':asset['id'],'view_tag':'main','filename':'image.svg','base64':base64.b64encode(b'<svg/>').decode()})[0],400)
        self.assertEqual(self.state(),before)
        request=urllib.request.Request(self.url+'/api/assets/create',data=b'{}',headers={'Origin':'https://example.com','Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,400)

    def test_real_storyboard_route_transmits_pinned_pixels_and_snapshots_manifest(self):
        asset=self.upload(self.create());view=asset['versions'][-1]['views'][0]
        self.action('adopt',asset_id=asset['id'],version=2)
        self.action('bind',shot_id='s1',asset_id=asset['id'],version=2,view_ids=[view['id']])
        self.upload(asset,data=png(color=(1,2,3)))
        generation_scope.authorize_budgets(1,self.database,2,9,'explicit mock storyboard',self.state()['revision'])
        with patch.object(server.image_provider,'for_model',return_value=self.provider):
            code,preview=self.api('image/prepare',{'shot_id':'s1'})
            self.assertEqual(code,200);self.assertFalse(preview['network_called'])
            self.assertIn('material:sha256:',str(preview['payload']));self.assertNotIn('base64,',str(preview['payload']))
            code,result=self.api('image/submit',{'shot_id':'s1'})
        self.assertEqual(code,200,result)
        payload=self.provider.submit.call_args[0][0]['payload']
        self.assertEqual(payload['input']['messages'][0]['content'][0]['image'],'data:image/png;base64,'+base64.b64encode(png()).decode())
        task=result['image_tasks'][0]
        self.assertEqual(task['material_reference_snapshot'][0]['version'],2)
        self.assertEqual(task['content_snapshot']['shot']['asset_references'][0]['version'],2)
        self.assertEqual(task['request_sha256'],asset_generation.digest(payload))
        self.assertNotIn('base64,',str(task['request']))

    def test_generic_save_cannot_bypass_version_selection(self):
        before=self.state();shots=copy.deepcopy(before['shots'])
        shots[0]['asset_references']=[{'asset_id':'forged','version':1,'views':[]}]
        self.assertEqual(self.api('save',{'shots':shots})[0],400)
        self.assertEqual(self.state(),before)
