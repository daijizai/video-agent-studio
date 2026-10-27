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
   page.goto('http://127.0.0.1:'+str(http.server_port)+'/#tools');page.locator('#image-budget-limit').wait_for();assert page.locator('#image-budget-limit').input_value()=='';assert page.locator('#video-budget-limit').input_value()==''
   page.locator('#image-budget-limit').fill('3');page.locator('#video-budget-limit').fill('7');page.locator('#authorize-budgets').click();page.get_by_text('图片总预算 ¥3.00',exact=True).wait_for();page.get_by_text('视频总预算 ¥7.00',exact=True).wait_for()
   cards=page.locator('.budget-card');assert '实际总额\n未核实' in cards.nth(0).inner_text();assert '2笔费用仍未知' in cards.nth(0).inner_text();assert '可用余额\n¥2.00' in cards.nth(0).inner_text();assert '可用余额\n¥5.00' in cards.nth(1).inner_text()
   assert not any(x['approved'] for x in server.read()['shots']);assert server.read()['budget_authorizations'][-1]['quality_approval'] is False
   page.reload();page.locator('#image-budget-limit').wait_for();assert page.locator('#image-budget-limit').input_value()=='3';assert page.locator('#video-budget-limit').input_value()=='7'
   page.get_by_role('button',name='＋ 新建项目',exact=True).click();page.get_by_label('项目名称',exact=True).fill('Other budget project');page.get_by_role('button',name='创建项目',exact=True).click();page.get_by_role('link',name='06 工具与设置').click();page.locator('#image-budget-limit').wait_for();assert page.locator('#image-budget-limit').input_value()=='';assert page.locator('#video-budget-limit').input_value()==''
   for w in [375,768,1440]:page.set_viewport_size({'width':w,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   assert not submits,submits;assert not errors,errors;b.close();print('PASS: explicit separate budget authorization, unknown/settled/inflight accounting, non-borrowed balances, quality unchanged, persistence, project isolation and zero model submits')
 finally:http.shutdown();http.server_close()
