"""Temporary database only; no generation or production data access."""
import copy
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import server
import storyboard_contract as contract
import workflow_state


class StoryboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_data = server.DATA
        server.DATA = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'STUDIO_SECRET_FILE': str(server.DATA/'private'/'credentials.json')})
        self.env.start();server.init()
        s = server.read()
        for i, shot in enumerate(s['shots']):
            shot.update(storyboard_task_id=f'img{i}',storyboard_local=f'/media/1/img{i}.png',
                        storyboard_sha256=str(i)*64,approved=True,approved_image_task_id=f'img{i}')
            shot['approval_snapshot'] = workflow_state.record_approval(s,shot,'test human','time')
        self.initial = copy.deepcopy(s);server.save(s)
        self.http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=self.http.serve_forever,daemon=True).start()

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.env.stop()
        server.DATA = self.original_data;self.tmp.cleanup()

    def post(self, payload):
        request = urllib.request.Request(f'http://127.0.0.1:{self.http.server_port}/api/save',
            data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def test_optional_edit_persists_revokes_only_changed_shot_and_snapshots(self):
        s=server.read();shots=copy.deepcopy(s['shots'])
        shots[0]['creative_details']={'camera':{'movement':'locked'},'action_chain':{'start':'静止','end':'静止','steps':[]}}
        with patch.object(server.providers.Provider,'submit') as video,patch.object(server.image_provider.ImageProvider,'submit') as image,patch.object(server,'remote') as comfy:
            code,result=self.post({'shots':shots,'project_id':1,'revision':s['revision']})
            self.assertEqual(code,200);self.assertFalse(result['shots'][0]['approved'])
            self.assertEqual(result['workflow']['approved_count'],3)
            self.assertTrue(all(x['approved'] for x in result['shots'][1:]))
            snapshot=server.content_snapshot(result,result['shots'][0])
            self.assertEqual(snapshot['shot']['creative_details'],shots[0]['creative_details'])
            snapshot['shot']['creative_details']['action_chain']['start']='changed copy'
            self.assertEqual(server.read()['shots'][0]['creative_details']['action_chain']['start'],'静止')
            video.assert_not_called();image.assert_not_called();comfy.assert_not_called()
        server.init();self.assertEqual(server.read()['workflow']['approved_count'],3)

    def test_legacy_acceptance_survives_read_init_and_unchanged_save(self):
        s=server.read()
        for shot in s['shots']:
            shot['approval_snapshot'].pop('storyboard_binding_version')
            shot['approval_snapshot'].pop('storyboard_binding_hash')
        task={'id':'old-film','kind':'sequence','status':'completed','local_video':'/media/1/old.mp4',
              'approval_snapshot':[copy.deepcopy(x['approval_snapshot']) for x in s['shots']]}
        s['tasks']=[task];s['final_video']={'task_id':'old-film','review_task_id':'old-film','review_status':'accepted_first_version'}
        server.save(s);server.init();before=server.read()
        self.assertEqual(before['workflow']['code'],'COMPLETE')
        code,result=self.post({'shots':before['shots']})
        self.assertEqual(code,200);self.assertEqual(result['workflow']['code'],'COMPLETE')
        self.assertNotIn('storyboard_binding_version',result['shots'][0]['approval_snapshot'])
        self.assertEqual(result['final_video'],s['final_video'])

    def test_reference_change_and_new_approval_cannot_make_old_video_current(self):
        s=server.read();old=copy.deepcopy(s['shots'][0]['approval_snapshot'])
        s['shots'][0]['reference_images']=['https://example.com/new.png']
        self.assertFalse(workflow_state.valid_approval(s,s['shots'][0]))
        s['shots'][0]['approval_snapshot']=workflow_state.record_approval(s,s['shots'][0],'test','time')
        self.assertTrue(workflow_state.valid_approval(s,s['shots'][0]))
        task={'shot_id':s['shots'][0]['id'],'content_snapshot':{'shot':{'approval_snapshot':old}}}
        self.assertFalse(workflow_state.task_matches(s,task))
        sequence={'approval_snapshot':[old]+[x['approval_snapshot'] for x in s['shots'][1:]]}
        self.assertFalse(workflow_state.task_matches(s,sequence))

    def test_malformed_optional_data_rejected_without_persisting(self):
        s=server.read();shots=copy.deepcopy(s['shots']);shots[0]['creative_details']={'prop_states':[{'asset_id':'p','start':{'count':-1}}]}
        code,result=self.post({'shots':shots})
        self.assertEqual(code,400);self.assertIn('非负整数',result['error'])
        self.assertEqual(server.read()['revision'],s['revision'])
        self.assertEqual(server.read()['shots'],s['shots'])

    def test_feedback_preserves_approval_but_story_intent_expires_only_changed_shot(self):
        s=server.read();shots=copy.deepcopy(s['shots']);shots[0]['review']='钥匙位置需要核对'
        code,result=self.post({'shots':shots})
        self.assertEqual(code,200);self.assertEqual(result['workflow']['approved_count'],4)
        self.assertEqual(result['shots'][0]['approval_snapshot'],s['shots'][0]['approval_snapshot'])
        result['shots'][0]['story_intent']='她发现日期异常，感到不安。'
        code,result=self.post({'shots':result['shots']})
        self.assertEqual(code,200);self.assertEqual(result['workflow']['approved_count'],3)
        self.assertFalse(result['shots'][0]['approved'])
        self.assertEqual(result['shots'][0]['prompt'],s['shots'][0]['prompt'])


if __name__=='__main__':unittest.main()
