"""Published-list-price estimates are display-only, never settled charges."""
from decimal import Decimal,InvalidOperation
PRICE_SOURCE='https://docs.volcengine.com/docs/ark/model-pricing?lang=zh'
PRICE_CHECKED='2026-10-30'

def public_estimate(task):
    request=task.get('request') or {}
    if task.get('status')!='completed' or request.get('model')!='doubao-seedance-2-5-260628':return None
    usage=task.get('usage') or {};tokens=usage.get('completion_tokens')
    if type(tokens) is not int or tokens<0:return None
    resolution=(task.get('provider_metadata') or {}).get('resolution') or request.get('resolution')
    if resolution not in ('480p','720p','1080p'):return None
    content=request.get('content') or [];has_video=any(isinstance(x,dict) and x.get('type')=='video_url' for x in content)
    prices={'480p':('70','42'),'720p':('70','42'),'1080p':('77','46')}
    rate=Decimal(prices[resolution][1 if has_video else 0]);amount=Decimal(tokens)*rate/Decimal(1000000)
    return {'amount_cny':float(amount),'tokens':tokens,'rate_cny_per_million':float(rate),'video_input':has_video,'resolution':resolution,'source':PRICE_SOURCE,'checked_at':PRICE_CHECKED,'kind':'published_list_price_estimate','note':'按官方公示单价和供应商Token估算，未包含账号折扣或资源抵扣，不是实付账单'}
