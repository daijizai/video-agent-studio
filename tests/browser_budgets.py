"""Independent category budget UI test with temporary records and no provider calls."""
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
   base='http://127.0.0.1:'+str(http.server_port)
   page.goto(base+'/#overview');page.locator('#video-budget-limit').wait_for(state='attached')
   assert page.locator('#image-budget-limit').count()==0
   assert page.locator('.budget-card').count()==1
   assert '图片预算' not in page.locator('#view').inner_text()
   page.locator('.budget-edit summary').click()
   page.locator('#video-budget-limit').fill('7');page.locator('#authorize-budgets').click()
   page.get_by_text('视频总预算已更新',exact=True).wait_for()
   assert '¥5.00' in page.locator('.budget-card').inner_text()
   assert not any(x['approved'] for x in server.read()['shots'])
   assert server.read()['budget_authorizations'][-1]['quality_approval'] is False
   page.reload();page.locator('#video-budget-limit').wait_for(state='attached');assert page.locator('#video-budget-limit').input_value()=='7'
   page.goto(base+'/#tools');page.get_by_role('heading',name='高级工具').wait_for()
   assert page.locator('#budget-panel-slot').count()==0
   page.goto(base+'/#overview');page.locator('.budget-card').wait_for()
   for w in [375,768,1440]:
    page.set_viewport_size({'width':w,'height':900})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),w
   page.set_viewport_size({'width':1440,'height':1000})
   page.screenshot(path='/tmp/frame-overview-budget.png',full_page=True)
   assert not submits,submits;assert not errors,errors;b.close();print('PASS: video-only overview budget, tools removal, authorization persistence, responsive layout and zero model submits')
 finally:http.shutdown();http.server_close()
