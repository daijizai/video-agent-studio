"""Project-local publication records and manually supplied performance snapshots."""
import math, uuid
from datetime import datetime
from urllib.parse import urlsplit

COUNTS=('views','likes','comments','shares','favorites','followers')

def text(value,label,limit,required=False):
    if not isinstance(value,str):raise ValueError(label+'格式无效')
    value=value.strip()
    if len(value)>limit or (required and not value):raise ValueError(label+'不能为空或过长' if required else label+'过长')
    return value

def timestamp(value,label,required=False):
    value=text(value,label,40,required)
    if value:
        try: parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:raise ValueError(label+'格式无效') from None
        if parsed.tzinfo is None:raise ValueError(label+'须包含时区')
    return value

def operate(server,state,action,p):
    records=state.setdefault('publications',[])
    if action in ('save-publication','save-snapshot') and not isinstance(p.get('data'),dict):raise ValueError('记录格式无效')
    if action=='save-publication':
        d=p['data']; existing=next((x for x in records if x['id']==p.get('publication_id')),None) if p.get('publication_id') else None
        if p.get('publication_id') and existing is None:raise ValueError('发布记录不存在')
        platform=text(d.get('platform',''),'平台',60,True); title=text(d.get('title',''),'发布标题',180)
        published=timestamp(d.get('published_at',''),'发布时间');url=text(d.get('url',''),'作品链接',2000)
        if url:
            parsed=urlsplit(url)
            if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password:raise ValueError('作品链接须为有效的网页地址')
        values={'platform':platform,'title':title,'published_at':published,'url':url,'notes':text(d.get('notes',''),'发布备注',3000),'advice':text(d.get('advice',''),'运营建议',6000)}
        if existing:existing.update(values)
        else:
            if len(records)>=100:raise ValueError('项目发布记录已达上限')
            existing={'id':uuid.uuid4().hex,'snapshots':[],**values};records.append(existing)
    elif action=='save-snapshot':
        record=next((x for x in records if x['id']==p.get('publication_id')),None)
        if not record:raise ValueError('发布记录不存在')
        d=p['data'];at=timestamp(d.get('observed_at',''),'记录时间',True)
        if record.get('published_at') and datetime.fromisoformat(at.replace('Z','+00:00'))<datetime.fromisoformat(record['published_at'].replace('Z','+00:00')):raise ValueError('记录时间不能早于发布时间')
        values={'observed_at':at,'note':text(d.get('note',''),'数据备注',3000)}
        for key in (*COUNTS,'ad_spend'):
            val=d.get(key)
            if val in (None,''):values[key]=None;continue
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val) or val<0 or val>1e12:raise ValueError('数据必须是非负数字')
            if key!='ad_spend' and int(val)!=val:raise ValueError('数量须为整数')
            if key=='ad_spend' and round(val,2)!=val:raise ValueError('投流金额最多保留两位小数')
            values[key]=int(val) if key!='ad_spend' else round(val,2)
        if all(values[k] is None for k in (*COUNTS,'ad_spend')) and not values['note']:raise ValueError('请填写至少一项数据或备注')
        snapshots=record.setdefault('snapshots',[]);existing=next((x for x in snapshots if x['id']==p.get('snapshot_id')),None) if p.get('snapshot_id') else None
        if p.get('snapshot_id') and existing is None:raise ValueError('数据记录不存在')
        if existing:existing.update(values)
        else:
            if len(snapshots)>=1000:raise ValueError('数据记录已达上限')
            snapshots.append({'id':uuid.uuid4().hex,**values})
    else:raise ValueError('未知运营操作')
    server.save(state)
    return server.read(state['project_id'])
