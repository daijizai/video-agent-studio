"""MiniMax settings and offline video preview, temporary project and private storage."""
import os,sys,tempfile,threading,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);shutil.copytree(server.ROOT/'static',root/'static');shutil.copytree(server.ROOT/'resources',root/'resources');server.ROOT=root;server.DATA=root/'data';server.DATA.mkdir()
 os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init()
 s=server.read();s['video_segments']=[{'id':'seg','name':'MiniMax test','order':0,'duration':6,'material_video_prompt':'A camera moves through a quiet street.','material_video_audio':False,'asset_references':[],'include_in_playlist':True,'draft_revision':1}];server.save(s)
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1000});errors=[];submits=[]
   page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:submits.append(r.url) if '/submit' in r.url else None)
   base='http://127.0.0.1:'+str(http.server_port);page.goto(base+'/#tools')
   page.locator('#provider-choice').select_option('minimax');assert page.locator('#minimax-model-options').is_visible()
   assert page.locator('#provider-resolution').input_value()=='768P';assert page.locator('#provider-audio').is_disabled()
   assert page.locator('#provider-audio').input_value()=='provider_default'
   page.locator('#minimax-model').select_option('MiniMax-H3-Lite');assert page.locator('#provider-resolution option').all_text_contents()==['480P','768P']
   page.locator('#minimax-model').select_option('MiniMax-H3');page.locator('#provider-resolution').select_option('2K')
   page.locator('#provider-save').click();page.wait_for_timeout(500);page.reload();page.locator('#minimax-model-options').wait_for(state='visible')
   assert page.locator('#provider-resolution').input_value()=='2K';assert page.locator('#provider-choice').input_value()=='minimax'
   page.locator('#provider-key').fill('offline-fake-browser-key');page.locator('#save-provider-key').click();page.wait_for_timeout(400)
   assert page.locator('#provider-key').input_value()=='';assert 'offline-fake-browser-key' not in page.content()
   assert page.locator('#budget-minimax-model').count()==1
   page.goto(base+'/#tasks');page.locator('[data-preview-segment]').wait_for();page.locator('[data-preview-segment]').click()
   page.locator('[data-submit-segment]').wait_for();preview=page.locator('[data-segment-preview]').inner_text()
   assert 'MiniMax-H3' in preview and '预占 ¥4.80' in preview and '声音由模型处理' in preview,preview
   for width in [375,768,1440]:
    page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
   assert not submits,submits;assert not errors,errors
   b.close();print('PASS: MiniMax models/resolutions, key write-only, reload, segment preview and cost, responsive, zero submits')
 finally:http.shutdown();http.server_close()
