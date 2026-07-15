from __future__ import annotations

import logging
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME
from .storage import configure_logging
from .ui.main_window import MainWindow, resource_dir


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setOrganizationName("维度光年")
    QFontDatabase.addApplicationFont(str(resource_dir() / "NotoSansSC-VF.ttf"))
    logger = configure_logging()

    def handle_exception(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb)); logger.critical("unhandled_exception\n%s", text)
        QMessageBox.critical(None, "程序发生异常", "程序遇到未处理问题，详细信息已写入本地日志。\n请重新启动或联系技术支持。")

    sys.excepthook = handle_exception
    window = MainWindow(); window.show(); return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
