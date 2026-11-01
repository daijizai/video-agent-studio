"""Check opening + identity references from the segment page without paid calls."""
import base64,json,os,shutil,sqlite3,sys,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from test_asset_library import AssetFixture,png
from playwright.sync_api import sync_playwright
fixture=AssetFixture();fixture.setUp();root=fixture.root
shutil.copytree(server.ROOT/'static',root/'static');shutil.copytree(server.ROOT/'resources',root/'resources')
role=fixture.upload(fixture.create('character','角色甲'),'portrait',png(color=(10,20,30)));role=fixture.upload(role,'body_front',png(color=(20,30,40)));role=fixture.upload(role,'body_side',png(color=(30,40,50)));role=fixture.upload(role,'body_back',png(color=(40,50,60)));fixture.action('adopt',asset_id=role['id'],version=role['latest_version'])
state=fixture.state();state['settings'].update(ratio='3:4',provider='seedance25',resolution='720p');state['video_segments']=[{'id':'seg','name':'片段一','order':0,'duration':6,'material_video_prompt':'互动','material_video_audio':False,'asset_references':[],'include_in_playlist':True,'draft_revision':1}]
with sqlite3.connect(fixture.database) as con:con.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(state,ensure_ascii=False),))
patches=[patch.object(server,'ROOT',root),patch.object(server,'DATA',root),patch.object(server,'material_service',return_value=fixture.service),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'private'/'credentials.json')})]
for item in patches:item.start()
http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
try:
 with patch('providers.transport',side_effect=AssertionError('real model forbidden')),sync_playwright() as p:
  browser=p.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':900});errors=[];submits=[]
  page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda req:submits.append(req.url) if '/material-video/submit' in req.url else None)
  base=f'http://127.0.0.1:{http.server_port}';s=page.request.get(base+'/api/state').json()
  result=page.request.post(base+'/api/material-video/add-opening-candidate',data={'project_id':1,'revision':s['revision'],'segment_id':'seg','base64':base64.b64encode(png(384,512)).decode()});assert result.ok
  page.goto(base+'/#tasks');page.get_by_role('heading',name='开场画面候选').wait_for()
  page.get_by_text('素材、项目视频风格与前置片段',exact=True).click();page.get_by_label('角色甲 · v5').check();page.get_by_label('侧面',exact=True).check();page.get_by_label('背面',exact=True).check()
  page.get_by_role('button',name='使用开场和素材参考').click();page.get_by_role('button',name='已使用开场和素材参考').wait_for()
  page.get_by_role('button',name='保存并预览完整生成输入').click()
  page.locator('[data-segment-preview]').get_by_text('开场参考：已审阅的开场图片与所选素材一同发送；开场画面不保证严格一致。').wait_for()
  page.locator('[data-segment-preview]').get_by_text('素材：角色甲 v5 · 正面、角色甲 v5 · 侧面、角色甲 v5 · 背面').wait_for()
  s=fixture.state();assert s['video_segments'][0]['video_input_mode']=='opening_reference';assert len(s['video_segments'][0]['asset_references'][0]['views'])==3;assert not submits,submits;assert not errors,errors
  browser.close()
 print('PASS: opening reference mode, actual materials, preview and no generation')
finally:
 http.shutdown();http.server_close()
 for item in reversed(patches):item.stop()
 fixture.tearDown()
