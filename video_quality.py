"""Project video quality reference selection and advisory comparison."""
import hashlib
import math
import re
import statistics
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PROMPT = ('主体对焦清楚，角色和关键道具的结构与材质细节自然可辨；光线、色调和材质沿用项目风格。'
                  '避免整体发虚、过度磨皮、塑料质感和夸张锐化，按景别保留合理景深与运动模糊。')


def config(state):
    brief = state.get('project_brief') or {}
    value = brief.get('video_quality') if isinstance(brief, dict) else None
    return value if isinstance(value, dict) and value.get('enabled') is True else None


def accepted_file(state, root, task):
    if not task or task.get('status') != 'completed' or task.get('review_status') != 'accepted':
        raise ValueError('画质基准须是本项目已验收的视频')
    prefix = '/media/%s/' % state['project_id']
    url = task.get('local_video', '')
    if not isinstance(url, str) or not url.startswith(prefix):
        raise ValueError('画质基准尚未在本项目归档')
    folder = (Path(root) / 'assets' / str(state['project_id'])).resolve()
    path = (folder / url[len(prefix):]).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        raise ValueError('画质基准文件不可用')
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(f.read()).hexdigest()
    if digest != task.get('accepted_video_sha256'):
        raise ValueError('画质基准文件已变化，需要重新验收')
    return path, digest


def select_reference(state, shot, root, parent):
    profile = config(state)
    if not profile:
        return None, []
    task_id = profile.get('baseline_task_id')
    base = next((t for t in state.get('tasks', []) if t.get('id') == task_id), None)
    try:
        _, digest = accepted_file(state, root, base)
    except ValueError as error:
        return {'task_id': task_id, 'status': 'not_sent'}, [str(error)]
    if profile.get('baseline_sha256') != digest:
        return {'task_id':task_id,'status':'not_sent'}, ['画质基准版本已变化，请重新设置']
    is_minimax=state.get('settings',{}).get('provider')=='minimax'
    if base.get('provider') not in (('seedance25','minimax') if is_minimax else ('seedance25',)):
        return {'task_id':task_id,'status':'not_sent'}, ['当前画质基准不是可确认的Seedance原始视频，未自动传入']
    info = base.get('media_info') or {}
    seconds = info.get('duration')
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 2 <= seconds <= (15 if is_minimax else 30):
        return {'task_id':task_id,'status':'not_sent'}, ['画质基准视频时长不符合接口要求']
    result = {'task_id':task_id,'sha256':digest,'duration':seconds}
    if parent and parent['task_id'] == task_id:
        return {**result,'status':'shared_with_parent'}, []
    if base.get('segment_id') == shot.get('id'):
        return {**result,'status':'not_sent'}, ['画质基准属于当前片段，未将同一片段作为自己的额外参考']
    parsed = urllib.parse.urlparse(base.get('video_url',''))
    if parsed.scheme!='https' or parsed.username or parsed.password or not parsed.hostname or not any(parsed.hostname.endswith('.'+domain) for domain in (('volces.com','hailuoai.com','minimax.chat') if is_minimax else ('volces.com',))):
        return {**result,'status':'not_sent'}, ['画质基准缺少可用的方舟原始视频地址']
    issues=[]
    params={k.lower():v for k,v in urllib.parse.parse_qs(parsed.query).items()}
    if 'x-tos-date' in params or 'x-tos-expires' in params:
        try:
            start=datetime.strptime(params['x-tos-date'][0],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp()
            expires=int(params['x-tos-expires'][0])
            if expires<=0 or datetime.now(timezone.utc).timestamp()>=start+expires:
                issues.append('画质基准原始地址已过期，请刷新原任务或配置长期保存')
        except (KeyError,ValueError,IndexError,OverflowError):
            issues.append('画质基准地址的有效期无法核实，请刷新原任务')
    if parent and float(parent['duration']) + seconds > (15 if is_minimax else 30):
        issues.append('上一段与画质基准合计超过'+('MiniMax参考视频15秒' if is_minimax else '方舟参考视频30秒')+'上限；本次仅传上一段')
    if issues:return {**result,'status':'not_sent'}, issues
    return {**result,'status':'sent','url':base['video_url']}, []


def _blur_sample(path):
    result = subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vf',
                             'fps=1/3,scale=640:-2,blurdetect,metadata=print:file=-',
                             '-an','-f','null','-'],capture_output=True,text=True,timeout=90,check=True)
    values = [float(x) for x in re.findall(r'lavfi\.blur=([0-9]+(?:\.[0-9]+)?)',result.stdout)]
    if not values:
        raise ValueError('未获得可用画面样本')
    return {'median':round(statistics.median(values),3),'samples':len(values)}


def inspect(state, root, task):
    profile = config(state)
    if not profile:
        return None
    baseline = next((t for t in state.get('tasks',[]) if t.get('id') == profile.get('baseline_task_id')),None)
    try:
        base_path, digest = accepted_file(state,root,baseline)
        if digest != profile.get('baseline_sha256'):
            raise ValueError('画质基准文件已变化')
        url = task.get('local_video','');prefix='/media/%s/'%state['project_id']
        if not url.startswith(prefix):raise ValueError('候选视频尚未归档')
        folder=(Path(root)/'assets'/str(state['project_id'])).resolve();file=(folder/url[len(prefix):]).resolve()
        if not file.is_relative_to(folder) or not file.is_file():raise ValueError('候选视频不可用')
        base_result=_blur_sample(base_path);candidate=_blur_sample(file)
        with file.open('rb') as f:
            candidate_sha=hashlib.file_digest(f,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(f.read()).hexdigest()
        ratio=candidate['median']/base_result['median'] if base_result['median'] else None
        return {'baseline_task_id':baseline['id'],'baseline_sha256':digest,'candidate_sha256':candidate_sha,'baseline':base_result,'candidate':candidate,
                'ratio':round(ratio,3) if ratio is not None else None,'possible_softness':bool(ratio and ratio>=1.1),
                'method':'ffmpeg blurdetect，全画面每3秒抽样；数值越高通常越模糊',
                'note':'仅供人工对照：景别、运动、景深、画面内容和特效均会影响结果；不能判定实际质量或替代验收。'}
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        return {'status':'unavailable','note':'自动画质对照未完成，请手动比较画面：'+str(error)[:180]}
