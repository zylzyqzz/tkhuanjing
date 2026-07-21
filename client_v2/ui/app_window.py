from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
import uuid

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import APP_VERSION
from ..api import ApiError, ClientApi
from ..checks import CheckContext, DEFAULT_PROFILE, run_checks, system_checks
from ..events import CheckEvent
from ..errors import normalize_error
from ..live_studio import find_live_studio, launch_live_studio, live_studio_process_state
from ..models import CheckReport
from ..regions import get_region
from ..state import ClientState, StateMachine
from ..storage import QUEUE_FILE, REPORT_DIR, acknowledge_device_events, load_config, load_credentials, load_json, load_license, load_reports, load_user, pending_device_events, queue_device_event, queue_report, save_config, save_credentials, save_license, save_report, update_queued_report
from ..system_repair import RepairResult, run_system_repair
from ..updater import download_update, launch_helper
from .screens.home_screen import HomeScreen
from .screens.result_screen import ResultScreen
from .screens.scan_screen import ScanScreen
from .sidebar import Sidebar
from .title_bar import TitleBar
from .tokens import ANIM_SLOW, APP_STYLESHEET, WINDOW_H, WINDOW_W
from .account_dialog import AccountDialog
from .history_dialog import HistoryDialog
from .enterprise_binding_dialog import EnterpriseBindingDialog
from ..agent.heartbeat import flush_once as flush_v2_heartbeat


def _assets() -> Path:
    return Path(__file__).resolve().parents[2] / "assets"


class CheckWorker(QObject):
    progress = Signal(int, str); row = Signal(str, str, str); done = Signal(object); failed = Signal(str)
    def __init__(self, config: dict, system_only: bool = False):
        super().__init__(); self.config = dict(config); self.system_only = system_only; self.cancelled = threading.Event()

    @Slot()
    def run(self):
        try:
            region = get_region(self.config.get("target_region_id")); credentials=load_credentials(); api = ClientApi(self.config.get("api_base", ""), credentials.get("device_token", "")); profile = dict(DEFAULT_PROFILE); license_data=load_license(); online=False
            try:
                if not api.token:
                    registered=api.register(self.config,APP_VERSION); save_credentials(device_token=api.token); license_data.update(registered.get("license",{}))
                profile.update(api.profile())
                user=load_user(); authorized=api.authorize(str(uuid.uuid4()),user.get("token","")); license_data.update(authorized); license_data["lease_until"]=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(); save_license(license_data); online=True
            except ApiError:
                lease=license_data.get("lease_until","")
                try: valid=datetime.fromisoformat(lease)>datetime.now(timezone.utc)
                except (ValueError,TypeError): valid=False
                if not valid and license_data.get("tier")!="FREE": raise
            context = CheckContext(profile, region, self.config.get("target_host", "tk.aimj.xin"), api, _assets(), APP_VERSION, online, self.cancelled, self._event, None, self.config.get("test_mode", "standard"))
            items = system_checks(context) if self.system_only else run_checks(context, lambda p,t: self.progress.emit(p,t))
            if self.cancelled.is_set():
                self.failed.emit("检测已取消"); return
            report = CheckReport(self.config["device_id"], APP_VERSION, items, target_region_id=region.region_id, run_mode="system_recheck" if self.system_only else "daily_preflight")
            report.ip_profile = next((x.metrics for x in items if x.check_id == "network.public_ip"), {})
            report.network_snapshot = {x.check_id:x.metrics for x in items if x.check_id.startswith("network.")}; report.environment_snapshot = {x.check_id:x.metrics for x in items if x.check_id.startswith(("system.","environment."))}; report.device_snapshot = {x.check_id:x.metrics for x in items if x.check_id.startswith("performance.")}; report.finalize(); self.done.emit(report)
        except Exception as exc: self.failed.emit(normalize_error(exc).display())

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


class UpdateWorker(QObject):
    progress = Signal(int, str); done = Signal(object); failed = Signal(str)
    def __init__(self, manifest): super().__init__(); self.manifest=manifest; self.cancelled=threading.Event()
    @Slot()
    def run(self):
        try: self.done.emit(download_update(self.manifest,lambda p,t:self.progress.emit(p,t),self.cancelled.is_set))
        except Exception as exc: self.failed.emit(normalize_error(exc,"UPDATE_FAILED").display())


class AppWindow(QWidget):
    bootstrap_updated = Signal(dict)
    def __init__(self):
        super().__init__(); self.config = load_config(); self.report: CheckReport | None = None; self.thread: QThread | None = None; self.worker = None; self.repair_events = []; self.machine=StateMachine(ClientState.IDLE); self.update_thread=None; self.update_worker=None; self._heartbeat_running=False; self._v2_heartbeat_running=False; self._last_studio_state="unknown"
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window); self.setAttribute(Qt.WA_TranslucentBackground); self.setFixedSize(WINDOW_W, WINDOW_H); self.setStyleSheet(APP_STYLESHEET)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); chrome = QWidget(); chrome.setObjectName("chrome"); root.addWidget(chrome); shell = QVBoxLayout(chrome); shell.setContentsMargins(0,0,0,0); shell.setSpacing(0); shell.addWidget(TitleBar(self))
        middle = QHBoxLayout(); middle.setContentsMargins(0,0,0,0); middle.setSpacing(0); self.sidebar = Sidebar(); self.sidebar.selected.connect(self._navigate); middle.addWidget(self.sidebar)
        self.stack = QStackedWidget(); self.stack.setObjectName("content"); middle.addWidget(self.stack,1); shell.addLayout(middle,1)
        self.home = HomeScreen(self.config.get("target_region_id", "")); self.scan = ScanScreen(); self.result = ResultScreen(); self.room_page = self._current_room_page(); self.settings = self._settings_page(); self.about = self._about_page()
        for page in (self.home,self.scan,self.result,self.room_page,self.settings,self.about): self.stack.addWidget(page)
        self.home.start_button.clicked.connect(self.start_check); self.scan.cancel_requested.connect(self.cancel); self.result.recheck_requested.connect(self.start_check); self.result.repair_requested.connect(self.start_repair); self.result.launch_requested.connect(self.launch); self.result.export_requested.connect(self.export_report); self.result.upload_requested.connect(self.upload_report); self.result.history_requested.connect(self.open_history)
        history = load_reports(1)
        if history: self.home.last_result.setText(f"上次检测：{history[0].get('conclusion','已完成')}")
        QTimer.singleShot(2500,self._retry_upload_queue)
        self.heartbeat_timer=QTimer(self); self.heartbeat_timer.setInterval(30000); self.heartbeat_timer.timeout.connect(self._heartbeat); self.heartbeat_timer.start(); QTimer.singleShot(3500,self._heartbeat)
        self.v2_heartbeat_timer=QTimer(self); self.v2_heartbeat_timer.setInterval(20000); self.v2_heartbeat_timer.timeout.connect(self._v2_heartbeat); self.v2_heartbeat_timer.start(); QTimer.singleShot(5000,self._v2_heartbeat)
        self.bootstrap_updated.connect(self._apply_device_bootstrap)

    def _current_room_page(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(40,30,40,30);title=QLabel("当前直播间");title.setProperty("title",True);layout.addWidget(title);hint=QLabel("查看这台电脑所属的企业、直播间、TikTok 账号和主播。");hint.setProperty("muted",True);layout.addWidget(hint);card=QFrame();card.setProperty("card",True);box=QVBoxLayout(card);self.room_status=QLabel("正在同步当前绑定……");self.room_status.setWordWrap(True);box.addWidget(self.room_status);open_button=QPushButton("设置或更换当前直播间");open_button.setProperty("primary",True);open_button.clicked.connect(self._open_enterprise_binding);box.addWidget(open_button);impact=QLabel("更换绑定只影响之后的新数据，历史检测和直播数据不会修改。");impact.setProperty("muted",True);impact.setWordWrap(True);box.addWidget(impact);layout.addWidget(card);layout.addStretch();return page

    def _settings_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(40,24,40,24); title = QLabel("帮助与诊断"); title.setProperty("title",True); layout.addWidget(title)
        account=QFrame(); account.setProperty("card",True); account_form=QFormLayout(account); user=load_user(); self.account_status=QLabel("已登录" if user.get("logged_in") else "未登录"); account_form.addRow("账号状态",self.account_status); login=QPushButton("打开账号中心"); login.clicked.connect(self._open_account); account_form.addRow("",login); layout.addWidget(account)
        card=QFrame(); card.setProperty("card",True); form=QFormLayout(card); self.live_path=QLineEdit(self.config.get("live_studio_path","")); form.addRow("TikTok LIVE Studio 路径",self.live_path); find=QPushButton("自动查找"); find.clicked.connect(self._find_live); form.addRow("",find); self.enterprise_code=QLineEdit(); self.enterprise_code.setPlaceholderText("旧版6位设备绑定码（兼容）"); form.addRow("旧版设备接入",self.enterprise_code); bind=QPushButton("兼容绑定"); bind.clicked.connect(self._bind_enterprise); form.addRow("",bind); update=QPushButton("检查软件更新"); update.clicked.connect(self.check_update); form.addRow("",update); save=QPushButton("保存诊断设置"); save.setProperty("primary",True); save.clicked.connect(self._save_settings); form.addRow("",save); layout.addWidget(card); layout.addStretch(); return page

    def _about_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(40,32,40,32); title=QLabel("关于 VD Nexus"); title.setProperty("title",True); layout.addWidget(title); card=QFrame(); card.setProperty("card",True); box=QVBoxLayout(card); text=QLabel(f"VD开播助手 V{APP_VERSION}\n\n面向 TikTok 直播的网络环境、系统环境和电脑性能检测工具。\n\n不读取账号密码、Cookie、个人文件或直播素材；缓存清理仅处理白名单临时目录。"); text.setWordWrap(True); box.addWidget(text); layout.addWidget(card); layout.addStretch(); return page

    def _navigate(self, page: str):
        if page == "home": self.stack.setCurrentWidget(self.home)
        elif page == "room": self.stack.setCurrentWidget(self.room_page)
        elif page == "device": self.stack.setCurrentWidget(self.result)
        else: self.stack.setCurrentWidget(self.settings)

    def start_check(self):
        if self.machine.busy or (self.thread and self.thread.isRunning()): return
        if self.machine.state not in {ClientState.IDLE,ClientState.READY,ClientState.CHECKED,ClientState.NEEDS_REPAIR,ClientState.FAILED,ClientState.CANCELLED}: self.machine=StateMachine(ClientState.IDLE)
        self.machine.transition(ClientState.CHECKING); self._apply_state()
        self._send_event("check_started")
        self.config["target_region_id"] = self.home.region.currentData(); save_config(self.config); self.scan.reset(False); self.stack.setCurrentWidget(self.scan); self._run_worker(CheckWorker(self.config), self._check_done)

    def start_repair(self):
        if self.machine.busy or (self.thread and self.thread.isRunning()): return
        self.machine.transition(ClientState.REPAIRING); self._apply_state()
        self._send_event("repair_started")
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
        target=ClientState.NEEDS_REPAIR if report.blocking_count else ClientState.READY if report.readiness_level!="INCOMPLETE" else ClientState.FAILED
        if self.machine.state in {ClientState.CHECKING,ClientState.RECHECKING}: self.machine.transition(target)
        self._apply_state(); self.report=report; save_report(report.to_dict()); self.result.set_report(report); self.home.last_result.setText(f"上次检测：{datetime.now().strftime('%Y-%m-%d %H:%M')} · {report.conclusion}"); QTimer.singleShot(ANIM_SLOW,self._show_result)

    def _repair_done(self, results):
        self.repair_events=[x.to_dict() for x in results]; self.machine.transition(ClientState.RECHECKING); self._apply_state(); self.scan.update_progress(100,"修复完成，正在复检系统环境…",True); QTimer.singleShot(120, self._start_system_recheck)

    def _start_system_recheck(self):
        if self.thread and self.thread.isRunning():
            QTimer.singleShot(120, self._start_system_recheck)
            return
        self._run_worker(CheckWorker(self.config, True), self._check_done)

    def _show_result(self): self.stack.setCurrentWidget(self.result); self.sidebar.select("device")
    def _failed(self,message):
        cancelled="已取消" in message; self.machine.transition(ClientState.CANCELLED if cancelled else ClientState.FAILED); self._apply_state(); self._send_event("check_failed", "warning", {"message": message[:300]}) if not cancelled else None; QMessageBox.information(self,"已取消",message) if cancelled else QMessageBox.critical(self,"操作未完成",message); self.stack.setCurrentWidget(self.home)
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

    def upload_report(self):
        if not self.report: return
        try:
            credentials=load_credentials(); api=ClientApi(self.config["api_base"],credentials.get("device_token","")); api.upload_report(self.report.to_dict()); update_queued_report(self.report.report_id,success=True); QMessageBox.information(self,"上传完成","报告已上传")
        except Exception as exc:
            queue_report(self.report.report_id,str(exc)); update_queued_report(self.report.report_id,success=False,error=str(exc)); QMessageBox.warning(self,"已加入待同步队列","当前无法上传，报告已保存到本机。")

    def _retry_upload_queue(self):
        credentials=load_credentials()
        if not credentials.get("device_token"): return
        for item in load_json(QUEUE_FILE,[]):
            entry={"report_id":item,"attempts":0} if isinstance(item,str) else item; report=load_json(REPORT_DIR/f"{entry.get('report_id','')}.json",{})
            if not report or int(entry.get("attempts",0))>=8: continue
            try: ClientApi(self.config["api_base"],credentials["device_token"]).upload_report(report); update_queued_report(entry["report_id"],success=True)
            except Exception as exc: update_queued_report(entry["report_id"],success=False,error=str(exc))

    def open_history(self):
        dialog=HistoryDialog(self)
        def selected(value): self.report=CheckReport.from_dict(value); self.result.set_report(self.report)
        dialog.report_selected.connect(selected); dialog.exec()

    def check_update(self):
        try:
            data=ClientApi(self.config["api_base"]).update_info()
            if not data.get("available") or data.get("version")==APP_VERSION: QMessageBox.information(self,"版本检查",f"当前已是最新版本 V{APP_VERSION}"); return
            if QMessageBox.question(self,"发现新版本",f"V{data.get('version')}\n\n{data.get('notes','')}\n\n是否验证签名并下载安装？")!=QMessageBox.Yes: return
            self.update_thread=QThread(self); self.update_worker=UpdateWorker(data); self.update_worker.moveToThread(self.update_thread); self.update_thread.started.connect(self.update_worker.run); self.update_worker.progress.connect(lambda p,t:self.home.last_result.setText(t)); self.update_worker.done.connect(self._update_downloaded); self.update_worker.done.connect(self.update_thread.quit); self.update_worker.failed.connect(lambda m:QMessageBox.warning(self,"更新失败",m)); self.update_worker.failed.connect(self.update_thread.quit); self.update_thread.finished.connect(self.update_worker.deleteLater); self.update_thread.start()
        except Exception as exc: QMessageBox.warning(self,"检查更新失败",normalize_error(exc).display())

    def _update_downloaded(self,path):
        try: launch_helper(path); self.close()
        except Exception as exc: QMessageBox.warning(self,"更新失败",normalize_error(exc).display())

    def _find_live(self):
        path=find_live_studio(self.live_path.text()); self.live_path.setText(str(path) if path else ""); QMessageBox.information(self,"自动查找",f"已找到：{path}" if path else "未找到 TikTok LIVE Studio")
    def _save_settings(self): self.config["live_studio_path"]=self.live_path.text().strip(); save_config(self.config); QMessageBox.information(self,"设置","已保存")
    def _bind_enterprise(self):
        code=self.enterprise_code.text().strip()
        if not code: return
        try:
            credentials=load_credentials(); api=ClientApi(self.config["api_base"],credentials.get("device_token",""))
            if not api.token:
                api.register(self.config,APP_VERSION); save_credentials(device_token=api.token)
            result=api.bind_enterprise(code); self.enterprise_code.clear(); QMessageBox.information(self,"绑定成功",f"已加入企业：{result['tenant']['name']}"); self._heartbeat()
        except Exception as exc: QMessageBox.warning(self,"绑定失败",normalize_error(exc).display())

    def _open_enterprise_binding(self): EnterpriseBindingDialog(self).exec(); self._v2_heartbeat()

    def _v2_heartbeat(self):
        if self._v2_heartbeat_running: return
        self._v2_heartbeat_running=True
        threading.Thread(target=self._flush_v2_safely,daemon=True,name="v2-device-heartbeat").start()

    def _flush_v2_safely(self):
        try:
            result=flush_v2_heartbeat();bootstrap=result.get("bootstrap",{})
            if bootstrap:self.bootstrap_updated.emit(bootstrap)
        except Exception: pass
        finally: self._v2_heartbeat_running=False

    @Slot(dict)
    def _apply_device_bootstrap(self,bootstrap):
        config=bootstrap.get("config",{});interval=max(10,int(config.get("heartbeat_interval_seconds",20)));self.v2_heartbeat_timer.setInterval(interval*1000);self.sidebar.apply_features(bootstrap.get("features",{}));binding=bootstrap.get("binding");organization=bootstrap.get("organization",{})
        self.room_status.setText(f"企业：{organization.get('name','-')}\n当前直播间已绑定，状态将在 {interval} 秒内同步。" if binding else f"企业：{organization.get('name','-')}\n这台电脑尚未选择直播间。")
        minimum=bootstrap.get("minimum_version","")
        if minimum and tuple(int(x) for x in minimum.split('.')[:3])>tuple(int(x) for x in APP_VERSION.split('.')[:3]):self.room_status.setText(self.room_status.text()+f"\n客户端需要升级到 V{minimum} 或更高版本。")

    def _presence_payload(self):
        state_map={ClientState.CHECKING:"checking",ClientState.REPAIRING:"repairing",ClientState.RECHECKING:"rechecking",ClientState.READY:"ready",ClientState.NEEDS_REPAIR:"risk",ClientState.FAILED:"failed"}
        readiness="unknown"
        if self.report: readiness="blocked" if self.report.blocking_count else "incomplete" if self.report.readiness_level=="INCOMPLETE" else "warning" if self.report.high_risk_count else "ready"
        summary={}
        if self.report:
            for category,prefix in (("network","network."),("system",("system.","environment.")),("performance","performance.")):
                prefixes=(prefix,) if isinstance(prefix,str) else prefix; items=[x for x in self.report.items if x.check_id.startswith(prefixes)]; statuses=[x.status for x in items]; status="FAIL" if "FAIL" in statuses else "WARNING" if "WARNING" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"; summary[category]={"status":status,"issues":sum(x in {"FAIL","WARNING"} for x in statuses)}
        return {"client_at":datetime.now(timezone.utc).isoformat(),"app_version":APP_VERSION,"live_state":state_map.get(self.machine.state,"idle"),"readiness_state":readiness,"studio_state":live_studio_process_state(),"target_region_id":self.config.get("target_region_id",""),"last_report_id":self.report.report_id if self.report else None,"last_report_at":self.report.checked_at if self.report else None,"module_summary":summary}

    def _heartbeat(self):
        if self._heartbeat_running: return
        credentials=load_credentials()
        if not credentials.get("device_token"): return
        self._heartbeat_running=True
        def send():
            try:
                api=ClientApi(self.config["api_base"],credentials["device_token"]); payload=self._presence_payload(); api.heartbeat(payload)
                pending=pending_device_events()
                if pending:
                    clean=[{k:v for k,v in item.items() if k!="attempts"} for item in pending]; result=api.upload_events(clean); acknowledge_device_events(result.get("accepted",[]))
                studio=payload["studio_state"]
                if studio!=self._last_studio_state and self._last_studio_state!="unknown": self._send_event("studio_started" if studio=="running" else "studio_stopped")
                self._last_studio_state=studio
            except Exception: pass
            finally: self._heartbeat_running=False
        threading.Thread(target=send,daemon=True,name="enterprise-heartbeat").start()

    def _send_event(self,event_type,severity="info",payload=None):
        credentials=load_credentials()
        if not credentials.get("device_token"): return
        event={"event_id":str(uuid.uuid4()),"event_type":event_type,"severity":severity,"client_at":datetime.now(timezone.utc).isoformat(),"payload":payload or {}}
        queue_device_event(event)
        def send():
            try:
                result=ClientApi(self.config["api_base"],credentials["device_token"]).upload_events([event]); acknowledge_device_events(result.get("accepted",[]))
            except Exception: pass
        threading.Thread(target=send,daemon=True,name="enterprise-event").start()
    def _open_account(self):
        dialog=AccountDialog(self); dialog.session_changed.connect(lambda user:self.account_status.setText("已登录" if user.get("logged_in") else "未登录")); dialog.exec()
    def _apply_state(self):
        busy=self.machine.busy; self.home.start_button.setEnabled(not busy); self.result.primary.setEnabled(not busy and self.machine.state not in {ClientState.FAILED,ClientState.CANCELLED}); self.scan.cancel_button.setEnabled(busy)
    def hideEvent(self,event): self.home.set_animation_active(False); super().hideEvent(event)
    def showEvent(self,event): self.home.set_animation_active(True); super().showEvent(event)
    def closeEvent(self,event):
        if self.worker and hasattr(self.worker,"cancelled"): self.worker.cancelled.set()
        if self.thread and self.thread.isRunning(): self.thread.quit(); self.thread.wait(1500)
        if self.update_worker: self.update_worker.cancelled.set()
        if self.update_thread and self.update_thread.isRunning(): self.update_thread.quit(); self.update_thread.wait(1500)
        super().closeEvent(event)
