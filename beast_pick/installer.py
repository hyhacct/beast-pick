"""Stage beside the running EXE; a hidden helper replaces it after a clean exit."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


@dataclass(frozen=True)
class InstallSession:
    target: Path
    folder: Path

    @property
    def payload(self):
        return self.folder / 'new.exe'

    @property
    def status_path(self):
        return self.folder / 'status.json'

    def status(self):
        try:
            return json.loads(self.status_path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            return {}


def prepare_update(target: Path) -> InstallSession:
    target = Path(target).resolve(strict=True)
    if target.suffix.lower() != '.exe' or not target.is_file():
        raise ValueError('无法确定当前程序的位置')
    try:
        folder = Path(tempfile.mkdtemp(prefix='.bp-update-', dir=target.parent))
    except OSError as exc:
        raise OSError('当前程序目录无法写入，请将 BP 放到可写目录后重试。') from exc
    return InstallSession(target, folder)


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def start_install(session: InstallSession, expected_hash: str, *, parent_pid=None, no_error_dialog=False):
    if file_hash(session.payload) != expected_hash:
        raise ValueError('更新文件校验失败，请重试')
    plan = dict(target=str(session.target), payload_sha256=expected_hash,
                current_sha256=file_hash(session.target), parent_pid=parent_pid or os.getpid())
    (session.folder / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
    script = session.folder / 'apply.ps1'
    script.write_text((Path(__file__).parent / 'apply_update.ps1').read_text(encoding='utf-8'), encoding='utf-8-sig')
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    args = [str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)]
    if no_error_dialog:
        args.append('-NoErrorDialog')
    return subprocess.Popen(args, cwd=session.target.parent,
                            creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)


def discard_update(session: InstallSession | None):
    if session is None:
        return
    # Only remove our named files inside this session, never traverse a user directory.
    folder = session.folder.resolve()
    if folder.parent != session.target.resolve().parent or not folder.name.startswith('.bp-update-'):
        raise ValueError('无效的更新临时目录')
    for name in ('new.exe', 'plan.json', 'apply.ps1', 'status.json', 'started', 'failed.exe'):
        (folder / name).unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass  # Keep a rollback copy if recovery needs it.


def acknowledge_update(arguments, executable=None):
    if '--complete-update' not in arguments:
        return
    index = arguments.index('--complete-update')
    if index + 1 >= len(arguments):
        return
    target = Path(executable or sys.executable).resolve()
    folder = Path(arguments[index + 1]).resolve()
    if folder.parent != target.parent or not folder.name.startswith('.bp-update-'):
        return
    try:
        plan = json.loads((folder / 'plan.json').read_text(encoding='utf-8'))
        if Path(plan['target']).resolve() == target and file_hash(target) == plan['payload_sha256']:
            (folder / 'started').write_text('ok', encoding='ascii')
    except (OSError, ValueError, KeyError):
        pass
