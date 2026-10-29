import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import workflow_state as w
class WorkflowFacts(unittest.TestCase):
 def state(self):
  return {'revision':1,'script':'story','characters':[{'id':'c','version':1,'notes':'fixed'}],'continuity':'fixed room','shots':[{'id':str(i),'name':'shot'+str(i),'duration':5,'frame':'medium','prompt':'video','image_prompt':'static','storyboard_task_id':'img'+str(i),'storyboard_local':'/media/1/img'+str(i)+'.png','storyboard_sha256':str(i)*64,'approved':False} for i in range(2)],'tasks':[],'image_tasks':[]}
 def approve(self,s):
  for shot in s['shots']:shot['approval_snapshot']=w.record_approval(s,shot,'test human','time');shot['approved_image_task_id']=shot['storyboard_task_id'];shot['approved']=True
 def video(self,s,status):return {'id':'video','kind':'sequence','provider':'wan3-prime','status':status,'approval_snapshot':[copy.deepcopy(x['approval_snapshot']) for x in s['shots']]}
 def test_preparation_and_images_are_not_video(self):
  s=self.state();s['script']='';self.assertEqual(w.derive(s)['code'],'PREPARATION');s['script']='story';s['image_tasks']=[{'status':'completed'}];self.assertEqual(w.derive(s)['code'],'STORYBOARD_REVIEW')
 def test_approved_without_real_submit_stays_ready(self):
  s=self.state();self.approve(s);s['last_error']='budget rejected';self.assertEqual(w.derive(s)['code'],'VIDEO_READY');s['image_tasks']=[{'status':'running'}];self.assertEqual(w.derive(s)['code'],'VIDEO_READY')
 def test_real_statuses_failure_retry(self):
  s=self.state();self.approve(s)
  for status,code in [('submitting','VIDEO_SUBMITTING'),('queued','VIDEO_GENERATING'),('running','VIDEO_GENERATING'),('failed','VIDEO_ATTENTION'),('unknown','VIDEO_ATTENTION')]:s['tasks']=[self.video(s,status)];self.assertEqual(w.derive(s)['code'],code)
  s['tasks']=[self.video(s,'failed'),{**self.video(s,'queued'),'id':'retry'}];self.assertEqual(w.derive(s)['current_video_task_id'],'retry');self.assertEqual(w.derive(s)['code'],'VIDEO_GENERATING')
 def test_completed_is_not_quality_pass_but_user_acceptance_is(self):
  s=self.state();self.approve(s);s['tasks']=[{**self.video(s,'completed'),'local_video':'/media/1/video.mp4'}];s['final_video']={'task_id':'video','review_status':'pending'};self.assertEqual(w.derive(s)['code'],'VIDEO_REVIEW');self.assertFalse(w.derive(s)['final_quality_approved'])
  s['final_video'].update(review_status='accepted_first_version',review_task_id='video');s['generation_pause']={'paused':True};r=w.derive(s);self.assertEqual(r['code'],'COMPLETE');self.assertIn('阶段性',r['label']);self.assertIn('不等于',r['next_action'])
 def test_edits_expire_approval_and_old_video_does_not_match_new(self):
  s=self.state();self.approve(s);s['tasks']=[{**self.video(s,'completed'),'local_video':'/media/1/video.mp4'}];s['shots'][0]['frame']='new framing';self.assertEqual(w.derive(s)['code'],'STORYBOARD_REVIEW');self.assertEqual(w.derive(s)['approved_count'],1)
  self.approve(s);self.assertEqual(w.derive(s)['code'],'VIDEO_READY');s['characters'][0]['notes']='changed';self.assertEqual(w.derive(s)['approved_count'],0)
 def test_budget_or_default_model_does_not_grant_or_invalidate_quality(self):
  s=self.state();s['settings']={'provider':'wan3-prime'};self.assertEqual(w.derive(s)['approved_count'],0);self.approve(s);s['settings']['provider']='wan3';s['budget_authorizations']=[{'version':2}];self.assertEqual(w.derive(s)['approved_count'],2)

 def test_material_stage_is_between_story_and_storyboard(self):
  s=self.state()
  for shot in s['shots']:shot.pop('storyboard_local',None)
  before=copy.deepcopy(s);result=w.derive(s)
  self.assertEqual(s,before)
  self.assertEqual(result['code'],'MATERIAL_PREPARATION')
  self.assertEqual([x['key'] for x in result['steps']],['story','materials','storyboard','generation','review'])
  step=result['steps'][1];self.assertTrue(step['active']);self.assertFalse(step['complete']);self.assertEqual(step['href'],'#characters')
  self.assertEqual(result['materials'],{'ready':0,'total':1,'complete':False})
 def test_legacy_video_progress_does_not_invent_adopted_materials(self):
  s=self.state();self.approve(s);result=w.derive(s)
  self.assertEqual(result['code'],'VIDEO_READY')
  self.assertFalse(result['steps'][1]['complete'])
