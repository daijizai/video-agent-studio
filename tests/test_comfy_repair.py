"""Isolated HTTP/SQLite evidence only. Never connects to a real ComfyUI."""
import copy
import json
import re
import sqlite3
import sys
import struct
import zlib
import tempfile
import threading
import unittest
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comfy_assets as assets
import comfy_templates as templates
from comfy_executor import LocalTransport, RepairService
import generation_scope
import workflow_state

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.database = self.root/'studio.db'; self.paused = False; self.fee_limit = 1
        self.calls = []; self.fail_download = False; self.unknown_submit = False; self.lock_free = []
        self.output_ref = None; self.finished = False
        width = height = 64
        self.source = assets.encode(width, height, bytes((20, 30, 40, 255))*width*height)
        mask = bytearray(bytes((0, 0, 0, 255))*width*height)
        mask[:32*4] = bytes((255, 255, 255, 255))*32
        self.mask = assets.encode(width, height, bytes(mask))
        self.generated = assets.encode(width, height, bytes((200, 100, 50, 255))*width*height)
        folder = self.root/'assets'/'1'; folder.mkdir(parents=True)
        (folder/'original.png').write_bytes(self.source); (folder/'mask.png').write_bytes(self.mask)
        shot = {'id': 'shot1', 'name': '修复测试', 'prompt': 'test', 'frame': 'close', 'duration': 5, 'estimate': 0,
                'storyboard_local': '/media/1/original.png', 'storyboard_sha256': assets.sha(self.source),
                'storyboard_task_id': 'old', 'approved_image_task_id': 'old', 'approved': True}
        state = {'project_id': 1, 'revision': 0, 'script': 'test', 'characters': [], 'continuity': '',
                 'shots': [shot], 'tasks': [], 'image_tasks': [], 'budget': 1, 'final_video': {'local_url': 'preserved.mp4'}}
        shot['approval_snapshot'] = workflow_state.record_approval(state, shot, 'test human approval', 'test')
        with sqlite3.connect(self.database) as con:
            con.execute('CREATE TABLE state (id INTEGER PRIMARY KEY, body TEXT)')
            con.execute('CREATE TABLE revisions (id INTEGER PRIMARY KEY, body TEXT, project_id INTEGER)')
            con.execute('INSERT INTO state VALUES (1,?)', (json.dumps(state),))
            other = copy.deepcopy(state); other['project_id'] = 2
            con.execute('INSERT INTO state VALUES (2,?)', (json.dumps(other),))
        comfy = self.root/'engine'; (comfy/'models'/'checkpoints').mkdir(parents=True)
        checkpoint = comfy/'models'/'checkpoints'/'reviewed.safetensors'; checkpoint.write_bytes(b'SIMULATED MODEL - NOT WEIGHTS')
        (comfy/'nodes.py').write_bytes(b'SIMULATED CORE')
        self.profile = {'architecture': 'sd15', 'checkpoint_path': str(checkpoint), 'checkpoint_sha256': assets.sha(checkpoint.read_bytes()), 'comfy_root': str(comfy), 'core_nodes_sha256': assets.sha((comfy/'nodes.py').read_bytes()), 'comfy_version': 'test-only'}
        self.node_info = {node['class_type']: {'input': {'required': {key: ['STRING'] for key in node['inputs']}}, 'python_module': 'nodes'} for node in templates.manifest()['graph_spec'].values()}
        self.node_info['CheckpointLoaderSimple']['input']['required']['ckpt_name'] = [['reviewed.safetensors']]
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, value, code=200, raw=False):
                data = value if raw else json.dumps(value).encode()
                self.send_response(code); self.end_headers(); self.wfile.write(data)
            def check_lock(self):
                try:
                    with sqlite3.connect(owner.database, timeout=.1) as con: con.execute('BEGIN IMMEDIATE')
                    owner.lock_free.append(True)
                except sqlite3.OperationalError: owner.lock_free.append(False)
            def do_GET(self):
                owner.calls.append(('GET', self.path)); self.check_lock()
                if self.path == '/object_info': return self.reply(owner.node_info)
                if self.path == '/system_stats': return self.reply({'system': {'comfyui_version': 'test-only'}})
                if self.path == '/history/prompt-test':
                    return self.reply({'prompt-test': {'status': {'completed': True}, 'outputs': {'9': {'images': [owner.output_ref]}}}} if owner.finished else {})
                if self.path == '/queue': return self.reply({'queue_running': [[0, 'prompt-test', owner.last_payload['prompt'], owner.last_payload['extra_data']]] if hasattr(owner, 'last_payload') else [], 'queue_pending': []})
                if self.path.startswith('/view?'):
                    if owner.fail_download: return self.reply({'error': 'temporary'}, 503)
                    return self.reply(owner.generated, raw=True)
                return self.reply({}, 404)
            def do_POST(self):
                owner.calls.append(('POST', self.path)); self.check_lock()
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if self.path == '/upload/image':
                    name = re.search(rb'filename="([^"]+)"', body)[1].decode()
                    return self.reply({'name': name, 'subfolder': '', 'type': 'input'})
                if self.path == '/prompt':
                    payload = json.loads(body); owner.last_payload = payload; task_id = payload['client_id']
                    owner.output_ref = {'filename': 'repair_'+task_id+'_00001_.png', 'subfolder': '', 'type': 'output'}
                    if owner.unknown_submit: return self.reply({'unexpected': True})
                    return self.reply({'prompt_id': 'prompt-test'})
                return self.reply({}, 404)
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.transport = LocalTransport('http://127.0.0.1:'+str(self.http.server_port))
        self.authorizations = []
        def authorize(state, database, kind, estimate, model, shot_id=None):
            self.authorizations.append((kind, estimate, model))
            if kind != 'image' or model != templates.MODEL_SCOPE or self.fee_limit <= len(state['image_tasks']): raise ValueError('图片授权额度不足')
            return 'explicit-test-image-authorization'
        self.service = RepairService(self.root, self.database, self.transport, self.profile, authorize, lambda *args: self.paused)

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.temp.cleanup()

    def state(self):
        with self.service.transaction() as con: return self.service.state(con, 1)

    def begin(self, **changes):
        args = {'project_id': 1, 'revision': self.state()['revision'], 'shot_id': 'shot1', 'source_url': '/media/1/original.png', 'mask_url': '/media/1/mask.png', 'values': {'description': '修正白色区域道具', 'seed': 42}, 'request_id': uuid.uuid4().hex}
        args.update(changes); return self.service.begin(**args)

    def submit(self):
        task = self.begin(); return self.service.execute(1, task['id'])

    def test_http_full_candidate_adopt_and_invalidate(self):
        self.assertTrue(self.service.preflight()['ready'])
        task = self.submit(); self.assertEqual(task['status'], 'queued')
        # A new service instance recovers by the persisted original prompt_id.
        restored = RepairService(self.root, self.database, self.transport, self.profile, self.service.authorize, self.service.paused)
        self.assertEqual(restored.poll(1, task['id'])['status'], 'running')
        self.finished = True; candidate = restored.poll(1, task['id'])
        self.assertEqual(candidate['status'], 'completed'); self.assertEqual(candidate['review_status'], 'pending')
        self.assertEqual(self.state()['shots'][0]['storyboard_local'], '/media/1/original.png')
        pixels = assets.decode(assets.asset(self.root, 1, candidate['candidate_local']))[2]
        original = assets.decode(self.source)[2]; generated = assets.decode(self.generated)[2]
        self.assertEqual(pixels[:128], generated[:128]); self.assertEqual(pixels[128:], original[128:])
        adopted = restored.adopt(1, self.state()['revision'], task['id'], candidate['candidate_sha256'], 'human selected candidate')
        self.assertEqual(adopted['status'], 'adopted'); state = self.state()
        self.assertFalse(workflow_state.valid_approval(state, state['shots'][0]))
        self.assertEqual(state['final_video']['local_url'], 'preserved.mp4'); self.assertEqual(state['tasks'], [])
        ledger = generation_scope.category_ledger(state, 'image', 1)
        self.assertEqual(ledger['actual_known_cny'], 0)
        self.assertEqual((self.root/'assets'/'1'/'original.png').read_bytes(), self.source)
        self.assertEqual(self.calls.count(('POST', '/prompt')), 1); self.assertTrue(all(self.lock_free))
        self.assertTrue(all(row == ('image', 0, templates.MODEL_SCOPE) for row in self.authorizations))

    def test_paused_and_approval_and_budget_refuse_before_prompt(self):
        self.paused = True
        with self.assertRaisesRegex(ValueError, '暂停'): self.begin()
        self.paused = False; self.fee_limit = 0
        with self.assertRaisesRegex(ValueError, '授权'): self.begin()
        self.fee_limit = 1
        with self.service.transaction() as con:
            state = self.service.state(con, 1); state['shots'][0]['approved'] = False; self.service.save(con, state)
        with self.assertRaisesRegex(ValueError, '批准'): self.begin()
        self.assertNotIn(('POST', '/prompt'), self.calls); self.assertEqual(self.state()['image_tasks'], [])

    def test_pause_after_intent_prevents_dispatch(self):
        task = self.begin(); self.paused = True
        with self.assertRaisesRegex(ValueError, '暂停'): self.service.execute(1, task['id'])
        self.assertNotIn(('POST', '/prompt'), self.calls)

    def test_unknown_never_resubmits(self):
        self.unknown_submit = True; task = self.submit()
        self.assertEqual(task['status'], 'unknown')
        with self.assertRaises(ValueError): self.service.execute(1, task['id'])
        with self.assertRaises(ValueError): self.begin()
        with self.assertRaises(ValueError): self.service.poll(1, task['id'])
        self.assertEqual(self.calls.count(('POST', '/prompt')), 1)

    def test_download_failure_only_rearchives(self):
        task = self.submit(); self.finished = True; self.fail_download = True
        self.assertEqual(self.service.poll(1, task['id'])['status'], 'archive_pending')
        self.fail_download = False
        self.assertEqual(self.service.poll(1, task['id'])['status'], 'completed')
        self.assertEqual(self.calls.count(('POST', '/prompt')), 1)
        self.assertEqual(self.calls.count(('GET', '/history/prompt-test')), 1)

    def test_project_path_symlink_and_changed_source(self):
        for url in ('/media/2/mask.png', '/media/1/../mask.png', 'http://localhost/private.png'):
            with self.assertRaises(ValueError): self.begin(mask_url=url)
        (self.root/'assets'/'1'/'escape.png').symlink_to(self.root/'assets'/'1'/'mask.png')
        with self.assertRaises(ValueError): self.begin(mask_url='/media/1/escape.png')
        (self.root/'assets'/'1'/'original.png').write_bytes(self.generated)
        with self.assertRaisesRegex(ValueError, '原图文件'): self.begin()
        self.assertEqual(self.state()['image_tasks'], [])

    def test_cross_project_task_and_stale_adoption(self):
        task = self.submit()
        with self.assertRaisesRegex(ValueError, '不属于'): self.service.poll(2, task['id'])
        self.finished = True; candidate = self.service.poll(1, task['id'])
        with self.assertRaisesRegex(ValueError, '版本'): self.service.adopt(1, 0, task['id'], candidate['candidate_sha256'], 'human')

    def test_parameters_masks_and_dependencies_fail_closed(self):
        for values in ({'description': 'x', 'nodes': {}}, {'description': 'x', 'strength': float('nan')}, {'description': 'x', 'seed': True}):
            with self.assertRaises(ValueError): self.begin(values=values)
        with self.assertRaises(ValueError): assets.inputs(self.source, self.source)
        self.profile['checkpoint_sha256'] = '0'*64
        other = RepairService(self.root, self.database, self.transport, self.profile)
        self.assertFalse(other.preflight()['ready'])
        self.node_info['KSampler']['python_module'] = 'custom_nodes.evil'
        self.assertFalse(self.service.preflight()['ready'])
        self.assertNotIn(('POST', '/prompt'), self.calls)

    def test_idempotent_request_and_double_dispatch(self):
        request_id = uuid.uuid4().hex; task = self.begin(request_id=request_id)
        with self.assertRaises(ValueError): self.begin(request_id=request_id)
        self.service.execute(1, task['id'])
        with self.assertRaises(ValueError): self.service.execute(1, task['id'])
        self.assertEqual(self.calls.count(('POST', '/prompt')), 1)

    def test_explicit_unknown_reconciliation_requires_executor_proof(self):
        self.unknown_submit = True; task = self.submit()
        self.assertEqual(task['status'], 'unknown')
        original = self.last_payload['extra_data']['studio_task_id']
        self.last_payload['extra_data']['studio_task_id'] = 'wrong'
        with self.assertRaises(ValueError): self.service.reconcile(1, task['id'], 'prompt-test')
        self.last_payload['extra_data']['studio_task_id'] = original
        recovered = self.service.reconcile(1, task['id'], 'prompt-test')
        self.assertEqual(recovered['provider_task_id'], 'prompt-test')
        self.assertEqual(self.calls.count(('POST', '/prompt')), 1)

    def test_real_authorizer_with_temporary_scope(self):
        scope = {'1': {'id': 'finite-test', 'database': str(self.database.resolve()), 'models': [templates.MODEL_SCOPE],
                       'local_repair_grant': {'id': 'local-test', 'limit': 1, 'baseline_task_ids': []}, 'budget_mode': 'separate_v1', 'budget_grants': {'image': {'id': 'image-grant', 'limit': 1}}, 'paused': False}}
        self.service = RepairService(self.root, self.database, self.transport, self.profile)
        with patch.object(generation_scope, 'read', return_value=scope):
            task = self.submit(); self.assertEqual(task['status'], 'queued')
            self.assertEqual(task['authorization_id'], 'image-grant')
            self.assertEqual(task['authorization_scope_snapshot'], scope['1'])
            scope['1']['paused'] = True
            with self.assertRaisesRegex(ValueError, '暂停'): self.begin()
        self.assertEqual(self.calls.count(('POST', '/prompt')), 1)

    def test_tampered_graph_and_revoked_authorization_block_dispatch(self):
        task = self.begin()
        with self.service.transaction() as con:
            state = self.service.state(con, 1)
            self.service.task(state, task['id'])['request']['1']['class_type'] = 'Unreviewed'
            self.service.save(con, state)
        self.assertEqual(self.service.execute(1, task['id'])['status'], 'failed')
        self.assertNotIn(('POST', '/prompt'), self.calls)

    def test_mask_import_and_candidate_tampering(self):
        self.paused = True
        imported = self.service.import_mask(1, self.state()['revision'], 'shot1', self.mask)
        self.assertEqual(assets.asset(self.root, 1, imported['local_url']), self.mask)
        self.assertFalse(imported['generation_called']); self.paused = False
        task = self.submit(); self.finished = True; candidate = self.service.poll(1, task['id'])
        (self.root/'assets'/'1'/Path(candidate['candidate_local']).name).write_bytes(self.generated)
        with self.assertRaisesRegex(ValueError, '候选文件'): self.service.adopt(1, self.state()['revision'], task['id'], candidate['candidate_sha256'], 'human')
        self.assertTrue(self.state()['shots'][0]['approved'])

    def test_png_filters_and_corruption(self):
        width = height = 64
        pixels = bytes((i*17+i//31)%256 for i in range(width*height*4))
        filtered = bytearray(); stride = width*4
        for y in range(height):
            row = pixels[y*stride:(y+1)*stride]; previous = pixels[(y-1)*stride:y*stride] if y else bytes(stride); mode = y%5
            filtered.append(mode)
            for x, value in enumerate(row):
                a = row[x-4] if x>=4 else 0; b = previous[x]; c = previous[x-4] if x>=4 else 0
                if mode == 0: pred = 0
                elif mode == 1: pred = a
                elif mode == 2: pred = b
                elif mode == 3: pred = (a+b)//2
                else:
                    p = a+b-c; distance = (abs(p-a),abs(p-b),abs(p-c)); pred=(a,b,c)[distance.index(min(distance))]
                filtered.append((value-pred)&255)
        def chunk(kind, value): return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
        png = assets.SIGNATURE+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(filtered)))+chunk(b'IEND',b'')
        self.assertEqual(assets.decode(png)[2], pixels)
        for bad in (png[:-1], png+b'extra', png[:40]+b'bad'+png[43:]):
            with self.assertRaises(ValueError): assets.decode(bad)

    def test_loopback_only_transport(self):
        for url in ('https://127.0.0.1:8188', 'http://example.com', 'http://user@localhost', 'http://localhost/?x=1'):
            with self.assertRaises(ValueError): LocalTransport(url)

if __name__ == '__main__': unittest.main()
