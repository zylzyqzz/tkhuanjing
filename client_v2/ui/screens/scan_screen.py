from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..widgets.check_row import CheckRow
from ..widgets.ring_widget import RingWidget


class ScanScreen(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(54, 24, 54, 24)
        self.title = QLabel("正在检测开播环境"); self.title.setAlignment(Qt.AlignCenter); self.title.setProperty("title", True); layout.addWidget(self.title)
        self.status = QLabel("正在准备…"); self.status.setAlignment(Qt.AlignCenter); self.status.setProperty("muted", True); layout.addWidget(self.status)
        ring_row = QVBoxLayout(); self.ring = RingWidget(); ring_row.addWidget(self.ring, 0, Qt.AlignCenter); layout.addLayout(ring_row)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.rows_widget = QWidget(); self.rows = QVBoxLayout(self.rows_widget); self.rows.setContentsMargins(0,0,0,0); self.rows.addStretch(); self.scroll.setWidget(self.rows_widget); layout.addWidget(self.scroll, 1)
        self.cancel_button = QPushButton("取消检测"); self.cancel_button.clicked.connect(self.cancel_requested); layout.addWidget(self.cancel_button, 0, Qt.AlignCenter)

    def reset(self, repair: bool = False) -> None:
        self.title.setText("正在一键修复系统环境" if repair else "正在检测开播环境")
        self.ring.set_progress(0, "修复中" if repair else "检测中")
        self.cancel_button.setText("停止后续修复" if repair else "取消检测")
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def update_progress(self, value: int, text: str, repair: bool = False) -> None:
        self.status.setText(text); self.ring.set_progress(value, "修复中" if repair else "检测中")

    def add_result(self, title: str, value: str, status: str) -> None:
        self.rows.insertWidget(self.rows.count() - 1, CheckRow(title, value, status))
