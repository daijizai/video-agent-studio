"""Isolated browser integration test: new project, edits, switching, reload, dry-run."""
from browser_workbench_helpers import new_project, switch_project, open_material_details, open_shot_feedback
import os,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
    server.DATA=Path(tmp)/'db';server.DATA.mkdir();os.environ['STUDIO_SECRET_FILE']=str(Path(tmp)/'private'/'credentials.json');server.init()
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:'+str(http.server_port));page.locator('.current-project').wait_for()
            new_project(page,'隔离验证项目')
            page.get_by_role('link',name='02 剧本').click();page.get_by_label('剧本正文',exact=True).fill('Only belongs to project B');page.get_by_role('button',name='保存剧本',exact=True).click();page.get_by_role('status').filter(has_text='已保存').wait_for()
            page.reload();page.locator('.current-project').wait_for();assert '隔离验证项目' in page.locator('.current-project').inner_text()
            assert page.get_by_label('剧本正文',exact=True).input_value()=='Only belongs to project B'
            switch_project(page,1,'script');page.get_by_label('剧本正文',exact=True).wait_for();page.wait_for_function("document.querySelector('#script').value.includes('雨夜')")
            assert page.get_by_label('剧本正文',exact=True).input_value()!='Only belongs to project B'
            page.get_by_role('link',name='06 工具与设置').click();page.get_by_role('button',name='安全保存到仓库外',exact=True).wait_for()
            assert page.locator('#provider-choice').input_value()=='seedance25'
            page.get_by_label('保存当前供应商密钥（只写，不回显）').fill('fake-browser-test-key-never-real')
            page.get_by_role('button',name='安全保存到仓库外',exact=True).click();page.get_by_text('已配置 · 本项目未调用',exact=True).first.wait_for()
            assert page.locator('#provider-key').input_value()==''
            assert 'fake-browser-test-key-never-real' not in page.content()
            page.get_by_role('link',name='进入开发者诊断',exact=True).click();page.get_by_role('button',name='预览请求与估价',exact=True).click();page.wait_for_function('document.querySelector("#provider-result").textContent.includes("wan3.0-video-prime")')
            assert 'wan3.0-video' in page.locator('#provider-result').inner_text()
            assert not page.get_by_role('button',name='提交供应商 · 视频未授权').is_enabled()
            for name in ['视频制作','素材资产库','制作总览']:
                page.locator('nav').get_by_role('link',name=name).click()
            for width in [375,768,1440]:
                page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert '第一季' not in page.content();assert 'SEASON' not in page.content();assert not errors,errors
            browser.close();print('Browser project isolation, reload, secret write-only UI, Wan3 dry-run and responsive tests passed')
    finally:http.shutdown();http.server_close()
