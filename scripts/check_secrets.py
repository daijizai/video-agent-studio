#!/usr/bin/env python3
"""Scan working/staged/tracked sources and all local Git history without printing secrets."""
import re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import secret_store
patterns=[re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(rb'github_pat_[A-Za-z0-9_]{30,}'),re.compile(rb'sk-[A-Za-z0-9_-]{24,}'),re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')]
known=[v.encode() for v in secret_store.stored().values() if v]
failures=[];count=0

def check(path,data,label):
    global count
    count+=1
    if path=='.env' or path.startswith('data/') or path.endswith(('.pem','credentials.json')):failures.append(label+': protected path')
    if any(p.search(data) for p in patterns) or any(v in data for v in known):failures.append(label+': credential pattern/value')

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
for path in set(git('ls-files','--cached','--others','--exclude-standard').decode().splitlines()):
    p=ROOT/path
    if p.is_file():check(path,p.read_bytes(),'working:'+path)
for entry in git('ls-files','--stage').decode().splitlines():
    meta,path=entry.split('\t',1);sha=meta.split()[1];check(path,git('cat-file','blob',sha),'staged:'+path)
for commit in git('rev-list','--all').decode().splitlines():
    for entry in git('ls-tree','-r',commit).decode().splitlines():
        meta,path=entry.split('\t',1);sha=meta.split()[2];check(path,git('cat-file','blob',sha),'history:'+commit[:8]+':'+path)
if failures:
    print('FAIL: '+str(len(failures))+' findings (values withheld)');print('\n'.join(failures));sys.exit(1)
print('PASS: '+str(count)+' working/staged/history blobs checked; no known secrets or high-confidence credential patterns found. External credential file is outside Git.')
