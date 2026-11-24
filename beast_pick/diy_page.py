"""Second page: build a weapon from the full catalogue with custom quality, stats,
attachments and affixes."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import diy

ROW_LIMIT = 600


class DiyPage(QWidget):
    apply_requested = Signal(dict)
    generate_requested = Signal(dict)
    notice = Signal(str)
    # A click that cannot write anything must never look like a dead button.
    blocked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = sorted(((key, value) for key, value in diy.families().items()),
                              key=lambda item: (item[1]['n'], item[0]))
        self.filtered = self.entries
        self.current = None
        self.stat_boxes = {}
        self.stat_labels = {}
        self.mod_boxes = {}
        self.mod_rows = {}
        self.mod_descriptions = {}
        self.available_slot_keys = set()
        self.slot_entries = diy.slots()
        self.build()
        self.reload_list()

    # ---------------------------------------------------------------- layout
    def build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索武器名称，例如：砍刀 / 步枪")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.schedule_reload)
        left_layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItem("全部武器", "")
        self.kind.addItem("近战", "melee")
        self.kind.addItem("枪械", "firearm")
        self.kind.currentIndexChanged.connect(self.reload_subtypes)
        filters.addWidget(self.kind, 1)
        self.subtype = QComboBox()
        self.subtype.currentIndexChanged.connect(self.schedule_reload)
        filters.addWidget(self.subtype, 1)
        left_layout.addLayout(filters)
        self.count = QLabel("")
        left_layout.addWidget(self.count)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["武器", "类型"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().resizeSection(0, 210)
        self.tree.currentItemChanged.connect(self.select_row)
        left_layout.addWidget(self.tree, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        self.title = QLabel("选择左侧武器开始配置")
        self.title.setWordWrap(True)
        font = self.title.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self.title.setFont(font)
        right_layout.addWidget(self.title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 0)
        body_layout.setSpacing(8)

        base_box = QGroupBox("品质与档位")
        base_form = QFormLayout(base_box)
        self.quality = QComboBox()
        for entry in diy.colors():
            self.quality.addItem(entry['name'], entry['value'])
        self.quality.currentIndexChanged.connect(self.refresh_preview)
        self.quality.setToolTip("品质由武器定义决定，实例写入不改变品质；这里的选择只影响预览与方案导出。")
        base_form.addRow("品质", self.quality)
        level_row = QWidget()
        level_layout = QHBoxLayout(level_row)
        level_layout.setContentsMargins(0, 0, 0, 0)
        self.level = QSpinBox()
        self.level.setRange(0, 0)
        self.level.valueChanged.connect(self.refresh_preview)
        level_layout.addWidget(self.level)
        self.level_hint = QLabel("—")
        level_layout.addWidget(self.level_hint, 1)
        base_form.addRow("档位", level_row)
        body_layout.addWidget(base_box)

        stats_box = QGroupBox("属性（勾选即覆盖武器原值）")
        self.stats_box = stats_box
        stats_layout = QVBoxLayout(stats_box)
        stats_layout.setContentsMargins(9, 6, 9, 6)
        stats_layout.setSpacing(6)
        self.stats_hint = QLabel("")
        self.stats_hint.setWordWrap(True)
        stats_layout.addWidget(self.stats_hint)
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(12)
        stats_grid.setVerticalSpacing(5)
        stats_layout.addLayout(stats_grid)
        for index, (key, (label, unit)) in enumerate(diy.STAT_LABELS.items()):
            box = QDoubleSpinBox()
            low, high = diy.STAT_LIMITS[key]
            box.setRange(low, high)
            box.setDecimals(3 if high <= 1 else 2)
            box.setSingleStep(0.05 if high <= 1 else 1)
            box.setMinimumWidth(84)
            box.setKeyboardTracking(False)
            box.valueChanged.connect(self.refresh_preview)
            check = QCheckBox()
            check.toggled.connect(self.refresh_preview)
            name = QLabel(label)
            self.stat_boxes[key] = (check, box)
            self.stat_labels[key] = (name, label)
            row, column = divmod(index, 2)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.addWidget(check)
            cell_layout.addWidget(box, 1)
            cell_layout.addWidget(QLabel(unit))
            stats_grid.addWidget(name, row, column * 2)
            stats_grid.addWidget(cell, row, column * 2 + 1)
        body_layout.addWidget(stats_box)
        self.refresh_stat_availability(None)

        mods_box = QGroupBox("配件")
        self.mods_form = QFormLayout(mods_box)
        self.mods_form.setVerticalSpacing(4)
        self.no_mod_slots = QLabel("这把武器没有可用的配件插槽。")
        self.no_mod_slots.setWordWrap(True)
        self.mods_form.addRow(self.no_mod_slots)
        attachments = sorted(diy.mods().items(), key=lambda item: (item[1]['n'], item[0]))
        for slot in self.slot_entries:
            key = slot['key']
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)
            combo = QComboBox()
            combo.addItem("不安装", "")
            for mod_id, entry in attachments:
                if key in entry['slots']:
                    combo.addItem(diy.mod_label(mod_id), mod_id)
            combo.currentIndexChanged.connect(lambda _index, key=key: self.attachment_changed(key))
            description = QLabel()
            description.setWordWrap(True)
            description.setTextFormat(Qt.TextFormat.PlainText)
            description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            description.hide()
            row_layout.addWidget(combo)
            row_layout.addWidget(description)
            self.mod_rows[key] = row
            self.mod_boxes[key] = combo
            self.mod_descriptions[key] = description
            self.mods_form.addRow(slot['name'], row)
            self.mods_form.setRowVisible(row, False)
        body_layout.addWidget(mods_box)

        affix_box = QGroupBox(f"词条（最多 {diy.MAX_AFFIXES} 条）")
        affix_layout = QVBoxLayout(affix_box)
        self.affix_search = QLineEdit()
        self.affix_search.setPlaceholderText("搜索词条")
        self.affix_search.setClearButtonEnabled(True)
        self.affix_search.textChanged.connect(self.filter_affixes)
        affix_layout.addWidget(self.affix_search)
        self.affix_list = QListWidget()
        self.affix_list.setMaximumHeight(124)
        for key, entry in sorted(diy.affixes().items(), key=lambda item: (item[1]['n'], item[0])):
            item = QListWidgetItem(diy.affix_label(key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            detail = entry['d'] or key
            item.setToolTip(f"{detail}\n{key}" if detail != key else key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.affix_list.addItem(item)
        self.affix_list.itemChanged.connect(self.on_affix_changed)
        affix_layout.addWidget(self.affix_list)
        body_layout.addWidget(affix_box)

        self.preview = QLabel("—")
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(72)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.preview.setStyleSheet("padding: 6px; border: 1px solid palette(mid);")
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_layout.addStretch()
        scroll.setWidget(body)
        right_layout.addWidget(scroll, 1)
        right_layout.addWidget(self.preview)

        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result.setStyleSheet("padding: 6px; border: 1px solid palette(mid);")
        self.result.hide()
        right_layout.addWidget(self.result)

        actions = QHBoxLayout()
        self.copy_button = QPushButton("复制方案")
        self.copy_button.clicked.connect(self.copy_plan)
        actions.addWidget(self.copy_button)
        self.apply_button = QPushButton("写入手持武器")
        self.apply_button.setToolTip("只修改当前手持近战武器的已支持属性，不会新增背包物品。")
        self.apply_button.clicked.connect(self.apply)
        actions.addWidget(self.apply_button, 1)
        self.generate_button = QPushButton("生成到背包")
        self.generate_button.setToolTip("新增一把选定的近战武器到背包，不替换手持武器；仅写入已标定属性。")
        self.generate_button.clicked.connect(self.generate)
        actions.addWidget(self.generate_button, 1)
        right_layout.addLayout(actions)
        self.write_scope = QLabel("写入只修改当前手持近战武器的部分属性，不会新增背包物品。生成按钮会另加一把近战武器到背包，不替换手持武器。")
        self.write_scope.setWordWrap(True)
        right_layout.addWidget(self.write_scope)
        self.status = QLabel("未连接游戏时仍可浏览武器并导出方案。")
        self.status.setWordWrap(True)
        right_layout.addWidget(self.status)
        splitter.addWidget(right)
        splitter.setSizes([300, 640])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(180)
        self.reload_timer.timeout.connect(self.reload_list)
        self.reload_subtypes()

    # --------------------------------------------------------------- filters
    def reload_subtypes(self):
        kinds = {entry['kind'] for key, entry in self.filtered} or {'melee', 'firearm'}
        selected = self.kind.currentData()
        self.subtype.blockSignals(True)
        self.subtype.clear()
        self.subtype.addItem("全部子类", "")
        names = sorted({entry['sub'] for key, entry in self.entries
                        if not selected or entry['kind'] == selected})
        for name in names:
            self.subtype.addItem(name, name)
        self.subtype.blockSignals(False)
        self.schedule_reload()

    def schedule_reload(self, *args):
        self.reload_timer.start()

    def reload_list(self):
        text = self.search.text().strip().lower()
        kind = self.kind.currentData()
        subtype = self.subtype.currentData()
        result = []
        for key, entry in self.entries:
            if kind and entry['kind'] != kind:
                continue
            if subtype and entry['sub'] != subtype:
                continue
            if text and text not in entry['n'].lower() and text not in key.lower():
                continue
            result.append((key, entry))
        self.filtered = result
        self.tree.blockSignals(True)
        self.tree.clear()
        for key, entry in result[:ROW_LIMIT]:
            item = QTreeWidgetItem([entry['n'], entry['sub']])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            variants = entry.get('variants') or [key]
            tip = [entry['n'], key]
            if len(variants) > 1:
                tip.append(f"共 {len(variants)} 个等级变体：{variants[0]} … {variants[-1]}")
            item.setToolTip(0, "\n".join(tip))
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)
        shown = min(len(result), ROW_LIMIT)
        suffix = f"，仅显示前 {ROW_LIMIT} 条" if len(result) > ROW_LIMIT else ''
        self.count.setText(f"共 {len(result)} 把武器{suffix}")
        if self.current and any(key == self.current for key, _ in result[:ROW_LIMIT]):
            self.select_weapon(self.current)
        elif result:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def filter_affixes(self, text):
        text = text.strip().lower()
        for index in range(self.affix_list.count()):
            item = self.affix_list.item(index)
            item.setHidden(bool(text) and text not in item.text().lower())

    def refresh_stat_availability(self, entry):
        """Enable only the fields this build can really write for this weapon.

        The measured offsets belong to one description class, so a firearm would
        get its numbers written into unrelated fields. Keep those read-only and
        say why, instead of letting the click fail silently later.
        """
        writable = diy.writable_stats()
        allowed = diy.writable_for(entry)
        kind = (entry or {}).get('kind')
        for key, (check, box) in self.stat_boxes.items():
            name, label = self.stat_labels[key]
            supported = allowed and key in writable
            check.setEnabled(supported)
            box.setEnabled(supported)
            if supported:
                check.setToolTip("勾选后使用此数值覆盖武器原值")
                box.setToolTip("勾选后使用此数值覆盖武器原值")
                name.setText(label)
                continue
            if check.isChecked():
                check.setChecked(False)
            if not writable:
                reason = "当前游戏构建还没有属性写入布局"
            elif not allowed and kind == 'firearm':
                reason = "枪械的属性偏移尚未标定，暂不可写"
            else:
                reason = "该属性位于武器定义中，实例写入改不动它"
            check.setToolTip(reason)
            box.setToolTip(reason)
            name.setText(f"{label}（只读）")
        if not writable:
            hint = "此构建没有属性写入布局：可以浏览、配置并复制方案，写入会被拒绝。"
        elif not allowed:
            hint = ("属性写入只对近战武器标定过：这把武器的类型暂不支持写入。"
                    "品质、配件、词条也暂不写入。")
        else:
            names = "、".join(diy.STAT_LABELS[key][0] for key in writable if key in diy.STAT_LABELS)
            hint = f"本次会写入的数值：{names}。不写入：品质、配件、词条（仍可配置并导出方案）。"
        self.stats_hint.setText(hint)

    # -------------------------------------------------------------- selection
    def select_row(self, item, _previous=None):
        if item is None:
            return
        self.select_weapon(item.data(0, Qt.ItemDataRole.UserRole))

    def select_weapon(self, weapon_id):
        entry = diy.find_weapon(weapon_id)
        if not entry:
            return False
        weapon_id = entry['id']
        self.current = weapon_id
        for index in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(index)
            if row.data(0, Qt.ItemDataRole.UserRole) == weapon_id:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(row)
                self.tree.blockSignals(False)
                break
        self.title.setText(f"{entry['n']}　·　{entry['sub']}")
        table = diy.tiers().get(entry.get('tbl', ''), [])
        self.level.blockSignals(True)
        self.level.setRange(0, max(0, len(table) - 1))
        self.level.setValue(max(0, len(table) // 2))
        self.level.blockSignals(False)
        self.level.setEnabled(bool(table))
        self.refresh_stat_availability(entry)
        self.quality.blockSignals(True)
        index = self.quality.findData(entry.get('q') if entry.get('q') is not None else 0)
        self.quality.setCurrentIndex(max(0, index))
        self.quality.blockSignals(False)
        for key, (check, box) in self.stat_boxes.items():
            box.blockSignals(True)
            check.blockSignals(True)
            value = entry['s'].get(key)
            check.setChecked(False)
            box.setValue(float(value) if isinstance(value, (int, float)) else diy.STAT_LIMITS[key][0])
            check.blockSignals(False)
            box.blockSignals(False)
        self.refresh_attachment_slots(weapon_id)
        self.affix_list.blockSignals(True)
        for index in range(self.affix_list.count()):
            self.affix_list.item(index).setCheckState(Qt.CheckState.Unchecked)
        self.affix_list.blockSignals(False)
        self.refresh_preview()
        return True

    def refresh_attachment_slots(self, weapon_id):
        self.available_slot_keys = {slot['key'] for slot in diy.weapon_slots(weapon_id)}
        self.mods_form.setRowVisible(self.no_mod_slots, not self.available_slot_keys)
        for key, combo in self.mod_boxes.items():
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
            self.mod_descriptions[key].clear()
            self.mod_descriptions[key].hide()
            self.mods_form.setRowVisible(self.mod_rows[key], key in self.available_slot_keys)

    def attachment_changed(self, key):
        text = diy.mod_details(self.mod_boxes[key].currentData()) if key in self.available_slot_keys else ''
        description = self.mod_descriptions[key]
        description.setText(text)
        description.setVisible(bool(text))
        self.refresh_preview()

    def chosen_affixes(self):
        result = []
        for index in range(self.affix_list.count()):
            item = self.affix_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def on_affix_changed(self, item):
        if len(self.chosen_affixes()) > diy.MAX_AFFIXES:
            item.setCheckState(Qt.CheckState.Unchecked)
            self.notice.emit(f"最多选择 {diy.MAX_AFFIXES} 条词条")
        self.refresh_preview()

    def plan(self) -> dict:
        stats = {}
        for key, (check, box) in self.stat_boxes.items():
            if check.isChecked():
                stats[key] = box.value()
        chosen = {slot: combo.currentData() for slot, combo in self.mod_boxes.items()
                  if slot in self.available_slot_keys and combo.currentData()}
        return {
            'weapon': self.current,
            'quality': self.quality.currentData() or 0,
            'level': self.level.value(),
            'stats': stats,
            'mods': chosen,
            'affixes': self.chosen_affixes(),
        }

    def refresh_preview(self, *args):
        if not self.current:
            self.preview.setText("—")
            return
        try:
            summary = diy.preview(self.plan())
        except ValueError as exc:
            self.preview.setText(f"⚠ {exc}")
            return
        table = diy.damage_table(self.current)
        formula = diy.damage_formula(self.current)
        if table:
            self.level_hint.setText(f"伤害表 {len(table)} 档")
        elif formula:
            self.level_hint.setText(f"特殊公式：{formula}")
        else:
            self.level_hint.setText("该武器没有伤害档位表")
        damage = "—" if summary['damage'] is None else f"{summary['damage']:g}"
        total = "—" if summary['damage_total'] is None else f"{summary['damage_total']:g}"
        parts = [
            f"品质：{summary['quality']}　档位：{summary['level']}",
            f"基础伤害：{damage}（按生命上限公式：{formula}）" if formula and summary['damage'] is None
            else f"基础伤害：{damage}" + (f"　配件加成：+{summary['damage_bonus']:g}%　合成伤害：{total}"
                                        if summary['damage_bonus'] else ''),
            f"耐久：{summary['durability'] if summary['durability'] is not None else '—'}",
        ]
        if summary['mods']:
            labels = {slot['key']: slot['name'] for slot in self.slot_entries}
            parts.append("配件：" + "、".join(f"{labels[m['slot']]}：{m['name']}" for m in summary['mods']))
        if summary['affix_names']:
            parts.append("词条：" + "、".join(summary['affix_names']))
        self.preview.setText("\n".join(parts))

    # ----------------------------------------------------------------- actions
    def show_result(self, text, ok=True):
        self.result.setText(("✔ " if ok else "⚠ ") + text)
        self.result.setStyleSheet(
            "padding: 6px; border: 1px solid palette(mid);"
            + ("" if ok else "font-weight: bold;"))
        self.result.show()
        self.status.setText(text)

    def apply(self):
        if not self.current:
            self.blocked.emit("请先在左侧选择一把武器。")
            return
        try:
            plan = diy.validate_plan(self.plan())
        except ValueError as exc:
            self.blocked.emit(str(exc))
            return
        if not plan['stats']:
            entry = diy.find_weapon(self.current)
            name = (entry or {}).get('n') or self.current
            if not diy.writable_stats():
                reason = "当前游戏构建还没有属性写入布局，无法写入任何数值。"
            elif not diy.writable_for(entry):
                reason = (f"「{name}」的属性写入尚未标定：目前只支持近战武器，"
                          "这把武器的类型会写坏存档，已取消。")
            else:
                reason = "本次一个数值都没勾选：请勾选至少一项属性，再点写入。"
            self.blocked.emit(reason + "\n\n品质、配件、词条目前也不写入——这些改动需要先标定"
                                       "武器描述对象里的对应字段，正在做。")
            return
        self.apply_requested.emit(plan)

    def generate(self):
        if not self.current:
            self.blocked.emit("请先在左侧选择一把近战武器。")
            return
        try:
            plan = diy.prepare_generation(self.plan())
        except ValueError as exc:
            self.blocked.emit(str(exc))
            return
        self.generate_requested.emit(plan)

    def copy_plan(self):
        if not self.current:
            self.notice.emit("请先选择一把武器")
            return
        try:
            text = diy.export_plan(self.plan())
        except ValueError as exc:
            self.notice.emit(str(exc))
            return
        QApplication.clipboard().setText(text)
        self.status.setText("方案已复制到剪贴板。")
