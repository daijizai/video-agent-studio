"""Pinned Ark contracts. Prepare is offline; no activation, recharge or retry."""
from decimal import Decimal, ROUND_UP
import re, urllib.parse
import providers, secret_store

VIDEO_MODEL='doubao-seedance-2-5-260628'
IMAGE_MODEL='doubao-seedream-5-0-flash-260915'
BASE='https://ark.cn-beijing.volces.com/api/v3'

def references(values,limit):
    if not isinstance(values,list) or len(values)>limit:raise ValueError('参考图数量超限')
    for url in values:
        if not isinstance(url,str):raise ValueError('参考图URL必须为字符串')
        p=urllib.parse.urlparse(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('方舟参考图需为无凭据的HTTPS图片URL；不能直接使用千问临时OSS地址')
        if p.path.lower().endswith(('.mp4','.mov','.mp3','.wav')):raise ValueError('本次工作台适配仅开放图片参考；视频/音频参考需单独核价')
    return values

def headers():
    key=secret_store.get_key('ARK_API_KEY')
    if not key:raise ValueError('请先配置方舟 ARK_API_KEY')
    return {'Authorization':'Bearer '+key,'Content-Type':'application/json'}

def video_references(shot):
    return references([shot['storyboard_image']] if shot.get('storyboard_image') else shot.get('reference_images',[]),30)

def reference_binding(shot):
    return {'version':1,'model':VIDEO_MODEL,'image_task_id':shot.get('storyboard_task_id'),
            'image_sha256':shot.get('storyboard_sha256'),'urls':list(video_references(shot))}

def require_reference_approval(shot):
    if shot.get('ark_reference_approval')!=reference_binding(shot):
        raise ValueError('方舟参考图绑定尚未批准或已变化；请审阅当前实际参考后重新批准，历史成片审批保留')

def prepare_video(shot,config):
    duration=float(shot['duration'])
    if not duration.is_integer() or not 4<=duration<=30:raise ValueError('Seedance 2.5支持4–30秒整数时长')
    refs=video_references(shot)
    prompt=str(shot.get('prompt','')).strip()
    if not prompt:raise ValueError('镜头提示词不能为空')
    resolution=config.get('resolution','720p');ratio=config.get('ratio','16:9');audio=config.get('audio',False)
    if resolution not in ('480p','720p','1080p') or ratio not in ('16:9','9:16','1:1'):raise ValueError('未支持的Seedance分辨率或画幅')
    if type(audio) is not bool:raise ValueError('audio必须为布尔值')
    payload={'model':VIDEO_MODEL,'content':[{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':u},'role':'reference_image'} for u in refs],
             'resolution':resolution,'ratio':ratio,'duration':int(duration),'generate_audio':audio,'watermark':True,'output_format':'mp4',
             'omni_reference_task_type':'reference'}
    # Official output dimensions for this pinned model, not input image dimensions.
    dimensions={'480p':{'16:9':(854,480),'9:16':(480,854),'1:1':(640,640)},
                '720p':{'16:9':(1280,720),'9:16':(720,1280),'1:1':(960,960)},
                '1080p':{'16:9':(1920,1080),'9:16':(1080,1920),'1:1':(1440,1440)}}
    width,height=dimensions[resolution][ratio]
    tokens=Decimal(width*height*24*int(duration))/1024
    # Reserve one extra second for frame rounding; this is a budget estimate, not billing.
    reserved_tokens=Decimal(width*height*24*(int(duration)+1))/1024
    rate=Decimal('0.077' if resolution=='1080p' else '0.07')
    estimate=(reserved_tokens*rate/1000).quantize(Decimal('.01'),rounding=ROUND_UP)
    return {'provider':'seedance25','payload':payload,'estimated_cny':float(estimate),'currency':'CNY','network_called':False,'price_checked':'2026-10-28',
            'estimate_basis':{'width':width,'height':height,'fps':24,'planned_tokens':float(tokens),'reserved_seconds':int(duration)+1,'cny_per_1000_tokens':float(rate)},
            'note':'仅图片/文字输入；¥'+str(rate)+'/千视频tokens，按官方输出尺寸×24fps并预留1秒帧舍入余量，非账单或价格上限；含真人人脸参考受平台限制',
            'warnings':['参考素材合规性须人工审阅；写实人物参考不能默认可用；仅完成请求构造，未实测生成']}

class SeedreamProvider:
    def __init__(self,request=None):self.request=request or providers.transport
    def headers(self):return headers()
    def prepare(self,shot,defaults=None):
        from image_provider import STATIC_FRAME_PREFIX,prompt_warnings
        prompt=str(shot.get('image_prompt') or shot.get('prompt') or '').strip()
        if not prompt:raise ValueError('请先填写关键帧画面描述')
        refs=references(shot.get('reference_images',[]),10) # Seedream 5.0 Flash documented limit.
        raw=shot.get('image_size','720*1280')
        if raw not in ('720*1280','1280*720','1024*1024','1536*2048','2048*1536','2048*2048','2048*1152'):raise ValueError('未支持的关键帧画幅')
        w,h=map(int,raw.split('*'))
        shape='竖版' if w<h else '横版' if w>h else '正方形'
        payload={'model':IMAGE_MODEL,'prompt':STATIC_FRAME_PREFIX+'\n'+prompt+'\n画幅：'+shape+'，宽高比 '+str(w)+':'+str(h),'size':'2K','response_format':'url','output_format':'png','watermark':True,'stream':False}
        if refs:payload['image']=refs
        return {'provider':'seedream','payload':payload,'estimated_cny':0.12,'currency':'CNY','network_called':False,'warnings':prompt_warnings(prompt),
                'note':'Seedream 5.0 Flash：¥0.12/张；本适配每次1张2K PNG，画幅由提示词描述，实际尺寸须读取产物；未假定免费额度'}
    def submit(self,prepared,authorized=False):
        if not authorized:raise ValueError('图像生成未获得项目授权')
        r=self.request('POST',BASE+'/images/generations',self.headers(),prepared['payload'])
        urls=[x['url'] for x in r.get('data',[]) if x.get('url')]
        if len(urls)!=1:raise RuntimeError('方舟同步结果未返回唯一图片，保留提交记录，禁止自动重试')
        return {'status':'completed','image_urls':urls,'usage':r.get('usage',{}),'actual_cost_cny':None,'provider_request_id':r.get('id')}
