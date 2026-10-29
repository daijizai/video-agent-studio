"""Default dispatch must reach Seedream while explicit Qwen and history remain intact."""
import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import image_provider, server

class ImageDefaults(unittest.TestCase):
    def test_default_prepares_seedream_without_network(self):
        with patch('providers.transport',side_effect=AssertionError('network forbidden')):
            prepared=image_provider.for_model().prepare({'prompt':'single neutral robot design'})
        self.assertEqual(prepared['provider'],'seedream')
        self.assertEqual(prepared['payload']['model'],'doubao-seedream-5-0-flash-260915')
        self.assertEqual(prepared['estimated_cny'],.12)
        self.assertFalse(prepared['network_called'])

    def test_explicit_qwen_keeps_its_own_contract(self):
        prepared=image_provider.for_model('qwen-image-3.0-pro').prepare({'prompt':'single neutral robot design'})
        self.assertEqual(prepared['provider'],'qwen-image')
        self.assertEqual(prepared['payload']['model'],'qwen-image-3.0-pro')
        self.assertEqual(prepared['estimated_cny'],.25)

    def test_new_project_default_does_not_rewrite_task_evidence(self):
        previous=server.DATA
        with tempfile.TemporaryDirectory() as tmp:
            try:
                server.DATA=Path(tmp);server.init()
                state=server.create_project('Default image model')
                self.assertEqual(state['settings']['image_model'],image_provider.DEFAULT_IMAGE_MODEL)
                old={'id':'historical-qwen','shot_id':'old-shot','status':'completed','estimate':.25,
                     'provider':'qwen-image','request':{'model':'qwen-image-3.0-pro'}}
                state['image_tasks']=[copy.deepcopy(old)];server.save(state)
                self.assertEqual(server.read()['image_tasks'][0],old)
            finally:server.DATA=previous
