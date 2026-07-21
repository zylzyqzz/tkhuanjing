from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
import uuid

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import APP_VERSION
from ..api import ApiError, ClientApi
from ..checks import CheckContext, DEFAULT_PROFILE, run_checks, system_checks
from ..events import CheckEvent
from ..errors import normalize_error
from ..live_studio import find_live_studio, launch_live_studio, live_studio_process_state
from ..models import CheckReport
from ..regions import get_region
from ..state import ClientState, StateMachine
from ..storage import DATA_DIR, QUEUE_FILE, REPORT_DIR, acknowledge_device_events, configure_logging, load_config, load_credentials, load_json, load_license, load_reports, pending_device_events, queue_device_event, queue_report, save_config, save_credentials, save_license, save_report, update_queued_report
from ..system_repair import RepairResult, run_system_repair
from ..updater import download_update, launch_helper
from .screens.home_screen import HomeScreen
from .screens.result_screen import ResultScreen
from .screens.scan_screen import ScanScreen
from .screens.device_status_screen import DeviceStatusScreen
from .screens.help_screen import HelpScreen
from .sidebar import Sidebar
from .title_bar import TitleBar
from .tokens import ANIM_SLOW, APP_STYLESHEET, WINDOW_H, WINDOW_W
from .account_dialog import AccountDialog
from .history_dialog import HistoryDialog
from .enterprise_binding_dialog import EnterpriseBindingDialog
from ..agent.heartbeat import flush_once as flush_v2_heartbeat, payload as v2_heartbeat_payload


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
    device_sync_completed = Signal(dict)
    device_sync_failed = Signal(str)
    def __init__(self):
        super().__init__(); self.config = load_config(); self.report: CheckReport | None = None; self.thread: QThread | None = None; self.worker = None; self.repair_events = []; self.machine=StateMachine(ClientState.IDLE); self.update_thread=None; self.update_worker=None; self._heartbeat_running=False; self._v2_heartbeat_running=False; self._last_studio_state="unknown"; self._device_bootstrap={}; self._last_device_sync={}; self._logger=configure_logging()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window); self.setAttribute(Qt.WA_TranslucentBackground); self.setFixedSize(WINDOW_W, WINDOW_H); self.setStyleSheet(APP_STYLESHEET)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); chrome = QWidget(); chrome.setObjectName("chrome"); root.addWidget(chrome); shell = QVBoxLayout(chrome); shell.setContentsMargins(0,0,0,0); shell.setSpacing(0); shell.addWidget(TitleBar(self))
        middle = QHBoxLayout(); middle.setContentsMargins(0,0,0,0); middle.setSpacing(0); self.sidebar = Sidebar(); self.sidebar.selected.connect(self._navigate); middle.addWidget(self.sidebar)
        self.stack = QStackedWidget(); self.stack.setObjectName("content"); middle.addWidget(self.stack,1); shell.addLayout(middle,1)
        self.home = HomeScreen(self.config.get("target_region_id", "")); self.scan = ScanScreen(); self.result = ResultScreen(); self.room_page = self._current_room_page(); self.device_page = DeviceStatusScreen(); self.help_page = HelpScreen()
        for page in (self.home,self.scan,self.result,self.room_page,self.device_page,self.help_page): self.stack.addWidget(page)
        self.home.start_button.clicked.connect(self.start_check); self.scan.cancel_requested.connect(self.cancel); self.result.recheck_requested.connect(self.start_check); self.result.repair_requested.connect(self.start_repair); self.result.launch_requested.connect(self.launch); self.result.export_requested.connect(self.export_report); self.result.upload_requested.connect(self.upload_report); self.result.history_requested.connect(self.open_history)
        history = load_reports(1)
        if history: self.home.last_result.setText(f"上次检测：{history[0].get('conclusion','已完成')}")
        QTimer.singleShot(2500,self._retry_upload_queue)
        self.heartbeat_timer=QTimer(self); self.heartbeat_timer.setInterval(30000); self.heartbeat_timer.timeout.connect(self._heartbeat); self.heartbeat_timer.start(); QTimer.singleShot(3500,self._heartbeat)
        self.v2_heartbeat_timer=QTimer(self); self.v2_heartbeat_timer.setInterval(20000); self.v2_heartbeat_timer.timeout.connect(self._v2_heartbeat); self.v2_heartbeat_timer.start(); QTimer.singleShot(5000,self._v2_heartbeat)
        self.bootstrap_updated.connect(self._apply_device_bootstrap)
        self.device_sync_completed.connect(self._device_sync_done)
        self.device_sync_failed.connect(self.device_page.set_error)
        self.device_page.sync_requested.connect(self._manual_sync)
        self.help_page.open_logs_requested.connect(self._open_logs)
        self.help_page.copy_diagnostics_requested.connect(self._copy_diagnostics)
        self.help_page.sync_requested.connect(self._manual_sync)
        self.help_page.update_requested.connect(self.check_update)
        self.help_page.account_requested.connect(self._open_account)

    def _current_room_page(self):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(40,30,40,30);title=QLabel("当前直播间");title.setProperty("title",True);layout.addWidget(title);hint=QLabel("查看这台电脑所属的企业、直播间、TikTok 账号和主播。");hint.setProperty("muted",True);layout.addWidget(hint);card=QFrame();card.setProperty("card",True);box=QVBoxLayout(card);self.room_status=QLabel("正在同步当前绑定……");self.room_status.setWordWrap(True);box.addWidget(self.room_status);open_button=QPushButton("设置或更换当前直播间");open_button.setProperty("primary",True);open_button.clicked.connect(self._open_enterprise_binding);box.addWidget(open_button);impact=QLabel("更换绑定只影响之后的新数据，历史检测和直播数据不会修改。");impact.setProperty("muted",True);impact.setWordWrap(True);box.addWidget(impact);layout.addWidget(card);layout.addStretch();return page

    def _navigate(self, page: str):
        if page == "home": self.stack.setCurrentWidget(self.home)
        elif page == "room": self.stack.setCurrentWidget(self.room_page)
        elif page == "device": self.stack.setCurrentWidget(self.device_page)
        else: self.stack.setCurrentWidget(self.help_page)

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

    def _show_result(self): self.stack.setCurrentWidget(self.result); self.sidebar.select("home")
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

    def _open_enterprise_binding(self): EnterpriseBindingDialog(self).exec(); self._manual_sync()

    def _v2_heartbeat(self):
        if self._v2_heartbeat_running: return
        self._v2_heartbeat_running=True
        threading.Thread(target=self._flush_v2_safely,daemon=True,name="v2-device-heartbeat").start()

    def _flush_v2_safely(self):
        try:
            credentials=load_credentials()
            if not credentials.get("device_token"):
                api=ClientApi(self.config["api_base"]); registered=api.register(self.config,APP_VERSION); save_credentials(device_token=registered["device_token"])
            result=flush_v2_heartbeat();bootstrap=result.get("bootstrap",{});metrics=v2_heartbeat_payload()
            if bootstrap:self.bootstrap_updated.emit(bootstrap)
            self.device_sync_completed.emit({"result":result,"bootstrap":bootstrap or self._device_bootstrap,"metrics":metrics})
        except Exception as exc:
            self._logger.warning("device sync failed: %s",exc)
            self.device_sync_failed.emit("同步未完成：请检查网络或重新登录企业账号。")
        finally: self._v2_heartbeat_running=False

    @Slot(dict)
    def _apply_device_bootstrap(self,bootstrap):
        self._device_bootstrap=bootstrap;config=bootstrap.get("config",{});features=bootstrap.get("features",{});interval=max(10,int(config.get("heartbeat_interval_seconds",20)));self.v2_heartbeat_timer.setInterval(interval*1000);self.sidebar.apply_features(features);binding=bootstrap.get("binding");organization=bootstrap.get("organization",{})
        if (self.stack.currentWidget() is self.room_page and not features.get("device_binding",True)) or (self.stack.currentWidget() is self.device_page and not features.get("device_heartbeat",True)):
            self.stack.setCurrentWidget(self.home);self.sidebar.select("home")
        if binding:self.room_status.setText(f"企业：{organization.get('name','-')}\n直播间：{binding.get('room_name') or binding.get('room_id','-')}\n账号：{binding.get('account_name') or '未关联'} · 主播：{binding.get('anchor_name') or '未关联'}\n最后同步：刚刚")
        else:self.room_status.setText(f"企业：{organization.get('name','-')}\n这台电脑尚未选择直播间。")
        minimum=bootstrap.get("minimum_version","")
        if minimum and tuple(int(x) for x in minimum.split('.')[:3])>tuple(int(x) for x in APP_VERSION.split('.')[:3]):self.room_status.setText(self.room_status.text()+f"\n客户端需要升级到 V{minimum} 或更高版本。")

    @Slot(dict)
    def _device_sync_done(self,value):
        self._last_device_sync=value
        result=value.get("result",{})
        if result.get("auth_error"):
            self.device_page.set_error("设备凭据已失效，客户端将在下一次同步时自动重新注册。")
            self.help_page.show_feedback("设备凭据已失效，已停止使用旧凭据。")
            return
        if result.get("unbound"):
            self.room_status.setText("这台电脑尚未加入企业。请在“当前直播间”中登录并完成首次绑定。")
        self.device_page.set_state(value.get("bootstrap",{}),result,value.get("metrics",{}))
        self.help_page.show_feedback(f"同步完成 · 配置版本 {value.get('bootstrap',{}).get('config_version','—')}")

    def _manual_sync(self):
        self.help_page.show_feedback("正在后台重新同步，不会阻塞当前页面……")
        self._v2_heartbeat()

    def _open_logs(self):
        DATA_DIR.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))
        self.help_page.show_feedback("已打开日志目录；发送日志前请确认接收方身份。")

    def _copy_diagnostics(self):
        diagnostics={"product":"VD Nexus","version":APP_VERSION,"device_id":self.config.get("device_id"),"api_base":self.config.get("api_base"),"target_region_id":self.config.get("target_region_id"),"config_version":self._device_bootstrap.get("config_version"),"organization":self._device_bootstrap.get("organization"),"binding":self._device_bootstrap.get("binding"),"last_sync":{"sent":self._last_device_sync.get("result",{}).get("sent",0),"queued":self._last_device_sync.get("result",{}).get("queued",0)}}
        QApplication.clipboard().setText(json.dumps(diagnostics,ensure_ascii=False,indent=2));self.help_page.show_feedback("诊断信息已复制；其中不包含密码、令牌、Cookie 或直播素材。")

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
            except Exception as exc: self._logger.debug("legacy heartbeat failed: %s",exc)
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
            except Exception as exc: self._logger.debug("device event upload failed: %s",exc)
        threading.Thread(target=send,daemon=True,name="enterprise-event").start()
    def _open_account(self):
        AccountDialog(self).exec()
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
