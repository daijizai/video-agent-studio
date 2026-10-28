"""Bounded provider video caching and metadata, without forwarding credentials."""
import json,shutil,subprocess,urllib.request,urllib.parse
from pathlib import Path

def cache_video(root,project_id,task_id,url):
 p=urllib.parse.urlparse(url)
 if p.scheme!='https' or p.username or p.password or not p.hostname or not any(p.hostname.endswith('.'+d) for d in ('aliyuncs.com','alicdn.com','qianwenaiapi.com','volces.com','byteimg.com')):raise ValueError('不支持的模型视频下载域名')
 target=Path(root)/'assets'/str(project_id)/(task_id+'.mp4');target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():
  temp=target.with_suffix('.part')
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args,**kwargs):raise ValueError('不允许视频下载重定向')
  try:
   count=0
   with urllib.request.build_opener(NoRedirect).open(url,timeout=30) as response,open(temp,'wb') as out:
    while True:
     chunk=response.read(65536)
     if not chunk:break
     count+=len(chunk)
     if count>256*1024*1024:raise ValueError('视频超过256MB下载上限')
     out.write(chunk)
   with open(temp,'rb') as f:
    if b'ftyp' not in f.read(32):raise ValueError('输出不是支持的MP4')
   temp.replace(target)
  finally:
   if temp.exists():temp.unlink()
 return '/media/'+str(project_id)+'/'+task_id+'.mp4',probe_video(target)

def probe_video(path):
 if not shutil.which('ffprobe'):return {'verified':False,'note':'FFprobe未安装'}
 r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,codec_name,width,height','-of','json',str(path)],capture_output=True,text=True,timeout=15)
 if r.returncode:return {'verified':False,'note':'媒体元数据读取失败'}
 data=json.loads(r.stdout);video=next((s for s in data.get('streams',[]) if s.get('codec_type')=='video'),{})
 return {'verified':True,'duration':float(data.get('format',{}).get('duration',0)),'video':video,'has_audio':any(s.get('codec_type')=='audio' for s in data.get('streams',[]))}
