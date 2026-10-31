"""Opening-frame image upload over HTTP uses the image-sized request limit."""
import base64,json,os,sqlite3,struct,sys,tempfile,threading,unittest,urllib.request,zlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from test_asset_library import png

class OpeningHTTP(unittest.TestCase):
 def test_large_valid_png_is_candidate_not_video_request(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);data=root/'data';data.mkdir()
   with patch.object(server,'ROOT',root),patch.object(server,'DATA',data),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'private'/'credentials.json')}):
    server.init();s=server.read();s['video_segments']=[{'id':'seg','name':'测试','duration':6,'material_video_prompt':'场景','asset_references':[]}];server.save(s)
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
     initial=png();body=b'k\0'+b'x'*1_600_000;kind=b'tEXt';chunk=struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
     picture=initial[:33]+chunk+initial[33:];s=server.read()
     payload={'project_id':1,'revision':s['revision'],'segment_id':'seg','base64':base64.b64encode(picture).decode()}
     data=json.dumps(payload).encode();self.assertGreater(len(data),2_000_000)
     req=urllib.request.Request(f'http://127.0.0.1:{http.server_port}/api/material-video/add-opening-candidate',data=data,headers={'Content-Type':'application/json'})
     with urllib.request.urlopen(req,timeout=20) as response:result=json.load(response)
     self.assertEqual(result['candidate']['status'],'candidate')
     self.assertEqual((root/'assets'/'1'/Path(result['candidate']['url']).name).read_bytes(),picture)
     current=server.read();self.assertEqual(current['tasks'],[]);self.assertNotIn('material_video_approval',current['video_segments'][0])
    finally:http.shutdown();http.server_close()

if __name__=='__main__':unittest.main()
