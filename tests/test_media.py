import sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
class MediaRanges(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);(root/'assets'/'1').mkdir(parents=True);(root/'assets'/'1'/'clip.mp4').write_bytes(b'0123456789');(root/'private.txt').write_text('not media')
  self.patch=patch.object(server,'ROOT',root);self.patch.start();self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.http.server_port)
 def tearDown(self):self.http.shutdown();self.http.server_close();self.patch.stop();self.tmp.cleanup()
 def request(self,path='/media/1/clip.mp4',range=None,method='GET'):
  req=urllib.request.Request(self.url+path,headers={'Range':range} if range else {},method=method)
  try:
   with urllib.request.urlopen(req) as r:return r.status,dict(r.headers),r.read()
  except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()
 def test_full_head_and_seek_range(self):
  code,h,b=self.request();self.assertEqual(code,200);self.assertEqual(b,b'0123456789');self.assertEqual(h['Content-Type'],'video/mp4');self.assertEqual(h['Accept-Ranges'],'bytes')
  code,h,b=self.request(range='bytes=2-5');self.assertEqual(code,206);self.assertEqual(b,b'2345');self.assertEqual(h['Content-Range'],'bytes 2-5/10')
  code,h,b=self.request(range='bytes=7-');self.assertEqual(b,b'789')
  code,h,b=self.request(range='bytes=-3');self.assertEqual(b,b'789')
  code,h,b=self.request(method='HEAD');self.assertEqual(code,200);self.assertEqual(b,b'');self.assertEqual(h['Content-Length'],'10')
 def test_invalid_range_traversal_and_symlink(self):
  for r in ['bytes=99-','bytes=8-2','bytes=-0','bytes=0-1,3-4','invalid']:
   self.assertEqual(self.request(range=r)[0],416)
  self.assertEqual(self.request('/media/1/../../private.txt')[0],400)
  (server.ROOT/'assets'/'1'/'escape.mp4').symlink_to(server.ROOT/'private.txt')
  self.assertEqual(self.request('/media/1/escape.mp4')[0],404)
