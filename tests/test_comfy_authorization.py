import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import generation_scope
from comfy_templates import MODEL_SCOPE

class LocalRepairAuthorizationTests(unittest.TestCase):
    def test_explicit_count_is_required_consumed_and_does_not_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);database=root/'studio.db';authorization=root/'scope.json'
            state={'project_id':1,'image_tasks':[],'tasks':[],'budget':0}
            with sqlite3.connect(database) as con:
                con.execute('CREATE TABLE state (id INTEGER PRIMARY KEY,body TEXT)')
                con.execute('INSERT INTO state VALUES (1,?)',(json.dumps(state),))
            authorization.write_text(json.dumps({'1':{'id':'scope','database':str(database.resolve()),'paused':True,'models':[]}}))
            with patch.object(generation_scope,'path',return_value=authorization):
                with self.assertRaisesRegex(ValueError,'次数'):generation_scope.authorize_budgets(1,database,0,0,'test human',0,models=[MODEL_SCOPE])
                generation_scope.authorize_budgets(1,database,0,0,'test human one repair',0,models=[MODEL_SCOPE],local_repair_limit=1)
                scope=generation_scope.read();self.assertTrue(scope['1']['paused'])
                self.assertEqual(scope['1']['local_repair_grant']['limit'],1)
                with self.assertRaises(ValueError):generation_scope.check(state,database,'image',0,MODEL_SCOPE)
                scope['1']['paused']=False;authorization.write_text(json.dumps(scope))
                self.assertTrue(generation_scope.check(state,database,'image',0,MODEL_SCOPE))
                state['image_tasks'].append({'id':'used','provider':'comfy-masked-repair','estimate':0,'actual_cost_cny':0,'status':'completed'})
                with self.assertRaisesRegex(ValueError,'次数'):generation_scope.check(state,database,'image',0,MODEL_SCOPE)
                for invalid in (0,-1,True,101,1.5):
                    with self.assertRaises(ValueError):generation_scope.authorize_budgets(1,database,0,0,'test',0,local_repair_limit=invalid)
