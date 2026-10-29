"""Standard-view UX with temporary assets, paused budget and zero model requests."""
from browser_workbench_helpers import new_project, switch_project, open_material_details, open_shot_feedback
import copy
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
import asset_generation
import asset_templates
import generation_scope
import image_provider
import server
from test_asset_library import AssetFixture
from asset_handoff_fixture import handoff
from playwright.sync_api import sync_playwright

fixture=AssetFixture();fixture.setUp();root=fixture.root
shutil.copytree(server.ROOT/'static',root/'static')
provider=image_provider.ImageProvider();provider.headers=Mock(return_value={});provider.submit=Mock(side_effect=AssertionError('model call forbidden'))
generator=asset_generation.AssetGeneration(fixture.service,lambda _:provider)
patches=[patch.object(server,'ROOT',root),patch.object(server,'DATA',root),patch.object(server,'material_service',return_value=fixture.service),
         patch.object(server,'material_generation',return_value=generator),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'private'/'credentials.json')})]
for item in patches:item.start()
generation_scope.authorize_budgets(1,fixture.database,0,0,'paused template fixture',0)
scope=generation_scope.read();scope['1']['paused']=True;generation_scope.path().write_text(json.dumps(scope));auth_before=generation_scope.path().read_bytes()
http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
  page.goto(f'http://127.0.0.1:{http.server_port}/#characters');page.locator('[data-detail]').wait_for()
  before=copy.deepcopy(fixture.state())
  open_material_details(page);design=page.get_by_role('dialog');assert '设计草案' in design.inner_text()
  assert '尚未交接' in design.inner_text();assert design.locator('input,textarea').count()==0
  assert '服装' in design.inner_text();assert 'template_hash' not in design.inner_text()
  page.keyboard.press('Escape');assert page.locator('[data-generate]').is_disabled()
  role=fixture.service.catalog(1)['assets'][0];fixture.install_profile(role['id'],handoff(root,'character'))
  page.reload();page.locator('[data-generate]').wait_for();before=copy.deepcopy(fixture.state());page.locator('[data-generate]').click()
  assert page.locator('[data-view-tag][value="portrait"]').count()==0
  assert page.locator('[data-view-tag][value="body_front"]').is_disabled()
  assert page.locator('[data-view-tag][value="body_back"]').is_disabled()
  assert page.get_by_role('button',name='预览本次生成计划',exact=True).is_disabled()
  assert '先审阅已保存的身份母版' in page.get_by_role('dialog').inner_text()
  assert fixture.state()==before;page.keyboard.press('Escape')
  # Adopt an artificial identity image in this disposable fixture.
  role=fixture.service.catalog(1)['assets'][0];role=fixture.upload(role,'portrait');fixture.action('adopt',asset_id=role['id'],version=4)
  page.reload();page.locator('[data-generate]').wait_for();assert '全身正面待建立' in page.locator('.material-production').inner_text()
  page.locator('[data-generate]').click()
  assert page.locator('[data-view-tag][value="body_front"]').is_checked()
  assert page.locator('[data-view-tag][value="head_side"]').count()==0
  assert page.locator('[data-view-tag][value="body_side"]').is_disabled()
  page.get_by_role('button',name='预览本次生成计划',exact=True).click();page.get_by_role('heading',name='确认生成计划',exact=True).wait_for()
  assert '预计 ¥0.52' in page.get_by_role('dialog').inner_text();page.keyboard.press('Escape')
  role=fixture.upload(role,'body_front');fixture.action('adopt',asset_id=role['id'],version=5)
  page.reload();page.locator('[data-generate]').wait_for();page.locator('[data-generate]').click()
  assert page.locator('[data-view-tag][value="body_side"]').is_enabled();assert page.locator('[data-view-tag][value="body_back"]').is_disabled()
  page.keyboard.press('Escape');role=fixture.upload(role,'body_side');fixture.action('adopt',asset_id=role['id'],version=6)
  page.reload();page.locator('[data-generate]').wait_for();page.locator('[data-generate]').click()
  assert page.locator('[data-view-tag][value="body_back"]').is_enabled()
  page.locator('[data-view-tag][value="body_back"]').check();page.get_by_role('button',name='预览本次生成计划',exact=True).click()
  page.get_by_role('heading',name='确认生成计划',exact=True).wait_for();assert '预计 ¥0.54' in page.get_by_role('dialog').inner_text()
  page.keyboard.press('Escape')
  # A new recipe must ask for current-standard review without rewriting history.
  before_recipe=copy.deepcopy(fixture.state())
  with patch.object(asset_templates,'RECIPE_VERSION','2.0'):
   page.reload();page.locator('[data-generate]').wait_for()
   assert '当前制作规范待复核' in page.locator('.material-production').inner_text()
   assert fixture.state()==before_recipe
   page.locator('[data-generate]').click();assert page.locator('[data-view-tag][value="body_back"]').is_disabled();page.keyboard.press('Escape')
   open_material_details(page);page.locator('[data-history]').click()
   page.get_by_role('button',name='按当前规范重新审阅 v6',exact=True).click()
   page.wait_for_function('!document.querySelector("dialog")')
   assert len(fixture.service.catalog(1)['assets'][0]['production_reviews'])==4
  for width,height in [(375,812),(812,375),(1440,1000)]:
   page.set_viewport_size({'width':width,'height':height});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   open_material_details(page);dialog=page.get_by_role('dialog');assert dialog.evaluate('(e)=>e.getBoundingClientRect().width<=innerWidth')
   for _ in range(5):page.keyboard.press('Tab');assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
   page.keyboard.press('Escape')
  assert generation_scope.path().read_bytes()==auth_before;provider.submit.assert_not_called();assert not errors,errors
  browser.close();print('PASS: readable system design without machine forms, identity/full-body/side-back gates, fee preview .25/.52/.54, recipe change re-review without historical rewrite, phone/keyboard, paused zero budget and zero model calls')
finally:
 http.shutdown();http.server_close()
 for item in reversed(patches):item.stop()
 fixture.tearDown()
