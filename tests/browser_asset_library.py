"""Integrated material UI, mock generation only, no production DB or inference."""
import copy
import hashlib
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import asset_generation
import generation_scope
import image_provider
import server
import workflow_state
from test_asset_library import AssetFixture,png
from playwright.sync_api import sync_playwright

fixture=AssetFixture();fixture.setUp();root=fixture.root
fixture.install_profile(fixture.service.catalog(1)['assets'][0]['id'])
shutil.copytree(server.ROOT/'static',root/'static')
provider=image_provider.ImageProvider();provider.headers=Mock(return_value={});provider.submit=Mock(return_value='material-mock-task')
provider.status=Mock(return_value={'status':'completed','image_urls':['https://example.aliyuncs.com/material.png'],'usage':{},'actual_cost_cny':None})
generator=asset_generation.AssetGeneration(fixture.service,lambda _:provider,lambda _:png())
assetdir=root/'assets'/'1';assetdir.mkdir(parents=True);(assetdir/'board.png').write_bytes(png())
s=fixture.state();shot=s['shots'][0]
shot.update(storyboard_task_id='board',storyboard_local='/media/1/board.png',storyboard_sha256=hashlib.sha256(png()).hexdigest(),approved_image_task_id='board')
shot['approval_snapshot']=workflow_state.record_approval(s,shot,'test fixture human','time')
with fixture.service._connect() as con:con.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(s),))
patches=[patch.object(server,'ROOT',root),patch.object(server,'DATA',root),patch.object(server,'material_service',return_value=fixture.service),
         patch.object(server,'material_generation',return_value=generator),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'private'/'credentials.json')})]
for item in patches:item.start()
generation_scope.authorize_budgets(1,fixture.database,1,5,'explicit mock fixture only',0)
scope=generation_scope.read();scope['1']['paused']=True;generation_scope.path().write_text(json.dumps(scope))
http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
try:
 with patch('providers.transport',side_effect=AssertionError('real model forbidden')),sync_playwright() as p:
  browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(f'http://127.0.0.1:{http.server_port}/#characters');page.get_by_role('heading',name='素材资产库',exact=True).wait_for()
  page.locator('.material-card').wait_for();assert page.locator('.material-card').count()==1
  assert '尚无图片' in page.locator('.material-card').inner_text();assert '角色' in page.locator('.material-card .badge').inner_text()
  assert fixture.state()['characters']==fixture.initial['characters']
  page.locator('[data-generate]').click();page.get_by_role('button',name='预览本次生成计划',exact=True).click()
  page.get_by_role('heading',name='确认生成计划',exact=True).wait_for();assert '预计 ¥0.25' in page.get_by_role('dialog').inner_text()
  assert page.get_by_role('button',name='生成暂不可用',exact=True).is_disabled();provider.submit.assert_not_called()
  page.keyboard.press('Escape');assert generation_scope.is_paused(1,fixture.database)
  page.get_by_role('button',name='从故事整理素材',exact=True).click()
  page.get_by_role('button',name='加入素材清单',exact=True).click();page.wait_for_function('document.querySelectorAll(".material-card").length===2')
  page.get_by_role('button',name='物品',exact=True).click();page.locator('.material-card').wait_for();assert page.locator('.material-card').count()==1
  assert '钥匙' in page.locator('.material-card').inner_text();assert fixture.state()['shots'][0]['approved']
  fixture.install_profile(fixture.service.catalog(1)['assets'][-1]['id'])
  # Explicitly resume ONLY the mock fixture to exercise the real adapter orchestration.
  scope=generation_scope.read();scope['1']['paused']=False;generation_scope.path().write_text(json.dumps(scope));page.reload()
  page.locator('.material-card').first.wait_for();page.get_by_role('button',name='物品',exact=True).click()
  page.locator('[data-generate]').click();page.get_by_role('button',name='预览本次生成计划',exact=True).click()
  page.get_by_role('button',name='确认生成 1 张',exact=True).click()
  page.locator('[data-task-poll]').wait_for();assert provider.submit.call_count==1
  job=fixture.state()['image_tasks'][0];assert job['kind']=='asset_image' and 'shot_id' not in job
  page.locator('[data-task-poll]').click();page.wait_for_function('document.querySelector(".material-cover img")!==null')
  assert '候选 v2' in page.locator('[data-asset-tasks]').inner_text()
  assert fixture.service.catalog(1)['assets'][-1]['adopted_version'] is None
  page.locator('[data-history]').click();page.get_by_role('button',name='放大外观主图',exact=True).click()
  page.get_by_role('button',name='原尺寸',exact=True).wait_for();page.keyboard.press('Escape')
  assert page.get_by_role('dialog').count()==1
  page.get_by_role('button',name='人工采用 v2',exact=True).click()
  page.wait_for_function('document.querySelector(".material-version")?.textContent.includes("已采用")')
  assert fixture.state()['shots'][0]['approved']
  # Optional upload is secondary; it creates a candidate without replacing adopted v2.
  page.locator('.material-card details > summary').click();page.get_by_role('button',name='导入已有图片',exact=True).click()
  upload_file=root/'single-view.png';upload_file.write_bytes(png(color=(30,50,70)))
  page.get_by_label('这张图片的视图',exact=True).select_option('side')
  page.get_by_label('选择本机图片（PNG / JPEG / WebP，最多12MB）',exact=True).set_input_files(str(upload_file))
  page.get_by_role('button',name='导入选定图片',exact=True).click()
  page.wait_for_function('document.querySelector(".material-version")?.textContent.includes("当前 v3")')
  obj=fixture.service.catalog(1)['assets'][-1];assert obj['adopted_version']==2;assert len(obj['versions'])==3
  assert fixture.state()['shots'][0]['approved']
  # Edit text into a new independent version, without replacing existing character context.
  page.get_by_role('button',name='全部',exact=True).click();role=page.locator('.material-card').filter(has=page.get_by_role('heading',name='记者',exact=True))
  role.locator('[data-edit]').click();page.get_by_label('简要设定',exact=True).fill('冷静，短发，灰夹克。')
  page.get_by_role('button',name='保存为新版本',exact=True).click()
  page.wait_for_function('document.querySelector(".material-summary")?.textContent.includes("冷静")')
  assert fixture.state()['characters']==fixture.initial['characters']
  for width,height in [(375,812),(812,375),(1440,1100)]:
   page.set_viewport_size({'width':width,'height':height});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   if width==375:
    page.get_by_role('button',name='＋ 新增素材',exact=True).click();dialog=page.get_by_role('dialog',name='新增角色或物品',exact=True)
    assert dialog.evaluate('(e)=>e.getBoundingClientRect().width<=innerWidth')
    for _ in range(8):page.keyboard.press('Tab');assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
    page.keyboard.press('Escape')
  screenshot=os.environ.get('ASSET_LIBRARY_SCREENSHOT')
  if screenshot:page.screenshot(path=screenshot)
  page.get_by_role('link',name='04 分镜工作台',exact=True).click()
  page.locator('[data-material-refs] > summary').click();page.get_by_role('button',name='选择已采用素材',exact=True).click()
  page.get_by_role('button',name='用于本镜 · 重新审阅',exact=True).click()
  page.wait_for_function('document.querySelector("[data-material-refs]")?.textContent.includes("v2")')
  shot=fixture.state()['shots'][0];assert shot['asset_references'][0]['version']==2;assert not shot['approved']
  page.get_by_role('link',name='03 素材资产库',exact=True).click();page.locator('.material-card').first.wait_for()
  page.reload();page.locator('.material-card').first.wait_for();assert '已采用 v2' in page.locator('.material-card').filter(has_text='钥匙').inner_text()
  page.get_by_role('combobox',name='选择项目',exact=True).select_option('2')
  page.wait_for_function('document.querySelectorAll(".material-card").length===1')
  assert page.locator('.material-card img').count()==0;assert '钥匙' not in page.locator('[data-asset-list]').inner_text()
  assert fixture.state(1)['shots'][0]['asset_references'][0]['version']==2
  assert fixture.state(2).get('material_assets') is None;assert provider.submit.call_count==1;assert not errors,errors
  browser.close();print('PASS: character/object filter, legacy/no-image state, paused fee preview, mock AI master generation, manual adoption, independent views/import/history, candidate edit, pinned shot reference, reload/project isolation, mobile and native keyboard dialogs; no real inference')
finally:
 http.shutdown();http.server_close()
 for item in reversed(patches):item.stop()
 fixture.tearDown()
