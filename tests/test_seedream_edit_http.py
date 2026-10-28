"""Workbench HTTP integration; temporary DB and mocked Ark only."""
import json
import threading
import urllib.request
import urllib.error
from unittest.mock import patch
from test_seedream_edit import SeedreamEditTests
import server

class SeedreamEditHTTPTests(SeedreamEditTests):
    def setUp(self):
        super().setUp();self.service.lock=server.LOCK
        self.patches=[patch.object(server,'ROOT',self.root),patch.object(server,'DATA',self.root),patch.object(server,'seedream_edit_service',return_value=self.service)]
        for p in self.patches:p.start()
        with self.service.transaction() as con:
            con.execute('CREATE TABLE workspace (id INTEGER PRIMARY KEY,current_project INTEGER)');con.execute('INSERT INTO workspace VALUES (1,1)')
        self.service.selected=server.current_project
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.url='http://127.0.0.1:'+str(self.http.server_port)
    def tearDown(self):
        self.http.shutdown();self.http.server_close()
        for p in reversed(self.patches):p.stop()
        super().tearDown()
    def api(self,path,payload=None):
        req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=10) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def common(self):return {'project_id':1,'revision':self.state()['revision']}
    def http_begin(self):
        code,task=self.api('repair/begin',{**self.common(),'shot_id':'shot','source_url':'/media/1/original.png','region':{'x':16,'y':16,'width':32,'height':32},'description':'修正杯子','request_id':'d'*32})
        self.assertEqual(code,200,task);return task
    def test_default_http_flow_preflight_and_candidate_adoption(self):
        code,ready=self.api('repair/preflight');self.assertEqual(code,200);self.assertEqual(ready['backend'],'seedream');self.assertEqual(ready['estimated_cny'],.12)
        self.assertFalse(ready['api_verified']);self.assertFalse(ready['quality_verified']);self.assertNotIn(self.key,json.dumps(ready))
        with patch.object(server,'repair_service',side_effect=AssertionError('wrong local executor')):
            task=self.http_begin();code,result=self.api('repair/execute',{**self.common(),'task_id':task['id']})
        self.assertEqual(code,200,result);self.assertEqual(result['provider'],'seedream-edit');self.assertEqual(result['status'],'completed')
        code,adopted=self.api('repair/adopt',{**self.common(),'task_id':task['id'],'candidate_sha256':result['candidate_sha256'],'source':'human browser adoption'})
        self.assertEqual(code,200);self.assertEqual(adopted['status'],'adopted');self.assertFalse(self.state()['shots'][0]['approved'])
    def test_image_poll_restores_only_download_not_supplier_or_comfy_status(self):
        self.download_failure=True;task=self.http_begin();code,result=self.api('repair/execute',{**self.common(),'task_id':task['id']});self.assertTrue(result['download_error'])
        self.download_failure=False
        with patch.object(server.image_provider.ImageProvider,'status',side_effect=AssertionError('wrong model status')),patch.object(server,'remote',side_effect=AssertionError('wrong comfy')):
            code,state=self.api('image/poll',{**self.common(),'task_id':task['id']})
        self.assertEqual(code,200);self.assertTrue(state['image_tasks'][0]['candidate_local']);self.assertEqual(len(self.sent),1)
    def test_existing_intent_can_resume_without_double_reservation(self):
        import generation_scope
        import seedream_edit
        scope={'1':{'id':'scope','database':str(self.database.resolve()),'models':[seedream_edit.MODEL],'budget_mode':'separate_v1','budget_grants':{'image':{'id':'finite-image-grant','limit':.12}},'paused':False}}
        with patch.object(generation_scope,'read',return_value=scope):
            task=self.http_begin()
            code,ready=self.api('repair/preflight')
            self.assertFalse(ready['execution_allowed']);self.assertIn(task['id'],ready['resumable_task_ids'])
            code,result=self.api('repair/execute',{**self.common(),'task_id':task['id']})
            self.assertEqual(code,200);self.assertEqual(result['status'],'completed');self.assertEqual(len(self.sent),1)

    def test_material_task_is_never_seedream_edit(self):
        with self.service.transaction() as con:
            state=self.service.state(con,1);state['image_tasks'].append({'id':'material','kind':'asset_image','provider':'seedream-edit','status':'reserved','estimate':.12});self.service.save(con,state)
        code,_=self.api('repair/poll',{**self.common(),'task_id':'material'});self.assertEqual(code,400)
        with patch.object(server,'material_generation') as material:
            material.return_value.poll.return_value={}
            code,_=self.api('image/poll',{**self.common(),'task_id':'material'})
            self.assertEqual(code,200);material.return_value.poll.assert_called_once_with(1,'material')
        with self.assertRaises(ValueError):self.begin()
    def test_paused_and_cross_project_http_reject_without_network(self):
        self.paused=True
        code,_=self.api('repair/begin',{**self.common(),'shot_id':'shot','source_url':'/media/1/original.png','region':{'x':1,'y':1,'width':16,'height':16},'description':'x','request_id':'c'*32});self.assertEqual(code,400)
        self.paused=False
        with self.service.transaction() as con:con.execute('UPDATE workspace SET current_project=2')
        code,_=self.api('repair/execute',{'project_id':1,'task_id':'not-real'});self.assertEqual(code,400);self.assertEqual(self.sent,[])
    def test_unknown_http_cannot_resubmit_and_no_raw_error_leak(self):
        task=self.http_begin()
        def fail(*args):self.sent.append(args);raise TimeoutError(self.key)
        self.service.request=fail
        code,result=self.api('repair/execute',{**self.common(),'task_id':task['id']});self.assertEqual(code,200);self.assertEqual(result['status'],'unknown')
        code,result=self.api('repair/execute',{**self.common(),'task_id':task['id']});self.assertEqual(code,400);self.assertNotIn(self.key,json.dumps(result));self.assertEqual(len(self.sent),1)

# The inherited suite also runs under the host's actual shared lock.
del SeedreamEditTests
