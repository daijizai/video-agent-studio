"""Official, image-reference-only video adapters. No network during prepare()."""
import secret_store
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
from decimal import Decimal, ROUND_UP

CATALOG = {
    'wan3': {'label':'千问AI Wan3.0-Video · 主用','model':'wan3.0-video','key_env':'WAN3_API_KEY','reference_limit':10},
    'wan': {'label': '阿里 Wan 2.6 R2V Flash', 'model': 'wan2.6-r2v-flash', 'key_env': 'DASHSCOPE_API_KEY', 'reference_limit': 5},
    'seedance': {'label': '字节 Seedance 2.0 Mini', 'model': 'doubao-seedance-2-0-mini-260615', 'key_env': 'ARK_API_KEY', 'reference_limit': 9},
}

def paid_enabled():
    return False  # No global paid unlock: the backend validates finite project scopes.

def config_status():
    return [{**v, 'id': k, 'credential_present': bool(secret_store.get_key(v['key_env'])),
             'endpoint_configured': bool(os.getenv('WAN_WORKSPACE_ID')) if k == 'wan' else True,
             'connection': 'unverified', 'paid_enabled': paid_enabled()}
            for k, v in CATALOG.items()]

class ProviderHTTPError(RuntimeError):
    def __init__(self,status,code,message,headers):
        self.details={'http_status':status,'provider_code':code,'message':secret_store.redact(message),'headers':secret_store.redact(headers)}
        super().__init__('供应商HTTP %s / %s；请核对原任务，不自动重试'%(status,code))
def transport(method, url, headers, payload=None):
    req = urllib.request.Request(url, method=method, headers=headers,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError('Provider redirects are disabled')
    # Never retry POST. Never expose provider exception bodies or headers (may contain secrets).
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            body=json.load(error);code=body.get('code') or body.get('error',{}).get('code') or 'HTTPError'
            code=code if isinstance(code,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',code) else 'HTTPError'
        except Exception:body={};code='HTTPError'
        message=str(body.get('message',''))[:500]
        safe_headers={k:error.headers[k] for k in ('Retry-After','X-RateLimit-Limit','X-RateLimit-Remaining','X-RateLimit-Reset','X-Request-Id') if error.headers and error.headers.get(k)}
        raise ProviderHTTPError(error.code,code,message,safe_headers) from None
    except Exception:
        raise RuntimeError('供应商请求失败或超时；请核对原任务，不要自动重试') from None

class Provider:
    def __init__(self, provider, request=transport):
        if provider not in CATALOG: raise ValueError('未知供应商')
        self.id = provider
        self.meta = CATALOG[provider]
        self.request = request

    def base_url(self):
        if self.id == 'wan3':
            return 'https://cn-beijing.maas.qianwenaiapi.com/api/v1'
        if self.id == 'seedance': return 'https://ark.cn-beijing.volces.com/api/v3'
        workspace = os.getenv('WAN_WORKSPACE_ID', '')
        if not re.fullmatch(r'[A-Za-z0-9-]+', workspace):
            raise ValueError('请在 .env 设置 WAN_WORKSPACE_ID（北京业务空间 ID）')
        return 'https://' + workspace + '.cn-beijing.maas.aliyuncs.com/api/v1'

    def headers(self):
        key = secret_store.get_key(self.meta['key_env'])
        if not key: raise ValueError('尚未配置 ' + self.meta['key_env'])
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
        if self.id in ('wan','wan3'): headers['X-DashScope-Async'] = 'enable'
        return headers

    def prepare(self, shot, config):
        duration = float(shot['duration'])
        maximum = 30 if self.id == 'wan3' else (10 if self.id == 'wan' else 15)
        if not duration.is_integer() or not 2 <= duration <= maximum:
            raise ValueError('该适配器支持 2–%d 秒整数镜头' % maximum)
        duration = int(duration)
        refs = shot.get('reference_images', [])
        if not isinstance(refs, list) or not (0 if self.id=='wan3' else 1) <= len(refs) <= self.meta['reference_limit']:
            raise ValueError('请提供 1–%d 张角色参考图 HTTPS URL' % self.meta['reference_limit'])
        for url in refs:
            p = urllib.parse.urlparse(url)
            if p.scheme != 'https' or not p.hostname or p.username or p.password:
                raise ValueError('参考图只允许无凭据的 HTTPS URL')
            if p.path.lower().endswith(('.mp4', '.mov', '.mp3', '.wav')):
                raise ValueError('本适配器仅支持图片参考，视频/音频输入需另行核价')
        prompt = str(shot.get('prompt', '')).strip()
        if not prompt: raise ValueError('镜头提示词不能为空')
        resolution = config.get('resolution', '720p')
        audio = config.get('audio', False)
        if type(audio) is not bool: raise ValueError('audio 必须为布尔值')
        if self.id == 'wan3':
            if resolution not in ('480p','720p','1080p'):raise ValueError('Wan3支持480p/720p/1080p')
            ratio=config.get('ratio','16:9')
            if ratio not in ('16:9','9:16','1:1'):raise ValueError('未支持的画幅比例')
            payload={'model':'wan3.0-video','input':{'prompt':prompt},'parameters':{'resolution':resolution.upper(),'ratio':ratio,'duration':duration,'audio':audio,'watermark':True,'prompt_extend':False}}
            if refs:payload['input']['media']=[{'type':'reference_image','url':url} for url in refs]
            estimate=Decimal({'480p':'0.30','720p':'0.60','1080p':'1.20'}[resolution])*duration
            note='Wan3北京原价预占；页面限时7折未抵扣，音频开关同价；仅图片/文本输入'
        elif self.id == 'wan':
            if resolution not in ('720p', '1080p'): raise ValueError('Wan 支持 720p / 1080p')
            size = '1280*720' if resolution == '720p' else '1920*1080'
            payload = {'model': self.meta['model'], 'input': {'prompt': prompt, 'reference_urls': refs},
                       'parameters': {'size': size, 'duration': duration, 'audio': audio, 'shot_type': 'single', 'watermark': True}}
            unit = {'720p': ('0.15', '0.30'), '1080p': ('0.25', '0.50')}[resolution][int(audio)]
            estimate = Decimal(unit) * duration
            note = '北京刊例价：图片参考，无视频输入；按生成秒数估算'
        else:
            if resolution not in ('480p', '720p'): raise ValueError('Seedance Mini 支持 480p / 720p')
            payload = {'model': self.meta['model'], 'content': [{'type': 'text', 'text': prompt}] +
                       [{'type': 'image_url', 'image_url': {'url': url}, 'role': 'reference_image'} for url in refs],
                       'resolution': resolution, 'ratio': '16:9', 'duration': duration, 'generate_audio': audio, 'watermark': True}
            width, height = (864, 480) if resolution == '480p' else (1280, 720)
            tokens = Decimal(width * height * 24 * duration) / 1024
            estimate = tokens * Decimal('23') / 1000000
            note = '23 元/百万视频 tokens；16:9、24fps、无视频输入估算，最终以 usage 为准'
        return {'provider': self.id, 'payload': payload, 'estimated_cny': float(estimate.quantize(Decimal('.01'), rounding=ROUND_UP)),
                'currency': 'CNY', 'price_checked': '2026-10-28', 'note': note, 'network_called': False}

    def submit(self, prepared, idempotency_key, authorized=False):
        if not authorized: raise ValueError('付费生成未授权：STUDIO_ENABLE_PAID_GENERATION 默认为 false')
        headers = self.headers()
        # idempotency_key is a local durable intent identifier; neither API is assumed to deduplicate it.
        path = '/services/aigc/video-generation/video-synthesis' if self.id in ('wan','wan3') else '/contents/generations/tasks'
        response = self.request('POST', self.base_url() + path, headers, prepared['payload'])
        task_id = response.get('output', {}).get('task_id') if self.id in ('wan','wan3') else response.get('id')
        if not task_id: raise RuntimeError('供应商未返回任务编号；提交结果不确定，禁止自动重试')
        return str(task_id)

    def status(self, task_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', task_id): raise ValueError('非法任务编号')
        path = '/tasks/' if self.id in ('wan','wan3') else '/contents/generations/tasks/'
        headers=self.headers();headers.pop('X-DashScope-Async',None)
        response = self.request('GET', self.base_url() + path + task_id, headers)
        if self.id in ('wan','wan3'):
            output = response.get('output', {})
            status = {'PENDING': 'queued', 'RUNNING': 'running', 'SUCCEEDED': 'completed', 'FAILED': 'failed', 'CANCELED': 'cancelled'}.get(output.get('task_status'), 'unknown')
            url = output.get('video_url')
        else:
            status = {'queued': 'queued', 'running': 'running', 'succeeded': 'completed', 'failed': 'failed', 'cancelled': 'cancelled', 'expired': 'failed'}.get(response.get('status'), 'unknown')
            url = response.get('content', {}).get('video_url')
        return {'status': status, 'video_url': url, 'usage': response.get('usage', {}), 'actual_cost_cny': None}
