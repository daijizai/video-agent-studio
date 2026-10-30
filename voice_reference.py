"""Record a shared audio anchor from the first accepted segment; never infer speakers."""
import hashlib,subprocess,wave
from pathlib import Path

def extract_initial(state,segment,task,root):
    formal=sorted((s for s in state.get('video_segments',[]) if not s.get('legacy_task_ids')),key=lambda s:s.get('order',0))
    if not formal or formal[0]['id']!=segment['id']:return None
    brief=state.get('project_brief') or {};brief=brief if isinstance(brief,dict) else {'summary':brief}
    if brief.get('voice_reference'):return None
    local=task.get('local_video','');prefix='/media/'+str(state['project_id'])+'/'
    if not local.startswith(prefix):return '首段声音参考未准备：视频未归档'
    folder=(Path(root)/'assets'/str(state['project_id'])).resolve();video=(folder/local.removeprefix(prefix)).resolve()
    if not video.is_relative_to(folder) or not video.is_file():return '首段声音参考未准备：源视频不可用'
    audio_folder=folder/'audio';audio_folder.mkdir(parents=True,exist_ok=True)
    name='opening-voice-reference-'+task['id'][:8]+'.wav';output=audio_folder/name
    try:
        if not output.exists():
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(video),'-map','0:a:0','-vn','-t','30','-ac','1','-ar','24000','-c:a','pcm_s16le','-n',str(output)],check=True,capture_output=True,timeout=60)
        with wave.open(str(output),'rb') as w:duration=w.getnframes()/w.getframerate()
        if not 2<=duration<=30 or output.stat().st_size>15*1024*1024:return '首段音轨不满足声音参考格式或长度要求'
        speakers=list(dict.fromkeys(c.get('name') for c in state.get('characters',[]) if isinstance(c.get('name'),str) and c['name'].strip()))
        if not speakers:return '首段音轨已提取，待登记角色'
        record={'enabled':True,'source_task_id':task['id'],'source_video_sha256':task['accepted_video_sha256'],'relative_path':'audio/'+name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'duration':round(duration,3),'expected_speakers':speakers,'mapping_status':'用户已确认首段整体；各角色声音在混合音轨中的覆盖与归属待核对'}
        brief['voice_reference']=record;state['project_brief']=brief;return record
    except (subprocess.SubprocessError,OSError,wave.Error,ZeroDivisionError):return '首段音轨提取失败，请检查是否含音频'
