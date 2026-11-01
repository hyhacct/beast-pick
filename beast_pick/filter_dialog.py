"""Native Qt editor for subtype and exact inventory rules."""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QStyledItemDelegate,
    QTabWidget, QTableView, QVBoxLayout, QWidget,
)

from .catalog import checked_rules, load_catalog
from .categories import ITEM_TYPES

ROLES = Qt.ItemDataRole
RULE_NAMES = {None: "跟随上级", True: "拾取", False: "跳过"}


class RuleModel(QAbstractTableModel):
    def __init__(self, kind, rules, selection, parent=None):
        super().__init__(parent)
        self.kind, self.rules, self.selection = kind, rules, selection
        self.catalog = load_catalog()
        self.rows = sorted(self.catalog[kind].items(), key=lambda pair: (pair[1]["group"], pair[1]["name"], pair[0]))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 5 if self.kind == "items" else 4

    def headerData(self, section, orientation, role=ROLES.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == ROLES.DisplayRole:
            return (["规则", "物品名称", "大类", "子类", "内部标识"] if self.kind == "items"
                    else ["规则", "子类名称", "大类", "内部标识"])[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=ROLES.DisplayRole):
        if not index.isValid():
            return None
        key, item = self.rows[index.row()]
        rule = self.rules[self.kind].get(key)
        if role == ROLES.EditRole and index.column() == 0:
            return -1 if rule is None else int(rule)
        if role in (ROLES.DisplayRole, ROLES.ToolTipRole):
            inherited = self.selection[item["group"]]
            if self.kind == "items":
                inherited = self.rules["subtypes"].get(item["subtype"], inherited)
            rule_text = RULE_NAMES[rule] if rule is not None else f"跟随上级（{'拾取' if inherited else '跳过'}）"
            columns = [rule_text, item["name"], ITEM_TYPES[item["group"]][0]]
            if self.kind == "items":
                columns.append(self.catalog["subtypes"][item["subtype"]]["name"])
            columns.append(key)
            return columns[index.column()]
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=ROLES.EditRole):
        if role != ROLES.EditRole or index.column() != 0 or value not in (-1, 0, 1):
            return False
        key = self.rows[index.row()][0]
        if value == -1:
            self.rules[self.kind].pop(key, None)
        else:
            self.rules[self.kind][key] = bool(value)
        self.dataChanged.emit(index, index, [ROLES.DisplayRole, ROLES.EditRole])
        return True


class RuleProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self.group = self.subtype = ""

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        key, entry = model.rows[row]
        if self.group and entry["group"] != self.group:
            return False
        if self.subtype and entry.get("subtype") != self.subtype:
            return False
        fields = [key, entry["name"], ITEM_TYPES[entry["group"]][0]]
        if model.kind == "items":
            fields.append(model.catalog["subtypes"][entry["subtype"]]["name"])
        return self.query in " ".join(fields).casefold()


class RuleDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        for label, value in [("跟随上级", -1), ("拾取", 1), ("跳过", 0)]:
            editor.addItem(label, value)
        return editor

    def setEditorData(self, editor, index):
        editor.setCurrentIndex(editor.findData(index.data(ROLES.EditRole)))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentData(), ROLES.EditRole)


class FilterDialog(QDialog):
    def __init__(self, rules, selection, parent=None):
        super().__init__(parent)
        self.rules = checked_rules(rules)
        self.setWindowTitle("详细物品筛选")
        self.resize(960, 620)
        layout = QVBoxLayout(self)
        label = QLabel("优先级：具体物品 > 子类 > 主窗口大类。双击规则可修改；也可选中多行后批量设置。")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.tabs = QTabWidget()
        self.pages = []
        for kind, tab_title in [("subtypes", "按子类"), ("items", "按物品名称")]:
            page = QWidget()
            box = QVBoxLayout(page)
            controls = QHBoxLayout()
            search = QLineEdit()
            search.setPlaceholderText("搜索名称或内部标识，如：手雷、燃烧瓶")
            controls.addWidget(search, 1)
            groups = QComboBox()
            groups.addItem("全部大类", "")
            for key, (name, _) in ITEM_TYPES.items():
                groups.addItem(name, key)
            controls.addWidget(groups)
            subtype = QComboBox()
            subtype.setMinimumWidth(160)
            if kind == "items":
                controls.addWidget(subtype)
            box.addLayout(controls)
            model = RuleModel(kind, self.rules, selection, self)
            proxy = RuleProxy(self)
            proxy.setSourceModel(model)
            table = QTableView()
            table.setModel(proxy)
            table.setItemDelegateForColumn(0, RuleDelegate(table))
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            table.verticalHeader().hide()
            table.verticalHeader().setDefaultSectionSize(25)
            table.setWordWrap(False)
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(0, 160)
            table.setColumnWidth(1, 225)
            table.setColumnWidth(2, 150)
            if kind == "items":
                table.setColumnWidth(3, 180)
            header.setStretchLastSection(True)
            box.addWidget(table, 1)
            actions = QHBoxLayout()
            for title, value in [("选中项跟随上级", -1), ("选中项拾取", 1), ("选中项跳过", 0)]:
                button = QPushButton(title)
                button.clicked.connect(lambda checked=False, t=table, p=proxy, m=model, v=value: self.apply_selected(t, p, m, v))
                actions.addWidget(button)
            actions.addStretch()
            count = QLabel()
            actions.addWidget(count)
            box.addLayout(actions)
            def refresh(*args, p=proxy, s=search, g=groups, st=subtype, c=count, k=kind):
                p.query, p.group = s.text().strip().casefold(), g.currentData()
                p.subtype = st.currentData() or "" if k == "items" else ""
                p.invalidateFilter()
                c.setText(f"{p.rowCount()} 项")
            def group_changed(*args, g=groups, st=subtype, cb=refresh):
                st.blockSignals(True)
                st.clear()
                st.addItem("全部子类", "")
                for key, entry in sorted(load_catalog()["subtypes"].items(), key=lambda pair: pair[1]["name"]):
                    if not g.currentData() or entry["group"] == g.currentData():
                        st.addItem(entry["name"], key)
                st.blockSignals(False)
                cb()
            search.textChanged.connect(refresh)
            groups.currentIndexChanged.connect(group_changed)
            subtype.currentIndexChanged.connect(refresh)
            group_changed()
            self.tabs.addTab(page, tab_title)
            self.pages.append((model, proxy))
        self.tabs.currentChanged.connect(self.refresh_inherited)
        layout.addWidget(self.tabs, 1)
        note = QLabel("没有中文名称的条目显示内部标识；清单含当前构建的任务/特殊物品，是否可领取仍由游戏判断。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_selected(self, table, proxy, model, value):
        for index in table.selectionModel().selectedRows():
            model.setData(proxy.mapToSource(index), value)

    def refresh_inherited(self, *args):
        for model, proxy in self.pages:
            model.dataChanged.emit(model.index(0, 0), model.index(model.rowCount() - 1, 0), [ROLES.DisplayRole])
