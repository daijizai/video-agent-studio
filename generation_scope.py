"""Repository-external, project/database-bound finite spending authorizations."""
import json,time,os,tempfile,uuid
from pathlib import Path
import secret_store

def path():return secret_store.secret_path().parent/'generation-authorizations.json'
def read():
 p=path()
 if not p.exists():return {}
 return json.loads(p.read_text())
def active(project_id,database):
 scope=read().get(str(project_id))
 return bool(scope and scope.get('database')==str(Path(database).resolve()) and scope.get('expires_at',0)>time.time())
def check(state,database,kind,estimate,model):
 if not active(state['project_id'],database):raise ValueError('当前项目没有有效的有限生成授权')
 scope=read()[str(state['project_id'])]
 if model not in scope['models']:raise ValueError('该模型不在本次Demo授权范围')
 images=[t for t in state.get('image_tasks',[]) if t.get('status')!='rejected'];videos=[t for t in state.get('tasks',[]) if t.get('status')!='rejected']
 rows=images if kind=='image' else videos
 if len(rows)>=scope['image_limit' if kind=='image' else 'video_limit']:raise ValueError('本次Demo已达到授权任务次数；不自动重试或增加次数')
 reserved=sum(float(t['estimate']) for t in images+videos)
 if reserved+estimate>min(float(scope['max_cny']),float(state['budget'])):raise ValueError('将超过本次Demo的固定授权预算')
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
