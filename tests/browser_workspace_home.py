"""Workspace navigation, pinning and creation with isolated local records."""
import os,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    server.DATA=Path(tmp)/'db';server.DATA.mkdir()
    os.environ['STUDIO_SECRET_FILE']=str(Path(tmp)/'private'/'credentials.json')
    server.init();server.create_project('Second film');server.create_project('New thriller')
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(http.server_port)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];submits=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:submits.append(r.url) if '/submit' in r.url else None)
            page.goto(base+'/workspace.html?pin=2')
            page.get_by_text('3 个项目',exact=True).wait_for()
            assert page.locator('.project').first.get_attribute('data-project-id')=='2'
            page.reload();page.locator('.project').first.wait_for()
            assert page.locator('.project').first.get_attribute('data-project-id')=='2'
            page.get_by_role('button',name='打开 New thriller',exact=True).click()
            page.get_by_role('link',name='返回工作空间首页',exact=True).wait_for()
            assert server.current_project()==3
            page.get_by_role('link',name='返回工作空间首页',exact=True).click()
            page.get_by_role('heading',name='全部项目',exact=True).wait_for()
            page.get_by_role('button',name='＋ 新建项目',exact=True).click()
            page.get_by_label('项目名称',exact=True).fill('<img src=x onerror=alert(1)>')
            page.get_by_role('button',name='创建并打开',exact=True).click()
            page.get_by_role('link',name='返回工作空间首页',exact=True).wait_for()
            page.get_by_role('link',name='返回工作空间首页',exact=True).click()
            page.get_by_text('4 个项目',exact=True).wait_for()
            assert page.locator('#projects img').count()==0
            for width in (375,768,1440):
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            assert not submits,submits
            browser.close()
            print('PASS: all-project home, persistent pin order, project open, return link, creation, escaped titles, mobile layout, zero generation')
    finally:
        http.shutdown();http.server_close()
