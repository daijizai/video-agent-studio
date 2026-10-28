"""Bounded, dependency-free PNG validation and exact binary-mask compositing."""
import hashlib
import re
import struct
import zlib
from pathlib import Path

MAX_BYTES = 20*1024*1024
MAX_PIXELS = 2048*2048
SIGNATURE = b'\x89PNG\r\n\x1a\n'

def sha(data): return hashlib.sha256(data).hexdigest()

def asset(root, project_id, url):
    if type(project_id) is not int or project_id < 1 or not isinstance(url, str):
        raise ValueError('项目或素材路径无效')
    if not re.fullmatch('/media/'+str(project_id)+r'/[A-Za-z0-9_-]+\.png', url):
        raise ValueError('素材须属于当前项目，且为PNG')
    assets_root = Path(root)/'assets'
    project_root = assets_root/str(project_id)
    if assets_root.is_symlink() or project_root.is_symlink(): raise ValueError('素材目录不能为符号链接')
    base = project_root.resolve()
    if base.parent != assets_root.resolve(): raise ValueError('素材目录越界')
    file = base/Path(url).name
    if file.is_symlink() or file.resolve().parent != base or not file.is_file():
        raise ValueError('素材不存在或路径越界')
    with file.open('rb') as stream: data = stream.read(MAX_BYTES+1)
    decode(data)
    return data

def decode(data):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES or not data.startswith(SIGNATURE):
        raise ValueError('仅支持20MB以内PNG')
    offset = 8; compressed = bytearray(); header = None; ended = False
    while offset+12 <= len(data):
        size = struct.unpack('>I', data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]; body = data[offset+8:offset+8+size]
        if len(body) != size or offset+12+size > len(data): raise ValueError('PNG截断')
        crc = struct.unpack('>I', data[offset+8+size:offset+12+size])[0]
        if zlib.crc32(kind+body) & 0xffffffff != crc: raise ValueError('PNG校验失败')
        if header is None and kind != b'IHDR': raise ValueError('PNG头缺失')
        if kind == b'IHDR':
            if header is not None or size != 13: raise ValueError('PNG头无效')
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT': compressed.extend(body)
        elif kind == b'IEND':
            if size: raise ValueError('PNG结束无效')
            ended = True; offset += size+12; break
        elif kind in (b'acTL', b'tRNS') or (kind[:1].isupper() and kind not in (b'PLTE',)):
            raise ValueError('不支持此PNG类型')
        offset += size+12
    if not ended or offset != len(data): raise ValueError('PNG未完整结束')
    width, height, depth, color, compression, filtering, interlace = header
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color)
    if not channels or depth != 8 or compression or filtering or interlace:
        raise ValueError('仅支持8bit非交错灰度/RGB/RGBA PNG')
    if not 64 <= width <= 2048 or not 64 <= height <= 2048 or width*height > MAX_PIXELS or width%8 or height%8:
        raise ValueError('图片须为64–2048像素且宽高为8的倍数')
    stride = width*channels; expected = (stride+1)*height
    dec = zlib.decompressobj()
    try: raw = dec.decompress(bytes(compressed), expected+1)
    except zlib.error as exc: raise ValueError('PNG压缩数据无效') from exc
    if len(raw) != expected or not dec.eof or dec.unused_data or dec.unconsumed_tail:
        raise ValueError('PNG像素数据长度无效')
    previous = bytearray(stride); rgba = bytearray()
    for y in range(height):
        start = y*(stride+1); mode = raw[start]; row = bytearray(raw[start+1:start+1+stride])
        if mode > 4: raise ValueError('PNG过滤无效')
        for x in range(stride):
            a = row[x-channels] if x >= channels else 0; b = previous[x]; c = previous[x-channels] if x >= channels else 0
            if mode == 1: pred = a
            elif mode == 2: pred = b
            elif mode == 3: pred = (a+b)//2
            elif mode == 4:
                p = a+b-c; distances = (abs(p-a), abs(p-b), abs(p-c))
                pred = (a, b, c)[distances.index(min(distances))]
            else: pred = 0
            row[x] = (row[x]+pred) & 255
        for x in range(0, stride, channels):
            if color == 0: rgba.extend((row[x], row[x], row[x], 255))
            elif color == 2: rgba.extend((*row[x:x+3], 255))
            elif color == 4: rgba.extend((row[x], row[x], row[x], row[x+1]))
            else: rgba.extend(row[x:x+4])
        previous = row
    return width, height, bytes(rgba)

def encode(width, height, rgba):
    def chunk(kind, value): return struct.pack('>I', len(value))+kind+value+struct.pack('>I', zlib.crc32(kind+value)&0xffffffff)
    rows = b''.join(b'\0'+rgba[y*width*4:(y+1)*width*4] for y in range(height))
    return SIGNATURE+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))+chunk(b'IDAT', zlib.compress(rows))+chunk(b'IEND', b'')

def inputs(source, mask):
    width, height, pixels = decode(source); mw, mh, mp = decode(mask)
    if (width, height) != (mw, mh): raise ValueError('遮罩与原图尺寸须相同')
    values = set()
    for i in range(0, len(mp), 4):
        r, g, b, a = mp[i:i+4]
        if r != g or r != b or r not in (0, 255) or a != 255:
            raise ValueError('首版遮罩须为不透明纯黑白图：白色修改，黑色保留')
        values.add(r)
    if values != {0, 255}: raise ValueError('遮罩须同时含保留和修改区域')
    return width, height, pixels, mp

def composite(source, mask, generated):
    width, height, original, mp = inputs(source, mask); gw, gh, result = decode(generated)
    if (width, height) != (gw, gh): raise ValueError('输出尺寸与原图不符')
    out = bytearray(original)
    for i in range(0, len(out), 4):
        if mp[i] == 255: out[i:i+4] = result[i:i+4]
    return encode(width, height, bytes(out))
