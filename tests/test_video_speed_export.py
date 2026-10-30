import hashlib
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import media_files
import video_speed_export as speed


class VideoSpeedExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        folder=self.root/'assets'/'4';folder.mkdir(parents=True)
        self.source=folder/'full.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=24:duration=4',
                        '-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-c:a','aac',
                        '-shortest','-y',str(self.source)],check=True)
        self.sha=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.state={'project_id':4,'final_video':{'local_url':'/media/4/full.mp4','sha256':self.sha}}

    def tearDown(self):self.tmp.cleanup()

    def test_real_export_speeds_video_and_audio_without_changing_pitch_or_source(self):
        job=speed.start(self.state,self.root,1.5,self.sha)
        deadline=time.monotonic()+30
        while job['status']=='running' and time.monotonic()<deadline:
            time.sleep(.05);job=speed.status(4,job['id'])
        self.assertEqual(job['status'],'completed',job)
        out=self.root/'assets'/'4'/job['url'].rsplit('/',1)[-1]
        info=media_files.probe_video(out)
        self.assertAlmostEqual(info['duration'],4/1.5,delta=.15)
        self.assertTrue(info['has_audio']);self.assertEqual(info['video']['width'],320)
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(out),'-map','0:a:0','-ac','1','-ar','8000','-f','s16le','-'])
        import array
        samples=array.array('h');samples.frombytes(raw)
        middle=samples[4000:12000]
        frequency=sum(a<0<=b for a,b in zip(middle,middle[1:]))
        self.assertGreater(frequency,425);self.assertLess(frequency,455)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.sha)

    def test_bad_rates_changed_source_and_project_isolation(self):
        for rate in (1,2.1,1.15,'1.1',float('nan')):
            with self.assertRaises(ValueError):speed.start(self.state,self.root,rate,self.sha)
        with self.assertRaisesRegex(ValueError,'更新'):speed.start(self.state,self.root,1.1,'other')
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'变化'):speed.start(self.state,self.root,1.1,self.sha)
        with self.assertRaises(ValueError):speed.status(5,'not-a-job')

if __name__=='__main__':unittest.main()
