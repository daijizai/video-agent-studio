"""MiniMax China H3 V2 adapter. Preparation is offline; no automatic retry."""
import math,urllib.parse
from decimal import Decimal,ROUND_UP
import secret_store

BASE='https://api.minimax.cn'
MODELS={
 'MiniMax-H3':{'rates':{'768P':'0.50','2K':'0.80'},'image':'0.20','free_images':5,'min_duration':4},
 'MiniMax-H3-Highspeed':{'rates':{'480P':'0.26','768P':'0.40'},'image':'0.20','free_images':5,'min_duration':4},
 'MiniMax-H3-Lite':{'rates':{'480P':'0.16','768P':'0.26'},'image':'0.13','free_images':5,'min_duration':4},
 'MiniMax-H3-Max':{'rates':{'480P':'0.33','768P':'0.50'},'video_rates':{'480P':'0.37','768P':'0.97'},'image':'0.50','free_images':2,'min_duration':5},
}

def prepare_video(shot,config):
 model=config.get('minimax_model','MiniMax-H3')
 if model not in MODELS:raise ValueError('未支持的MiniMax视频模型')
 spec=MODELS[model];duration=shot.get('duration')
 if type(duration) not in (int,float) or not math.isfinite(duration) or not float(duration).is_integer() or not spec['min_duration']<=duration<=15:raise ValueError('MiniMax当前模型支持%d至15秒整数时长'%spec['min_duration'])
 resolution=str(config.get('resolution','768P')).upper()
 if resolution not in spec['rates']:raise ValueError('MiniMax当前模型支持分辨率：'+ ' / '.join(spec['rates']))
 ratio=config.get('ratio','16:9')
 if ratio not in ('21:9','16:9','4:3','1:1','3:4','9:16'):raise ValueError('MiniMax请选择明确的输出画幅')
 prompt=shot.get('prompt','')
 if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>7000:raise ValueError('MiniMax提示词须为1至7000字符')
 refs=shot.get('reference_images') or []
 if not isinstance(refs,list) or len(refs)>9:raise ValueError('MiniMax最多9张参考图片')
 for url in refs:
  if not isinstance(url,str):raise ValueError('参考图片地址无效')
  parsed=urllib.parse.urlparse(url)
  if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('MiniMax参考图须使用无凭据的HTTPS URL')
 payload={'model':model,'content':[{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':url},'role':'reference_image'} for url in refs],'duration':int(duration),'resolution':resolution,'ratio':ratio,'aigc_watermark':True}
 return estimate(payload)

def estimate(payload,video_seconds=0,audio_seconds=0):
 """Estimate from the exact manifest, rounding video input seconds upward."""
 model=payload['model'];spec=MODELS[model];resolution=payload['resolution'];content=payload['content']
 counts={kind:sum(x['type']==kind for x in content) for kind in ('image_url','video_url','audio_url')}
 if counts['image_url']>9 or counts['video_url']>3 or counts['audio_url']>3 or sum(counts.values())>12:raise ValueError('MiniMax参考素材数量超过上限（图片9、视频3、音频3、合计12）')
 if not 0<=video_seconds<=15 or not 0<=audio_seconds<=15:raise ValueError('MiniMax参考视频或音频总时长不能超过15秒')
 output=Decimal(spec['rates'][resolution])*payload['duration']
 videos=Decimal(spec.get('video_rates',spec['rates'])[resolution])*math.ceil(video_seconds)
 images=Decimal(spec['image'])*max(0,counts['image_url']-spec['free_images'])
 note='MiniMax中国站公示原价预占：输出视频+输入视频+超出免费张数的图片；音频输入免费，非账单实付'
 return {'provider':'minimax','payload':payload,'estimated_cny':float((output+videos+images).quantize(Decimal('.01'),rounding=ROUND_UP)),'currency':'CNY','price_checked':'2026-10-31','note':note,'estimate_note':note,'network_called':False,'audio_mode':'provider_default','estimate_basis':{'output_cny':float(output),'input_video_cny':float(videos),'input_image_cny':float(images)}}

def status(provider,task_id):
 response=provider.request('GET',BASE+'/v2/query/video_generation/'+task_id,provider.headers())
 task=response.get('task')
 if not isinstance(task,dict) or str(task.get('id'))!=task_id:raise RuntimeError('MiniMax未返回匹配的原任务，保留原状态')
 result={'status':{'queued':'queued','running':'running','succeeded':'completed','failed':'failed','cancelled':'cancelled'}.get(task.get('status'),'unknown'),'video_url':(task.get('content') or {}).get('url'),'usage':task.get('usage') or {},'actual_cost_cny':None,'provider_metadata':{k:task[k] for k in ('model','created_at','updated_at','duration','resolution','ratio') if k in task}}
 error=task.get('error')
 if isinstance(error,dict):result['provider_error']=secret_store.redact({k:str(error[k])[:500] for k in ('code','type','message') if k in error})
 return result
