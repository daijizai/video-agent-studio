"""Editable segment drafts; task input snapshots remain immutable."""
import base64,binascii,copy,hashlib,json,re,subprocess,uuid
from pathlib import Path
import asset_library,asset_templates

def accepted_video(root,state,task_id):
    task=next((t for t in state.get('tasks',[]) if t.get('id')==task_id),None)
    if not task or task.get('status')!='completed' or task.get('review_status')!='accepted':raise ValueError('请先审阅采用前一段视频')
    local=task.get('local_video','');prefix=f"/media/{state['project_id']}/"
    if not local.startswith(prefix) or not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:mp4|webm)',local[len(prefix):]):raise ValueError('前一段视频尚未本地归档')
    base=Path(root)/'assets';folder=base/str(state['project_id']);file=folder/local[len(prefix):]
    if base.is_symlink() or folder.is_symlink() or file.is_symlink() or not file.is_file() or file.resolve().parent!=folder.resolve():raise ValueError('前一段视频文件不可用')
    digest=hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    if task.get('accepted_video_sha256')!=digest.hexdigest():raise ValueError('已验收视频内容已变化')
    return task,file

def read_opening(root,state,segment,frame_id,require_approved=True):
    frame=next((v for v in segment.get('opening_frames',[]) if v.get('id')==frame_id),None)
    if not frame:raise ValueError('开场画面候选不存在')
    expected=f"/media/{state['project_id']}/opening_{frame_id}.png"
    if frame.get('url')!=expected or not isinstance(frame_id,str) or len(frame_id)!=32 or any(c not in '0123456789abcdef' for c in frame_id):raise ValueError('开场画面路径无效')
    base=Path(root)/'assets';folder=base/str(state['project_id']);file=folder/('opening_'+frame_id+'.png')
    if base.is_symlink() or folder.is_symlink() or file.is_symlink() or not file.is_file() or file.resolve().parent!=folder.resolve():raise ValueError('开场画面文件不可用')
    with file.open('rb') as stream:data=stream.read(asset_library.MAX_BYTES+1)
    info=asset_library.inspect_image(data)
    if any(info[k]!=frame.get(k) for k in ('sha256','width','height')):raise ValueError('开场画面内容已变化，请重新审阅')
    if frame.get('source_task_id'):
        task,_=accepted_video(root,state,frame['source_task_id'])
        if task.get('accepted_video_sha256')!=frame.get('source_video_sha256'):raise ValueError('开场画面的来源视频已变化')
    if require_approved and (frame.get('status')!='approved' or frame.get('approved_sha256')!=info['sha256']):raise ValueError('请先审阅采用当前开场画面')
    return frame,data,info

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
    if action=='delete-empty-segment':
        if segment.get('legacy_task_ids') or segment.get('opening_frames') or any(t.get('segment_id')==segment['id'] for t in state.get('tasks',[])):
            raise ValueError('含任务或开场画面的片段不能删除')
        state['video_segments']=[x for x in state['video_segments'] if x['id']!=segment['id']]
        server.save(state);return {'deleted':True,'segment_id':segment['id']}
    if action in ('add-opening-candidate','extract-opening-from-video'):
        source={'source':'Codex · OpenAI 生图工具'}
        if action=='extract-opening-from-video':
            task,video=accepted_video(server.ROOT,state,p.get('source_task_id'))
            if task.get('segment_id')==segment['id']:raise ValueError('请选择其他已验收片段')
            try:
                probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames','-of','json',str(video)],check=True,capture_output=True,timeout=60)
                count=int(json.loads(probe.stdout)['streams'][0]['nb_read_frames'])
                if not 1<=count<=100000:raise ValueError('来源视频帧数无效')
                result=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(video),'-vf',f'select=eq(n\\,{count-1})','-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],check=True,capture_output=True,timeout=60)
                data=result.stdout
            except (OSError,subprocess.SubprocessError,KeyError,IndexError,TypeError,json.JSONDecodeError) as error:raise ValueError('尾帧提取失败，请检查原视频') from error
            source={'source':'已审阅视频的实际末帧','source_task_id':task['id'],'source_video_sha256':task['accepted_video_sha256'],'source_frame_index':count-1}
        else:
            encoded=p.get('base64')
            if not isinstance(encoded,str) or len(encoded)>(asset_library.MAX_BYTES+2)//3*4:raise ValueError('首帧图片过大或编码无效')
            try:data=base64.b64decode(encoded,validate=True)
            except (ValueError,binascii.Error):raise ValueError('首帧图片编码无效') from None
        info=asset_library.inspect_image(data)
        if info['extension']!='png':raise ValueError('首帧候选请使用 PNG 原图')
        base=Path(server.ROOT)/'assets';folder=base/str(state['project_id'])
        if base.is_symlink() or folder.is_symlink():raise ValueError('素材目录不可为符号链接')
        folder.mkdir(parents=True,exist_ok=True)
        if folder.resolve().parent!=base.resolve():raise ValueError('素材目录无效')
        fid=uuid.uuid4().hex;file=folder/('opening_'+fid+'.png')
        try:
            with file.open('xb') as f:f.write(data)
            file.chmod(0o600)
            frame={'id':fid,'url':f"/media/{state['project_id']}/opening_{fid}.png",'sha256':info['sha256'],
                'width':info['width'],'height':info['height'],'status':'candidate',**source}
            segment.setdefault('opening_frames',[]).append(frame)
            server.save(state)
        except Exception:
            file.unlink(missing_ok=True);raise
        return {'candidate':frame}
    if action=='approve-opening':
        frame,_,info=read_opening(server.ROOT,state,segment,p.get('frame_id'),False)
        frame.update(status='approved',approved_sha256=info['sha256'],review_source=str(p.get('source','用户审阅采用开场画面'))[:300])
        segment.pop('material_video_approval',None);server.save(state)
        return {'approved':True,'frame_id':frame['id']}
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
    for key in ('material_video_audio','include_in_playlist','use_depth_reference'):
        if key in update:
            if type(update[key]) is not bool:raise ValueError('选项须为布尔值')
            segment[key]=update[key]
    if 'production_requirements' in update:
        requirements=update['production_requirements']
        if not isinstance(requirements,dict):raise ValueError('镜头制作要求格式无效')
        subjects=requirements.get('visible_subjects');scale_ids=requirements.get('approved_scale_asset_ids',[])
        if not isinstance(subjects,list) or not subjects or len(subjects)>30 or any(not isinstance(x,str) or not x.strip() or len(x)>80 for x in subjects) or len(set(subjects))!=len(subjects):raise ValueError('可见主体清单无效')
        if not isinstance(scale_ids,list) or len(scale_ids)>9 or any(not isinstance(x,str) for x in scale_ids):raise ValueError('比例素材清单无效')
        segment['production_requirements']={'visible_subjects':subjects,'approved_scale_asset_ids':scale_ids}
    if 'video_input_mode' in update:
        mode=update['video_input_mode']
        if mode not in ('references','first_frame','opening_reference'):raise ValueError('视频输入方式无效')
        if mode=='opening_reference' and state.get('settings',{}).get('provider','seedance25') not in ('seedance25','minimax'):raise ValueError('开场画面加素材参考仅支持 Seedance 2.5 和 MiniMax H3')
        if mode in ('first_frame','opening_reference'):
            frame_id=update.get('opening_frame_id') or segment.get('opening_frame_id')
            read_opening(server.ROOT,state,segment,frame_id)
            segment['opening_frame_id']=frame_id
        segment['video_input_mode']=mode
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
    if 'shot_language_ids' in update:
        import creative_resources
        refs=creative_resources.resolve(server.ROOT,update['shot_language_ids'],segment.get('shot_language'))
        if refs or 'shot_language' in segment:segment['shot_language']=refs
    if 'reference_asset_ids' in update:
        ids=update['reference_asset_ids']
        if not isinstance(ids,list) or len(ids)>9 or len(ids)!=len(set(ids)):raise ValueError('素材选择无效或超限')
        views_by_asset=update.get('reference_views_by_asset',{})
        if not isinstance(views_by_asset,dict) or any(k not in ids for k in views_by_asset):raise ValueError('素材视图选择无效')
        refs=[]
        for aid in ids:
            asset=next((a for a in asset_library.assets(state) if a['id']==aid),None)
            if not asset or not asset.get('adopted_version'):raise ValueError('只能选择当前项目已采用素材')
            version=asset_library._version(asset,asset['adopted_version']);asset_templates.verify_skill_source(server.ROOT,version['design_profile'],asset['kind'])
            tag={'character':'body_front','object':'main','scene':'scene_main','scale':'scale_main'}.get(asset['kind']);default=next((v for v in version['views'] if v['tag']==tag),None)
            if not default:raise ValueError('所选素材缺少所需的正面或场景主图')
            selected_ids=views_by_asset.get(aid)
            if selected_ids is None:views=[default]
            else:
                if asset['kind']!='character' or not isinstance(selected_ids,list) or not selected_ids or len(selected_ids)>3 or any(not isinstance(x,str) for x in selected_ids) or len(selected_ids)!=len(set(selected_ids)):raise ValueError('请选择角色的有效视图')
                views=[next((v for v in version['views'] if v['id']==vid and v['tag'] in ('body_front','body_side','body_back')),None) for vid in selected_ids]
                if any(v is None for v in views):raise ValueError('角色视图不属于当前已采用版本')
                review=asset_templates.review_status(state,asset,version)
                if any(v['tag'] not in review['ref_eligible_tags'] for v in views):raise ValueError('角色视图尚未按当前规范审阅')
            for view in views:server.material_service()._checked_view(state['project_id'],view)
            entry={'asset_id':aid,'kind':asset['kind'],'version':version['version'],'name':version['name'],'variant':version.get('variant',''),'views':copy.deepcopy(views),'production_review':asset_templates.review_record(state,asset,version)}
            if asset['kind']=='scale':entry['related_versions']=copy.deepcopy(version.get('related_versions',[]))
            refs.append(entry)
        chosen={r['asset_id']:r['version'] for r in refs if r['kind']=='character'}
        for ref in refs:
            if ref['kind']=='scale' and any(x['asset_id'] in chosen and chosen[x['asset_id']]!=x['version'] for x in ref['related_versions']):
                raise ValueError('比例参考与所选角色版本不一致，请重新审阅对应参考图')
        segment['asset_references']=refs
    if 'selected_task_id' in update:
        if update['selected_task_id'] not in {t['id'] for t in all_tasks(state,segment)}:raise ValueError('候选不属于该片段')
        segment['selected_task_id']=update['selected_task_id']
    if 'video_style' in update:
        if not isinstance(update['video_style'],str) or len(update['video_style'])>12000:raise ValueError('视频风格无效')
        brief=state.get('project_brief') or {};brief=brief if isinstance(brief,dict) else {'summary':brief};brief['video_style']=update['video_style'];state['project_brief']=brief
    if before!=segment:segment['draft_revision']=before.get('draft_revision',0)+1;segment.pop('material_video_approval',None)
    server.save(state);return {'segment':segment}
