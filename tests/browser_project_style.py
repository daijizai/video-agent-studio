"""Style editing in an isolated workspace; no model calls."""
import os,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
import server
from test_asset_library import png
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);server.DATA=root/'data';server.DATA.mkdir()
    os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init()
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page(viewport={'width':1100,'height':800});errors=[];submits=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda r:submits.append(r.url) if '/generation/submit' in r.url else None)
            base='http://127.0.0.1:'+str(http.server_port)
            page.goto(base+'/#characters');page.get_by_text('项目视觉风格',exact=True).click()
            page.get_by_label('视觉风格描述',exact=True).fill('冷白光，低饱和电影感')
            picture=root/'style.png';picture.write_bytes(png())
            page.get_by_label('或从电脑选择参考图（PNG / JPEG / WebP，最多10MB）',exact=True).set_input_files(str(picture))
            page.get_by_role('button',name='保存项目风格',exact=True).click()
            page.get_by_role('button',name='项目视觉风格',exact=True).click()
            page.get_by_alt_text('当前项目风格参考图',exact=True).wait_for()
            assert page.get_by_label('视觉风格描述',exact=True).input_value()=='冷白光，低饱和电影感'
            page.reload();page.get_by_text('项目视觉风格',exact=True).click()
            assert page.get_by_label('视觉风格描述',exact=True).input_value()=='冷白光，低饱和电影感'
            assert page.get_by_alt_text('当前项目风格参考图',exact=True).count()==1
            catalog=page.request.get(base+'/api/assets').json()
            result=page.request.post(base+'/api/assets/style',data={'project_id':catalog['project_id'],'revision':catalog['revision'],'description':'冷白光，低饱和电影感','style_prompt':'详细风格：柔和侧光，保留材质细节。','reference_action':'keep'})
            assert result.ok
            page.reload();page.get_by_text('项目视觉风格',exact=True).click()
            page.get_by_text('查看具体风格提示词',exact=True).click()
            assert page.get_by_text('详细风格：柔和侧光，保留材质细节。',exact=True).is_visible()
            page.get_by_role('button',name='关闭具体风格提示词').click()
            page.get_by_label('视觉风格描述',exact=True).fill('暖色风格')
            page.get_by_role('button',name='查看具体风格提示词').click()
            assert page.get_by_text('描述已修改但尚未保存；下方仍显示上次保存的内容。',exact=True).is_visible()
            page.get_by_role('button',name='关闭具体风格提示词').click()
            page.get_by_role('button',name='关闭项目视觉风格').click()
            page.request.post(base+'/api/projects/new',data={'title':'独立项目'})
            page.reload();page.get_by_text('项目视觉风格',exact=True).click()
            assert page.get_by_label('视觉风格描述',exact=True).input_value()==''
            assert page.get_by_alt_text('当前项目风格参考图',exact=True).count()==0
            for width in (375,768,1100):
                page.set_viewport_size({'width':width,'height':800});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            assert not submits,submits
            browser.close();print('PASS: project style editing, image upload, persistence, isolation and no generation')
    finally:http.shutdown();http.server_close()
