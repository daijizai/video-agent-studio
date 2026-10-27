"""Synthetic local-video controls test. Never touches a real project or provider."""
import os,sys,tempfile,threading,subprocess,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,media_files
from playwright.sync_api import sync_playwright
if not shutil.which('ffmpeg'):raise SystemExit('SKIP: FFmpeg needed for synthetic media test')
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);shutil.copytree(server.ROOT/'static',root/'static');server.ROOT=root;server.DATA=root/'data';server.DATA.mkdir();os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init()
 assets=root/'assets'/'1';assets.mkdir(parents=True);clip=assets/'control-test.mp4'
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=24:duration=3','-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest','-movflags','+faststart',str(clip)],check=True)
 info=media_files.probe_video(clip);assert info['has_audio'] and info['duration']>=3
 s=server.read();s['tasks']=[{'id':'test-task','shot_id':s['shots'][0]['id'],'name':'合成控件测试','provider':'test-fixture','provider_task_id':'test-only','status':'completed','estimate':0,'local_video':'/media/1/control-test.mp4','media_info':info,'test_only':True}];s['final_video']={'local_url':'/media/1/control-test.mp4','media_info':info,'test_only':True};server.save(s)
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));submits=[];page.on('request',lambda r:submits.append(r.url) if '/submit' in r.url else None)
   page.goto('http://127.0.0.1:'+str(http.server_port)+'/#tasks');page.locator('video').wait_for();assert page.locator('#video-choice').input_value()=='final';page.wait_for_function('document.querySelector("video").readyState >= 1');assert page.locator('video').evaluate('(v)=>v.controls');assert page.locator('#video-test-badge').is_visible()
   page.locator('video').evaluate('(v)=>{v.volume=.3;v.currentTime=1.5;return v.play()}');page.wait_for_function('document.querySelector("video").currentTime >= 1.5');page.locator('video').evaluate('(v)=>v.pause()');assert page.locator('video').evaluate('(v)=>v.paused');assert abs(page.locator('video').evaluate('(v)=>v.volume')-.3)<.01
   assert page.locator('#video-media-info').inner_text();assert 'FFprobe音轨：存在' in page.locator('#video-cost').inner_text();assert not page.locator('#video-submit').is_enabled()
   page.locator('#video-choice').select_option('final');page.locator('video').wait_for();assert page.locator('#video-shot-title').inner_text()=='整片结果'
   page.locator('#video-choice').select_option(s['shots'][1]['id']);page.get_by_role('heading',name='本镜尚无独立视频',exact=True).wait_for();assert page.locator('video').count()==0;page.get_by_role('button',name='切换到整片结果').click();page.locator('video').wait_for();assert page.locator('#video-choice').input_value()=='final'
   for w in [375,768,1440]:page.set_viewport_size({'width':w,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   assert not submits,submits;assert not errors,errors;b.close();print('PASS: synthetic video playback/pause/seek/volume, audio metadata, final selection, honest empty state, responsive UI; zero generation submissions')
 finally:http.shutdown();http.server_close()
