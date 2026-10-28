"""Synthetic Codex handoffs. Writes Skill sources ONLY inside temporary fixtures."""
import copy
import hashlib
from pathlib import Path
import asset_templates as contracts


def handoff(root,kind='character',subtype='human'):
    skill=contracts.SKILLS[kind];folder=Path(root)/'skills'/skill;folder.mkdir(parents=True,exist_ok=True)
    source=folder/'SKILL.md';reference=folder/'templates'/'fixture-contract.md';reference.parent.mkdir(exist_ok=True)
    protocol=Path(root)/'docs'/'PRODUCTION_HANDOFF.md';protocol.parent.mkdir(exist_ok=True)
    if not source.exists():source.write_text('---\nname: '+skill+'\nmetadata:\n  version: "fixture-1"\n---\nSynthetic test Skill source. No production creative knowledge.\n')
    if not reference.exists():reference.write_text('Synthetic independent-view source for contract tests.\n')
    if not protocol.exists():protocol.write_text('Synthetic public handoff contract for tests.\n')
    if kind=='object':subtype='object';keys=contracts.OBJECT_FIELDS
    else:keys=contracts.ROBOT_FIELDS if subtype=='robot' else contracts.OTHER_FIELDS if subtype in ('animal','other') else contracts.CHARACTER_FIELDS
    values={key:contracts.entry('测试设计：'+contracts.FIELD_LABELS[key], 'system_choice','synthetic Codex handoff') for key in keys}
    values['identity']=contracts.entry('测试主体','story_fact','synthetic story fact')
    profile={'schema_version':1,'design_version':'fixture-1','subtype':subtype,'fields':values,
        'source':{'skill_id':skill,'skill_version':'fixture-1','skill_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'references':{'templates/fixture-contract.md':hashlib.sha256(reference.read_bytes()).hexdigest()},
                  'handoff_contract_sha256':hashlib.sha256(protocol.read_bytes()).hexdigest()},
        'master_plan':{'identity_tag':'main' if kind=='object' else 'portrait','structure_tag':'main' if kind=='object' else 'body_front','has_head':kind=='character','has_feet':kind=='character'},
        'standard_setup':{'id':'neutral-fixture-1','background':'测试中性背景','lighting':'测试均匀柔光','scale':'测试统一尺度'},'view_recipes':{}}
    for tag,(name,part,direction,_) in contracts.VIEW_SPECS.items():
        if (tag in ('main','front','side','back','detail'))!=(kind=='object'):continue
        profile['view_recipes'][tag]={'id':name,'version':'fixture-1',
            'prompt':'测试用独立静态视图：'+tag+'。只呈现同一测试主体，保持已交接的设计与中性标准设置。',
            'part':part,'direction':direction,'single_image':True,'single_subject':True,'neutral_pose':True,
            'head_visible':True,'feet_visible':part=='full_body','complete_subject':True,'contains_hands':False,'setup_id':'neutral-fixture-1'}
    return copy.deepcopy(profile)
