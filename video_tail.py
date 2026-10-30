"""Create a provenance-bound local reference tail without submitting a model request."""
import hashlib
import math
import os
import subprocess
import uuid
from pathlib import Path

import media_files


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def create(state, root, task_id, seconds):
    """Create a separate last-N-seconds MP4 from an accepted project video.

    The resulting local file is not an uploaded reference and carries no assertion
    that any provider will accept it, especially for face-containing material.
    """
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 2 <= seconds <= 30:
        raise ValueError('片尾时长须为 2 至 30 秒')
    project_id = state['project_id']
    task = next((t for t in state.get('tasks', []) if t.get('id') == task_id), None)
    if not task or task.get('status') != 'completed' or task.get('review_status') != 'accepted':
        raise ValueError('只能从本项目已验收的视频裁剪片尾')
    prefix = f'/media/{project_id}/'
    local = task.get('local_video', '')
    if not isinstance(local, str) or not local.startswith(prefix):
        raise ValueError('源视频尚未归档到本项目')
    folder = (Path(root) / 'assets' / str(project_id)).resolve()
    source = (folder / local[len(prefix):]).resolve()
    if not source.is_relative_to(folder) or not source.is_file():
        raise ValueError('源视频文件不可用')
    source_sha = _sha256(source)
    if source_sha != task.get('accepted_video_sha256'):
        raise ValueError('源视频与已验收版本不一致')
    info = media_files.probe_video(source)
    duration = info.get('duration', 0)
    if not info.get('verified') or not info.get('video') or duration < seconds:
        raise ValueError('源视频时长不足或视频格式不可用')
    start = max(0.0, duration - seconds)
    outdir = folder / 'reference-tails'
    outdir.mkdir(parents=True, exist_ok=True)
    clip_id = uuid.uuid4().hex
    target = outdir / (clip_id + '.mp4')
    temporary = outdir / (clip_id + '.part.mp4')
    try:
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', f'{start:.6f}', '-i', str(source),
               '-t', f'{seconds:.6f}', '-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', '-n', str(temporary)]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
        out = media_files.probe_video(temporary)
        actual = out.get('duration', 0)
        if not out.get('verified') or not out.get('video') or not 2 <= actual <= 30.05 or abs(actual - seconds) > .15:
            raise ValueError('片尾裁剪结果时长或格式不符合要求')
        if info.get('has_audio') and not out.get('has_audio'):
            raise ValueError('片尾缺少源视频音轨')
        clip_sha = _sha256(temporary)
        os.replace(temporary, target)
        return {'id': clip_id, 'source_task_id': task_id, 'source_sha256': source_sha,
                'start_seconds': round(start, 3), 'end_seconds': round(duration, 3),
                'duration_seconds': round(actual, 3), 'sha256': clip_sha,
                'relative_path': f'reference-tails/{clip_id}.mp4',
                'media_info': out, 'provider_usable': False,
                'provider_status': '本地裁剪完成；未上传，未验证平台素材审核条件'}
    finally:
        temporary.unlink(missing_ok=True)
