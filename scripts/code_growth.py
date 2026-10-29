#!/usr/bin/env python3
"""Generate a deterministic, hand-drawn SVG from daily Git source snapshots."""
import datetime as dt
import html
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.sh'}
ZONE = dt.timezone(dt.timedelta(hours=8))


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def history():
    daily = {}
    # First-parent snapshots describe the main branch, including merged changes.
    for row in git('log', '--first-parent', '--reverse', '--format=%H %ct', 'HEAD').decode().splitlines():
        commit, timestamp = row.split()
        day = dt.datetime.fromtimestamp(int(timestamp), ZONE).date().isoformat()
        daily[day] = commit
    counts = {}
    points = []
    for day, commit in sorted(daily.items()):
        total = 0
        for entry in git('ls-tree', '-rz', commit).split(b'\0'):
            if not entry:
                continue
            meta, raw_path = entry.split(b'\t', 1)
            mode, kind, sha = meta.decode().split()
            path = Path(raw_path.decode())
            if kind != 'blob' or mode == '120000' or path.suffix not in EXTENSIONS:
                continue
            if any(p in {'node_modules', 'vendor', 'data', '.venv', 'venv', 'review-previews'} for p in path.parts):
                continue
            if sha not in counts:
                blob = git('cat-file', 'blob', sha)
                counts[sha] = sum(bool(line.strip()) for line in blob.splitlines()) if b'\0' not in blob else 0
            total += counts[sha]
        points.append({'date': day, 'lines': total})
    return points


def render(points):
    width, height = 960, 440
    left, right, top, bottom = 100, 900, 100, 338
    first = dt.date.fromisoformat(points[0]['date'])
    span = max(1, (dt.date.fromisoformat(points[-1]['date']) - first).days)
    maximum = max(1, max(p['lines'] for p in points))
    ceiling = max(1000, math.ceil(maximum / 5000) * 5000)
    coords = [(left + (dt.date.fromisoformat(p['date']) - first).days / span * (right-left), bottom-p['lines']/ceiling*(bottom-top)) for p in points]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">代码量增长 · Code growth</title>',
           '<desc id="desc">每日源码非空行数，日期按北京时间。包含测试和注释，排除文档和素材。</desc>',
           '<rect x="2" y="2" width="956" height="436" rx="18" fill="#fffdf6" stroke="#ded7c7"/>',
           '<g font-family="Comic Sans MS, Chalkboard SE, cursive, sans-serif" fill="#343a40">',
           '<text x="40" y="48" font-size="25" font-weight="bold">代码一点点，故事一帧帧。</text>',
           f'<text x="40" y="77" font-size="14" fill="#73716b">CODE GROWTH / {points[-1]["date"]} / {points[-1]["lines"]:,} non-empty lines</text>']
    for i in range(5):
        y = bottom - i / 4 * (bottom-top)
        out += [f'<path d="M {left} {y:.1f} Q 500 {y+1:.1f} {right} {y:.1f}" fill="none" stroke="#e5e0d4" stroke-dasharray="4 7"/>', f'<text x="86" y="{y+5:.1f}" text-anchor="end" font-size="13">{ceiling*i/4:,.0f}</text>']
    out += [f'<path d="M {left-1} {top-5} Q {left+2} 220 {left} {bottom+1} Q 500 {bottom-1} {right+12} {bottom+1}" fill="none" stroke="#45443e" stroke-width="2" stroke-linecap="round"/>']
    path = 'M ' + ' L '.join(f'{x:.2f} {y:.2f}' for x,y in coords)
    out += [f'<path d="{path} L {coords[-1][0]:.2f} {bottom} L {coords[0][0]:.2f} {bottom} Z" fill="#bce2d5" opacity=".35"/>']
    # Two offset strokes give a pen/sketch feel without SVG filters or scripts.
    sketch = 'M ' + ' L '.join(f'{x+math.sin(i*3)*1.3:.2f} {y+math.cos(i*2)*1.6:.2f}' for i,(x,y) in enumerate(coords))
    out += [f'<path d="{path}" fill="none" stroke="#238778" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>', f'<path d="{sketch}" fill="none" stroke="#238778" stroke-width="1" opacity=".5"/>']
    for p,(x,y) in zip(points,coords):
        out += [f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#fffdf6" stroke="#238778" stroke-width="2"><title>{html.escape(p["date"])}: {p["lines"]:,} lines</title></circle>']
    indices = sorted({round(i*(len(points)-1)/min(5,max(1,len(points)-1))) for i in range(min(5,len(points)-1)+1)})
    for i in indices:
        out += [f'<text x="{coords[i][0]:.2f}" y="366" text-anchor="middle" font-size="13">{points[i]["date"]}</text>']
    out += ['<text x="34" y="112" font-size="13">行数</text>', '<text x="900" y="394" text-anchor="end" font-size="13">日期 / UTC+8</text>', '<text x="40" y="414" font-size="12" fill="#73716b">Git history · 源码非空行（含测试与注释） · 自动更新 · 减少也如实记录</text>', '</g></svg>']
    return '\n'.join(out) + '\n'


def main():
    points = history()
    if not points:
        raise SystemExit('No Git history found')
    output = ROOT / 'docs/metrics'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'code-growth.json').write_text(json.dumps(points, indent=2) + '\n')
    (output / 'code-growth.svg').write_text(render(points))
    print(f'{len(points)} daily snapshots; latest: {points[-1]["lines"]:,} lines')


if __name__ == '__main__':
    main()
