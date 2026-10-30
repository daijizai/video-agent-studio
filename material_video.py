"""Material-reference video execution, separate from keyframe approvals."""
import base64,copy,hashlib,json,time,uuid,math,urllib.parse,re,wave
from decimal import Decimal,ROUND_UP
import ark_provider,asset_library,generation_scope,providers,media_files,video_quality

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def prepare(state,shot,library):
    asset_library.validate_references(state,shot,library)
    refs=shot.get('asset_references') or []
    if not refs:raise ValueError('请先绑定已验收素材')
    sources=[];data={};roles=[]
    for ref in refs:
        asset=next(a for a in asset_library.assets(state) if a['id']==ref['asset_id'])
        if asset.get('adopted_version')!=ref['version']:raise ValueError('素材采用版本已变化，请重新绑定')
        for view in ref['views']:
            raw,info=library._checked_view(state['project_id'],view)
            if min(info['width'],info['height'])<300 or max(info['width'],info['height'])>6000 or len(raw)>=30*1024*1024:raise ValueError('素材尺寸不满足视频参考要求')
            marker='https://material-video.invalid/'+info['sha256']+'.'+info['extension']
            data[marker]='data:'+info['mime']+';base64,'+base64.b64encode(raw).decode()
            sources.append({'asset_id':ref['asset_id'],'version':ref['version'],'name':ref['name'],'view_id':view['id'],'sha256':info['sha256']})
            roles.append('第%d张参考图为%s，仅固定身份或物品结构，不照搬标准图姿态与背景。'%(len(sources),ref['name']))
    prompt=shot.get('material_video_prompt') or shot.get('prompt','')
    shot_language=shot.get('shot_language') or []
    if not isinstance(shot_language,list) or len(shot_language)>3:raise ValueError('镜头语言引用无效')
    if shot_language:
        if any(not isinstance(x,dict) or x.get('kind') not in ('size','composition','movement') or not isinstance(x.get('instruction'),str) or len(x['instruction'])>500 for x in shot_language):raise ValueError('镜头语言引用无效')
        if len({x['kind'] for x in shot_language})!=len(shot_language):raise ValueError('每类镜头语言最多选一项')
        prompt+='\n本段镜头语言（多镜头时以各镜头明确安排为准）：'+' '.join(x['instruction'] for x in shot_language)
    style=state.get('project_style') or {}
    prompt+='\n素材用途：'+''.join(roles)+'\n这些均为素材参考，不指定任何首帧或分镜图片。\n项目风格：'+(style.get('prompt') or style.get('description',''))
    brief=state.get('project_brief') or {}
    video_style=brief.get('video_style','') if isinstance(brief,dict) else ''
    if video_style:prompt+='\n项目视频风格：'+video_style
    quality=video_quality.config(state)
    if quality:
        quality_prompt=quality.get('prompt','')
        if not isinstance(quality_prompt,str) or not quality_prompt.strip() or len(quality_prompt)>2000:raise ValueError('项目画质要求无效')
        prompt+='\n项目画质要求：'+quality_prompt
    config=copy.deepcopy(state['settings'])
    if 'material_video_audio' in shot:
        if type(shot['material_video_audio']) is not bool:raise ValueError('声音选项须为布尔值')
        config['audio']=shot['material_video_audio']
    voice_snapshots=[];voice_data=[]
    shared=brief.get('voice_reference') if isinstance(brief,dict) else None
    if config.get('audio'):
        selections=[];covered=set()
        for asset in state.get('voice_assets',[]):
            adopted=asset.get('adopted_version')
            version=next((v for v in asset.get('versions',[]) if v.get('version')==adopted and v.get('review_status')=='accepted'),None)
            if not version:continue
            name=asset.get('character_name','');covered.add(name)
            selections.append({'source_task_id':version['source_task_id'],'source_video_sha256':version['source_video_sha256'],'relative_path':'voice/'+version['id']+'.wav','sha256':version['sha256'],'duration':version['duration'],'expected_speakers':[name],'mapping_status':'用户试听后采用','usage':'character_voice_reference','asset_id':asset['id'],'asset_version':adopted})
        if shared and shared.get('enabled'):
            remaining=[name for name in shared.get('expected_speakers',[]) if name not in covered]
            if remaining:selections.append({**shared,'expected_speakers':remaining,'usage':'shared_project_voice_reference'})
        total_duration=0
        for voice in selections:
            source=next((t for t in state['tasks'] if t['id']==voice.get('source_task_id')),None)
            if not source or source.get('status')!='completed' or source.get('review_status')!='accepted':raise ValueError('声音参考的源视频尚未验收')
            if voice.get('source_video_sha256') and voice['source_video_sha256']!=source.get('accepted_video_sha256'):raise ValueError('声音参考来源已变化，请重新确认')
            rel=voice.get('relative_path','')
            if not re.fullmatch(r'(audio|voice)/[A-Za-z0-9_-]+\.wav',rel):raise ValueError('声音参考路径无效')
            folder=(library.root/'assets'/str(state['project_id'])).resolve();file=(folder/rel).resolve()
            if not file.is_relative_to(folder) or not file.is_file():raise ValueError('声音参考文件不可用')
            raw=file.read_bytes();sha=hashlib.sha256(raw).hexdigest()
            if sha!=voice.get('sha256') or len(raw)>15*1024*1024:raise ValueError('声音参考已变化或超过15MB')
            try:
                with wave.open(str(file),'rb') as audio:duration=audio.getnframes()/audio.getframerate()
            except (wave.Error,EOFError,ZeroDivisionError):raise ValueError('声音参考不是有效的WAV文件') from None
            if not 2<=duration<=30 or abs(float(voice.get('duration',0))-duration)>.1:raise ValueError('声音参考须为2至30秒且时长与记录一致')
            roles=voice.get('expected_speakers',[])
            if not isinstance(roles,list) or not roles or any(not isinstance(x,str) or not x or len(x)>80 for x in roles):raise ValueError('声音参考角色信息无效')
            total_duration+=duration;voice_data.append('data:audio/wav;base64,'+base64.b64encode(raw).decode())
            snapshot={'source_task_id':source['id'],'sha256':sha,'duration':round(duration,3),'expected_speakers':roles,'mapping_status':voice.get('mapping_status','待核对'),'usage':voice['usage']}
            if voice.get('asset_id'):snapshot.update(asset_id=voice['asset_id'],asset_version=voice['asset_version'])
            voice_snapshots.append(snapshot)
            prompt+='\n参考音频%d用于尽量保持%s的声音特征，仅借鉴音色和说话习惯，不重复参考音频中的台词。'%(len(voice_snapshots),'、'.join(roles))
        if len(voice_snapshots)>10 or total_duration>30:raise ValueError('声音参考最多10段、总时长最多30秒；请缩短或选择素材')
        if voice_snapshots:prompt+='\n按本段指定说话人说原文；声音参考可能含环境声，角色识别和生成效果须审阅。'
    parent_snapshot=None
    if shot.get('material_video_parent_task_id'):
        if shot.get('material_video_reference_mode')=='tail':
            raise ValueError('片尾已在本地裁剪，但尚未接入方舟可读取的上传地址；不能将原视频冒充片尾发送。请选择完整原视频或完成上传接入')
        parent=next((t for t in state['tasks'] if t['id']==shot['material_video_parent_task_id']),None)
        if not parent or parent.get('provider')!='seedance25' or parent.get('status')!='completed' or parent.get('review_status')!='accepted':raise ValueError('前置视频必须为当前项目已验收的Seedance原任务')
        url=parent.get('video_url','');parsed=urllib.parse.urlparse(url)
        if parsed.scheme!='https' or parsed.username or parsed.password or not parsed.hostname or not parsed.hostname.endswith('.volces.com'):raise ValueError('前置视频缺少方舟原始产物URL，请查询原任务')
        local=parent.get('local_video','');prefix='/media/'+str(state['project_id'])+'/'
        if not local.startswith(prefix):raise ValueError('前置视频尚未本地归档')
        file=(library.root/'assets'/local.removeprefix('/media/')).resolve()
        if not file.is_relative_to((library.root/'assets').resolve()) or not file.is_file():raise ValueError('前置视频原文件不可用')
        sha=hashlib.sha256(file.read_bytes()).hexdigest()
        if parent.get('accepted_video_sha256')!=sha:raise ValueError('前置视频内容已变化，需要重新验收')
        info=parent.get('media_info') or {};seconds=float(info.get('duration') or parent['request']['duration'])
        if not 4<=seconds<=30:raise ValueError('前置参考视频时长超出支持范围')
        width=int(info.get('width') or 1280);height=int(info.get('height') or 720)
        parent_snapshot={'task_id':parent['id'],'provider_task_id':parent['provider_task_id'],'sha256':sha,'url':url,'duration':seconds,'width':width,'height':height,'usage':'extend_after'}
        prompt+='\n向后延长视频1，从视频1结束后的下一时刻开始叙事，延续同一人物、场景和声音，不重演上一段对白。输出本次新增的后续片段，不把原片段再次完整重放。'

    baseline,quality_warnings=video_quality.select_reference(state,shot,library.root,parent_snapshot)
    if baseline and baseline['status']=='shared_with_parent':
        prompt+='\n视频1同时作为画质基准和动作衔接参考，保留画面的自然锐度和材质。'
    elif baseline and baseline['status']=='sent':
        prompt+='\n视频%d仅作为画质参考，借鉴清晰度、光线与材质，不复制剧情、动作或构图。'%(2 if parent_snapshot else 1)
    if len(prompt)>500:
        quality_warnings.append('本次Prompt超过500字；方舟建议精简中文提示词，但不会自动删除内容。')
    spec={'duration':shot['duration'],'prompt':prompt,'reference_images':list(data)}
    prepared=ark_provider.prepare_video(spec,config)
    if parent_snapshot:
        prepared['payload']['content'].append({'type':'video_url','video_url':{'url':parent_snapshot['url']},'role':'reference_video'})
        prepared['payload']['ratio']='adaptive';prepared['payload']['omni_reference_task_type']='extend'
        total_seconds=math.ceil(parent_snapshot['duration'])+int(shot['duration'])+1
        if baseline and baseline['status']=='sent':total_seconds+=math.ceil(baseline['duration'])
        # Billing uses output dimensions, which may differ from the source video's.
        basis=prepared['estimate_basis'];tokens=Decimal(basis['width']*basis['height']*24*total_seconds)/1024
        rate=Decimal('0.077' if config.get('resolution')=='1080p' else '0.07')
        prepared['estimated_cny']=float((tokens*rate/1000).quantize(Decimal('.01'),rounding=ROUND_UP))
        prepared['estimate_note']='保守沿用无视频输入单价，并计入前段视频时长与1秒余量；非实际折扣单价或账单'
    if baseline and baseline['status']=='sent':
        prepared['payload']['content'].append({'type':'video_url','video_url':{'url':baseline['url']},'role':'reference_video'})
        if not parent_snapshot:
            width,height=(1920,1080) if config.get('resolution')=='1080p' else (1280,720)
            tokens=Decimal(width*height*24*(math.ceil(baseline['duration'])+int(shot['duration'])+1))/1024
            rate=Decimal('0.077' if config.get('resolution')=='1080p' else '0.07')
            prepared['estimated_cny']=float((tokens*rate/1000).quantize(Decimal('.01'),rounding=ROUND_UP))
    for voice_snapshot in voice_snapshots:
        prepared['payload']['content'].append({'type':'audio_url','audio_url':{'url':'audio:sha256:'+voice_snapshot['sha256']},'role':'reference_audio'})
    manifest=copy.deepcopy(prepared['payload'])
    audio_index=0
    for item in prepared['payload']['content']:
        if item['type']=='image_url':item['image_url']['url']=data[item['image_url']['url']]
        elif item['type']=='audio_url':item['audio_url']['url']=voice_data[audio_index];audio_index+=1
    if len(json.dumps(prepared['payload']).encode())>64*1024*1024:raise ValueError('视频请求超过64MB')
    snapshot={'project_id':state['project_id'],'shot_id':shot['id'],'request':manifest,'materials':sources,'style':style,'script':state['script'],'parent_video':parent_snapshot,'voice_reference':voice_snapshots[0] if voice_snapshots else None,'voice_references':voice_snapshots,'quality_profile':copy.deepcopy(quality),'quality_reference':baseline,'quality_warnings':quality_warnings,'shot_language':copy.deepcopy(shot_language)}
    return prepared,snapshot

def operate(server,state,action,p):
    import video_segments
    if action in ('init-segments','create-segment','save-segment','accept-segment','reject-candidate'):return video_segments.operate(server,state,action,p)
    if action=='set-quality-baseline':
        task=next((t for t in state.get('tasks',[]) if t.get('id')==p.get('task_id')),None)
        _,sha=video_quality.accepted_file(state,server.ROOT,task)
        brief=state.get('project_brief') or {};brief=brief if isinstance(brief,dict) else {'summary':brief}
        previous=brief.get('video_quality') or {}
        brief['video_quality']={'enabled':True,'baseline_task_id':task['id'],'baseline_sha256':sha,'prompt':previous.get('prompt') or video_quality.DEFAULT_PROMPT,'source':'用户确认以此视频作为画质基准'}
        state['project_brief']=brief;server.save(state)
        return {'quality_profile':brief['video_quality']}
    if p.get('segment_id'):
        shot=next(x for x in state.get('video_segments',[]) if x['id']==p['segment_id'])
    else:shot=next(x for x in state['shots'] if x['id']==p['shot_id'])
    if action=='prepare-tail':
        import video_tail
        from pathlib import Path
        source_id=shot.get('material_video_parent_task_id')
        if not source_id:raise ValueError('请先选择已验收的前置视频')
        tail=video_tail.create(state,server.ROOT,source_id,p.get('seconds'))
        shot['material_video_tail']=tail
        shot['material_video_reference_mode']='tail'
        shot['draft_revision']=shot.get('draft_revision',0)+1
        shot.pop('material_video_approval',None)
        try:server.save(state)
        except Exception:
            (Path(server.ROOT)/'assets'/str(state['project_id'])/tail['relative_path']).unlink(missing_ok=True)
            raise
        return {'tail':tail}
    if action=='check-quality':
        import video_segments
        task=next((t for t in video_segments.all_tasks(state,shot) if t.get('id')==p.get('task_id') and t.get('status')=='completed'),None)
        if not task:raise ValueError('只能对照本片段已完成的视频')
        review=video_quality.inspect(state,server.ROOT,task)
        if review is None:raise ValueError('请先设置已验收的画质基准')
        task['quality_review']=review;server.save(state)
        return {'quality_review':review}
    prepared,snapshot=prepare(state,shot,server.material_service());signature=digest(snapshot)
    if action=='preview':return {'estimated_cny':prepared['estimated_cny'],'snapshot':snapshot,'fingerprint':signature,'network_called':False}
    if action=='approve':
        if p.get('fingerprint')!=signature:raise ValueError('素材或内容已变化，请重新预览')
        shot['material_video_approval']={'fingerprint':signature,'source':str(p.get('source','用户确认素材参考视频')),'at':time.time()};server.save(state)
        return {'approved':True,'fingerprint':signature}
    if action!='submit':raise ValueError('未知素材视频操作')
    if shot.get('material_video_approval',{}).get('fingerprint')!=signature:raise ValueError('请先确认当前素材与镜头内容')
    pending=[t for t in state['tasks'] if t.get('shot_id')==shot['id'] and t.get('status') in ('submitting','queued','running','unknown')]
    retry_of=None
    if pending:
        if (len(pending)==1 and pending[0]['status']=='unknown' and not pending[0].get('provider_task_id') and p.get('retry_unknown_task_id')==pending[0]['id'] and p.get('retry_risk_confirmed') is True):
            retry_of=pending[0]['id']
        else:raise ValueError('该镜头已有在途或未知视频任务；未知重试须逐次明确确认，原预占仍保留')
    if any(t.get('shot_id')==shot['id'] for t in state['tasks']) and not p.get('redo'):raise ValueError('已有任务，请明确重做')
    auth=generation_scope.check(state,server.DATA/'studio.db','video',prepared['estimated_cny'],ark_provider.VIDEO_MODEL)
    provider=providers.Provider('seedance25');provider.headers()
    task={'id':uuid.uuid4().hex,'shot_id':shot['id'],'name':shot['name'],'provider':'seedance25','kind':'material_reference_video','status':'submitting','provider_task_id':None,'estimate':prepared['estimated_cny'],'request':snapshot['request'],'material_snapshot':snapshot,'approval_snapshot':copy.deepcopy(shot['material_video_approval']),'authorization_id':auth,'submitted_epoch':time.time()}
    if p.get('segment_id'):
        task['segment_id']=shot['id'];task['segment_draft_revision']=shot.get('draft_revision',1)
    if retry_of:task['retry_of_unknown_task_id']=retry_of;task['retry_authorization_source']=str(p.get('retry_source','用户明确确认重复计费风险后重试'))[:500]
    state['tasks'].append(task);server.save(state)
    try:task['provider_task_id']=provider.submit(prepared,task['id'],authorized=True);task['status']='queued'
    except providers.ProviderHTTPError as error:
        task['submission_diagnostics']=copy.deepcopy(error.details)
        definitive=error.details.get('http_status') in (400,401,403,404,413,415,422)
        task['status']='rejected' if definitive else 'unknown'
        if definitive:task['actual_cost_cny']=0
        server.save(state)
        raise ValueError(('供应商明确拒绝：' if definitive else '供应商结果待核对：')+str(error.details.get('provider_code','HTTPError'))+'；诊断已保存，未自动重试')
    except Exception:
        task['status']='unknown';task['submission_diagnostics']={'reason':'transport_or_missing_task_id'};server.save(state);raise ValueError('提交结果未知，保留原任务，禁止自动重试')
    server.save(state);return {'task_id':task['id'],'status':task['status'],'provider_task_id':task['provider_task_id'],'estimated_cny':task['estimate']}
