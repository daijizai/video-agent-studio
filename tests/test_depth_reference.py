import hashlib,json,tempfile,time,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import depth_reference
class DepthReferenceTests(unittest.TestCase):
 def test_valid_and_changed_or_expired_material(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);root=base/'studio';ref=root/'assets'/'6'/'reference';ref.mkdir(parents=True)
   file=ref/'motion-reference.mp4';file.write_bytes(b'depth')
   private=base/'.video-agent-studio-private';private.mkdir()
   data={'project_id':6,'url':'https://test.volcvideo.com/path?token=secret','expires_at':time.time()+5000,'sha256':hashlib.sha256(b'depth').hexdigest(),'duration':10,'file':'reference/motion-reference.mp4','task_id':'id'}
   p=private/'depth-reference-6.json';p.write_text(json.dumps(data))
   self.assertEqual(depth_reference.load(root,6)['sha256'],data['sha256'])
   file.write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'已变化'):depth_reference.load(root,6)
   file.write_bytes(b'depth');data['expires_at']=time.time()-1;p.write_text(json.dumps(data))
   with self.assertRaisesRegex(ValueError,'过期'):depth_reference.load(root,6)
if __name__=='__main__':unittest.main()
