"""Exercise Codex handoff and provenance in an isolated workspace, without model calls."""
import os, shutil, sys, threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from test_asset_library import AssetFixture
from playwright.sync_api import sync_playwright

fixture=AssetFixture();fixture.setUp();root=fixture.root
shutil.copytree(server.ROOT/'static',root/'static')
asset=fixture.upload(fixture.create(),data=None)
view=asset['versions'][-1]['views'][0]
fixture.action('record-codex-source',asset_id=asset['id'],view_ids=[view['id']])
patches=[patch.object(server,'ROOT',root),patch.object(server,'DATA',root),patch.object(server,'material_service',return_value=fixture.service),
         patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'private'/'credentials.json')})]
for item in patches:item.start()
http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
threading.Thread(target=http.serve_forever,daemon=True).start()
try:
 with patch('providers.transport',side_effect=AssertionError('real model forbidden')),sync_playwright() as p:
  browser=p.chromium.launch();page=browser.new_page();errors=[];submits=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.on('request',lambda req:submits.append(req.url) if '/generation/submit' in req.url else None)
  page.goto(f'http://127.0.0.1:{http.server_port}/#characters')
  page.locator('.material-card').filter(has_text='钥匙').wait_for()
  assert page.get_by_text('来源：Codex · OpenAI 生图工具').is_visible()
  page.get_by_label('图片生成方式').select_option('codex-dialog')
  card=page.locator('.material-card').filter(has_text='钥匙')
  card.get_by_role('button',name='通过 Codex 生成').click()
  assert '工作台不会直接调用生图工具' in page.get_by_role('dialog').inner_text()
  assert '钥匙' in page.get_by_label('发给 Codex 的内容').input_value()
  page.get_by_label('需要的视图').select_option('side')
  assert '侧面' in page.get_by_label('发给 Codex 的内容').input_value()
  assert not errors,errors
  assert not submits,submits
  browser.close()
 print('PASS: Codex handoff, verified provenance and no generation')
finally:
 http.shutdown();http.server_close()
 for item in reversed(patches):item.stop()
 fixture.tearDown()
