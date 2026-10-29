"""Isolated browser test for submit feedback, polling, terminal stop and retained edits."""
from browser_workbench_helpers import new_project, switch_project, open_material_details, open_shot_feedback
import os,sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,generation_scope
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 server.DATA=Path(tmp)/'db';server.DATA.mkdir();os.environ['STUDIO_SECRET_FILE']=str(Path(tmp)/'private'/'credentials.json');server.init();generation_scope.grant(1,server.DATA/'studio.db',2,1,0)
 release=threading.Event()
 def submit(self,prepared,authorized=False):
  assert authorized;release.wait(5);return 'mock-image-task'
 responses=[TimeoutError('temporary test network failure'),{'status':'running','image_urls':[],'usage':{},'actual_cost_cny':None},{'status':'completed','image_urls':['https://example.aliyuncs.com/image.png'],'usage':{'output_image_count':1},'actual_cost_cny':None}]
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with patch.object(server.image_provider.ImageProvider,'headers',return_value={}),patch.object(server.image_provider.ImageProvider,'submit',submit),patch.object(server.image_provider.ImageProvider,'status',side_effect=responses) as query,patch.object(server,'cache_image',return_value='/mock-image.png'),sync_playwright() as p:
   b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.clock.install()
   page.route('**/mock-image.png',lambda route:route.fulfill(content_type='image/png',body=__import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nRUAAAAASUVORK5CYII=')))
   page.goto('http://127.0.0.1:'+str(http.server_port)+'/#shots');page.locator('[data-image-generate="0"]').wait_for()
   assert not page.locator('.shot-details').first.evaluate('(e)=>e.open')
   page.locator('[data-image-generate="0"]').click();page.get_by_text('正在提交 · 请勿重复',exact=True).wait_for();release.set()
   page.locator('[data-image-art="0"]').get_by_text('已提交 · 排队中',exact=True).wait_for()
   open_shot_feedback(page,0);page.locator('#intent0').fill('Unsaved static composition survives polling')
   page.clock.fast_forward(1000);page.get_by_text('查询暂失败，将退避重查原任务',exact=True).wait_for();assert query.call_count==1
   page.clock.fast_forward(16000);page.locator('[data-image-art="0"]').get_by_text('生成中',exact=True).wait_for();assert query.call_count==2
   page.clock.fast_forward(8000);page.locator('[data-image-art="0"] img').wait_for();assert query.call_count==3
   page.wait_for_function("document.querySelector('[data-image-art=\"0\"] img').naturalWidth > 0")
   assert page.locator('dialog .shot-details').evaluate('(e)=>e.open');assert page.locator('#intent0').input_value()=='Unsaved static composition survives polling'
   page.clock.fast_forward(60000);assert query.call_count==3
   page.locator('[data-shot-save="0"]').click();page.get_by_role('status').filter(has_text='已保存').wait_for();assert server.read()['shots'][0]['story_intent']=='Unsaved static composition survives polling'
   page.get_by_role('link',name='06 工具与设置').click();page.get_by_role('link',name='进入开发者诊断',exact=True).click();page.locator('[data-execution-task]').wait_for();assert page.locator('[data-execution-task]').count()==1;assert '千问AI图片API' in page.locator('#execution-ledger').inner_text();assert '先连接ComfyUI' not in page.locator('#execution-ledger').inner_text()
   page.get_by_role('link',name='04 分镜工作台').click()
   s=server.read();s['image_tasks'][0]['status']='failed';s['shots'][0]['image_status']='failed';s['shots'][0].pop('storyboard_local',None);s['shots'][0].pop('storyboard_image',None);server.save(s)
   page.reload();page.locator('[data-image-art="0"]').get_by_text('生成失败',exact=True).wait_for();page.clock.fast_forward(60000);assert query.call_count==3
   s=server.read();s['image_tasks'][0]['status']='unknown';s['image_tasks'][0]['provider_task_id']=None;s['shots'][0]['image_status']='unknown';server.save(s)
   page.reload();page.locator('[data-image-art="0"]').get_by_text('待核对',exact=True).wait_for();page.clock.fast_forward(60000);assert query.call_count==3;assert not page.locator('[data-image-poll]').first.is_enabled()
   # Switch to a genuinely isolated empty project; old terminal task is never queried again.
   other=server.create_project('Polling isolation');page.reload();page.locator('.current-project').wait_for();assert page.locator('.shot').count()==0;page.clock.fast_forward(60000);assert query.call_count==3
   for w in [375,768,1440]:page.set_viewport_size({'width':w,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   assert not errors,errors;b.close();print('PASS: immediate submit state, poll error/backoff, completion image, terminal stop, collapsed editable details and project isolation')
 finally:release.set();http.shutdown();http.server_close()
