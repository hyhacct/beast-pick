"""Production-client connect/stop/detach check with a bounded survival watch."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frida
from beast_pick.backend import Client, PROCESS

report = {'started': datetime.now().isoformat(), 'cycles': []}
try:
    for cycle in range(3):
        with Client() as client:
            connection = client.connect()
            pid = connection['pid']
            time.sleep(1)
            client.stop()
            state = client.heartbeat()
            assert state['enabled'] is False
        report['cycles'].append({'pid': pid, 'state': state, 'closed': datetime.now().isoformat()})
        time.sleep(2)
        assert any(p.pid == pid for p in frida.get_local_device().enumerate_processes()), 'Game exited after detach'
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        assert any(p.pid == pid for p in frida.get_local_device().enumerate_processes()), 'Game exited during survival watch'
        time.sleep(1)
    report.update(ok=True, alive_pid=pid, post_detach_watch_seconds=25)
except BaseException as exc:
    report.update(ok=False, error=repr(exc))
    raise
finally:
    report['finished'] = datetime.now().isoformat()
    (ROOT/'artifacts/lifecycle-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
