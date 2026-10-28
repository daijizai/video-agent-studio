"""Real workbench routes, simulated executor, temporary DB only."""
import base64
import copy
import json
import threading
import urllib.error
import urllib.request
from unittest.mock import patch
from test_comfy_repair import RepairTests
import server
import comfy_templates

class RepairHTTPTests(RepairTests):
    def setUp(self):
        super().setUp()
        self.service.lock=server.LOCK
        self.patches=[patch.object(server,'ROOT',self.root),patch.object(server,'DATA',self.root),patch.object(server,'repair_service',return_value=self.service)]
        for item in self.patches:item.start()
        with self.service.transaction() as con:
            con.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY,current_project INTEGER)')
            con.execute('INSERT INTO workspace VALUES (1,1)')
        self.service.selected=server.current_project
        self.host=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=self.host.serve_forever,daemon=True).start()
        self.host_url='http://127.0.0.1:'+str(self.host.server_port)

    def tearDown(self):
        self.host.shutdown();self.host.server_close()
        for item in reversed(self.patches):item.stop()
        super().tearDown()

    def api(self,path,payload=None):
        headers={'Content-Type':'application/json'}
        request=urllib.request.Request(self.host_url+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=10) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def common(self):return {'project_id':1,'revision':self.state()['revision']}

    def http_begin(self):
        common=self.common()
        code,mask=self.api('comfy/mask',{**common,'shot_id':'shot1','png_base64':base64.b64encode(self.mask).decode()})
        self.assertEqual(code,200)
        code,task=self.api('comfy/begin',{**common,'shot_id':'shot1','source_url':'/media/1/original.png','mask_url':mask['local_url'],'values':{'description':'修正区域'},'request_id':'b'*32})
        self.assertEqual(code,200);return task

    def test_public_routes_full_flow_and_image_dispatch(self):
        code,health=self.api('comfy/preflight');self.assertEqual(code,200)
        self.assertTrue(health['ready']);self.assertNotIn('template',health);self.assertNotIn('issues',health)
        task=self.http_begin()
        code,submitted=self.api('comfy/execute',{**self.common(),'task_id':task['id']})
        self.assertEqual(code,200);self.assertEqual(submitted['status'],'queued')
        self.finished=True
        with patch.object(server.image_provider.ImageProvider,'status',side_effect=AssertionError('wrong provider')):
            code,state=self.api('image/poll',{**self.common(),'task_id':task['id']})
        self.assertEqual(code,200);candidate=state['image_tasks'][0]
        self.assertEqual(candidate['status'],'completed');self.assertTrue(state['shots'][0]['approved'])
        code,adopted=self.api('comfy/adopt',{**self.common(),'task_id':task['id'],'candidate_sha256':candidate['candidate_sha256'],'source':'explicit test human adoption'})
        self.assertEqual(code,200);self.assertEqual(adopted['status'],'adopted')
        self.assertFalse(server.read()['shots'][0]['approved']);self.assertEqual(self.calls.count(('POST','/prompt')),1)

    def test_host_concurrency_and_stale_save_cannot_drop_task(self):
        before=server.read();before['_write_revision']=before['revision']
        task=self.http_begin()
        with self.assertRaisesRegex(ValueError,'版本'):server.save(before)
        reached=threading.Event();release=threading.Event();original=self.transport.upload
        def blocked(name,data):
            reached.set();release.wait(5);return original(name,data)
        response=[]
        with patch.object(self.transport,'upload',side_effect=blocked):
            thread=threading.Thread(target=lambda:response.append(self.api('comfy/execute',{**self.common(),'task_id':task['id']})))
            thread.start();self.assertTrue(reached.wait(3))
            # The upload waits, but ordinary project edits must still acquire the global lock.
            latest=server.read()
            code,updated=self.api('save',{'project_id':1,'revision':latest['revision'],'title':'concurrent saved title'})
            release.set();thread.join(5);self.assertEqual(code,200,updated)
        self.assertFalse(thread.is_alive());self.assertEqual(response[0][0],200)
        final=server.read();self.assertEqual(final['title'],'concurrent saved title')
        self.assertEqual(final['image_tasks'][0]['provider_task_id'],'prompt-test')

    def test_cross_project_and_paused_public_errors_do_not_leak(self):
        self.paused=True
        code,result=self.api('comfy/begin',{**self.common(),'shot_id':'shot1','source_url':'/media/1/original.png','mask_url':'/media/1/mask.png','values':{'description':'x'},'request_id':'c'*32})
        self.assertEqual(code,400);self.assertNotIn(str(self.root),str(result))
        self.paused=False
        with self.service.transaction() as con:con.execute('UPDATE workspace SET current_project=2')
        code,result=self.api('comfy/execute',{'project_id':1,'task_id':'wrong'})
        self.assertEqual(code,400);self.assertEqual(self.calls.count(('POST','/prompt')),0)

    def test_uploading_and_archive_pending_block_other_image_submission(self):
        task=self.http_begin()
        for status in ('uploading','archive_pending'):
            self.service.update(1,task['id'],status=status)
            with patch.object(server.generation_scope,'active',return_value=True),patch.object(server.generation_scope,'is_paused',return_value=False):
                code,result=self.api('image/submit',{**self.common(),'shot_id':'shot1','redo':True})
            self.assertEqual(code,400);self.assertIn('在途',result['error'])

# Avoid unittest rediscovering the imported base in this module.
del RepairTests
