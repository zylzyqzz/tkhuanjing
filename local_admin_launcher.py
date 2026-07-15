from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser

import psutil


HOST = "127.0.0.1"
PORT = 8000
HEALTH_URL = f"http://{HOST}:{PORT}/api/v1/health"
ADMIN_URL = f"http://{HOST}:{PORT}/tk-admin/"
INSTANCE_MUTEX = "Local\\WeiDuTKAdminLocal-2.1"


def base_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def runtime_dir() -> Path:
    path = base_dir() / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def trace(message_text: str) -> None:
    try:
        with (runtime_dir() / "launcher.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message_text}\n")
    except OSError:
        pass


def message(title: str, text: str, error: bool = False) -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 if error else 0x40)
    else:
        print(f"{title}: {text}")


def configure_environment() -> None:
    runtime = runtime_dir()
    secret_file = runtime / "local-secrets.json"
    try:
        values = json.loads(secret_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        values = {}
    if not isinstance(values, dict):
        values = {}
    changed = False
    for key in ("session", "license", "service"):
        if not isinstance(values.get(key), str) or len(values[key]) < 32:
            values[key] = secrets.token_urlsafe(48)
            changed = True
    if changed or not secret_file.exists():
        temp = secret_file.with_suffix(".tmp")
        temp.write_text(json.dumps(values), encoding="utf-8")
        os.replace(temp, secret_file)
    database = (runtime / "platform.sqlite3").resolve().as_posix()
    os.environ.update({
        "TK_ENV": "development", "TK_DATABASE_URL": f"sqlite:///{database}",
        "TK_DATA_DIR": str(runtime), "TK_PUBLIC_BASE": f"http://{HOST}:{PORT}",
        "TK_SESSION_SECRET": values["session"], "TK_LICENSE_SECRET": values["license"],
        "TK_LOCAL_SERVICE_SECRET": values["service"],
        "TK_ADMIN_USER": "admin",
    })


def acquire_instance_mutex() -> tuple[int | None, bool]:
    if os.name != "nt":
        return None, False
    import ctypes
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, INSTANCE_MUTEX)
    return handle, ctypes.windll.kernel32.GetLastError() == 183


def close_instance_mutex(handle: int | None) -> None:
    if handle and os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.CloseHandle(handle)


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            payload = json.loads(response.read().decode())
            return response.status == 200 and payload.get("database") == "ok" and payload.get("admin_assets") == "ok"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def port_in_use() -> bool:
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex((HOST, PORT)) == 0


def pid_file() -> Path:
    return runtime_dir() / "admin.pid"


def stop_server() -> int:
    try:
        pid = int(pid_file().read_text(encoding="ascii").strip())
        process = psutil.Process(pid)
        executable = Path(process.exe()).name.lower()
        if executable != "tkadminlocal.exe":
            raise RuntimeError("PID 不属于 TK 本地管理后台")
        process.terminate()
        try:
            process.wait(10)
        except psutil.TimeoutExpired:
            process.kill()
        pid_file().unlink(missing_ok=True)
        message("TK 管理后台", "本地管理后台已停止。")
        return 0
    except (OSError, ValueError, psutil.NoSuchProcess):
        pid_file().unlink(missing_ok=True)
        message("TK 管理后台", "本地管理后台当前没有运行。")
        return 0
    except Exception as exc:
        message("停止失败", str(exc), True)
        return 1


def open_when_ready() -> None:
    for _ in range(80):
        if healthy():
            webbrowser.open(ADMIN_URL)
            return
        time.sleep(.25)
    message("启动失败", "后台未能在规定时间内启动，请查看 runtime/server.log。", True)


def reset_password(username: str) -> int:
    configure_environment()
    from server.migrate import run as migrate
    from server.manage import reset_admin_password
    migrate()
    password = os.environ.get("TK_BOOTSTRAP_PASSWORD", "")
    if not password:
        message("密码重置失败", "缺少 TK_BOOTSTRAP_PASSWORD 环境变量。", True)
        return 2
    reset_admin_password(username, password)
    return 0


def start_server() -> int:
    trace("start_requested")
    if healthy():
        trace("existing_backend_healthy")
        webbrowser.open(ADMIN_URL)
        return 0
    mutex, already_running = acquire_instance_mutex()
    if already_running:
        close_instance_mutex(mutex)
        trace("existing_backend_is_starting")
        for _ in range(80):
            if healthy():
                webbrowser.open(ADMIN_URL)
                return 0
            time.sleep(.25)
        message("TK 管理后台", "后台正在启动或启动失败，请稍后重试并查看运行日志。", True)
        return 4
    if port_in_use():
        close_instance_mutex(mutex)
        trace("port_8000_in_use_by_other_process")
        message("端口被占用", "本机 8000 端口已被其他程序占用，TK 管理后台无法启动。", True)
        return 3
    configure_environment()
    pid_file().write_text(str(os.getpid()), encoding="ascii")
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        trace("importing_uvicorn")
        import uvicorn
        trace("importing_server_app")
        from server.main import app
        trace("starting_uvicorn")
        # The packaged launcher is a windowless executable, so stdout/stderr are
        # intentionally unavailable.  Uvicorn's default colour formatter probes
        # stderr.isatty() and crashes in that environment.  Application logs are
        # already written to runtime/server.log.
        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            log_level="info",
            access_log=False,
            log_config=None,
        )
        trace("uvicorn_stopped")
        return 0
    finally:
        pid_file().unlink(missing_ok=True)
        close_instance_mutex(mutex)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--reset-password-env", metavar="USERNAME")
    args = parser.parse_args()
    if args.stop:
        return stop_server()
    if args.reset_password_env:
        return reset_password(args.reset_password_env)
    return start_server()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        trace("fatal_error\n" + traceback.format_exc())
        message("TK 管理后台启动失败", str(exc), True)
        raise
