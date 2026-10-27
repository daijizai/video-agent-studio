#!/usr/bin/env python3
"""Codex-friendly JSON client. The running HTTP backend owns all persistence and rules."""
import argparse,getpass,json,sys,urllib.request,urllib.error,urllib.parse,uuid
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8766',help='Loopback backend URL')
    sub=parser.add_subparsers(dest='group',required=True)
    projects=sub.add_parser('projects').add_subparsers(dest='action',required=True)
    projects.add_parser('list');p=projects.add_parser('create');p.add_argument('title');p=projects.add_parser('select');p.add_argument('id',type=int)
    script=sub.add_parser('script').add_subparsers(dest='action',required=True)
    script.add_parser('get');p=script.add_parser('set');p.add_argument('--file',required=True,help='UTF-8 script text');p.add_argument('--continuity-file')
    for name in ('characters','shots'):
        actions=sub.add_parser(name).add_subparsers(dest='action',required=True)
        actions.add_parser('list');p=actions.add_parser('add');p.add_argument('--file',required=True,help='JSON object')
        p=actions.add_parser('update');p.add_argument('id');p.add_argument('--file',required=True,help='JSON object')
        if name=='shots':
            p=actions.add_parser('approve');p.add_argument('id');p.add_argument('--revoke',action='store_true')
            p=actions.add_parser('review');p.add_argument('id');p.add_argument('--file',required=True,help='UTF-8 review')
    tasks=sub.add_parser('tasks').add_subparsers(dest='action',required=True)
    tasks.add_parser('list')
    for name in ('preview','submit'):
        p=tasks.add_parser(name);p.add_argument('shot_id')
        if name=='submit':p.add_argument('--engine',choices=['provider','comfy'],default='provider')
    p=tasks.add_parser('status');p.add_argument('id')
    settings=sub.add_parser('provider').add_subparsers(dest='action',required=True)
    settings.add_parser('status');p=settings.add_parser('configure');p.add_argument('--provider',choices=['wan3','wan','seedance'],default='wan3');p.add_argument('--resolution',choices=['480p','720p','1080p'],default='720p');p.add_argument('--audio',action='store_true')
    p=sub.add_parser('secret');p.add_argument('--provider',choices=['wan3','wan','seedance'],default='wan3')
    p=sub.add_parser('budget');p.add_argument('amount',type=float)
    sub.add_parser('export')
    args=parser.parse_args()
    try:
        parsed=urllib.parse.urlparse(args.url)
        if parsed.scheme!='http' or parsed.hostname not in ('localhost','127.0.0.1','::1') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise ValueError('CLI只允许本机HTTP后端')
        def api(path,payload=None,state=None):
            if payload is not None and state is not None:payload={**payload,'project_id':state['project_id'],'revision':state['revision']}
            req=urllib.request.Request(args.url.rstrip('/')+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
            except urllib.error.HTTPError as e:
                try:message=json.load(e).get('error','后端请求失败')
                except Exception:message='后端请求失败'
                raise ValueError(message) from None
            except urllib.error.URLError:raise ValueError('后端未连接；请先运行 PORT=8766 python3 server.py') from None
        def file_json(path):
            result=json.loads(Path(path).read_text())
            if not isinstance(result,dict):raise ValueError('输入文件须为JSON对象')
            return result
        group=args.group
        if group=='projects':
            if args.action=='list':result=api('projects')
            elif args.action=='create':result=api('projects/new',{'title':args.title})
            else:result=api('projects/switch',{'project_id':args.id})
        elif group=='provider':
            if args.action=='status':result=api('providers')
            else:result=api('settings',{'provider':args.provider,'resolution':args.resolution,'audio':args.audio},api('state'))
        elif group=='secret':
            # No --key or plaintext argv, no stdin fallback that echoes input.
            if not sys.stdin.isatty():raise ValueError('密钥配置须在交互终端运行；不可通过命令行参数或管道输入')
            value=getpass.getpass('API key（隐藏输入，写入仓库外）: ')
            result=api('credentials',{'provider':args.provider,'value':value},api('state'));value=None
        else:
            state=api('state')
            if group=='export':result=api('export')
            elif group=='budget':result=api('save',{'budget':args.amount},state)
            elif group=='script':
                if args.action=='get':result={k:state[k] for k in ('project_id','title','script','continuity','revision')}
                else:
                    payload={'script':Path(args.file).read_text()}
                    if args.continuity_file:payload['continuity']=Path(args.continuity_file).read_text()
                    result=api('save',payload,state)
            elif group in ('shots','characters'):
                rows=state[group]
                if args.action=='list':result=rows
                else:
                    if args.action=='add':
                        item=file_json(args.file)
                        defaults={'id':str(uuid.uuid4()),'name':'新镜头','frame':'中景','duration':5,'estimate':0,'prompt':'','approved':False,'status':'待确认','review':'','reference_images':[]} if group=='shots' else {'id':str(uuid.uuid4()),'name':'新角色','role':'待设定','notes':'','version':1,'color':'#729c9b'}
                        rows.append({**defaults,**item,'id':defaults['id'],'approved':False} if group=='shots' else {**defaults,**item,'id':defaults['id']})
                    else:
                        item=next((x for x in rows if x['id']==args.id),None)
                        if item is None:raise ValueError('记录不存在')
                        if args.action=='approve':item['approved']=not args.revoke
                        elif args.action=='review':item['review']=Path(args.file).read_text()
                        else:
                            updated=file_json(args.file);updated.pop('id',None);item.update(updated)
                            if group=='shots':item.update(approved=False,status='待确认')
                            else:item['version']=int(item.get('version',1))+1
                    result=api('save',{group:rows},state)
            elif group=='tasks':
                if args.action=='list':result=state['tasks']
                elif args.action=='preview':result=api('provider/preview',{'shot_id':args.shot_id},state)
                elif args.action=='submit':result=api('provider/submit' if args.engine=='provider' else 'submit',{'shot_id':args.shot_id},state)
                else:
                    task=next((t for t in state['tasks'] if t['id']==args.id),None)
                    if task is None:raise ValueError('任务不存在')
                    result=api('provider/poll' if task['provider'] in ('wan3','wan','seedance') else 'poll',{'task_id':args.id},state)
        print(json.dumps({'ok':True,'data':result},ensure_ascii=False));return 0
    except Exception as e:
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
