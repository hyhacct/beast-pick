"""Run the delivered EXE outside the developer environment, with no UI input."""
import json
import hashlib
import argparse
import os
import subprocess
import sys
import tempfile
import struct
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from beast_pick import __version__
parser = argparse.ArgumentParser()
parser.add_argument('exe', nargs='?', type=Path, default=root / 'dist' / 'BP.exe')
parser.add_argument('--check-game', action='store_true')
parser.add_argument('--check-updates', action='store_true')
options = parser.parse_args()
exe = options.exe
archive = CArchiveReader(str(exe))
assert b'%LOCALAPPDATA%\\BP\\runtime' in exe.read_bytes(), 'EXE must use the per-user runtime extraction directory'
icu = [name for name in archive.toc if Path(name).name.lower().startswith(('icuuc', 'icuin', 'icudt'))]
assert not icu, f'Incompatible ICU bundled: {icu}'
payload_hashes = {}
for relative in ('beast_pick/agent.js', 'beast_pick/filters.js', 'beast_pick/apply_update.ps1', 'beast_pick/profiles/current.json', 'beast_pick/data/items.json',
                 'beast_pick/assets/beast-pick.ico', 'beast_pick/assets/beast-pick.png'):
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
    if options.check_updates:
        args.append('--check-updates')
    process = subprocess.run(args, cwd=work, env=env, timeout=85 if options.check_updates else 45)
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
    resource_types = {entry.id for entry in binary.DIRECTORY_ENTRY_RESOURCE.entries}
    assert {3, 14}.issubset(resource_types), 'EXE icon resources are missing'
    icon_source = (root / 'beast_pick/assets/beast-pick.ico').read_bytes()
    icon_count = struct.unpack_from('<H', icon_source, 4)[0]
    expected_frames = set()
    for index in range(icon_count):
        length, offset = struct.unpack_from('<II', icon_source, 6 + index * 16 + 8)
        expected_frames.add(icon_source[offset:offset + length])
    icon_resources = next(entry for entry in binary.DIRECTORY_ENTRY_RESOURCE.entries if entry.id == 3)
    actual_frames = set()
    for entry in icon_resources.directory.entries:
        for language in entry.directory.entries:
            resource = language.data.struct
            actual_frames.add(binary.get_data(resource.OffsetToData, resource.Size))
    assert len(expected_frames) == 7 and expected_frames.issubset(actual_frames), 'EXE does not contain the custom icon frames'
assert report['max_radius'] == 500
assert report['item_types']['weapons'] is False
assert report['style'] in ('windowsvista', 'windows')
assert report['custom_icon'] and report['update_notice'] and report['update_download_requires_consent']
assert report['update_prompt_notes_visible']
print(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({'payloads_match_source': payload_hashes}, indent=2))
