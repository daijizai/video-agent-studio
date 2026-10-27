#!/usr/bin/env python3
"""Concatenate reviewed, same-codec MP4 shots; optionally burn UTF-8 SRT subtitles."""
import argparse, subprocess, tempfile, shutil
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('clips',nargs='+');p.add_argument('-o','--output',required=True);p.add_argument('--subtitles');a=p.parse_args()
if not shutil.which('ffmpeg'):p.error('请先安装 FFmpeg，并将其加入 PATH')
clips=[Path(x).resolve() for x in a.clips]
if any(not x.is_file() for x in clips):p.error('镜头文件不存在')
out=Path(a.output).resolve()
if out.exists():p.error('输出文件已存在，请使用新文件名')
with tempfile.TemporaryDirectory() as tmp:
    listing=Path(tmp)/'clips.txt';listing.write_text(''.join("file '"+str(x).replace("'", "'\\''")+"'\n" for x in clips))
    cmd=['ffmpeg','-n','-f','concat','-safe','0','-i',str(listing)]
    if a.subtitles:
        sub=Path(a.subtitles).resolve()
        if not sub.is_file():p.error('字幕不存在')
        shutil.copyfile(sub,Path(tmp)/'captions.srt');cmd+=['-vf','subtitles=captions.srt','-c:v','libx264','-c:a','aac']
    else:cmd+=['-c','copy']
    subprocess.run(cmd+[str(out)],cwd=tmp,check=True)
