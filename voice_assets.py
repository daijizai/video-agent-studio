"""Project-scoped voice candidates extracted from accepted video audio."""
import copy,hashlib,math,re,subprocess,uuid,wave
from pathlib import Path

def operate(state,root,action,p):
    items=state.setdefault('voice_assets',[]);pid=state['project_id'];root=Path(root)
    if action=='create':
        name=p.get('name');task_id=p.get('source_task_id');start=p.get('start');end=p.get('end')
        if not isinstance(name,str) or not name.strip() or len(name)>80:raise ValueError('声音名称无效')
        if name not in [c.get('name') for c in state.get('characters',[])]:raise ValueError('声音须绑定本项目已有角色')
        if type(start) not in (int,float) or type(end) not in (int,float) or not math.isfinite(start) or not math.isfinite(end) or start<0 or not 2<=end-start<=30:raise ValueError('声音时间段须为2至30秒')
        task=next((t for t in state.get('tasks',[]) if t['id']==task_id and t['status']=='completed' and t.get('review_status')=='accepted'),None)
        if not task:raise ValueError('声音来源须为已验收视频')
        url=task.get('local_video','');prefix=f'/media/{pid}/'
        if not url.startswith(prefix):raise ValueError('已验收视频尚未归档')
        folder=(root/'assets'/str(pid)).resolve();video=(folder/url.removeprefix(prefix)).resolve()
        if not video.is_relative_to(folder) or not video.is_file():raise ValueError('源视频不可用')
        digest=hashlib.sha256(video.read_bytes()).hexdigest()
        if digest!=task.get('accepted_video_sha256'):raise ValueError('源视频与验收版本不一致')
        length=float((task.get('media_info') or {}).get('duration',0))
        if length<=0 or end>length+.02:raise ValueError('声音时间段超出源视频')
        prior=next((a for a in items if a['character_name']==name),None)
        if prior and any(v['source_task_id']==task_id and v['start']==start and v['end']==end for v in prior['versions']):raise ValueError('这个声音片段已在素材库中')
        directory=folder/'voice';directory.mkdir(parents=True,exist_ok=True);id=uuid.uuid4().hex;path=directory/(id+'.wav')
        try:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(start),'-i',str(video),'-t',str(end-start),'-map','0:a:0','-vn','-ac','1','-ar','24000','-c:a','pcm_s16le','-n',str(path)],check=True,capture_output=True,timeout=30)
            with wave.open(str(path),'rb') as f:duration=f.getnframes()/f.getframerate()
            if not 2<=duration<=30 or path.stat().st_size>15*1024*1024:raise ValueError('提取声音的时长或大小不符合要求')
            v={'version':len(prior['versions'])+1 if prior else 1,'id':id,'url':f'/voice-media/{pid}/{id}.wav','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'duration':round(duration,3),'source_task_id':task_id,'source_video_sha256':digest,'start':start,'end':end,'review_status':'candidate','method':'按时间切段，未进行声源分离；说话人归属和串音待试听确认'}
            if prior:prior['versions'].append(v);prior['latest_version']=v['version']
            else:items.append({'id':'voice-'+uuid.uuid4().hex,'kind':'voice','name':name+'的声音','character_name':name,'latest_version':1,'adopted_version':None,'versions':[v]})
        except Exception:
            path.unlink(missing_ok=True);raise
        return
    if action=='adopt':
        asset=next((a for a in items if a['id']==p.get('asset_id')),None);number=p.get('version')
        version=next((v for v in asset['versions'] if v['version']==number),None) if asset and type(number) is int else None
        if not version:raise ValueError('声音版本不存在')
        path=(root/'assets'/str(pid)/'voice'/(version['id']+'.wav')).resolve();folder=(root/'assets'/str(pid)/'voice').resolve()
        if not path.is_relative_to(folder) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=version['sha256']:raise ValueError('声音文件已变化或不可用')
        asset['adopted_version']=number;version['review_status']='accepted';version['review_source']='用户在素材库试听并明确采用'
        return
    raise ValueError('未知声音素材操作')

def audio_data(state,root,project_id,voice_id):
    if state.get('project_id')!=project_id:raise ValueError('声音不属于当前项目')
    entry=next((v for a in state.get('voice_assets',[]) for v in a['versions'] if v['id']==voice_id),None)
    if not entry:raise ValueError('声音素材不存在')
    folder=(Path(root)/'assets'/str(project_id)/'voice').resolve();path=(folder/(voice_id+'.wav')).resolve()
    if not path.is_relative_to(folder) or not path.is_file():raise ValueError('声音文件不可用')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('声音文件已变化')
    return data
