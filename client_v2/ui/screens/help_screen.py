from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class HelpScreen(QWidget):
    open_logs_requested = Signal()
    copy_diagnostics_requested = Signal()
    sync_requested = Signal()
    update_requested = Signal()
    account_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 28, 40, 28)
        title = QLabel("帮助与诊断")
        title.setProperty("title", True)
        layout.addWidget(title)
        note = QLabel("遇到问题时可导出不含密码、Cookie 和直播素材的诊断信息。")
        note.setProperty("muted", True)
        layout.addWidget(note)

        card = QFrame()
        card.setProperty("card", True)
        grid = QGridLayout(card)
        actions = (
            ("打开日志目录", self.open_logs_requested),
            ("复制诊断信息", self.copy_diagnostics_requested),
            ("重新同步企业配置", self.sync_requested),
            ("检查软件更新", self.update_requested),
            ("打开账号中心", self.account_requested),
        )
        for index, (text, signal) in enumerate(actions):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            grid.addWidget(button, index // 2, index % 2)
        layout.addWidget(card)

        support = QFrame()
        support.setProperty("card", True)
        box = QVBoxLayout(support)
        heading = QLabel("客服与隐私说明")
        heading.setProperty("subhead", True)
        text = QLabel(
            "联系客服时请提供诊断编号、客户端版本和问题发生时间。\n\n"
            "VD Nexus 只上报设备在线状态、环境检测摘要、LIVE Studio 进程状态和轻量性能指标；"
            "不读取 TikTok 密码、Cookie、浏览器会话、直播画面或个人素材。"
        )
        text.setWordWrap(True)
        box.addWidget(heading)
        box.addWidget(text)
        layout.addWidget(support)
        self.feedback = QLabel("准备就绪")
        self.feedback.setProperty("muted", True)
        layout.addWidget(self.feedback)
        layout.addStretch()

    def show_feedback(self, text: str) -> None:
        self.feedback.setText(text)
