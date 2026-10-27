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
