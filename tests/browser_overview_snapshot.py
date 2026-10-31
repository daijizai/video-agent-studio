"""Project snapshot metrics and one-screen desktop layout; temporary facts only."""
import os,sys,tempfile,threading,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);shutil.copytree(server.ROOT/'static',root/'static');server.ROOT=root;server.DATA=root/'data';server.DATA.mkdir();os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init()
 s=server.read();s['image_tasks']=[{'id':'paid','shot_id':s['shots'][0]['id'],'status':'completed','estimate':.4,'actual_cost_cny':.2},{'id':'unknown','shot_id':s['shots'][0]['id'],'provider_task_id':None,'status':'unknown','estimate':.3,'actual_cost_cny':None},{'id':'unsettled','shot_id':s['shots'][1]['id'],'status':'completed','estimate':.5,'actual_cost_cny':None}];s['tasks']=[{'id':'video','shot_id':s['shots'][0]['id'],'provider':'wan3','status':'queued','estimate':2,'actual_cost_cny':None}];server.save(s)
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000});errors=[];submits=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:submits.append(r.url) if '/submit' in r.url else None)
   s=server.read();s['video_segments']=[{'id':'a','duration':8},{'id':'b','duration':6},{'id':'c','duration':99,'include_in_playlist':False}]
   s['tasks']=[{'id':'ok','segment_id':'a','status':'completed','local_video':'/media/'+str(s['project_id'])+'/sample.mp4'},{'id':'running','segment_id':'b','status':'running'}];server.save(s)
   page.goto('http://127.0.0.1:'+str(http.server_port)+'/#overview');page.locator('.overview-dashboard>.panel').first.wait_for()
   assert page.locator('.overview-dashboard>.panel').count()==4
   assert '2个片段 · 计划 14 秒' in page.locator('.overview-video-summary').inner_text().replace('\n','')
   assert '可播放 1 / 2 段' in page.locator('.overview-video-summary').inner_text()
   assert page.locator('.overview-progress').count()==0
   assert '执行记录' not in page.locator('#view').inner_text()
   for width,height in [(1440,900),(1280,800)]:
    page.set_viewport_size({'width':width,'height':height})
    assert page.locator('.overview-dashboard').evaluate('(el)=>el.getBoundingClientRect().bottom')<=height
   for width in [375,768,1440]:
    page.set_viewport_size({'width':width,'height':900})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   assert not errors,errors;assert not submits,submits;b.close();print('PASS: metric counts, excluded segments, playable candidates, desktop one-screen layout, responsive overflow and zero submissions')
 finally:http.shutdown();http.server_close()
