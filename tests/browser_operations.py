"""Exercise operations page in an isolated workspace without touching user data."""
import os,shutil,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);data=root/'data';data.mkdir();shutil.copytree(server.ROOT/'static',root/'static');shutil.copytree(server.ROOT/'resources',root/'resources')
 with patch.object(server,'ROOT',root),patch.object(server,'DATA',data),patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(root/'secret.json')}):
  server.init();http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{http.server_port}/#operations');page.get_by_role('heading',name='作品运营').wait_for()
    page.get_by_role('button',name='添加发布记录').last.click();d=page.get_by_role('dialog');d.locator('#op-platform').fill('抖音');d.locator('#op-title').fill('我的枕头');d.locator('#op-time').fill('2026-11-01T09:00');d.get_by_role('button',name='保存',exact=True).click()
    page.get_by_text('我的枕头').wait_for();page.get_by_role('button',name='＋ 记录数据').click();d.locator('#op-observed').fill('2026-11-01T10:00');d.locator('#op-views').fill('1000');d.locator('#op-likes').fill('50');d.locator('#op-ad_spend').fill('20');d.get_by_role('button',name='保存数据').click()
    page.locator('.ops-metrics').get_by_text('1,000',exact=True).wait_for();page.get_by_role('button',name='＋ 记录数据').click();d.locator('#op-observed').fill('2026-11-01T11:00');d.locator('#op-views').fill('1500');d.locator('#op-likes').fill('75');d.locator('#op-ad_spend').fill('25');d.get_by_role('button',name='保存数据').click()
    page.get_by_text('与上次记录相比：播放 +500 · 点赞 +25 · 投流 +¥5。建议结合评论内容和投流时间复盘，不直接把增长归因于投流。').wait_for()
    page.get_by_text('查看历史数据（2）').click();page.locator('.ops-history').get_by_text('1,000',exact=True).wait_for()
    page.set_viewport_size({'width':375,'height':812});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile layout overflows'
    assert not errors,errors;browser.close()
   print('PASS: publication, time snapshots, comparison, history and mobile layout')
  finally:http.shutdown();http.server_close()
