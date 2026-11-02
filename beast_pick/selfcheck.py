"""Bounded check of the actual packaged runtime; never enables looting."""
import json
import traceback
from pathlib import Path


def run(output: str, check_game: bool = False, check_updates: bool = False) -> int:
    report = {"ok": False}
    try:
        from PySide6.QtCore import QEventLoop, QTimer, qVersion
        from PySide6.QtWidgets import QApplication
        from shiboken6 import delete
        import tempfile
        import frida
        from .backend import Client, MAX_RADIUS
        from . import __version__
        from . import app as ui
        from .categories import ITEM_TYPES
        from .catalog import load_catalog
        from .filter_dialog import FilterDialog
        from .updates import Release
        # Initialize the actual window, settings and worker with isolated settings.
        app = QApplication([])
        ui.configure_application(app)
        with tempfile.TemporaryDirectory(prefix='beast-pick-gui-check-') as work:
            ui.BASE = Path(work)
            saved = dict(radius=500, corpses=True, items=True, containers=False, open_containers=False, locked_containers=False,
                         item_types={key: key != 'weapons' for key in ITEM_TYPES},
                         item_rules={"items": {"Water_FT": False}, "subtypes": {"throwables:ItemType_Grenade": False}})
            (ui.BASE / 'settings.json').write_text(json.dumps(saved), encoding='utf-8')
            window = ui.Window(check_updates=False)
            assert app.applicationName() == 'beast-pick'
            assert window.windowTitle() == f'BP · 困兽自动搜刮  v{__version__}'
            assert not window.windowIcon().isNull()
            assert window.update_button.isEnabled() and not window.update_client.busy
            assert not window.update_timer.isActive()
            window.on_update_checked(Release('v99.0.0', '自检更新说明'))
            assert 'v99.0.0' in window.update_label.text()
            assert window.update_button.text() == '查看更新…'
            assert not window.update_client.busy  # Finding an update never starts a download.
            report.update(update_notice=True, update_download_requires_consent=True, custom_icon=True)
            if check_updates:
                loop = QEventLoop()
                timeout = QTimer()
                timeout.setSingleShot(True)
                timeout.timeout.connect(loop.quit)
                def update_checked(release):
                    report['github_update_check'] = {'tag': release.tag, 'page': release.page_url}
                    loop.quit()
                def update_failed(message):
                    report['github_update_error'] = message
                    loop.quit()
                window.update_client.checked.connect(update_checked)
                window.update_client.failed.connect(update_failed)
                window.update_client.check()
                timeout.start(40000)
                loop.exec()
                timeout.stop()
                window.update_client.cancel()
                window.update_client.checked.disconnect(update_checked)
                window.update_client.failed.disconnect(update_failed)
            assert window.radius.value() == MAX_RADIUS == 500
            assert not window.type_checks['weapons'].isChecked()
            assert not window.containers.isChecked()
            assert not window.open_containers.isChecked() and not window.locked_containers.isChecked()
            assert not window.locked_containers.isEnabled()
            assert all(box.isChecked() for key, box in window.type_checks.items() if key != 'weapons')
            assert (ui.BASE / 'settings.json').read_text(encoding='utf-8') == json.dumps(saved)
            assert not app.styleSheet()
            dialog = FilterDialog(window.item_rules, window.settings()['item_types'], window)
            assert dialog.tabs.tabText(0) == '按子类'
            model, proxy = dialog.pages[1]
            proxy.query = 'Water_FT'.casefold()
            proxy.invalidateFilter()
            assert any(model.rows[proxy.mapToSource(proxy.index(row, 0)).row()][0] == 'Water_FT' for row in range(proxy.rowCount()))
            row = next(i for i, (key, _) in enumerate(model.rows) if key == 'Water_FT')
            assert model.data(model.index(row, 0)).startswith('跳过')
            assert model.setData(model.index(row, 0), 1)
            assert dialog.rules['items']['Water_FT'] is True
            assert window.item_rules['items']['Water_FT'] is False  # Cancel cannot leak edits.
            delete(dialog)
            report.update(catalog_items=len(load_catalog()['items']), detailed_rules=window.item_rules)
            report['catalog_subtypes'] = len(load_catalog()['subtypes'])
            report.update(style=app.style().objectName(), item_types=window.settings()['item_types'], containers=window.settings()['containers'])
            window.thread.finished.connect(app.quit)
            QTimer.singleShot(50, window.close)
            assert app.exec() == 0
            assert window.thread.wait(5000)
            persisted = json.loads((ui.BASE / 'settings.json').read_text(encoding='utf-8'))
            assert persisted == saved
            # Dispose Qt while Python wrappers are still live, before a later
            # game connection extends the process lifetime past GUI teardown.
            delete(window)
        delete(app)
        if check_updates:
            assert 'github_update_check' in report, report
        report.update(version=__version__, qt=qVersion(), frida=frida.__version__, max_radius=MAX_RADIUS)
        if check_game:
            with Client() as client:
                report['game'] = client.connect()
                report['state'] = client.heartbeat()
                assert not report['state']['enabled']
        report['ok'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
