"""Public story UI vs explicit diagnostics; temp DB, no external calls or submit."""
import base64
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
    s=server.read();s.update(title='故事审阅测试项目',script='她发现了一张来自明天的登记卡。',continuity='INTERNAL-CONTINUITY-ONLY',project_brief='INTERNAL-IP-RULES-ONLY')
    s['settings']['workflow']='INTERNAL-WORKFLOW-ONLY'
    folder=root/'assets'/'1';folder.mkdir(parents=True)
    for i,shot in enumerate(s['shots']):
        (folder/f'img{i}.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG7kAAAAASUVORK5CYII='))
        shot.update(name=f'镜头 {i+1}',image_prompt='INTERNAL-IMAGE-PROMPT',prompt='INTERNAL-VIDEO-PROMPT',
                    reference_images=['https://example.com/reference.png'],storyboard_task_id=f'img{i}',
                    storyboard_local=f'/media/1/img{i}.png',storyboard_sha256=str(i)*64,approved=True,approved_image_task_id=f'img{i}')
        shot['creative_details']={'beat':'发现时间矛盾，情绪从疑惑变为警觉。','action':'INTERNAL-ACTION-INSTRUCTION',
            'action_chain':{'start':'坐姿','end':'坐姿'},'prop_states':[{'asset_id':'P01-v1','start':{'location':'托盘','count':1},'end':{'location':'托盘','count':1}}]}
    s['shots'][1]['creative_details']['prop_states'][0]['start']['location']='右手'
    for shot in s['shots']:shot['approval_snapshot']=workflow_state.record_approval(s,shot,'fixture human','time')
    s['tasks']=[{'id':'fixture-film','kind':'sequence','status':'completed','estimate':0,'local_video':'/media/1/fixture.mp4',
                 'approval_snapshot':[copy.deepcopy(x['approval_snapshot']) for x in s['shots']]}]
    s['final_video']={'task_id':'fixture-film','review_task_id':'fixture-film','review_status':'accepted_first_version'}
    server.save(s)
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
            def saved_click(button):
                with page.expect_response('**/api/save') as response:button.click()
                assert response.value.status==200
            errors=[];submits=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:submits.append(r.url) if '/submit' in r.url else None)
            page.goto(f'http://127.0.0.1:{http.server_port}/#shots')
            page.locator('.shot-details').first.wait_for(state='attached')
            baseline=copy.deepcopy(server.read());assert baseline['workflow']['code']=='COMPLETE'
            page.locator('.shot-details').nth(1).locator('> summary').click()
            assert page.locator('.storyboard-assist').count()==0
            assert page.locator('#provider-result,#ip0,#sp0,#refs0,#sf0,[data-path]').count()==0
            assert 'INTERNAL-' not in page.content()
            page.locator('[data-story-check="1"]').click()
            question=page.locator('[data-story-questions="1"]').inner_text()
            assert '拾取、放下、交接' in question
            assert all(key not in question for key in ['prop_states','P01-v1','location','hash','reference_bindings'])
            assert server.read()==baseline
            page.locator('#feedback1').fill('钥匙上一镜还在托盘，这里不应直接拿在手里。')
            saved_click(page.locator('[data-feedback-save="1"]'))
            page.get_by_role('status').filter(has_text='反馈已保存').wait_for()
            assert server.read()['workflow']['code']=='COMPLETE'
            assert server.read()['workflow']['approved_count']==4
            first=page.locator('.shot-details').first;first.locator('> summary').click()
            page.locator('#intent0').fill('她先疑惑，再意识到日期不对。')
            page.locator('[data-approve="0"]').click();page.get_by_role('status').filter(has_text='请先保存').wait_for()
            saved_click(page.locator('[data-shot-save="0"]'));page.get_by_role('status').filter(has_text='已保存到本机').wait_for()
            saved=server.read();assert saved['workflow']['approved_count']==3
            for key in ['prompt','image_prompt','reference_images','creative_details']:
                assert saved['shots'][0][key]==baseline['shots'][0][key],key
            page.reload();page.locator('.shot-details').first.wait_for(state='attached')
            page.locator('.shot-details').first.locator('> summary').click()
            assert page.locator('#intent0').input_value()=='她先疑惑，再意识到日期不对。'
            for width,height in [(375,812),(812,375),(1440,1000)]:
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            screenshot=os.environ.get('STORYBOARD_PUBLIC_SCREENSHOT')
            if screenshot:page.screenshot(path=screenshot)
            page.get_by_role('link',name='02 剧本',exact=True).click();page.locator('#script').wait_for()
            assert page.locator('#continuity,#brief').count()==0
            assert 'INTERNAL-' not in page.content()
            saved_click(page.get_by_role('button',name='保存剧本',exact=True))
            page.get_by_role('status').filter(has_text='已保存到本机').wait_for()
            assert server.read()['continuity']==baseline['continuity']
            assert server.read()['project_brief']==baseline['project_brief']
            assert server.read()['shots'][1]['approved'] is True
            page.locator('#script').fill('新的故事正文，来自普通用户。')
            saved_click(page.get_by_role('button',name='保存剧本',exact=True))
            page.get_by_role('status').filter(has_text='已保存到本机').wait_for()
            assert server.read()['script']=='新的故事正文，来自普通用户。'
            page.get_by_role('link',name='03 角色资产库',exact=True).click()
            page.locator('#ct0').fill('冷静的记者，短发，习惯先观察再行动。')
            saved_click(page.locator('[data-character="0"]'));page.get_by_role('status').filter(has_text='已保存到本机').wait_for()
            assert server.read()['characters'][0]['notes']=='冷静的记者，短发，习惯先观察再行动。'
            page.get_by_role('link',name='06 工具与设置',exact=True).click()
            page.locator('#provider-choice').wait_for()
            assert page.locator('#workflow,#url,#continuity,#provider-result').count()==0
            assert page.locator('#provider-key').input_value()==''
            assert 'INTERNAL-' not in page.content()
            current=copy.deepcopy(server.read())
            page.get_by_role('link',name='进入开发者诊断',exact=True).click()
            page.locator('#continuity').wait_for()
            assert page.locator('#continuity').input_value()==baseline['continuity']
            assert page.locator('#brief').input_value()==baseline['project_brief']
            assert page.locator('#workflow').input_value()=='INTERNAL-WORKFLOW-ONLY'
            assert page.locator('#ip0').input_value()=='INTERNAL-IMAGE-PROMPT'
            assert page.locator('#provider-result').count()==1
            assert page.locator('.storyboard-assist').count()==4
            assert server.read()==current, 'entering diagnostics must not migrate or save'
            page.get_by_role('link',name='返回分镜',exact=True).click()
            page.locator('#intent0').wait_for(state='attached')
            assert page.locator('[data-path],#workflow,#ip0,#continuity,#provider-result').count()==0
            page.get_by_role('button',name='＋ 新建项目',exact=True).click()
            page.get_by_label('项目名称',exact=True).fill('独立故事 B')
            page.get_by_role('button',name='创建项目',exact=True).click()
            page.wait_for_function("document.querySelector('#project-select option:checked')?.textContent.includes('独立故事 B')")
            page.get_by_role('link',name='04 分镜工作台',exact=True).click()
            page.get_by_role('button',name='＋ 添加镜头',exact=True).click()
            page.locator('#intent0').wait_for(state='attached')
            assert page.locator('#intent0').input_value()==''
            assert server.read()['continuity']==''
            assert not submits,submits;assert not errors,errors
            browser.close();print('PASS: public vs diagnostic separation, hidden data preserved, natural feedback/check no approval changes, intent edit expires only changed shot, script/character edits, reload/project isolation, keyboard/mobile, zero submit')
    finally:http.shutdown();http.server_close()
