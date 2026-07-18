# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path.cwd()
a = Analysis(
    [str(root / "run_client_v2.py")], pathex=[str(root)],
    datas=[(str(root / "assets"), "assets")],
    hiddenimports=["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "psutil", "httpx"],
    excludes=["tkinter", "pytest", "sqlalchemy", "fastapi", "alembic"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VDLiveCheck", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False, icon=str(root / "assets" / "app_icon.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="VDLiveCheck")
