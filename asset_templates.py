"""Thin runtime contract for Codex/Skill-authored material design handoffs.

No Skill interpretation, creative appearance invention or text-model calls.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

BLUEPRINT_VERSION='1.0'
RECIPE_VERSION='1.0'
MAPPING_VERSION='1.0'
SKILLS={'character':'frame-character-assets','object':'frame-object-assets'}
ORIGINS=('story_fact','system_choice','unknown')
FIELD_LABELS={'identity':'身份','age':'年龄','appearance':'外观身份','face_outline':'脸部轮廓','face_features':'辨识特征',
 'hair':'发型与发色','body':'体型比例','outerwear':'外层服装','innerwear':'内搭','lowerwear':'下装','footwear':'鞋',
 'clothing_materials':'衣料与工艺','body_proportions':'头身与四肢比例','accessories':'必要配件','project_style':'项目风格',
 'service_age':'服役年限','chassis':'机体结构','head_shell':'头部外壳','sensors':'传感器与辨识特征','joints':'关节',
 'manipulators':'手部与机足','surface_materials':'表面材料','markings':'固定识别特征',
 'body_plan':'体态与结构','covering':'毛皮/外壳','distinctive_features':'辨识结构','appendages':'肢体/操作部件',
 'shape':'形状','material':'材质','structure':'结构','color':'颜色','wear':'磨损标记'}
CHARACTER_FIELDS=('identity','age','appearance','face_outline','face_features','hair','body','outerwear','innerwear',
 'lowerwear','footwear','clothing_materials','body_proportions','accessories','project_style')
ROBOT_FIELDS=('identity','service_age','chassis','head_shell','sensors','joints','body_proportions','manipulators',
 'surface_materials','markings','project_style')
OBJECT_FIELDS=('identity','shape','material','structure','color','wear','project_style')
OTHER_FIELDS=('identity','body_plan','covering','distinctive_features','appendages','body_proportions','project_style')
# Technical stage/shape contracts, not creative prompts.
VIEW_SPECS={
 'portrait':('character.identity','head','front',()),
 'head_front':('character.head.front','head','front',('identity',)),
 'head_side':('character.head.side','head','right_90',('identity',)),
 'head_back':('character.head.back','head','back_180',('identity',)),
 'body_front':('character.body.master','full_body','front',('identity',)),
 'body_side':('character.body.side','full_body','right_90',('identity','body')),
 'body_back':('character.body.back','full_body','back_180',('identity','body')),
 'three_quarter':('character.body.three-quarter','full_body','three_quarter',('identity','body')),
 'main':('object.master','object','primary',()),'front':('object.front','object','front',('object',)),
 'side':('object.side','object','right_90',('object',)),'back':('object.back','object','back_180',('object',)),
 'detail':('object.detail','detail','detail',('object',))}
STATIC='只输出一张独立静态原图、一个主体、一个指定视图；禁止拼版、三联图、接触印样、多姿态或动作先后。'


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def entry(value,origin='system_choice',evidence=''):
    return {'value':str(value).strip()[:400],'origin':origin,'evidence':str(evidence).strip()[:200]}


def design_input_hash(state,asset,version):
    return digest({'project_id':state.get('project_id'),'asset_id':asset['id'],'kind':asset['kind'],
        'name':version.get('name'),'summary':version.get('summary'),'role':version.get('role'),'variant':version.get('variant')})


def _string(value,name,limit=400,required=True):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value or (required and not value.strip()):raise ValueError(name+'无效或过长')
    return value.strip()


def _schema(kind,subtype):
    if kind=='object':return OBJECT_FIELDS
    if subtype=='human':return CHARACTER_FIELDS
    if subtype=='robot':return ROBOT_FIELDS
    if subtype in ('animal','other'):return OTHER_FIELDS
    return ()


def normalize_profile(profile,kind):
    if not isinstance(profile,dict) or type(profile.get('schema_version',1)) is not int or profile.get('schema_version',1)!=1:raise ValueError('设计交接格式无效')
    subtype=profile.get('subtype','object' if kind=='object' else 'unspecified')
    if subtype not in ('human','robot','animal','other','object','unspecified') or (kind=='object' and subtype!='object'):raise ValueError('素材子类型无效')
    result={'schema_version':1,'design_version':_string(str(profile.get('design_version','1')),'设计版本',80),
            'subtype':subtype,'fields':{},'source':{},'view_recipes':{},'standard_setup':{},'master_plan':{},'input_basis_hash':profile.get('input_basis_hash','')}
    if result['input_basis_hash'] and (not isinstance(result['input_basis_hash'],str) or not re.fullmatch(r'[a-f0-9]{64}',result['input_basis_hash'])):raise ValueError('设计输入绑定指纹无效')
    fields=profile.get('fields',{})
    if not isinstance(fields,dict) or len(fields)>40:raise ValueError('设计字段无效')
    allowed=set(_schema(kind,subtype)) or set(FIELD_LABELS)
    for key,value in fields.items():
        if key not in allowed or not isinstance(value,dict) or value.get('origin') not in ORIGINS:raise ValueError('设计字段与类型/来源不匹配')
        result['fields'][key]=entry(_string(value.get('value'),'设计值',400,False),value['origin'],_string(value.get('evidence',''),'设计来源',200,False))
    source=profile.get('source',{})
    if not isinstance(source,dict):raise ValueError('Skill来源必须为对象')
    for key in ('skill_id','skill_version','skill_sha256','handoff_contract_sha256','document','sha256','section'):
        if key in source:result['source'][key]=_string(source[key],'来源',200,False)
    refs=source.get('references',{})
    if not isinstance(refs,dict) or len(refs)>20:raise ValueError('规范文件引用无效')
    result['source']['references']={_string(k,'规范相对路径',180):_string(v,'规范指纹',64) for k,v in refs.items()}
    setup=profile.get('standard_setup',{})
    if not isinstance(setup,dict):raise ValueError('标准视图设置必须为对象')
    result['standard_setup']={k:_string(setup[k],'标准视图设置',400) for k in ('id','background','lighting','scale') if k in setup}
    plan=profile.get('master_plan',{})
    if not isinstance(plan,dict):raise ValueError('母版计划必须为对象')
    if plan:
        identity=plan.get('identity_tag');structure=plan.get('structure_tag')
        if kind=='object' and (identity!='main' or structure!='main'):raise ValueError('物品必须以主图为母版')
        if kind=='character' and (identity not in ('portrait','body_front') or structure!='body_front'):raise ValueError('角色母版计划需明确身份与全身/结构正面')
        result['master_plan']={'identity_tag':identity,'structure_tag':structure,
            'has_head':plan.get('has_head'),'has_feet':plan.get('has_feet')}
        if type(result['master_plan']['has_head']) is not bool or type(result['master_plan']['has_feet']) is not bool:raise ValueError('身体部位适用项必须为布尔值')
    recipes=profile.get('view_recipes',{})
    if not isinstance(recipes,dict) or len(recipes)>8:raise ValueError('视图交接配方无效')
    for tag,value in recipes.items():
        if tag not in VIEW_SPECS or not isinstance(value,dict):raise ValueError('未知视图配方')
        result['view_recipes'][tag]={'id':_string(value.get('id'),'配方ID',100),'version':_string(str(value.get('version','')),'配方版本',80),
            'prompt':_string(value.get('prompt'),'已交接视图描述',4000),'part':value.get('part'),'direction':value.get('direction'),
            'single_image':value.get('single_image'),'single_subject':value.get('single_subject'),'neutral_pose':value.get('neutral_pose'),
            'head_visible':value.get('head_visible'),'feet_visible':value.get('feet_visible'),'contains_hands':value.get('contains_hands'),
            'complete_subject':value.get('complete_subject'),
            'setup_id':_string(value.get('setup_id'),'标准设置引用',80)}
    return result


def verify_skill_source(root,profile,kind):
    """Verify bytes only; never execute or interpret Skill prose."""
    profile=normalize_profile(profile,kind);source=profile['source'];expected=SKILLS[kind]
    if source.get('skill_id')!=expected or not source.get('skill_version') or not re.fullmatch(r'[a-f0-9]{64}',source.get('skill_sha256','')):raise ValueError('制作助手尚未交接当前Skill的设计来源，请先准备视觉设计')
    base=Path(root)/'skills'/expected
    if base.parent.is_symlink() or base.is_symlink():raise ValueError('Skill来源目录不可为符号链接')
    def checked(path,sha):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve()):raise ValueError('规范文件不可用或路径越界')
        with path.open('rb') as stream:data=stream.read(256*1024+1)
        if len(data)>256*1024 or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Skill或配方文件已变化，请由制作助手重新交接并审阅')
        return data
    raw=checked(base/'SKILL.md',source['skill_sha256']).decode('utf-8')
    front=raw.split('---',2)[1] if raw.startswith('---') and raw.count('---')>=2 else ''
    declared=re.search(r'(?m)^\s+version:\s*[\"\']?([A-Za-z0-9._-]+)',front)
    if not declared or declared[1]!=source['skill_version']:raise ValueError('Skill元数据版本与交接版本不匹配')
    for relative,sha in source['references'].items():
        path=Path(relative)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in ('references','templates') or path.suffix not in ('.md','.json') or not re.fullmatch(r'[a-f0-9]{64}',sha):raise ValueError('规范相对路径或指纹无效')
        current=base
        for part in path.parts:
            current=current/part
            if current.is_symlink():raise ValueError('规范路径不可为符号链接')
        checked(current,sha)
    if not any(path.startswith('templates/') for path in source['references']):raise ValueError('请记录本次使用的Skill模板来源指纹')
    protocol=Path(root)/'docs'/'PRODUCTION_HANDOFF.md'
    protocol_sha=source.get('handoff_contract_sha256','')
    if protocol.parent.is_symlink() or protocol.is_symlink() or not protocol.is_file() or not re.fullmatch(r'[a-f0-9]{64}',protocol_sha):raise ValueError('公共交接合同来源未就绪')
    with protocol.open('rb') as stream:raw=stream.read(256*1024+1)
    if len(raw)>256*1024 or hashlib.sha256(raw).hexdigest()!=protocol_sha:raise ValueError('公共交接合同已变化，请重新交接')
    return copy.deepcopy(source)


def blueprint(state,asset,version):
    profile=normalize_profile(version.get('design_profile',{}),asset['kind'])
    required=_schema(asset['kind'],profile['subtype']);fields=profile['fields']
    missing=[key for key in required if key not in fields or not fields[key]['value']]
    if not required:missing.append('subtype')
    if profile['source'].get('skill_id')!=SKILLS[asset['kind']] or not profile['source'].get('skill_sha256') or not profile['source'].get('handoff_contract_sha256'):missing.append('skill_handoff')
    if any(k not in profile['standard_setup'] for k in ('id','background','lighting','scale')):missing.append('standard_setup')
    if not profile['view_recipes']:missing.append('view_recipes')
    if not profile['master_plan']:missing.append('master_plan')
    if profile['input_basis_hash']!=design_input_hash(state,asset,version):missing.append('creative_input_changed')
    if not missing:
        for tag in profile['view_recipes']:
            try:recipe(asset['kind'],tag,'qwen-image-3.0-pro',profile)
            except ValueError:missing.append('view_recipe:'+tag)
    result={'schema_version':BLUEPRINT_VERSION,'design_version':profile['design_version'],'kind':asset['kind'],'subtype':profile['subtype'],
        'name':version.get('name',''),'fields':copy.deepcopy(fields),'ready':not missing,'missing':missing,'input_basis_hash':profile['input_basis_hash'],
        'status':'skill_design_draft_pending_review' if not missing else 'awaiting_skill_handoff',
        'source':copy.deepcopy(profile['source']),'standard_setup':copy.deepcopy(profile['standard_setup']),'master_plan':copy.deepcopy(profile['master_plan']),
        'immutable_fields':list(required),'unknowns':[FIELD_LABELS[k]+'：故事未指定，由创作交接保留未知' for k,v in fields.items() if v['origin']=='unknown'],
        'source_signature':digest({'project_id':state.get('project_id'),'asset_id':asset['id'],'name':version.get('name'),
            'summary':version.get('summary'),'variant':version.get('variant'),'fields':fields,'source':profile['source'],'setup':profile['standard_setup'],'master_plan':profile['master_plan']})}
    result['design_hash']=digest(result);return result


def mapping(model):
    if model in ('qwen-image-3.0','qwen-image-3.0-pro'):return {'version':MAPPING_VERSION,'provider':'qwen-image','model':model,'input':'messages.image: data URI','size':'explicit width*height','n':1,'prompt_extend':False,'output':'async image task'}
    if model=='doubao-seedream-5-0-flash-260915':return {'version':MAPPING_VERSION,'provider':'seedream','model':model,'input':'image: data URI array','size':'2K; aspect described in prompt','output_format':'png','output':'synchronous URL; validate single image'}
    raise ValueError('素材模型映射尚未接入')


def concrete_mapping(payload):
    def normalize(value,key=''):
        if isinstance(value,str) and key in ('text','prompt'):return '{{skill_handoff_prompt}}'
        if isinstance(value,str) and value.startswith('https://material-reference.invalid/'):return '{{approved_reference_image}}'
        if isinstance(value,dict):return {k:normalize(v,k) for k,v in value.items()}
        if isinstance(value,list):return [normalize(v,key) for v in value]
        return value
    return {'version':MAPPING_VERSION,'request':normalize(payload)}


def recipe(kind,tag,model,profile=None):
    if tag not in VIEW_SPECS or (tag in ('main','front','side','back','detail'))!=(kind=='object'):raise ValueError('视图不属于该素材类型')
    if not isinstance(profile,dict):raise ValueError('制作助手尚未交接该视图配方')
    profile=normalize_profile(profile,kind);value=profile['view_recipes'].get(tag)
    if not value:raise ValueError('制作助手尚未交接该视图描述，请先准备对应配方')
    name,part,direction,requirements=VIEW_SPECS[tag]
    plan=profile['master_plan']
    if not plan:raise ValueError('母版阶段计划尚未交接')
    if tag==plan['identity_tag']:requirements=()
    elif tag==plan['structure_tag']:requirements=('identity',)
    elif kind=='character' and part=='head':requirements=('identity',)
    if value['part']!=part or value['direction']!=direction or value['single_image'] is not True or value['single_subject'] is not True:raise ValueError('视图配方不满足单图/主体/朝向合同')
    if value['setup_id']!=profile['standard_setup'].get('id'):raise ValueError('视图未绑定同一照明与尺度设置')
    if kind=='character' and value['neutral_pose'] is not True:raise ValueError('标准角色视图必须使用中性姿态')
    if kind=='character' and part=='head' and not plan['has_head']:raise ValueError('该主体未声明头部，不能套用头部视图')
    if kind=='character' and ((not plan['has_head'] and value['head_visible'] is True) or (not plan['has_feet'] and value['feet_visible'] is True)):raise ValueError('视图声明了该主体不存在的部位')
    if part=='full_body' and (value['complete_subject'] is not True or (plan['has_head'] and value['head_visible'] is not True) or (plan['has_feet'] and value['feet_visible'] is not True)):raise ValueError('全身视图必须完整保留适用的身体部位')
    if part=='object' and value['complete_subject'] is not True:raise ValueError('物品标准图必须完整保留主体')
    if kind=='object' and value['contains_hands'] is not False:raise ValueError('物品标准图不得包含持有人或手掌')
    template={'id':value['id'],'version':value['version'],'contract_id':name,'policy_version':RECIPE_VERSION,'kind':kind,'view_tag':tag,
        'prompt':value['prompt'],'framing':{k:value[k] for k in ('part','direction','neutral_pose','head_visible','feet_visible','complete_subject')},
        'static':STATIC,'requires':list(requirements),'standard_setup':copy.deepcopy(profile['standard_setup']),'master_plan':copy.deepcopy(plan),
        'source':copy.deepcopy(profile['source']),'size':'1536*2048' if part=='full_body' else '1024*1024'}
    template['template_hash']=digest(template);mapped=mapping(model)
    return {'template':template,'mapping':mapped,'mapping_hash':digest(mapped),'recipe_hash':digest({'template':template,'mapping':mapped})}


def contract(state,asset,version,tag,model):
    design=blueprint(state,asset,version)
    if not design['ready']:raise ValueError('制作助手尚未交接完整视觉设计；无需用户补填机器参数')
    bundle={'schema_version':1,'blueprint':design,**recipe(asset['kind'],tag,model,version.get('design_profile'))}
    bundle['contract_hash']=digest(bundle);return bundle


def render_prompt(bundle):
    template=bundle['template'];parts=[template['static'],template['prompt']]
    if template['framing']['part']=='full_body':parts.append('保持当前主体完整可见，四周留边，不裁切交接中声明存在的身体部位。')
    return '\n'.join(parts)


def public_design(design):
    labels={'story_fact':'故事已给定','system_choice':'Codex设计草案','unknown':'故事未指定'}
    return {'design_version':design['design_version'],'subtype':design['subtype'],'ready':design['ready'],
        'status':'设计草案，待审阅' if design['ready'] else '待制作助手按Skill交接设计，无需填写技术表单',
        'master_plan':copy.deepcopy(design['master_plan']),'summary':[{'label':FIELD_LABELS[k],'value':v['value'],'source':labels[v['origin']]} for k,v in design['fields'].items()],
        'unknowns':copy.deepcopy(design['unknowns'])}


def review_record(state,asset,version):
    design=blueprint(state,asset,version)
    if not design['ready']:raise ValueError('请先由制作助手交接完整设计与配方，再审阅采用')
    checks={view['id']:{'tag':view['tag'],'recipe_hash':recipe(asset['kind'],view['tag'],view.get('origin',{}).get('model','qwen-image-3.0-pro'),version['design_profile'])['recipe_hash']} for view in version.get('views',[])}
    return {'schema_version':1,'asset_version':version['version'],'design_hash':design['design_hash'],'source_signature':design['source_signature'],'reviewed_views':checks,'quality_guarantee':False}


def not_reviewed(status='当前设计与规范待审阅'):
    return {'reviewed_tags':[],'identity_reviewed':False,'body_reviewed':False,'base_ready':False,'multiview_reviewed':False,'reusable':False,'ref_eligible_tags':[],'status':status,'quality_guarantee':False}


def review_status(state,asset,version):
    try:desired=review_record(state,asset,version)
    except ValueError:return not_reviewed('待Skill设计与配方交接')
    recorded=next((r for r in reversed(asset.get('production_reviews',[])) if r.get('asset_version')==version['version']),None)
    valid=bool(recorded and all(recorded.get(k)==desired[k] for k in ('schema_version','asset_version','design_hash','source_signature','reviewed_views')))
    tags=[v['tag'] for v in version.get('views',[])] if valid else []
    plan=normalize_profile(version.get('design_profile',{}),asset['kind'])['master_plan']
    identity=plan.get('identity_tag');structure=plan.get('structure_tag')
    base=bool(identity in tags and structure in tags)
    multi=bool(asset['kind']=='character' and all(t in tags for t in ('body_front','body_side','body_back')))
    eligible=[]
    for tag in tags:
        req=recipe(asset['kind'],tag,version.get('views',[{}])[0].get('origin',{}).get('model','qwen-image-3.0-pro'),version['design_profile'])['template']['requires']
        if ('identity' in req and identity not in tags) or ('body' in req and structure not in tags) or ('object' in req and 'main' not in tags):continue
        eligible.append(tag)
    return {'reviewed_tags':tags,'identity_reviewed':identity in tags,'body_reviewed':structure in tags,'base_ready':base,
        'multiview_reviewed':multi,'reusable':base and (multi or asset['kind']=='object'),'ref_eligible_tags':eligible,
        'status':'已人工审阅当前规范' if valid else '当前规范待复核','quality_guarantee':False}


def select_reference_views(state,asset,version,tag,model,reference_version,requested_view_id):
    spec=recipe(asset['kind'],tag,model,version.get('design_profile'))
    if not spec['template']['requires']:return []
    if type(reference_version) is not int or asset.get('adopted_version')!=reference_version:raise ValueError('先审阅采用对应母版，再生成后续独立视图')
    adopted=next((v for v in asset['versions'] if v['version']==reference_version),None)
    if adopted is None:raise ValueError('采用版本不存在')
    if blueprint(state,asset,adopted)['design_hash']!=blueprint(state,asset,version)['design_hash']:raise ValueError('设计已变化，请重新审阅对应母版')
    status=review_status(state,asset,adopted);by_tag={v['tag']:v for v in adopted.get('views',[])}
    plan=spec['template']['master_plan']
    required=list(dict.fromkeys([plan['identity_tag']]+([plan['structure_tag']] if 'body' in spec['template']['requires'] else [])))
    if any(t not in by_tag or t not in status['reviewed_tags'] for t in required):raise ValueError('缺少当前规范已审阅的'+('物品主图' if asset['kind']=='object' else '身份及全身正面母版' if 'body' in spec['template']['requires'] else '身份母版'))
    for source_tag in required:
        source_model=by_tag[source_tag].get('origin',{}).get('model','qwen-image-3.0-pro')
        if recipe(asset['kind'],source_tag,source_model,version['design_profile'])['recipe_hash']!=recipe(asset['kind'],source_tag,source_model,adopted['design_profile'])['recipe_hash']:
            raise ValueError('母版配方已变化，请重新交接并审阅母版')
    refs=[by_tag[t] for t in required]
    if requested_view_id and requested_view_id not in {v['id'] for v in refs}:
        selected=next((v for v in adopted.get('views',[]) if v['id']==requested_view_id),None)
        if asset['kind']=='character' and tag.startswith('head_') and selected and selected['tag']=='head_front' and 'head_front' in status['reviewed_tags']:refs.append(selected)
        else:raise ValueError('所选参考不是该视图需要的已采用母版')
    return copy.deepcopy(refs)


def parse_design_markdown(text,document='design.md'):
    """Explicit source notes for Codex, never a ready generation handoff."""
    if not isinstance(text,str) or len(text)>100000:raise ValueError('设计文档无效或过长')
    parts=re.split(r'^##\s+(.+?)\s*$',text,flags=re.M);items=[]
    for i in range(1,len(parts)-1,2):
        notes=dict(re.findall(r'^-\s*([^：\n]+)：([^\n]+)',parts[i+1],re.M))
        if notes:items.append({'name':parts[i].strip(),'notes':notes,'ready':False})
    return {'source':{'document':str(document).replace('\\','/').rsplit('/',1)[-1][:180],'sha256':hashlib.sha256(text.encode()).hexdigest()},'items':items,'ready':False,'note':'须由Codex读取相应Skill后交接结构化设计与独立视图描述'}
