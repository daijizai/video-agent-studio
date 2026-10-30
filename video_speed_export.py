"""Local, bounded, asynchronous exports of the current project's completed video."""
import hashlib
import math
import os
import re
import subprocess
import threading
import uuid
from pathlib import Path

import media_files

_lock=threading.Lock()
_jobs={}


def _digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def start(state,root,rate,expected_sha256,expected_url=None):
    if type(rate) not in (float,int) or not math.isfinite(rate) or not 1.1<=rate<=2.0 or abs(rate*10-round(rate*10))>1e-8:
        raise ValueError('倍速须为1.1至2.0，每次增加0.1')
    pid=state['project_id'];final=state.get('final_video') or {};url=final.get('local_url','')
    prefix=f'/media/{pid}/'
    if not isinstance(url,str) or not re.fullmatch(re.escape(prefix)+r'[A-Za-z0-9_-]+\.mp4',url):
        raise ValueError('当前项目没有可导出的完整视频')
    folder=(Path(root)/'assets'/str(pid)).resolve();source=(folder/url[len(prefix):]).resolve()
    if not source.is_relative_to(folder) or not source.is_file():raise ValueError('完整视频文件不可用')
    digest=_digest(source)
    if final.get('sha256') and digest!=final['sha256']:raise ValueError('完整视频文件已变化，请先重新确认成片')
    if expected_sha256!=digest and not (not final.get('sha256') and expected_url==url):raise ValueError('成片已更新，请刷新页面后重新选择倍速')
    info=media_files.probe_video(source)
    if not info.get('verified') or not info.get('video') or not 0<info.get('duration',0)<=3600:raise ValueError('视频格式或时长不受支持')
    rate=round(rate,1)
    with _lock:
        for job in _jobs.values():
            if job['project_id']==pid and job['status']=='running':
                if job['source_sha256']==digest and job['rate']==rate:return _public(job)
                raise ValueError('当前项目已有倍速导出正在进行，请稍候')
        if sum(j['status']=='running' for j in _jobs.values())>=2:raise ValueError('已有其他倍速导出正在进行，请稍候')
        job={'id':uuid.uuid4().hex,'project_id':pid,'source_sha256':digest,'rate':rate,'status':'running','progress':0,'duration':info['duration']}
        _jobs[job['id']]=job
    threading.Thread(target=_run,args=(job,source,folder,info),daemon=True).start()
    return _public(job)


def _public(job):
    return {k:v for k,v in job.items() if k in ('id','status','progress','rate','url','error','output_duration')}


def status(project_id,job_id):
    with _lock:
        job=_jobs.get(job_id)
        if not job or job['project_id']!=project_id:raise ValueError('导出任务不存在或不属于当前项目')
        return _public(job)


def _run(job,source,folder,info):
    name='speed_'+job['id']+'.mp4';target=folder/name;temp=folder/('speed_'+job['id']+'.part.mp4')
    try:
        rate=job['rate'];cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostats','-progress','pipe:1','-i',str(source),
            '-map','0:v:0','-filter:v',f'setpts=PTS/{rate:.1f}','-c:v','libx264','-preset','fast','-crf','18',
            '-fps_mode','cfr']
        if info.get('has_audio'):
            cmd+=['-map','0:a:0','-filter:a',f'atempo={rate:.1f}','-c:a','aac','-b:a','160k']
        cmd+=['-movflags','+faststart','-n',str(temp)]
        with subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True) as process:
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try:
                        seconds=int(line.split('=',1)[1])/1000000
                        with _lock:job['progress']=min(99,max(0,int(seconds/(info['duration']/rate)*100)))
                    except ValueError:pass
            if process.wait()!=0:raise RuntimeError('视频转码失败')
        if _digest(source)!=job['source_sha256']:raise RuntimeError('原视频在导出期间发生变化')
        out=media_files.probe_video(temp);expected=info['duration']/rate
        if not out.get('verified') or not out.get('video') or (info.get('has_audio') and not out.get('has_audio')) or abs(out.get('duration',0)-expected)>max(.25,expected*.02):
            raise RuntimeError('导出的视频时长或音轨校验失败')
        os.replace(temp,target)
        with _lock:job.update(status='completed',progress=100,url=f'/media/{job["project_id"]}/{name}',output_duration=out['duration'])
    except Exception:
        temp.unlink(missing_ok=True)
        with _lock:job.update(status='failed',error='导出未完成，请检查本地空间和视频后重试')
