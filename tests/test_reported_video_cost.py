import unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch
import generation_scope

class ReportedVideoCostTests(unittest.TestCase):
 def test_video_limit_disabled_preserves_image_limit_and_unknown_task(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';p=Path(tmp)/'auth.json'
   p.write_text(json.dumps({'4':{'database':str(db.resolve()),'budget_mode':'separate_v1','models':['video','image'],'budget_grants':{'image':{'id':'i','limit':20},'video':{'id':'v','limit':100}}}}))
   state={'project_id':4,'tasks':[{'status':'unknown','estimate':120}],'image_tasks':[]}
   with patch.object(generation_scope,'path',return_value=p):
    with self.assertRaisesRegex(ValueError,'视频独立预算不足'):generation_scope.check(state,db,'video',1,'video')
    generation_scope.disable_video_limit(4,db,'用户要求忽略视频预算',1)
    self.assertEqual(generation_scope.check(state,db,'video',50,'video'),'v')
    self.assertIsNone(generation_scope.budget_summary(state,db)['video']['limit_cny'])
    self.assertEqual(generation_scope.budget_summary(state,db)['video']['committed_cny'],120)
    with self.assertRaisesRegex(ValueError,'图片独立预算不足'):generation_scope.check(state,db,'image',21,'image')
    self.assertEqual(generation_scope.read()['4']['budget_override_history'][0]['previous_limit'],100)
 def test_reported_original_used_for_completed_reservation_but_not_marked_actual(self):
  state={'tasks':[{'status':'completed','estimate':10.59,'actual_cost_cny':None,'reported_original_cny':3.141,'reported_original_source':'user supplied bill original'}]}
  ledger=generation_scope.category_ledger(state,'video',100)
  self.assertEqual(ledger['committed_cny'],3.141);self.assertEqual(ledger['actual_known_cny'],0)
  self.assertEqual(ledger['actual_unknown_tasks'],1);self.assertIsNone(ledger['actual_total_cny'])
 def test_unknown_request_cannot_be_cleared_by_a_reported_amount(self):
  state={'tasks':[{'status':'unknown','estimate':25.71,'reported_original_cny':0,'reported_original_source':'user'}]}
  self.assertEqual(generation_scope.category_ledger(state,'video',100)['committed_cny'],25.71)
 def test_screenshot_amount_updates_completed_estimate_without_claiming_settlement(self):
  state={'tasks':[{'status':'completed','estimate':30,'actual_cost_cny':None,'screenshot_cost':{'amount_cny':'12.3400','source':'用户提供的截图','matching':'按用量推算金额匹配，未核对订单编号'}},
                  {'status':'unknown','estimate':4,'screenshot_cost':{'amount_cny':'0','source':'用户提供的截图','matching':'按用量推算金额匹配，未核对订单编号'}}]}
  ledger=generation_scope.category_ledger(state,'video',100)
  self.assertEqual(ledger['committed_cny'],16.34);self.assertIsNone(ledger['actual_total_cny']);self.assertEqual(ledger['actual_unknown_tasks'],2)
 def test_unsourced_amount_cannot_reduce_budget(self):
  state={'tasks':[{'status':'completed','estimate':10.59,'reported_original_cny':1}]}
  self.assertEqual(generation_scope.category_ledger(state,'video',100)['committed_cny'],10.59)
if __name__=='__main__':unittest.main()
