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
   page.goto(base+'/#overview');page.locator('.overview-budget').wait_for()
   assert page.locator('#project-basics,#provider-choice,#provider-ratio').count()==0
   page.goto(base+'/#tasks');page.locator('#video-settings-open').wait_for()
   assert page.locator('#provider-choice').count()==0
   page.locator('#video-settings-open').click();page.get_by_role('dialog').wait_for()
   page.locator('#provider-ratio').select_option('9:16');page.locator('#provider-resolution').select_option('1080p');page.locator('#provider-audio').select_option('true')
   page.get_by_role('button',name='取消',exact=True).click()
   assert server.read()['settings'].get('ratio')!='9:16'
   page.locator('#video-settings-open').click()
   page.locator('#provider-ratio').select_option('9:16');page.locator('#provider-resolution').select_option('1080p');page.locator('#provider-audio').select_option('true')
   page.locator('#provider-save').click();page.get_by_text('制作设置已保存；未发起生成',exact=True).wait_for()
   assert page.get_by_role('dialog').count()==0
   page.reload();page.locator('#video-settings-open').click()
   assert page.locator('#provider-ratio').input_value()=='9:16'
   assert page.locator('#provider-resolution').input_value()=='1080p'
   assert page.locator('#provider-audio').input_value()=='true'
   page.locator('#provider-choice').select_option('minimax')
   assert page.locator('#provider-resolution').input_value()=='768P'
   assert page.locator('#provider-audio').is_disabled()
   page.locator('#provider-save').click();page.get_by_text('制作设置已保存；未发起生成',exact=True).wait_for()
   page.wait_for_function("document.querySelector('#video-settings-summary')?.textContent.includes('MiniMax')")
   assert server.read()['settings']['provider']=='minimax'
   assert server.read()['settings']['resolution']=='768P'
   page.locator('#video-settings-open').click()
   for w in [375,768,1440]:
    page.set_viewport_size({'width':w,'height':1000})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),w
    assert page.get_by_role('dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth'),w
   page.screenshot(path='/tmp/frame-video-settings-dialog.png',full_page=True)
   page.keyboard.press('Escape');assert page.get_by_role('dialog').count()==0
   assert page.locator('#video-settings-open').evaluate('(el)=>el===document.activeElement')
   page.goto(base+'/#tools');page.get_by_role('heading',name='高级工具').wait_for()
   assert page.locator('#provider-choice,#provider-ratio,#image-default-model').count()==0
   page.goto(base+'/#characters');page.locator('#image-model-open').wait_for();page.locator('#image-model-open').click();page.locator('#image-model-save').wait_for()
   assert page.locator('#image-default-model').count()==1
   page.locator('#image-default-model').select_option('qwen-image-3.0-pro')
   page.locator('#image-model-save').click();page.get_by_text('图片默认模型已保存；未发起生成',exact=True).wait_for()
   assert server.read()['settings']['image_model']=='qwen-image-3.0-pro'
   assert page.locator('.provider-panel').count()==0
   sizes=page.locator('.asset-heading-actions>button').evaluate_all('(items)=>items.map(el=>el.getBoundingClientRect().height)')
   assert len(set(sizes))==1,sizes
   assert not submits,submits;assert not errors,errors;b.close();print('PASS: modal save/cancel/Escape/focus, persistence, model compatibility, route ownership, responsive layout and zero generation')
 finally:http.shutdown();http.server_close()
