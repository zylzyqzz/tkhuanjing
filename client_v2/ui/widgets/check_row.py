from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..tokens import ROW_DOT_D, ROW_H, status_color


class CheckRow(QWidget):
    def __init__(self, title: str, value: str, status: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(ROW_H)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        dot = QLabel()
        dot.setFixedSize(ROW_DOT_D, ROW_DOT_D)
        dot.setStyleSheet(f"background:{status_color(status)};border-radius:{ROW_DOT_D // 2}px")
        layout.addWidget(dot)
        label = QLabel(title)
        layout.addWidget(label, 1)
        result = QLabel(value)
        result.setProperty("muted", True)
        layout.addWidget(result)
