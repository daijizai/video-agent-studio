"""Persisted stage UI checks; only temporary facts, no model or media generation."""
import os,sys,tempfile,threading,shutil,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,workflow_state
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);shutil.copytree(server.ROOT/'static',root/'static');server.ROOT=root;server.DATA=root/'data';server.DATA.mkdir();os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init();s=server.read()
 for i,shot in enumerate(s['shots']):
  shot.update(storyboard_task_id='image'+str(i),storyboard_local='/media/1/image'+str(i)+'.png',storyboard_sha256=str(i)*64,approved_image_task_id='image'+str(i),approved=True);shot['approval_snapshot']=workflow_state.record_approval(s,shot,'test human','time')
 task={'id':'sequence','kind':'sequence','provider':'wan3-prime','status':'queued','estimate':1,'approval_snapshot':[copy.deepcopy(x['approval_snapshot']) for x in s['shots']]};s['tasks']=[task];server.save(s)
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000});calls=[];page.on('request',lambda r:calls.append(r.url) if '/submit' in r.url else None)
   page.goto('http://127.0.0.1:'+str(http.server_port)+'/#overview');page.locator('[data-workflow-code="VIDEO_GENERATING"]').wait_for();assert '视频排队中' in page.locator('#view').inner_text();assert page.locator('.step.done').count()==2;assert '23:53' not in page.locator('.hero').evaluate('(e)=>getComputedStyle(e,":after").content')
   page.reload();page.locator('[data-workflow-code="VIDEO_GENERATING"]').wait_for()
   s=server.read();s['tasks'][0].update(status='completed',local_video='/media/1/sequence.mp4');s['final_video']={'task_id':'sequence','review_status':'pending'};server.save(s);page.reload();page.locator('[data-workflow-code="VIDEO_REVIEW"]').wait_for();assert page.locator('.step.done').count()==3
   s=server.read();s['shots'][0]['prompt']='changed after approval';server.save(s);server.init();page.reload();page.locator('[data-workflow-code="STORYBOARD_REVIEW"]').wait_for();assert '旧审批已过期' in page.locator('#view').inner_text();assert page.locator('.step.done').count()==1
   assert not calls,calls;b.close();print('PASS: overview derives from persisted approvals/tasks, reload/init stable, images not videos, stale approval rollback, no fixed example time, zero submit calls')
 finally:http.shutdown();http.server_close()
