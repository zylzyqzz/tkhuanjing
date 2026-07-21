from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ... import APP_VERSION


class DeviceStatusScreen(QWidget):
    sync_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 28, 40, 28)
        title = QLabel("设备状态")
        title.setProperty("title", True)
        layout.addWidget(title)
        self.summary = QLabel("正在同步设备在线状态……")
        self.summary.setProperty("muted", True)
        layout.addWidget(self.summary)

        card = QFrame()
        card.setProperty("card", True)
        grid = QGridLayout(card)
        grid.setContentsMargins(22, 18, 22, 18)
        grid.setHorizontalSpacing(34)
        grid.setVerticalSpacing(14)
        self.values: dict[str, QLabel] = {}
        fields = (
            ("online", "在线状态"),
            ("version", "客户端版本"),
            ("studio", "LIVE Studio"),
            ("collector", "采集服务"),
            ("cpu", "CPU"),
            ("memory", "内存"),
            ("network", "网络"),
            ("heartbeat", "最后心跳"),
        )
        for index, (key, label) in enumerate(fields):
            row, column = divmod(index, 2)
            box = QFrame()
            box.setProperty("card", True)
            inner = QVBoxLayout(box)
            caption = QLabel(label)
            caption.setProperty("muted", True)
            value = QLabel("—")
            value.setProperty("subhead", True)
            self.values[key] = value
            inner.addWidget(caption)
            inner.addWidget(value)
            grid.addWidget(box, row, column)
        layout.addWidget(card)

        self.config_note = QLabel("配置尚未同步")
        self.config_note.setProperty("muted", True)
        layout.addWidget(self.config_note)
        sync = QPushButton("立即重新同步")
        sync.setProperty("primary", True)
        sync.clicked.connect(self.sync_requested)
        layout.addWidget(sync)
        layout.addStretch()

    def set_state(self, bootstrap: dict, heartbeat: dict | None = None, metrics: dict | None = None) -> None:
        heartbeat = heartbeat or {}
        metrics = metrics or {}
        response = heartbeat.get("response", {})
        feature_enabled = bootstrap.get("features", {}).get("device_heartbeat", True)
        self.values["online"].setText("在线" if response.get("server_time") else "等待心跳")
        self.values["version"].setText(f"V{APP_VERSION}")
        studio = metrics.get("live_software", {}).get("running")
        self.values["studio"].setText("运行中" if studio else "未运行")
        collector = metrics.get("collection", {}).get("status", "unknown")
        self.values["collector"].setText({"healthy": "正常", "degraded": "异常", "offline": "离线"}.get(collector, "未知"))
        values = metrics.get("metrics", {})
        self.values["cpu"].setText(self._percent(values.get("cpu_percent")))
        self.values["memory"].setText(self._percent(values.get("memory_percent")))
        latency, upload = values.get("network_latency_ms"), values.get("upload_mbps")
        parts = []
        if latency is not None:
            parts.append(f"{latency:.0f} ms")
        if upload is not None:
            parts.append(f"上传 {upload:.1f} Mbps")
        self.values["network"].setText(" · ".join(parts) or "待采样")
        server_time = response.get("server_time")
        self.values["heartbeat"].setText(self._time(server_time) if server_time else "尚未成功")
        self.summary.setText("状态心跳正常，企业后台可以看到这台电脑。" if response.get("server_time") else "客户端正在后台同步，断网数据会在恢复后自动补传。")
        version = bootstrap.get("config_version", "—")
        interval = bootstrap.get("config", {}).get("heartbeat_interval_seconds", "—")
        self.config_note.setText(f"配置版本 {version} · 心跳周期 {interval} 秒" + (" · 实时状态功能已暂停" if not feature_enabled else ""))

    def set_error(self, message: str) -> None:
        self.summary.setText(message)
        self.values["online"].setText("同步异常")

    @staticmethod
    def _percent(value) -> str:
        return f"{float(value):.0f}%" if isinstance(value, (int, float)) else "待采样"

    @staticmethod
    def _time(value) -> str:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
        except (TypeError, ValueError):
            return str(value or "尚未成功")
