"""Manual/browser fixture: real public review UI + mock ComfyUI, never real media generation.
Run from repo root; Ctrl-C removes the temporary database and both random-port servers.
"""
import shutil
import sys
import threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_comfy_http import RepairHTTPTests
import server

if __name__=='__main__':
    source=Path(__file__).resolve().parents[1]
    fixture=RepairHTTPTests('test_public_routes_full_flow_and_image_dispatch')
    fixture.setUp()
    try:
        shutil.copytree(source/'static',fixture.root/'static')
        state=server.read();state.update(title='隔离测试：局部修复（模拟执行）',episode='TEST',demo=False,target_duration=5,settings={'provider':'wan3-prime','image_model':'qwen-image-3.0-pro','comfy_url':'','workflow':''},events=[])
        server.save(state)
        with fixture.service.transaction() as con:
            other=fixture.service.state(con,2);other['title']='隔离备用项目';fixture.service.save(con,other)
        scope={'1':{'id':'fixture','database':str(fixture.database),'models':['comfy-masked-repair-sd15-v1'],'budget_mode':'separate_v1','budget_grants':{'image':{'id':'test-image','limit':1},'video':{'id':'test-video','limit':0}},'paused':False}}
        fixture.finished=True
        with patch.object(server.generation_scope,'read',return_value=scope):
            print(fixture.host_url+'/#shots',flush=True)
            threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:fixture.tearDown()
