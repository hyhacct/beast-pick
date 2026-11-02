"""Create the player ZIP, release notes and checksums from a verified EXE."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beast_pick import __version__
from release import check, release_notes


def main():
    check()
    report = json.loads((ROOT / 'artifacts/packaged-self-check.json').read_text(encoding='utf-8'))
    if not report['ok'] or report['version'] != __version__:
        raise SystemExit('先运行 build.ps1 并通过当前版本的打包检查。')
    output = ROOT / 'release'
    output.mkdir(exist_ok=True)
    executable = output / 'BP.exe'
    shutil.copy2(ROOT / 'dist/BP.exe', executable)
    archive = output / f'BP-v{__version__}-windows-x64.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
        bundle.write(executable, 'BP.exe')
        bundle.write(ROOT / 'LICENSE', 'LICENSE')
        bundle.write(ROOT / 'packaging/USAGE.zh-CN.txt', '使用说明.txt')
    checksums = ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in (executable, archive))
    (output / 'SHA256SUMS.txt').write_text(checksums, encoding='utf-8')
    (output / 'RELEASE_NOTES.md').write_text(release_notes(__version__, (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')), encoding='utf-8')
    print(checksums, end='')


if __name__ == '__main__':
    main()
