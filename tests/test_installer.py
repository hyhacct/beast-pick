import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from beast_pick.installer import acknowledge_update, discard_update, file_hash, fresh_environment, prepare_update, start_install


def wait_until(predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError('Update operation timed out')


@pytest.fixture(scope='module')
def sample_exes(tmp_path_factory):
    if os.name != 'nt':
        pytest.skip('Windows replacement tests')
    compiler = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.exists():
        pytest.skip('Windows C# compiler is unavailable')
    root = tmp_path_factory.mktemp('updater-exes')
    programs = {
        'old': '''string dir=AppDomain.CurrentDomain.BaseDirectory;
            if(args.Length==0) { while(!File.Exists(Path.Combine(dir,"exit"))) Thread.Sleep(30); }
            else File.WriteAllText(Path.Combine(dir,"recovered.txt"),"old");''',
        'new': '''string dir=AppDomain.CurrentDomain.BaseDirectory;
            File.WriteAllText(Path.Combine(dir,"launched.txt"),"new");
            if(args.Length==2 && args[0]=="--complete-update") File.WriteAllText(Path.Combine(args[1],"started"),"ok");''',
        'bad': 'Environment.Exit(1);',
    }
    result = {}
    for name, body in programs.items():
        source = root / f'{name}.cs'
        source.write_text('using System; using System.IO; using System.Threading; class App { static void Main(string[] args) {' + body + '} }')
        exe = root / f'{name}.exe'
        subprocess.run([str(compiler), '/nologo', '/target:winexe', '/out:' + str(exe), str(source)], check=True, capture_output=True)
        result[name] = exe
    return result


def test_staging_and_acknowledgement_stay_beside_the_current_exe(tmp_path):
    target = tmp_path / 'BP.exe'
    target.write_bytes(b'old')
    session = prepare_update(target)
    assert session.folder.parent == target.parent
    assert session.payload == session.folder / 'new.exe'
    session.payload.write_bytes(b'new')
    assert file_hash(session.payload) == hashlib.sha256(b'new').hexdigest()
    discard_update(session)
    assert not session.folder.exists() and target.read_bytes() == b'old'


def test_acknowledgement_requires_the_expected_target_and_hash(tmp_path):
    import json
    target = tmp_path / 'BP.exe'
    target.write_bytes(b'new')
    session = prepare_update(target)
    (session.folder / 'plan.json').write_text(json.dumps(dict(target=str(target), payload_sha256=file_hash(target))))
    acknowledge_update(['--complete-update', str(session.folder)], target)
    assert (session.folder / 'started').read_text() == 'ok'
    (session.folder / 'started').unlink()
    target.write_bytes(b'changed')
    acknowledge_update(['--complete-update', str(session.folder)], target)
    assert not (session.folder / 'started').exists()
    discard_update(session)


def test_fresh_environment_drops_inherited_pyinstaller_runtime(monkeypatch):
    monkeypatch.setenv('_PYI_APPLICATION_HOME_DIR', r'C:\old\_MEI123')
    monkeypatch.setenv('_PYI_ARCHIVE_FILE', r'C:\old\BP.exe')
    monkeypatch.setenv('_MEIPASS2', r'C:\old\_MEI123')
    environment = fresh_environment()
    assert '_PYI_APPLICATION_HOME_DIR' not in environment
    assert '_PYI_ARCHIVE_FILE' not in environment
    assert '_MEIPASS2' not in environment
    assert environment['PYINSTALLER_RESET_ENVIRONMENT'] == '1'


def test_update_helper_resets_pyinstaller_runtime_environment():
    script = (Path(__file__).resolve().parents[1] / 'beast_pick' / 'apply_update.ps1').read_text(encoding='utf-8')
    assert "-like '_PYI_*'" in script
    assert "-eq '_MEIPASS2'" in script
    assert "$env:PYINSTALLER_RESET_ENVIRONMENT = '1'" in script


@pytest.mark.parametrize('payload_name', ['new', 'bad'])
def test_windows_wait_replace_restart_cleanup_and_rollback(tmp_path, sample_exes, payload_name):
    root = tmp_path / "中文 目录 user's app"
    root.mkdir()
    target = root / 'BP.exe'
    shutil.copyfile(sample_exes['old'], target)
    old_bytes = target.read_bytes()
    settings = root / 'settings.json'
    settings.write_bytes(b'{"radius":8}')
    session = prepare_update(target)
    shutil.copyfile(sample_exes[payload_name], session.payload)
    new_bytes = session.payload.read_bytes()
    old = subprocess.Popen([str(target)], creationflags=subprocess.CREATE_NO_WINDOW)
    helper = None
    try:
        helper = start_install(session, file_hash(session.payload), parent_pid=old.pid, no_error_dialog=True)
        wait_until(lambda: session.status().get('state') in ('ready', 'failed'))
        assert session.status().get('state') == 'ready'
        assert old.poll() is None
        assert target.read_bytes() == old_bytes  # The running, mapped EXE must not be touched.
        (root / 'exit').write_text('exit')
        old.wait(timeout=5)
        code = helper.wait(timeout=15)
        assert settings.read_bytes() == b'{"radius":8}'
        if payload_name == 'new':
            assert code == 0 and target.read_bytes() == new_bytes
            assert (root / 'launched.txt').read_text() == 'new'
            assert not session.folder.exists()  # No old EXE or temporary installer remains.
        else:
            assert code == 1 and target.read_bytes() == old_bytes
            assert session.status().get('state') == 'failed'
            wait_until(lambda: (root / 'recovered.txt').exists())
            discard_update(session)
    finally:
        if old.poll() is None:
            old.terminate()
            old.wait(timeout=5)
        if helper is not None and helper.poll() is None:
            helper.terminate()
            helper.wait(timeout=5)


def test_tampered_payload_is_rejected_before_helper_starts(tmp_path):
    target = tmp_path / 'BP.exe'
    target.write_bytes(b'old-exe')
    session = prepare_update(target)
    session.payload.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='校验失败'):
        start_install(session, '0' * 64, no_error_dialog=True)
    assert target.read_bytes() == b'old-exe'
    discard_update(session)
