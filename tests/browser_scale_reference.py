"""Scale reference, opening candidate and video inputs in an isolated workspace."""
import base64,json,os,shutil,sqlite3,sys,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from test_asset_library import AssetFixture,png
from playwright.sync_api import sync_playwright

fixture=AssetFixture();fixture.setUp();root=fixture.root
shutil.copytree(server.ROOT/'static',root/'static');shutil.copytree(server.ROOT/'resources',root/'resources')
roles=[]
for name in ('甲','乙'):
 role=fixture.upload(fixture.create('character',name),'portrait');role=fixture.upload(role,'body_front')
 fixture.action('adopt',asset_id=role['id'],version=role['latest_version']);roles.append(role)
created=fixture.action('create',kind='scale',name='比例参考',related_asset_ids=[r['id'] for r in roles])
scale=fixture.install_profile(created['assets'][-1]['id']);scale=fixture.upload(scale,'scale_main')
fixture.action('adopt',asset_id=scale['id'],version=scale['latest_version'])
state=fixture.state();state['settings']['ratio']='3:4';state['video_segments']=[{'id':'seg','name':'片段一','order':0,'duration':6,'material_video_prompt':'两只角色互动','material_video_audio':False,'asset_references':[],'include_in_playlist':True,'draft_revision':1}]
with sqlite3.connect(fixture.database) as con:con.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(state,ensure_ascii=False),))
patches=[patch.object(server,'ROOT',root),patch.object(server,'DATA',root),patch.object(server,'material_service',return_value=fixture.service),
         patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'private'/'credentials.json')})]
for item in patches:item.start()
http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
try:
 with patch('providers.transport',side_effect=AssertionError('real model forbidden')),sync_playwright() as p:
  browser=p.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':900});errors=[];submits=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.on('request',lambda req:submits.append(req.url) if '/generation/submit' in req.url or '/material-video/submit' in req.url else None)
  base=f'http://127.0.0.1:{http.server_port}'
  page.goto(base+'/#characters');page.get_by_role('button',name='比例参考',exact=True).click()
  card=page.locator('.material-card').filter(has_text='比例参考');card.wait_for();assert card.get_by_role('button',name='审计通过').is_visible()
  card.get_by_role('button',name='审计通过').click();assert '关联角色：甲 v3、乙 v3' in page.get_by_role('dialog').inner_text();page.keyboard.press('Escape')
  s=page.request.get(base+'/api/state').json()
  result=page.request.post(base+'/api/material-video/add-opening-candidate',data={'project_id':1,'revision':s['revision'],'segment_id':'seg','base64':base64.b64encode(png(384,512)).decode()})
  assert result.ok
  page.goto(base+'/#tasks');page.get_by_role('heading',name='开场画面候选').wait_for()
  assert '尚未作为视频首帧输入' in page.locator('.opening-frame-panel').inner_text()
  page.get_by_text('素材、项目视频风格与前置片段',exact=True).click()
  page.get_by_label('甲 · v3').check();page.get_by_label('乙 · v3').check();page.get_by_label('比例参考 · v2').check()
  page.get_by_role('button',name='保存并预览完整生成输入').click()
  page.locator('[data-segment-preview]').get_by_text('素材：甲 v3、乙 v3、比例参考 v2').wait_for()
  current=fixture.state()['video_segments'][0];assert current['asset_references'][-1]['kind']=='scale'
  page.get_by_role('button',name='审阅通过并使用此首帧').click()
  page.get_by_role('button',name='已采用此首帧').wait_for()
  page.get_by_role('button',name='保存并预览完整生成输入').click()
  page.locator('[data-segment-preview]').get_by_text('首帧：已审阅的开场图片；绑定的其他图片本次不发送。').wait_for()
  current=fixture.state()['video_segments'][0];assert current['video_input_mode']=='first_frame'
  assert not submits,submits
  assert not errors,errors
  browser.close()
 print('PASS: linked scale reference, opening candidate, preview and no submit')
finally:
 http.shutdown();http.server_close()
 for item in reversed(patches):item.stop()
 fixture.tearDown()
