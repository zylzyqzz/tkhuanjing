from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import threading
import uuid
import zipfile

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..api import ApiError, ClientApi
from ..checks import CheckContext, DEFAULT_PROFILE, PLUGINS, run_checks, run_repair
from ..environment_setup import SetupAction, capture_environment_snapshot, execute_setup_action, new_setup_record, planned_actions
from ..events import CheckEvent
from ..models import CheckReport, CheckResult, SEVERITY, Status
from ..regions import REGIONS, get_region
from ..storage import CONFIG_FILE, DATA_DIR, DEFAULT_CONFIG, REPORT_DIR, baseline_delta, cleanup_reports, configure_logging, load_config, load_license, load_reports, queue_report, save_config, save_license, save_report
from ..streaming_config import discover_streaming_profiles
from ..updater import UpdateError, download_update, launch_helper
from .components import FramelessWindow, MetricCard, ModeCard, ModuleTile, ScanCore, TechBackdrop, TerminalLog, TitleBar
from .theme import COLORS, THEMES, apply_theme


def resource_dir() -> Path:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "assets" if getattr(sys, "_MEIPASS", "") else Path("."),
        Path(sys.executable).resolve().parent / "assets",
        Path(__file__).resolve().parents[2] / "assets",
    ]
    return next((path for path in candidates if (path / "app_icon.ico").exists()), candidates[-1])


def card() -> QFrame:
    frame = QFrame()
    frame.setProperty("card", True)
    return frame


class CheckWorker(QObject):
    progress = Signal(int, str)
    event = Signal(object)
    completed = Signal(object, object, object)
    failed = Signal(str)

    def __init__(self, config: dict, run_mode: str = "daily_preflight", before_snapshot: dict | None = None, actions: list[SetupAction] | None = None) -> None:
        super().__init__()
        self.config = dict(config)
        self.run_mode = run_mode
        self.before_snapshot = before_snapshot or {}
        self.actions = actions or []
        self.cancelled = threading.Event()
        self.paused = threading.Event()
        self.logs: list[dict] = []
        self.setup_record: dict = {}

    def _emit_event(self, event: CheckEvent) -> None:
        self.logs.append(event.to_dict())
        self.event.emit(event)

    def _wait_if_paused(self) -> None:
        while self.paused.is_set() and not self.cancelled.is_set():
            self.paused.wait(.15)

    @Slot()
    def run(self) -> None:
        api = ClientApi(self.config["api_base"], self.config.get("device_token", ""))
        profile, online, license_data = dict(DEFAULT_PROFILE), False, load_license()
        try:
            self._emit_event(CheckEvent("check_started", "core", "初始化直播环境检测核心", "info", 0))
            if not api.token:
                registered = api.register(self.config, APP_VERSION)
                self.config["device_token"] = api.token
                license_data.update(registered.get("license", {}))
            profile.update(api.profile())
            authorized = api.authorize(str(uuid.uuid4()))
            license_data.update({
                "credits": authorized.get("credits", license_data.get("credits", -1)),
                "expires_at": authorized.get("expires_at", license_data.get("expires_at", "")),
                "lease_until": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
            })
            online = True
        except ApiError as exc:
            lease = license_data.get("lease_until", "")
            try:
                valid_lease = datetime.fromisoformat(lease) > datetime.now(timezone.utc)
            except (ValueError, TypeError):
                valid_lease = False
            self._emit_event(CheckEvent("data_source", "client", f"管理服务离线，继续本地检测：{exc}", "fallback", 2))
            if not valid_lease and license_data.get("tier") != "FREE":
                self.failed.emit(f"无法验证离线授权：{exc}")
                return
        try:
            region = get_region(self.config.get("target_region_id"))
            if self.run_mode == "environment_setup":
                self.setup_record = new_setup_record(self.config["device_id"], region, self.before_snapshot)
                for index, action in enumerate(self.actions):
                    if self.cancelled.is_set():
                        break
                    self._wait_if_paused()
                    percent = int((index + 1) / max(len(self.actions), 1) * 22)
                    self._emit_event(CheckEvent("repair_started", "setup", f"正在配置：{action.title}", "warning", percent))
                    result = execute_setup_action(action, region)
                    self.setup_record["actions"].append(result.to_dict())
                    level = "success" if result.status == "success" else "fail"
                    self._emit_event(CheckEvent("repair_finished", "setup", f"{result.title}：{result.message}", level, percent))
                self.setup_record["status"] = "configured"
            context = CheckContext(profile, region, self.config["target_host"], api, resource_dir(), APP_VERSION, online, self.cancelled, self._emit_event, self.paused, self.config.get("test_mode", "standard"))
            items = run_checks(context, lambda value, text: self.progress.emit(max(value, 23 if self.run_mode == "environment_setup" else value), text))
            after = capture_environment_snapshot(region, resource_dir()) if self.run_mode == "environment_setup" else {}
            report = CheckReport(self.config["device_id"], APP_VERSION, items, target_region_id=region.region_id, run_mode=self.run_mode)
            report.streaming_profiles = discover_streaming_profiles()
            report.data_sources = sorted({item.data_source for item in items if item.data_source})
            report.ip_profile = next((item.metrics for item in items if item.check_id == "network.public_ip"), {})
            report.network_snapshot = {item.check_id: item.metrics for item in items if item.check_id.startswith("network.")}
            report.environment_snapshot = {item.check_id: item.metrics for item in items if item.check_id.startswith(("system.", "environment."))}
            report.device_snapshot = {item.check_id: item.metrics for item in items if item.check_id.startswith(("devices.", "performance."))}
            report.check_logs = self.logs
            report.before_snapshot = self.before_snapshot
            report.after_snapshot = after
            report.repair_events = self.setup_record.get("actions", [])
            confidence: dict[str, int] = {}
            for item in items:
                confidence[item.confidence] = confidence.get(item.confidence, 0) + 1
            report.confidence_summary = confidence
            report.finalize()
            report.test_mode = self.config.get("test_mode", "standard")
            current = report.to_dict()
            previous = next((row for row in load_reports(10) if row.get("run_mode") == self.run_mode), None)
            report.baseline_delta = baseline_delta(current, previous) if self.config.get("auto_compare_reports", True) else {"available": False}
            self.completed.emit(report, self.config, license_data)
        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self) -> None:
        self.cancelled.set()
        self.paused.clear()

    def toggle_pause(self) -> bool:
        if self.paused.is_set():
            self.paused.clear()
            return False
        self.paused.set()
        return True


class PrepareSetupWorker(QObject):
    completed = Signal(object, object)
    failed = Signal(str)

    def __init__(self, region_id: str) -> None:
        super().__init__()
        self.region = get_region(region_id)

    @Slot()
    def run(self) -> None:
        try:
            snapshot = capture_environment_snapshot(self.region, resource_dir())
            self.completed.emit(snapshot, planned_actions(snapshot, self.region))
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, manifest: dict) -> None:
        super().__init__()
        self.manifest = manifest
        self.cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(download_update(self.manifest, lambda value, text: self.progress.emit(value, text), lambda: self.cancelled))
        except Exception as exc:
            self.failed.emit(str(exc))


class SetupPlanDialog(QDialog):
    def __init__(self, parent, snapshot: dict, actions: list[SetupAction]) -> None:
        super().__init__(parent)
        self.setWindowTitle("确认环境配置项目")
        self.resize(720, 620)
        self.actions = actions
        self.checks: list[tuple[QCheckBox, SetupAction]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        title = QLabel("配置前环境快照")
        title.setProperty("heading", True)
        layout.addWidget(title)
        overview = QLabel(f"当前时区：{snapshot.get('timezone','未知')}\n区域格式：{snapshot.get('culture','未知')}\n系统区域：{snapshot.get('system_locale','未知')}\n默认网关：{snapshot.get('default_gateway','未知')}")
        overview.setProperty("muted", True)
        layout.addWidget(overview)
        notice = QLabel("安全项目默认勾选；涉及时区、区域、进程和缓存的项目需要您主动勾选。所有执行结果都会写入配置报告。")
        notice.setWordWrap(True)
        notice.setProperty("impact", True)
        layout.addWidget(notice)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        for action in actions:
            item = card()
            box = QVBoxLayout(item)
            check = QCheckBox(f"{action.title}  ·  {'安全处理' if action.level == 'safe' else '需要确认'}")
            check.setChecked(action.level == "safe")
            box.addWidget(check)
            detail = QLabel(f"当前：{action.before or '未读取'}\n目标：{action.target or '按检测结果处理'}")
            detail.setWordWrap(True)
            detail.setProperty("muted", True)
            box.addWidget(detail)
            body_layout.addWidget(item)
            self.checks.append((check, action))
        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        confirm = QPushButton("确认并开始配置")
        confirm.setProperty("gold", True)
        confirm.clicked.connect(self.accept)
        row.addWidget(confirm)
        layout.addLayout(row)

    def selected_actions(self) -> list[SetupAction]:
        return [action for check, action in self.checks if check.isChecked()]


class ActivationDialog(QDialog):
    def __init__(self, parent, activate_callback) -> None:
        super().__init__(parent)
        self.setWindowTitle("授权服务")
        self.resize(820, 650)
        self.activate_callback = activate_callback
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        title = QLabel("选择授权方案")
        title.setProperty("heading", True)
        layout.addWidget(title)
        subtitle = QLabel("有效期内不限检测次数。点击整张套餐卡片即可选择，付款后联系客户服务获取激活码。")
        subtitle.setProperty("muted", True)
        layout.addWidget(subtitle)
        packages = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, (name, price, days) in enumerate((("月卡", "¥99", "30 天"), ("季卡", "¥288", "90 天"), ("半年卡", "¥488", "180 天"), ("年卡", "¥688", "365 天"))):
            button = QPushButton(f"{name}\n{price}\n{days}内不限次数")
            button.setCheckable(True)
            button.setMinimumHeight(105)
            self.group.addButton(button)
            packages.addWidget(button)
            if index == 1:
                button.setChecked(True)
        layout.addLayout(packages)
        qr_row = QHBoxLayout()
        for label, filename in (("扫码付款", "收款码.jpg"), ("联系客户服务", "客服二维码.png")):
            pane = card()
            box = QVBoxLayout(pane)
            heading = QLabel(label)
            heading.setProperty("subheading", True)
            box.addWidget(heading)
            image = QLabel()
            pixmap = QPixmap(str(resource_dir() / filename))
            image.setPixmap(pixmap.scaled(205, 205, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            image.setAlignment(Qt.AlignCenter)
            box.addWidget(image)
            qr_row.addWidget(pane)
        layout.addLayout(qr_row)
        row = QHBoxLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("输入客户服务提供的激活码")
        row.addWidget(self.code)
        activate = QPushButton("立即激活")
        activate.setProperty("primary", True)
        activate.clicked.connect(self._activate)
        row.addWidget(activate)
        layout.addLayout(row)

    def _activate(self) -> None:
        code = self.code.text().strip()
        if not code:
            QMessageBox.warning(self, "请输入激活码", "请先输入客户服务提供的激活码")
        elif self.activate_callback(code):
            self.accept()


class MainWindow(FramelessWindow):
    PAGE_NAMES = ["开播中心", "检测过程", "检测报告", "问题处理", "网络报告", "历史记录", "授权服务", "系统设置", "关于产品"]

    def __init__(self) -> None:
        super().__init__()
        self.logger = configure_logging()
        self.config = load_config()
        self.license = load_license()
        self.current_report: CheckReport | None = None
        self.worker: CheckWorker | None = None
        self.thread: QThread | None = None
        self.prepare_thread: QThread | None = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(resource_dir() / "app_icon.ico")))
        self.setMinimumSize(1120, 720)
        self.resize(1360, 850)
        self.setStyleSheet(apply_theme(self.config.get("theme_id", "obsidian"), self.config.get("font_scale", "standard")))
        self._build()
        self._apply_theme()
        self._refresh_history()
        self._update_license_label()
        start_page = int(self.config.get("last_page", 0)) if self.config.get("remember_last_page") else {"home": 0, "network": 4, "history": 5}.get(self.config.get("startup_page", "home"), 0)
        self._show_page(start_page if 0 <= start_page < len(self.PAGE_NAMES) else 0)
        if self.config.get("update_check_on_start", True):
            QTimer.singleShot(1800, lambda: self._check_update(silent=True))

    def _build(self) -> None:
        chrome = QWidget()
        chrome.setObjectName("windowChrome")
        self.setCentralWidget(chrome)
        root = QVBoxLayout(chrome)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        root.addWidget(TitleBar(self, APP_NAME, APP_VERSION))
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        root.addWidget(body, 1)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(174)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 12, 12, 15)
        side.setSpacing(7)
        brand = QLabel("JC  LIVE CORE")
        brand.setObjectName("sideBrand")
        brand.setAlignment(Qt.AlignCenter)
        side.addWidget(brand)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        icons = ["01", "02", "03", "04", "05", "06", "07", "08", "09"]
        for index, (icon, name) in enumerate(zip(icons, self.PAGE_NAMES)):
            button = QPushButton(f"{icon}   {name}")
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.clicked.connect(lambda _=False, page=index: self._show_page(page))
            self.nav_group.addButton(button, index)
            side.addWidget(button)
        side.addStretch()
        self.license_label = QLabel()
        self.license_label.setProperty("muted", True)
        self.license_label.setWordWrap(True)
        side.addWidget(self.license_label)
        body_layout.addWidget(sidebar)
        self.backdrop = TechBackdrop()
        self.backdrop.set_reduced(self.config.get("effects_level", "full") == "light")
        backdrop_layout = QVBoxLayout(self.backdrop)
        backdrop_layout.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        backdrop_layout.addWidget(self.pages)
        body_layout.addWidget(self.backdrop, 1)
        for page in (self._home_page(), self._scan_page(), self._report_page(), self._problems_page(), self._network_page(), self._history_page(), self._service_page(), self._settings_page(), self._about_page()):
            self.pages.addWidget(page)

    def _shell(self, eyebrow: str, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)
        eye = QLabel(eyebrow.upper())
        eye.setObjectName("pageEyebrow")
        layout.addWidget(eye)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        sub = QLabel(subtitle)
        sub.setObjectName("pageSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        return page, layout

    def _home_page(self) -> QWidget:
        page, layout = self._shell("LIVE READINESS CENTER", "今天的直播环境，准备好了吗？", "选择目标地区后执行日常开播检查，或在新设备、更换网络和重新整理电脑时配置环境。")
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("目标直播地区 / Target region"))
        target_row.addStretch()
        self.region = QComboBox()
        self.region.setMinimumWidth(370)
        for region in REGIONS:
            self.region.addItem(region.label, region.region_id)
        self.region.setCurrentIndex(max(0, self.region.findData(self.config.get("target_region_id"))))
        target_row.addWidget(self.region)
        layout.addLayout(target_row)
        modes = QHBoxLayout()
        modes.setSpacing(16)
        daily = ModeCard("◉", "DAILY PREFLIGHT", "一键开播检查", "日常开播前使用。真实检测网络、电脑性能、直播软件与设备状态，只读取数据，不主动修改电脑环境。", "立即开始开播检查", "#43AEFF")
        daily.clicked.connect(lambda: self._start_check("daily_preflight"))
        modes.addWidget(daily)
        setup = ModeCard("◇", "NEW DEVICE SETUP", "一键配置环境", "新设备、更换网络、切换账号或环境异常时使用。确认后配置系统区域、刷新网络缓存并自动复检。", "开始配置新环境", "#E9AE55")
        setup.clicked.connect(self._start_setup)
        modes.addWidget(setup)
        layout.addLayout(modes, 1)
        stats = QHBoxLayout()
        self.home_status = MetricCard("上次开播结论", "尚未检测")
        self.home_problems = MetricCard("待处理问题", "0", "项")
        self.home_region = MetricCard("目标地区", get_region(self.config.get("target_region_id")).country_code)
        self.home_version = MetricCard("客户端版本", f"V{APP_VERSION}")
        for widget in (self.home_status, self.home_problems, self.home_region, self.home_version):
            stats.addWidget(widget)
        layout.addLayout(stats)
        service = QHBoxLayout()
        hint = card()
        hint_box = QVBoxLayout(hint)
        hint_title = QLabel("直播准备重要提示")
        hint_title.setProperty("subheading", True)
        hint_box.addWidget(hint_title)
        hint_text = QLabel("网络归属地、时区和区域一致性仅用于技术准备提示；软件不会承诺 IP 纯净度、账号流量或平台审核结果。")
        hint_text.setWordWrap(True)
        hint_text.setProperty("muted", True)
        hint_box.addWidget(hint_text)
        service.addWidget(hint, 2)
        links = card()
        links_box = QHBoxLayout(links)
        network = QPushButton("纯净网络服务")
        network.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://jd.wdai.cc")))
        account = QPushButton("TK 账号服务")
        account.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("http://wdai.cc")))
        links_box.addWidget(network)
        links_box.addWidget(account)
        service.addWidget(links, 1)
        layout.addLayout(service)
        return page

    def _scan_page(self) -> QWidget:
        page, layout = self._shell("LIVE DIAGNOSTIC ENGINE", "直播环境核心正在运行", "检测过程与真实采样同步，任何单项异常都不会终止整轮检查。")
        row = QHBoxLayout()
        visual = card()
        visual_box = QVBoxLayout(visual)
        self.scan_core = ScanCore()
        self.scan_core.set_reduced(self.config.get("effects_level", "full") == "light")
        visual_box.addWidget(self.scan_core, 1)
        self.scan_status = QLabel("等待检测任务")
        self.scan_status.setAlignment(Qt.AlignCenter)
        self.scan_status.setProperty("subheading", True)
        visual_box.addWidget(self.scan_status)
        self.progress = QProgressBar()
        visual_box.addWidget(self.progress)
        controls = QHBoxLayout()
        self.pause_button = QPushButton("暂停")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.pause_button.setEnabled(False)
        controls.addWidget(self.pause_button)
        self.cancel_button = QPushButton("取消检测")
        self.cancel_button.setProperty("danger", True)
        self.cancel_button.clicked.connect(self._cancel_check)
        self.cancel_button.setEnabled(False)
        controls.addWidget(self.cancel_button)
        visual_box.addLayout(controls)
        row.addWidget(visual, 3)
        module_panel = QVBoxLayout()
        self.module_tiles: dict[str, ModuleTile] = {}
        module_defs = [
            ("network", "IP", "IP 与网络质量"), ("system", "OS", "Windows 环境"),
            ("performance", "CPU", "电脑性能与编码"), ("devices", "DEV", "直播设备与插件"),
            ("streaming", "LIVE", "直播软件参数"), ("client", "APP", "客户端完整性"),
        ]
        for module_id, icon, name in module_defs:
            tile = ModuleTile(icon, name)
            self.module_tiles[module_id] = tile
            module_panel.addWidget(tile)
        module_panel.addStretch()
        row.addLayout(module_panel, 2)
        layout.addLayout(row, 3)
        self.terminal = TerminalLog()
        self.terminal.setMinimumHeight(170)
        layout.addWidget(self.terminal, 2)
        return page

    def _report_page(self) -> QWidget:
        page, layout = self._shell("CONSISTENCY REPORT", "开播技术准备度报告", "先看结论和关键指标，再进入具体问题；UNKNOWN 表示检测未完成，不会伪装成通过。")
        summary = card()
        summary_box = QHBoxLayout(summary)
        summary_box.setContentsMargins(22, 18, 22, 18)
        self.report_badge = QLabel("尚未检测")
        self.report_badge.setProperty("heading", True)
        summary_box.addWidget(self.report_badge)
        self.report_conclusion = QLabel("完成开播检查后生成系统一致性结论")
        self.report_conclusion.setWordWrap(True)
        self.report_conclusion.setProperty("muted", True)
        summary_box.addWidget(self.report_conclusion, 1)
        self.repair_all_button = QPushButton("一键处理安全问题")
        self.repair_all_button.setProperty("primary", True)
        self.repair_all_button.clicked.connect(self._repair_all)
        self.repair_all_button.setEnabled(False)
        summary_box.addWidget(self.repair_all_button)
        layout.addWidget(summary)
        metric_row = QHBoxLayout()
        self.report_metrics = {
            "ip": MetricCard("公网 IP", "--"), "down": MetricCard("下载速度", "--", "Mbps"),
            "up": MetricCard("稳定上传", "--", "Mbps"), "latency": MetricCard("目标延迟", "--", "ms"),
            "problems": MetricCard("风险与异常", "0", "项"),
        }
        for widget in self.report_metrics.values():
            metric_row.addWidget(widget)
        layout.addLayout(metric_row)
        self.report_modules = QGridLayout()
        layout.addLayout(self.report_modules, 1)
        actions = QHBoxLayout()
        actions.addStretch()
        export = QPushButton("导出 JSON 报告")
        export.clicked.connect(self._export_current_report)
        actions.addWidget(export)
        upload = QPushButton("主动上传报告")
        upload.clicked.connect(self._upload_report)
        actions.addWidget(upload)
        rerun = QPushButton("重新完整检测")
        rerun.setProperty("primary", True)
        rerun.clicked.connect(lambda: self._start_check("daily_preflight"))
        actions.addWidget(rerun)
        layout.addLayout(actions)
        return page

    def _problems_page(self) -> QWidget:
        page, layout = self._shell("PROBLEM RESOLUTION", "问题处理中心", "每个问题都提供检测证据、实际影响、处理办法和复检入口。")
        toolbar = QHBoxLayout()
        self.problem_filter = QComboBox()
        self.problem_filter.addItems(["全部问题", "失败", "风险", "未完成"])
        self.problem_filter.currentTextChanged.connect(self._render_problems)
        toolbar.addWidget(self.problem_filter)
        toolbar.addStretch()
        self.problem_summary = QLabel("尚无检测结果")
        self.problem_summary.setProperty("muted", True)
        toolbar.addWidget(self.problem_summary)
        layout.addLayout(toolbar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.problem_layout = QVBoxLayout(body)
        self.problem_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        return page

    def _network_page(self) -> QWidget:
        page, layout = self._shell("NETWORK INTELLIGENCE REPORT", "网络检测分析报告", "单独呈现 IP 注册信息、线路质量、目标地区匹配和原始测速证据；第三方数据缺失不会被当作网络故障。")
        metrics = QHBoxLayout()
        self.network_metrics = {
            "location": MetricCard("IP 归属地", "--"), "isp": MetricCard("ISP / ASN", "--"),
            "download": MetricCard("下载", "--", "Mbps"), "upload": MetricCard("稳定上传", "--", "Mbps"),
            "latency": MetricCard("目标延迟", "--", "ms"), "variation": MetricCard("上传波动", "--", "%"),
        }
        for widget in self.network_metrics.values():
            metrics.addWidget(widget)
        layout.addLayout(metrics)
        body = QHBoxLayout()
        identity_card = card(); identity_box = QVBoxLayout(identity_card)
        identity_title = QLabel("IP 身份与注册信息"); identity_title.setProperty("subheading", True); identity_box.addWidget(identity_title)
        self.network_identity_table = QTableWidget(0, 2)
        self.network_identity_table.setHorizontalHeaderLabels(["检测项目", "检测结果"])
        self.network_identity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.network_identity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.network_identity_table.verticalHeader().setVisible(False)
        self.network_identity_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.network_identity_table.setSelectionMode(QAbstractItemView.NoSelection)
        identity_box.addWidget(self.network_identity_table, 1)
        body.addWidget(identity_card, 3)
        diagnosis_card = card(); diagnosis_box = QVBoxLayout(diagnosis_card)
        diagnosis_title = QLabel("直播网络分析"); diagnosis_title.setProperty("subheading", True); diagnosis_box.addWidget(diagnosis_title)
        self.network_details = TerminalLog(); diagnosis_box.addWidget(self.network_details, 1)
        body.addWidget(diagnosis_card, 4)
        layout.addLayout(body, 1)
        actions = QHBoxLayout()
        self.network_source_label = QLabel("完成一次开播检查后生成网络报告"); self.network_source_label.setProperty("muted", True); actions.addWidget(self.network_source_label)
        actions.addStretch()
        export = QPushButton("导出网络报告"); export.clicked.connect(self._export_network_report); actions.addWidget(export)
        recheck = QPushButton("重新检测网络"); recheck.setProperty("primary", True); recheck.clicked.connect(lambda: self._start_check("daily_preflight")); actions.addWidget(recheck)
        layout.addLayout(actions)
        return page

    def _history_page(self) -> QWidget:
        page, layout = self._shell("LOCAL REPORT ARCHIVE", "本机历史记录", "报告默认保存在本机，只有主动操作后才会上传后台。")
        row = QHBoxLayout()
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("搜索地区、模式或报告编号")
        self.history_search.textChanged.connect(self._refresh_history)
        row.addWidget(self.history_search)
        export = QPushButton("导出选中报告")
        export.clicked.connect(self._export_history)
        row.addWidget(export)
        layout.addLayout(row)
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["检查时间", "模式", "目标地区", "结论", "状态", "报告编号"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        layout.addWidget(self.history_table, 1)
        return page

    def _service_page(self) -> QWidget:
        page, layout = self._shell("LICENSE & SUPPORT", "授权服务", "有效期内不限检测次数。付款码和客户服务二维码已随程序资源离线嵌入。")
        hero = card()
        hero_box = QVBoxLayout(hero)
        self.service_license = QLabel()
        self.service_license.setProperty("heading", True)
        hero_box.addWidget(self.service_license)
        activate = QPushButton("选择套餐 / 输入激活码")
        activate.setProperty("gold", True)
        activate.clicked.connect(self._activation)
        hero_box.addWidget(activate)
        layout.addWidget(hero)
        qr_row = QHBoxLayout()
        for title, filename in (("付款二维码", "收款码.jpg"), ("客户服务二维码", "客服二维码.png")):
            pane = card()
            box = QVBoxLayout(pane)
            heading = QLabel(title)
            heading.setProperty("subheading", True)
            box.addWidget(heading)
            image = QLabel()
            pixmap = QPixmap(str(resource_dir() / filename))
            image.setPixmap(pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            image.setAlignment(Qt.AlignCenter)
            box.addWidget(image)
            qr_row.addWidget(pane)
        layout.addLayout(qr_row, 1)
        return page

    def _settings_page(self) -> QWidget:
        page, layout = self._shell("SYSTEM PREFERENCES", "系统设置", "按您的日常使用习惯定制启动、检测、外观、提示和本地数据；内部服务地址不会暴露在客户端。")
        tabs = QTabWidget(); tabs.setObjectName("settingsTabs")

        general = QWidget(); general.setObjectName("settingsPage"); general_box = QVBoxLayout(general); general_card = card(); form = QVBoxLayout(general_card)
        form.addWidget(QLabel("默认目标地区"))
        self.default_region_setting = QComboBox()
        for item in REGIONS: self.default_region_setting.addItem(item.label, item.region_id)
        self.default_region_setting.setCurrentIndex(max(0, self.default_region_setting.findData(self.config.get("target_region_id"))))
        form.addWidget(self.default_region_setting)
        form.addWidget(QLabel("启动后默认页面")); self.startup_page_select = QComboBox()
        for title, value in (("开播中心", "home"), ("网络报告", "network"), ("历史记录", "history")): self.startup_page_select.addItem(title, value)
        self.startup_page_select.setCurrentIndex(max(0, self.startup_page_select.findData(self.config.get("startup_page", "home")))); form.addWidget(self.startup_page_select)
        self.remember_last_page = QCheckBox("记住退出前打开的页面"); self.remember_last_page.setChecked(bool(self.config.get("remember_last_page", False))); form.addWidget(self.remember_last_page)
        self.result_sound = QCheckBox("检测完成后播放提示音"); self.result_sound.setChecked(bool(self.config.get("result_sound", True))); form.addWidget(self.result_sound)
        self.auto_open_report = QCheckBox("检测完成后自动打开检测报告"); self.auto_open_report.setChecked(bool(self.config.get("auto_open_report", True))); form.addWidget(self.auto_open_report)
        self.update_on_start = QCheckBox("启动软件时自动检查新版本"); self.update_on_start.setChecked(bool(self.config.get("update_check_on_start", True))); form.addWidget(self.update_on_start)
        self.show_check_tips = QCheckBox("检测前显示目标地区和预计耗时提示"); self.show_check_tips.setChecked(bool(self.config.get("show_check_tips", True))); form.addWidget(self.show_check_tips)
        reset = QPushButton("恢复推荐设置"); reset.clicked.connect(self._reset_settings); form.addWidget(reset)
        general_box.addWidget(general_card); general_box.addStretch(); tabs.addTab(general, "常规设置")

        appearance = QWidget(); appearance.setObjectName("settingsPage"); appearance_box = QVBoxLayout(appearance); appearance_card = card(); form = QVBoxLayout(appearance_card)
        form.addWidget(QLabel("产品主题")); self.theme_select = QComboBox()
        for key, value in THEMES.items(): self.theme_select.addItem(value["name"], key)
        self.theme_select.setCurrentIndex(max(0, self.theme_select.findData(self.config.get("theme_id", "obsidian"))))
        self.theme_select.currentIndexChanged.connect(self._preview_theme); form.addWidget(self.theme_select)
        form.addWidget(QLabel("视觉特效")); self.effects_select = QComboBox()
        for title, value in (("完整特效", "full"), ("标准特效", "standard"), ("轻量模式", "light")): self.effects_select.addItem(title, value)
        self.effects_select.setCurrentIndex(max(0, self.effects_select.findData(self.config.get("effects_level", "full")))); form.addWidget(self.effects_select)
        form.addWidget(QLabel("界面字体")); self.font_select = QComboBox(); self.font_select.addItem("标准", "standard"); self.font_select.addItem("较大", "large")
        self.font_select.setCurrentIndex(max(0, self.font_select.findData(self.config.get("font_scale", "standard")))); self.font_select.currentIndexChanged.connect(self._preview_theme); form.addWidget(self.font_select)
        hint = QLabel("主题切换立即生效；轻量模式会降低粒子、扫描和背景绘制频率。"); hint.setProperty("muted", True); hint.setWordWrap(True); form.addWidget(hint)
        appearance_box.addWidget(appearance_card); appearance_box.addStretch(); tabs.addTab(appearance, "外观与动效")

        detection = QWidget(); detection.setObjectName("settingsPage"); detection_box = QVBoxLayout(detection); detection_card = card(); form = QVBoxLayout(detection_card)
        form.addWidget(QLabel("网络检测强度")); self.test_mode_select = QComboBox()
        self.test_mode_select.addItem("快速检测 · 约 1–2 分钟 · 约 6 MB", "quick")
        self.test_mode_select.addItem("标准检测 · 约 2–3 分钟 · 约 12 MB", "standard")
        self.test_mode_select.addItem("深度检测 · 约 4–6 分钟 · 约 30 MB", "deep")
        self.test_mode_select.setCurrentIndex(max(0, self.test_mode_select.findData(self.config.get("test_mode", "standard")))); form.addWidget(self.test_mode_select)
        self.auto_compare_reports = QCheckBox("检测完成后自动与上一次结果比较"); self.auto_compare_reports.setChecked(bool(self.config.get("auto_compare_reports", True))); form.addWidget(self.auto_compare_reports)
        info = QLabel("七组关键检查始终启用。快速模式适合单项复检，标准模式用于每日开播，深度模式增加上下行采样轮数。检测阈值由管理后台统一下发，避免客户误改标准。")
        info.setWordWrap(True); info.setProperty("muted", True); form.addWidget(info)
        detection_box.addWidget(detection_card); detection_box.addStretch(); tabs.addTab(detection, "检测设置")

        privacy = QWidget(); privacy.setObjectName("settingsPage"); privacy_box = QVBoxLayout(privacy); privacy_card = card(); form = QVBoxLayout(privacy_card)
        form.addWidget(QLabel(f"本地报告目录\n{REPORT_DIR}"))
        retention_row = QHBoxLayout(); retention_row.addWidget(QLabel("报告保留时间")); self.retention_select = QComboBox()
        for title, days in (("30 天", 30), ("90 天", 90), ("180 天", 180), ("永久保留", 0)): self.retention_select.addItem(title, days)
        self.retention_select.setCurrentIndex(max(0, self.retention_select.findData(int(self.config.get("report_retention_days", 90))))); retention_row.addWidget(self.retention_select); form.addLayout(retention_row)
        self.upload_confirm = QCheckBox("上传报告前始终要求我确认"); self.upload_confirm.setChecked(bool(self.config.get("upload_confirm", True))); form.addWidget(self.upload_confirm)
        buttons = QHBoxLayout(); open_dir = QPushButton("打开报告目录"); open_dir.clicked.connect(self._open_report_dir); buttons.addWidget(open_dir)
        clean = QPushButton("清理过期报告"); clean.clicked.connect(self._cleanup_local_reports); buttons.addWidget(clean)
        export = QPushButton("导出售后诊断包"); export.clicked.connect(self._export_diagnostics); buttons.addWidget(export); form.addLayout(buttons)
        privacy_note = QLabel("诊断包只包含软件日志、脱敏配置和最近检测报告，不包含账号密码、Cookie、浏览器数据或个人文件。")
        privacy_note.setWordWrap(True); privacy_note.setProperty("muted", True); form.addWidget(privacy_note)
        privacy_box.addWidget(privacy_card); privacy_box.addStretch(); tabs.addTab(privacy, "数据与隐私")

        layout.addWidget(tabs, 1)
        save = QPushButton("保存全部设置"); save.setProperty("primary", True); save.clicked.connect(self._save_settings); layout.addWidget(save)
        return page

    def _about_page(self) -> QWidget:
        page, layout = self._shell("ABOUT JC LIVE CORE", "关于 JC开播助手", "版本、更新、产品边界与售后入口集中在这里，与系统设置完全分离。")
        hero = card(); hero_box = QHBoxLayout(hero); hero_box.setContentsMargins(26, 22, 26, 22)
        logo = QLabel(); logo.setPixmap(QPixmap(str(resource_dir() / "app_icon.ico")).scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)); hero_box.addWidget(logo)
        identity = QVBoxLayout(); name = QLabel(f"JC开播助手  V{APP_VERSION}"); name.setProperty("heading", True); identity.addWidget(name)
        company = QLabel("维度光年（上海）科技有限责任公司出品"); company.setProperty("subheading", True); identity.addWidget(company)
        channel = QLabel("正式版 Stable · Windows 10 / 11 · 开播前技术准备度检测"); channel.setProperty("muted", True); identity.addWidget(channel); hero_box.addLayout(identity, 1)
        update = QPushButton("检测版本更新"); update.setProperty("primary", True); update.clicked.connect(self._check_update); hero_box.addWidget(update)
        layout.addWidget(hero)

        content = QHBoxLayout()
        info_card = card(); info = QVBoxLayout(info_card); title = QLabel("产品信息与更新"); title.setProperty("subheading", True); info.addWidget(title)
        for heading, value in (
            ("当前版本", f"V{APP_VERSION} · 构建通道 Stable"),
            ("检测报告", "Schema V5 · 支持网络原始样本与可信度来源"),
            ("产品定位", "面向 TikTok／跨境电脑直播的开播前检查、环境配置和问题处理。"),
            ("隐私说明", "不采集账号密码、Cookie、浏览器数据和个人文件；报告需主动确认后上传。"),
            ("责任边界", "只判断网络、电脑、设备和直播软件的技术准备情况，不代表平台审核、流量或开播权限。"),
        ):
            label = QLabel(f"{heading}\n{value}"); label.setWordWrap(True); label.setProperty("muted", True); info.addWidget(label)
        buttons = QHBoxLayout(); history = QPushButton("查看更新记录"); history.clicked.connect(self._show_changelog); buttons.addWidget(history)
        copy_id = QPushButton("复制设备编号"); copy_id.clicked.connect(self._copy_device_id); buttons.addWidget(copy_id)
        verify = QPushButton("检查软件完整性"); verify.clicked.connect(self._show_integrity); buttons.addWidget(verify); info.addLayout(buttons); info.addStretch(); content.addWidget(info_card, 3)

        support_card = card(); support = QVBoxLayout(support_card); support_title = QLabel("授权与客户服务"); support_title.setProperty("subheading", True); support.addWidget(support_title)
        qr = QHBoxLayout()
        for title, filename in (("付款二维码", "收款码.jpg"), ("客服二维码", "客服二维码.png")):
            pane = QVBoxLayout(); label = QLabel(title); label.setAlignment(Qt.AlignCenter); pane.addWidget(label)
            image = QLabel(); pix = QPixmap(str(resource_dir() / filename)); image.setPixmap(pix.scaled(156, 156, Qt.KeepAspectRatio, Qt.SmoothTransformation)); image.setAlignment(Qt.AlignCenter); pane.addWidget(image); qr.addLayout(pane)
        support.addLayout(qr); contact = QPushButton("打开授权服务"); contact.setProperty("gold", True); contact.clicked.connect(lambda: self._show_page(6)); support.addWidget(contact); content.addWidget(support_card, 2)
        layout.addLayout(content, 1)
        return page

    def _start_setup(self) -> None:
        text = (
            "请确认当前是否为新设备，或确实需要重新配置电脑环境。\n\n"
            "配置过程可能修改 Windows 时区、地区和区域格式，刷新 DNS 与网络缓存，并清理经过确认的临时缓存。\n\n"
            "不会读取账号密码、Cookie 或个人文件，不会关闭 Defender，不会执行大范围注册表删除。"
        )
        if QMessageBox.question(self, "确认进入环境配置模式", text, QMessageBox.Cancel | QMessageBox.Ok, QMessageBox.Cancel) != QMessageBox.Ok:
            return
        self._save_settings_silent()
        self._show_page(1)
        self.scan_status.setText("正在读取配置前环境快照…")
        self.scan_core.start()
        self.terminal.clear()
        self.terminal.append_event(CheckEvent("setup_prepare", "setup", "正在读取配置前环境快照", "warning"))
        self.prepare_thread = QThread(self)
        worker = PrepareSetupWorker(self.region.currentData())
        worker.moveToThread(self.prepare_thread)
        self.prepare_thread.started.connect(worker.run)
        worker.completed.connect(self._setup_prepared)
        worker.failed.connect(self._setup_prepare_failed)
        worker.completed.connect(self.prepare_thread.quit)
        worker.failed.connect(self.prepare_thread.quit)
        self.prepare_thread.finished.connect(worker.deleteLater)
        self.prepare_thread.start()

    def _setup_prepared(self, snapshot: dict, actions: list[SetupAction]) -> None:
        self.scan_core.finish("")
        dialog = SetupPlanDialog(self, snapshot, actions)
        if dialog.exec() == QDialog.Accepted:
            self._launch_worker("environment_setup", snapshot, dialog.selected_actions())
        else:
            self._show_page(0)

    def _setup_prepare_failed(self, message: str) -> None:
        self.scan_core.finish("UNKNOWN")
        QMessageBox.warning(self, "无法准备环境配置", message)
        self._show_page(0)

    def _start_check(self, run_mode: str = "daily_preflight") -> None:
        self._save_settings_silent()
        if run_mode == "daily_preflight" and self.config.get("show_check_tips", True):
            mode = self.config.get("test_mode", "standard")
            estimate = {"quick": "约 1–2 分钟", "standard": "约 2–3 分钟", "deep": "约 4–6 分钟"}.get(mode, "约 2–3 分钟")
            region = get_region(self.config.get("target_region_id"))
            if QMessageBox.question(self, "准备开始开播检查", f"目标地区：{region.label}\n检测强度：{mode.upper()} · {estimate}\n\n本次日常检查只读取状态，不修改电脑环境。是否开始？") != QMessageBox.Yes:
                return
        self._launch_worker(run_mode, {}, [])

    def _launch_worker(self, run_mode: str, snapshot: dict, actions: list[SetupAction]) -> None:
        if self.thread and self.thread.isRunning():
            QMessageBox.information(self, "检测正在进行", "请等待当前任务完成，或先取消当前任务。")
            return
        self._show_page(1)
        self.progress.setValue(0)
        self.scan_status.setText("环境配置与复检" if run_mode == "environment_setup" else "正在执行日常开播检查")
        self.terminal.clear()
        for tile in self.module_tiles.values():
            tile.set_state("waiting")
        self.scan_core.start()
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.thread = QThread(self)
        self.worker = CheckWorker(self.config, run_mode, snapshot, actions)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._progress)
        self.worker.event.connect(self._event_received)
        self.worker.completed.connect(self._check_completed)
        self.worker.failed.connect(self._check_failed)
        self.worker.completed.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _event_received(self, event: CheckEvent) -> None:
        self.terminal.append_event(event)
        tile = self.module_tiles.get(event.module)
        if tile:
            if event.event == "module_started":
                tile.set_state("running")
            elif event.event == "module_finished":
                tile.set_state(event.level if event.level in {"warning", "fail", "unknown"} else "success")

    def _progress(self, value: int, text: str) -> None:
        self.progress.setValue(value)
        self.scan_status.setText(text)

    def _toggle_pause(self) -> None:
        if self.worker:
            paused = self.worker.toggle_pause()
            self.pause_button.setText("继续" if paused else "暂停")
            self.scan_status.setText("检测已暂停，将在当前项目完成后停止" if paused else "检测已继续")

    def _cancel_check(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.scan_status.setText("正在安全取消…")

    def _check_completed(self, report: CheckReport, config: dict, license_data: dict) -> None:
        self.current_report = report
        self.config = config
        self.license = license_data
        save_config(config)
        save_license(license_data)
        save_report(report.to_dict())
        self.scan_core.finish(report.overall_status.value)
        self.scan_status.setText("检测完成 · 已生成真实数据报告")
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress.setValue(100)
        self._render_report()
        self._render_problems()
        self._render_network()
        self._refresh_history()
        self._update_license_label()
        if self.config.get("result_sound", True): QApplication.beep()
        if self.config.get("auto_open_report", True): QTimer.singleShot(650, lambda: self._show_page(2))

    def _check_failed(self, message: str) -> None:
        self.scan_core.finish("UNKNOWN")
        self.scan_status.setText("检测未完成")
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.logger.error("check_failed %s", message)
        QMessageBox.critical(self, "检测未完成", message)

    def _render_report(self) -> None:
        if not self.current_report:
            return
        report = self.current_report
        colors = {Status.PASS: COLORS["pass"], Status.WARNING: COLORS["warning"], Status.FAIL: COLORS["fail"], Status.UNKNOWN: COLORS["unknown"]}
        readiness_labels = {
            "READY": "可以开播", "READY_WITH_RISK": "可以开播 · 存在风险",
            "NOT_READY": "暂不建议开播", "INCOMPLETE": "关键检测未完成",
        }
        self.report_badge.setText(readiness_labels.get(report.readiness_level, report.overall_status.value))
        self.report_badge.setStyleSheet(f"color:{colors[report.overall_status]};")
        counts = {status: sum(item.status == status for item in report.items) for status in Status}
        baseline = report.baseline_delta or {}
        comparison = ""
        if baseline.get("available"):
            new_count, resolved_count = len(baseline.get("new_issues", [])), len(baseline.get("resolved", []))
            upload = baseline.get("upload_mbps", {})
            upload_text = f" · 稳定上传较上次 {'+' if upload.get('change', 0) >= 0 else ''}{upload.get('change')} Mbps" if upload else ""
            comparison = f"\n与上次比较：新增 {new_count} 项 · 已恢复 {resolved_count} 项{upload_text}"
        self.report_conclusion.setText(f"{report.conclusion}\n{counts[Status.FAIL]} 个严重问题 · {counts[Status.WARNING]} 个风险项 · {counts[Status.PASS]} 项正常 · {counts[Status.UNKNOWN]} 项未完成{comparison}")
        problems = [item for item in report.items if item.status != Status.PASS]
        safe = [item for item in problems if item.repairable and item.repair_level == "safe"]
        self.repair_all_button.setEnabled(bool(safe))
        self.report_metrics["problems"].set_value(str(len(problems)))
        ip = report.ip_profile
        self.report_metrics["ip"].set_value(str(ip.get("ip") or "--"))
        speed = report.network_snapshot.get("network.throughput", {})
        self.report_metrics["down"].set_value(str(speed.get("download_mbps") or "--"))
        self.report_metrics["up"].set_value(str(speed.get("upload_mbps") or "--"))
        route = report.network_snapshot.get("network.target_route", {}).get("target_probes", [])
        latency_values = [item.get("connect_ms") for item in route if item.get("connect_ms") is not None]
        self.report_metrics["latency"].set_value(str(round(sum(latency_values) / len(latency_values))) if latency_values else "--")
        self.home_status.set_value(readiness_labels.get(report.readiness_level, report.overall_status.value))
        self.home_problems.set_value(str(len(problems)))
        self.home_region.set_value(get_region(report.target_region_id).country_code)
        while self.report_modules.count():
            item = self.report_modules.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        categories: dict[str, list[CheckResult]] = {}
        for result in report.items:
            categories.setdefault(result.category, []).append(result)
        for index, (category, items) in enumerate(categories.items()):
            pane = card()
            box = QVBoxLayout(pane)
            head = QHBoxLayout()
            title = QLabel(category)
            title.setProperty("subheading", True)
            head.addWidget(title)
            head.addStretch()
            worst = sorted(items, key=lambda item: SEVERITY[item.status])[0].status
            badge = QLabel(worst.value)
            badge.setStyleSheet(f"color:{colors[worst]};font-weight:800")
            head.addWidget(badge)
            box.addLayout(head)
            details = QLabel(f"{sum(item.status == Status.PASS for item in items)} 项正常 · {sum(item.status != Status.PASS for item in items)} 项需关注")
            details.setProperty("muted", True)
            box.addWidget(details)
            open_button = QPushButton("查看详情")
            open_button.clicked.connect(lambda _=False, category_name=category: self._open_category(category_name))
            box.addWidget(open_button)
            self.report_modules.addWidget(pane, index // 3, index % 3)

    def _open_category(self, category: str) -> None:
        mapping = {"网络环境": 4}
        if category in mapping:
            self._show_page(mapping[category])
        else:
            self.problem_filter.setCurrentText("全部问题")
            self._show_page(3)

    def _render_problems(self) -> None:
        while self.problem_layout.count():
            item = self.problem_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.current_report:
            self.problem_summary.setText("尚无检测结果")
            self.problem_layout.addStretch()
            return
        selected = self.problem_filter.currentText()
        statuses = {"失败": Status.FAIL, "风险": Status.WARNING, "未完成": Status.UNKNOWN}
        problems = [item for item in self.current_report.items if item.status != Status.PASS]
        if selected in statuses:
            problems = [item for item in problems if item.status == statuses[selected]]
        safe_count = sum(item.repairable and item.repair_level == "safe" for item in problems)
        self.problem_summary.setText(f"{len(problems)} 个问题 · {safe_count} 个可安全处理")
        for item in sorted(problems, key=lambda result: SEVERITY[result.status]):
            pane = QFrame()
            pane.setProperty("problemCard", True)
            pane.setProperty("severity", item.status.value)
            box = QVBoxLayout(pane)
            box.setContentsMargins(18, 15, 18, 15)
            head = QHBoxLayout()
            badge = QLabel(item.status.value)
            badge.setStyleSheet(f"color:{COLORS[item.status.value.lower()]};font-weight:900")
            head.addWidget(badge)
            title = QLabel(item.title)
            title.setProperty("subheading", True)
            head.addWidget(title)
            head.addStretch()
            value = QLabel(item.value)
            value.setStyleSheet("font-size:16px;font-weight:800")
            head.addWidget(value)
            box.addLayout(head)
            evidence = QLabel("检测证据：" + (" · ".join(item.evidence) if item.evidence else item.value))
            evidence.setWordWrap(True)
            evidence.setProperty("muted", True)
            box.addWidget(evidence)
            diagnosis = QLabel("问题定位：" + (item.diagnosis or item.reason or "检测未能确认具体原因"))
            diagnosis.setWordWrap(True)
            box.addWidget(diagnosis)
            impact = QLabel("不处理的影响：" + (item.impact or "当前项目存在未知影响"))
            impact.setWordWrap(True)
            impact.setProperty("impact", True)
            box.addWidget(impact)
            steps = QLabel("处理步骤：" + ("  →  ".join(item.solutions) if item.solutions else "当前没有可执行的处理动作"))
            steps.setWordWrap(True)
            steps.setProperty("muted", True)
            box.addWidget(steps)
            footer = QHBoxLayout()
            source = QLabel(f"数据来源：{item.data_source} · 可信度：{item.confidence}")
            source.setProperty("muted", True)
            footer.addWidget(source)
            footer.addStretch()
            if item.repairable and item.repair_id:
                action = QPushButton("立即安全处理" if item.repair_level == "safe" else "确认后处理")
                action.setProperty("primary", item.repair_level == "safe")
                action.setProperty("gold", item.repair_level != "safe")
                action.clicked.connect(lambda _=False, current=item: self._repair_item(current))
            else:
                action = QPushButton("按步骤处理后复检")
                action.clicked.connect(lambda: self._start_check("daily_preflight"))
            footer.addWidget(action)
            box.addLayout(footer)
            self.problem_layout.addWidget(pane)
        self.problem_layout.addStretch()

    def _render_network(self) -> None:
        self.network_details.clear()
        if not self.current_report:
            return
        report = self.current_report
        ip = report.ip_profile
        self.network_metrics["location"].set_value(f"{ip.get('country_code') or '--'} · {ip.get('city') or '--'}")
        self.network_metrics["isp"].set_value(str(ip.get("isp") or ip.get("asn") or "--")[:24])
        speed = report.network_snapshot.get("network.throughput", {})
        self.network_metrics["download"].set_value(str(speed.get("download_mbps") or "--"))
        self.network_metrics["upload"].set_value(str(speed.get("upload_mbps") or "--"))
        self.network_metrics["variation"].set_value(str(speed.get("upload_variation_percent") or "--"))
        probes = report.network_snapshot.get("network.target_route", {}).get("target_probes", [])
        values = [probe.get("connect_ms") for probe in probes if probe.get("connect_ms") is not None]
        self.network_metrics["latency"].set_value(str(round(sum(values) / len(values))) if values else "--")
        rows = [
            ("IP 地址", ip.get("ip") or "未获取"),
            ("IP 协议", ip.get("ip_version") or "待确认"),
            ("地理位置", " ".join(str(ip.get(key) or "") for key in ("country", "region", "city")).strip() or "待确认"),
            ("经度 / 纬度", f"{ip.get('longitude', '待确认')} / {ip.get('latitude', '待确认')}"),
            ("ASN", f"AS{ip.get('asn')}" if ip.get("asn") and not str(ip.get("asn")).upper().startswith("AS") else (ip.get("asn") or "待确认")),
            ("网络服务商 ISP", ip.get("isp") or "待确认"),
            ("网络组织", ip.get("organization") or ip.get("network_name") or "待确认"),
            ("CIDR 网段", ip.get("cidr") or "待确认"),
            ("注册国家 / 注册局", f"{ip.get('registered_country') or '待确认'} / {ip.get('registry') or '待确认'}"),
            ("时区", f"{ip.get('timezone') or '待确认'} {ip.get('timezone_utc') or ''}".strip()),
            ("住宅 / 家宽", self._verified_label(ip.get("residential_status"))),
            ("原生 IP", self._verified_label(ip.get("native_status"))),
            ("风险信息", self._risk_label(ip)),
        ]
        self.network_identity_table.setRowCount(len(rows))
        for row_index, (label, value) in enumerate(rows):
            self.network_identity_table.setItem(row_index, 0, QTableWidgetItem(str(label)))
            self.network_identity_table.setItem(row_index, 1, QTableWidgetItem(str(value)))
        sources = "、".join(ip.get("sources") or [ip.get("source") or "无可用来源"])
        confidence = {"high": "高", "medium": "中", "low": "低"}.get(ip.get("confidence"), ip.get("confidence") or "低")
        self.network_source_label.setText(f"数据来源：{sources} · 综合可信度：{confidence}")
        for result in [item for item in report.items if item.check_id.startswith("network.")]:
            level = result.status.value.lower()
            self.network_details.append_event(CheckEvent("network_result", "network", f"{result.title}｜{result.value}｜{result.diagnosis}｜来源 {result.data_source}", level))

    @staticmethod
    def _verified_label(value) -> str:
        if value is True or str(value).lower() in {"true", "yes", "residential", "native"}:
            return "数据源已确认"
        if value is False or str(value).lower() in {"false", "no"}:
            return "数据源显示否"
        return "待确认（当前数据源无法可靠证明）"

    @staticmethod
    def _risk_label(ip: dict) -> str:
        value = ip.get("risk_label")
        if not value or str(value).lower() in {"unverified", "unknown", "none"}:
            return "待确认（未接入可信风险数据库）"
        return str(value)

    def _export_network_report(self) -> None:
        if not self.current_report:
            QMessageBox.information(self, "尚无网络报告", "请先完成一次开播检查。")
            return
        payload = {
            "product": APP_NAME, "version": APP_VERSION, "report_id": self.current_report.report_id,
            "checked_at": self.current_report.checked_at, "target_region_id": self.current_report.target_region_id,
            "ip_profile": self.current_report.ip_profile, "network_snapshot": self.current_report.network_snapshot,
            "analysis_items": [item.to_dict() for item in self.current_report.items if item.check_id.startswith("network.")],
            "notice": "住宅、原生、纯净度和风险仅在数据源提供可核验证据时给出结论；待确认不等于异常。",
        }
        path, _ = QFileDialog.getSaveFileName(self, "导出网络报告", f"JC网络检测报告-{self.current_report.report_id}.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _repair_item(self, item: CheckResult, recheck: bool = True) -> bool:
        if item.repair_level == "confirm" and QMessageBox.question(self, "确认系统修改", "该操作会修改 Windows 设置，是否继续？") != QMessageBox.Yes:
            return False
        self._show_page(1)
        self.scan_core.start()
        self.scan_status.setText(f"正在处理：{item.title}")
        event = CheckEvent("repair_started", "repair", f"读取原始状态：{item.title}", "warning")
        self.terminal.append_event(event)
        ok, message, recovery = run_repair(item.repair_id, target_timezone=get_region(self.config.get("target_region_id")).windows_timezone)
        self.terminal.append_event(CheckEvent("repair_finished", "repair", message, "success" if ok else "fail"))
        self.scan_core.finish("PASS" if ok else "FAIL")
        if ok:
            item.details["repair_result"] = message
            item.details["repair_recovery"] = recovery
            item.repair_outcome = {"status": "success", "message": message, "before": item.value, "recovery": recovery, "verified": False, "timestamp": datetime.now(timezone.utc).isoformat()}
            if self.current_report:
                self.current_report.repair_events.append({"repair_id": item.repair_id, "before": item.value, "message": message, "recovery": recovery, "status": "success", "timestamp": datetime.now(timezone.utc).isoformat()})
            QMessageBox.information(self, "处理完成", f"{message}\n\n即将自动重新检测，确认问题是否恢复。")
            if recheck:
                QTimer.singleShot(250, lambda: self._start_check("daily_preflight"))
            return True
        item.repair_outcome = {"status": "failed", "message": message, "before": item.value, "verified": False, "timestamp": datetime.now(timezone.utc).isoformat()}
        QMessageBox.warning(self, "自动处理未完成", f"{message}\n\n请按照问题卡片中的步骤人工处理后复检。")
        return False

    def _repair_all(self) -> None:
        if not self.current_report:
            return
        items = [item for item in self.current_report.items if item.status != Status.PASS and item.repairable and item.repair_id and item.repair_level == "safe"]
        if not items:
            QMessageBox.information(self, "没有安全修复项", "当前问题需要确认修改或人工处理。")
            return
        success = sum(self._repair_item(item, recheck=False) for item in items)
        QMessageBox.information(self, "安全处理完成", f"已处理 {success}/{len(items)} 个安全项目，即将执行完整复检。")
        QTimer.singleShot(250, lambda: self._start_check("daily_preflight"))

    def _upload_report(self) -> None:
        if not self.current_report:
            QMessageBox.information(self, "尚无报告", "请先完成一次开播检查。")
            return
        if self.config.get("upload_confirm", True) and QMessageBox.question(self, "主动上传报告", "报告只包含技术检测结果，不包含账号密码、Cookie 或个人文件。确认上传？") != QMessageBox.Yes:
            return
        try:
            api = ClientApi(self.config["api_base"], self.config.get("device_token", ""))
            api.upload_report(self.current_report.to_dict())
            self.current_report.uploaded = True
            save_report(self.current_report.to_dict())
            QMessageBox.information(self, "上传成功", "管理后台已经收到本次报告。")
        except ApiError as exc:
            queue_report(self.current_report.report_id)
            QMessageBox.warning(self, "暂未上传", f"{exc}\n报告已加入待同步队列。")

    def _export_current_report(self) -> None:
        if not self.current_report:
            QMessageBox.information(self, "尚无报告", "请先完成一次开播检查。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出报告", f"TK开播报告-{self.current_report.report_id}.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(self.current_report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_history(self) -> None:
        if not hasattr(self, "history_table"):
            return
        query = self.history_search.text().lower() if hasattr(self, "history_search") else ""
        reports = [report for report in load_reports() if not query or query in (report.get("target_region_id", "") + report.get("run_mode", "") + report.get("report_id", "")).lower()]
        self.history_table.setRowCount(len(reports))
        self.history_table.setProperty("reports", reports)
        for row, report in enumerate(reports):
            region = get_region(report.get("target_region_id")).label
            mode = "环境配置" if report.get("run_mode") == "environment_setup" else "日常检查"
            values = (report.get("checked_at", "")[:19].replace("T", " "), mode, region, report.get("conclusion", ""), report.get("overall_status", ""), report.get("report_id", ""))
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _export_history(self) -> None:
        rows = self.history_table.selectionModel().selectedRows()
        reports = self.history_table.property("reports") or []
        if not rows:
            QMessageBox.information(self, "请选择报告", "请先选择需要导出的历史报告。")
            return
        report = reports[rows[0].row()]
        path, _ = QFileDialog.getSaveFileName(self, "导出报告", f"TK开播报告-{report['report_id']}.json", "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def _activation(self) -> None:
        ActivationDialog(self, self._activate_code).exec()

    def _activate_code(self, code: str) -> bool:
        try:
            api = ClientApi(self.config["api_base"], self.config.get("device_token", ""))
            if not api.token:
                data = api.register(self.config, APP_VERSION)
                self.config["device_token"] = api.token
                save_config(self.config)
                self.license.update(data.get("license", {}))
            data = api.activate(code)
            self.license.update(data["license"])
            self.license["lease_until"] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            save_license(self.license)
            self._update_license_label()
            QMessageBox.information(self, "激活成功", "授权已经生效。")
            return True
        except ApiError as exc:
            QMessageBox.warning(self, "激活失败", str(exc))
            return False

    def _update_license_label(self) -> None:
        tier = self.license.get("tier", "FREE")
        expires = self.license.get("expires_at", "")
        if expires:
            try:
                remaining = f"剩余 {max(0, (datetime.fromisoformat(expires) - datetime.now(timezone.utc)).days)} 天"
            except ValueError:
                remaining = "有效期校验中"
        else:
            credits = self.license.get("credits", -1)
            remaining = "永久授权" if credits == -1 else f"剩余 {credits} 次"
        text = f"授权状态\n{tier} · {remaining}"
        self.license_label.setText(text)
        if hasattr(self, "service_license"):
            self.service_license.setText(text.replace("\n", "  ·  "))

    def _save_settings_silent(self) -> None:
        region_id = self.default_region_setting.currentData() if hasattr(self, "default_region_setting") else self.region.currentData()
        self.config.update({
            "target_region_id": region_id,
            "startup_page": self.startup_page_select.currentData(), "remember_last_page": self.remember_last_page.isChecked(),
            "theme_id": self.theme_select.currentData(), "effects_level": self.effects_select.currentData(),
            "font_scale": self.font_select.currentData(), "test_mode": self.test_mode_select.currentData(),
            "result_sound": self.result_sound.isChecked(), "auto_open_report": self.auto_open_report.isChecked(),
            "update_check_on_start": self.update_on_start.isChecked(), "report_retention_days": self.retention_select.currentData(),
            "show_check_tips": self.show_check_tips.isChecked(), "auto_compare_reports": self.auto_compare_reports.isChecked(),
            "upload_confirm": self.upload_confirm.isChecked(), "privacy_confirm_upload": self.upload_confirm.isChecked(),
            "reduced_effects": self.effects_select.currentData() == "light",
        })
        region_index = self.region.findData(region_id)
        if region_index >= 0: self.region.setCurrentIndex(region_index)
        save_config(self.config)
        reduced = self.config["effects_level"] == "light"
        self.backdrop.set_reduced(reduced); self.scan_core.set_reduced(reduced)
        self._apply_theme()

    def _save_settings(self) -> None:
        self._save_settings_silent()
        QMessageBox.information(self, "保存成功", "设置已保存。视觉特效设置已立即生效。")

    def _apply_theme(self) -> None:
        theme_id = self.config.get("theme_id", "obsidian")
        self.setStyleSheet(apply_theme(theme_id, self.config.get("font_scale", "standard")))
        if hasattr(self, "backdrop"): self.backdrop.set_theme(theme_id)
        if hasattr(self, "scan_core"): self.scan_core.set_theme(theme_id)

    def _preview_theme(self, _index: int = -1) -> None:
        if not hasattr(self, "theme_select"): return
        self.config["theme_id"] = self.theme_select.currentData(); self.config["font_scale"] = self.font_select.currentData()
        self._apply_theme()

    def _reset_settings(self) -> None:
        preserved = {key: self.config.get(key) for key in ("device_id", "device_token", "api_base", "target_host")}
        self.config.update(DEFAULT_CONFIG); self.config.update({key: value for key, value in preserved.items() if value})
        save_config(self.config)
        QMessageBox.information(self, "已恢复推荐设置", "推荐设置已恢复，重新打开本页即可看到全部选项。")

    def _open_report_dir(self) -> None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(REPORT_DIR)))

    def _cleanup_local_reports(self) -> None:
        days = int(self.retention_select.currentData())
        removed = cleanup_reports(days)
        self._refresh_history()
        QMessageBox.information(self, "清理完成", "永久保留模式未删除报告。" if days <= 0 else f"已清理 {removed} 份过期报告。")

    def _export_diagnostics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出售后诊断包", str(Path.home() / f"TK诊断包-{datetime.now():%Y%m%d-%H%M}.zip"), "ZIP 文件 (*.zip)")
        if not path: return
        safe_config = {key: value for key, value in self.config.items() if key not in {"device_token"}}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("config-sanitized.json", json.dumps(safe_config, ensure_ascii=False, indent=2))
            log = DATA_DIR / "client.log"
            if log.is_file(): archive.write(log, "client.log")
            for report in sorted(REPORT_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:10]: archive.write(report, f"reports/{report.name}")
        QMessageBox.information(self, "导出完成", "诊断包已生成，可发送给技术支持。")

    def _copy_device_id(self) -> None:
        QApplication.clipboard().setText(self.config.get("device_id", ""))
        QMessageBox.information(self, "已复制", "设备编号已复制到剪贴板。")

    def _show_integrity(self) -> None:
        required = [resource_dir() / name for name in ("app_icon.ico", "收款码.jpg", "客服二维码.png")]
        missing = [path.name for path in required if not path.is_file() or path.stat().st_size == 0]
        if missing:
            QMessageBox.warning(self, "完整性异常", "以下核心资源缺失：\n" + "\n".join(missing) + "\n\n请重新安装最新版。")
        else:
            QMessageBox.information(self, "完整性检查通过", "程序图标、付款二维码和客服二维码资源均完整。")

    def _show_changelog(self) -> None:
        try:
            rows = ClientApi(self.config["api_base"], self.config.get("device_token", "")).changelog().get("releases", [])
            text = "\n\n".join(f"V{row.get('version')} · {row.get('title','')}\n{row.get('details') or row.get('notes','')}" for row in rows[:10]) or "暂无版本记录"
            QMessageBox.information(self, "版本更新记录", text)
        except ApiError as exc:
            QMessageBox.warning(self, "获取失败", str(exc))

    def _check_update(self, _checked: bool = False, silent: bool = False) -> None:
        try:
            data = ClientApi(self.config["api_base"], self.config.get("device_token", "")).update_info()
            if not data.get("available") or data.get("version") == APP_VERSION:
                if not silent:
                    QMessageBox.information(self, "版本检查", "当前已经是可用版本。")
                return
            if QMessageBox.question(self, "发现新版本", f"V{data['version']} · {data.get('title','')}\n\n{data.get('notes','')}\n\n是否立即下载并安装？") != QMessageBox.Yes:
                return
            self._show_page(1)
            self.progress.setValue(0)
            self.scan_status.setText("正在准备更新…")
            self.update_thread = QThread(self)
            self.update_worker = UpdateWorker(data)
            self.update_worker.moveToThread(self.update_thread)
            self.update_thread.started.connect(self.update_worker.run)
            self.update_worker.progress.connect(self._progress)
            self.update_worker.completed.connect(self._update_ready)
            self.update_worker.failed.connect(self._update_failed)
            self.update_worker.completed.connect(self.update_thread.quit)
            self.update_worker.failed.connect(self.update_thread.quit)
            self.update_thread.start()
        except ApiError as exc:
            if silent:
                self.logger.info("startup_update_check_failed %s", exc)
            else:
                QMessageBox.warning(self, "检查失败", str(exc))

    def _update_ready(self, path) -> None:
        try:
            launch_helper(path)
            QApplication.quit()
        except UpdateError as exc:
            self._update_failed(str(exc))

    def _update_failed(self, message: str) -> None:
        self.scan_status.setText("更新未完成")
        QMessageBox.warning(self, "更新失败", message)

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if self.config.get("remember_last_page"):
            self.config["last_page"] = index
            save_config(self.config)
        button = self.nav_group.button(index)
        if button:
            button.setChecked(True)

    def closeEvent(self, event) -> None:
        if self.worker and self.thread and self.thread.isRunning():
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(2500)
        if self.prepare_thread and self.prepare_thread.isRunning():
            self.prepare_thread.quit()
            self.prepare_thread.wait(1500)
        event.accept()
