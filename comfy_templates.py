"""Reviewed fixed graph for SD1.x masked inpainting; no user-supplied graph."""
import copy
import hashlib
import json
import math
import re

TEMPLATE_ID = 'masked-repair-sd15'
VERSION = 1
MODEL_SCOPE = 'comfy-masked-repair-sd15-v1'
NODES = {'CheckpointLoaderSimple', 'LoadImage', 'LoadImageMask', 'CLIPTextEncode',
         'VAEEncodeForInpaint', 'KSampler', 'VAEDecode', 'SaveImage'}

def parameters(values):
    if not isinstance(values, dict) or set(values) - {'description', 'strength', 'seed'}:
        raise ValueError('仅允许局部描述、修改强度和种子')
    text = values.get('description', '')
    strength = values.get('strength', .7)
    seed = values.get('seed', 0)
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1500:
        raise ValueError('局部描述须为1–1500字')
    if type(strength) not in (int, float) or not math.isfinite(strength) or not .2 <= strength <= 1:
        raise ValueError('修改强度须为0.2–1')
    if type(seed) is not int or not 0 <= seed <= 2**63-1:
        raise ValueError('种子须为非负整数')
    return {'description': text.strip(), 'strength': strength, 'seed': seed}

def graph(checkpoint, source, mask, values, task_id):
    values = parameters(values)
    for name in (checkpoint, source, mask):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or '..' in name:
            raise ValueError('执行文件名无效')
    if not re.fullmatch(r'[a-f0-9]{32}', task_id):
        raise ValueError('任务编号无效')
    def node(kind, **inputs): return {'class_type': kind, 'inputs': inputs}
    result = {
        '1': node('CheckpointLoaderSimple', ckpt_name=checkpoint),
        '2': node('LoadImage', image=source),
        '3': node('LoadImageMask', image=mask, channel='red'),
        '4': node('CLIPTextEncode', text=values['description'], clip=['1', 1]),
        '5': node('CLIPTextEncode', text='distorted, artifacts', clip=['1', 1]),
        '6': node('VAEEncodeForInpaint', pixels=['2', 0], vae=['1', 2], mask=['3', 0], grow_mask_by=6),
        '7': node('KSampler', model=['1', 0], positive=['4', 0], negative=['5', 0],
                  latent_image=['6', 0], seed=values['seed'], steps=20, cfg=7.0,
                  sampler_name='euler', scheduler='normal', denoise=values['strength']),
        '8': node('VAEDecode', samples=['7', 0], vae=['1', 2]),
        '9': node('SaveImage', images=['8', 0], filename_prefix='repair_'+task_id),
    }
    assert {n['class_type'] for n in result.values()} == NODES
    return result

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def manifest():
    spec = {'id': TEMPLATE_ID, 'version': VERSION, 'model_scope': MODEL_SCOPE,
            'architecture': 'sd15', 'nodes': sorted(NODES), 'output_node': '9',
            'mask': '8bit black/white PNG; white edits, black preserves; same size as source',
            'parameters': ['description', 'strength', 'seed'], 'cost_category': 'image',
            'external_model_fee_cny': 0, 'quality_verified': False,
            'graph_spec': graph('reviewed.safetensors', 'source.png', 'mask.png',
                                {'description': 'repair', 'strength': .7, 'seed': 0}, '0'*32)}
    return {**copy.deepcopy(spec), 'sha256': digest(spec)}
