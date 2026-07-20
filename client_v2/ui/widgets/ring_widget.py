from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..tokens import ACCENT, BORDER_DEFAULT, RING_OUTER_D, RING_STROKE, TEXT_PRIMARY


class RingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._mode = "检测中"
        self.setFixedSize(RING_OUTER_D, RING_OUTER_D)

    def set_progress(self, value: int, mode: str | None = None) -> None:
        self._value = max(0, min(100, value))
        if mode:
            self._mode = mode
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(RING_STROKE, RING_STROKE, -RING_STROKE, -RING_STROKE)
        pen = QPen(QColor(BORDER_DEFAULT), RING_STROKE, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        pen.setColor(QColor(ACCENT))
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self._value / 100))
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont("Microsoft YaHei UI", 27, QFont.Bold))
        painter.drawText(self.rect().adjusted(0, -16, 0, 0), Qt.AlignCenter, f"{self._value}%")
        painter.setFont(QFont("Microsoft YaHei UI", 11))
        painter.drawText(self.rect().adjusted(0, 49, 0, 0), Qt.AlignCenter, self._mode)
