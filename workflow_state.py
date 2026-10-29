"""Pure project-stage derivation from persisted content, approvals and real tasks."""
import hashlib,json
import storyboard_contract
import asset_library
import asset_templates

def approval_hash(state,shot):
 content={k:shot.get(k) for k in ('id','name','duration','frame','prompt','image_prompt','storyboard_task_id','storyboard_local','storyboard_sha256')}
 if 'story_intent' in shot:content['story_intent']=shot['story_intent']
 context={k:state.get(k) for k in ('script','characters','continuity')}
 return hashlib.sha256(json.dumps({'shot':content,'context':context},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def valid_approval(state,shot):
 record=shot.get('approval_snapshot') or {}
 return bool(shot.get('approved') and shot.get('storyboard_task_id') and shot.get('storyboard_local') and shot.get('approved_image_task_id')==shot.get('storyboard_task_id')==record.get('image_task_id') and record.get('content_hash')==approval_hash(state,shot) and storyboard_contract.matches(record,shot) and asset_library.valid_binding(record,shot))
def task_matches(state,task):
 records=task.get('approval_snapshot')
 if isinstance(records,list):
  current={s['id']:s for s in state.get('shots',[])}
  by_image={s.get('storyboard_task_id'):s for s in current.values()}
  return bool(len(records)==len(current) and records and all(r.get('image_task_id') in by_image and r.get('content_hash')==approval_hash(state,by_image[r['image_task_id']]) and storyboard_contract.matches(r,by_image[r['image_task_id']]) and asset_library.valid_binding(r,by_image[r['image_task_id']]) for r in records))
 shot=next((s for s in state.get('shots',[]) if s['id']==task.get('shot_id')),None)
 old=task.get('content_snapshot',{}).get('shot',{}).get('approval_snapshot',{})
 return bool(shot and valid_approval(state,shot) and old.get('content_hash')==approval_hash(state,shot) and storyboard_contract.matches(old,shot) and asset_library.valid_binding(old,shot))
def material_preparation(state):
 """Count only adopted, reviewed masters matching the current design."""
 items=asset_library.assets(state);ready=0
 for asset in items:
  adopted=next((v for v in asset.get('versions',[]) if v['version']==asset.get('adopted_version')),None)
  latest=next((v for v in asset.get('versions',[]) if v['version']==asset.get('latest_version')),None)
  if not adopted or not latest:continue
  try:
   same=asset_templates.blueprint(state,asset,adopted)['design_hash']==asset_templates.blueprint(state,asset,latest)['design_hash']
   if same and asset_templates.review_status(state,asset,adopted)['base_ready']:ready+=1
  except (ValueError,KeyError,TypeError):continue
 return {'ready':ready,'total':len(items),'complete':bool(items and ready==len(items))}

def derive(state):
 materials=material_preparation(state)
 shots=state.get('shots',[]);approved=[s['id'] for s in shots if valid_approval(state,s)]
 prepared=bool(str(state.get('script','')).strip() and state.get('characters') and shots)
 all_approved=bool(shots and len(approved)==len(shots));videos=[t for t in state.get('tasks',[]) if t.get('kind')=='sequence' or t.get('provider') in ('wan3','wan3-prime','wan','seedance','seedance25')]
 current=[t for t in videos if task_matches(state,t)];latest=current[-1] if current else None
 ready_video=bool(latest and latest.get('status')=='completed' and (latest.get('local_video') or latest.get('video_url')))
 final=state.get('final_video') or {};complete=bool(ready_video and final.get('task_id')==latest['id'] and final.get('review_status') in ('approved','accepted_first_version') and final.get('review_task_id')==latest['id'])
 if not prepared:code,label,next_title,action='PREPARATION','故事与资产准备','完善内容','准备剧本、角色与镜头规划；配置或图片任务不等于视频已生成。'
 elif not materials['complete'] and not any(s.get('storyboard_local') for s in shots):code,label,next_title,action='MATERIAL_PREPARATION','素材母版待准备 / 采用','准备角色与物品素材','已就绪 '+str(materials['ready'])+'/'+str(materials['total'])+' 项；先整理设定、生成母版并人工审阅采用，再供分镜引用。'
 elif not all_approved:code,label,next_title,action='STORYBOARD_REVIEW','分镜待审阅 / 审批已失效','审阅当前版本分镜','当前有效批准 '+str(len(approved))+'/'+str(len(shots))+'；内容或当前图变化后需重新确认。已有视频仍绑定原请求快照。'
 elif not latest:code,label,next_title,action='VIDEO_READY','分镜已确认 · 视频待提交','生成当前批准版本的视频','当前分镜已有效批准；只有真实提交任务后才进入生成阶段。'
 elif latest.get('status') in ('unknown','failed','rejected','cancelled'):code,label,next_title,action='VIDEO_ATTENTION','视频任务需处理','核对原视频任务','状态为 '+str(latest.get('status'))+'；未知提交不重提，按原编号查询或核对，不能把失败显示成生成中。'
 elif latest.get('status')=='submitting':code,label,next_title,action='VIDEO_SUBMITTING','视频提交中','等待提交结果','请求意图已持久化；等待供应商编号，网络异常进入待核对，不自动重发。'
 elif latest.get('status') in ('queued','running'):code,label,next_title,action='VIDEO_GENERATING',('视频排队中' if latest['status']=='queued' else '视频生成中'),'跟踪原任务','只查询已经保存的供应商任务编号，完成后下载回填，不重复生成。'
 elif complete:code,label,next_title,action='COMPLETE',('首版已阶段性接受' if final.get('review_status')=='accepted_first_version' else '成片已审核通过'),'保留交付与证据',('用户接受此首版，后续新生成已暂停；不等于所有对白、声线、道具指标客观完美。' if final.get('review_status')=='accepted_first_version' else '当前视频和当前批准版本匹配，且有独立的成片人类审核记录。')
 elif ready_video:code,label,next_title,action='VIDEO_REVIEW','视频已生成 · 待检查','播放并检查真实视频','检查时长、音轨、对白、人物与道具连续性；生成完成不等于成片质量通过。'
 else:code,label,next_title,action='VIDEO_ATTENTION','视频结果待核对','恢复原任务结果','任务记录存在但没有可用媒体，查询原任务并恢复下载，不自动重新生成。'
 active=0 if not prepared else 1 if code=='MATERIAL_PREPARATION' else 2 if not all_approved else 4 if ready_video else 3
 stages=[('story','故事开发',prepared,'#script'),('materials','素材准备',materials['complete'],'#characters'),('storyboard','分镜确认',all_approved,'#shots'),('generation','视频生成',ready_video,'#tasks'),('review','检查成片',complete,'#tasks')]
 steps=[{'key':key,'label':text,'complete':done,'active':i==active and not complete,'href':href,**({'detail':str(materials['ready'])+'/'+str(materials['total'])+' 项就绪' if materials['total'] else '待整理'} if key=='materials' else {})} for i,(key,text,done,href) in enumerate(stages)]
 return {'code':code,'label':label,'next_title':next_title,'next_action':action,'approved_count':len(approved),'valid_approved_ids':approved,'shot_count':len(shots),'current_video_task_id':latest.get('id') if latest else None,'video_status':latest.get('status') if latest else None,'steps':steps,'materials':materials,'final_quality_approved':complete}

def record_approval(state,shot,source,recorded_at):
 if not shot.get('storyboard_task_id') or not shot.get('storyboard_local') or not shot.get('storyboard_sha256'):raise ValueError('必须审阅当前本机图片后才能批准图片版本')
 return {'source':source,'recorded_at':recorded_at,'content_revision':state['revision'],'image_task_id':shot['storyboard_task_id'],'image_sha256':shot['storyboard_sha256'],'content_hash':approval_hash(state,shot),**storyboard_contract.record_binding(shot),**asset_library.record_binding(shot)}
