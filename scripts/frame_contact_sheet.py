#!/usr/bin/env python3
"""Build timestamped contact sheets from progressive_frames.py's cached manifest."""
import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from PIL import Image, ImageDraw

def build(cache, output, fps, start, end):
 cache=Path(cache);output=Path(output);data=json.loads((cache/'frames.json').read_text());records=data['frames']
 targets=[Fraction(k,fps) for k in range(math.ceil(start*fps),math.ceil(end*fps))]
 if not targets:raise ValueError('没有目标时间点')
 selected=[]
 for t in targets:
  key=f'{t.numerator}/{t.denominator}'
  if key not in records:raise ValueError(f'缺少抽帧 {float(t):.3f} 秒，请先运行抽帧脚本')
  rec=records[key];name=rec['file'];path=cache/name
  if Path(name).name!=name or path.is_symlink() or not path.is_file():raise ValueError('缓存帧路径无效')
  if hashlib.sha256(path.read_bytes()).hexdigest()!=rec['sha256']:raise ValueError('缓存帧内容发生变化')
  selected.append((t,rec,path))
 output.mkdir(parents=True,exist_ok=True);pages=[]
 for offset in range(0,len(selected),24):
  chunk=selected[offset:offset+24];cols=4;rows=math.ceil(len(chunk)/cols);canvas=Image.new('RGB',(1280,rows*204),'#151515');draw=ImageDraw.Draw(canvas)
  for j,(t,rec,path) in enumerate(chunk):
   tile=Image.open(path).convert('RGB');tile.thumbnail((320,180));x=j%cols*320;y=j//cols*204;canvas.paste(tile,(x,y+24));draw.text((x+3,y+4),f'target {float(t):.3f}s  actual {rec["actual_seconds"]:.3f}s',fill='white')
  page=output/f'contact-{offset//24+1:03d}.jpg'
  if page.exists():raise FileExistsError(f'输出已存在: {page}')
  canvas.save(page,quality=90);pages.append(str(page))
 return {'source_sha256':data['source_sha256'],'target_count':len(targets),'pages':pages}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('cache');p.add_argument('output');p.add_argument('--fps',type=int,required=True,choices=(1,2,3,4,8,16));p.add_argument('--start',default='0');p.add_argument('--end',required=True);a=p.parse_args()
 print(json.dumps(build(a.cache,a.output,a.fps,Fraction(a.start),Fraction(a.end)),ensure_ascii=False))
if __name__=='__main__':main()
