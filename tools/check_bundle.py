"""Run the delivered EXE outside the developer environment, with no UI input."""
import json
import hashlib
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from beast_pick import __version__
parser = argparse.ArgumentParser()
parser.add_argument('exe', nargs='?', type=Path, default=root / 'dist' / 'beast-pick.exe')
parser.add_argument('--check-game', action='store_true')
options = parser.parse_args()
exe = options.exe
archive = CArchiveReader(str(exe))
icu = [name for name in archive.toc if Path(name).name.lower().startswith(('icuuc', 'icuin', 'icudt'))]
assert not icu, f'Incompatible ICU bundled: {icu}'
payload_hashes = {}
for relative in ('beast_pick/agent.js', 'beast_pick/filters.js', 'beast_pick/profiles/current.json', 'beast_pick/data/items.json'):
    entry = next(name for name in archive.toc if name.replace('\\', '/') == relative)
    bundled = archive.extract(entry)
    assert bundled == (root / relative).read_bytes(), f'Stale bundled payload: {relative}'
    payload_hashes[relative] = hashlib.sha256(bundled).hexdigest()
env = {key: value for key, value in os.environ.items()
       if not key.upper().startswith(('PYTHON', 'QT_', 'PYSIDE', 'SHIBOKEN'))}
env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32') + ';' + os.environ['SystemRoot']
report_path = root / 'artifacts' / 'packaged-self-check.json'
report_path.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='beast-pick-clean-launch-') as work:
    args = [str(exe.resolve()), '--self-check', str(report_path)]
    if options.check_game:
        args.append('--check-game')
    process = subprocess.run(args, cwd=work, env=env, timeout=45)
    assert process.returncode == 0, f'Packaged process failed: {process.returncode}'
report = json.loads(report_path.read_text(encoding='utf-8'))
assert report['ok'], report
assert report['version'] == __version__
import pefile
with pefile.PE(str(exe)) as binary:
    fixed = binary.VS_FIXEDFILEINFO[0]
    actual_version = (fixed.FileVersionMS >> 16, fixed.FileVersionMS & 65535,
                      fixed.FileVersionLS >> 16, fixed.FileVersionLS & 65535)
    assert actual_version == (*map(int, __version__.split('.')), 0), actual_version
assert report['max_radius'] == 500
assert report['item_types']['weapons'] is False
assert report['style'] in ('windowsvista', 'windows')
print(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({'payloads_match_source': payload_hashes}, indent=2))
