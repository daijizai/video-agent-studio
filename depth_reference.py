"""Verified, project-scoped depth-motion reference with private signed URL."""
import hashlib,json,math,re,time,urllib.parse
from pathlib import Path

def load(root,project_id):
    root=Path(root).resolve(); private=root.parent/'.video-agent-studio-private'
    if type(project_id) is not int or project_id<1:raise ValueError('项目编号无效')
    meta=private/('depth-reference-%d.json'%project_id)
    if not meta.is_file() or meta.is_symlink():raise ValueError('本项目尚未准备深度视频')
    data=json.loads(meta.read_text())
    if data.get('project_id')!=project_id or not isinstance(data.get('file'),str) or not re.fullmatch(r'reference/[A-Za-z0-9_-]+\.mp4',data['file']):raise ValueError('深度视频记录无效')
    file=root/'assets'/str(project_id)/data['file']
    if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to((root/'assets'/str(project_id)).resolve()):raise ValueError('深度视频文件不可用')
    sha=hashlib.sha256(file.read_bytes()).hexdigest()
    if sha!=data.get('sha256'):raise ValueError('深度视频已变化，请重新审阅')
    if not isinstance(data.get('expires_at'),(int,float)) or data['expires_at']<=time.time()+600:raise ValueError('深度视频云端地址已过期，请重新获取')
    url=data.get('url','');parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password or not parsed.hostname or not parsed.hostname.endswith(('.volces.com','.volcvideo.com')):raise ValueError('深度视频云端地址无效')
    duration=data.get('duration')
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 2<=duration<=30:raise ValueError('深度视频时长无效')
    return {'url':url,'sha256':sha,'duration':duration,'name':'深度动作参考视频','task_id':data['task_id']}
