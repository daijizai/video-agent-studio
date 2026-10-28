"""Independent edit adapter, mock Ark requests and temporary project DB only."""
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import comfy_assets
import generation_scope
import secret_store
import seedream_edit as edit
import workflow_state

class SeedreamEditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.database=self.root/'studio.db'
        self.key='fake-test-credential-never-transmit';self.secrets=patch.object(secret_store,'stored',return_value={'ARK_API_KEY':self.key});self.secrets.start()
        self.source=comfy_assets.encode(64,64,bytes((20,30,40,255))*4096)
        self.generated=comfy_assets.encode(64,64,bytes((200,100,80,255))*4096)
        folder=self.root/'assets'/'1';folder.mkdir(parents=True);(folder/'original.png').write_bytes(self.source)
        shot={'id':'shot','name':'模拟局部编辑','prompt':'original','duration':5,'frame':'close','estimate':0,
              'storyboard_local':'/media/1/original.png','storyboard_sha256':comfy_assets.sha(self.source),'storyboard_task_id':'old','approved_image_task_id':'old','approved':True}
        state={'project_id':1,'revision':0,'budget':1,'shots':[shot],'image_tasks':[],'tasks':[],'script':'fixture','characters':[],'continuity':'','final_video':{'local_url':'untouched.mp4'}}
        shot['approval_snapshot']=workflow_state.record_approval(state,shot,'human fixture','test')
        with sqlite3.connect(self.database) as con:
            con.execute('CREATE TABLE state (id INTEGER PRIMARY KEY,body TEXT)');con.execute('CREATE TABLE revisions (id INTEGER PRIMARY KEY,body TEXT,project_id INTEGER)')
            for pid in (1,2):con.execute('INSERT INTO state VALUES (?,?)',(pid,json.dumps(state)))
        self.paused=False;self.budget=Decimal('.12');self.sent=[];self.downloads=[];self.download_failure=False
        self.response={'data':[{'url':'https://images.byteimg.com/result.png'}],'usage':{'generated_images':1},'id':'provider-request-1'}
        def authorize(state,database,kind,estimate,model,shot_id=None):
            if kind!='image' or model!=edit.MODEL:raise ValueError('范围拒绝')
            used=sum(Decimal(str(t['estimate'])) for t in state.get('image_tasks',[]) if t['status']!='rejected')
            if used+Decimal(str(estimate))>self.budget:raise ValueError('预算不足')
            return 'finite-image-grant'
        def request(method,url,headers,payload):
            self.sent.append((method,url,headers,payload))
            # The intent and .12 reservation are durable before POST; no DB write lock held.
            with sqlite3.connect(self.database,timeout=.1) as con:
                con.execute('BEGIN IMMEDIATE');body=json.loads(con.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
                self.assertEqual(body['image_tasks'][-1]['status'],'uploading');self.assertEqual(body['image_tasks'][-1]['estimate'],.12)
            return copy.deepcopy(self.response)
        def downloader(url):
            self.downloads.append(url)
            if self.download_failure:raise TimeoutError('fake failure')
            self.assertEqual(self.state()['image_tasks'][-1]['status'],'completed')
            return self.generated
        self.service=edit.SeedreamEditService(self.root,self.database,request,downloader,authorize,lambda *args:self.paused)

    def tearDown(self):self.secrets.stop();self.temp.cleanup()
    def state(self):
        with self.service.transaction() as con:return self.service.state(con,1)
    def begin(self,**changes):
        args={'project_id':1,'revision':self.state()['revision'],'shot_id':'shot','source_url':'/media/1/original.png','region':{'x':16,'y':16,'width':32,'height':32},'description':'把框内杯子改为红色','request_id':'a'*32}
        args.update(changes);return self.service.begin(**args)
    def submit(self):
        task=self.begin();return self.service.execute(1,task['id'])

    def test_bbox_coordinates_clamp_edges_and_reject_overflow(self):
        self.assertEqual(edit.bbox({'x':0,'y':0,'width':64,'height':64},64,64),[0,0,999,999])
        self.assertEqual(edit.bbox({'x':16,'y':16,'width':32,'height':32},64,64),[250,250,750,750])
        for region in ({'x':-1,'y':0,'width':1,'height':1},{'x':63,'y':0,'width':2,'height':1},{'x':0,'y':0,'width':True,'height':1},{'x':0,'y':0,'width':0,'height':1}):
            with self.assertRaises(ValueError):edit.bbox(region,64,64)
        with self.assertRaises(ValueError):edit.bbox({'x':0,'y':0,'width':1,'height':1},4096,4096)

    def test_sync_success_data_uri_cost_and_full_image_candidate(self):
        task=self.submit();self.assertEqual(task['status'],'completed');self.assertEqual(task['estimate'],.12)
        self.assertIsNone(task['actual_cost_cny']);self.assertEqual(task['review_status'],'unreviewed');self.assertFalse(task['outside_pixels_locked'])
        payload=self.sent[0][3];self.assertEqual(payload['model'],edit.MODEL);self.assertEqual(payload['size'],'2K');self.assertFalse(payload['layer_decomposition'])
        self.assertTrue(payload['image'].startswith('data:image/png;base64,'));self.assertNotIn('/media/',payload['image']);self.assertIn('<bbox>250 250 750 750</bbox>',payload['prompt'])
        data,_=edit.read_image(self.root,1,task['candidate_local']);self.assertEqual(data,self.generated) # No false outside-mask lock.
        self.assertEqual(self.state()['shots'][0]['storyboard_local'],'/media/1/original.png')
        persisted=json.dumps(self.state());self.assertNotIn(self.key,persisted);self.assertNotIn('data:image/png;base64,',persisted);self.assertEqual(len(self.sent),1)

    def test_pause_budget_model_and_approval_reject_without_call(self):
        self.paused=True
        with self.assertRaisesRegex(ValueError,'暂停'):self.begin()
        self.paused=False;self.budget=Decimal('.11')
        with self.assertRaisesRegex(ValueError,'预算'):self.begin()
        self.budget=Decimal('.12')
        with self.service.transaction() as con:
            state=self.service.state(con,1);state['shots'][0]['approved']=False;self.service.save(con,state)
        with self.assertRaises(ValueError):self.begin()
        self.assertEqual(self.sent,[]);self.assertEqual(self.state()['image_tasks'],[])

    def test_unknown_timeout_no_retry_and_no_secret_leak(self):
        task=self.begin()
        def fail(*args):self.sent.append(args);raise TimeoutError(self.key)
        self.service.request=fail
        unknown=self.service.execute(1,task['id']);self.assertEqual(unknown['status'],'unknown')
        for action in (lambda:self.service.execute(1,task['id']),lambda:self.service.poll(1,task['id']),self.begin):
            with self.assertRaises(ValueError):action()
        self.assertEqual(len(self.sent),1);self.assertNotIn(self.key,json.dumps(self.state()))

    def test_multiple_output_anomaly_keeps_unknown_and_conservative_reservation(self):
        self.response['data']*=2;task=self.submit()
        self.assertEqual(task['status'],'unknown');self.assertEqual(task['response_anomaly']['output_count'],2);self.assertEqual(task['estimate'],.24)
        self.assertEqual(self.downloads,[]);self.assertNotIn('candidate_local',task)

    def test_cache_failure_only_downloads_original_result(self):
        self.download_failure=True;task=self.submit();self.assertEqual(task['status'],'completed');self.assertTrue(task['download_error'])
        self.assertNotIn('candidate_local',task);self.download_failure=False
        restored=edit.SeedreamEditService(self.root,self.database,self.service.request,self.service.downloader,self.service.authorize,self.service.paused)
        result=restored.poll(1,task['id']);self.assertTrue(result['candidate_local']);self.assertEqual(len(self.sent),1);self.assertEqual(len(self.downloads),2)
        self.assertIsNone(result['provider_task_id'])

    def test_adoption_invalidates_approval_preserves_old_and_final(self):
        task=self.submit();result=self.service.adopt(1,self.state()['revision'],task['id'],task['candidate_sha256'],'human selected whole-image candidate')
        state=self.state();self.assertEqual(result['status'],'adopted');self.assertFalse(workflow_state.valid_approval(state,state['shots'][0]))
        self.assertEqual(state['final_video']['local_url'],'untouched.mp4');self.assertEqual(state['tasks'],[])
        self.assertEqual((self.root/'assets'/'1'/'original.png').read_bytes(),self.source)

    def test_source_hash_and_content_approval_binding(self):
        task=self.submit()
        (self.root/'assets'/'1'/'original.png').write_bytes(self.generated)
        with self.assertRaises(ValueError):self.service.adopt(1,self.state()['revision'],task['id'],task['candidate_sha256'],'human')
        self.assertTrue(self.state()['shots'][0]['approved'])

    def test_cross_project_path_symlink_stale_revision_and_prompt_tags(self):
        for path in ('/media/2/original.png','/media/1/../original.png','https://example.com/original.png'):
            with self.assertRaises(ValueError):self.begin(source_url=path)
        (self.root/'assets'/'1'/'escape.png').symlink_to(self.root/'assets'/'1'/'original.png')
        with self.assertRaises(ValueError):edit.read_image(self.root,1,'/media/1/escape.png')
        with self.assertRaises(ValueError):self.begin(description='<bbox>0 0 999 999</bbox>')
        task=self.begin()
        with self.assertRaises(ValueError):self.service.get(2,task['id'])
        with self.assertRaises(ValueError):self.begin(revision=0)

    def test_real_budget_gate_model_range_pause_and_reserved_amount(self):
        scope={'1':{'id':'scope','database':str(self.database.resolve()),'models':[edit.MODEL],'budget_mode':'separate_v1','budget_grants':{'image':{'id':'grant','limit':.12}},'paused':False}}
        self.service=edit.SeedreamEditService(self.root,self.database,self.service.request,self.service.downloader)
        with patch.object(generation_scope,'read',return_value=scope):
            scope['1']['models']=[]
            with self.assertRaises(ValueError):self.begin()
            scope['1']['models']=[edit.MODEL];task=self.submit();self.assertEqual(task['estimate'],.12)
            ledger=generation_scope.category_ledger(self.state(),'image',.12);self.assertEqual(ledger['committed_cny'],.12);self.assertEqual(ledger['remaining_cny'],0)
            self.assertEqual(self.state()['tasks'],[])

    def test_2k_long_edge_png_is_preserved_without_resampling(self):
        data=comfy_assets.encode(2816,1584,bytes((1,2,3,255))*(2816*1584))
        self.assertEqual(edit.png_info(data)['width'],2816)
        self.generated=data;task=self.submit();self.assertEqual(task['output_info']['height'],1584)
        with self.assertRaises(ValueError):edit.png_info(data[:-1])

    def test_late_download_cannot_overwrite_adopted_candidate(self):
        task=self.begin();self.download_failure=True
        done=self.service.execute(1,task['id']);self.assertTrue(done['download_error']);self.download_failure=False
        original=self.service.downloader;entered=[]
        def overlap(url):
            if not entered:
                entered.append(True)
                inner=self.service.poll(1,task['id'])
                self.service.adopt(1,self.state()['revision'],task['id'],inner['candidate_sha256'],'human inner adoption')
                return self.source # Different late bytes must not overwrite adopted output.
            return original(url)
        self.service.downloader=overlap
        result=self.service.poll(1,task['id']);self.assertEqual(result['status'],'adopted')
        data,_=edit.read_image(self.root,1,result['candidate_local']);self.assertEqual(data,self.generated)
        self.assertEqual(len(self.sent),1)

    def test_pause_or_budget_revocation_after_intent_prevents_dispatch(self):
        task=self.begin();self.paused=True
        with self.assertRaises(ValueError):self.service.execute(1,task['id'])
        self.paused=False;self.budget=Decimal('.11')
        with self.assertRaisesRegex(ValueError,'预算'):self.service.execute(1,task['id'])
        self.assertEqual(self.sent,[]);self.assertEqual(self.service.get(1,task['id'])['status'],'submitting')

    def test_output_url_and_credentials_absence_are_fail_closed(self):
        for url in ('http://images.byteimg.com/a.png','https://byteimg.com.evil.test/a.png','https://user:password@images.byteimg.com/a.png','https://images.byteimg.com:8443/a.png'):
            with self.assertRaises(ValueError):edit.output_url(url)
        with patch.object(secret_store,'get_key',return_value=''):
            self.assertFalse(self.service.preflight()['ready'])
            with self.assertRaises(ValueError):self.begin()
        self.assertEqual(self.sent,[])

if __name__=='__main__':unittest.main()
