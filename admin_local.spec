# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path.cwd()
a = Analysis(
    [str(root / "local_admin_launcher.py")], pathex=[str(root)],
    datas=[(str(root / "admin" / "dist"), "admin/dist")],
    hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on"],
    excludes=["PySide6", "tkinter", "pytest"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TKAdminLocal", debug=False, strip=False, upx=True, console=False, icon=str(root / "assets" / "app_icon.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="TKAdminLocal")
