import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from client_v2.state import ClientState
from client_v2.ui.account_dialog import AccountDialog
from client_v2.ui.app_window import AppWindow
from client_v2.ui.tokens import RING_OUTER_D, SIDEBAR_W, WINDOW_H, WINDOW_W


def test_new_ui_is_single_fixed_design_and_account_flow_constructs(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    window = AppWindow()
    dialog = AccountDialog(window)
    assert window.size().toTuple() == (WINDOW_W, WINDOW_H)
    assert window.sidebar.width() == SIDEBAR_W
    assert window.scan.ring.width() == RING_OUTER_D
    assert window.machine.state == ClientState.IDLE
    assert dialog.tabs.count() == 4
    window._navigate("device")
    assert window.stack.currentWidget() is window.device_page
    window._navigate("help")
    assert window.stack.currentWidget() is window.help_page
    window._apply_device_bootstrap({
        "organization":{"name":"测试企业"},
        "binding":{"room_id":1,"room_name":"一号直播间","account_name":"主账号","anchor_name":"主播 A"},
        "features":{"environment_check":True,"device_binding":True,"device_heartbeat":True},
        "config":{"heartbeat_interval_seconds":33},
        "config_version":12,
        "minimum_version":"2.1.0",
    })
    assert window.v2_heartbeat_timer.interval() == 33000
    assert "一号直播间" in window.room_status.text()
    window.device_page.set_state(window._device_bootstrap,{"response":{"server_time":"2026-07-20T10:00:00Z"}},{"live_software":{"running":True},"collection":{"status":"healthy"},"metrics":{"cpu_percent":20,"memory_percent":40}})
    assert window.device_page.values["online"].text() == "在线"
    assert window.device_page.values["studio"].text() == "运行中"
    dialog.close(); window.close()
