"""Project step journal starts now, isolates projects and stores state writes transactionally."""
import json,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import project_steps

class ProjectStepsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite';self.c=sqlite3.connect(self.path);self.c.row_factory=sqlite3.Row
  self.c.execute('CREATE TABLE state(id INTEGER PRIMARY KEY, body TEXT)')
  self.c.execute('INSERT INTO state VALUES(1,?)',(json.dumps({'title':'旧项目','script':'早期剧本'}),))
  project_steps.install(self.c);self.c.commit()
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def change(self,pid,body):self.c.execute('UPDATE state SET body=? WHERE id=?',(json.dumps(body,ensure_ascii=False),pid));self.c.commit()
 def test_future_only_and_all_project_writes(self):
  self.assertEqual(project_steps.list_steps(self.c,1)['steps'],[])
  self.change(1,{'title':'旧项目','script':'新剧本','tasks':[]})
  self.change(1,{'title':'旧项目','script':'新剧本','tasks':[{'id':'x','name':'第一段','status':'queued'}]})
  steps=project_steps.list_steps(self.c,1)['steps'];self.assertEqual(len(steps),2);self.assertIn('第一段：新增任务 · 排队中',steps[0]['details']);self.assertIn('剧本已更新',steps[1]['details'])
  self.c.execute('INSERT INTO state VALUES(2,?)',(json.dumps({'title':'新项目'}),));self.c.commit();self.assertEqual(project_steps.list_steps(self.c,2)['steps'][0]['title'],'创建项目')
  self.assertEqual(len(project_steps.list_steps(self.c,1)['steps']),2)
 def test_notes_pagination_noop_and_rollback(self):
  project_steps.add_note(self.c,1,'选择原因');self.c.commit();self.change(1,{'title':'旧项目','script':'新内容'})
  self.change(1,{'title':'旧项目','script':'新内容'});first=project_steps.list_steps(self.c,1,limit=1);self.assertIsNotNone(first['next_before']);second=project_steps.list_steps(self.c,1,before=first['next_before'],limit=1);self.assertEqual(second['steps'][0]['details'],['选择原因'])
  self.c.execute('UPDATE state SET body=? WHERE id=1',(json.dumps({'title':'将回滚'}),));self.c.rollback();self.assertEqual(len(project_steps.list_steps(self.c,1)['steps']),2)
  with self.assertRaises(ValueError):project_steps.add_note(self.c,1,'  ')
if __name__=='__main__':unittest.main()
