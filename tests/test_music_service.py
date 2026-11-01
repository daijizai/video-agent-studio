import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import music_service as music


class MusicServiceTests(unittest.TestCase):
    def test_health_requires_upstream_identity(self):
        for body, expected in [({'app':'go-music-dl','status':'ok'}, True),
                               ({'app':'other','status':'ok'}, False)]:
            response = io.BytesIO(json.dumps(body).encode())
            with patch.object(music.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = response
                self.assertEqual(music.status()['ready'], expected)

    def test_running_service_is_not_spawned_twice(self):
        with patch.object(music, 'status', return_value={'ready':True}), patch.object(music.subprocess, 'Popen') as spawn:
            self.assertTrue(music.start()['ready'])
            spawn.assert_not_called()

    def test_child_is_loopback_mode_and_does_not_inherit_api_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'music-dl').touch()
            with patch.object(music, 'RUNTIME', root), patch.object(music, 'status', side_effect=[{'ready':False},{'ready':True}]), patch.dict(music.os.environ, {'MINIMAX_API_KEY':'private-test-key','STUDIO_SECRET_FILE':'private-path'}), patch.object(music.subprocess, 'Popen') as spawn:
                self.assertTrue(music.start()['ready'])
                args, kwargs = spawn.call_args
                self.assertIn('--desktop', args[0])
                self.assertEqual(args[0][-1], '8767')
                self.assertNotIn('MINIMAX_API_KEY', kwargs['env'])
                self.assertNotIn('STUDIO_SECRET_FILE', kwargs['env'])
                self.assertEqual(kwargs['cwd'], root)

    def test_missing_installation_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(music, 'RUNTIME', Path(directory)), patch.object(music, 'status', return_value={'ready':False}):
            with self.assertRaisesRegex(ValueError, 'docs/MUSIC.md'):
                music.start()


if __name__ == '__main__':
    unittest.main()
