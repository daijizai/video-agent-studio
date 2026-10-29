"""Thin runtime contracts consume synthetic Skill handoffs, never private lore."""
import copy
from unittest.mock import Mock,patch
import asset_templates as contracts
import asset_generation as generation
import asset_library as library
import generation_scope
import image_provider
from asset_handoff_fixture import handoff
from test_asset_library import AssetFixture,png


class HandoffTests(AssetFixture):
    def setUp(self):
        super().setUp();self.role=self.service.catalog(1)['assets'][0]

    def ready_role(self,subtype='human'):
        return self.install_profile(self.role['id'],handoff(self.root,'character',subtype))

    def test_missing_design_is_pending_not_backend_invented_appearance(self):
        design=contracts.blueprint(self.state(),self.role,library._version(self.role))
        self.assertFalse(design['ready']);self.assertEqual(design['fields'],{})
        public=contracts.public_design(design);self.assertFalse(public['ready']);self.assertEqual(public['summary'],[])
        with self.assertRaisesRegex(ValueError,'交接'):contracts.contract(self.state(),self.role,library._version(self.role),'portrait','qwen-image-3.0-pro')

    def test_complete_handoff_preserves_fact_choice_unknown_without_nlp(self):
        profile=handoff(self.root,'character');profile['fields']['age']=contracts.entry('年龄未指定','unknown','synthetic source')
        role=self.install_profile(self.role['id'],profile);design=contracts.blueprint(self.state(),role,library._version(role))
        self.assertTrue(design['ready']);self.assertEqual(design['fields']['age']['origin'],'unknown')
        self.assertEqual(design['fields']['identity']['origin'],'story_fact');self.assertEqual(design['fields']['hair']['origin'],'system_choice')
        self.assertEqual(design,contracts.blueprint(self.state(),role,library._version(role)))

    def test_robot_schema_does_not_require_human_hair_skin_or_clothes(self):
        role=self.ready_role('robot');design=contracts.blueprint(self.state(),role,library._version(role))
        self.assertTrue(design['ready']);self.assertEqual(set(design['fields']),set(contracts.ROBOT_FIELDS))
        self.assertNotIn('hair',design['fields']);self.assertNotIn('footwear',design['fields'])
        wrong=handoff(self.root,'character','robot');wrong['fields']['hair']=contracts.entry('wrong schema')
        with self.assertRaises(ValueError):contracts.normalize_profile(wrong,'character')

    def test_nonhuman_can_use_complete_structure_front_as_identity_without_fake_headshot(self):
        profile=handoff(self.root,'character','robot');profile['master_plan']['identity_tag']='body_front'
        role=self.install_profile(self.role['id'],profile)
        bundle=contracts.contract(self.state(),role,library._version(role),'body_front','qwen-image-3.0-pro')
        self.assertEqual(bundle['template']['requires'],[])
        role=self.upload(role,'body_front');self.action('adopt',asset_id=role['id'],version=4)
        role=self.service.catalog(1)['assets'][0];v=library._version(role)
        self.assertTrue(contracts.review_status(self.state(),role,v)['identity_reviewed'])
        refs=contracts.select_reference_views(self.state(),role,v,'body_back','qwen-image-3.0-pro',4,None)
        self.assertEqual([ref['tag'] for ref in refs],['body_front'])
        animal=handoff(self.root,'character','animal');animal['master_plan'].update(identity_tag='body_front',has_feet=False)
        animal['view_recipes']['body_front']['feet_visible']=False
        recipe=contracts.recipe('character','body_front','qwen-image-3.0-pro',animal)
        self.assertTrue(recipe['template']['framing']['complete_subject'])
        self.assertNotIn('hair',contracts.normalize_profile(animal,'character')['fields'])

    def test_project_isolation_and_script_never_dumped_into_handed_prompt(self):
        role=self.ready_role();v=library._version(role);one=self.state();two=copy.deepcopy(one);two['project_id']=2
        self.assertNotEqual(contracts.blueprint(one,role,v)['design_hash'],contracts.blueprint(two,role,v)['design_hash'])
        one['script']='UNRELATED_PRIVATE_TEXT '*6000
        prompt=contracts.render_prompt(contracts.contract(one,role,v,'portrait','qwen-image-3.0-pro'))
        self.assertNotIn('UNRELATED_PRIVATE_TEXT',prompt);self.assertLess(len(prompt),4300)

    def test_skill_byte_hash_and_reference_path_verified_without_interpreting(self):
        profile=handoff(self.root,'character');contracts.verify_skill_source(self.root,profile,'character')
        bad_version=copy.deepcopy(profile);bad_version['source']['skill_version']='wrong-version'
        with self.assertRaisesRegex(ValueError,'版本'):contracts.verify_skill_source(self.root,bad_version,'character')
        reference=self.root/'skills'/'frame-character-assets'/'templates'/'fixture-contract.md'
        reference.write_text('changed source')
        with self.assertRaisesRegex(ValueError,'变化'):contracts.verify_skill_source(self.root,profile,'character')
        profile['source']['references']={'../../secret.md':'a'*64}
        with self.assertRaisesRegex(ValueError,'路径'):contracts.verify_skill_source(self.root,profile,'character')

    def test_character_and_object_skill_sources_iterate_independently(self):
        person=handoff(self.root,'character');obj=handoff(self.root,'object')
        (self.root/'skills'/'frame-character-assets'/'SKILL.md').write_text('character source changed')
        with self.assertRaises(ValueError):contracts.verify_skill_source(self.root,person,'character')
        contracts.verify_skill_source(self.root,obj,'object')
        (self.root/'docs'/'PRODUCTION_HANDOFF.md').write_text('shared execution contract changed')
        with self.assertRaises(ValueError):contracts.verify_skill_source(self.root,obj,'object')

    def test_invalid_complete_profile_is_not_ready_to_request(self):
        profile=handoff(self.root,'character');profile['view_recipes']['body_front']['single_image']=False
        role=self.install_profile(self.role['id'],profile)
        self.assertFalse(role['design_summary']['ready'])
        with self.assertRaises(ValueError):contracts.contract(self.state(),role,library._version(role),'body_front','qwen-image-3.0-pro')

    def test_technical_single_image_direction_neutral_and_full_body_guards(self):
        base=handoff(self.root,'character')
        for key,value in [('single_image',False),('single_subject',False),('direction','back_180'),('neutral_pose',False),('feet_visible',False),('head_visible',False)]:
            profile=copy.deepcopy(base);profile['view_recipes']['body_front'][key]=value
            with self.assertRaises(ValueError):contracts.recipe('character','body_front','qwen-image-3.0-pro',profile)
        obj=handoff(self.root,'object');obj['view_recipes']['main']['contains_hands']=True
        with self.assertRaises(ValueError):contracts.recipe('object','main','qwen-image-3.0-pro',obj)
        with self.assertRaises(ValueError):contracts.recipe('object','body_back','qwen-image-3.0-pro',obj)

    def test_explicit_design_operation_keeps_candidate_and_old_characters(self):
        before=copy.deepcopy(self.state());profile=handoff(self.root,'character')
        result=self.action('design',asset_id=self.role['id'],profile=profile);role=result['assets'][0]
        self.assertEqual(role['latest_version'],4);self.assertTrue(role['design_summary']['ready'])
        self.assertEqual(self.state()['characters'],before['characters']);self.assertEqual(self.state()['shots'],before['shots'])
        self.assertEqual(library._version(role)['views'],[])

    def test_editing_creative_brief_requires_fresh_agent_handoff_before_generation(self):
        role=self.ready_role();self.action('edit',asset_id=role['id'],summary='新的外观意图')
        role=self.service.catalog(1)['assets'][0]
        self.assertFalse(role['design_summary']['ready'])
        with self.assertRaises(ValueError):contracts.contract(self.state(),role,library._version(role),'portrait','qwen-image-3.0-pro')
        profile=handoff(self.root,'character')
        self.action('design',asset_id=role['id'],profile=profile)
        self.assertTrue(self.service.catalog(1)['assets'][0]['design_summary']['ready'])

    def test_body_side_requires_both_reviewed_masters_not_one_identity_photo(self):
        role=self.service.catalog(1)['assets'][0];role=self.install_profile(role['id'],handoff(self.root,'character'));role=self.upload(role,'portrait');self.action('adopt',asset_id=role['id'],version=4)
        role=self.service.catalog(1)['assets'][0];v=library._version(role)
        refs=contracts.select_reference_views(self.state(),role,v,'body_front','qwen-image-3.0-pro',4,None)
        self.assertEqual([r['tag'] for r in refs],['portrait'])
        with self.assertRaisesRegex(ValueError,'全身正面'):contracts.select_reference_views(self.state(),role,v,'body_back','qwen-image-3.0-pro',4,None)
        role=self.upload(role,'body_front');self.action('adopt',asset_id=role['id'],version=5)
        role=self.service.catalog(1)['assets'][0];v=library._version(role)
        self.assertTrue(contracts.review_status(self.state(),role,v)['base_ready']);self.assertFalse(contracts.review_status(self.state(),role,v)['reusable'])
        refs=contracts.select_reference_views(self.state(),role,v,'body_back','qwen-image-3.0-pro',5,None)
        self.assertEqual([r['tag'] for r in refs],['portrait','body_front'])
        role=self.upload(role,'body_side');role=self.upload(role,'body_back');self.action('adopt',asset_id=role['id'],version=7)
        role=self.service.catalog(1)['assets'][0];self.assertFalse(contracts.review_status(self.state(),role,library._version(role))['reusable'])
        role=self.upload(role,'head_side');role=self.upload(role,'head_back');self.action('adopt',asset_id=role['id'],version=9)
        role=self.service.catalog(1)['assets'][0];self.assertTrue(contracts.review_status(self.state(),role,library._version(role))['reusable'])

    def test_recipe_or_skill_change_needs_review_without_mutating_history(self):
        obj=self.upload(self.create());self.action('adopt',asset_id=obj['id'],version=2)
        obj=self.service.catalog(1)['assets'][-1];v=library._version(obj);before=copy.deepcopy(self.state())
        with patch.object(contracts,'RECIPE_VERSION','2.0'):self.assertFalse(contracts.review_status(self.state(),obj,v)['reusable'])
        self.assertEqual(self.state(),before)
        (self.root/'skills'/'frame-object-assets'/'SKILL.md').write_text('changed Skill')
        public=self.service.catalog(1)['assets'][-1]
        self.assertFalse(public['design_summary']['ready']);self.assertFalse(public['production_status']['reusable'])
        self.assertEqual(self.state(),before)

    def test_object_identity_does_not_take_holder_count_or_location_from_shot(self):
        obj=self.create();state=self.state();state['shots'][0]['creative_details']={'prop_states':[{'holder':'right','count':2,'location':'secret-room'}]}
        design=contracts.blueprint(state,obj,library._version(obj));self.assertEqual(set(design['fields']),set(contracts.OBJECT_FIELDS))
        prompt=contracts.render_prompt(contracts.contract(state,obj,library._version(obj),'main','qwen-image-3.0-pro'))
        self.assertNotIn('secret-room',prompt);self.assertNotIn('holder',prompt)

    def test_source_document_parser_does_not_pretend_to_be_a_skill_agent(self):
        parsed=contracts.parse_design_markdown('## Example\n- 故事事实：工厂考生\n- 本版系统设计选择：测试方案\n','/private/design.md')
        self.assertFalse(parsed['ready']);self.assertEqual(parsed['source']['document'],'design.md')
        self.assertFalse(parsed['items'][0]['ready']);self.assertIn('本版系统设计选择',parsed['items'][0]['notes'])


    def test_workflow_material_readiness_requires_current_adopted_masters(self):
        import workflow_state
        role=self.service.catalog(1)['assets'][0];role=self.install_profile(role['id'],handoff(self.root,'character'));role=self.upload(role,'portrait')
        self.action('adopt',asset_id=role['id'],version=role['latest_version'])
        self.assertEqual(workflow_state.material_preparation(self.state())['ready'],0)
        role=self.upload(role,'body_front');self.action('adopt',asset_id=role['id'],version=role['latest_version'])
        self.assertEqual(workflow_state.material_preparation(self.state()),{'ready':1,'total':1,'complete':True})
        role=self.service.catalog(1)['assets'][0]
        self.action('edit',asset_id=role['id'],name='新的角色设定',summary='新外观',role='主角',variant='')
        self.assertFalse(workflow_state.material_preparation(self.state())['complete'])

class RecipePipelineTests(AssetFixture):
    def setUp(self):
        super().setUp();import os
        self.env=patch.dict(os.environ,{'STUDIO_SECRET_FILE':str(self.root/'private'/'credentials.json')});self.env.start();self.addCleanup(self.env.stop)
        self.provider=image_provider.ImageProvider();self.provider.headers=Mock(return_value={});self.provider.submit=Mock(return_value='provider-id')
        self.provider.status=Mock(return_value={'status':'completed','image_urls':['https://example.aliyuncs.com/1.png']})
        self.gen=generation.AssetGeneration(self.service,lambda _:self.provider,lambda _:png(),lambda:1000)
        self.obj=self.create();self.items=[{'asset_id':self.obj['id'],'version':1,'view_tag':'main'}]

    def test_handoff_recipe_actual_mapping_and_refs_bind_plan_snapshot(self):
        preview=self.gen.preview(1,self.items,'qwen-image-3.0-pro');self.assertIn('designs',preview);self.assertFalse(preview['network_called'])
        bundle=self.gen._plan(self.state(),self.items,'qwen-image-3.0-pro')['jobs'][0]['production_contract']
        self.assertTrue(all(k in bundle for k in ('blueprint','template','mapping','mapping_hash','provider_mapping_hash','concrete_mapping','recipe_hash','contract_hash','reference_bindings','reference_review')))
        self.assertEqual(bundle['concrete_mapping']['request']['parameters']['n'],1)
        for field in ('RECIPE_VERSION','MAPPING_VERSION'):
            with patch.object(contracts,field,'2.0'):
                self.assertNotEqual(self.gen.preview(1,self.items,'qwen-image-3.0-pro')['fingerprint'],preview['fingerprint'])
                with self.assertRaisesRegex(ValueError,'变化'):self.gen.submit(1,preview['revision'],self.items,'qwen-image-3.0-pro',preview['fingerprint'],'a'*32)
        self.provider.submit.assert_not_called();self.assertEqual(self.state()['image_tasks'],[])

    def test_reserved_recipe_cannot_execute_after_source_change_but_history_is_frozen(self):
        generation_scope.authorize_budgets(1,self.database,2,0,'mock source fixture',self.state()['revision'])
        preview=self.gen.preview(1,self.items,'qwen-image-3.0-pro')
        with patch.object(self.gen,'advance',return_value=None):self.gen.submit(1,preview['revision'],self.items,'qwen-image-3.0-pro',preview['fingerprint'],'a'*32)
        old=copy.deepcopy(self.state()['image_tasks'][0])
        (self.root/'skills'/'frame-object-assets'/'SKILL.md').write_text('changed Skill')
        with self.assertRaises(ValueError):self.gen.advance(1,'a'*32)
        self.provider.submit.assert_not_called();self.assertEqual(self.state()['image_tasks'][0],old)
        self.gen._update(1,lambda s:s['image_tasks'][0].update(status='completed',production_contract={'historical':'kept'}))
        history=copy.deepcopy(self.state());self.gen.poll(1,old['id']);self.assertEqual(self.state(),history)

    def test_project_view_prompt_edit_also_expires_reserved_request(self):
        generation_scope.authorize_budgets(1,self.database,2,0,'mock prompt revision fixture',self.state()['revision'])
        preview=self.gen.preview(1,self.items,'qwen-image-3.0-pro')
        with patch.object(self.gen,'advance',return_value=None):self.gen.submit(1,preview['revision'],self.items,'qwen-image-3.0-pro',preview['fingerprint'],'a'*32)
        changed=handoff(self.root,'object');changed['view_recipes']['main']['prompt']='同一物品的新已交接主图描述。'
        self.action('design',asset_id=self.obj['id'],profile=changed)
        with self.assertRaisesRegex(ValueError,'配方'):self.gen.advance(1,'a'*32)
        self.provider.submit.assert_not_called()

    def test_paused_zero_budget_and_auth_file_unchanged_on_handoff_preview(self):
        generation_scope.authorize_budgets(1,self.database,0,0,'mock paused fixture',self.state()['revision'])
        data=generation_scope.read();data['1']['paused']=True;generation_scope.path().write_text(__import__('json').dumps(data))
        auth=generation_scope.path().read_bytes();state=copy.deepcopy(self.state())
        preview=self.gen.preview(1,self.items,'qwen-image-3.0-pro')
        with self.assertRaisesRegex(ValueError,'暂停'):self.gen.submit(1,preview['revision'],self.items,'qwen-image-3.0-pro',preview['fingerprint'],'a'*32)
        self.assertEqual(generation_scope.path().read_bytes(),auth);self.assertEqual(self.state(),state);self.provider.submit.assert_not_called()
