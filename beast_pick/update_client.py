"""Asynchronous, cancellable update checks and verified downloads; never runs an EXE."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QIODevice, QSaveFile, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .updates import API_URL, LATEST_URL, MAX_DOWNLOAD, Release, executable_checksum, release_from_api, release_from_redirect


class UpdateClient(QObject):
    checked = Signal(object)
    failed = Signal(str)
    progress = Signal("qlonglong", "qlonglong")
    downloaded = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None, *, manager=None):
        super().__init__(parent)
        self.manager = manager if manager is not None else QNetworkAccessManager(self)
        self.reply = None
        self.phase = "idle"
        self.release = None
        self.output = None
        self.destination = None
        self.buffer = bytearray()
        self.received = 0
        self.expected_hash = None

    @property
    def busy(self):
        return self.reply is not None

    def _get(self, url, phase):
        self.phase = phase
        self.buffer.clear()
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", f"beast-pick/{__version__}".encode("ascii"))
        request.setRawHeader(b"Accept", b"application/vnd.github+json" if phase == "api" else b"*/*")
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setTransferTimeout(30000 if phase == "download" else 15000)
        reply = self.manager.get(request)
        self.reply = reply
        reply.readyRead.connect(lambda: self._read(reply))
        reply.finished.connect(lambda: self._finished(reply))
        if phase == "download":
            reply.downloadProgress.connect(lambda received, total: self.progress.emit(received, total)
                                           if reply is self.reply else None)

    def check(self):
        if self.busy:
            return
        self._get(API_URL, "api")

    def download(self, release: Release, destination: Path):
        if self.busy:
            raise RuntimeError("更新任务正在进行，请稍后重试")
        destination = Path(destination).resolve()
        if destination.suffix.lower() != ".exe":
            raise ValueError("请将新版程序保存为 EXE 文件")
        if destination == Path(sys.executable).resolve():
            raise ValueError("不能覆盖正在运行的程序，请选择其他文件名或文件夹")
        self.release = release
        self.destination = destination
        self.expected_hash = None
        self.received = 0
        self._get(release.asset_url("SHA256SUMS.txt"), "checksum")

    def _read(self, reply):
        if reply is not self.reply:
            return
        try:
            chunk = bytes(reply.readAll())
            if self.phase == "download":
                self.received += len(chunk)
                limit = self.release.size or MAX_DOWNLOAD
                if self.received > limit:
                    raise ValueError("下载文件超出预期大小")
                if self.output.write(chunk) != len(chunk):
                    raise OSError("无法写入下载文件：" + self.output.errorString())
                self.hasher.update(chunk)
            else:
                self.buffer.extend(chunk)
                limit = 65536 if self.phase == "checksum" else 2 * 1024 * 1024
                if len(self.buffer) > limit:
                    raise ValueError("更新信息过大，已停止读取")
        except Exception as exc:
            self._fail(str(exc))

    def _finished(self, reply):
        if reply is not self.reply:
            reply.deleteLater()
            return
        self._read(reply)
        if reply is not self.reply:
            reply.deleteLater()
            return
        self.reply = None
        phase = self.phase
        try:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NetworkError.NoError or status != 200:
                if phase == "api":
                    self._get(LATEST_URL, "page")
                    return
                raise RuntimeError(f"无法连接 GitHub 或下载未完成（HTTP {status or '—'}）：{reply.errorString()}")
            if phase in ("api", "page"):
                try:
                    release = (release_from_api(json.loads(self.buffer)) if phase == "api"
                               else release_from_redirect(reply.url().toString()))
                except (ValueError, TypeError, KeyError):
                    if phase == "api":
                        self._get(LATEST_URL, "page")
                        return
                    raise
                self.phase = "idle"
                self.checked.emit(release)
            elif phase == "checksum":
                self.expected_hash = executable_checksum(self.buffer.decode("utf-8-sig").replace("\r\n", "\n"),
                                                         self.release.executable_name)
                self.output = QSaveFile(str(self.destination))
                self.output.setDirectWriteFallback(False)
                if not self.output.open(QIODevice.OpenModeFlag.WriteOnly):
                    raise OSError("无法保存新版程序：" + self.output.errorString())
                self.hasher = hashlib.sha256()
                self._get(self.release.asset_url(self.release.executable_name), "download")
            elif phase == "download":
                if self.received == 0 or (self.release.size is not None and self.received != self.release.size):
                    raise ValueError("下载文件不完整，请重试")
                if self.hasher.hexdigest() != self.expected_hash:
                    raise ValueError("SHA-256 校验不一致，已丢弃下载文件，请重试")
                if not self.output.commit():
                    raise OSError("无法保存下载文件：" + self.output.errorString())
                self.output = None
                self.phase = "idle"
                self.downloaded.emit(str(self.destination))
        except Exception as exc:
            self._fail(str(exc))
        finally:
            reply.deleteLater()

    def _discard(self):
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()
        if self.output is not None:
            self.output.cancelWriting()
            self.output = None
        self.buffer.clear()
        self.phase = "idle"

    def _fail(self, message):
        self._discard()
        self.failed.emit(message)

    def cancel(self):
        if self.busy:
            self._discard()
            self.cancelled.emit()
