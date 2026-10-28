"""Real review UI against mock Seedream routes. No real API, temporary data only."""
import shutil
import sys
import threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_seedream_edit_http import SeedreamEditHTTPTests
import seedream_edit
import server

if __name__=='__main__':
    source=Path(__file__).resolve().parents[1]
    fixture=SeedreamEditHTTPTests('test_default_http_flow_preflight_and_candidate_adoption');fixture.setUp()
    try:
        shutil.copytree(source/'static',fixture.root/'static')
        state=server.read();state.update(title='隔离验收：Seedream编辑（模拟）',episode='TEST',demo=False,target_duration=5,settings={'provider':'wan3-prime','image_model':seedream_edit.MODEL,'comfy_url':'','workflow':''},events=[])
        server.save(state)
        with fixture.service.transaction() as con:
            other=fixture.service.state(con,2);other['title']='隔离备用项目';fixture.service.save(con,other)
        scope={'1':{'id':'scope','database':str(fixture.database.resolve()),'models':[seedream_edit.MODEL],'budget_mode':'separate_v1','budget_grants':{'image':{'id':'finite-image-grant','limit':.12},'video':{'id':'video','limit':0}},'paused':False}}
        with patch.object(server.generation_scope,'read',return_value=scope):
            print(fixture.url+'/#shots',flush=True);threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:fixture.tearDown()
