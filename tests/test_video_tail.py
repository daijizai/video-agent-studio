import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import video_tail
import material_video
from unittest.mock import Mock


class VideoTailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        folder = self.root / 'assets' / '4'
        folder.mkdir(parents=True)
        self.source = folder / 'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=24:duration=7',
                        '-f','lavfi','-i','sine=frequency=440:duration=7','-c:v','libx264','-c:a','aac',
                        '-shortest','-y',str(self.source)],check=True)
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.task = {'id':'source','status':'completed','review_status':'accepted',
                     'local_video':'/media/4/source.mp4','accepted_video_sha256':self.sha}
        self.state = {'project_id':4,'tasks':[self.task]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_cuts_tail_without_changing_source_and_keeps_audio(self):
        clip = video_tail.create(self.state,self.root,'source',3)
        self.assertAlmostEqual(clip['start_seconds'],4,delta=.15)
        self.assertAlmostEqual(clip['duration_seconds'],3,delta=.15)
        self.assertTrue(clip['media_info']['has_audio'])
        self.assertFalse(clip['provider_usable'])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.sha)
        self.assertEqual(hashlib.sha256((self.root/'assets'/'4'/clip['relative_path']).read_bytes()).hexdigest(),clip['sha256'])

    def test_refuses_unreviewed_or_changed_source_and_bad_duration(self):
        self.task['review_status'] = None
        with self.assertRaisesRegex(ValueError,'已验收'): video_tail.create(self.state,self.root,'source',3)
        self.task['review_status'] = 'accepted'
        with self.assertRaisesRegex(ValueError,'时长'): video_tail.create(self.state,self.root,'source',1)
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'不一致'): video_tail.create(self.state,self.root,'source',3)

    def test_cross_project_path_is_rejected(self):
        self.task['local_video']='/media/5/source.mp4'
        with self.assertRaisesRegex(ValueError,'本项目'): video_tail.create(self.state,self.root,'source',3)

    def test_segment_prepare_records_tail_and_never_submits_model(self):
        segment={'id':'next','material_video_parent_task_id':'source','draft_revision':1,
                 'material_video_approval':{'fingerprint':'old'}}
        self.state['video_segments']=[segment]
        server=Mock();server.ROOT=self.root
        result=material_video.operate(server,self.state,'prepare-tail',{'segment_id':'next','seconds':3})
        self.assertEqual(result['tail']['source_sha256'],self.sha)
        self.assertEqual(segment['material_video_reference_mode'],'tail')
        self.assertNotIn('material_video_approval',segment)
        server.save.assert_called_once()
        server.material_service.assert_not_called()

    def test_failed_save_cleans_only_new_tail(self):
        segment={'id':'next','material_video_parent_task_id':'source'}
        self.state['video_segments']=[segment]
        server=Mock();server.ROOT=self.root;server.save.side_effect=ValueError('stale revision')
        with self.assertRaisesRegex(ValueError,'stale revision'):
            material_video.operate(server,self.state,'prepare-tail',{'segment_id':'next','seconds':3})
        self.assertFalse(list((self.root/'assets'/'4'/'reference-tails').glob('*.mp4')))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.sha)


if __name__ == '__main__':
    unittest.main()
