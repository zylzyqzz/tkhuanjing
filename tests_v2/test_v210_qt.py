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
    dialog.close(); window.close()
