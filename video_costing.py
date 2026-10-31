"""Published-list-price estimates are display-only, never settled charges."""
from decimal import Decimal,InvalidOperation
from collections import Counter
from datetime import datetime,timezone
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

def record_screenshot(state,amounts):
    """Record a user-provided cost screenshot without inventing invoice IDs or settlement status."""
    if not isinstance(amounts,list) or not amounts or len(amounts)>200:raise ValueError('截图金额列表无效')
    values=[]
    for item in amounts:
        if not isinstance(item,str) or not item or len(item)>20:raise ValueError('金额须以十进制字符串提供')
        try:value=Decimal(item)
        except InvalidOperation:raise ValueError('截图金额无效') from None
        if not value.is_finite() or value<0 or value>100000 or value.as_tuple().exponent < -6:raise ValueError('截图金额超出范围')
        values.append(value)
    eligible=[t for t in state.get('tasks',[]) if t.get('status')=='completed' and (t.get('request') or {}).get('model')=='doubao-seedance-2-5-260628']
    calculated=[]
    for task in eligible:
        estimate=public_estimate(task)
        if estimate is None:raise ValueError('存在缺少用量的已完成视频任务，无法完整匹配截图')
        calculated.append(Decimal(str(estimate['amount_cny'])))
    if Counter(values)!=Counter(calculated):raise ValueError('截图金额与已完成任务的推算金额不能完整匹配；未保存，请核对订单')
    now=datetime.now(timezone.utc).isoformat();counts=Counter(values)
    for task,value in zip(eligible,calculated):
        task['screenshot_cost']={'amount_cny':str(value),'currency':'CNY','source':'用户提供的截图',
                                 'matching':'按用量推算金额匹配，未核对订单编号',
                                 'same_amount_count':counts[value],'amount_type':'截图未显示列名，待核对',
                                 'recorded_at':now}
    result={'count':len(values),'total_cny':str(sum(values,Decimal('0'))),'currency':'CNY',
            'source':'用户提供的视频费用截图','matching':'与全部已完成视频任务的按用量推算金额一致，订单对应未核对',
            'amount_type':'截图未显示列名，实付待核对','recorded_at':now}
    state['video_screenshot_cost_summary']=result
    return result
