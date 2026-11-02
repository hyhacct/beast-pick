"""One decision: update now or keep using the current version."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from . import __version__


class UpdateDialog(QDialog):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.setWindowTitle('发现新版本')
        self.resize(540, 370)
        layout = QVBoxLayout(self)
        heading = QLabel(f'BP {release.tag} 已发布（当前 v{__version__}）')
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlainText(release.notes or '该版本暂无更新说明。')
        layout.addWidget(self.notes)
        layout.addWidget(QLabel('更新完成后自动重启。'))
        buttons = QDialogButtonBox()
        self.update_button = buttons.addButton('立即更新', QDialogButtonBox.ButtonRole.AcceptRole)
        self.later_button = buttons.addButton('稍后', QDialogButtonBox.ButtonRole.RejectRole)
        self.update_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
