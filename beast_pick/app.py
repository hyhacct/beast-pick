from __future__ import annotations

import ctypes
import json
import logging
import sys
import tempfile
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, QLockFile, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton, QStyle, QStyleFactory,
    QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QProgressDialog, QDialog,
)

from .backend import Client, MAX_RADIUS
from . import __version__
from . import diy
from .categories import ITEM_TYPES, checked_item_types
from .catalog import checked_rules, has_allowed
from .diy_page import DiyPage
from .filter_dialog import FilterDialog
from .weapon_exclusions_dialog import WeaponExclusionsDialog
from .weapon_catalog import checked_exclusions
from .update_client import UpdateClient
from .update_dialog import UpdateDialog
from .installer import acknowledge_update, prepare_update, start_install, discard_update

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
STATUS = {
    "waiting": "等待游戏更新", "disabled": "已停止", "running": "正在自动搜刮",
    "background": "等待切回游戏", "waiting_level": "等待场景就绪", "paused": "游戏已暂停或正在加载",
    "waiting_player": "等待本地角色就绪",
    "lease_expired": "连接超时，已自动停止", "error": "出现错误，已停止",
}


class Worker(QObject):
    event = Signal(dict)
    completed = Signal(str, dict)
    failed = Signal(str)
    finished = Signal()

    @Slot()
    def start(self):
        self.client = Client(self.event.emit)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    @Slot(str, dict)
    def command(self, name, payload):
        try:
            if name == "connect":
                result = self.client.connect(payload.get("game", "auto"))
            elif name == "configure":
                result = self.client.configure(**payload)
            elif name == "stop":
                self.client.stop(); result = {}
            elif name == "diy_apply":
                result = self.client.diy_apply(payload.get("plan") or {})
            elif name == "diy_generate":
                result = self.client.diy_generate(payload.get("plan") or {})
            elif name == "disconnect":
                self.client.close(); result = {}
            elif name == "quit":
                self.timer.stop()
                self.client.close()
                self.finished.emit()
                return
            else:
                raise ValueError(name)
            self.completed.emit(name, result or {})
        except Exception as exc:
            logging.exception("Command failed: %s", name)
            self.failed.emit(str(exc))
            if name == "quit":
                self.finished.emit()

    @Slot()
    def poll(self):
        if not self.client.connected:
            return
        try:
            self.event.emit({"event": "stats", **self.client.heartbeat()})
        except Exception as exc:
            self.event.emit({"event": "detached", "reason": str(exc)})
            self.client.close()


class Window(QMainWindow):
    command = Signal(str, dict)

    def __init__(self, *, check_updates=True, update_prompts=True):
        super().__init__()
        self.connected = False
        self.game_key = None
        self.enabled = False
        self.inflight = False
        self.quitting = False
        self.last_status = None
        self.loading_settings = True
        self.config_dirty = False
        self.available_release = None
        self.update_manual = False
        self.update_progress = None
        self.update_prompts = update_prompts
        self.update_target = Path(sys.executable) if getattr(sys, 'frozen', False) else None
        self.update_session = None
        self.install_process = None
        self.install_timer = QTimer(self)
        self.install_timer.setInterval(100)
        self.install_timer.timeout.connect(self.poll_update_install)
        self.item_rules = checked_rules()
        self.excluded_by_game = {"dl2": [], "beast": []}
        self.diy_ready = False
        self.keys = {0x75: False, 0x76: False, 0x77: False}  # F6 / F7 / F8
        self.setWindowTitle(f"BP · 消光 2 / 困兽自动搜刮  v{__version__}")
        self.setWindowIcon(QApplication.windowIcon())
        self.setMinimumSize(900, 640)
        self.resize(1040, 880)
        self.settings_timer = QTimer(self)
        self.settings_timer.setSingleShot(True)
        self.settings_timer.setInterval(180)
        self.settings_timer.timeout.connect(self.flush_settings)
        self.diy_pending = False
        self.diy_timer = QTimer(self)
        self.diy_timer.setSingleShot(True)
        self.diy_timer.setInterval(4000)
        self.diy_timer.timeout.connect(self.on_diy_timeout)
        self.build_ui()
        self.update_client = UpdateClient(self)
        self.update_client.checked.connect(self.on_update_checked)
        self.update_client.failed.connect(self.on_update_failed)
        self.update_client.progress.connect(self.on_update_progress)
        self.update_client.downloaded.connect(self.on_update_downloaded)
        self.update_client.cancelled.connect(self.on_update_cancelled)
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.check_updates)
        if check_updates:
            self.update_timer.start(100)
        self.load_settings()
        self.loading_settings = False
        self.thread = QThread(self)
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.command.connect(self.worker.command)
        self.worker.event.connect(self.on_event)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.finish_close)
        self.thread.start()
        self.hotkeys = QTimer(self)
        self.hotkeys.setInterval(70)
        self.hotkeys.timeout.connect(self.check_keys)
        self.hotkeys.start()
        self.add_log("进入单人或联机存档后连接游戏，按 F6 开始，F8 停止。")

    def build_ui(self):
        toolbar = QToolBar("操作", self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(toolbar)
        self.connection = QPushButton("连接游戏")
        self.connection.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon))
        self.connection.clicked.connect(self.connect_game)
        self.toggle_button = QPushButton("开始 (F6)")
        self.toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.toggle_button.setEnabled(False)
        self.toggle_button.clicked.connect(self.toggle)
        self.stop_button = QPushButton("停止 (F8)")
        self.stop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        for button in (self.connection, self.toggle_button, self.stop_button):
            button.setMinimumHeight(30)
            toolbar.addWidget(button)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("游戏："))
        self.game_choice = QComboBox()
        for text, value in [("自动检测", "auto"), ("消逝的光芒 2", "dl2"), ("消逝的光芒：困兽", "beast")]:
            self.game_choice.addItem(text, value)
        self.game_choice.currentIndexChanged.connect(self.game_choice_changed)
        toolbar.addWidget(self.game_choice)
        self.badge = QLabel("  未连接游戏  ")
        toolbar.addWidget(self.badge)

        file_menu = self.menuBar().addMenu("文件(&F)")
        self.connect_action = file_menu.addAction("连接 / 断开游戏")
        self.connect_action.triggered.connect(self.connection.click)
        file_menu.addSeparator()
        file_menu.addAction("退出(&X)", self.close)
        operations = self.menuBar().addMenu("操作(&O)")
        self.toggle_action = operations.addAction("开始 / 暂停\tF6", self.toggle)
        self.stop_action = operations.addAction("停止\tF8", self.stop)
        view_menu = self.menuBar().addMenu("视图(&V)")
        view_menu.addAction("自动拾取", lambda: self.tabs.setCurrentIndex(0))
        help_menu = self.menuBar().addMenu("帮助(&H)")
        help_menu.addAction("使用说明", self.show_help)
        self.update_action = help_menu.addAction("检查更新…", lambda: self.check_updates(True))

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(8)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(8, 10, 8, 6)
        page_layout.setSpacing(10)
        self.tabs.addTab(page, "自动拾取")

        update_row = QHBoxLayout()
        self.update_label = QLabel(f"当前版本 v{__version__}")
        self.update_label.setWordWrap(True)
        update_row.addWidget(self.update_label, 1)
        self.update_button = QPushButton("检查更新")
        self.update_button.clicked.connect(self.update_clicked)
        update_row.addWidget(self.update_button)
        page_layout.addLayout(update_row)
        options_box = QGroupBox("搜刮设置")
        options = QVBoxLayout(options_box)
        row = QHBoxLayout()
        self.corpses = QCheckBox("自动搜刮尸体"); self.corpses.setChecked(True)
        self.containers = QCheckBox("自动搜刮普通容器"); self.containers.setChecked(True)
        self.containers.setToolTip("按筛选领取普通容器战利品；下方可单独开启箱柜和锁箱功能。")
        self.items = QCheckBox("自动拾取散落物品"); self.items.setChecked(True)
        row.addWidget(self.corpses); row.addWidget(self.containers); row.addWidget(self.items); row.addStretch()
        options.addLayout(row)
        open_row = QHBoxLayout()
        self.open_containers = QCheckBox("自动开启箱柜")
        self.locked_containers = QCheckBox("强制开启锁箱柜（试验）")
        self.open_containers.setToolTip("直接完成已识别箱柜的长按 / 连按 F 开启流程。每秒最多开启一个；门、关联机关和未知类型跳过。")
        self.locked_containers.setToolTip("对已确认的普通锁箱柜跳过撬锁小游戏。未知锁型、特殊禁搜刮容器跳过。尚未完成长期稳定性验证。")
        open_row.addWidget(self.open_containers)
        open_row.addWidget(self.locked_containers)
        open_row.addStretch()
        options.addLayout(open_row)
        self.open_containers.toggled.connect(self.update_open_controls)
        self.containers.toggled.connect(self.update_open_controls)
        self.locked_containers.setEnabled(False)
        radius_row = QHBoxLayout()
        radius_row.addWidget(QLabel("拾取半径："))
        self.radius = QDoubleSpinBox(); self.radius.setRange(1, MAX_RADIUS); self.radius.setSingleStep(1)
        self.radius.setValue(8); self.radius.setSuffix(" 米"); self.radius.setDecimals(0)
        self.radius.setMinimumWidth(110)
        self.radius.setKeyboardTracking(False)
        radius_row.addWidget(self.radius)
        radius_row.addWidget(QLabel("（1–500 米，可直接输入）"))
        radius_row.addStretch()
        options.addLayout(radius_row)
        note = QLabel("仅搜刮场景中已加载的目标；暂停、加载或切出游戏时等候。")
        note.setWordWrap(True)
        options.addWidget(note)
        page_layout.addWidget(options_box)

        melee_box = QGroupBox("近战玩法")
        melee_layout = QHBoxLayout(melee_box)
        self.rapid_melee = QCheckBox("千刀：按住左键连续快砍 (F7)")
        self.rapid_melee.setToolTip("仅手持近战武器时生效；松开停止，切出游戏或暂停时停止。F8 停止全部功能。")
        self.rapid_melee.toggled.connect(self.settings_changed)
        melee_layout.addWidget(self.rapid_melee)
        self.melee_speed = QDoubleSpinBox()
        self.melee_speed.setRange(2, 20); self.melee_speed.setDecimals(0)
        self.melee_speed.setValue(12); self.melee_speed.setSuffix(" 倍")
        self.melee_speed.setKeyboardTracking(False)
        self.melee_speed.valueChanged.connect(self.settings_changed)
        melee_layout.addWidget(self.melee_speed)
        self.melee_status = QLabel("未开启")
        melee_layout.addWidget(self.melee_status)
        page_layout.addWidget(melee_box)
        melee_box.hide()  # User requested removal from the visible interface.

        filter_box = QGroupBox("允许拾取的物品类型")
        filter_layout = QVBoxLayout(filter_box)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)
        self.type_checks = {}
        for i, (key, (label, _)) in enumerate(ITEM_TYPES.items()):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.toggled.connect(self.settings_changed)
            self.type_checks[key] = checkbox
            grid.addWidget(checkbox, i // 3, i % 3)
        filter_layout.addLayout(grid)
        filter_row = QHBoxLayout()
        for text, callback in [("全选", lambda: self.select_types(True)),
                               ("全不选", lambda: self.select_types(False)),
                               ("排除武器", lambda: self.type_checks["weapons"].setChecked(False))]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            filter_row.addWidget(button)
        filter_row.addStretch()
        self.detail_button = QPushButton("详细筛选…")
        self.detail_button.clicked.connect(self.edit_filters)
        filter_row.addWidget(self.detail_button)
        filter_layout.addLayout(filter_row)
        hint = QLabel("可在详细筛选中选择子类和具体物品；优先级：具体物品 > 子类 > 大类。")
        hint.setWordWrap(True)
        hint.setToolTip("存在排除项时，也会跳过内容不透明的物资包，防止间接领到被排除的物品。")
        filter_layout.addWidget(hint)
        page_layout.addWidget(filter_box)
        filter_box.hide()
        self.type_checks["weapons"].setText("拾取武器（取消勾选则排除）")
        weapon_row = QHBoxLayout()
        weapon_row.addWidget(self.type_checks["weapons"])
        self.weapon_exclusions_button = QPushButton("排除指定武器 / 投掷物…")
        self.weapon_exclusions_button.clicked.connect(self.edit_weapon_exclusions)
        weapon_row.addWidget(self.weapon_exclusions_button)
        weapon_row.addStretch()
        options.addLayout(weapon_row)

        stats_box = QGroupBox("本次连接统计")
        numbers = QHBoxLayout(stats_box)
        self.body_count = QLabel("0"); self.item_count = QLabel("0"); self.near_count = QLabel("—")
        self.container_count = QLabel("0")
        self.container_count.setToolTip("已领取物品的普通容器数；同一个容器只计一次。")
        self.filtered_count = QLabel("0")
        for label, value in [("尸体：", self.body_count), ("容器：", self.container_count), ("散落物品：", self.item_count),
                             ("附近目标：", self.near_count), ("已排除：", self.filtered_count)]:
            numbers.addWidget(QLabel(label)); numbers.addWidget(value); numbers.addStretch()
        page_layout.addWidget(stats_box)

        log_title = QHBoxLayout()
        log_title.addWidget(QLabel("运行记录"))
        log_title.addStretch()
        clear_button = QPushButton("清空记录")
        clear_button.clicked.connect(lambda: self.log.clear())
        log_title.addWidget(clear_button)
        page_layout.addLayout(log_title)
        self.log = QTreeWidget()
        self.log.setHeaderLabels(["时间", "事件", "内容", "距离"])
        self.log.setRootIsDecorated(False)
        self.log.setAlternatingRowColors(True)
        self.log.setUniformRowHeights(True)
        self.log.setMinimumHeight(120)
        self.log.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        header = self.log.header()
        for col in (0, 1, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        page_layout.addWidget(self.log, 1)

        # DIY is temporarily hidden; retain its implementation for later work.
        self.diy_page = None

        self.status = QLabel("等待连接游戏")
        self.statusBar().addWidget(self.status, 1)
        self.scan_status = QLabel("F6 开关  |  F8 停止")
        self.statusBar().addPermanentWidget(self.scan_status)
        for widget in [self.corpses, self.containers, self.items, self.open_containers, self.locked_containers]:
            widget.toggled.connect(self.settings_changed)
        self.radius.valueChanged.connect(self.settings_changed)
        self.refresh_controls()

    # ------------------------------------------------------------ DIY 武器页
    def build_diy_page(self):
        """The catalogue is generated offline; a missing file must not block page one."""
        try:
            page = DiyPage()
        except Exception as exc:
            logging.exception("DIY page failed to load")
            self.diy_ready = False
            page = QWidget()
            box = QVBoxLayout(page)
            message = QLabel(f"DIY 武器目录加载失败：{exc}\n\n"
                             "请重新运行 tools/build_weapon_catalog.py 生成 beast_pick/data/weapons.json。")
            message.setWordWrap(True)
            box.addWidget(message)
            box.addStretch()
            return page
        self.diy_ready = True
        page.notice.connect(self.on_diy_notice)
        page.blocked.connect(self.on_diy_blocked)
        page.apply_requested.connect(self.diy_apply)
        page.generate_requested.connect(self.diy_generate)
        return page

    def on_diy_blocked(self, text):
        """A refused click must produce a visible answer, not a dead button."""
        self.on_diy_notice(text)
        if self.diy_ready:
            self.diy_page.show_result(text, ok=False)
        QMessageBox.information(self, "DIY 武器", text)

    def on_tab_changed(self, index):
        if index == 1 and self.diy_ready and not self.connected:
            self.diy_page.status.setText("未连接游戏：可浏览武器、配置并复制方案。")

    def on_diy_notice(self, text):
        self.add_log(text, action="DIY 武器")
        if self.diy_ready:
            self.diy_page.status.setText(text)

    def diy_apply(self, plan):
        if self.quitting:
            return
        if self.inflight:
            self.on_diy_notice("正在执行上一个操作，请稍候再写入。")
            return
        if self.diy_pending:
            self.on_diy_notice("上一个 DIY 请求还在等待游戏响应，请稍候。")
            return
        if not self.connected:
            self.on_diy_notice("请先连接游戏，再写入武器属性。")
            return
        self.diy_pending = True
        self.diy_page.status.setText("正在写入手持武器…")
        self.diy_timer.start()
        self.command.emit("diy_apply", {"plan": plan})
        self.refresh_controls()

    def diy_generate(self, plan):
        if self.quitting:
            return
        if self.inflight:
            self.on_diy_notice("正在执行上一个操作，请稍候再生成。")
            return
        if self.diy_pending:
            self.on_diy_notice("上一个 DIY 请求还在等待游戏响应，请稍候。")
            return
        if not self.connected:
            self.on_diy_notice("请先连接游戏，再生成武器到背包。")
            return
        self.diy_pending = True
        self.diy_page.status.setText("正在生成武器到背包…")
        self.diy_timer.start()
        self.command.emit("diy_generate", {"plan": plan})
        self.refresh_controls()

    def finish_diy(self, event):
        self.diy_timer.stop()
        self.diy_pending = False
        if not event.get("ok"):
            text = event.get("error") or event.get("message") or "DIY 操作未完成"
            self.on_diy_notice(text)
            if self.diy_ready:
                self.diy_page.show_result(text, ok=False)
        else:
            self.on_diy_applied(event)
        self.refresh_controls()

    def on_diy_timeout(self):
        if not self.diy_pending:
            return
        self.diy_pending = False
        text = ("游戏没有响应：模拟线程当前不在运行。切回游戏画面、退出暂停菜单后再点一次。")
        self.on_diy_notice(text)
        if self.diy_ready:
            self.diy_page.show_result(text, ok=False)
        self.refresh_controls()

    def on_diy_applied(self, result):
        result = result or {}
        generated = bool(result.get("generated"))
        applied = generated or bool(result.get("applied"))
        message = result.get("message") or (
            "手持武器属性已更新。" if applied else "没有手持武器属性被更新。"
        )
        self.on_diy_notice(message)
        if self.diy_ready:
            self.diy_page.show_result(message, ok=applied)
        verify = result.get("verify") or {}
        if verify:
            text = "、".join(f"{diy.STAT_LABELS.get(key, (key, ''))[0]}={value:g}" for key, value in verify.items())
            self.add_log(("生成后回读：" if generated else "写入后回读：") + text,
                         action="生成 DIY 武器" if generated else "DIY 武器")

    def check_updates(self, manual=False):
        if self.quitting or self.update_client.busy:
            return
        self.update_timer.stop()
        self.update_manual = manual
        self.update_label.setText("正在检查 GitHub 新版本…")
        self.set_update_busy(True)
        self.update_client.check()

    def set_update_busy(self, busy):
        self.update_button.setEnabled(not busy)
        self.update_action.setEnabled(not busy)

    def show_update_notice(self):
        if self.available_release:
            self.update_label.setText(f"发现新版本 {self.available_release.tag}（当前 v{__version__}）")
            self.update_button.setText("立即更新")
        else:
            self.update_label.setText(f"当前版本 v{__version__}，未发现更新版本")
            self.update_button.setText("检查更新")

    def on_update_checked(self, release):
        if self.quitting:
            return
        self.available_release = release if release.newer_than(__version__) else None
        self.set_update_busy(False)
        self.show_update_notice()
        if self.available_release:
            self.add_log(f"发现新版本 {release.tag}。")
            if self.update_prompts:
                self.update_clicked()
        elif self.update_manual:
            QMessageBox.information(self, "检查更新", f"当前版本 v{__version__}，未发现更新的正式版本。")

    def update_clicked(self):
        if self.quitting or self.update_client.busy:
            return
        release = self.available_release
        if release is None:
            self.check_updates(True)
            return
        if UpdateDialog(release, self).exec() == QDialog.DialogCode.Accepted:
            self.begin_update_download(release)

    def begin_update_download(self, release):
        self.update_manual = True
        try:
            if self.update_target is None:
                raise RuntimeError('请使用打包版 BP.exe 进行自动更新。')
            self.update_session = prepare_update(self.update_target)
        except Exception as exc:
            self.on_update_failed(str(exc))
            return
        self.set_update_busy(True)
        self.update_label.setText(f"正在下载 {release.tag}…")
        self.update_progress = QProgressDialog("正在获取更新文件…", "取消下载", 0, 0, self)
        self.update_progress.setWindowTitle("下载更新")
        self.update_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.update_progress.setAutoClose(False)
        self.update_progress.setAutoReset(False)
        self.update_progress.canceled.connect(self.update_client.cancel)
        self.update_progress.show()
        try:
            self.update_client.download(release, self.update_session.payload)
        except Exception as exc:
            self.on_update_failed(str(exc))

    def on_update_progress(self, received, total):
        if self.update_progress is None:
            return
        mib = received / (1024 * 1024)
        if total > 0:
            self.update_progress.setRange(0, 1000)
            self.update_progress.setValue(min(1000, received * 1000 // total))
            self.update_progress.setLabelText(f"已下载 {mib:.1f} / {total / (1024 * 1024):.1f} MB，完成后校验文件…")
        else:
            self.update_progress.setLabelText(f"已下载 {mib:.1f} MB，完成后校验文件…")

    def close_update_progress(self):
        if self.update_progress is not None:
            dialog, self.update_progress = self.update_progress, None
            dialog.reset()
            dialog.close()
            dialog.deleteLater()

    def on_update_downloaded(self, filename):
        if self.quitting:
            return
        try:
            if self.update_session is None or Path(filename).resolve() != self.update_session.payload:
                raise RuntimeError('更新文件位置不匹配')
            self.update_progress.setCancelButton(None)
            self.update_progress.setRange(0, 0)
            self.update_progress.setLabelText('正在安装并重启…')
            self.install_process = start_install(self.update_session, self.update_client.expected_hash)
            self.install_started = time.monotonic()
            self.install_timer.start()
        except Exception as exc:
            self.on_update_failed(str(exc))

    def poll_update_install(self):
        status = self.update_session.status()
        if status.get('state') == 'ready':
            self.install_timer.stop()
            self.close()  # Stop looting and detach cleanly before the helper replaces this EXE.
        elif status.get('state') == 'failed' or self.install_process.poll() is not None or time.monotonic() - self.install_started > 15:
            self.install_timer.stop()
            if self.install_process.poll() is None:
                self.install_process.terminate()
                self.install_process.wait(timeout=3)
            self.install_process = None
            self.on_update_failed(status.get('message') or '无法启动更新，请重试。')

    def discard_staged_update(self):
        if self.update_session is not None and self.install_process is None:
            try:
                discard_update(self.update_session)
            except OSError:
                logging.exception('Could not remove update staging files')
            self.update_session = None

    def on_update_failed(self, message):
        self.discard_staged_update()
        self.close_update_progress()
        self.set_update_busy(False)
        if self.quitting:
            return
        self.show_update_notice()
        if self.available_release is None:
            self.update_label.setText("更新检查失败，可点击‘检查更新’重试")
        self.add_log("更新未完成：" + message)
        if self.update_manual:
            QMessageBox.warning(self, "更新未完成", message)

    def on_update_cancelled(self):
        self.discard_staged_update()
        self.close_update_progress()
        self.set_update_busy(False)
        if not self.quitting:
            self.show_update_notice()
            self.add_log("已取消更新下载。")

    def show_help(self):
        QMessageBox.information(self, "使用说明", "启动游戏并进入存档，点击连接游戏。\n"
            "勾选要搜刮的尸体、普通容器或散落物品，并设置半径。\n"
            "取消勾选‘拾取武器’可排除武器；切回游戏后按 F6 开始或暂停，F8 停止。\n\n"
            "仅处理已加载目标；可能跨墙或楼层。自动开箱与锁箱选项需分别勾选。")

    def game_choice_changed(self, *args):
        self.update_weapon_exclusion_count()
        self.settings_changed()

    def update_weapon_exclusion_count(self):
        if not hasattr(self, 'weapon_exclusions_button'):
            return
        game = self.game_key or self.game_choice.currentData()
        count = len(self.excluded_by_game.get(game, []))
        label = '排除指定武器 / 投掷物…'
        self.weapon_exclusions_button.setText(f'{label}（{count} 个版本）' if count else label)

    def edit_weapon_exclusions(self):
        game = self.game_key or self.game_choice.currentData()
        if game not in ('dl2', 'beast'):
            QMessageBox.information(self, '选择游戏', '请先在工具栏选择游戏，或连接后再设置排除项。')
            return
        dialog = WeaponExclusionsDialog(game, self.excluded_by_game[game], self)
        if dialog.exec():
            self.excluded_by_game[game] = checked_exclusions(game, sorted(dialog.exclusions))
            self.update_weapon_exclusion_count()
            self.settings_changed()
        dialog.deleteLater()

    def select_types(self, selected):
        for checkbox in self.type_checks.values():
            checkbox.setChecked(selected)

    def update_open_controls(self, *args):
        self.open_containers.setEnabled(self.containers.isChecked())
        self.locked_containers.setEnabled(self.containers.isChecked() and self.open_containers.isChecked())

    def edit_filters(self):
        dialog = FilterDialog(self.item_rules, {key: box.isChecked() for key, box in self.type_checks.items()}, self)
        # Global F6/F8 remain handled by the parent timer while this dialog is open.
        if dialog.exec():
            self.item_rules = checked_rules(dialog.rules)
            self.update_rule_count()
            self.settings_changed()
        dialog.deleteLater()

    def update_rule_count(self):
        count = sum(len(v) for v in self.item_rules.values())
        self.detail_button.setText(f"详细筛选…（{count} 条）" if count else "详细筛选…")

    def add_log(self, text, action="状态", distance=None):
        item = QTreeWidgetItem([f"{datetime.now():%H:%M:%S}", action, text,
                               "" if distance is None else f"{distance:.1f} 米"])
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setToolTip(2, text)
        self.log.addTopLevelItem(item)
        while self.log.topLevelItemCount() > 250:
            self.log.takeTopLevelItem(0)
        self.log.scrollToBottom()
        logging.info("%s | %s%s", action, text, "" if distance is None else f" | {distance:.1f} 米")

    def settings(self, enabled=None):
        return dict(radius=self.radius.value(), corpses=self.corpses.isChecked(),
                    items=self.items.isChecked(), containers=self.containers.isChecked(), enabled=self.enabled if enabled is None else enabled,
                    item_types={key: (self.type_checks["weapons"].isChecked() if key == "weapons" else True) for key in ITEM_TYPES}, item_rules={"items": {}, "subtypes": {}},
                    open_containers=self.open_containers.isChecked(), locked_containers=self.locked_containers.isChecked(),
                    rapid_melee=False, melee_speed=self.melee_speed.value(),
                    excluded_ids=list(self.excluded_by_game.get(self.game_key or self.game_choice.currentData(), [])))

    def load_settings(self):
        try:
            s = json.loads((BASE / "settings.json").read_text(encoding="utf-8"))
            self.radius.setValue(float(s.get("radius", 8)))
            self.corpses.setChecked(bool(s.get("corpses", True)))
            self.containers.setChecked(bool(s.get("containers", True)))
            self.items.setChecked(bool(s.get("items", True)))
            self.open_containers.setChecked(bool(s.get("open_containers", False)))
            self.locked_containers.setChecked(bool(s.get("locked_containers", False)))
            self.melee_speed.setValue(float(s.get("melee_speed", 12)))
            self.update_open_controls()
            selection = checked_item_types(s.get("item_types"))
            for key, box in self.type_checks.items():
                box.setChecked(selection[key])
            self.item_rules = checked_rules(s.get("item_rules"))
            self.update_rule_count()
            preference = s.get('game_preference', 'auto')
            index = self.game_choice.findData(preference)
            if index >= 0:
                self.game_choice.setCurrentIndex(index)
            exclusions = s.get('excluded_weapons', {})
            if isinstance(exclusions, dict):
                for game in ('dl2', 'beast'):
                    try:
                        self.excluded_by_game[game] = checked_exclusions(game, exclusions.get(game, []))
                    except ValueError:
                        logging.warning('Invalid saved %s weapon exclusions', game)
            self.update_weapon_exclusion_count()
        except (OSError, ValueError, TypeError):
            pass

    @Slot()
    def settings_changed(self, *args):
        if self.loading_settings:
            return
        self.config_dirty = True
        self.settings_timer.start()

    def flush_settings(self):
        s = self.settings(False); s.pop("enabled"); s.pop("excluded_ids")
        try:
            temp = BASE / "settings.json.tmp"
            # Combat always requires a new opt-in after launching BP.
            temp.write_text(json.dumps({**s, "rapid_melee": False, "game_preference": self.game_choice.currentData(), "excluded_weapons": self.excluded_by_game}, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(BASE / "settings.json")
        except OSError:
            logging.exception("Could not save settings")
        if self.connected and not self.inflight and self.config_dirty:
            self.config_dirty = False
            # Clearing the final type while running stops immediately.
            if not has_allowed(s["item_types"], s["item_rules"]) or not (s["corpses"] or s["items"] or s["containers"]):
                self.enabled = False
            self.inflight = True
            self.command.emit("configure", self.settings())

    @Slot()
    def connect_game(self):
        if self.inflight:
            return
        self.inflight = True; self.connection.setEnabled(False)
        self.command.emit("disconnect" if self.connected else "connect", {} if self.connected else {"game": self.game_choice.currentData()})
        self.status.setText("正在校验游戏构建…" if not self.connected else "正在断开…")
        self.refresh_controls()

    @Slot()
    def toggle(self):
        if not self.connected or self.inflight:
            return
        if not self.enabled and not (self.corpses.isChecked() or self.items.isChecked() or self.containers.isChecked()):
            self.add_log("请至少勾选一个搜刮功能。")
            return
        if not self.enabled and not has_allowed(self.settings()["item_types"], self.settings()["item_rules"]):
            self.add_log("请至少勾选一种允许拾取的物品类型。")
            return
        self.inflight = True
        self.command.emit("configure", self.settings(not self.enabled))
        self.refresh_controls()

    def stop(self):
        self.rapid_melee.setChecked(False)
        if self.connected:
            self.enabled = False
            self.command.emit("stop", {})

    def toggle_melee(self):
        if self.connected and not self.inflight and not self.quitting:
            self.rapid_melee.setChecked(not self.rapid_melee.isChecked())

    @Slot(str, dict)
    def on_completed(self, name, result):
        self.inflight = False; self.connection.setEnabled(True)
        if name == "connect":
            self.connected = True
            self.game_key = result.get("game")
            game_label = "消逝的光芒 2" if self.game_key == "dl2" else "消逝的光芒：困兽"
            self.setWindowTitle(f"BP · {game_label}  v{__version__}")
            self.update_weapon_exclusion_count()
            if self.game_key == "dl2":
                self.add_log("消光 2：自动开箱需勾选；锁箱需再单独勾选试验选项。")
            self.connection.setText("断开连接")
            self.badge.setText(f"  已连接 {game_label}  PID {result['pid']}  ")
            self.body_count.setText("0"); self.item_count.setText("0")
            self.container_count.setText("0")
            self.add_log(f"已连接 PID {result['pid']}；构建校验通过。")
            self.command.emit("configure", self.settings(False))
        elif name == "configure":
            self.enabled = result.get("enabled", False)
        elif name == "disconnect":
            self.set_disconnected("已断开连接")
        elif name == "stop":
            self.enabled = False
            self.add_log("已停止自动搜刮。")
        self.refresh_controls()
        if self.config_dirty and not self.quitting:
            self.settings_timer.start()

    def refresh_controls(self):
        self.toggle_button.setEnabled(self.connected and not self.quitting and not self.inflight)
        self.toggle_button.setText("暂停 (F6)" if self.enabled else "开始 (F6)")
        self.toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause
            if self.enabled else QStyle.StandardPixmap.SP_MediaPlay))
        self.stop_button.setEnabled(self.connected and not self.quitting)
        self.toggle_action.setEnabled(self.toggle_button.isEnabled())
        self.stop_action.setEnabled(self.stop_button.isEnabled())
        self.connect_action.setEnabled(not self.inflight and not self.quitting)
        self.game_choice.setEnabled(not self.connected and not self.inflight and not self.quitting)
        self.rapid_melee.setEnabled(False)
        for widget in (self.corpses, self.containers):
            widget.setEnabled(True)
        self.update_open_controls()
        if self.diy_ready:
            # Let the write button explain an unavailable operation on click.
            self.diy_page.apply_button.setEnabled(not self.quitting)
            self.diy_page.generate_button.setEnabled(not self.quitting)

    def set_disconnected(self, reason):
        self.connected = self.enabled = self.inflight = False
        self.game_key = None
        self.setWindowTitle(f"BP · 消光 2 / 困兽自动搜刮  v{__version__}")
        self.update_weapon_exclusion_count()
        self.diy_pending = False
        self.diy_timer.stop()
        self.rapid_melee.setChecked(False)
        self.melee_status.setText("未开启")
        self.connection.setText("连接游戏"); self.connection.setEnabled(True)
        self.badge.setText("  未连接游戏  "); self.status.setText(reason)
        self.near_count.setText("—"); self.filtered_count.setText("0")
        self.scan_status.setText("F6 开关  |  F8 停止")
        self.refresh_controls(); self.add_log(reason)

    @Slot(dict)
    def on_event(self, event):
        kind = event.get("event")
        if kind == "stats":
            self.enabled = event.get("enabled", False)
            self.body_count.setText(str(event.get("corpses", 0)))
            self.container_count.setText(str(event.get('containers', 0)))
            self.item_count.setText(str(event.get("items", 0)))
            self.near_count.setText(str(event.get("nearbyCorpses", 0) + event.get("nearbyItems", 0) + event.get("nearbyContainers", 0)))
            self.filtered_count.setText(str(event.get("filtered", 0)))
            self.filtered_count.setToolTip(f"当前扫描按类型跳过的目标，含未知类型 {event.get('unknown', 0)} 个")
            melee = event.get("melee") or {}
            self.melee_status.setText({"disabled": "未开启", "idle": "等待按住左键", "attacking": "连续快砍中",
                "background": "等待切回游戏", "paused": "已暂停", "waiting_level": "等待场景就绪",
                "waiting_player": "等待角色", "melee_required": "请手持近战武器", "error": "已停止：出错"}.get(melee.get("status"), "未开启"))
            self.melee_status.setToolTip(melee.get("error") or "松开左键停止；F8 停止全部功能。")
            self.scan_status.setText(f"半径 {self.radius.value():g} 米  |  扫描 {event.get('scanMs', 0)} ms")
            state = event.get("status", "waiting")
            self.status.setText(STATUS.get(state, state))
            if state != self.last_status:
                self.last_status = state
                self.add_log(STATUS.get(state, state))
                if event.get("error"):
                    self.add_log(event["error"])
            self.refresh_controls()
        elif kind == "loot":
            if event["kind"] == "container_open":
                text = "锁箱柜" if event.get("locked") else "普通箱柜"
                if event.get("children", 0):
                    text += f"已开启，发现 {event['children']} 个物品目标，继续按筛选领取"
                elif event.get("after") == 5:
                    text += "已开启，未发现剩余物品"
                else:
                    text += "已开启，继续按筛选领取物品"
                self.add_log(text, action="开启箱柜", distance=event.get("distance", 0))
                return
            label = {"corpse": "搜刮尸体", "container": "搜刮容器", "container_open": "打开容器"}.get(event["kind"], "拾取物品")
            group = event.get("group")
            text = event.get("name") or (ITEM_TYPES[group][0] if group in ITEM_TYPES else {
                "corpse": "尸体战利品", "container": "容器战利品", "container_open": "已打开，继续按筛选领取内容"}.get(event["kind"], "物品")
            )
            self.add_log(text, action=label, distance=event.get("distance", 0))
        elif kind == "detached":
            self.set_disconnected("游戏连接已断开：" + event.get("reason", ""))
        elif kind == "diy":
            self.finish_diy(event)
        elif kind == "container_wait":
            self.add_log(event["message"], action="等待箱柜内容", distance=event.get("distance", 0))
        elif kind == "error":
            self.stop(); self.on_failed(event.get("error", "未知错误"))
        elif kind == "melee_error":
            self.rapid_melee.setChecked(False)
            self.add_log("千刀已停止：" + event.get("error", "未知错误"))

    @Slot(str)
    def on_failed(self, text):
        self.inflight = False
        # A rejected command (for example an unsupported DIY write) must not leave
        # the DIY page waiting for the watchdog.
        self.diy_pending = False
        self.diy_timer.stop()
        self.connection.setEnabled(True)
        self.status.setText("操作未完成，详见下方日志")
        self.add_log(text); self.refresh_controls()
        if self.diy_ready and self.tabs.currentIndex() == 1:
            self.diy_page.status.setText(text)

    def check_keys(self):
        for key in self.keys:
            down = bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)
            if down and not self.keys[key]:
                if key == 0x75: self.toggle()
                elif key == 0x76: pass
                else: self.stop()
            self.keys[key] = down

    def closeEvent(self, event):
        if self.quitting and not self.thread.isRunning():
            event.accept(); return
        event.ignore()
        if not self.quitting:
            self.quitting = True
            self.update_timer.stop()
            self.install_timer.stop()
            self.update_client.cancel()
            self.discard_staged_update()
            self.close_update_progress()
            self.enabled = False
            self.rapid_melee.setChecked(False)
            self.flush_settings()
            self.settings_timer.stop()
            self.hotkeys.stop(); self.setEnabled(False)
            self.status.setText("正在停止并断开游戏…")
            self.command.emit("quit", {})

    @Slot()
    def finish_close(self):
        self.close()


def configure_application(app):
    app.setApplicationName("beast-pick")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets" / "beast-pick.ico")))
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hyhacct.beast-pick")
    # Keep Windows controls, focus rectangles, menus and the system palette.
    styles = {name.lower(): name for name in QStyleFactory.keys()}
    app.setStyle(styles.get("windowsvista", styles.get("windows", "Fusion")))
    app.setFont(QFont("Microsoft YaHei UI", 9))


def main():
    app = QApplication(sys.argv)
    configure_application(app)
    # Also honor the pre-rename lock while users migrate their desktop copy.
    locks = [QLockFile(str(Path(tempfile.gettempdir()) / name)) for name in
             ("beast-pick-instance.lock", "beast-autoloot-instance.lock")]
    for lock in locks:
        if not lock.tryLock(100):
            QMessageBox.information(None, "Beast Pick", "工具已经在运行，请先关闭旧版或切回现有窗口。")
            return 0
    (BASE / "logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler(BASE / "logs" / "beast-pick.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    window = Window(check_updates='--skip-update-check' not in sys.argv); window.show()
    acknowledge_update(sys.argv)
    result = app.exec()
    # Do not leave the Python QMainWindow override alive until QApplication's
    # destructor runs during interpreter finalization.
    from shiboken6 import delete
    if window.thread.isRunning():
        window.thread.wait(5000)
    if not window.thread.isRunning():
        delete(window)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
