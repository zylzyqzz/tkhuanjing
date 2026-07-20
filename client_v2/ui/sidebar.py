from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout

from .tokens import SIDEBAR_ACTIVE, SIDEBAR_BG, SIDEBAR_HOVER, SIDEBAR_TEXT, SIDEBAR_TEXT_ON, SIDEBAR_W


class Sidebar(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedWidth(SIDEBAR_W); self.setStyleSheet(f"QFrame{{background:{SIDEBAR_BG}}}")
        layout = QVBoxLayout(self); layout.setContentsMargins(12,22,12,18); layout.setSpacing(8)
        brand = QLabel("VD NEXUS"); brand.setStyleSheet("color:white;font-size:17px;font-weight:800;padding:8px"); layout.addWidget(brand)
        self.group = QButtonGroup(self); self.group.setExclusive(True); self.buttons = {}
        for key, icon, text in (("home","⌂","首页"),("report","≡","检测报告"),("settings","⚙","设置"),("about","ⓘ","关于")):
            button = QPushButton(f"{icon}   {text}"); button.setCheckable(True); button.setFixedHeight(44); button.setStyleSheet(f"QPushButton{{text-align:left;padding-left:14px;color:{SIDEBAR_TEXT};background:transparent;border:0}}QPushButton:hover{{background:{SIDEBAR_HOVER};color:white}}QPushButton:checked{{background:{SIDEBAR_ACTIVE};color:{SIDEBAR_TEXT_ON};font-weight:700}}")
            button.clicked.connect(lambda _=False, page=key: self.selected.emit(page)); self.group.addButton(button); self.buttons[key] = button; layout.addWidget(button)
        layout.addStretch(); note = QLabel("网络 · 系统 · 性能"); note.setStyleSheet(f"color:{SIDEBAR_TEXT};font-size:10px;padding:8px"); layout.addWidget(note); self.buttons["home"].setChecked(True)

    def select(self, page: str):
        if page in self.buttons: self.buttons[page].setChecked(True)
