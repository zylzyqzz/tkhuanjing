# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path.cwd()
a = Analysis([str(root / "run_updater_v2.py")], pathex=[str(root)], hiddenimports=["psutil"], excludes=["PySide6", "fastapi", "sqlalchemy"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TKUpdater", debug=False, strip=False, upx=False, console=False, icon=str(root / "assets" / "app_icon.ico"))
