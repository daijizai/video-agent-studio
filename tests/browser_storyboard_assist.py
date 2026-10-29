"""Real integrated UI, temporary SQLite, no submit/model/production data calls."""
from browser_workbench_helpers import new_project, switch_project, open_material_details, open_shot_feedback
import copy
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import workflow_state
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);shutil.copytree(server.ROOT/'static',root/'static');server.ROOT=root
    server.DATA=root/'data';server.DATA.mkdir()
    os.environ['STUDIO_SECRET_FILE']=str(root/'private'/'credentials.json');server.init()
    s=server.read()
    for i,shot in enumerate(s['shots']):
        shot.update(storyboard_task_id=f'img{i}',storyboard_local=f'/media/1/img{i}.png',
                    storyboard_sha256=str(i)*64,approved=True,approved_image_task_id=f'img{i}')
        shot['approval_snapshot']=workflow_state.record_approval(s,shot,'test human','time')
    s['shots'][0]['creative_details']={'camera':{'movement':'locked'},'action_chain':{'end':'坐姿'}}
    # Reapprove the test fixture's explicit structure, not actual media.
    s['shots'][0]['approval_snapshot']=workflow_state.record_approval(s,s['shots'][0],'fixture','time')
    s['shots'][0]['reference_images']=['https://example.com/reference.png']
    s['shots'][0]['approval_snapshot']=workflow_state.record_approval(s,s['shots'][0],'fixture','time')
    server.save(s)
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];submits=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:submits.append(r.url) if '/submit' in r.url else None)
            page.goto(f'http://127.0.0.1:{http.server_port}/#diagnostics')
            page.locator('.storyboard-assist').first.wait_for(state='attached')
            assert page.locator('.storyboard-assist[open]').count()==0
            first=page.locator('.shot-details').nth(0);first.locator('> summary').click()
            assist=first.locator('.storyboard-assist');summary=assist.locator('> summary')
            summary.focus();summary.press('Enter');assert assist.get_attribute('open') is not None
            original=copy.deepcopy(server.read())
            assist.get_by_role('button',name='检查当前分镜草稿').click()
            assert '参考图 1 未绑定用途' in assist.locator('.assist-report').inner_text()
            assert server.read()==original, 'preflight must not write or revoke approval'
            assist.get_by_role('link',name='定位此字段').first.click()
            assert page.locator(':focus').get_attribute('data-path')=='reference_bindings.0.purpose'
            assist.get_by_label('用途（人物／场景／道具／构图）',exact=True).fill('人物身份')
            assist.get_by_label('必须保持的特征（每行一项）',exact=True).fill('脸型\n夹克颜色')
            assist.get_by_label('资产 ID／明确版本',exact=True).fill('C01-v1')
            assist.get_by_label('来源任务 ID 或内容哈希',exact=True).fill('fixture-reference-task')
            assist.get_by_label('起始状态',exact=True).fill('坐姿')
            assist.get_by_label('结束状态',exact=True).fill('坐姿')
            assist.get_by_role('button',name='添加道具状态',exact=True).click()
            assist.get_by_label('资产 ID（例如 P01-v1）',exact=True).fill('P01-v1')
            assist.get_by_label('数量（空白表示未知）',exact=True).nth(0).fill('1')
            assist.get_by_label('数量（空白表示未知）',exact=True).nth(1).fill('1')
            assist.get_by_label('持有人／持有手',exact=True).nth(0).fill('C01-v1/右手')
            assist.get_by_label('持有人／持有手',exact=True).nth(1).fill('C01-v1/右手')
            assist.get_by_label('可见性',exact=True).nth(1).select_option('offscreen')
            # Unsaved helper edits cannot be approved through the existing approval button.
            first.locator('[data-approve]').click();page.get_by_role('status').filter(has_text='请先保存').wait_for()
            assert server.read()==original
            first.locator('[data-shot-save]').click()
            page.get_by_role('status').filter(has_text='已保存到本机').wait_for()
            saved=server.read();assert saved['workflow']['approved_count']==3
            assert saved['shots'][0]['creative_details']['camera']=={'movement':'locked'}
            assert saved['shots'][0]['creative_details']['reference_bindings'][0]['url']=='https://example.com/reference.png'
            assert saved['shots'][0]['image_prompt']==original['shots'][0].get('image_prompt',original['shots'][0]['prompt'])
            assert saved['shots'][0]['prompt']==original['shots'][0]['prompt']
            page.reload();page.locator('.storyboard-assist').first.wait_for(state='attached')
            first=page.locator('.shot-details').nth(0);first.locator('> summary').click()
            assist=first.locator('.storyboard-assist');assist.locator('> summary').click()
            assert assist.get_by_label('用途（人物／场景／道具／构图）',exact=True).input_value()=='人物身份'
            assert assist.get_by_label('可见性',exact=True).nth(1).input_value()=='offscreen'
            # A contradictory next start is visible and can be focused across cards.
            second=page.locator('.shot-details').nth(1);second.locator('> summary').click()
            second.locator('.storyboard-assist > summary').click()
            second.get_by_label('起始状态',exact=True).fill('站姿')
            second.get_by_role('button',name='检查当前分镜草稿').click()
            assert '上镜结束「坐姿」；本镜开始「站姿」' in second.locator('.assist-report').inner_text()
            for width,height in [(375,812),(812,375),(1440,1000)]:
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.set_viewport_size({'width':1100,'height':1100})
            screenshot=os.environ.get('STORYBOARD_TEST_SCREENSHOT')
            if screenshot:
                assist.scroll_into_view_if_needed();page.screenshot(path=screenshot)
            # Switching projects must not leak an unsaved assistant draft.
            second.get_by_label('触发事件（可空）',exact=True).fill('UNSAVED-PROJECT-A')
            new_project(page,'辅助编辑隔离项目')
            page.wait_for_function("document.querySelector('.current-project')?.textContent.includes('辅助编辑隔离项目')")
            page.get_by_role('link',name='04 分镜工作台',exact=True).click();page.get_by_role('button',name='＋ 添加镜头',exact=True).click();page.goto(f'http://127.0.0.1:{http.server_port}/#diagnostics')
            page.locator('.storyboard-assist').wait_for(state='attached')
            assert 'UNSAVED-PROJECT-A' not in page.content()
            assert not server.read()['shots'][0].get('creative_details')
            switch_project(page,1,'diagnostics')
            page.wait_for_function('document.querySelectorAll(".shot-details").length===4')
            assert server.read()['shots'][0]['creative_details']==saved['shots'][0]['creative_details']
            assert 'action_chain' not in server.read()['shots'][1].get('creative_details',{})
            assert not submits,submits;assert not errors,errors
            browser.close()
            print('PASS: integrated optional editor, keyboard focus links, preflight leaves approvals/SQLite unchanged, explicit save/reload, static/video separation, project isolation, mobile/landscape, zero submit')
    finally:
        http.shutdown();http.server_close()
