from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget

from ...models import CheckReport, Status
from ..tokens import status_bg, status_color
from ..widgets.check_row import CheckRow


class ResultScreen(QWidget):
    repair_requested = Signal()
    launch_requested = Signal()
    recheck_requested = Signal()
    export_requested = Signal()
    upload_requested = Signal()
    history_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self); outer.setContentsMargins(28, 20, 28, 20)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); body = QWidget(); self.body = QVBoxLayout(body); self.scroll.setWidget(body); outer.addWidget(self.scroll)
        self.hero = QFrame(); self.hero.setProperty("card", True); hero_box = QVBoxLayout(self.hero); self.hero_title = QLabel("尚未检测"); self.hero_title.setProperty("title", True); hero_box.addWidget(self.hero_title); self.hero_text = QLabel("完成检测后生成结论"); self.hero_text.setWordWrap(True); hero_box.addWidget(self.hero_text); self.body.addWidget(self.hero)
        self.attention_title = QLabel("需要关注的项目"); self.attention_title.setProperty("subhead", True); self.body.addWidget(self.attention_title)
        self.attention = QVBoxLayout(); self.body.addLayout(self.attention)
        actions = QHBoxLayout(); self.primary = QPushButton("开始开播"); self.primary.setProperty("primary", True); self.primary.clicked.connect(self._primary); actions.addWidget(self.primary); self.recheck = QPushButton("重新检测"); self.recheck.clicked.connect(self.recheck_requested); actions.addWidget(self.recheck); export = QPushButton("导出"); export.clicked.connect(self.export_requested); actions.addWidget(export); upload=QPushButton("上传"); upload.clicked.connect(self.upload_requested); actions.addWidget(upload); history=QPushButton("历史"); history.clicked.connect(self.history_requested); actions.addWidget(history); actions.addStretch(); self.body.addLayout(actions)
        self.toggle = QToolButton(); self.toggle.setText("查看完整检测结果"); self.toggle.setCheckable(True); self.toggle.toggled.connect(self._toggle); self.body.addWidget(self.toggle)
        self.complete_widget = QWidget(); self.complete = QVBoxLayout(self.complete_widget); self.complete_widget.hide(); self.body.addWidget(self.complete_widget)
        self.reports = QVBoxLayout(); self.body.addLayout(self.reports); self.body.addStretch()
        self._needs_repair = False

    def _primary(self):
        self.repair_requested.emit() if self._needs_repair else self.launch_requested.emit()

    def _toggle(self, checked: bool):
        self.complete_widget.setVisible(checked); self.toggle.setText("收起完整检测结果" if checked else "查看完整检测结果")

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def set_report(self, report: CheckReport) -> None:
        self._clear(self.attention); self._clear(self.complete); self._clear(self.reports)
        self._needs_repair = report.blocking_count > 0
        incomplete = report.readiness_level == "INCOMPLETE"
        if incomplete:
            status, title, text = "UNKNOWN", "系统环境检测未完成", "暂时无法确认开播环境，请重新检测。"
        elif report.blocking_count:
            status, title, text = "FAIL", "需要修复系统环境", "发现影响开播的系统设置，一键修复后将自动复检。"
        elif report.readiness_level == "READY_WITH_RISK":
            status, title, text = "WARNING", "可以开播", "系统环境正常，网络或电脑性能存在建议项。"
        else:
            status, title, text = "PASS", "可以开播", "网络、系统环境和电脑性能已完成检测。"
        self.hero.setStyleSheet(f"QFrame{{background:{status_bg(status)};border:1px solid {status_color(status)};border-radius:10px}}")
        self.hero_title.setText(title); self.hero_text.setText(text); self.primary.setText("一键修复系统环境" if self._needs_repair else "开始开播"); self.primary.setEnabled(not incomplete)
        order = {"系统环境": 0, "网络环境": 1, "电脑性能": 2}
        issues = sorted((x for x in report.items if x.status in {Status.FAIL, Status.WARNING}), key=lambda x: order.get(x.category, 9))
        if not issues: self.attention.addWidget(QLabel("没有需要关注的项目"))
        for item in issues: self.attention.addWidget(CheckRow(item.title, item.diagnosis, item.status.value))
        for item in report.items: self.complete.addWidget(CheckRow(item.title, item.value, item.status.value))
        for category, heading in (("网络环境", "网络环境报告与建议"), ("电脑性能", "电脑性能说明与建议"), ("系统环境", "系统环境检查与修复记录")):
            card = QFrame(); card.setProperty("card", True); box = QVBoxLayout(card); label = QLabel(heading); label.setProperty("subhead", True); box.addWidget(label)
            rows = [x for x in report.items if x.category == category]
            summary = QLabel("\n".join(f"• {x.title}：{x.value}｜{x.diagnosis}" + (f"｜建议：{' / '.join(x.solutions)}" if x.solutions else "") for x in rows)); summary.setWordWrap(True); summary.setProperty("muted", True); box.addWidget(summary)
            if category == "系统环境" and report.repair_events:
                repairs = QLabel("修复记录：\n" + "\n".join(f"• {x.get('title','系统修复')}：{x.get('message','')}（{'成功' if x.get('ok') else '失败'}）" for x in report.repair_events)); repairs.setWordWrap(True); repairs.setProperty("muted", True); box.addWidget(repairs)
            self.reports.addWidget(card)
