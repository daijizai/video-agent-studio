"""Project steps show only future project changes and accept retrospective notes."""
import json,os,shutil,sys,tempfile,threading
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
    base=f'http://127.0.0.1:{http.server_port}';page.goto(base+'/#tools');page.get_by_role('heading',name='操作步骤').wait_for();page.get_by_text('创建项目',exact=True).wait_for()
    state=page.request.get(base+'/api/state').json();res=page.request.post(base+'/api/save',data={'project_id':state['project_id'],'revision':state['revision'],'script':'用于测试的剧本'});assert res.ok
    page.get_by_role('button',name='刷新记录').click();page.get_by_text('剧本已更新',exact=True).wait_for();page.get_by_text('保存项目内容',exact=True).wait_for()
    page.get_by_label('补充复盘信息').fill('用中景展示角色关系');page.get_by_role('button',name='保存补充').click();page.get_by_text('用中景展示角色关系',exact=True).wait_for()
    assert not errors,errors;browser.close()
   print('PASS: automatic steps, project changes and retrospective notes')
  finally:http.shutdown();http.server_close()
