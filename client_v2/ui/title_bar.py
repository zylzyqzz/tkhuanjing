from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from .. import APP_NAME, APP_VERSION
from .tokens import BTN_CLOSE_HOVER, TITLEBAR_BG, TITLEBAR_BORDER, TITLEBAR_H


class TitleBar(QFrame):
    def __init__(self, window, parent=None):
        super().__init__(parent); self.window = window; self._drag: QPoint | None = None
        self.setFixedHeight(TITLEBAR_H)
        self.setStyleSheet(f"QFrame{{background:{TITLEBAR_BG};border-bottom:1px solid {TITLEBAR_BORDER}}}")
        layout = QHBoxLayout(self); layout.setContentsMargins(16,0,8,0)
        logo = QLabel("◈"); logo.setStyleSheet("color:#2563EB;font-size:20px;font-weight:800"); layout.addWidget(logo)
        title = QLabel(f"{APP_NAME}  V{APP_VERSION}"); title.setStyleSheet("font-weight:700"); layout.addWidget(title); layout.addStretch()
        minimize = QPushButton("—"); minimize.setFixedSize(36,30); minimize.clicked.connect(window.showMinimized); layout.addWidget(minimize)
        close = QPushButton("×"); close.setFixedSize(36,30); close.setStyleSheet(f"QPushButton:hover{{background:{BTN_CLOSE_HOVER};color:white}}QPushButton{{border:0;font-size:18px}}"); close.clicked.connect(window.close); layout.addWidget(close)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self._drag = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton: self.window.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _event): self._drag = None
