"""Project-isolated character/object originals and immutable versions; no generation.

Standalone service: the host supplies its existing SQLite file and global lock.
No schema/data/file changes occur on import or catalog reads.
"""
import base64
import binascii
import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import threading
import uuid
import zlib
import asset_templates
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_SIDE = 8192
MAX_DECODED = 68 * 1024 * 1024
KINDS = ('character', 'object')
VIEWS = {
    'character': {'portrait': '头像正面', 'head_front': '头部正面', 'head_side': '头部侧面',
                  'head_back': '头部背面', 'body_front': '全身正面', 'body_side': '全身侧面',
                  'body_back': '全身背面', 'three_quarter': '四分之三视角'},
    'object': {'main': '外观主图', 'front': '正面', 'side': '侧面', 'back': '背面', 'detail': '细节'}
}
EXTENSIONS = {'png': 'image/png', 'jpg': 'image/jpeg', 'webp': 'image/webp'}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, name, maximum=4000, required=False):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ValueError(name + '格式无效或过长')
    value = value.strip()
    if required and not value:
        raise ValueError('请填写' + name)
    return value


def _dimensions(width, height):
    if not 1 <= width <= MAX_SIDE or not 1 <= height <= MAX_SIDE or width * height > MAX_PIXELS:
        raise ValueError('图片宽高须为1–8192像素，且总像素不超过1600万')
    return width, height


def _png(data):
    offset = 8; header = None; compressed = bytearray(); palette = False; ended = False
    while offset + 12 <= len(data):
        size = struct.unpack('>I', data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]; end = offset + 12 + size
        if end > len(data):
            raise ValueError('PNG文件截断')
        body = data[offset+8:end-4]
        if zlib.crc32(kind + body) & 0xffffffff != struct.unpack('>I', data[end-4:end])[0]:
            raise ValueError('PNG校验失败')
        if header is None and kind != b'IHDR':
            raise ValueError('PNG图片头缺失')
        if kind == b'IHDR':
            if header is not None or size != 13:
                raise ValueError('PNG图片头无效')
            header = struct.unpack('>IIBBBBB', body)
            _dimensions(header[0], header[1])
        elif kind == b'IDAT':
            compressed.extend(body)
        elif kind == b'PLTE':
            if not size or size > 768 or size % 3:
                raise ValueError('PNG调色板无效')
            palette = True
        elif kind == b'IEND':
            if size:
                raise ValueError('PNG结束块无效')
            ended = True; offset = end; break
        elif kind in (b'acTL', b'fcTL', b'fdAT'):
            raise ValueError('请导入单张静态图片，不支持动态图')
        elif kind[:1].isupper():
            raise ValueError('不支持此PNG类型')
        offset = end
    if not ended or offset != len(data) or not compressed:
        raise ValueError('PNG图片未完整结束')
    width, height, depth, color, compression, filtering, interlace = header
    depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if color not in depths or depth not in depths[color] or compression or filtering or interlace:
        raise ValueError('不支持此PNG编码；请另存为非交错PNG、JPEG或WebP')
    if color == 3 and not palette:
        raise ValueError('PNG调色板缺失')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    stride = (width * channels * depth + 7) // 8
    expected = (stride + 1) * height
    if expected > MAX_DECODED:
        raise ValueError('图片解码体积过大，请降低尺寸或位深')
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as error:
        raise ValueError('PNG像素数据无效') from error
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('PNG像素数据长度无效')
    if any(raw[y * (stride + 1)] > 4 for y in range(height)):
        raise ValueError('PNG过滤数据无效')
    return width, height


def _jpeg(data):
    offset = 2; dimensions = None; scan = False; entropy = 0; tables = set()
    while offset < len(data):
        if data[offset] != 255:
            raise ValueError('JPEG标记无效')
        while offset < len(data) and data[offset] == 255:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]; offset += 1
        if marker == 0xD9:
            if offset != len(data) or not dimensions or not scan or not entropy or not {0xDB, 0xC4}.issubset(tables):
                raise ValueError('JPEG图片不完整')
            return dimensions
        if marker in (0, 0xD8) or 0xD0 <= marker <= 0xD7 or offset + 2 > len(data):
            raise ValueError('JPEG文件无效')
        size = int.from_bytes(data[offset:offset+2], 'big')
        if size < 2 or offset + size > len(data):
            raise ValueError('JPEG文件截断')
        body = data[offset+2:offset+size]; offset += size
        tables.add(marker)
        if marker in (0xC0, 0xC2):
            if len(body) < 6 or body[0] != 8 or len(body) != 6 + 3 * body[5] or not 1 <= body[5] <= 4:
                raise ValueError('不支持此JPEG编码')
            height, width = struct.unpack('>HH', body[1:5])
            dimensions = _dimensions(width, height)
        elif 0xC0 <= marker <= 0xCF and marker not in (0xC4,):
            raise ValueError('仅支持常见8bit基线或渐进JPEG')
        if marker == 0xDA:
            if dimensions is None or len(body) < 4:
                raise ValueError('JPEG扫描数据无效')
            scan = True
            while offset < len(data):
                if data[offset] != 255:
                    entropy += 1; offset += 1; continue
                if offset+1 < len(data) and (data[offset+1] == 0 or 0xD0 <= data[offset+1] <= 0xD7):
                    entropy += 1; offset += 2; continue
                break
    raise ValueError('JPEG图片未完整结束')


def _webp(data):
    if len(data) < 20 or int.from_bytes(data[4:8], 'little') != len(data)-8:
        raise ValueError('WebP文件长度无效')
    offset = 12; dimensions = None; canvas = None; images = 0
    while offset+8 <= len(data):
        kind = data[offset:offset+4]; size = int.from_bytes(data[offset+4:offset+8], 'little')
        end = offset+8+size
        if end > len(data):
            raise ValueError('WebP文件截断')
        body = data[offset+8:end]
        if kind in (b'ANIM', b'ANMF'):
            raise ValueError('请导入静态WebP，不支持动态图')
        if kind == b'VP8X':
            if size != 10 or body[0] & 2:
                raise ValueError('不支持此WebP类型')
            canvas = _dimensions(int.from_bytes(body[4:7], 'little')+1, int.from_bytes(body[7:10], 'little')+1)
        elif kind == b'VP8 ':
            if size <= 10 or body[3:6] != b'\x9d\x01\x2a' or body[0] & 1:
                raise ValueError('WebP图像数据无效')
            dimensions = _dimensions(int.from_bytes(body[6:8], 'little') & 0x3fff, int.from_bytes(body[8:10], 'little') & 0x3fff)
            images += 1
        elif kind == b'VP8L':
            if size <= 5 or body[0] != 0x2f:
                raise ValueError('WebP无损数据无效')
            bits = int.from_bytes(body[1:5], 'little')
            if bits >> 29:
                raise ValueError('WebP版本无效')
            dimensions = _dimensions((bits & 0x3fff)+1, ((bits >> 14) & 0x3fff)+1); images += 1
        offset = end + (size % 2)
    if offset != len(data) or images != 1 or not dimensions or (canvas and canvas != dimensions):
        raise ValueError('WebP图片不完整')
    return dimensions


def inspect_image(data, filename=''):
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise ValueError('图片须为非空文件，且不超过12MB')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        ext = 'png'; width, height = _png(data)
    elif data.startswith(b'\xff\xd8'):
        ext = 'jpg'; width, height = _jpeg(data)
    elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        ext = 'webp'; width, height = _webp(data)
    else:
        raise ValueError('仅支持PNG、JPEG、静态WebP；不接受SVG或其他文件')
    if ext in ('jpg','webp'):
        decoder=shutil.which('ffmpeg')
        if not decoder:raise ValueError('当前环境请先使用PNG原图；JPEG/WebP解码器暂不可用')
        try:
            result=subprocess.run([decoder,'-v','error','-threads','1','-protocol_whitelist','pipe',
                '-f','image2pipe','-c:v','mjpeg' if ext=='jpg' else 'webp','-i','pipe:0',
                '-frames:v','1','-f','null','-'],input=data,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)
        except (OSError,subprocess.TimeoutExpired) as error:
            raise ValueError('图片解码失败或超时，请使用正常单张原图') from error
        if result.returncode or result.stderr:raise ValueError('图片像素数据损坏，无法完整解码')
    if filename:
        filename = _text(filename, '文件名', 180)
        if '/' in filename or '\\' in filename or Path(filename).suffix.lower() not in ('.'+ext, '.jpeg' if ext == 'jpg' else '.'+ext):
            raise ValueError('文件扩展名与图片格式不符，或文件名包含路径')
    return {'extension': ext, 'mime': EXTENSIONS[ext], 'width': width, 'height': height,
            'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def legacy_id(character_id):
    return 'legacy-' + hashlib.sha256(str(character_id).encode()).hexdigest()[:24]


def assets(state):
    """A non-mutating legacy projection: no fabricated historical versions."""
    result = copy.deepcopy(state.get('material_assets') or [])
    mapped = {a.get('character_id') for a in result if a.get('kind') == 'character'}
    projected = []
    for character in state.get('characters', []):
        if character['id'] in mapped:
            continue
        version = max(1, int(character.get('version') or 1))
        projected.append({'id': legacy_id(character['id']), 'kind': 'character', 'character_id': character['id'],
            'latest_version': version, 'adopted_version': None, 'versions': [{'version': version,
                'name': character.get('name', ''), 'summary': character.get('notes', ''),
                'role': character.get('role', ''), 'variant': '', 'views': [], 'created_at': None,
                'origin': 'legacy_text', 'note': '保留原角色设定；此前未保存的历史不可恢复'}]})
    order={c['id']:i for i,c in enumerate(state.get('characters',[]))}
    return sorted(projected + result,key=lambda a:(a['kind']!='character',order.get(a.get('character_id'),len(order)) if a['kind']=='character' else 0))


def _version(asset, number=None):
    number = asset['latest_version'] if number is None else number
    found = next((v for v in asset['versions'] if v['version'] == number), None)
    if found is None:
        raise ValueError('素材版本不存在')
    return found


def _append(asset, version):
    version = copy.deepcopy(version)
    version.update(version=max(v['version'] for v in asset['versions'])+1, created_at=_now())
    asset['versions'].append(version); asset['latest_version'] = version['version']
    return version


def reference_hash(shot):
    refs = shot.get('asset_references') or []
    return hashlib.sha256(json.dumps(refs, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def record_binding(shot):
    return {'material_binding_version': 1, 'material_binding_hash': reference_hash(shot)}


def valid_binding(record, shot):
    if 'material_binding_version' not in record:
        return not shot.get('asset_references')
    return record.get('material_binding_version') == 1 and record.get('material_binding_hash') == reference_hash(shot)


def suggestions(state):
    """Conservative, deterministic story inventory; never paid text inference."""
    text = '\n'.join(str(state.get(k) or '') for k in ('script', 'continuity', 'project_brief'))
    existing = {v['name'] for a in assets(state) for v in a['versions']}
    names = ('钥匙', '手电筒', '对讲机', '背包', '手枪', '登记卡', '信封', '门禁卡', '照片', '手机', '手表', '船票')
    result = []
    for name in names:
        if name in existing or name not in text:
            continue
        context = next((s.strip() for s in re.split('[。！？\n]', text) if name in s), '')[:240]
        result.append({'kind': 'object', 'name': name, 'summary': context or '故事中出现的'+name, 'source': 'story_rule'})
    return result


def validate_references(state, shot, service=None):
    refs = shot.get('asset_references') or []
    if not isinstance(refs,list) or len(refs)>30:
        raise ValueError('镜头素材引用格式无效')
    current={a['id']:a for a in assets(state)}
    for ref in refs:
        if not isinstance(ref,dict) or ref.get('asset_id') not in current:
            raise ValueError('镜头引用了不属于当前项目的素材')
        asset=current[ref['asset_id']];version=_version(asset,ref.get('version'))
        if ref.get('kind')!=asset['kind'] or ref.get('name')!=version['name'] or not isinstance(ref.get('views'),list) or not ref['views']:
            raise ValueError('镜头素材版本信息不完整')
        for view in ref['views']:
            if view not in version.get('views',[]):raise ValueError('镜头素材原图与版本不匹配')
            if service:service._checked_view(state['project_id'],view)


class AssetLibrary:
    def __init__(self, root, database, lock=None):
        self.root = Path(root)
        self.database = Path(database)
        self.lock = lock or threading.RLock()

    def _connect(self):
        con = sqlite3.connect(self.database.resolve().as_uri()+'?mode=rw', uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA busy_timeout=30000')
        return con

    def _load(self, con, project_id, expected_revision=None, require_selected=True):
        if type(project_id) is not int or project_id < 1:
            raise ValueError('项目编号无效')
        selected = con.execute('SELECT current_project FROM workspace WHERE id=1').fetchone()
        if require_selected and (not selected or selected[0] != project_id):
            raise ValueError('当前项目已切换，请重新打开素材库')
        row = con.execute('SELECT body FROM state WHERE id=?', (project_id,)).fetchone()
        if not row:
            raise ValueError('项目不存在')
        revision = con.execute('SELECT COALESCE(MAX(id),0) FROM revisions WHERE project_id=?', (project_id,)).fetchone()[0]
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision != revision):
            raise ValueError('项目版本已变化，请刷新素材库后重试')
        state = json.loads(row[0]); state['project_id'] = project_id; state['revision'] = revision
        return state

    def _folder(self, project_id, create=False):
        base = self.root/'assets'
        path = base
        for component in (None, str(project_id), 'library'):
            path = path if component is None else path/component
            if path.is_symlink():
                raise ValueError('素材目录不可为符号链接')
            if create:
                path.mkdir(mode=0o700,exist_ok=True)
            if path.exists() and not path.is_dir():
                raise ValueError('素材目录无效')
        if path.resolve().parent != (base/str(project_id)).resolve() or not path.resolve().is_relative_to(base.resolve()):
            raise ValueError('素材路径越界')
        return path

    def _file(self, project_id, url):
        match = re.fullmatch(r'/asset-media/([1-9][0-9]*)/([a-f0-9]{32})\.(png|jpg|webp)', str(url))
        if not match or int(match[1]) != project_id:
            raise ValueError('图片不属于当前项目')
        folder = self._folder(project_id)
        file = folder/(match[2]+'.'+match[3])
        if file.is_symlink() or not file.is_file() or file.resolve().parent != folder.resolve():
            raise ValueError('素材图片不存在或路径越界')
        return file

    def _checked_view(self, project_id, view):
        file = self._file(project_id, view['url'])
        with file.open('rb') as stream:
            data = stream.read(MAX_BYTES+1)
        info = inspect_image(data)
        if any(info[k] != view[k] for k in ('sha256', 'width', 'height', 'bytes', 'mime')):
            raise ValueError('素材原图已变化，请重新导入并审阅')
        return data, info

    def _sources(self, state):
        result = []; seen = set(); pid = state['project_id']
        entries = [(s.get('storyboard_local'), s.get('name', '镜头图片')) for s in state.get('shots', [])]
        entries += [(t.get('local_artifact'), t.get('name', '已保存图片')) for t in state.get('image_tasks', [])]
        for url, name in entries:
            if not isinstance(url, str) or url in seen or not re.fullmatch('/media/'+str(pid)+r'/[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp)', url):
                continue
            seen.add(url); result.append({'source_id': hashlib.sha256(url.encode()).hexdigest()[:24], 'url': url, 'name': name})
        return result

    def _public(self, state):
        public_assets=assets(state)
        for asset in public_assets:
            version=_version(asset)
            asset['design_summary']=asset_templates.public_design(asset_templates.blueprint(state,asset,version))
            for candidate in asset['versions']:
                candidate['design_summary']=asset_templates.public_design(asset_templates.blueprint(state,asset,candidate))
                candidate['production_status']=asset_templates.review_status(state,asset,candidate)
                if candidate['design_summary']['ready']:
                    try:asset_templates.verify_skill_source(self.root,candidate.get('design_profile',{}),asset['kind'])
                    except ValueError:
                        candidate['design_summary'].update(ready=False,status='制作助手需按最新Skill重新交接设计')
                        candidate['production_status']=asset_templates.not_reviewed('Skill来源已变化或不可用')
            asset['design_summary']=version['design_summary']
            profile=asset_templates.normalize_profile(version.get('design_profile',{}),asset['kind'])
            asset['master_plan']=profile['master_plan']
            asset['available_view_tags']=list(profile['view_recipes'])
            asset['production_status']=_version(asset,asset['adopted_version'])['production_status'] if asset.get('adopted_version') else asset_templates.not_reviewed('设计与母版待审阅')
            asset['adopted_design_matches_latest']=bool(asset.get('adopted_version') and asset_templates.blueprint(state,asset,_version(asset,asset['adopted_version']))['design_hash']==asset_templates.blueprint(state,asset,version)['design_hash'])
        return {'project_id': state['project_id'], 'revision': state['revision'], 'assets': public_assets, 'project_style':copy.deepcopy(state.get('project_style') or {}),
            'sources': self._sources(state), 'view_labels': VIEWS,
            'shots': [{'id': s['id'], 'name': s['name'], 'asset_references': s.get('asset_references', [])} for s in state.get('shots', [])],
            'limits': {'max_bytes': MAX_BYTES, 'max_side': MAX_SIDE, 'max_pixels': MAX_PIXELS}, 'generation_enabled': False}

    def propose(self, project_id):
        with self.lock, self._connect() as con:
            con.execute('BEGIN')
            state = self._load(con, project_id)
            return {'items': suggestions(state), 'network_called': False, 'note': '已有角色自动保留；物品为故事关键词候选，请按故事取舍，不调用付费文本模型。'}

    def catalog(self, project_id):
        with self.lock, self._connect() as con:
            con.execute('BEGIN')
            return self._public(self._load(con, project_id))

    def media(self, project_id, url):
        with self.lock, self._connect() as con:
            con.execute('BEGIN'); state = self._load(con, project_id)
            views = [v for a in assets(state) for version in a['versions'] for v in version.get('views', [])]
            views += [entry['reference'] for entry in state.get('project_style_history',[]) if entry.get('reference')]
            view = next((v for v in views if v['url'] == url), None)
            if view is None:
                raise ValueError('图片未登记在当前项目素材库')
            return self._checked_view(project_id, view)

    def _source_data(self, state, source_id):
        source = next((s for s in self._sources(state) if s['source_id'] == source_id), None)
        if source is None:
            raise ValueError('请从当前项目已登记的图片中选择，不接受任意本机路径')
        base = self.root/'assets'; folder = base/str(state['project_id']); file = folder/Path(source['url']).name
        if base.is_symlink() or folder.is_symlink() or file.is_symlink() or file.resolve().parent != folder.resolve() or not file.is_file():
            raise ValueError('来源图片不存在或路径越界')
        with file.open('rb') as stream:
            return stream.read(MAX_BYTES+1), source

    def _asset(self, state, asset_id):
        current = assets(state)
        asset = next((a for a in current if a['id'] == asset_id), None)
        if asset is None:
            raise ValueError('当前项目没有该素材')
        # First mutation materializes only this legacy asset, never all characters.
        if not any(a['id'] == asset_id for a in state.get('material_assets', [])):
            state.setdefault('material_assets', []).append(asset)
        return next(a for a in state['material_assets'] if a['id'] == asset_id)

    def _sync_character(self, state, asset, version):
        if asset['kind'] != 'character':
            return
        character_id = asset.get('character_id') or 'asset-'+asset['id']
        asset['character_id'] = character_id
        old = next((c for c in state.get('characters', []) if c['id'] == character_id), None)
        # Adopting a new view alone must not change the existing character context.
        values = {'name': version['name'], 'notes': version['summary'], 'role': version.get('role', '')}
        if old is not None:
            if any(old.get(k, '') != v for k, v in values.items()):
                old.update(values); old['version'] = int(old.get('version') or 1)+1
        else:
            state.setdefault('characters', []).append({'id': character_id, 'version': 1, 'color': '#729c9b', **values})

    def mutate(self, project_id, expected_revision, action, payload):
        if type(expected_revision) is not int:
            raise ValueError('保存素材需要明确项目版本')
        created = []
        with self.lock, self._connect() as con:
            try:
                con.execute('BEGIN IMMEDIATE'); state = self._load(con, project_id, expected_revision)
                self._mutate(state, action, payload, created)
                state.setdefault('material_events', []).append({'id': uuid.uuid4().hex, 'action': action,
                    'asset_id': payload.get('asset_id'), 'at': _now(), 'generation_called': False})
                state.pop('_write_revision', None); state.pop('workflow', None)
                body = json.dumps(state, ensure_ascii=False)
                cursor = con.execute('INSERT INTO revisions(body,project_id) VALUES (?,?)', (body, project_id))
                con.execute('UPDATE state SET body=? WHERE id=?', (body, project_id)); con.commit()
                state['revision'] = cursor.lastrowid
                return self._public(state)
            except Exception:
                con.rollback()
                for file in created:
                    file.unlink(missing_ok=True)
                raise

    def _mutate(self, state, action, payload, created):
        if action == 'style':
            current=state.get('project_style') or {}; prompt=_text(payload.get('description',''),'风格描述',2000)
            if 'style_prompt' in payload:
                detail=_text(payload.get('style_prompt',''),'详细风格描述',12000)
                source=payload.get('style_source',{})
                if not isinstance(source,dict):raise ValueError('风格规范来源无效')
                if source:
                    skill=self.root/'skills'/'frame-visual-style'/'SKILL.md';template=skill.parent/'templates'/'style-bible.md'
                    if source.get('skill_id')!='frame-visual-style' or source.get('skill_version')!='1.0.0' or source.get('skill_sha256')!=hashlib.sha256(skill.read_bytes()).hexdigest() or source.get('template_sha256')!=hashlib.sha256(template.read_bytes()).hexdigest():raise ValueError('风格Skill来源已变化，请重新交接')
            elif prompt==current.get('description',''):
                detail=current.get('prompt','');source=copy.deepcopy(current.get('source') or {})
            else:detail='';source={}
            mode=payload.get('reference_action','keep'); reference=current.get('reference')
            if mode=='clear':reference=None
            elif mode=='select':
                matches=[v for a in assets(state) for ver in a['versions'] for v in ver.get('views',[]) if v['id']==payload.get('view_id')]
                if not matches or any(v['sha256']!=matches[0]['sha256'] for v in matches):raise ValueError('请选择当前项目中已有且版本一致的图片')
                self._checked_view(state['project_id'],matches[0]);reference=copy.deepcopy(matches[0])
            elif mode=='upload':
                encoded=payload.get('base64')
                if not isinstance(encoded,str) or len(encoded)>(MAX_BYTES+2)//3*4:raise ValueError('参考图超过12MB或编码无效')
                try:data=base64.b64decode(encoded,validate=True)
                except (ValueError,binascii.Error):raise ValueError('参考图编码无效') from None
                info=inspect_image(data,_text(payload.get('filename',''),'文件名',180))
                if info['bytes']>10*1024*1024:raise ValueError('风格参考图超过10MB')
                image_id=uuid.uuid4().hex
                file=self._folder(state['project_id'],create=True)/(image_id+'.'+info['extension'])
                with file.open('xb') as out:created.append(file);out.write(data);file.chmod(0o600)
                reference={'id':image_id,'url':f"/asset-media/{state['project_id']}/{image_id}.{info['extension']}",'origin':{'type':'style_upload'},**info}
            elif mode!='keep':raise ValueError('未知风格参考操作')
            if prompt!=current.get('description','') or reference!=current.get('reference') or detail!=current.get('prompt','') or source!=(current.get('source') or {}):
                entry={'version':int(current.get('version',0))+1,'description':prompt,'prompt':detail,'source':source,'reference':reference,'created_at':_now()}
                state['project_style']=entry;state.setdefault('project_style_history',[]).append(copy.deepcopy(entry))
            return
        if action == 'organize':
            selected = payload.get('names')
            proposed = {s['name']: s for s in suggestions(state)}
            if not isinstance(selected, list) or not selected or any(not isinstance(n,str) or n not in proposed for n in selected) or len(selected)!=len(set(selected)):
                raise ValueError('故事素材清单已变化，请重新整理并选择')
            for name in selected:
                self._mutate(state, 'create', proposed[name], created)
            return
        if action == 'create':
            kind = payload.get('kind')
            if kind not in KINDS:
                raise ValueError('素材类型仅支持角色或物品')
            version = {'version': 1, 'name': _text(payload.get('name'), '名称', 80, True),
                'summary': _text(payload.get('summary', ''), '简要设定'), 'role': _text(payload.get('role', ''), '角色定位', 160),
                'variant': _text(payload.get('variant', ''), '外观版本说明', 160), 'views': [], 'created_at': _now(), 'origin': 'user_text'}
            version['related_asset_ids'] = self._related(state,payload.get('related_asset_ids',[]))
            state.setdefault('material_assets', []).append({'id': uuid.uuid4().hex, 'kind': kind,
                'latest_version': 1, 'adopted_version': None, 'versions': [version]})
            return
        if action in ('bind', 'unbind'):
            self._bind(state, action, payload)
            return
        asset = self._asset(state, payload.get('asset_id'))
        if action == 'design':
            profile=asset_templates.normalize_profile(payload.get('profile'),asset['kind'])
            current=_version(asset)
            basis=asset_templates.design_input_hash(state,asset,current)
            if profile.get('input_basis_hash') and profile['input_basis_hash']!=basis:raise ValueError('创作输入已变化，请重新交接设计')
            profile['input_basis_hash']=basis
            if profile!=current.get('design_profile'):
                old=asset_templates.normalize_profile(current.get('design_profile',{}),asset['kind'])
                # Adding view recipes alone keeps existing candidates, but never grants a new approval.
                shared=('subtype','fields','standard_setup','master_plan','input_basis_hash')
                extend_only=all(old.get(k)==profile.get(k) for k in shared) and all(profile['view_recipes'].get(k)==v for k,v in old.get('view_recipes',{}).items())
                version=copy.deepcopy(current);version.update(design_profile=profile,views=copy.deepcopy(current.get('views',[])) if extend_only else [],origin='system_design_draft')
                _append(asset,version)
        elif action == 'edit':
            current = _version(asset); version = copy.deepcopy(current)
            for field, limit, required in [('name',80,True), ('summary',4000,False), ('role',160,False), ('variant',160,False)]:
                if field in payload:
                    version[field] = _text(payload[field], field, limit, required)
            if 'related_asset_ids' in payload:version['related_asset_ids']=self._related(state,payload['related_asset_ids'])
            if any(version.get(k) != current.get(k) for k in ('name', 'summary', 'role', 'variant','related_asset_ids')):
                if any(version.get(k)!=current.get(k) for k in ('summary','variant')):
                    version['views']=[]
                _append(asset, version)
        elif action in ('upload', 'import-existing'):
            tag = payload.get('view_tag')
            if tag not in VIEWS[asset['kind']]:
                raise ValueError('请选择适用于该素材类型的单张视图')
            if action == 'upload':
                encoded = payload.get('base64')
                if not isinstance(encoded, str) or len(encoded) > (MAX_BYTES+2)//3*4:
                    raise ValueError('上传图片超过12MB或编码无效')
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as error:
                    raise ValueError('图片编码无效') from error
                origin = {'type': 'browser_upload', 'filename': _text(payload.get('filename', ''), '文件名', 180)}
                info = inspect_image(data, origin['filename'])
            else:
                data, source = self._source_data(state, payload.get('source_id'))
                info = inspect_image(data); origin = {'type': 'project_image', 'source_url': source['url']}
            image_id = uuid.uuid4().hex
            folder = self._folder(state['project_id'], create=True)
            file = folder/(image_id+'.'+info['extension'])
            with file.open('xb') as stream:
                created.append(file); stream.write(data); file.chmod(0o600)
            view = {'id': image_id, 'tag': tag, 'label': VIEWS[asset['kind']][tag],
                'url': f"/asset-media/{state['project_id']}/{image_id}.{info['extension']}", 'imported_at': _now(), 'origin': origin, **info}
            version = copy.deepcopy(_version(asset))
            identity=asset_templates.normalize_profile(version.get('design_profile',{}),asset['kind'])['master_plan'].get('identity_tag','portrait' if asset['kind']=='character' else 'main')
            if tag == identity:
                version['views']=[]
            version['views'] = [v for v in version.get('views', []) if v['tag'] != tag] + [view]
            version['origin'] = 'image_import'; _append(asset, version)
        elif action == 'adopt':
            number = payload.get('version')
            if type(number) is not int:
                raise ValueError('请明确选择采用的版本')
            version = _version(asset, number)
            asset_templates.verify_skill_source(self.root,version.get('design_profile',{}),asset['kind'])
            for view in version.get('views', []):
                self._checked_view(state['project_id'], view)
            asset['adopted_version'] = number
            review=asset_templates.review_record(state,asset,version)
            review['reviewed_at']=_now()
            asset.setdefault('production_reviews',[]).append(review)
            asset.setdefault('adoption_history', []).append({'version': number, 'adopted': True, 'at': _now()})
            self._sync_character(state, asset, version)
        elif action == 'unadopt':
            if asset.get('adopted_version') is None or type(payload.get('version')) is not int or payload.get('version') != asset.get('adopted_version'):
                raise ValueError('采用版本已变化，请刷新后重试')
            asset.setdefault('adoption_history', []).append({'version': asset['adopted_version'], 'adopted': False, 'at': _now()})
            asset['adopted_version'] = None
        else:
            raise ValueError('不支持的素材操作')

    def _related(self,state,values):
        allowed={a['id'] for a in assets(state) if a['kind']=='character'}
        if not isinstance(values,list) or len(values)>30 or any(not isinstance(v,str) or v not in allowed for v in values):
            raise ValueError('关联角色须来自当前项目')
        return list(dict.fromkeys(values))

    def _bind(self, state, action, payload):
        shot = next((s for s in state.get('shots', []) if s['id'] == payload.get('shot_id')), None)
        if shot is None:
            raise ValueError('当前项目没有该镜头')
        old = copy.deepcopy(shot.get('asset_references') or [])
        asset_id = payload.get('asset_id')
        refs = [r for r in old if r['asset_id'] != asset_id]
        if action == 'bind':
            asset = self._asset(state, asset_id); number = payload.get('version')
            if type(number) is not int or asset.get('adopted_version') != number:
                raise ValueError('只能选择人工采用的明确素材版本')
            version = _version(asset, number); ids = payload.get('view_ids')
            asset_templates.verify_skill_source(self.root,version.get('design_profile',{}),asset['kind'])
            status=asset_templates.review_status(state,asset,version)
            if not isinstance(ids, list) or not ids or len(ids) > 10 or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
                raise ValueError('请选择1–10张独立视图')
            views = []
            for image_id in ids:
                view = next((v for v in version.get('views', []) if v['id'] == image_id), None)
                if view is None:
                    raise ValueError('图片不属于选定的素材版本')
                if view['tag'] not in status['ref_eligible_tags']:
                    raise ValueError('素材设计或制作规范已更新，请按当前规范重新审阅后选择')
                required=asset_templates.recipe(asset['kind'],view['tag'],view.get('origin',{}).get('model','qwen-image-3.0-pro'),version.get('design_profile'))['template']['requires']
                if asset['kind']=='character' and required and not status['identity_reviewed']:
                    raise ValueError('角色身份母版尚未按当前规范审阅')
                if 'body' in required and not status['body_reviewed']:
                    raise ValueError('全身正面母版尚未按当前规范审阅')
                self._checked_view(state['project_id'], view); views.append(copy.deepcopy(view))
            refs.append({'asset_id': asset['id'], 'kind': asset['kind'], 'version': number,
                'name': version['name'], 'variant': version.get('variant', ''), 'views': views,
                'production_review':asset_templates.review_record(state,asset,version)})
        if sum(len(ref.get('views',[])) for ref in refs)>3:raise ValueError('本镜最多选择3张素材参考，请只选关键视图')
        if refs != old:
            shot['asset_references'] = refs
            shot.update(approved=False, text_approved=False, status='待确认')
            if shot.get('storyboard_task_id'):
                shot['image_quality'] = 'unreviewed'


def handle_post(service, project_id, revision, action, payload):
    """Small explicit adapter for host integration/tests; no hidden filesystem scans."""
    return service.mutate(project_id, revision, action, payload)
