"""Local go-music-dl companion. No generation credentials are inherited."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'data' / 'music-service'
URL = 'http://127.0.0.1:8767/music'
LOCK = threading.Lock()


def status():
    ready = False
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + '/healthz', timeout=2) as response:
            result = json.loads(response.read(4096))
            ready = result.get('app') == 'go-music-dl' and result.get('status') == 'ok'
    except Exception:
        pass
    return {'ready': ready, 'installed': (RUNTIME / 'music-dl').is_file(),
            'url': URL, 'version': 'v1.1.3', 'downloads': 'data/music-service/data/downloads'}


def start():
    with LOCK:
        if status()['ready']:
            return status()
        binary = RUNTIME / 'music-dl'
        if not binary.is_file():
            raise ValueError('尚未安装音乐服务，请按 docs/MUSIC.md 安装发布包')
        # Desktop mode is upstream's loopback-only server. Keep all private
        # studio provider keys and custom credential locations out of its env.
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG') if k in os.environ}
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with (RUNTIME / 'service.log').open('ab') as log:
            process = subprocess.Popen([str(binary), 'web', '--desktop', '--no-browser', '--port', '8767'],
                                       cwd=RUNTIME, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
        for _ in range(30):
            result = status()
            if result['ready']:
                return result
            if process.poll() is not None:
                break
            time.sleep(.1)
        raise ValueError('音乐服务未启动，请检查 8767 端口或 data/music-service/service.log')
