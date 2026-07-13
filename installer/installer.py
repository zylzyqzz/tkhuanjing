import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from pathlib import Path


def install():
    bundle = Path(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
    candidates = [bundle / "client_launcher.exe"] + [p for p in bundle.glob("*.exe") if p.name != Path(sys.executable).name]
    source = next((str(p) for p in candidates if p.exists()), None)
    if not source:
        raise FileNotFoundError("安装程序内缺少客户端文件")
    target_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "WeiDuTKClient")
    target = os.path.join(target_dir, "WeiDuTKClient.exe")
    icon_source = os.path.join(str(bundle), "app_icon.ico")
    icon_target = os.path.join(target_dir, "app_icon.ico")
    os.makedirs(target_dir, exist_ok=True)
    shutil.copy2(source, target)
    if os.path.exists(icon_source):
        shutil.copy2(icon_source, icon_target)
    desktop = subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"], text=True, creationflags=0x08000000).strip()
    temp_shortcut = os.path.join(desktop, "WeiDuTKClient.lnk")
    final_shortcut = os.path.join(desktop, "\u7ef4\u5ea6TK\u73af\u5883\u52a9\u624b.lnk")
    ps = "$desk='%s'; Get-ChildItem -LiteralPath $desk -Filter 'client-*.lnk' -ErrorAction SilentlyContinue | Remove-Item -Force; $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%s'); $s.TargetPath='%s'; $s.WorkingDirectory='%s'; $s.IconLocation='%s,0'; $s.Description='TK Client'; $s.Save()" % (desktop.replace("'", "''"), temp_shortcut.replace("'", "''"), target.replace("'", "''"), target_dir.replace("'", "''"), icon_target.replace("'", "''"))
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], creationflags=0x08000000, check=False)
    if os.path.exists(temp_shortcut):
        if os.path.exists(final_shortcut):
            os.remove(final_shortcut)
        os.rename(temp_shortcut, final_shortcut)
    subprocess.Popen([target], cwd=target_dir)


root = tk.Tk()
root.title("TK环境助手安装")
root.geometry("440x230")
root.resizable(False, False)
tk.Label(root, text="TK环境助手", font=("Microsoft YaHei", 20, "bold")).pack(pady=(28, 8))
tk.Label(root, text="安装客户端并创建桌面快捷方式", font=("Microsoft YaHei", 11)).pack(pady=4)
tk.Label(root, text="安装完成后可从桌面快捷方式启动", fg="#687080").pack(pady=4)
def do_install():
    try:
        install()
        root.destroy()
    except Exception as exc:
        messagebox.showerror("安装失败", "客户端安装失败：\\n" + str(exc), parent=root)


tk.Button(root, text="立即安装", width=18, height=2, command=do_install).pack(pady=18)
root.mainloop()
