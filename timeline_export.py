"""Project-scoped, non-destructive local video timeline exports."""
import hashlib,math,os,re,subprocess,threading,uuid
from pathlib import Path
import media_files
_lock=threading.Lock();_jobs={}
MAX_UPPER_BYTES=128*1024*1024

def import_upper(root,project_id,name,stream,size):
 if not 0<size<=MAX_UPPER_BYTES:raise ValueError('请选择不超过128MB的MP4')
 folder=(Path(root)/'assets'/str(project_id)).resolve()
 folder.mkdir(parents=True,exist_ok=True)
 target=folder/('upper_'+uuid.uuid4().hex+'.mp4')
 temp=target.with_suffix('.part')
 try:
  with temp.open('xb') as file:
   remaining=size
   while remaining:
    chunk=stream.read(min(remaining,1024*1024))
    if not chunk:raise ValueError('上传未完成，请重新选择文件')
    file.write(chunk);remaining-=len(chunk)
  with temp.open('rb') as file:
   if file.read(8)[4:]!=b'ftyp':raise ValueError('请选择MP4视频')
  info=media_files.probe_video(temp)
  duration=info.get('duration',0)
  if not info.get('verified') or not info.get('video') or not math.isfinite(duration) or duration<.1:
   raise ValueError('MP4中没有可用的视频画面')
  digest=_sha(temp)
  temp.replace(target)
  return {'name':Path(name).name[:160] or '上半屏视频', 'url':f'/media/{project_id}/{target.name}',
          'duration':duration,'sha256':digest},target
 finally:temp.unlink(missing_ok=True)

def _sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
 return h.hexdigest()
def _public(job):return {k:v for k,v in job.items() if k in ('id','status','error','url','duration')}
def start(state,root,clips,include_music=False,upper=None):
 if not isinstance(clips,list) or not 1<=len(clips)<=30:raise ValueError('请选择1至30段视频')
 pid=state['project_id'];folder=(Path(root)/'assets'/str(pid)).resolve();prepared=[]
 for item in clips:
  if not isinstance(item,dict):raise ValueError('片段格式无效')
  t=next((t for t in state.get('tasks',[]) if t.get('id')==item.get('task_id') and t.get('status')=='completed' and t.get('review_status')!='rejected_quality'),None)
  if not t:raise ValueError('请选择本项目可用的视频')
  url=t.get('local_video','');prefix='/media/%d/'%pid
  if not re.fullmatch(re.escape(prefix)+r'[A-Za-z0-9_-]+\.mp4',url):raise ValueError('视频尚未归档')
  path=(folder/url[len(prefix):]).resolve()
  if not path.is_relative_to(folder) or not path.is_file():raise ValueError('视频文件不可用')
  info=media_files.probe_video(path)
  if not info.get('verified') or not info.get('video'):raise ValueError('视频无法读取')
  start,end=item.get('start'),item.get('end')
  if type(start) not in (int,float) or type(end) not in (int,float) or not math.isfinite(start) or not math.isfinite(end) or start<0 or end-start<.1 or end>info['duration']+.05:raise ValueError('裁剪范围无效')
  end=min(end,info['duration']);digest=_sha(path)
  if t.get('accepted_video_sha256') and digest!=t['accepted_video_sha256']:raise ValueError('已审阅视频文件已变化')
  prepared.append({'path':path,'start':float(start),'end':float(end),'info':info,'sha':digest})
 dims={(x['info']['video'].get('width'),x['info']['video'].get('height')) for x in prepared}
 if len(dims)!=1:raise ValueError('当前导出仅支持画面尺寸一致的视频')
 formats={x['info']['video'].get('pix_fmt') for x in prepared}
 if formats!={'yuv420p'}:raise ValueError('当前画面无损导出仅支持 yuv420p 视频')
 rates={(x['info']['video'].get('avg_frame_rate'),x['info']['video'].get('r_frame_rate')) for x in prepared}
 if rates!={('24/1','24/1')}:raise ValueError('当前画面无损导出仅支持帧率一致的24帧视频')
 colors={tuple(x['info']['video'].get(k) for k in ('color_range','color_space','color_transfer','color_primaries')) for x in prepared}
 if len(colors)!=1:raise ValueError('视频色彩信息不一致，无法直接无损拼接')
 music=None
 if include_music:
  cfg=(state.get('project_brief') or {}).get('timeline_audio') or {};url=cfg.get('url','');prefix='/media/%d/'%pid
  if not re.fullmatch(re.escape(prefix)+r'[A-Za-z0-9_-]+\.mp4',url):raise ValueError('音轨尚未配置')
  path=(folder/url[len(prefix):]).resolve()
  if not path.is_relative_to(folder) or not path.is_file() or not media_files.probe_video(path).get('has_audio'):raise ValueError('音轨不可用')
  music={'path':path,'sha':_sha(path)}
 if upper is not None:
  if not isinstance(upper,dict):raise ValueError('上半屏配置无效')
  cfg=(state.get('project_brief') or {}).get('timeline_upper') or {}
  url=cfg.get('url','');prefix=f'/media/{pid}/'
  if url!=upper.get('url') or not re.fullmatch(re.escape(prefix)+r'upper_[a-f0-9]{32}\.mp4',url):
   raise ValueError('请重新选择本项目的上半屏视频')
  path=(folder/url[len(prefix):]).resolve()
  if not path.is_relative_to(folder) or not path.is_file() or _sha(path)!=cfg.get('sha256'):
   raise ValueError('上半屏视频已变化，请重新导入')
  start_at=upper.get('start');total=sum(c['end']-c['start'] for c in prepared)
  if type(start_at) not in (int,float) or not math.isfinite(start_at) or start_at<0 or start_at+total>cfg['duration']+.04:
   raise ValueError('上半屏剩余时长不足，请提前起点或缩短下半屏')
  upper={'path':path,'sha':cfg['sha256'],'start':start_at}
 with _lock:
  if any(j['project_id']==pid and j['status']=='running' for j in _jobs.values()):raise ValueError('已有导出正在进行，请稍候')
  job={'id':uuid.uuid4().hex,'project_id':pid,'status':'running'};_jobs[job['id']]=job
 threading.Thread(target=_run,args=(job,prepared,folder,music,upper),daemon=True).start();return _public(job)
def status(project_id,job_id):
 with _lock:
  j=_jobs.get(job_id)
  if not j or j['project_id']!=project_id:raise ValueError('导出任务不存在或不属于当前项目')
  return _public(j)
def _run(job,clips,folder,music=None,upper=None):
 name='edit_'+job['id']+'.mp4';target=folder/name;temp=folder/('edit_'+job['id']+'.part.mp4')
 try:
  cmd=['ffmpeg','-hide_banner','-loglevel','error']
  for c in clips:cmd+=['-i',str(c['path'])]
  if music:cmd+=['-i',str(music['path'])]
  if upper:cmd+=['-i',str(upper['path'])]
  filters=[];any_audio=any(c['info']['has_audio'] for c in clips)
  total=sum(c['end']-c['start'] for c in clips)
  for i,c in enumerate(clips):
   st,en=c['start'],c['end'];filters.append(f'[{i}:v:0]trim=start={st:.6f}:end={en:.6f},setpts=PTS-STARTPTS[v{i}]')
   if any_audio:
    if c['info']['has_audio']:filters.append(f'[{i}:a:0]atrim=start={st:.6f}:end={en:.6f},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]')
    else:filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={en-st:.6f},asetpts=PTS-STARTPTS[a{i}]')
  inputs=''.join(f'[v{i}]'+(f'[a{i}]' if any_audio else '') for i in range(len(clips)))
  base='base' if upper else 'vout'
  filters.append(inputs+f'concat=n={len(clips)}:v=1:a={1 if any_audio else 0}[{base}]'+('[aout]' if any_audio else ''))
  if upper:
   idx=len(clips)+int(bool(music));start=upper['start']
   filters.append(f'[{idx}:v:0]trim=start={start:.6f}:end={start+total:.6f},setpts=PTS-STARTPTS,'
                  'fps=24,tpad=stop_mode=clone:stop_duration=0.05,'
                  'scale=1080:608:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                  'pad=1080:608:(ow-iw)/2:(oh-ih)/2,pad=1080:648:0:0,setsar=1,format=yuv420p[upper]')
   filters.append('[base]fps=24,scale=1080:608:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                  'pad=1080:608:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[lower]')
   # Keep a 40px divider and place the rest of the black space at the outer edges.
   filters.append('[upper][lower]vstack=inputs=2:shortest=1,pad=1080:1440:0:84[vout]')
  if music:
   idx=len(clips)
   filters.append(f'[{idx}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={total:.6f},asetpts=PTS-STARTPTS[music]')
   if any_audio:filters.append('[aout][music]amix=inputs=2:duration=first:normalize=0[finalaudio]')
   else:filters.append('[music]anull[finalaudio]')
  cmd+=['-filter_complex',';'.join(filters),'-map','[vout]']
  if music or any_audio:cmd+=['-map','[finalaudio]' if music else '[aout]','-c:a','aac' if upper else 'alac']
  cmd+=['-c:v','libx264','-preset','fast','-crf','18' if upper else '0','-pix_fmt','yuv420p','-fps_mode','passthrough','-movflags','+faststart','-n',str(temp)]
  subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
  if music and _sha(music['path'])!=music['sha']:raise ValueError('音轨发生变化')
  if upper and _sha(upper['path'])!=upper['sha']:raise ValueError('上半屏视频发生变化')
  if any(_sha(c['path'])!=c['sha'] for c in clips):raise ValueError('原视频发生变化')
  info=media_files.probe_video(temp)
  if not info.get('verified') or abs(info['duration']-total)>(.09 if upper else .3) or ((any_audio or music) and not info['has_audio']):raise ValueError('导出时长或声音校验失败')
  os.replace(temp,target)
  with _lock:job.update(status='completed',url=f'/media/{job["project_id"]}/{name}',duration=info['duration'])
 except Exception:
  temp.unlink(missing_ok=True)
  with _lock:job.update(status='failed',error='导出失败，请检查片段与本地磁盘后重试')
