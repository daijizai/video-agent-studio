import copy
import unittest
from unittest.mock import Mock
from test_asset_library import AssetFixture
import video_segments


class CleanupTests(AssetFixture):
    def test_delete_requires_current_name_and_preserves_other_assets_and_media(self):
        asset=self.upload(self.create())
        other=self.create(name='保留')
        url=asset['versions'][-1]['views'][0]['url']
        file=self.root/'assets'/'1'/'library'/url.rsplit('/',1)[-1]
        with self.assertRaisesRegex(ValueError,'名称不匹配'):
            self.action('delete',asset_id=asset['id'],name='错误')
        self.action('delete',asset_id=asset['id'],name='钥匙')
        ids=[a['id'] for a in self.service.catalog(1)['assets']]
        self.assertNotIn(asset['id'],ids);self.assertIn(other['id'],ids)
        self.assertTrue(file.exists())

    def test_delete_rejects_current_segment_binding(self):
        asset=self.create();state=self.state()
        state['video_segments']=[{'asset_references':[{'asset_id':asset['id']}]}]
        with self.assertRaisesRegex(ValueError,'仍被镜头引用'):
            self.service._mutate(state,'delete',{'asset_id':asset['id'],'name':'钥匙'},[])

    def test_remove_only_unapproved_opening_and_clear_selected_input(self):
        host=Mock();state={'video_segments':[{'id':'seg','opening_frames':[{'id':'old','status':'candidate'},{'id':'keep','status':'approved'}],
            'opening_frame_id':'old','video_input_mode':'first_frame','material_video_approval':{'old':True}}]}
        before=copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError,'只能移除'):
            video_segments.operate(host,state,'remove-opening-candidate',{'segment_id':'seg','frame_id':'keep'})
        self.assertEqual(state,before)
        video_segments.operate(host,state,'remove-opening-candidate',{'segment_id':'seg','frame_id':'old'})
        seg=state['video_segments'][0]
        self.assertEqual([f['id'] for f in seg['opening_frames']],['keep'])
        self.assertEqual(seg['video_input_mode'],'references')
        self.assertNotIn('opening_frame_id',seg);self.assertNotIn('material_video_approval',seg)


if __name__=='__main__':unittest.main()
