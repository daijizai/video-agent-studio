"""Repository-external, project/database-bound finite spending authorizations."""
import json,time,os,tempfile,uuid,sqlite3
from decimal import Decimal
from pathlib import Path
import secret_store

def path():return secret_store.secret_path().parent/'generation-authorizations.json'
def read():
 p=path()
 if not p.exists():return {}
 return json.loads(p.read_text())
def active(project_id,database):
 scope=read().get(str(project_id))
 return bool(scope and scope.get('database')==str(Path(database).resolve()) and (bool(scope.get('budget_grants')) or scope.get('expires_at',0)>time.time()))
def check(state,database,kind,estimate,model,shot_id=None):
 if not active(state['project_id'],database):raise ValueError('当前项目没有有效的有限生成授权')
 scope=read()[str(state['project_id'])]
 if model not in scope['models']:raise ValueError('该模型不在本次Demo授权范围')
 if scope.get('budget_mode')=='separate_v1':
  grant=scope.get('budget_grants',{}).get(kind)
  if not grant:raise ValueError('该类别预算尚未获得明确授权')
  ledger=category_ledger(state,kind,grant['limit'])
  if Decimal(str(ledger['committed_cny']))+Decimal(str(estimate))>Decimal(str(grant['limit'])):raise ValueError(('图片' if kind=='image' else '视频')+'独立预算不足；不能挪用另一类别额度')
  return grant['id']
 images=[t for t in state.get('image_tasks',[]) if t.get('status')!='rejected'];videos=[t for t in state.get('tasks',[]) if t.get('status')!='rejected']
 rows=images if kind=='image' else videos
 if len(rows)>=scope['image_limit' if kind=='image' else 'video_limit']:raise ValueError('本次Demo已达到授权任务次数；不自动重试或增加次数')
 if kind=='image' and len(images)>=scope.get('base_image_limit',scope['image_limit']):
  allowed=False
  for extension in scope.get('extensions',[]):
   if shot_id not in extension['shot_ids']:continue
   added=[t for t in images if t['id'] not in extension['baseline_task_ids']]
   cost=sum((Decimal(str(t['estimate'])) for t in added),Decimal('0'))
   if sum(t['shot_id']==shot_id for t in added)<1 and cost+Decimal(str(estimate))<=Decimal(str(extension['max_extra_cny'])):allowed=True
  if not allowed:raise ValueError('该镜头没有剩余的指定增量授权；不扩大其他镜头次数')
 reserved=sum((Decimal(str(t['estimate'])) for t in images+videos),Decimal('0'))
 if reserved+Decimal(str(estimate))>min(Decimal(str(scope['max_cny'])),Decimal(str(state['budget']))):raise ValueError('将超过本次Demo的固定授权预算')
 return scope['id']
def grant(project_id,database,max_cny=11,image_limit=6,video_limit=1):
 p=path();p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);p.parent.chmod(0o700)
 data=read();key=str(project_id)
 if key in data:raise ValueError('已有项目授权，不覆盖、不自动扩大额度')
 data[key]={'id':str(uuid.uuid4()),'database':str(Path(database).resolve()),'max_cny':max_cny,'image_limit':image_limit,'video_limit':video_limit,'models':['qwen-image-3.0','wan3.0-video'],'expires_at':time.time()+86400,'purpose':'用户明确授权的单次30秒有声Demo；不充值；图像须展示审阅后才可提交视频'}
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.generation-')
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'w') as f:json.dump(data,f)
  os.replace(tmp,p);p.chmod(0o600)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return {'project_id':project_id,'max_cny':max_cny,'image_limit':image_limit,'video_limit':video_limit,'scope_id':data[key]['id']}

def extend_images(project_id,database,shot_ids,max_extra_cny,note):
 """Human-authorized, finite, named-shot extension; never called by polling or HTTP."""
 if not active(project_id,database):raise ValueError('原项目授权不存在或已过期')
 if len(set(shot_ids))!=len(shot_ids) or not shot_ids:raise ValueError('指定镜头清单无效')
 with sqlite3.connect(database) as c:
  row=c.execute('SELECT body FROM state WHERE id=?',(project_id,)).fetchone()
  state=json.loads(row[0])
 if not set(shot_ids).issubset({s['id'] for s in state['shots']}):raise ValueError('镜头不属于该项目')
 images=[t for t in state.get('image_tasks',[]) if t['status']!='rejected']
 if any(t['status'] in ('submitting','queued','running','unknown') for t in images):raise ValueError('先核对在途任务，不借增量绕过unknown')
 data=read();scope=data[str(project_id)]
 if any(set(shot_ids)&set(e['shot_ids']) for e in scope.get('extensions',[])):raise ValueError('这些镜头已有增量授权，不重复扩大')
 reserved=sum((Decimal(str(t['estimate'])) for t in images+state.get('tasks',[])),Decimal('0'))
 if Decimal(str(max_extra_cny))<=0 or reserved+Decimal(str(max_extra_cny))>Decimal(str(scope['max_cny'])):raise ValueError('增量超出原总预算')
 scope.setdefault('base_image_limit',scope['image_limit'])
 extension={'id':str(uuid.uuid4()),'shot_ids':list(shot_ids),'baseline_task_ids':[t['id'] for t in images],'max_extra_cny':max_extra_cny,'per_shot_limit':1,'note':note,'authorized_at':time.time()}
 scope.setdefault('extensions',[]).append(extension);scope['image_limit']+=len(shot_ids)
 p=path();fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.generation-')
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'w') as f:json.dump(data,f)
  os.replace(tmp,p);p.chmod(0o600)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return {'project_id':project_id,'extension_id':extension['id'],'named_shots':len(shot_ids),'additional_images':len(shot_ids),'additional_cny_cap':max_extra_cny,'total_cny_cap':scope['max_cny'],'video_limit':scope['video_limit']}

def category_ledger(state,kind,limit=None):
 rows=state.get('image_tasks',[]) if kind=='image' else state.get('tasks',[])
 known=Decimal('0');committed=Decimal('0');inflight=Decimal('0');unsettled=Decimal('0');unknown=0
 for task in rows:
  if task.get('status')=='rejected':continue
  estimate=Decimal(str(task.get('estimate',0)));actual=task.get('actual_cost_cny');live=task.get('status') in ('submitting','queued','running','unknown')
  if actual is None:
   unknown+=1;committed+=estimate
   if live:inflight+=estimate
   else:unsettled+=estimate
  else:
   if live:unknown+=1
   value=Decimal(str(actual));known+=value;committed+=max(value,estimate) if live else value
   if live:inflight+=max(value,estimate)-value
 return {'limit_cny':limit,'actual_known_cny':float(known),'actual_total_cny':float(known) if unknown==0 else None,'actual_unknown_tasks':unknown,'committed_cny':float(committed),'inflight_reserved_cny':float(inflight),'unsettled_reserved_cny':float(unsettled),'remaining_cny':float(Decimal(str(limit))-committed) if limit is not None else None,'billing_complete':unknown==0}
def budget_summary(state,database):
 scope=read().get(str(state['project_id']),{}) if active(state['project_id'],database) else {}
 grants=scope.get('budget_grants',{}) if scope.get('budget_mode')=='separate_v1' else {}
 return {kind:{**category_ledger(state,kind,grants.get(kind,{}).get('limit')),'authorized':kind in grants,'authorization':grants.get(kind)} for kind in ('image','video')}
def authorize_budgets(project_id,database,image_limit,video_limit,source,content_revision):
 from math import isfinite
 for amount in (image_limit,video_limit):
  if type(amount) not in (int,float) or not isfinite(amount) or not 0<=amount<=100000:raise ValueError('分类预算须为0–100000的明确金额')
 data=read();key=str(project_id);scope=data.get(key)
 if scope and scope.get('database')!=str(Path(database).resolve()):raise ValueError('项目与数据库绑定不匹配')
 if not scope:scope={'id':str(uuid.uuid4()),'database':str(Path(database).resolve()),'models':['qwen-image-3.0','wan3.0-video'],'image_limit':0,'video_limit':0};data[key]=scope
 version=len(scope.get('budget_authorization_history',[]))+1
 record={'version':version,'source':secret_store.redact(source),'content_revision':content_revision,'authorized_at':time.time(),'image_limit':image_limit,'video_limit':video_limit,'quality_approval':False}
 scope.setdefault('budget_authorization_history',[]).append(record);scope['budget_mode']='separate_v1'
 scope['budget_grants']={kind:{'id':str(uuid.uuid4()),'limit':amount,'version':version,'source':secret_store.redact(source),'content_revision':content_revision,'authorized_at':record['authorized_at'],'purpose':'图片制作与必要修复' if kind=='image' else '视频制作；仍须画面质量与阶段批准'} for kind,amount in (('image',image_limit),('video',video_limit))}
 p=path();p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);p.parent.chmod(0o700);fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.generation-')
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'w') as f:json.dump(data,f)
  os.replace(tmp,p);p.chmod(0o600)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return record
