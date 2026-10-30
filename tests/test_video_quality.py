import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import video_quality as quality


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        folder=self.root/'assets'/'4';folder.mkdir(parents=True)
        self.file=folder/'baseline.mp4';self.file.write_bytes(b'baseline')
        sha=hashlib.sha256(b'baseline').hexdigest()
        self.base={'id':'first','provider':'seedance25','segment_id':'first-segment','status':'completed','review_status':'accepted',
                   'local_video':'/media/4/baseline.mp4','accepted_video_sha256':sha,
                   'video_url':'https://ark-acg.tos-cn-beijing.volces.com/first.mp4','media_info':{'duration':12}}
        self.state={'project_id':4,'tasks':[self.base],'project_brief':{'video_quality':{'enabled':True,'baseline_task_id':'first','baseline_sha256':sha,'prompt':'清晰'}}}
        self.shot={'id':'second'}
    def tearDown(self):self.tmp.cleanup()

    def test_baseline_sent_or_reused_without_duplicate(self):
        result,warnings=quality.select_reference(self.state,self.shot,self.root,{'task_id':'parent','duration':15})
        self.assertEqual(result['status'],'sent');self.assertEqual(warnings,[])
        result,warnings=quality.select_reference(self.state,self.shot,self.root,{'task_id':'first','duration':12})
        self.assertEqual(result['status'],'shared_with_parent');self.assertEqual(warnings,[])

    def test_refuses_extra_input_when_total_exceeds_limit_and_reports_it(self):
        result,warnings=quality.select_reference(self.state,self.shot,self.root,{'task_id':'parent','duration':19})
        self.assertEqual(result['status'],'not_sent');self.assertNotIn('url',result)
        self.assertIn('30秒',warnings[0])

    def test_changed_baseline_is_not_automatically_sent(self):
        self.file.write_bytes(b'changed')
        result,warnings=quality.select_reference(self.state,self.shot,self.root,None)
        self.assertEqual(result['status'],'not_sent');self.assertTrue(warnings)

    def test_expired_signed_baseline_is_not_sent(self):
        self.base['video_url']+='?X-Tos-Date=20200101T000000Z&X-Tos-Expires=60'
        result,warnings=quality.select_reference(self.state,self.shot,self.root,None)
        self.assertEqual(result['status'],'not_sent');self.assertIn('过期',warnings[0])

    def test_advisory_blur_comparison_records_hash_and_warns_about_context(self):
        candidate=self.file.parent/'candidate.mp4';candidate.write_bytes(b'candidate')
        with patch.object(quality,'_blur_sample',side_effect=[{'median':5,'samples':4},{'median':6,'samples':4}]):
            review=quality.inspect(self.state,self.root,{'local_video':'/media/4/candidate.mp4'})
        self.assertTrue(review['possible_softness']);self.assertEqual(review['ratio'],1.2)
        self.assertIn('景别',review['note']);self.assertEqual(review['candidate_sha256'],hashlib.sha256(b'candidate').hexdigest())

    def test_blur_sampling_actually_runs_on_video(self):
        video=self.file.parent/'test.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=24:duration=4',
                        '-c:v','libx264','-y',str(video)],check=True)
        result=quality._blur_sample(video)
        self.assertGreater(result['samples'],0);self.assertGreater(result['median'],0)

if __name__=='__main__':unittest.main()
