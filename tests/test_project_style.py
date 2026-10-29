import base64, copy, hashlib, unittest
from unittest.mock import Mock
from test_asset_library import AssetFixture,png
import asset_generation
import asset_library
import image_provider
import seedream_edit

class ProjectStyleTests(AssetFixture):
    def test_detailed_style_is_preserved_and_bound_to_skill(self):
        folder=self.root/'skills'/'frame-visual-style';(folder/'templates').mkdir(parents=True)
        skill=folder/'SKILL.md';skill.write_text('test skill')
        template=folder/'templates'/'style-bible.md';template.write_text('test template')
        source={'skill_id':'frame-visual-style','skill_version':'1.0.0','skill_sha256':hashlib.sha256(skill.read_bytes()).hexdigest(),'template_sha256':hashlib.sha256(template.read_bytes()).hexdigest()}
        detail='冷白光与低饱和工业摄影质感。'*80
        c=self.action('style',description='冷白工业风',style_prompt=detail,style_source=source,reference_action='upload',filename='style.png',base64=base64.b64encode(png()).decode())
        style=c['project_style'];self.assertEqual(style['prompt'],detail);self.assertEqual(style['source'],source)
        asset=self.create();service=asset_generation.AssetGeneration(self.service)
        job=service._job(self.state(),{'asset_id':asset['id'],'version':asset['latest_version'],'view_tag':'main'},'qwen-image-3.0-pro')
        self.assertIn(detail,job['request']['input']['messages'][0]['content'][-1]['text'])
        self.assertEqual(job['estimate'],.27)
        preview=service.preview(1,[{'asset_id':asset['id'],'version':asset['latest_version'],'view_tag':'main'}],'doubao-seedream-5-0-flash-260915')
        self.assertIn('官方建议',preview['note'])
        updated=self.action('style',description='改为暖光',reference_action='keep')['project_style']
        self.assertEqual(updated['prompt'],'');self.assertEqual(updated['source'],{})
    def test_repair_keeps_source_and_style_roles_separate(self):
        data=png();info=seedream_edit.png_info(data)
        result=seedream_edit.payload_for(data,info,{'x':5,'y':5,'width':50,'height':60},'修复按钮',{'description':'冷白电影光'},data,'image/png')
        self.assertEqual(len(result['image']),2)
        self.assertIn('编辑图 1',result['prompt']);self.assertIn('图2仅参考',result['prompt'])
        self.assertIn('冷白电影光',result['prompt'])
    def test_style_is_project_scoped_versioned_and_not_a_generation(self):
        before=copy.deepcopy(self.state())
        payload=base64.b64encode(png()).decode()
        c=self.action('style',description='冷白工业电影光',reference_action='upload',filename='style.png',base64=payload)
        first=c['project_style'];self.assertEqual(first['version'],1)
        data,info=self.service.media(1,first['reference']['url']);self.assertEqual(data,png())
        self.assertEqual(self.state(2).get('project_style'),None)
        self.assertEqual(self.state()['image_tasks'],before['image_tasks'])
        c=self.action('style',description='低饱和冷光',reference_action='keep')
        self.assertEqual(c['project_style']['version'],2)
        self.assertEqual(c['project_style']['reference']['sha256'],first['reference']['sha256'])
        self.assertEqual(len(self.state()['project_style_history']),2)
        with self.assertRaises(ValueError):self.action('style',description='x',reference_action='upload',filename='x.png',base64='%%%')

    def test_style_is_in_asset_request_and_hydrates_separately(self):
        asset=self.create();self.action('style',description='克制电影光',reference_action='upload',filename='style.png',base64=base64.b64encode(png()).decode())
        service=asset_generation.AssetGeneration(self.service)
        state=self.state();item={'asset_id':asset['id'],'version':asset['latest_version'],'view_tag':'main'}
        job=service._job(state,item,'doubao-seedream-5-0-flash-260915')
        self.assertIn('克制电影光',job['request']['prompt'])
        self.assertIn('仅参考色彩、光线和画面质感',job['request']['prompt'])
        self.assertTrue(job['request']['image'][-1].startswith('style:sha256:'))
        self.assertEqual(job['reference_inputs'],[])
        hydrated=service._hydrate(1,job)
        self.assertTrue(hydrated['payload']['image'][-1].startswith('data:image/png;base64,'))
        self.assertEqual(job['estimate'],.12)
        self.assertEqual(job['production_contract']['project_style']['version'],1)
        self.action('style',description='改为暖光',reference_action='keep')
        with self.assertRaisesRegex(ValueError,'风格已变化'):service._validate_reserved_contract(self.state(),job)

    def test_storyboard_receives_style_without_overwriting_history(self):
        self.action('style',description='冷色调',reference_action='upload',filename='style.png',base64=base64.b64encode(png()).decode())
        shot={'prompt':'角色抬头','image_prompt':'人物坐在桌边','_material_project_id':1}
        prepared=asset_generation.prepare_storyboard(self.service,shot,{'image_model':'doubao-seedream-5-0-flash-260915'})
        self.assertIn('冷色调',prepared['payload']['prompt'])
        self.assertTrue(prepared['payload']['image'][-1].startswith('data:image/png;base64,'))
        self.assertIn('sha256:',prepared['request_manifest']['image'][-1])
        self.assertEqual(prepared['style_snapshot']['version'],1)
        self.assertEqual(self.state()['image_tasks'],[])

    def test_extending_view_recipes_preserves_existing_candidates(self):
        asset=self.create();profile=copy.deepcopy(asset_library._version(asset)['design_profile']);back=profile['view_recipes'].pop('back')
        asset=self.action('design',asset_id=asset['id'],profile=profile)['assets'][-1];asset=self.upload(asset)
        v=asset_library._version(asset);old_views=copy.deepcopy(v['views']);profile=copy.deepcopy(v['design_profile'])
        profile['view_recipes']['back']=back
        extended=self.action('design',asset_id=asset['id'],profile=profile)['assets'][-1]
        self.assertEqual(asset_library._version(extended)['views'],old_views)
        self.assertIsNone(extended['adopted_version'])
        selected=self.action('style',description='参考风格',reference_action='select',view_id=old_views[0]['id'])
        self.assertEqual(selected['project_style']['reference']['sha256'],old_views[0]['sha256'])
        v=asset_library._version(extended);profile=copy.deepcopy(v['design_profile'])
        profile['view_recipes']['back']['prompt']+=' added different recipe'
        # Changing an already declared recipe is not a pure extension.
        changed=self.action('design',asset_id=asset['id'],profile=profile)
        newest=next(a for a in changed['assets'] if a['id']==asset['id'])
        self.assertEqual(asset_library._version(newest)['views'],[])
        self.assertEqual(asset_library._version(newest,v['version'])['views'],old_views)
