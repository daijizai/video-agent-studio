import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
import creative_resources,video_segments

ROOT=Path(__file__).resolve().parents[1]

class CreativeResourceTests(unittest.TestCase):
 def test_catalog_has_three_kinds_and_no_duplicates(self):
  c=creative_resources.catalog(ROOT)
  self.assertEqual({x['kind'] for x in c['items']},{'size','composition','movement'})
  self.assertIn('movement-dolly-zoom',{x['id'] for x in c['items']})
  self.assertIn('movement-orbit',{x['id'] for x in c['items']})
  self.assertEqual(len({x['id'] for x in c['items']}),len(c['items']))
 def test_choices_are_shared_across_projects_and_saved_as_snapshots(self):
  server=Mock();server.ROOT=ROOT
  ids=['size-medium','composition-thirds','movement-orbit']
  refs=[]
  for pid in (1,2):
   seg={'id':'s','name':'x','draft_revision':1,'material_video_approval':{'fingerprint':'old'}}
   state={'project_id':pid,'video_segments':[seg],'tasks':[]}
   video_segments.operate(server,state,'save-segment',{'segment_id':'s','draft':{'shot_language_ids':ids}})
   refs.append(seg['shot_language']);self.assertNotIn('material_video_approval',seg)
  self.assertEqual(refs[0],refs[1]);self.assertEqual([x['id'] for x in refs[0]],ids)
 def test_prior_snapshot_survives_catalog_update(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'resources').mkdir();path=root/'resources'/'shot-language.json';doc=json.loads((ROOT/'resources'/'shot-language.json').read_text());path.write_text(json.dumps(doc))
   before=creative_resources.resolve(root,['movement-orbit'])
   doc['version']=2;next(x for x in doc['items'] if x['id']=='movement-orbit')['instruction']='新版环绕说明';path.write_text(json.dumps(doc))
   self.assertEqual(creative_resources.resolve(root,['movement-orbit'],before),before)
   self.assertEqual(creative_resources.resolve(root,['movement-orbit'])[0]['instruction'],'新版环绕说明')
 def test_reject_duplicate_categories_and_unknown_items(self):
  with self.assertRaises(ValueError):creative_resources.resolve(ROOT,['size-medium','size-full'])
  with self.assertRaises(ValueError):creative_resources.resolve(ROOT,['missing'])
 def test_empty_choice_does_not_invalidate_existing_approval(self):
  server=Mock();server.ROOT=ROOT;seg={'id':'s','material_video_approval':{'fingerprint':'ok'}}
  state={'project_id':1,'video_segments':[seg],'tasks':[]}
  video_segments.operate(server,state,'save-segment',{'segment_id':'s','draft':{'shot_language_ids':[]}})
  self.assertIn('material_video_approval',seg)

if __name__=='__main__':unittest.main()
