import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox
import urllib.request


APP_VERSION = "1.0.3"
UPDATE_URLS = [
    "https://tk.aimj.xin/api/client/update",
]


def fetch_update():
    last = None
    for url in UPDATE_URLS:
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last = exc
    raise last or RuntimeError("无法连接更新服务器")


def version_key(value):
    try:
        return tuple(int(x) for x in str(value).split("."))
    except Exception:
        return (0,)


def download_checked(url, expected, target):
    with urllib.request.urlopen(url, timeout=120) as response, open(target, "wb") as output:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            output.write(block)
    if expected:
        digest = hashlib.sha256()
        with open(target, "rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest().lower() != expected.lower():
            os.remove(target)
            raise RuntimeError("更新文件校验失败")


def replace_self(new_file):
    current = os.path.abspath(sys.executable)
    batch = os.path.join(tempfile.gettempdir(), "tk_platform_update.bat")
    with open(batch, "w", encoding="utf-8") as file:
        file.write(
            f'@echo off\r\ntimeout /t 2 /nobreak >nul\r\n'
            f'move /y "{new_file}" "{current}" >nul\r\n'
            f'start "" "{current}"\r\ndel "%~f0"\r\n'
        )
    subprocess.Popen(["cmd", "/c", batch], creationflags=0x08000000)


def launch_core():
    base = os.path.join(tempfile.gettempdir(), "tk_platform_client_core")
    os.makedirs(base, exist_ok=True)
    bundle = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(tempfile.gettempdir(), "tk_platform_launcher.log"), "a", encoding="utf-8") as log:
        log.write(f"bundle={bundle} base={base} frozen={getattr(sys, '_MEIPASS', None)}\\n")
    for name in ("client_core.exe", "客服二维码.png", "收款码.jpg"):
        source = os.path.join(bundle, name)
        if os.path.exists(source):
            shutil.copy2(source, os.path.join(base, name))
    core = os.path.join(base, "client_core.exe")
    if not os.path.exists(core):
        installed = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "client_core.exe")
        if os.path.exists(installed):
            base = os.path.dirname(installed)
            core = installed
    if not os.path.exists(core):
        messagebox.showerror("客户端启动失败", "核心客户端文件缺失，请重新运行安装程序修复安装。")
        return
    subprocess.Popen([core], cwd=base)


def main():
    root = tk.Tk()
    root.withdraw()
    try:
        info = fetch_update()
        if version_key(info.get("version", "0.0.0")) > version_key(APP_VERSION):
            notes = info.get("notes") or "本次更新包含功能优化与问题修复。"
            if messagebox.askyesno("发现新版本", f"发现版本 {info['version']}\\n\\n更新内容：\\n{notes}\\n\\n是否立即更新？"):
                new_file = os.path.abspath(sys.executable) + ".new"
                download_checked(info["url"], info.get("sha256", ""), new_file)
                replace_self(new_file)
                root.destroy()
                return
    except Exception:
        pass
    root.destroy()
    launch_core()


if __name__ == "__main__":
    main()
