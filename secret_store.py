"""Repository-external credential storage. No secret value is logged or returned."""
import json
import os
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
ALLOWED = ('WAN3_API_KEY', 'DASHSCOPE_API_KEY', 'ARK_API_KEY')

def secret_path():
    path=Path(os.getenv('STUDIO_SECRET_FILE', str(ROOT.parent/'.video-agent-studio-private'/'credentials.json'))).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('密钥路径必须位于项目仓库之外')
    return path

def stored():
    path=secret_path()
    if not path.exists():return {}
    try:
        data=json.loads(path.read_text())
        return {k:v for k,v in data.items() if k in ALLOWED and isinstance(v,str)}
    except Exception:
        raise ValueError('无法读取仓库外私密配置，请检查文件权限和格式') from None

def get_key(name):
    return stored().get(name) or os.getenv(name,'')

def write_key(name,value):
    if name not in ALLOWED:raise ValueError('未知密钥类型')
    if not isinstance(value,str) or not 8<=len(value.strip())<=4096:raise ValueError('密钥长度无效')
    path=secret_path();path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.parent.chmod(0o700)
    data=stored();data[name]=value.strip()
    fd,tmp=tempfile.mkstemp(prefix='.credentials-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f:json.dump(data,f)
        os.replace(tmp,path);path.chmod(0o600)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def redact(value):
    """Defense in depth for API responses and errors containing a known credential."""
    try: values=list(stored().values())
    except ValueError:values=[]
    values += [os.getenv(k,'') for k in ALLOWED]
    def clean(item):
        if isinstance(item,dict):return {k:clean(v) for k,v in item.items()}
        if isinstance(item,list):return [clean(v) for v in item]
        if isinstance(item,str):
            for token in values:
                if token:item=item.replace(token,'[REDACTED]')
        return item
    return clean(value)
