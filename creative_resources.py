"""Versioned, workspace-wide cinematography reference catalog."""
import hashlib,json,re
from pathlib import Path

KINDS={'size':'景别','composition':'构图','movement':'运镜'}

def catalog(root):
    path=Path(root)/'resources'/'shot-language.json'
    raw=path.read_bytes()
    if len(raw)>200000:raise ValueError('创作资源目录过大')
    doc=json.loads(raw)
    if type(doc.get('version')) is not int or doc['version']<1 or not isinstance(doc.get('items'),list):raise ValueError('创作资源目录无效')
    seen=set()
    for item in doc['items']:
        if not isinstance(item,dict) or item.get('kind') not in KINDS or not re.fullmatch(r'[a-z0-9-]{1,80}',str(item.get('id',''))) or item['id'] in seen:raise ValueError('创作资源项目无效')
        if any(not isinstance(item.get(k),str) or not item[k].strip() or len(item[k])>500 for k in ('name','description','use','instruction')):raise ValueError('创作资源内容无效')
        seen.add(item['id'])
    return {'version':doc['version'],'sha256':hashlib.sha256(raw).hexdigest(),'items':doc['items']}

def resolve(root,ids,prior=None):
    if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):raise ValueError('镜头语言选择无效')
    doc=catalog(root);lookup={x['id']:x for x in doc['items']};previous={x['id']:x for x in (prior or [])};result=[];kinds=set()
    for id in ids:
        item=previous.get(id) or lookup.get(id)
        if not item or item['kind'] in kinds:raise ValueError('每类镜头语言最多选一项')
        kinds.add(item['kind'])
        result.append({**item,'catalog_version':item.get('catalog_version',doc['version'])})
    return result
