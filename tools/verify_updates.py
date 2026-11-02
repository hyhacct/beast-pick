"""Bounded check of the production updater against GitHub; never executes downloads."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from beast_pick.update_client import UpdateClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', type=Path, help='Optionally download and verify the latest EXE to this path')
    parser.add_argument('--report', type=Path, default=ROOT / 'artifacts/update-live-check.json')
    args = parser.parse_args()
    app = QApplication([])
    client = UpdateClient(app)
    result = {'ok': False}
    done = False

    def finish(error=None):
        nonlocal done
        if done:
            return
        done = True
        if error:
            result['error'] = error
        else:
            result['ok'] = True
        client.cancel()
        app.quit()

    def checked(release):
        result.update(tag=release.tag, page=release.page_url, size=release.size)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.download:
            args.download.parent.mkdir(parents=True, exist_ok=True)
            client.download(release, args.download)
        else:
            finish()

    def downloaded(filename):
        result.update(download=filename, verified_bytes=Path(filename).stat().st_size)
        finish()

    client.checked.connect(checked)
    client.failed.connect(finish)
    client.downloaded.connect(downloaded)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: finish('Update verification timed out'))
    timeout.start(180000 if args.download else 40000)
    client.check()
    app.exec()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
