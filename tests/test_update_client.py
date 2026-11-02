"""Drive real Qt signals and atomic files with an in-memory network transport."""
import hashlib
import json
from pathlib import Path
import sys

import pytest
from PySide6.QtCore import QEventLoop, QObject, Signal, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from beast_pick.update_client import UpdateClient
from beast_pick.updates import API_URL, LATEST_URL, Release
from test_updates import metadata


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app


class Reply(QObject):
    readyRead = Signal()
    finished = Signal()
    downloadProgress = Signal("qlonglong", "qlonglong")

    def __init__(self, request, body=b"", status=200, final_url=None, parent=None):
        super().__init__(parent)
        self.body = body
        self.final_url = QUrl(final_url) if final_url else request.url()
        self.status = status
        self.done = False
        self.network_error = QNetworkReply.NetworkError.NoError if status == 200 else QNetworkReply.NetworkError.ContentAccessDenied
        QTimer.singleShot(0, self.deliver)

    def readAll(self):
        body, self.body = self.body, b""
        return body

    def url(self):
        return self.final_url

    def attribute(self, key):
        assert key == QNetworkRequest.Attribute.HttpStatusCodeAttribute
        return self.status

    def error(self):
        return self.network_error

    def errorString(self):
        return "Test HTTP error"

    def deliver(self):
        if self.done:
            return
        size = len(self.body)
        self.readyRead.emit()
        if self.done:
            return
        self.downloadProgress.emit(size, size)
        if not self.done:
            self.done = True
            self.finished.emit()

    def abort(self):
        if not self.done:
            self.network_error = QNetworkReply.NetworkError.OperationCanceledError
            self.done = True
            self.finished.emit()


class Manager(QNetworkAccessManager):
    def __init__(self, routes):
        super().__init__()
        self.routes = routes
        self.requests = []

    def get(self, request):
        url = request.url().toString()
        self.requests.append(url)
        return Reply(request, **self.routes.get(url, {"status": 404}), parent=self)


def drive(client, start):
    events = []
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    slots = []
    for name in ("checked", "failed", "downloaded", "cancelled"):
        slot = lambda *args, name=name: (events.append((name, args)), loop.quit())
        getattr(client, name).connect(slot)
        slots.append((name, slot))
    timer.start(3000)
    start()
    if not events:
        loop.exec()
    timer.stop()
    for name, slot in slots:
        getattr(client, name).disconnect(slot)
    assert events, "Update client did not finish"
    return events


def test_api_check_and_rate_limit_fallback(qt_app):
    client = UpdateClient(qt_app, manager=Manager({API_URL: {"body": json.dumps(metadata()).encode()}}))
    events = drive(client, client.check)
    assert events[0][0] == "checked"
    assert events[0][1][0].tag == "v0.3.0"
    assert not client.busy
    manager = Manager({API_URL: {"status": 403}, LATEST_URL: {"body": b"<html></html>",
        "final_url": Release("v0.3.0").page_url}})
    client = UpdateClient(qt_app, manager=manager)
    events = drive(client, client.check)
    assert events[0][0] == "checked"
    assert events[0][1][0].tag == "v0.3.0"
    assert manager.requests == [API_URL, LATEST_URL]


def test_failed_check_does_not_hang(qt_app):
    client = UpdateClient(qt_app, manager=Manager({}))
    assert drive(client, client.check)[0][0] == "failed"
    assert not client.busy


def download_client(body, *, size=None, digest=None, tag="v0.3.0"):
    release = Release(tag, size=size)
    digest = digest or hashlib.sha256(body).hexdigest()
    manager = Manager({release.asset_url("SHA256SUMS.txt"): {"body": (digest + "  " + release.executable_name + "\r\n").encode()},
                       release.asset_url(release.executable_name): {"body": body}})
    return UpdateClient(QApplication.instance(), manager=manager), release


@pytest.mark.parametrize("tag", ["v0.2.1", "v0.3.0"])
def test_verified_download_commits_only_after_checksum_passes(qt_app, tmp_path, tag):
    body = b"MZ-test-release-payload"
    client, release = download_client(body, size=len(body), tag=tag)
    destination = tmp_path / "new.exe"
    destination.write_bytes(b"previous-file")
    events = drive(client, lambda: client.download(release, destination))
    assert events == [("downloaded", (str(destination),))]
    assert destination.read_bytes() == body
    assert not client.busy and client.output is None


@pytest.mark.parametrize("reason", ["checksum", "truncated", "too_large", "http_error", "missing_checksum"])
def test_bad_download_preserves_existing_file_and_removes_partial(qt_app, tmp_path, reason):
    body = b"MZ-test-release-payload"
    size = len(body) + 1 if reason == "truncated" else len(body) - 1 if reason == "too_large" else len(body)
    client, release = download_client(body, size=size, digest="0" * 64 if reason == "checksum" else None)
    if reason == "http_error":
        client.manager.routes[release.asset_url(release.executable_name)]["status"] = 500
    if reason == "missing_checksum":
        client.manager.routes[release.asset_url("SHA256SUMS.txt")]["body"] = b"not a checksum"
    destination = tmp_path / "new.exe"
    destination.write_bytes(b"keep-existing")
    assert drive(client, lambda: client.download(release, destination))[0][0] == "failed"
    assert destination.read_bytes() == b"keep-existing"
    assert set(tmp_path.iterdir()) == {destination}
    assert not client.busy and client.output is None


def test_cancel_during_download_preserves_existing_file(qt_app, tmp_path):
    client, release = download_client(b"payload")
    client.progress.connect(lambda *_: client.cancel())
    destination = tmp_path / "new.exe"
    destination.write_bytes(b"keep-existing")
    assert drive(client, lambda: client.download(release, destination))[0][0] == "cancelled"
    assert destination.read_bytes() == b"keep-existing"
    assert set(tmp_path.iterdir()) == {destination}
    assert not client.busy and client.output is None


def test_download_rejects_running_executable_before_network_access(qt_app):
    client, release = download_client(b"payload")
    with pytest.raises(ValueError, match="正在运行"):
        client.download(release, Path(sys.executable))
    assert not client.manager.requests


@pytest.fixture
def window(qt_app, tmp_path, monkeypatch):
    from beast_pick import app as ui
    from shiboken6 import delete
    monkeypatch.setattr(ui, "BASE", tmp_path)
    ui.configure_application(qt_app)
    result = ui.Window(check_updates=False)
    yield result
    loop = QEventLoop()
    result.thread.finished.connect(loop.quit)
    result.close()
    if result.thread.isRunning():
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
    assert result.thread.wait(3000)
    delete(result)


def test_update_banner_waits_for_user_and_later_does_not_download(window, monkeypatch):
    window.on_update_checked(Release("v99.0.0", "更新内容"))
    assert "v99.0.0" in window.update_label.text()
    assert window.update_button.text() == "查看更新…"
    assert not window.update_client.busy
    seen = []
    def later(box):
        seen.append(box.detailedText())
        next(button for button in box.buttons() if button.text() == "稍后").click()
    monkeypatch.setattr(QMessageBox, "exec", later)
    window.update_clicked()
    assert seen == ["更新内容"]
    assert not window.update_client.busy


def test_only_download_choice_and_save_location_start_a_download(window, tmp_path, monkeypatch):
    window.on_update_checked(Release("v99.0.0"))
    destination = tmp_path / "update.exe"
    calls = []
    def choose_download(box):
        next(button for button in box.buttons() if button.text() == "下载新版…").click()
    monkeypatch.setattr(QMessageBox, "exec", choose_download)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(destination), ""))
    monkeypatch.setattr(window, "begin_update_download", lambda release, filename: calls.append((release.tag, filename)))
    window.update_clicked()
    assert calls == [("v99.0.0", str(destination))]


def test_closing_window_cancels_active_update(window):
    manager = Manager({API_URL: {"body": json.dumps(metadata()).encode()}})
    window.update_client.manager = manager
    window.check_updates()
    assert window.update_client.busy
    window.close()
    assert not window.update_client.busy
