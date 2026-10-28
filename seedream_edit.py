"""Seedream single-image coordinate edit. No auto dispatch, upload service or model install.
Uses existing project SQLite, shared lock, Ark auth/transport and image budgets.
"""
import base64
import copy
import json
import math
import re
import struct
import urllib.parse
import urllib.request
import uuid
import zlib
from pathlib import Path

import ark_provider
import comfy_assets
import comfy_templates
from comfy_executor import RepairService, LIVE
import generation_scope
import providers
import secret_store
import workflow_state

PROVIDER = 'seedream-edit'
MODEL = ark_provider.IMAGE_MODEL
PRICE = .12
VERSION = 1
LIMIT = 20*1024*1024  # Workbench subset of the documented 30MB input maximum.
BOUNDARY = '整图编辑候选；框选为空间引导，不保证框外内容或像素不变。'
DOMAINS = ('aliyuncs.com','alicdn.com','volces.com','byteimg.com')

def png_info(data):
    """Validate 8bit RGB(A)/grayscale non-interlaced PNG without adding Pillow.
    Accept 2K landscape/portrait outputs beyond a 2048px edge. No rescaling/compositing.
    """
    if not isinstance(data,bytes) or len(data)>LIMIT or not data.startswith(comfy_assets.SIGNATURE):raise ValueError('需要20MB以内PNG')
    offset=8;header=None;compressed=bytearray();ended=False
    while offset+12<=len(data):
        size=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8];body=data[offset+8:offset+8+size]
        if len(body)!=size or offset+size+12>len(data):raise ValueError('PNG截断')
        crc=struct.unpack('>I',data[offset+8+size:offset+12+size])[0]
        if zlib.crc32(kind+body)&0xffffffff!=crc:raise ValueError('PNG校验失败')
        if header is None and kind!=b'IHDR':raise ValueError('PNG头无效')
        if kind==b'IHDR':
            if header is not None or size!=13:raise ValueError('PNG头无效')
            header=struct.unpack('>IIBBBBB',body)
        elif kind==b'IDAT':compressed.extend(body)
        elif kind==b'IEND':
            if size:raise ValueError('PNG结束无效')
            ended=True;offset+=size+12;break
        elif kind==b'acTL' or kind[:1].isupper():raise ValueError('不支持此PNG类型')
        offset+=size+12
    if not header or not ended or offset!=len(data):raise ValueError('PNG未完整结束')
    width,height,depth,color,compression,filtering,interlace=header;channels={0:1,2:3,4:2,6:4}.get(color)
    if not channels or depth!=8 or compression or filtering or interlace:raise ValueError('需要8bit非交错PNG')
    if not 15<=width<=4096 or not 15<=height<=4096 or width*height>16777216 or not 1/16<=width/height<=16:raise ValueError('图片超出工作台尺寸范围')
    stride=width*channels+1;expected=stride*height;decoder=zlib.decompressobj()
    try:raw=decoder.decompress(bytes(compressed),expected+1)
    except zlib.error:raise ValueError('PNG压缩数据无效') from None
    if len(raw)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or any(raw[y*stride]>4 for y in range(height)):raise ValueError('PNG像素数据无效')
    return {'width':width,'height':height,'format':'png','sha256':comfy_assets.sha(data)}

def read_image(root,project_id,url):
    if type(project_id) is not int or project_id<1 or not isinstance(url,str) or not re.fullmatch('/media/'+str(project_id)+r'/[A-Za-z0-9_-]+\.png',url):raise ValueError('图片须属于当前项目')
    base=Path(root)/'assets';folder=base/str(project_id);file=folder/Path(url).name
    if base.is_symlink() or folder.is_symlink() or file.is_symlink() or file.resolve().parent!=folder.resolve() or not file.is_file():raise ValueError('图片路径越界或不存在')
    with file.open('rb') as stream:data=stream.read(LIMIT+1)
    return data,png_info(data)

def bbox(region,width,height):
    if not isinstance(region,dict) or set(region)!={'x','y','width','height'} or any(type(v) is not int for v in region.values()):raise ValueError('框选区域无效')
    x,y,w,h=(region[k] for k in ('x','y','width','height'))
    if x<0 or y<0 or w<1 or h<1 or x+w>width or y+h>height:raise ValueError('框选区域越界')
    def norm(v,total):return min(999,max(0,math.floor(v/total*1000+.5)))
    coords=[norm(x,width),norm(y,height),norm(x+w,width),norm(y+h,height)]
    if coords[0]>=coords[2] or coords[1]>=coords[3]:raise ValueError('框选区域过小')
    return coords

def payload_for(data,info,region,description):
    if not isinstance(description,str) or not 1<=len(description.strip())<=1500:raise ValueError('请描述要修改的内容')
    if '<' in description or '>' in description:raise ValueError('修改描述不能包含坐标或结构标记')
    coords=bbox(region,info['width'],info['height'])
    prompt='编辑图 1 <bbox>'+ ' '.join(map(str,coords))+'</bbox> 区域：'+description.strip()+'。尽量保持其余内容、构图和宽高比。输出一幅完整静态图片，不进行图层拆分。'
    return {'model':MODEL,'prompt':prompt,'image':'data:image/png;base64,'+base64.b64encode(data).decode('ascii'),
            'size':'2K','response_format':'url','output_format':'png','watermark':True,'stream':False,'layer_decomposition':False}

def output_url(value):
    if not isinstance(value,str):raise ValueError('产物引用无效')
    p=urllib.parse.urlsplit(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443) or not any(p.hostname==d or p.hostname.endswith('.'+d) for d in DOMAINS):raise ValueError('不支持的产物域名')
    return value

def download(url):
    output_url(url)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('禁止产物重定向')
    with urllib.request.build_opener(NoRedirect).open(url,timeout=30) as response:data=response.read(LIMIT+1)
    png_info(data);return data  # No Ark headers are forwarded to the image host.

class SeedreamEditService(RepairService):
    def __init__(self,root,database,request=None,downloader=None,authorize=None,paused=None,lock=None,selected=None):
        super().__init__(root,database,None,{},authorize,paused,lock,selected)
        self.request=request or providers.transport;self.downloader=downloader or download

    def preflight(self):
        return {'ready':bool(secret_store.get_key('ARK_API_KEY')),'api_verified':False,'quality_verified':False,
                'model':MODEL,'estimated_cny':PRICE,'boundary':BOUNDARY,'network_called':False}

    def task(self,state,task_id):
        task=next((t for t in state.get('image_tasks',[]) if t.get('id')==task_id and t.get('provider')==PROVIDER and t.get('kind')=='image'),None)
        if not task or task.get('project_id')!=state['project_id']:raise ValueError('任务不属于当前项目')
        return task

    def gate(self,state,shot_id,source_url):
        if self.selected and self.selected()!=state['project_id']:raise ValueError('当前项目已切换')
        if self.paused(state['project_id'],self.database):raise ValueError('项目已暂停新生成')
        shot=next((s for s in state['shots'] if s['id']==shot_id),None)
        if not shot or not workflow_state.valid_approval(state,shot) or shot.get('storyboard_local')!=source_url:raise ValueError('须先审阅当前原图与分镜')
        data,info=read_image(self.root,state['project_id'],source_url)
        if info['sha256']!=shot.get('storyboard_sha256'):raise ValueError('原图文件已变化，请重新审阅')
        return shot,data,info

    def begin(self,project_id,revision,shot_id,source_url,region,description,request_id):
        if not isinstance(request_id,str) or not re.fullmatch(r'[a-f0-9]{32}',request_id):raise ValueError('请求编号无效')
        with self.transaction() as con:
            state=self.state(con,project_id,revision);shot,data,info=self.gate(state,shot_id,source_url)
            if any(t.get('request_id')==request_id or t.get('status') in LIVE|{'reserved'} for t in state.get('image_tasks',[])):raise ValueError('已有原请求或在途图片任务，禁止重提')
            payload=payload_for(data,info,region,description)
            # Validate local credentials before creating an intent; never persist auth headers.
            ark_provider.headers()
            authorization_id=self.authorize(state,self.database,'image',PRICE,MODEL,shot_id=shot_id)
            task_id=uuid.uuid4().hex;archived=self.write_asset(project_id,task_id+'_source.png',data)
            parameters={k:v for k,v in payload.items() if k!='image'}
            task={'id':task_id,'project_id':project_id,'shot_id':shot_id,'name':shot['name'],'provider':PROVIDER,
                  'kind':'image','cost_category':'image','request_id':request_id,'status':'submitting','provider_task_id':None,
                  'request_model':MODEL,'request_parameters':parameters,'request_sha256':comfy_templates.digest(payload),
                  'source_url':source_url,'archived_source':archived,'source_sha256':info['sha256'],'source_info':info,
                  'region':copy.deepcopy(region),'normalized_bbox':bbox(region,info['width'],info['height']),
                  'description':description.strip(),'content_revision':state['revision'],
                  'content_snapshot':copy.deepcopy({k:state.get(k) for k in ('script','characters','continuity','project_brief')}),
                  'approval_snapshot':copy.deepcopy(shot['approval_snapshot']),'authorization_id':authorization_id,
                  'authorization_scope_snapshot':copy.deepcopy(generation_scope.read().get(str(project_id),{})) if self.uses_default_authorization else {'id':authorization_id},
                  'estimate':PRICE,'actual_cost_cny':None,'price_snapshot':{'cny_per_output':PRICE,'outputs':1,'checked':'2026-10-29','source':'https://ark.volcengine.com/docs/model-pricing#457edfd0'},
                  'template_version':VERSION,'boundary':BOUNDARY,'outside_pixels_locked':False,'quality_verified':False,'review_status':'unreviewed'}
            state.setdefault('image_tasks',[]).append(task);self.save(con,state)
        return copy.deepcopy(task)

    def execute(self,project_id,task_id):
        headers=ark_provider.headers()
        with self.transaction() as con:
            state=self.state(con,project_id);task=self.task(state,task_id)
            if task['status']!='submitting':raise ValueError('原请求已领取，禁止重提')
            shot,_,_=self.gate(state,task['shot_id'],task['source_url'])
            if shot['approval_snapshot']!=task['approval_snapshot']:raise ValueError('原图审批已变化')
            scoped=copy.deepcopy(state);scoped['image_tasks']=[t for t in scoped['image_tasks'] if t['id']!=task_id]
            if self.authorize(scoped,self.database,'image',PRICE,MODEL,shot_id=task['shot_id'])!=task['authorization_id']:raise ValueError('授权版本已变化')
            source,info=read_image(self.root,project_id,task['archived_source'])
            if info['sha256']!=task['source_sha256']:raise ValueError('归档原图已变化')
            payload=payload_for(source,info,task['region'],task['description'])
            if comfy_templates.digest(payload)!=task['request_sha256'] or payload['model']!=task['request_model']:raise ValueError('持久请求已变化')
            task['status']='uploading';self.save(con,state)
        # One synchronous POST only. No database/global lock held during remote execution.
        try:response=self.request('POST',ark_provider.BASE+'/images/generations',headers,payload)
        except Exception:
            self.update(project_id,task_id,status='unknown',error='编辑提交结果待核对；禁止自动重发')
            return self.get(project_id,task_id)
        rows=response.get('data') if isinstance(response,dict) else None
        if not isinstance(rows,list) or len(rows)!=1:
            count=len(rows) if isinstance(rows,list) else 0
            self.update(project_id,task_id,status='unknown',response_anomaly={'output_count':count},estimate=max(PRICE,round(count*PRICE,2)),error='同步返回数量异常；保留预占，须核对账单与结果')
            return self.get(project_id,task_id)
        try:
            url=output_url(rows[0].get('url'))
            token=headers['Authorization'].removeprefix('Bearer ')
            if token and token in url:raise ValueError('产物引用异常')
        except Exception:
            self.update(project_id,task_id,status='unknown',error='同步产物引用异常；禁止重发');return self.get(project_id,task_id)
        usage=response.get('usage',{})
        usage={k:v for k,v in usage.items() if k in ('generated_images','output_tokens','total_tokens') and type(v) in (int,float)} if isinstance(usage,dict) else {}
        provider_id=response.get('id')
        provider_id=provider_id if isinstance(provider_id,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',provider_id) and token not in provider_id else None
        self.update(project_id,task_id,status='completed',image_urls=[url],usage=usage,provider_request_id=provider_id,download_error='候选待下载')
        return self.archive(project_id,task_id)

    def update(self,project_id,task_id,**fields):
        with self.transaction() as con:
            state=self.state(con,project_id);task=self.task(state,task_id)
            if task['status']=='adopted':return
            if task.get('candidate_local') and fields.get('download_error'):return
            if task['status']=='completed' and fields.get('status') not in (None,'completed'):return
            task.update(fields);self.save(con,state)

    def poll(self,project_id,task_id):
        task=self.get(project_id,task_id)
        if task['status']=='completed' and not task.get('candidate_local'):return self.archive(project_id,task_id)
        if task['status'] in ('unknown','uploading','submitting'):raise ValueError('同步结果无异步编号，须核对原请求，禁止重发')
        return task

    def archive(self,project_id,task_id):
        task=self.get(project_id,task_id)
        if task['status']!='completed' or task.get('candidate_local'):return task
        try:
            data=self.downloader(output_url(task['image_urls'][0]));info=png_info(data)
            # Publish at most once under the short shared transaction. A concurrent
            # late download must never replace an already-adopted candidate file.
            with self.transaction() as con:
                state=self.state(con,project_id);current=self.task(state,task_id)
                if current['status']=='completed' and not current.get('candidate_local'):
                    local=self.write_asset(project_id,task_id+'_candidate.png',data)
                    current.update(candidate_local=local,candidate_sha256=info['sha256'],output_info=info,download_error=None,review_status='unreviewed',outside_pixels_locked=False)
                    self.save(con,state)
        except Exception:self.update(project_id,task_id,download_error='候选尚未保存，可重试下载原结果；不会重新生成')
        return self.get(project_id,task_id)

    def adopt(self,project_id,revision,task_id,candidate_sha256,source):
        if not isinstance(source,str) or not 1<=len(source.strip())<=500:raise ValueError('须记录人工采用来源')
        with self.transaction() as con:
            state=self.state(con,project_id,revision);task=self.task(state,task_id)
            if self.selected and self.selected()!=project_id:raise ValueError('当前项目已切换')
            if task['status']!='completed' or not task.get('candidate_local') or candidate_sha256!=task.get('candidate_sha256'):raise ValueError('请审阅当前已归档候选')
            shot=next((s for s in state['shots'] if s['id']==task['shot_id']),None)
            if not shot or not workflow_state.valid_approval(state,shot) or shot.get('storyboard_local')!=task['source_url'] or shot.get('approval_snapshot')!=task['approval_snapshot']:raise ValueError('当前镜头或原图审批已变化')
            _,original=read_image(self.root,project_id,task['source_url']);_,candidate=read_image(self.root,project_id,task['candidate_local'])
            if original['sha256']!=task['source_sha256'] or candidate['sha256']!=candidate_sha256:raise ValueError('原图或候选文件已变化')
            shot.setdefault('image_review_history',[]).append({'image_task_id':shot.get('storyboard_task_id'),'local':shot['storyboard_local'],'sha256':shot.get('storyboard_sha256'),'approval_snapshot':copy.deepcopy(shot.get('approval_snapshot')),'quality':shot.get('image_quality')})
            shot.update(storyboard_local=task['candidate_local'],storyboard_image=task['candidate_local'],storyboard_task_id=task_id,storyboard_sha256=candidate_sha256,approved=False,approved_image_task_id=None,approval_snapshot=None,image_quality='unreviewed',image_status='completed',status='待检查')
            task.update(status='adopted',review_status='adopted_pending_approval',adoption_source=secret_store.redact(source.strip()))
            self.save(con,state)
        return self.get(project_id,task_id)
