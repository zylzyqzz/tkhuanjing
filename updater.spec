# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path.cwd()
a = Analysis([str(root / "client_src" / "updater.py")], pathex=[str(root / "client_src")], binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TKUpdater", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, disable_windowed_traceback=False, icon=str(root / "assets" / "app_icon.ico"))
