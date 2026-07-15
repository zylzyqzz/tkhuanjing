from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget


class FramelessWindow(QMainWindow):
    """Native-feeling frameless window with system move and resize support."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._resize_margin = 8
        self.setMouseTracking(True)

    def _edges_at(self, pos) -> Qt.Edges:
        edges = Qt.Edges()
        if pos.x() <= self._resize_margin:
            edges |= Qt.LeftEdge
        elif pos.x() >= self.width() - self._resize_margin:
            edges |= Qt.RightEdge
        if pos.y() <= self._resize_margin:
            edges |= Qt.TopEdge
        elif pos.y() >= self.height() - self._resize_margin:
            edges |= Qt.BottomEdge
        return edges

    def mouseMoveEvent(self, event) -> None:
        edges = self._edges_at(event.position().toPoint())
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeBDiagCursor)
        elif edges & (Qt.LeftEdge | Qt.RightEdge):
            self.setCursor(Qt.SizeHorCursor)
        elif edges & (Qt.TopEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            edges = self._edges_at(event.position().toPoint())
            if edges and self.windowHandle():
                self.windowHandle().startSystemResize(edges)
                event.accept()
                return
        super().mousePressEvent(event)


class TitleBar(QFrame):
    def __init__(self, window: QMainWindow, title: str, version: str) -> None:
        super().__init__()
        self.window = window
        self.setObjectName("titleBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 0, 8, 0)
        row.setSpacing(10)
        mark = QLabel("◇")
        mark.setObjectName("brandMark")
        row.addWidget(mark)
        name = QLabel(title)
        name.setObjectName("windowTitle")
        row.addWidget(name)
        version_label = QLabel(f"V{version}")
        version_label.setObjectName("versionPill")
        row.addWidget(version_label)
        row.addStretch()
        for symbol, tip, callback in (
            ("—", "最小化", window.showMinimized),
            ("□", "最大化/还原", self._toggle_max),
            ("×", "关闭", window.close),
        ):
            button = QPushButton(symbol)
            button.setObjectName("windowControl")
            button.setToolTip(tip)
            button.clicked.connect(callback)
            row.addWidget(button)

    def _toggle_max(self) -> None:
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.window.windowHandle():
            self.window.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._toggle_max()


class TechBackdrop(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.phase = 0
        self.reduced = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(45)

    def set_reduced(self, reduced: bool) -> None:
        self.reduced = reduced
        self.timer.setInterval(150 if reduced else 45)

    def _tick(self) -> None:
        if not self.window().isMinimized():
            self.phase = (self.phase + 1) % 1000
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#050A12"))
        radial = QLinearGradient(0, 0, self.width(), self.height())
        radial.setColorAt(0, QColor(7, 18, 35, 245))
        radial.setColorAt(.48, QColor(5, 12, 23, 248))
        radial.setColorAt(1, QColor(10, 8, 17, 250))
        painter.fillRect(self.rect(), radial)
        painter.setPen(QPen(QColor(70, 132, 214, 18), 1))
        spacing = 48
        offset = 0 if self.reduced else self.phase % spacing
        for x in range(-spacing + offset, self.width(), spacing):
            painter.drawLine(x, 0, x, self.height())
        for y in range(-spacing + offset, self.height(), spacing):
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(Qt.NoPen)
        count = 10 if self.reduced else 28
        for index in range(count):
            x = (index * 173 + self.phase * (1 + index % 3)) % max(self.width(), 1)
            y = (index * 97 + self.phase * .35) % max(self.height(), 1)
            painter.setBrush(QColor(70, 154, 255, 25 + index % 4 * 10))
            painter.drawEllipse(QPointF(x, y), 1.5 + index % 3, 1.5 + index % 3)


class ModeCard(QFrame):
    clicked = Signal()

    def __init__(self, icon: str, eyebrow: str, title: str, text: str, button_text: str, accent: str) -> None:
        super().__init__()
        self.accent = accent
        self.setProperty("modeCard", True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        box = QVBoxLayout(self)
        box.setContentsMargins(26, 24, 26, 24)
        box.setSpacing(10)
        top = QHBoxLayout()
        symbol = QLabel(icon)
        symbol.setObjectName("modeIcon")
        symbol.setStyleSheet(f"color:{accent};")
        top.addWidget(symbol)
        top.addStretch()
        tag = QLabel(eyebrow)
        tag.setObjectName("eyebrow")
        tag.setStyleSheet(f"color:{accent}; border-color:{accent};")
        top.addWidget(tag)
        box.addLayout(top)
        heading = QLabel(title)
        heading.setObjectName("modeTitle")
        box.addWidget(heading)
        desc = QLabel(text)
        desc.setWordWrap(True)
        desc.setObjectName("modeDescription")
        box.addWidget(desc)
        box.addStretch()
        button = QPushButton(button_text)
        button.setObjectName("modeButton")
        button.setStyleSheet(f"QPushButton{{background:{accent};}} QPushButton:hover{{background:{accent}; filter:brightness(1.15);}}")
        button.clicked.connect(self.clicked)
        box.addWidget(button)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self.accent)
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 24), 1))
        base_y = int(self.height() * .62)
        for index in range(5):
            y = base_y + index * 19
            painter.drawLine(int(self.width() * .43), y, self.width() - 42 - index * 7, y)
            painter.drawEllipse(QPointF(self.width() - 42 - index * 7, y), 2, 2)
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 25), 2))
        painter.drawEllipse(QPointF(self.width() * .78, self.height() * .40), 62, 62)
        painter.drawEllipse(QPointF(self.width() * .78, self.height() * .40), 40, 40)
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 14), 12))
        painter.drawArc(QRectF(self.width() * .78 - 71, self.height() * .40 - 71, 142, 142), 24 * 16, 104 * 16)


class ScanCore(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.phase = 0
        self.running = False
        self.result = ""
        self.reduced = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setMinimumSize(360, 360)

    def start(self) -> None:
        self.running = True
        self.result = ""
        self.timer.start(28 if not self.reduced else 90)
        self.update()

    def finish(self, result: str) -> None:
        self.running = False
        self.result = result
        self.timer.stop()
        self.update()

    def set_reduced(self, reduced: bool) -> None:
        self.reduced = reduced

    def _tick(self) -> None:
        self.phase = (self.phase + 2) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) * .38
        painter.setPen(QPen(QColor(65, 119, 190, 32), 1))
        for scale in (.38, .58, .78, 1.0):
            painter.drawEllipse(center, radius * scale, radius * scale)
        for angle in range(0, 360, 30):
            radians = math.radians(angle)
            painter.drawLine(center, QPointF(center.x() + math.cos(radians) * radius, center.y() + math.sin(radians) * radius))
        if self.running:
            sweep = QPainterPath(center)
            sweep.arcTo(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2), -self.phase, 42)
            sweep.lineTo(center)
            gradient = QColor(65, 164, 255, 68)
            painter.fillPath(sweep, gradient)
            painter.setPen(QPen(QColor(89, 188, 255, 165), 2))
            radians = math.radians(self.phase)
            painter.drawLine(center, QPointF(center.x() + math.cos(radians) * radius, center.y() - math.sin(radians) * radius))
            if not self.reduced:
                painter.setPen(Qt.NoPen)
                for index in range(18):
                    angle = math.radians(self.phase * (1 + index % 3) + index * 47)
                    orbit = radius * (.38 + (index % 4) * .16)
                    painter.setBrush(QColor(80, 174, 255, 80 + index % 3 * 45))
                    painter.drawEllipse(QPointF(center.x() + math.cos(angle) * orbit, center.y() + math.sin(angle) * orbit), 2 + index % 2, 2 + index % 2)
        accent = QColor("#4DAAFF")
        if self.result == "PASS": accent = QColor("#4EE0A1")
        if self.result == "WARNING": accent = QColor("#F2B45F")
        if self.result == "FAIL": accent = QColor("#FF6075")
        pulse = 1 + (.06 * math.sin(math.radians(self.phase * 3)) if self.running else 0)
        core = radius * .28 * pulse
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 75), 14))
        painter.drawRoundedRect(QRectF(center.x() - core, center.y() - core, core * 2, core * 2), 22, 22)
        painter.setPen(QPen(accent, 2))
        painter.setBrush(QColor(7, 21, 38, 245))
        painter.drawRoundedRect(QRectF(center.x() - core, center.y() - core, core * 2, core * 2), 22, 22)
        painter.setPen(QColor("#EAF4FF"))
        painter.drawText(QRectF(center.x() - core, center.y() - 16, core * 2, 32), Qt.AlignCenter, "检测中" if self.running else self.result or "READY")


class ModuleTile(QFrame):
    def __init__(self, icon: str, title: str) -> None:
        super().__init__()
        self.setProperty("moduleTile", True)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        self.icon = QLabel(icon)
        self.icon.setObjectName("moduleGlyph")
        row.addWidget(self.icon)
        self.title = QLabel(title)
        row.addWidget(self.title)
        row.addStretch()
        self.state = QLabel("等待")
        self.state.setObjectName("moduleState")
        row.addWidget(self.state)

    def set_state(self, state: str) -> None:
        self.setProperty("state", state)
        self.state.setText({"running": "检测中", "success": "完成", "warning": "风险", "fail": "异常", "unknown": "未知"}.get(state, "等待"))
        self.style().unpolish(self)
        self.style().polish(self)


class TerminalLog(QTextEdit):
    COLORS = {"info": "#69B8FF", "success": "#53DFA4", "pass": "#53DFA4", "warning": "#F1B966", "fail": "#FF6B7D", "unknown": "#8798AE", "fallback": "#A789FF"}

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("terminal")
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(400)

    def append_event(self, event) -> None:
        stamp = event.timestamp[11:19] if getattr(event, "timestamp", "") else "--:--:--"
        level = getattr(event, "level", "info")
        color = self.COLORS.get(level, self.COLORS["info"])
        message = getattr(event, "message", str(event))
        self.append(f'<span style="color:#5E728F">[{stamp}]</span> <span style="color:{color}">{message}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "--", unit: str = "") -> None:
        super().__init__()
        self.setProperty("metricCard", True)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 13, 16, 13)
        name = QLabel(label)
        name.setObjectName("metricLabel")
        box.addWidget(name)
        row = QHBoxLayout()
        self.value = QLabel(value)
        self.value.setObjectName("metricValue")
        row.addWidget(self.value)
        self.unit = QLabel(unit)
        self.unit.setObjectName("metricUnit")
        row.addWidget(self.unit)
        row.addStretch()
        box.addLayout(row)

    def set_value(self, value: str, unit: str | None = None) -> None:
        self.value.setText(value)
        if unit is not None:
            self.unit.setText(unit)
