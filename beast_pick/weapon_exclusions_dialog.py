"""Compact game-specific exact-item exclusion editor."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout
from .weapon_catalog import weapon_groups


class WeaponExclusionsDialog(QDialog):
    def __init__(self, game, exclusions, parent=None):
        super().__init__(parent)
        self.game = game
        self.exclusions = set(exclusions)
        self.setWindowTitle(('消光 2' if game == 'dl2' else '困兽') + ' · 排除指定物品')
        self.resize(640, 660)
        layout = QVBoxLayout(self)
        note = QLabel('勾选要排除的武器或投掷物；同名条目会同时排除所列的全部等级和版本。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索名称或内部 ID，例如：草叉')
        layout.addWidget(self.search)
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        for name, group, identities in weapon_groups(game):
            suffix = '投掷物' if group == 'throwables' else '武器'
            item = QListWidgetItem(f'{name}  ·  {suffix}  ·  {len(identities)} 个版本')
            item.setData(Qt.ItemDataRole.UserRole, identities)
            item.setData(Qt.ItemDataRole.UserRole + 1, (name + ' ' + ' '.join(identities)).casefold())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if any(x in self.exclusions for x in identities) else Qt.CheckState.Unchecked)
            item.setToolTip('\n'.join(identities[:30]) + ('\n…' if len(identities) > 30 else ''))
            self.items.addItem(item)
        self.items.itemChanged.connect(self.changed)
        self.search.textChanged.connect(self.filter_items)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def changed(self, item):
        ids = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.exclusions.update(ids)
        else:
            self.exclusions.difference_update(ids)

    def filter_items(self, text):
        value = text.casefold().strip()
        for i in range(self.items.count()):
            item = self.items.item(i)
            item.setHidden(value not in item.data(Qt.ItemDataRole.UserRole + 1))