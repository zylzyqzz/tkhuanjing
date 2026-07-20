from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import threading

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import APP_VERSION
from ..api import ClientApi
from ..checks import CheckContext, DEFAULT_PROFILE, run_checks, system_checks
from ..events import CheckEvent
from ..live_studio import find_live_studio, launch_live_studio
from ..models import CheckReport
from ..regions import get_region
from ..storage import clear_user_session, load_config, load_reports, load_user, save_config, save_report, set_user_session
from ..system_repair import RepairResult, run_system_repair
from .screens.home_screen import HomeScreen
from .screens.result_screen import ResultScreen
from .screens.scan_screen import ScanScreen
from .sidebar import Sidebar
from .title_bar import TitleBar
from .tokens import ANIM_SLOW, APP_STYLESHEET, WINDOW_H, WINDOW_W


def _assets() -> Path:
    return Path(__file__).resolve().parents[2] / "assets"


class CheckWorker(QObject):
    progress = Signal(int, str); row = Signal(str, str, str); done = Signal(object); failed = Signal(str)
    def __init__(self, config: dict, system_only: bool = False):
        super().__init__(); self.config = dict(config); self.system_only = system_only; self.cancelled = threading.Event()

    @Slot()
    def run(self):
        try:
            region = get_region(self.config.get("target_region_id")); api = ClientApi(self.config.get("api_base", ""), self.config.get("device_token", "")); profile = dict(DEFAULT_PROFILE)
            context = CheckContext(profile, region, self.config.get("target_host", "tk.aimj.xin"), api, _assets(), APP_VERSION, False, self.cancelled, self._event, None, self.config.get("test_mode", "standard"))
            items = system_checks(context) if self.system_only else run_checks(context, lambda p,t: self.progress.emit(p,t))
            report = CheckReport(self.config["device_id"], APP_VERSION, items, target_region_id=region.region_id, run_mode="system_recheck" if self.system_only else "daily_preflight")
            report.ip_profile = next((x.metrics for x in items if x.check_id == "network.public_ip"), {})
            report.network_snapshot = {x.check_id:x.metrics for x in items if x.check_id.startswith("network.")}; report.environment_snapshot = {x.check_id:x.metrics for x in items if x.check_id.startswith(("system.","environment."))}; report.device_snapshot = {x.check_id:x.metrics for x in items if x.check_id.startswith("performance.")}; report.finalize(); self.done.emit(report)
        except Exception as exc: self.failed.emit(str(exc))

    def _event(self, event: CheckEvent):
        if event.event == "check_result": self.row.emit(event.message.split("：",1)[0], event.message.split("：",1)[-1], event.level.upper())


class RepairWorker(QObject):
    progress = Signal(int, str); row = Signal(str, str, str); done = Signal(object); failed = Signal(str)
    def __init__(self, region): super().__init__(); self.region = region; self.cancelled = threading.Event()
    @Slot()
    def run(self):
        try: self.done.emit(run_system_repair(self.region, self._progress, self.cancelled))
        except Exception as exc: self.failed.emit(str(exc))
    def _progress(self, value: int, title: str, result: RepairResult | None):
        self.progress.emit(value, title)
        if result: self.row.emit(result.title, result.message, "PASS" if result.ok else "FAIL")


class AppWindow(QWidget):
    def __init__(self):
        super().__init__(); self.config = load_config(); self.report: CheckReport | None = None; self.thread: QThread | None = None; self.worker = None; self.repair_events = []
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window); self.setAttribute(Qt.WA_TranslucentBackground); self.setFixedSize(WINDOW_W, WINDOW_H); self.setStyleSheet(APP_STYLESHEET)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); chrome = QWidget(); chrome.setObjectName("chrome"); root.addWidget(chrome); shell = QVBoxLayout(chrome); shell.setContentsMargins(0,0,0,0); shell.setSpacing(0); shell.addWidget(TitleBar(self))
        middle = QHBoxLayout(); middle.setContentsMargins(0,0,0,0); middle.setSpacing(0); self.sidebar = Sidebar(); self.sidebar.selected.connect(self._navigate); middle.addWidget(self.sidebar)
        self.stack = QStackedWidget(); self.stack.setObjectName("content"); middle.addWidget(self.stack,1); shell.addLayout(middle,1)
        self.home = HomeScreen(self.config.get("target_region_id", "")); self.scan = ScanScreen(); self.result = ResultScreen(); self.settings = self._settings_page(); self.about = self._about_page()
        for page in (self.home,self.scan,self.result,self.settings,self.about): self.stack.addWidget(page)
        self.home.start_button.clicked.connect(self.start_check); self.scan.cancel_requested.connect(self.cancel); self.result.recheck_requested.connect(self.start_check); self.result.repair_requested.connect(self.start_repair); self.result.launch_requested.connect(self.launch); self.result.export_requested.connect(self.export_report)
        history = load_reports(1)
        if history: self.home.last_result.setText(f"上次检测：{history[0].get('conclusion','已完成')}")

    def _settings_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(40,24,40,24); title = QLabel("设置"); title.setProperty("title",True); layout.addWidget(title)
        account=QFrame(); account.setProperty("card",True); account_form=QFormLayout(account); user=load_user(); self.account_status=QLabel("已登录" if user.get("logged_in") else "未登录"); account_form.addRow("账号状态",self.account_status); self.phone=QLineEdit(); self.phone.setPlaceholderText("手机号"); account_form.addRow("手机号",self.phone); self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.Password); self.password.setPlaceholderText("密码"); account_form.addRow("密码",self.password); login=QPushButton("登录 / 退出"); login.clicked.connect(self._toggle_login); account_form.addRow("",login); layout.addWidget(account)
        card=QFrame(); card.setProperty("card",True); form=QFormLayout(card); self.live_path=QLineEdit(self.config.get("live_studio_path","")); form.addRow("TikTok LIVE Studio 路径",self.live_path); find=QPushButton("自动查找"); find.clicked.connect(self._find_live); form.addRow("",find); save=QPushButton("保存设置"); save.setProperty("primary",True); save.clicked.connect(self._save_settings); form.addRow("",save); layout.addWidget(card); layout.addStretch(); return page

    def _about_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(40,32,40,32); title=QLabel("关于 VD Nexus"); title.setProperty("title",True); layout.addWidget(title); card=QFrame(); card.setProperty("card",True); box=QVBoxLayout(card); text=QLabel(f"VD开播助手 V{APP_VERSION}\n\n面向 TikTok 直播的网络环境、系统环境和电脑性能检测工具。\n\n不读取账号密码、Cookie、个人文件或直播素材；缓存清理仅处理白名单临时目录。"); text.setWordWrap(True); box.addWidget(text); layout.addWidget(card); layout.addStretch(); return page

    def _navigate(self, page: str):
        if page == "home": self.stack.setCurrentWidget(self.home)
        elif page == "report": self.stack.setCurrentWidget(self.result)
        elif page == "settings": self.stack.setCurrentWidget(self.settings)
        else: self.stack.setCurrentWidget(self.about)

    def start_check(self):
        if self.thread and self.thread.isRunning(): return
        self.config["target_region_id"] = self.home.region.currentData(); save_config(self.config); self.scan.reset(False); self.stack.setCurrentWidget(self.scan); self._run_worker(CheckWorker(self.config), self._check_done)

    def start_repair(self):
        if self.thread and self.thread.isRunning(): return
        self.scan.reset(True); self.stack.setCurrentWidget(self.scan); self._run_worker(RepairWorker(get_region(self.config.get("target_region_id"))), self._repair_done)

    def _run_worker(self, worker, done):
        self.thread=QThread(self); self.worker=worker; worker.moveToThread(self.thread); self.thread.started.connect(worker.run); worker.progress.connect(lambda p,t:self.scan.update_progress(p,t,isinstance(worker,RepairWorker))); worker.row.connect(self.scan.add_result); worker.done.connect(done); worker.done.connect(self.thread.quit); worker.failed.connect(self._failed); worker.failed.connect(self.thread.quit); self.thread.finished.connect(worker.deleteLater); self.thread.start()

    def _check_done(self, report: CheckReport):
        if report.run_mode == "system_recheck" and self.report:
            retained = [x for x in self.report.items if not x.check_id.startswith(("system.", "environment."))]
            report.items = retained + report.items
            report.run_mode = "daily_preflight"
            report.ip_profile = self.report.ip_profile
            report.network_snapshot = self.report.network_snapshot
            report.device_snapshot = self.report.device_snapshot
            report.finalize()
        if self.repair_events: report.repair_events=list(self.repair_events)
        self.report=report; save_report(report.to_dict()); self.result.set_report(report); self.home.last_result.setText(f"上次检测：{datetime.now().strftime('%Y-%m-%d %H:%M')} · {report.conclusion}"); QTimer.singleShot(ANIM_SLOW,self._show_result)

    def _repair_done(self, results):
        self.repair_events=[x.to_dict() for x in results]; self.scan.update_progress(100,"修复完成，正在复检系统环境…",True); QTimer.singleShot(120, self._start_system_recheck)

    def _start_system_recheck(self):
        if self.thread and self.thread.isRunning():
            QTimer.singleShot(120, self._start_system_recheck)
            return
        self._run_worker(CheckWorker(self.config, True), self._check_done)

    def _show_result(self): self.stack.setCurrentWidget(self.result); self.sidebar.select("report")
    def _failed(self,message): QMessageBox.critical(self,"操作未完成",message); self.stack.setCurrentWidget(self.home)
    def cancel(self):
        if self.worker and hasattr(self.worker,"cancelled"): self.worker.cancelled.set()

    def launch(self):
        try:
            path=launch_live_studio(self.config.get("live_studio_path","")); self.config["live_studio_path"]=str(path); save_config(self.config)
        except FileNotFoundError:
            path,_=QFileDialog.getOpenFileName(self,"选择 TikTok LIVE Studio 程序","","Programs (*.exe)")
            if path: self.config["live_studio_path"]=path; save_config(self.config); launch_live_studio(path)

    def export_report(self):
        if not self.report: return
        path,_=QFileDialog.getSaveFileName(self,"导出检测报告",f"VD-Nexus-{self.report.report_id}.json","JSON (*.json)")
        if path: Path(path).write_text(json.dumps(self.report.to_dict(),ensure_ascii=False,indent=2),encoding="utf-8")

    def _find_live(self):
        path=find_live_studio(self.live_path.text()); self.live_path.setText(str(path) if path else ""); QMessageBox.information(self,"自动查找",f"已找到：{path}" if path else "未找到 TikTok LIVE Studio")
    def _save_settings(self): self.config["live_studio_path"]=self.live_path.text().strip(); save_config(self.config); QMessageBox.information(self,"设置","已保存")
    def _toggle_login(self):
        if load_user().get("logged_in"):
            clear_user_session(); self.account_status.setText("未登录"); return
        try:
            api=ClientApi(self.config.get("api_base","")); data=api.auth_login(self.phone.text().strip(),self.password.text()); set_user_session(data["token"],data.get("profile",{})); self.account_status.setText("已登录"); self.password.clear()
        except Exception as exc: QMessageBox.warning(self,"登录失败",str(exc))
    def hideEvent(self,event): self.home.set_animation_active(False); super().hideEvent(event)
    def showEvent(self,event): self.home.set_animation_active(True); super().showEvent(event)
    def closeEvent(self,event):
        if self.worker and hasattr(self.worker,"cancelled"): self.worker.cancelled.set()
        if self.thread and self.thread.isRunning(): self.thread.quit(); self.thread.wait(1500)
        super().closeEvent(event)
