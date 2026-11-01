"""Project change journal: records future persisted state writes, plus explicit notes."""
import json

LABELS={'title':'项目名称','episode':'项目集数','script':'剧本','script_audit':'剧本审阅','script_audit_history':'剧本审阅记录',
 'characters':'人物设定','continuity':'连续性资料','shots':'镜头资料','material_assets':'素材资产','material_events':'素材操作记录',
 'asset_view_sources':'素材来源','project_style':'视觉风格','project_style_history':'风格版本','video_segments':'视频片段',
 'tasks':'视频任务','image_tasks':'图片任务','final_video':'完整视频','settings':'模型与设置','budget':'预算',
 'budget_authorizations':'预算授权','project_brief':'项目设定','publications':'作品运营','voice_assets':'声音素材',
 'target_duration':'目标时长','events':'项目事件','quality_lessons':'复盘经验','_deleted':'项目状态'}
IGNORE={'revision','workflow','project_id','_write_revision'}

def install(con):
 con.execute('''CREATE TABLE IF NOT EXISTS project_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
  created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  kind TEXT NOT NULL, before_body TEXT, after_body TEXT, note TEXT)''')
 con.execute('CREATE INDEX IF NOT EXISTS project_steps_project_id ON project_steps(project_id,id DESC)')
 con.execute('''CREATE TRIGGER IF NOT EXISTS project_steps_state_insert AFTER INSERT ON state
 BEGIN INSERT INTO project_steps(project_id,kind,after_body) VALUES (NEW.id,'created',NEW.body); END''')
 con.execute('''CREATE TRIGGER IF NOT EXISTS project_steps_state_update AFTER UPDATE OF body ON state
 WHEN OLD.body != NEW.body
 BEGIN INSERT INTO project_steps(project_id,kind,before_body,after_body) VALUES (NEW.id,'change',OLD.body,NEW.body); END''')

def _task_details(before,after,key):
 old={x.get('id'):x for x in before.get(key,[]) if isinstance(x,dict) and x.get('id')}
 new={x.get('id'):x for x in after.get(key,[]) if isinstance(x,dict) and x.get('id')};out=[]
 for id,v in new.items():
  oldval=old.get(id);name=v.get('name') or id[:8];status=v.get('status','待核对');review=v.get('review_status');statuses={'queued':'排队中','running':'生成中','completed':'已完成','failed':'失败','rejected':'已拒绝','unknown':'结果待核对','submitting':'提交中','accepted':'已通过','rejected_quality':'未通过'}
  if not oldval:out.append(f'{name}：新增任务 · {statuses.get(status,status)}')
  elif v.get('status')!=oldval.get('status'):out.append(f'{name}：{statuses.get(oldval.get("status"),oldval.get("status","未知"))} → {statuses.get(status,status)}')
  if oldval and review!=oldval.get('review_status') and review:out.append(f'{name}：审阅状态 {statuses.get(review,review)}')
 return out

ACTIONS={'/api/save':'保存项目内容','/api/approvals/script':'审阅剧本','/api/settings':'更新模型设置',
 '/api/material-video/preview':'预览视频输入','/api/material-video/approve':'确认视频输入',
 '/api/material-video/submit':'提交视频生成','/api/material-video/save-segment':'保存视频片段',
 '/api/material-video/approve-opening':'采用开场画面','/api/material-video/accept-segment':'验收视频片段',
 '/api/material-video/reject-candidate':'标记视频候选问题','/api/assets/upload':'上传素材',
 '/api/assets/adopt':'采用素材','/api/assets/create':'创建素材',
 '/api/assets/generation/preview':'预览素材生成','/api/assets/generation/submit':'提交素材生成',
 '/api/operations/save-publication':'保存发布信息','/api/operations/save-snapshot':'保存运营数据',
 '/api/budgets/authorize':'设置预算授权','/api/video-speed/start':'导出倍速视频',
 '/api/projects/new':'新建项目','/api/projects/delete':'移除项目'}

def add_request(con,project_id,path,status):
 if not path.startswith('/api/') or path.startswith('/api/project-steps') or path.endswith(('/poll','/status')) or path in ('/api/projects/switch','/api/projects/new','/api/video-speed/status'):return
 con.execute('INSERT INTO project_steps(project_id,kind,note) VALUES (?,?,?)',(project_id,'request',json.dumps({'path':path,'status':status},ensure_ascii=False)))

def describe(row):
 if row['kind']=='request':
  info=json.loads(row['note']);label=ACTIONS.get(info.get('path'),'工作台操作 · '+info.get('path',''));ok=200<=info.get('status',500)<400
  return {'id':row['id'],'created':row['created'],'kind':'request','title':label,'details':['请求已处理，实际结果以项目状态为准' if ok else '请求未完成，请查看对应功能的状态']}
 if row['kind']=='note':return {'id':row['id'],'created':row['created'],'kind':'note','title':'复盘补充','details':[row['note']]}
 after=json.loads(row['after_body'] or '{}');before=json.loads(row['before_body'] or '{}')
 if row['kind']=='created':return {'id':row['id'],'created':row['created'],'kind':'created','title':'创建项目','details':['创建项目：'+str(after.get('title','未命名项目'))]}
 changed=[key for key in sorted(set(before)|set(after)) if key not in IGNORE and before.get(key)!=after.get(key)]
 details=[]
 for key in changed:
  if key in ('tasks','image_tasks'):
   details+=_task_details(before,after,key)
  else:details.append(LABELS.get(key,'其他项目数据（'+key+'）')+'已更新')
 if not details:details=['项目数据已保存']
 return {'id':row['id'],'created':row['created'],'kind':'change','title':'项目内容发生变化','details':details}

def list_steps(con,project_id,before=None,limit=30):
 if before is not None and (type(before) is not int or before<=0):raise ValueError('记录游标无效')
 if type(limit) is not int or not 1<=limit<=100:raise ValueError('记录数量无效')
 rows=con.execute('SELECT id,created,kind,before_body,after_body,note FROM project_steps WHERE project_id=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?', (project_id,before,before,limit+1)).fetchall()
 selected=rows[:limit];return {'steps':[describe(row) for row in selected],'next_before':selected[-1]['id'] if len(rows)>limit else None}

def add_note(con,project_id,note):
 if not isinstance(note,str) or not note.strip() or len(note.strip())>4000:raise ValueError('复盘内容须为1至4000字')
 con.execute('INSERT INTO project_steps(project_id,kind,note) VALUES (?,?,?)',(project_id,'note',note.strip()))
