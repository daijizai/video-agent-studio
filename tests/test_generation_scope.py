import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import generation_scope
class FiniteScopeTests(unittest.TestCase):
 def test_scope_bound_to_project_database_budget_and_counts(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(Path(tmp)/'private'/'credentials.json')}):
   database=Path(tmp)/'db.sqlite';generation_scope.grant(2,database,11,6,1)
   self.assertTrue(generation_scope.active(2,database));self.assertFalse(generation_scope.active(1,database));self.assertFalse(generation_scope.active(2,Path(tmp)/'other.sqlite'))
   s={'project_id':2,'budget':11,'image_tasks':[],'tasks':[]}
   self.assertTrue(generation_scope.check(s,database,'image',.18,'qwen-image-3.0'))
   with self.assertRaises(ValueError):generation_scope.check(s,database,'video',12,'wan3.0-video')
   with self.assertRaises(ValueError):generation_scope.check(s,database,'video',1,'unapproved-model')
   s['image_tasks']=[{'estimate':.18,'status':'unknown'}]*6
   with self.assertRaises(ValueError):generation_scope.check(s,database,'image',.18,'qwen-image-3.0')
   with self.assertRaises(ValueError):generation_scope.grant(2,database,99,99,99)
 def test_named_extension_only_once_and_same_total_budget(self):
  import sqlite3,json
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(Path(tmp)/'private'/'credentials.json')}):
   database=Path(tmp)/'db.sqlite';rows=[{'id':'t'+str(i),'shot_id':'s'+str(i),'estimate':.2,'status':'completed'} for i in range(6)];s={'project_id':2,'budget':11,'shots':[{'id':'s'+str(i)} for i in range(6)],'image_tasks':rows,'tasks':[]}
   with sqlite3.connect(database) as c:c.execute('CREATE TABLE state(id INTEGER,body TEXT)');c.execute('INSERT INTO state VALUES (2,?)',(json.dumps(s),))
   generation_scope.grant(2,database,11,6,0)
   generation_scope.extend_images(2,database,['s0','s1','s4'],.6,'explicit human approval')
   self.assertTrue(generation_scope.check(s,database,'image',.2,'qwen-image-3.0',shot_id='s0'))
   with self.assertRaises(ValueError):generation_scope.check(s,database,'image',.2,'qwen-image-3.0',shot_id='s3')
   s['image_tasks'].append({'id':'redo0','shot_id':'s0','estimate':.2,'status':'unknown'})
   with self.assertRaises(ValueError):generation_scope.check(s,database,'image',.2,'qwen-image-3.0',shot_id='s0')
   with self.assertRaises(ValueError):generation_scope.extend_images(2,database,['s0'],.2,'duplicate approval')
   self.assertEqual(generation_scope.read()['2']['max_cny'],11);self.assertEqual(generation_scope.read()['2']['video_limit'],0)
 def test_independent_budget_no_count_gate_no_borrow_and_unknown_not_zero(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(Path(tmp)/'private'/'credentials.json')}):
   database=Path(tmp)/'db.sqlite';generation_scope.authorize_budgets(2,database,3,7,'explicit separate budgets',8)
   s={'project_id':2,'budget':1,'image_tasks':[{'id':str(i),'shot_id':'s','status':'completed','estimate':.2,'actual_cost_cny':None} for i in range(8)],'tasks':[{'id':'v','status':'unknown','estimate':6,'actual_cost_cny':None}]}
   summary=generation_scope.budget_summary(s,database);self.assertEqual(summary['image']['remaining_cny'],1.4);self.assertIsNone(summary['image']['actual_total_cny']);self.assertEqual(summary['image']['actual_unknown_tasks'],8)
   self.assertTrue(generation_scope.check(s,database,'image',.22,'qwen-image-3.0',shot_id='new-shot'))
   with self.assertRaises(ValueError):generation_scope.check(s,database,'image',1.5,'qwen-image-3.0')
   with self.assertRaises(ValueError):generation_scope.check(s,database,'video',2,'wan3.0-video')
   self.assertFalse(generation_scope.active(1,database));self.assertEqual(summary['image']['authorization']['content_revision'],8)
 def test_unknown_bill_and_live_partial_are_conservative(self):
  s={'image_tasks':[{'status':'completed','estimate':.2,'actual_cost_cny':None},{'status':'unknown','estimate':.3,'actual_cost_cny':None},{'status':'completed','estimate':.2,'actual_cost_cny':.1},{'status':'rejected','estimate':.2}],'tasks':[]}
  r=generation_scope.category_ledger(s,'image',1);self.assertEqual(r['committed_cny'],.6);self.assertEqual(r['remaining_cny'],.4);self.assertEqual(r['actual_known_cny'],.1);self.assertIsNone(r['actual_total_cny']);self.assertEqual(r['actual_unknown_tasks'],2)
