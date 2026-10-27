"""Qwen Image 3.0 storyboard generation/editing using the official async API."""
from decimal import Decimal
import re, urllib.parse
import providers, secret_store
STATIC_FRAME_PREFIX='单张独立画面：只描绘一个静态瞬间、一个构图。不画分格、拼贴、分屏、三联画或接触印样。不将时间顺序展开成多个画面。'
def prompt_warnings(prompt):
    warnings=[]
    if re.search(r'\b[0-9]{2}:[0-9]{2}|随后|然后|先.{0,30}再|第[一二三四五六123456]个?镜头',prompt):warnings.append('检测到可能的时序/多镜信息；图片应改写为单一静态瞬间，视频动作和对白留在视频提示中')
    return warnings
class ImageProvider:
    def __init__(self,request=providers.transport):self.request=request
    def prepare(self,shot):
        prompt=str(shot.get('image_prompt') or shot.get('prompt') or '').strip()
        if not prompt:raise ValueError('请先填写关键帧画面描述')
        model=shot.get('image_model','qwen-image-3.0')
        if model not in ('qwen-image-3.0','qwen-image-3.0-pro'):raise ValueError('未支持的分镜图模型')
        refs=shot.get('reference_images',[])
        if not isinstance(refs,list) or len(refs)>3:raise ValueError('Qwen Image 3.0最多支持3张角色/场景参考图')
        for url in refs:
            p=urllib.parse.urlparse(url)
            if not ((p.scheme=='https' and p.hostname and not p.username and not p.password) or (p.scheme=='oss' and p.netloc=='dashscope-instant')):raise ValueError('参考图需为HTTPS或官方临时OSS图片URL')
        size=shot.get('image_size','720*1280')
        if size not in ('720*1280','1280*720','1024*1024'):raise ValueError('请选择已支持的关键帧尺寸')
        warnings=prompt_warnings(prompt)
        content=[{'image':url} for url in refs]+[{'text':STATIC_FRAME_PREFIX+'\n'+prompt}]
        payload={'model':model,'input':{'messages':[{'role':'user','content':content}]},'parameters':{'size':size,'n':1,'prompt_extend':False,'watermark':True}}
        estimate=Decimal('0.18' if model=='qwen-image-3.0' else '0.25')+Decimal('0.02')*len(refs)
        return {'provider':'qwen-image','payload':payload,'estimated_cny':float(estimate),'currency':'CNY','network_called':False,'warnings':warnings,'note':'北京1K档：每次1张；参考图每张另计¥0.02；免费额度尚不抵扣预占'}
    def headers(self):
        key=secret_store.get_key('WAN3_API_KEY')
        if not key:raise ValueError('请先配置同平台WAN3_API_KEY')
        return {'Authorization':'Bearer '+key,'Content-Type':'application/json','X-DashScope-Async':'enable'}
    def submit(self,prepared,authorized=False):
        if not authorized:raise ValueError('图像生成付费开关未开启')
        headers=self.headers()
        if 'oss://' in str(prepared['payload']):headers['X-DashScope-OssResourceResolve']='enable'
        r=self.request('POST','https://maas.qianwenaiapi.com/api/v1/services/aigc/image-generation/generation',headers,prepared['payload'])
        task_id=r.get('output',{}).get('task_id')
        if not task_id:raise ValueError('未返回图像任务ID，禁止自动重试')
        return str(task_id)
    def status(self,task_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',task_id):raise ValueError('非法任务ID')
        headers=self.headers();headers.pop('X-DashScope-Async',None)
        r=self.request('GET','https://maas.qianwenaiapi.com/api/v1/tasks/'+task_id,headers)
        out=r.get('output',{});status={'PENDING':'queued','RUNNING':'running','SUCCEEDED':'completed','FAILED':'failed','CANCELED':'cancelled'}.get(out.get('task_status'),'unknown')
        urls=[]
        for choice in out.get('choices',[]):
            for item in choice.get('message',{}).get('content',[]):
                if item.get('image'):urls.append(item['image'])
        for item in out.get('results',[]):
            if item.get('url'):urls.append(item['url'])
        return {'status':status,'image_urls':urls,'usage':r.get('usage',out.get('usage',{})),'error_code':out.get('code'),'actual_cost_cny':None}
