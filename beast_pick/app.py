from __future__ import annotations

import ctypes
import json
import logging
import sys
import tempfile
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, QLockFile, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QGroupBox, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton, QStyle, QStyleFactory,
    QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .backend import Client, MAX_RADIUS
from . import __version__
from .categories import ITEM_TYPES, checked_item_types
from .catalog import checked_rules, has_allowed
from .filter_dialog import FilterDialog

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
STATUS = {
    "waiting": "等待游戏更新", "disabled": "已停止", "running": "正在自动搜刮",
    "background": "等待切回游戏", "waiting_level": "等待场景就绪", "paused": "游戏已暂停或正在加载",
    "single_player_only": "仅支持单人场景，当前已暂停", "waiting_player": "等待角色就绪",
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
                result = self.client.connect()
            elif name == "configure":
                result = self.client.configure(**payload)
            elif name == "stop":
                self.client.stop(); result = {}
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

    def __init__(self):
        super().__init__()
        self.connected = False
        self.enabled = False
        self.inflight = False
        self.quitting = False
        self.last_status = None
        self.loading_settings = True
        self.config_dirty = False
        self.item_rules = checked_rules()
        self.keys = {0x75: False, 0x77: False}  # F6 / F8
        self.setWindowTitle(f"Beast Pick · 困兽自动搜刮  v{__version__}")
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon))
        self.setMinimumSize(700, 570)
        self.resize(760, 660)
        self.settings_timer = QTimer(self)
        self.settings_timer.setSingleShot(True)
        self.settings_timer.setInterval(180)
        self.settings_timer.timeout.connect(self.flush_settings)
        self.build_ui()
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
        self.add_log("进入单人存档后连接游戏，按 F6 开始，F8 停止。")

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
        help_menu = self.menuBar().addMenu("帮助(&H)")
        help_menu.addAction("使用说明", self.show_help)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(10)
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
        layout.addWidget(options_box)

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
        layout.addWidget(filter_box)

        stats_box = QGroupBox("本次连接统计")
        numbers = QHBoxLayout(stats_box)
        self.body_count = QLabel("0"); self.item_count = QLabel("0"); self.near_count = QLabel("—")
        self.container_count = QLabel("0")
        self.container_count.setToolTip("已领取物品的普通容器数；同一个容器只计一次。")
        self.filtered_count = QLabel("0")
        for label, value in [("尸体：", self.body_count), ("容器：", self.container_count), ("散落物品：", self.item_count),
                             ("附近目标：", self.near_count), ("已排除：", self.filtered_count)]:
            numbers.addWidget(QLabel(label)); numbers.addWidget(value); numbers.addStretch()
        layout.addWidget(stats_box)

        log_title = QHBoxLayout()
        log_title.addWidget(QLabel("运行记录"))
        log_title.addStretch()
        clear_button = QPushButton("清空记录")
        clear_button.clicked.connect(lambda: self.log.clear())
        log_title.addWidget(clear_button)
        layout.addLayout(log_title)
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
        layout.addWidget(self.log, 1)
        self.status = QLabel("等待连接游戏")
        self.statusBar().addWidget(self.status, 1)
        self.scan_status = QLabel("F6 开关  |  F8 停止")
        self.statusBar().addPermanentWidget(self.scan_status)
        for widget in [self.corpses, self.containers, self.items, self.open_containers, self.locked_containers]:
            widget.toggled.connect(self.settings_changed)
        self.radius.valueChanged.connect(self.settings_changed)
        self.refresh_controls()

    def show_help(self):
        QMessageBox.information(self, "使用说明", "1. 进入单人存档，点击‘连接游戏’。\n"
            "2. 设置半径、大类和详细筛选。\n3. 切回游戏按 F6 开启，F8 停止。\n\n"
            "详细筛选支持中文名称和子类；优先级：具体物品 > 子类 > 大类。\n"
            "选择‘跟随上级’可恢复继承规则。无法确认身份的目标在有详细规则时跳过。\n"
            "开启箱柜与强制开启锁箱柜是独立开关，默认关闭；只接受已识别的普通容器类型。\n"
            "每秒最多开启一个；门、关联机关、特殊禁搜刮容器和未知锁型跳过。\n"
            "开锁仍处于试验阶段，尚未完成长期稳定性验证。\n"
            "打开后按筛选领取内容；独立物品需勾选‘自动拾取散落物品’。\n"
            "有排除规则时跳过内容不透明的物资包；未知大类跳过。\n"
            "500 米仅查询已加载目标，不判断墙体遮挡。\n\n"
            "适配版本：1.7.1.0na。关闭窗口停止功能并移除本工具回调；空闲桥接保留到游戏退出。")

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
                    item_types={key: box.isChecked() for key, box in self.type_checks.items()}, item_rules=self.item_rules,
                    open_containers=self.open_containers.isChecked(), locked_containers=self.locked_containers.isChecked())

    def load_settings(self):
        try:
            s = json.loads((BASE / "settings.json").read_text(encoding="utf-8"))
            self.radius.setValue(float(s.get("radius", 8)))
            self.corpses.setChecked(bool(s.get("corpses", True)))
            self.containers.setChecked(bool(s.get("containers", True)))
            self.items.setChecked(bool(s.get("items", True)))
            self.open_containers.setChecked(bool(s.get("open_containers", False)))
            self.locked_containers.setChecked(bool(s.get("locked_containers", False)))
            self.update_open_controls()
            selection = checked_item_types(s.get("item_types"))
            for key, box in self.type_checks.items():
                box.setChecked(selection[key])
            self.item_rules = checked_rules(s.get("item_rules"))
            self.update_rule_count()
        except (OSError, ValueError, TypeError):
            pass

    @Slot()
    def settings_changed(self, *args):
        if self.loading_settings:
            return
        self.config_dirty = True
        self.settings_timer.start()

    def flush_settings(self):
        s = self.settings(False); s.pop("enabled")
        try:
            temp = BASE / "settings.json.tmp"
            temp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(BASE / "settings.json")
        except OSError:
            logging.exception("Could not save settings")
        if self.connected and not self.inflight and self.config_dirty:
            self.config_dirty = False
            # Clearing the final type while running stops immediately.
            if not has_allowed(s["item_types"], self.item_rules) or not (s["corpses"] or s["items"] or s["containers"]):
                self.enabled = False
            self.inflight = True
            self.command.emit("configure", self.settings())

    @Slot()
    def connect_game(self):
        if self.inflight:
            return
        self.inflight = True; self.connection.setEnabled(False)
        self.command.emit("disconnect" if self.connected else "connect", {})
        self.status.setText("正在校验游戏构建…" if not self.connected else "正在断开…")
        self.refresh_controls()

    @Slot()
    def toggle(self):
        if not self.connected or self.inflight:
            return
        if not self.enabled and not (self.corpses.isChecked() or self.items.isChecked() or self.containers.isChecked()):
            self.add_log("请至少勾选一个搜刮功能。")
            return
        if not self.enabled and not has_allowed({key: box.isChecked() for key, box in self.type_checks.items()}, self.item_rules):
            self.add_log("请至少勾选一种允许拾取的物品类型。")
            return
        self.inflight = True
        self.command.emit("configure", self.settings(not self.enabled))
        self.refresh_controls()

    def stop(self):
        if self.connected:
            self.enabled = False
            self.command.emit("stop", {})

    @Slot(str, dict)
    def on_completed(self, name, result):
        self.inflight = False; self.connection.setEnabled(True)
        if name == "connect":
            self.connected = True
            self.connection.setText("断开连接")
            self.badge.setText(f"  已连接  PID {result['pid']}  ")
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

    def set_disconnected(self, reason):
        self.connected = self.enabled = self.inflight = False
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
        elif kind == "container_wait":
            self.add_log(event["message"], action="等待箱柜内容", distance=event.get("distance", 0))
        elif kind == "error":
            self.stop(); self.on_failed(event.get("error", "未知错误"))

    @Slot(str)
    def on_failed(self, text):
        self.inflight = False; self.connection.setEnabled(True)
        self.status.setText("操作未完成，详见下方日志")
        self.add_log(text); self.refresh_controls()

    def check_keys(self):
        for key in self.keys:
            down = bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)
            if down and not self.keys[key]:
                self.toggle() if key == 0x75 else self.stop()
            self.keys[key] = down

    def closeEvent(self, event):
        if self.quitting and not self.thread.isRunning():
            event.accept(); return
        event.ignore()
        if not self.quitting:
            self.quitting = True
            self.enabled = False
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
    window = Window(); window.show()
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
