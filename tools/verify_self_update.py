"""Exercise replacement into an isolated directory and open the real packaged BP.

Never connects to the game. Close the opened verification window after inspection.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beast_pick.installer import prepare_update, start_install, file_hash


def main():
    root = Path(tempfile.mkdtemp(prefix='self-update-smoke-', dir=ROOT / 'artifacts'))
    compiler = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    source = root / 'old.cs'
    source.write_text('using System; using System.IO; using System.Threading; class App { static void Main() { while(!File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"exit"))) Thread.Sleep(30); } }')
    target = root / 'BP.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/out:' + str(target), str(source)], check=True, capture_output=True)
    settings = root / 'settings.json'
    original_settings = json.dumps(dict(radius=9, corpses=False, items=True, containers=False)).encode()
    settings.write_bytes(original_settings)
    session = prepare_update(target)
    shutil.copyfile(ROOT / 'dist/BP.exe', session.payload)
    expected = file_hash(session.payload)
    old = subprocess.Popen([str(target)], creationflags=subprocess.CREATE_NO_WINDOW)
    helper = start_install(session, expected, parent_pid=old.pid, no_error_dialog=True)
    try:
        deadline = time.monotonic() + 15
        while session.status().get('state') not in ('ready', 'failed') and time.monotonic() < deadline:
            time.sleep(0.05)
        assert session.status().get('state') == 'ready', session.status()
        assert old.poll() is None
        (root / 'exit').write_text('exit')
        old.wait(timeout=5)
        assert helper.wait(timeout=45) == 0, session.status()
        assert file_hash(target) == expected
        assert not session.folder.exists()
        assert settings.read_bytes() == original_settings
        report = dict(ok=True, target=str(target), old_exe_removed=True, temporary_files_removed=True,
                      settings_preserved=True, new_window_started=True, sha256=expected)
        (ROOT / 'artifacts/self-update-packaged-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        if old.poll() is None:
            old.terminate()
            old.wait(timeout=5)
        if helper.poll() is None:
            helper.terminate()
            helper.wait(timeout=5)


if __name__ == '__main__':
    main()
