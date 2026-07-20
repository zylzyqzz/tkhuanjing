from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..tokens import ACCENT, ACCENT_LIGHT, ANIM_BREATH, BTN_H_PRIMARY, BTN_W_PRIMARY
from ..widgets.region_selector import RegionSelector


class HomeScreen(QWidget):
    def __init__(self, region_id: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 30, 48, 30)
        layout.addStretch()
        self.shield = QLabel("✓")
        self.shield.setAlignment(Qt.AlignCenter)
        self.shield.setFixedSize(QSize(108, 108))
        self.shield.setStyleSheet(f"font-size:48px;font-weight:800;color:{ACCENT};background:{ACCENT_LIGHT};border-radius:54px")
        shield_row = QHBoxLayout(); shield_row.addStretch(); shield_row.addWidget(self.shield); shield_row.addStretch(); layout.addLayout(shield_row)
        title = QLabel("开播前环境检测")
        title.setAlignment(Qt.AlignCenter); title.setProperty("title", True); layout.addWidget(title)
        desc = QLabel("只检测网络环境、影响开播的系统环境和电脑性能")
        desc.setAlignment(Qt.AlignCenter); desc.setProperty("muted", True); layout.addWidget(desc)
        layout.addSpacing(18)
        region_row = QHBoxLayout(); region_row.addStretch(); region_row.addWidget(QLabel("目标地区")); self.region = RegionSelector(region_id); region_row.addWidget(self.region); region_row.addStretch(); layout.addLayout(region_row)
        layout.addSpacing(14)
        button_row = QHBoxLayout(); button_row.addStretch(); self.start_button = QPushButton("开始检测"); self.start_button.setProperty("primary", True); self.start_button.setFixedSize(BTN_W_PRIMARY, BTN_H_PRIMARY); button_row.addWidget(self.start_button); button_row.addStretch(); layout.addLayout(button_row)
        self.last_result = QLabel("上次检测：尚未检测"); self.last_result.setAlignment(Qt.AlignCenter); self.last_result.setProperty("muted", True); layout.addWidget(self.last_result)
        layout.addStretch()
        self._opacity = QGraphicsOpacityEffect(self.shield); self.shield.setGraphicsEffect(self._opacity)
        self._breath = QPropertyAnimation(self._opacity, b"opacity", self); self._breath.setDuration(ANIM_BREATH); self._breath.setStartValue(.58); self._breath.setEndValue(1.0); self._breath.setEasingCurve(QEasingCurve.InOutSine); self._breath.setLoopCount(-1); self._breath.start()

    def set_animation_active(self, active: bool) -> None:
        self._breath.resume() if active and self._breath.state() == QPropertyAnimation.Paused else self._breath.pause() if not active else None


from PySide6.QtCore import Qt
