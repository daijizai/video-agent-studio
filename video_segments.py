"""Editable segment drafts; task input snapshots remain immutable."""
import copy,uuid
import asset_library,asset_templates

def all_tasks(state,segment):
    return [t for t in state.get('tasks',[]) if t.get('segment_id')==segment['id'] or t['id'] in segment.get('legacy_task_ids',[])]

def initialize(state):
    if 'video_segments' in state:return False
    segments=[];shots=state.get('shots',[])
    if shots:
        first=copy.deepcopy(shots[0]);segments.append({'id':'segment-opening','name':'片段01 · 考试条件','order':0,'duration':first.get('duration',15),'material_video_prompt':first.get('material_video_prompt') or first.get('prompt',''),'material_video_audio':first.get('material_video_audio',True),'asset_references':first.get('asset_references',[]),'source_shot_ids':[first['id']],'legacy_task_ids':[],'include_in_playlist':True,'draft_revision':1})
    for task in state.get('tasks',[]):
        shot=next((s for s in shots if s['id']==task.get('shot_id')),None)
        # Historical tasks are grouped separately, never relabelled as a new opening.
        sid='legacy-segment-'+str(task.get('shot_id') or task['id'])
        segment=next((s for s in segments if s['id']==sid),None)
        if segment:segment['legacy_task_ids'].append(task['id']);continue
        segments.append({'id':sid,'name':'历史测试 · '+task.get('name','视频'),'order':len(segments),'duration':task.get('request',{}).get('duration',shot.get('duration',15) if shot else 15),'material_video_prompt':shot.get('material_video_prompt') or shot.get('prompt','') if shot else '', 'material_video_audio':task.get('request',{}).get('generate_audio',False),'asset_references':copy.deepcopy(shot.get('asset_references',[]) if shot else []),'source_shot_ids':[shot['id']] if shot else [],'legacy_task_ids':[task['id']],'include_in_playlist':False,'draft_revision':1})
    state['video_segments']=segments;return True

def operate(server,state,action,p):
    if action=='init-segments':
        if initialize(state):server.save(state)
        return {'segments':state['video_segments']}
    initialize(state)
    if action=='create-segment':
        segment={'id':'segment-'+uuid.uuid4().hex,'name':'片段%02d'%(sum(not s.get('legacy_task_ids') for s in state['video_segments'])+1),'order':len(state['video_segments']),'duration':15,'material_video_prompt':'','material_video_audio':True,'asset_references':[],'legacy_task_ids':[],'include_in_playlist':True,'draft_revision':1}
        state['video_segments'].append(segment);server.save(state);return {'segment':segment}
    segment=next((s for s in state['video_segments'] if s['id']==p.get('segment_id')),None)
    if not segment:raise ValueError('视频片段不存在')
    if action=='reject-candidate':
        task=next((t for t in all_tasks(state,segment) if t['id']==p.get('task_id') and t['status']=='completed'),None)
        if not task:raise ValueError('只能标记本片段已完成的候选')
        reason=p.get('reason','')
        if not isinstance(reason,str) or not reason.strip() or len(reason)>500:raise ValueError('请填写审核未通过的原因')
        task['review_status']='rejected_quality';task['review_reason']=reason.strip();task['review_source']='用户审阅反馈'
        if segment.get('selected_task_id')==task['id']:segment.pop('selected_task_id',None)
        server.save(state);return {'rejected':True,'task_id':task['id']}
    if action=='accept-segment':
        import hashlib
        task=next((t for t in all_tasks(state,segment) if t['id']==p.get('task_id') and t['status']=='completed'),None)
        if not task:raise ValueError('只能验收本片段已完成的候选')
        local=task.get('local_video','');prefix='/media/'+str(state['project_id'])+'/'
        if not local.startswith(prefix):raise ValueError('请先归档视频原文件')
        file=(server.ROOT/'assets'/local.removeprefix('/media/')).resolve()
        if not file.is_relative_to((server.ROOT/'assets').resolve()) or not file.is_file():raise ValueError('视频文件不可用')
        task['review_status']='accepted';task['accepted_video_sha256']=hashlib.sha256(file.read_bytes()).hexdigest();task['review_source']=str(p.get('source','用户验收当前片段'))[:500]
        segment['selected_task_id']=task['id']
        import video_quality
        brief=state.get('project_brief') or {};brief=brief if isinstance(brief,dict) else {'summary':brief}
        formal=sorted((x for x in state['video_segments'] if not x.get('legacy_task_ids')),key=lambda x:x.get('order',0))
        if not brief.get('video_quality') and formal and formal[0]['id']==segment['id']:
            brief['video_quality']={'enabled':True,'baseline_task_id':task['id'],'baseline_sha256':task['accepted_video_sha256'],'prompt':video_quality.DEFAULT_PROMPT,'source':'第一段经用户验收后作为项目画质基准'}
            state['project_brief']=brief
        import voice_reference
        audio_result=voice_reference.extract_initial(state,segment,task,server.ROOT)
        server.save(state);return {'accepted':True,'task_id':task['id'],'voice_reference':audio_result}
    if action!='save-segment':raise ValueError('未知片段操作')
    update=p.get('draft',{})
    if not isinstance(update,dict):raise ValueError('片段草稿无效')
    before=copy.deepcopy(segment)
    for key,limit in [('name',100),('material_video_prompt',16000)]:
        if key in update:
            if not isinstance(update[key],str) or len(update[key])>limit:raise ValueError('片段文字过长或格式无效')
            segment[key]=update[key].strip()
    if 'duration' in update:
        value=update['duration']
        if type(value) not in (int,float) or int(value)!=value or not 4<=value<=30:raise ValueError('片段时长须为4至30秒整数')
        segment['duration']=int(value)
    for key in ('material_video_audio','include_in_playlist'):
        if key in update:
            if type(update[key]) is not bool:raise ValueError('选项须为布尔值')
            segment[key]=update[key]
    if 'material_video_parent_task_id' in update:
        tid=update['material_video_parent_task_id']
        if tid:
            task=next((t for t in state['tasks'] if t['id']==tid and t.get('status')=='completed'),None)
            if not task or task in all_tasks(state,segment):raise ValueError('前置视频必须是其他片段已完成的任务')
        segment['material_video_parent_task_id']=tid or ''
    if 'material_video_reference_mode' in update:
        mode=update['material_video_reference_mode']
        if mode not in ('original','tail'):raise ValueError('前置视频参考方式无效')
        segment['material_video_reference_mode']=mode
    if 'reference_asset_ids' in update:
        ids=update['reference_asset_ids']
        if not isinstance(ids,list) or len(ids)>9 or len(ids)!=len(set(ids)):raise ValueError('素材选择无效或超限')
        refs=[]
        for aid in ids:
            asset=next((a for a in asset_library.assets(state) if a['id']==aid),None)
            if not asset or not asset.get('adopted_version'):raise ValueError('只能选择当前项目已采用素材')
            version=asset_library._version(asset,asset['adopted_version']);asset_templates.verify_skill_source(server.ROOT,version['design_profile'],asset['kind'])
            tag='body_front' if asset['kind']=='character' else 'main';view=next((v for v in version['views'] if v['tag']==tag),None)
            if not view:raise ValueError('所选素材缺少全身正面或主图')
            server.material_service()._checked_view(state['project_id'],view)
            refs.append({'asset_id':aid,'kind':asset['kind'],'version':version['version'],'name':version['name'],'variant':version.get('variant',''),'views':[copy.deepcopy(view)],'production_review':asset_templates.review_record(state,asset,version)})
        segment['asset_references']=refs
    if 'selected_task_id' in update:
        if update['selected_task_id'] not in {t['id'] for t in all_tasks(state,segment)}:raise ValueError('候选不属于该片段')
        segment['selected_task_id']=update['selected_task_id']
    if 'video_style' in update:
        if not isinstance(update['video_style'],str) or len(update['video_style'])>12000:raise ValueError('视频风格无效')
        brief=state.get('project_brief') or {};brief=brief if isinstance(brief,dict) else {'summary':brief};brief['video_style']=update['video_style'];state['project_brief']=brief
    if before!=segment:segment['draft_revision']=before.get('draft_revision',0)+1;segment.pop('material_video_approval',None)
    server.save(state);return {'segment':segment}
