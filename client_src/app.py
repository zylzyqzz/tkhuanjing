from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import uuid

from api import ApiError, ClientApi
from checks import (
    check_client,
    check_devices,
    check_network,
    check_performance,
    check_streaming_software,
    check_system,
    merged_profile,
    run_repair,
)
from models import CheckReport, CheckResult
from storage import (
    APP_DIR,
    append_log,
    load_config,
    load_license,
    load_reports,
    save_config,
    save_license,
    save_report,
)


APP_NAME = "维度 TikTok 直播开播助手"
APP_VERSION = "2.0.0"
DISCLAIMER = "本软件仅判断电脑、网络、设备和直播软件的技术准备情况，不代表平台账号审核、流量或开播权限结果。"
CHANGELOG = "2.0.0\n• 全新开播前检测首页\n• 网络、性能、直播软件、设备、系统和客户端完整性检测\n• 本地报告、后台上传与修复建议\n• 设备绑定和短期离线授权"


def resource_dir() -> Path:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")),
        Path(sys.executable).parent,
        Path(__file__).resolve().parent.parent / "assets",
    ]
    for candidate in candidates:
        if candidate and (candidate / "收款码.jpg").exists():
            return candidate
    return candidates[-1]


def display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value


class LiveCheckApp(tk.Tk):
    COLORS = {
        "bg": "#0b1120", "panel": "#111a2e", "panel2": "#17213a", "text": "#eef4ff",
        "muted": "#8fa1c1", "blue": "#4388ff", "green": "#2dd4a7", "yellow": "#f5c451",
        "red": "#ff637d", "border": "#273552",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1120x760")
        self.minsize(960, 650)
        self.configure(bg=self.COLORS["bg"])
        self.config_data = load_config()
        self.license_data = load_license()
        self.api = ClientApi(self.config_data["api_base"], self.config_data["device_id"], self.config_data.get("device_token", ""))
        self.profile = merged_profile(None)
        self.current_report: dict | None = None
        self.current_results: dict[str, CheckResult] = {}
        self.latest_update_info: dict = {}
        self.running = False
        self._images: list[object] = []
        self._configure_style()
        self._build()
        self._load_history()
        self._refresh_header()
        threading.Thread(target=self._bootstrap_online, daemon=True).start()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=self.COLORS["bg"])
        style.configure("Panel.TFrame", background=self.COLORS["panel"])
        style.configure("TLabel", background=self.COLORS["bg"], foreground=self.COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Panel.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=self.COLORS["bg"], foreground=self.COLORS["text"], font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Hero.TButton", background=self.COLORS["blue"], foreground="white", borderwidth=0, font=("Microsoft YaHei UI", 13, "bold"), padding=(24, 16))
        style.map("Hero.TButton", background=[("active", "#65a0ff"), ("disabled", "#42506b")])
        style.configure("TButton", background=self.COLORS["panel2"], foreground=self.COLORS["text"], borderwidth=1, padding=(13, 8), font=("Microsoft YaHei UI", 9))
        style.map("TButton", background=[("active", "#223152")])
        style.configure("Treeview", background=self.COLORS["panel"], fieldbackground=self.COLORS["panel"], foreground=self.COLORS["text"], rowheight=34, borderwidth=0, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", background=self.COLORS["panel2"], foreground=self.COLORS["muted"], font=("Microsoft YaHei UI", 9, "bold"), borderwidth=0)
        style.map("Treeview", background=[("selected", "#244984")])
        style.configure("TEntry", fieldbackground="#0d1629", foreground=self.COLORS["text"], insertcolor="white", padding=7)
        style.configure("TSpinbox", fieldbackground="#0d1629", foreground=self.COLORS["text"], arrowcolor=self.COLORS["text"], padding=7)
        style.configure("Horizontal.TProgressbar", background=self.COLORS["blue"], troughcolor=self.COLORS["panel2"], borderwidth=0)

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(24, 18))
        header.pack(fill="x")
        ttk.Label(header, text="◈  " + APP_NAME, style="Title.TLabel").pack(side="left")
        self.version_label = ttk.Label(header, text=f"V{APP_VERSION} · 服务连接中", foreground=self.COLORS["muted"])
        self.version_label.pack(side="right")

        body = ttk.Frame(self, padding=(24, 0, 24, 20))
        body.pack(fill="both", expand=True)
        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=18, width=270)
        sidebar.pack(side="left", fill="y", padx=(0, 16))
        sidebar.pack_propagate(False)
        content = ttk.Frame(body, style="Panel.TFrame", padding=20)
        content.pack(side="left", fill="both", expand=True)

        ttk.Label(sidebar, text="直播间信息", style="Panel.TLabel", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ttk.Label(sidebar, text="客户名称", style="Muted.TLabel").pack(anchor="w", pady=(16, 5))
        self.customer_var = tk.StringVar(value=self.config_data.get("customer_name", ""))
        ttk.Entry(sidebar, textvariable=self.customer_var).pack(fill="x")
        ttk.Label(sidebar, text="直播间名称", style="Muted.TLabel").pack(anchor="w", pady=(12, 5))
        self.room_var = tk.StringVar(value=self.config_data.get("room_name", "直播间 1"))
        ttk.Entry(sidebar, textvariable=self.room_var).pack(fill="x")
        ttk.Label(sidebar, text="直播码率（Kbps）", style="Muted.TLabel").pack(anchor="w", pady=(12, 5))
        self.bitrate_var = tk.IntVar(value=int(self.config_data.get("bitrate_kbps", 6000)))
        ttk.Spinbox(sidebar, textvariable=self.bitrate_var, from_=1000, to=50000, increment=500).pack(fill="x")
        ttk.Button(sidebar, text="保存直播间信息", command=self._save_room).pack(fill="x", pady=(12, 18))

        ttk.Label(sidebar, text="授权状态", style="Panel.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self.license_label = ttk.Label(sidebar, text="", style="Muted.TLabel", wraplength=225, justify="left")
        self.license_label.pack(fill="x", pady=(8, 8))
        ttk.Button(sidebar, text="激活 / 充值", command=self._activation_dialog).pack(fill="x")
        ttk.Separator(sidebar).pack(fill="x", pady=18)
        ttk.Label(sidebar, text="设备编号", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text=self.config_data["device_id"], style="Panel.TLabel", wraplength=225).pack(anchor="w", pady=(4, 14))
        ttk.Button(sidebar, text="付款二维码", command=lambda: self._show_qr("付款二维码", "收款码.jpg")).pack(fill="x", pady=3)
        ttk.Button(sidebar, text="联系客服", command=lambda: self._show_qr("客服二维码", "客服二维码.png")).pack(fill="x", pady=3)
        ttk.Button(sidebar, text="关于与更新说明", command=self._about).pack(fill="x", pady=3)

        top = ttk.Frame(content, style="Panel.TFrame")
        top.pack(fill="x")
        self.status_badge = tk.Label(top, text="尚未检测", bg="#273552", fg="white", font=("Microsoft YaHei UI", 11, "bold"), padx=16, pady=8)
        self.status_badge.pack(side="left")
        self.last_label = ttk.Label(top, text="点击下方按钮完成开播前技术检查", style="Muted.TLabel")
        self.last_label.pack(side="left", padx=14)
        self.upload_button = ttk.Button(top, text="上传本次报告", command=self._upload_current, state="disabled")
        self.upload_button.pack(side="right")

        self.run_button = ttk.Button(content, text="开始开播检查", style="Hero.TButton", command=self._start_check)
        self.run_button.pack(fill="x", pady=(18, 8))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(content, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x")
        self.progress_text = ttk.Label(content, text="等待开始", style="Muted.TLabel")
        self.progress_text.pack(anchor="w", pady=(6, 12))

        columns = ("category", "status", "title", "value", "action")
        self.tree = ttk.Treeview(content, columns=columns, show="headings")
        for key, title, width in [("category", "分类", 70), ("status", "结果", 70), ("title", "检测项目", 150), ("value", "检测值", 180), ("action", "建议", 300)]:
            self.tree.heading(key, text=title); self.tree.column(key, width=width, minwidth=60, stretch=key in {"value", "action"})
        self.tree.tag_configure("PASS", foreground=self.COLORS["green"])
        self.tree.tag_configure("WARNING", foreground=self.COLORS["yellow"])
        self.tree.tag_configure("FAIL", foreground=self.COLORS["red"])
        self.tree.tag_configure("UNKNOWN", foreground=self.COLORS["muted"])
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._result_details)

        history_bar = ttk.Frame(content, style="Panel.TFrame")
        history_bar.pack(fill="x", pady=(12, 0))
        ttk.Label(history_bar, text="最近检查", style="Panel.TLabel", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.history_var = tk.StringVar(value="暂无历史记录")
        ttk.Label(history_bar, textvariable=self.history_var, style="Muted.TLabel").pack(side="left", padx=12)
        ttk.Button(history_bar, text="查看历史", command=self._history_dialog).pack(side="right")

    def _call_ui(self, fn, *args, **kwargs) -> None:
        self.after(0, lambda: fn(*args, **kwargs))

    def _bootstrap_online(self) -> None:
        try:
            response = self.api.register(APP_VERSION, self.room_var.get().strip(), self.customer_var.get().strip())
            self.config_data["device_token"] = self.api.token
            save_config(self.config_data)
            self.profile = merged_profile(self.api.check_profile().get("profile"))
            if response.get("license"):
                self.license_data.update(response["license"]); save_license(self.license_data)
            pending = list(self.license_data.get("pending_events", []))
            for event_id in pending:
                synced = self.api.authorize_check(event_id)
                self.license_data.update(synced.get("license", {}))
            if pending:
                self.license_data["pending_events"] = []
                save_license(self.license_data)
            self.latest_update_info = self.api.update_info()
            self._call_ui(self._set_online, True)
            if self._version_key(self.latest_update_info.get("version", "0.0.0")) > self._version_key(APP_VERSION):
                self._call_ui(self._prompt_update, self.latest_update_info)
        except ApiError:
            self._call_ui(self._set_online, False)

    def _set_online(self, online: bool) -> None:
        self.version_label.configure(text=f"V{APP_VERSION} · {'服务在线' if online else '离线模式'}", foreground=self.COLORS["green"] if online else self.COLORS["yellow"])
        self._refresh_header()

    @staticmethod
    def _version_key(value: str) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in str(value).split("."))
        except ValueError:
            return (0,)

    def _prompt_update(self, info: dict) -> None:
        details = info.get("details") or info.get("notes") or "包含功能优化和问题修复。"
        if not messagebox.askyesno("发现新版本", f"发现版本 {info.get('version')}\n\n{details}\n\n是否立即更新？"):
            return
        updater = Path(sys.executable).parent / "TKUpdater.exe"
        target = Path(sys.executable)
        if not getattr(sys, "frozen", False):
            updater_script = Path(__file__).with_name("updater.py")
            command = [sys.executable, str(updater_script), str(os.getpid()), str(target), info.get("url", ""), info.get("sha256", "")]
        elif updater.exists():
            command = [str(updater), str(os.getpid()), str(target), info.get("url", ""), info.get("sha256", "")]
        else:
            messagebox.showerror("无法更新", "更新助手缺失，请从官网下载最新正式安装程序。")
            return
        subprocess.Popen(command, cwd=str(target.parent), creationflags=0x08000000)
        self.destroy()

    def _save_room(self) -> None:
        self.config_data.update(customer_name=self.customer_var.get().strip(), room_name=self.room_var.get().strip() or "直播间 1", bitrate_kbps=max(1000, int(self.bitrate_var.get())))
        save_config(self.config_data)
        messagebox.showinfo("已保存", "直播间信息已保存。")
        threading.Thread(target=self._bootstrap_online, daemon=True).start()

    def _refresh_header(self) -> None:
        tier = self.license_data.get("tier", "FREE")
        credits = int(self.license_data.get("credits", 0))
        label = "永久授权" if credits < 0 else f"剩余 {credits} 次"
        self.license_label.configure(text=f"{tier} · {label}\n断网时仅在授权有效期内可用")

    def _authorize(self, event_id: str) -> tuple[bool, str]:
        try:
            if not self.api.token:
                self._bootstrap_online()
            response = self.api.authorize_check(event_id)
            self.license_data.update(response.get("license", {})); save_license(self.license_data)
            self._call_ui(self._refresh_header)
            return bool(response.get("allowed")), response.get("message", "")
        except ApiError:
            lease = self.license_data.get("lease_until", "")
            try:
                valid = datetime.fromisoformat(lease.replace("Z", "+00:00")) > datetime.now(timezone.utc)
            except Exception:
                valid = False
            credits = int(self.license_data.get("credits", 0))
            if valid and (credits < 0 or credits > 0):
                if credits > 0:
                    self.license_data["credits"] = credits - 1
                pending = self.license_data.setdefault("pending_events", [])
                pending.append(event_id); save_license(self.license_data)
                self._call_ui(self._refresh_header)
                return True, "离线授权"
            return False, "授权已过期或次数不足，请联网激活/充值"

    def _start_check(self) -> None:
        if self.running:
            return
        self._save_room_silent()
        self.running = True
        self.run_button.configure(state="disabled", text="正在检测…")
        self.upload_button.configure(state="disabled")
        self.progress_var.set(0)
        for row in self.tree.get_children(): self.tree.delete(row)
        threading.Thread(target=self._run_checks, daemon=True).start()

    def _save_room_silent(self) -> None:
        self.config_data.update(customer_name=self.customer_var.get().strip(), room_name=self.room_var.get().strip() or "直播间 1", bitrate_kbps=max(1000, int(self.bitrate_var.get())))
        save_config(self.config_data)

    def _run_checks(self) -> None:
        event_id = str(uuid.uuid4())
        allowed, message = self._authorize(event_id)
        if not allowed:
            self._call_ui(self._finish_blocked, message)
            return
        sections = []
        online = True
        try:
            self.profile = merged_profile(self.api.check_profile().get("profile"))
        except ApiError:
            online = False
        callbacks = [
            lambda cb: check_network(self.api, self.profile, int(self.config_data["bitrate_kbps"]), self.config_data.get("target_host", "v.wdai.cc"), cb),
            lambda cb: check_performance(self.profile, cb),
            check_streaming_software,
            check_devices,
            check_system,
            lambda cb: check_client(resource_dir(), APP_VERSION, online, cb),
        ]
        try:
            for index, callback in enumerate(callbacks):
                def progress(text: str, n=index):
                    self._call_ui(self._set_progress, (n / len(callbacks)) * 100, text)
                try:
                    rows = callback(progress)
                except Exception as exc:
                    append_log(f"check section failed: {exc!r}")
                    rows = [CheckResult(f"section.{index}", "检测", "UNKNOWN", "检测模块异常", "未完成", str(exc), "重新检测或联系技术支持")]
                sections.extend(rows)
                self._call_ui(self._add_results, rows)
            report = CheckReport(self.config_data.get("customer_name", ""), self.config_data.get("room_name", ""), self.config_data["device_id"], APP_VERSION, sections)
            report.finalize(); data = report.to_dict(); save_report(data)
            self._call_ui(self._finish_report, data)
        except Exception as exc:
            append_log(f"full check failed: {exc!r}")
            self._call_ui(self._finish_blocked, f"检测中断：{exc}")

    def _set_progress(self, value: float, text: str) -> None:
        self.progress_var.set(value); self.progress_text.configure(text=text)

    def _add_results(self, rows: list[CheckResult]) -> None:
        labels = {"PASS": "通过", "WARNING": "风险", "FAIL": "失败", "UNKNOWN": "未完成"}
        for item in rows:
            iid = item.check_id
            while self.tree.exists(iid): iid += "_"
            self.current_results[iid] = item
            self.tree.insert("", "end", iid=iid, values=(item.category, labels[item.status], item.title, item.value, item.action or item.reason), tags=(item.status,))

    def _finish_report(self, report: dict) -> None:
        self.running = False; self.current_report = report
        self.run_button.configure(state="normal", text="重新进行开播检查")
        self.upload_button.configure(state="normal")
        self.progress_var.set(100); self.progress_text.configure(text="检查完成 · 双击检测项查看详细说明或执行修复")
        colors = {"PASS": self.COLORS["green"], "WARNING": self.COLORS["yellow"], "FAIL": self.COLORS["red"]}
        labels = {"PASS": "可以开播", "WARNING": "存在风险", "FAIL": "不建议开播"}
        status = report["overall_status"]
        self.status_badge.configure(text=labels.get(status, "检测完成"), bg=colors.get(status, self.COLORS["border"]))
        self.last_label.configure(text=report["conclusion"])
        self._load_history()

    def _finish_blocked(self, message: str) -> None:
        self.running = False; self.run_button.configure(state="normal", text="开始开播检查")
        self.progress_text.configure(text=message)
        messagebox.showwarning("暂时无法检测", message)

    def _upload_current(self) -> None:
        if not self.current_report: return
        self.upload_button.configure(state="disabled")
        def worker():
            try:
                response = self.api.upload_report(self.current_report)
                self.current_report["uploaded"] = True; save_report(self.current_report)
                self._call_ui(messagebox.showinfo, "上传成功", f"报告已上传，编号：{response.get('report_id')}")
            except ApiError as exc:
                self._call_ui(messagebox.showerror, "上传失败", str(exc))
            finally:
                self._call_ui(self.upload_button.configure, state="normal")
        threading.Thread(target=worker, daemon=True).start()

    def _result_details(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected: return
        item = self.current_results.get(selected[0])
        if not item: return
        text = f"{item.title}\n\n检测值：{item.value}\n\n原因：{item.reason or '无'}\n\n建议：{item.action or '无需处理'}"
        if item.repairable and item.repair_id:
            if messagebox.askyesno("检测详情", text + "\n\n该操作可能需要管理员权限。是否执行一键修复？"):
                ok, message = run_repair(item.repair_id); append_log(f"repair {item.repair_id}: {ok} {message}")
                messagebox.showinfo("修复结果" if ok else "修复失败", message)
        else:
            messagebox.showinfo("检测详情", text)

    def _activation_dialog(self) -> None:
        dialog = tk.Toplevel(self); dialog.title("激活 / 充值"); dialog.geometry("500x280"); dialog.configure(bg=self.COLORS["panel"]); dialog.transient(self); dialog.grab_set()
        tk.Label(dialog, text="输入激活码", bg=self.COLORS["panel"], fg=self.COLORS["text"], font=("Microsoft YaHei UI", 15, "bold")).pack(pady=(25, 8))
        tk.Label(dialog, text="TK1：1次 9.9元　TKX：10次 79元　TKV：永久 99元", bg=self.COLORS["panel"], fg=self.COLORS["muted"], font=("Microsoft YaHei UI", 10)).pack()
        value = tk.StringVar(); entry = ttk.Entry(dialog, textvariable=value, font=("Consolas", 12)); entry.pack(fill="x", padx=45, pady=22); entry.focus_set()
        def activate():
            try:
                result = self.api.activate(value.get(), APP_VERSION)
                self.license_data.update(result.get("license", {})); save_license(self.license_data); self._refresh_header(); dialog.destroy(); messagebox.showinfo("激活成功", result.get("message", "激活成功"))
            except ApiError as exc: messagebox.showerror("激活失败", str(exc), parent=dialog)
        ttk.Button(dialog, text="立即激活", style="Hero.TButton", command=activate).pack()

    def _show_qr(self, title: str, filename: str) -> None:
        path = resource_dir() / filename
        if not path.exists(): messagebox.showerror("资源缺失", f"未找到 {filename}，请重新运行正式安装程序。"); return
        dialog = tk.Toplevel(self); dialog.title(title); dialog.configure(bg="white"); dialog.transient(self)
        try:
            from PIL import Image, ImageTk
            image = Image.open(path); image.thumbnail((460, 540)); photo = ImageTk.PhotoImage(image); self._images.append(photo)
            tk.Label(dialog, image=photo, bg="white").pack(padx=12, pady=12)
        except Exception as exc:
            dialog.destroy(); messagebox.showerror("加载失败", str(exc))

    def _about(self) -> None:
        remote = self.latest_update_info.get("details") or self.latest_update_info.get("notes") or ""
        extra = f"\n\n服务器最新说明：\n{remote}" if remote else ""
        messagebox.showinfo("关于与更新说明", f"{APP_NAME}\n版本：{APP_VERSION}\n\n{CHANGELOG}{extra}\n\n{DISCLAIMER}")

    def _load_history(self) -> None:
        rows = load_reports(30)
        if rows:
            top = rows[0]; self.history_var.set(f"{display_time(top.get('checked_at',''))} · {top.get('conclusion','')}")
        else: self.history_var.set("暂无历史记录")

    def _history_dialog(self) -> None:
        rows = load_reports(30)
        dialog = tk.Toplevel(self); dialog.title("检查历史"); dialog.geometry("760x460"); dialog.configure(bg=self.COLORS["bg"]); dialog.transient(self)
        tree = ttk.Treeview(dialog, columns=("time", "room", "status", "id"), show="headings")
        for key, title, width in [("time", "检查时间", 150), ("room", "直播间", 140), ("status", "结论", 260), ("id", "报告编号", 180)]: tree.heading(key, text=title); tree.column(key, width=width)
        for row in rows: tree.insert("", "end", values=(display_time(row.get("checked_at", "")), row.get("room_name", ""), row.get("conclusion", ""), row.get("report_id", "")))
        tree.pack(fill="both", expand=True, padx=16, pady=16)


def main() -> None:
    app = LiveCheckApp()
    try:
        icon = resource_dir() / "app_icon.ico"
        if icon.exists(): app.iconbitmap(str(icon))
    except Exception:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()
