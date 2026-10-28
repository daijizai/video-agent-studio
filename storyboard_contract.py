"""Versioned review binding for optional storyboard assistance. No DB or migration.

Integration: add record_binding(shot) to NEW approval records, and require
matches(record, shot) alongside the existing workflow content/image hash.
Legacy records remain valid unless optional assistance was explicitly added.
"""
import hashlib
import json

FIELDS = ('action_chain', 'prop_states', 'reference_bindings')


def has_assistance(shot):
    details = shot.get('creative_details') or {}
    return any(key in details for key in FIELDS)


def binding_hash(shot):
    details = shot.get('creative_details') or {}
    content = {'schema': 1, 'reference_images': shot.get('reference_images') or [],
               'assistance': {key: details[key] for key in FIELDS if key in details}}
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def record_binding(shot):
    return {'storyboard_binding_version': 1, 'storyboard_binding_hash': binding_hash(shot)}


def matches(record, shot):
    if 'storyboard_binding_version' not in record:
        return not has_assistance(shot)
    return record.get('storyboard_binding_version') == 1 and record.get('storyboard_binding_hash') == binding_hash(shot)


def invalidate_changed(previous, current):
    """Only explicit reference/assist edits revoke a shot; no historical migration."""
    old = {shot['id']: shot for shot in previous}
    for shot in current:
        before = old.get(shot['id'])
        if before is not None and (binding_hash(before) != binding_hash(shot) or before.get('story_intent') != shot.get('story_intent')):
            shot.update(approved=False, text_approved=False, status='待确认')
            if shot.get('storyboard_task_id'):
                shot['image_quality'] = 'unreviewed'


def validate_shots(shots):
    """Validate optional form types, without normalizing or inventing data."""
    def string(value):
        if not isinstance(value, str) or len(value) > 10000:
            raise ValueError('辅助编辑文本格式无效或超过10000字符')

    def strings(value):
        if not isinstance(value, list) or len(value) > 100:
            raise ValueError('辅助编辑列表格式无效或超过100项')
        for item in value:
            string(item)

    for shot in shots:
        if 'story_intent' in shot:
            string(shot['story_intent'])
        details = shot.get('creative_details') or {}
        if not isinstance(details, dict):
            raise ValueError('创作分镜必须为对象')
        chain = details.get('action_chain', {})
        if not isinstance(chain, dict):
            raise ValueError('动作链必须为对象')
        for key in ('start', 'trigger', 'end', 'incoming_transition'):
            if key in chain:
                string(chain[key])
        if 'steps' in chain:
            strings(chain['steps'])
        for field in ('prop_states', 'reference_bindings'):
            rows = details.get(field, [])
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError('辅助编辑状态列表格式无效或超过100行')
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError('辅助编辑状态行必须为对象')
                if field == 'reference_bindings':
                    if type(row.get('reference_index')) is not int or row['reference_index'] < 1:
                        raise ValueError('参考图序号必须为正整数')
                    for key in ('url', 'purpose', 'asset_version', 'source_task_id'):
                        if key in row:
                            string(row[key])
                    if 'preserve' in row:
                        strings(row['preserve'])
                else:
                    for key in ('asset_id', 'transition', 'incoming_transition'):
                        if key in row:
                            string(row[key])
                    for phase in ('start', 'end'):
                        state = row.get(phase, {})
                        if not isinstance(state, dict):
                            raise ValueError('道具起止状态必须为对象')
                        for key in ('location', 'holder'):
                            if key in state:
                                string(state[key])
                        if state.get('count') is not None and (type(state['count']) is not int or state['count'] < 0):
                            raise ValueError('道具数量须为非负整数；未知请留空')
                        if state.get('visible', 'unknown') not in ('unknown', 'visible', 'offscreen'):
                            raise ValueError('道具可见性无效')
