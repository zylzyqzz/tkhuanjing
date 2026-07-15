#!/usr/bin/env python3
from __future__ import annotations

import cgi
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(os.environ.get("TK_PLATFORM_ROOT", "/opt/tk-platform"))
DB_PATH = ROOT / "database" / "platform.sqlite3"
DOWNLOADS = ROOT / "downloads"
BACKUPS = ROOT / "backups"
ADMIN_USER = os.environ.get("TK_ADMIN_USER", "admin")
ADMIN_HASH = os.environ.get("TK_ADMIN_PASSWORD_HASH", "")
LICENSE_SECRET = os.environ.get("TK_LICENSE_SECRET", "change-this-license-secret").encode()
PUBLIC_BASE = os.environ.get("TK_PUBLIC_BASE", "https://v.wdai.cc").rstrip("/")
LISTEN_HOST = os.environ.get("TK_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("TK_LISTEN_PORT", "39999"))
MAX_JSON = 512 * 1024
MAX_UPLOAD_TEST = 5 * 1024 * 1024
TIERS = {"TK1": (1, "1次"), "TKX": (10, "10次"), "TKV": (-1, "永久VIP")}
CODE_STATUSES = {"available", "distributed", "used", "exhausted", "revoked"}
REPORT_STATUSES = {"PASS", "WARNING", "FAIL", "UNKNOWN"}
SESSIONS: dict[str, dict] = {}
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
API_ATTEMPTS: dict[str, list[float]] = {}


DEFAULT_SETTINGS = {
    "product_name": "维度 TikTok 直播开播助手",
    "product_intro": "面向 TikTok 电脑直播公司和工作室的开播前技术检查工具，快速检查网络、电脑、音视频设备和直播软件准备情况。",
    "product_features": "开播前一键检查\n网络稳定性分析\n摄像头与麦克风检测\n电脑性能与编码器检测\n检查报告与技术支持",
    "product_faq": "安装后为什么要检查？\n开播前检查可以提前发现卡顿、断流、黑屏和无声风险。\n检查通过是否代表平台一定允许开播？\n不是，本工具只判断技术准备情况。",
    "support_text": "需要帮助时，请在客户端打开客服二维码联系技术支持。",
    "latest_changelog": "2.0.0：上线开播前综合检测、检查报告和设备管理。",
}

DEFAULT_PROFILE = {
    "profile_name": "TikTok 直播默认标准",
    "upload_multiplier": 2.0,
    "packet_loss_warning": 1.0,
    "packet_loss_fail": 3.0,
    "jitter_warning_ms": 30.0,
    "jitter_fail_ms": 60.0,
    "latency_warning_ms": 150.0,
    "latency_fail_ms": 250.0,
    "upload_test_bytes": 2097152,
    "min_free_disk_gb": 10.0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    for path in (DB_PATH.parent, DOWNLOADS, BACKUPS):
        path.mkdir(parents=True, exist_ok=True)


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=20, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode=wal")
    conn.execute("pragma foreign_keys=on")
    return conn


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"pragma table_info({table})")}


def add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in columns(conn, table):
        conn.execute(f"alter table {table} add column {definition}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            create table if not exists codes (
              code text primary key, tier text not null, credits integer not null,
              status text not null, created_at text not null
            );
            create table if not exists releases (
              version text primary key, notes text, filename text not null,
              sha256 text not null, created_at text not null, active integer default 0
            );
            create table if not exists settings (key text primary key, value text not null);
            create table if not exists customers (
              id integer primary key autoincrement, name text not null, contact text default '',
              notes text default '', status text default 'active', created_at text not null
            );
            create table if not exists live_rooms (
              id integer primary key autoincrement, customer_id integer, name text not null,
              region text default '', bitrate_kbps integer default 6000, notes text default '', created_at text not null,
              foreign key(customer_id) references customers(id) on delete set null
            );
            create table if not exists devices (
              device_id text primary key, token_hash text not null, customer_id integer, room_id integer,
              customer_name text default '', room_name text default '', app_version text default '',
              license_code text, free_uses_remaining integer default 1,
              created_at text not null, last_seen text not null,
              foreign key(customer_id) references customers(id) on delete set null,
              foreign key(room_id) references live_rooms(id) on delete set null,
              foreign key(license_code) references codes(code) on delete set null
            );
            create table if not exists check_reports (
              report_id text primary key, device_id text not null, customer_name text default '',
              room_name text default '', app_version text default '', checked_at text not null,
              overall_status text not null, conclusion text default '', uploaded_at text not null,
              foreign key(device_id) references devices(device_id) on delete cascade
            );
            create table if not exists check_items (
              id integer primary key autoincrement, report_id text not null, check_id text not null,
              category text default '', status text not null, title text default '', value text default '',
              reason text default '', action text default '', repairable integer default 0, details_json text default '{}',
              foreign key(report_id) references check_reports(report_id) on delete cascade
            );
            create table if not exists check_profiles (
              id integer primary key autoincrement, name text not null, region text default '*',
              bitrate_kbps integer default 6000, rules_json text not null, active integer default 1,
              created_at text not null, updated_at text not null
            );
            create table if not exists support_cases (
              id integer primary key autoincrement, report_id text, device_id text, title text not null,
              status text default 'open', owner text default '', notes text default '',
              created_at text not null, updated_at text not null,
              foreign key(report_id) references check_reports(report_id) on delete set null
            );
            create table if not exists audit_logs (
              id integer primary key autoincrement, actor text not null, action text not null,
              target_type text default '', target_id text default '', details text default '', created_at text not null
            );
            create table if not exists license_events (
              event_id text primary key, device_id text not null, code text, event_type text not null,
              credits_after integer, created_at text not null
            );
            create index if not exists idx_reports_device_time on check_reports(device_id, checked_at desc);
            create index if not exists idx_reports_status_time on check_reports(overall_status, checked_at desc);
            create index if not exists idx_items_check_status on check_items(check_id, status);
            """
        )
        for definition in (
            "customer_note text default ''", "bound_device_id text", "activated_at text",
            "used_count integer default 0", "updated_at text"
        ):
            add_column(conn, "codes", definition)
        for definition in ("title text default ''", "details text default ''", "installer_filename text default ''"):
            add_column(conn, "releases", definition)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("insert or ignore into settings(key,value) values(?,?)", (key, value))
        if not conn.execute("select 1 from check_profiles where active=1 limit 1").fetchone():
            now = utc_now()
            conn.execute(
                "insert into check_profiles(name,region,bitrate_kbps,rules_json,active,created_at,updated_at) values(?,?,?,?,1,?,?)",
                (DEFAULT_PROFILE["profile_name"], "*", 6000, json.dumps(DEFAULT_PROFILE, ensure_ascii=False), now, now),
            )
        conn.commit()


def audit(actor: str, action: str, target_type: str = "", target_id: str = "", details: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "insert into audit_logs(actor,action,target_type,target_id,details,created_at) values(?,?,?,?,?,?)",
            (actor, action, target_type, target_id, details[:2000], utc_now()),
        )


def password_ok(password: str) -> bool:
    try:
        salt, expected = ADMIN_HASH.split("$", 1)
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 240000).hex()
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def code_signature(random_part: str) -> str:
    digest = hmac.new(LICENSE_SECRET, random_part.encode(), hashlib.sha256).digest()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = count = 0
    output: list[str] = []
    for byte in digest[:5]:
        bits = (bits << 8) | byte; count += 8
        while count >= 5:
            count -= 5; output.append(alphabet[(bits >> count) & 31])
    return "".join(output)[:5]


def make_code(tier: str) -> str:
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        random_part = "".join(secrets.choice(chars) for _ in range(5))
        code = f"{tier}-{random_part}-{code_signature(random_part)}"
        with connect() as conn:
            if not conn.execute("select 1 from codes where code=?", (code,)).fetchone():
                return code


def active_release() -> dict | None:
    with connect() as conn:
        row = conn.execute("select * from releases where active=1 order by created_at desc limit 1").fetchone()
        if not row:
            row = conn.execute("select * from releases order by created_at desc limit 1").fetchone()
    return dict(row) if row else None


def active_profile() -> dict:
    with connect() as conn:
        row = conn.execute("select * from check_profiles where active=1 order by updated_at desc limit 1").fetchone()
    if not row:
        return dict(DEFAULT_PROFILE)
    try:
        return json.loads(row["rules_json"])
    except ValueError:
        return dict(DEFAULT_PROFILE)


def license_view(conn: sqlite3.Connection, device: sqlite3.Row) -> dict:
    lease_until = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(timespec="seconds")
    if device["license_code"]:
        code = conn.execute("select * from codes where code=?", (device["license_code"],)).fetchone()
        if code:
            return {"code": code["code"], "tier": code["tier"], "credits": code["credits"], "status": code["status"], "lease_until": lease_until, "pending_events": []}
    return {"code": "", "tier": "FREE", "credits": device["free_uses_remaining"], "status": "available" if device["free_uses_remaining"] > 0 else "exhausted", "lease_until": lease_until, "pending_events": []}


def json_bytes(value, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"


class Handler(BaseHTTPRequestHandler):
    server_version = "TKLivePlatform/2.0"

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} {fmt % args}")

    def send_body(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers(); self.wfile.write(body)

    def send_json(self, value, status: int = 200) -> None:
        self.send_body(*json_bytes(value, status))

    def read_json(self, maximum: int = MAX_JSON) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > maximum:
            raise ValueError("请求内容大小不正确")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求格式不正确")
        return value

    def session(self) -> dict | None:
        jar = cookies.SimpleCookie(); jar.load(self.headers.get("Cookie", ""))
        morsel = jar.get("tk_session")
        session = SESSIONS.get(morsel.value) if morsel else None
        if session and time.time() - session["last_seen"] < 8 * 3600:
            session["last_seen"] = time.time(); return session
        if morsel: SESSIONS.pop(morsel.value, None)
        return None

    def require_admin(self, csrf: bool = False) -> dict | None:
        session = self.session()
        if not session:
            self.send_json({"error": "请先登录"}, 401); return None
        if csrf and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
            self.send_json({"error": "安全令牌无效，请刷新页面"}, 403); return None
        return session

    def device(self) -> sqlite3.Row | None:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        digest = token_hash(auth[7:])
        with connect() as conn:
            return conn.execute("select * from devices where token_hash=?", (digest,)).fetchone()

    def require_device(self) -> sqlite3.Row | None:
        device = self.device()
        if not device:
            self.send_json({"error": "设备未登记或令牌无效"}, 401); return None
        with connect() as conn:
            conn.execute("update devices set last_seen=? where device_id=?", (utc_now(), device["device_id"]))
        return device

    def do_GET(self) -> None:
        parsed = urlparse(self.path); path = parsed.path; query = parse_qs(parsed.query)
        try:
            if path == "/" or path == "/download/": return self.download_page()
            if path == "/tk-admin/": return self.admin_page()
            if path.startswith("/downloads/"): return self.download_file(path)
            if path == "/api/client/update": return self.client_update()
            if path == "/api/client/check-profile": return self.client_profile()
            if path == "/api/client/reports/latest": return self.client_latest_report()
            if path == "/tk-api/session": return self.admin_session()
            if path == "/tk-api/stats": return self.admin_stats()
            if path == "/tk-api/settings": return self.admin_settings()
            if path == "/tk-api/customers": return self.admin_list("customers", query)
            if path == "/tk-api/rooms": return self.admin_list("rooms", query)
            if path == "/tk-api/devices": return self.admin_list("devices", query)
            if path == "/tk-api/reports": return self.admin_list("reports", query)
            if path == "/tk-api/report": return self.admin_report(query)
            if path == "/tk-api/support": return self.admin_list("support", query)
            if path == "/tk-api/codes": return self.admin_list("codes", query)
            if path == "/tk-api/releases": return self.admin_list("releases", query)
            if path == "/tk-api/profile": return self.admin_profile()
            if path == "/tk-api/audit": return self.admin_list("audit", query)
            if path == "/tk-api/codes/export": return self.export_codes(query)
            if path == "/tk-api/reports/export": return self.export_reports(query)
            if path == "/tk-api/backup": return self.backup_database()
            self.send_json({"error": "not found"}, 404)
        except (ValueError, sqlite3.Error) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": "服务器内部错误", "detail": str(exc)}, 500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/client/register": return self.client_register()
            if path == "/api/client/upload-test": return self.client_upload_test()
            if path == "/api/client/reports": return self.client_report_upload()
            if path == "/api/client/activate": return self.client_activate()
            if path == "/api/client/authorize-check": return self.client_authorize_check()
            if path == "/tk-api/login": return self.admin_login()
            if path == "/tk-api/logout": return self.admin_logout()
            if path == "/tk-api/codes/generate": return self.admin_generate_codes()
            if path == "/tk-api/codes/status": return self.admin_code_status()
            if path == "/tk-api/customer/save": return self.admin_save_customer()
            if path == "/tk-api/room/save": return self.admin_save_room()
            if path == "/tk-api/support/save": return self.admin_save_support()
            if path == "/tk-api/settings": return self.admin_save_settings()
            if path == "/tk-api/profile": return self.admin_save_profile()
            if path == "/tk-api/release": return self.admin_release()
            if path == "/tk-api/release/activate": return self.admin_activate_release()
            self.send_json({"error": "not found"}, 404)
        except (ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": "服务器内部错误", "detail": str(exc)}, 500)

    # ---- public client API ----
    def client_register(self) -> None:
        data = self.read_json(64 * 1024)
        device_id = str(data.get("device_id", "")).strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{8,64}", device_id):
            raise ValueError("设备编号格式不正确")
        token = secrets.token_urlsafe(32); digest = token_hash(token); now = utc_now()
        customer_name = str(data.get("customer_name", ""))[:100]
        room_name = str(data.get("room_name", ""))[:100]
        app_version = str(data.get("app_version", ""))[:30]
        with connect() as conn:
            existing = conn.execute("select * from devices where device_id=?", (device_id,)).fetchone()
            if existing:
                conn.execute("update devices set token_hash=?,customer_name=?,room_name=?,app_version=?,last_seen=? where device_id=?", (digest, customer_name, room_name, app_version, now, device_id))
            else:
                conn.execute("insert into devices(device_id,token_hash,customer_name,room_name,app_version,created_at,last_seen) values(?,?,?,?,?,?,?)", (device_id, digest, customer_name, room_name, app_version, now, now))
            device = conn.execute("select * from devices where device_id=?", (device_id,)).fetchone()
            license_data = license_view(conn, device)
        self.send_json({"device_token": token, "device_id": device_id, "license": license_data})

    def client_profile(self) -> None:
        if not self.require_device(): return
        self.send_json({"profile": active_profile()})

    def client_upload_test(self) -> None:
        if not self.require_device(): return
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_UPLOAD_TEST:
            raise ValueError("测速数据大小不正确")
        remaining = length; received = 0
        while remaining:
            block = self.rfile.read(min(65536, remaining))
            if not block: break
            received += len(block); remaining -= len(block)
        self.send_json({"received": received})

    def client_update(self) -> None:
        release = active_release()
        if not release:
            return self.send_json({"version": "0.0.0", "title": "暂无更新", "notes": "", "details": "", "url": "", "installer_url": "", "sha256": ""})
        filename = release["filename"]
        installer = release.get("installer_filename") or f"setup-{release['version']}.exe"
        self.send_json({
            "version": release["version"], "title": release.get("title") or release.get("notes") or "版本更新",
            "notes": release.get("notes") or "", "details": release.get("details") or "",
            "url": f"{PUBLIC_BASE}/downloads/{quote(filename)}", "installer_url": f"{PUBLIC_BASE}/downloads/{quote(installer)}",
            "sha256": release["sha256"],
        })

    def client_activate(self) -> None:
        device = self.require_device()
        if not device: return
        data = self.read_json(64 * 1024); code_value = str(data.get("code", "")).strip().upper()
        with connect() as conn:
            code = conn.execute("select * from codes where code=?", (code_value,)).fetchone()
            if not code or code["status"] in {"revoked", "exhausted"}:
                raise ValueError("激活码无效、已耗尽或已作废")
            if code["bound_device_id"] and code["bound_device_id"] != device["device_id"]:
                raise ValueError("激活码已绑定其他设备")
            if device["license_code"] and device["license_code"] != code_value:
                current = conn.execute("select * from codes where code=?", (device["license_code"],)).fetchone()
                if current and current["credits"] < 0:
                    raise ValueError("当前设备已经永久激活")
            now = utc_now()
            conn.execute("update codes set status='used',bound_device_id=?,activated_at=coalesce(activated_at,?),updated_at=? where code=?", (device["device_id"], now, now, code_value))
            conn.execute("update devices set license_code=?,last_seen=? where device_id=?", (code_value, now, device["device_id"]))
            updated = conn.execute("select * from devices where device_id=?", (device["device_id"],)).fetchone()
            license_data = license_view(conn, updated)
        audit(device["device_id"], "client.activate", "code", code_value)
        self.send_json({"ok": True, "message": f"{TIERS[code['tier']][1]}激活成功", "license": license_data})

    def client_authorize_check(self) -> None:
        device = self.require_device()
        if not device: return
        data = self.read_json(32 * 1024); event_id = str(data.get("event_id", ""))
        if not re.fullmatch(r"[0-9a-fA-F-]{32,40}", event_id):
            raise ValueError("事件编号格式不正确")
        with connect() as conn:
            previous = conn.execute("select * from license_events where event_id=?", (event_id,)).fetchone()
            current_device = conn.execute("select * from devices where device_id=?", (device["device_id"],)).fetchone()
            if previous:
                return self.send_json({"allowed": True, "message": "已同步", "license": license_view(conn, current_device)})
            now = utc_now(); code_value = current_device["license_code"]
            if code_value:
                code = conn.execute("select * from codes where code=?", (code_value,)).fetchone()
                if not code or code["status"] == "revoked" or code["credits"] == 0:
                    return self.send_json({"allowed": False, "message": "激活码次数不足或已作废", "license": license_view(conn, current_device)}, 403)
                after = code["credits"] if code["credits"] < 0 else code["credits"] - 1
                status = "exhausted" if after == 0 else "used"
                conn.execute("update codes set credits=?,status=?,used_count=coalesce(used_count,0)+1,updated_at=? where code=?", (after, status, now, code_value))
            else:
                if current_device["free_uses_remaining"] <= 0:
                    return self.send_json({"allowed": False, "message": "免费次数已用完，请激活或充值", "license": license_view(conn, current_device)}, 403)
                after = current_device["free_uses_remaining"] - 1
                conn.execute("update devices set free_uses_remaining=? where device_id=?", (after, device["device_id"]))
            conn.execute("insert into license_events(event_id,device_id,code,event_type,credits_after,created_at) values(?,?,?,?,?,?)", (event_id, device["device_id"], code_value, "check", after, now))
            current_device = conn.execute("select * from devices where device_id=?", (device["device_id"],)).fetchone()
            license_data = license_view(conn, current_device)
        self.send_json({"allowed": True, "message": "已授权本次检查", "license": license_data})

    def client_report_upload(self) -> None:
        device = self.require_device()
        if not device: return
        data = self.read_json(MAX_JSON)
        report_id = str(data.get("report_id", "")); status = str(data.get("overall_status", "UNKNOWN"))
        if not re.fullmatch(r"[0-9a-fA-F-]{32,40}", report_id) or status not in REPORT_STATUSES:
            raise ValueError("报告格式不正确")
        items = data.get("items", [])
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError("报告项目数量不正确")
        with connect() as conn:
            conn.execute(
                "insert or ignore into check_reports(report_id,device_id,customer_name,room_name,app_version,checked_at,overall_status,conclusion,uploaded_at) values(?,?,?,?,?,?,?,?,?)",
                (report_id, device["device_id"], str(data.get("customer_name", ""))[:100], str(data.get("room_name", ""))[:100], str(data.get("app_version", ""))[:30], str(data.get("checked_at", utc_now()))[:40], status, str(data.get("conclusion", ""))[:500], utc_now()),
            )
            if conn.execute("select count(*) from check_items where report_id=?", (report_id,)).fetchone()[0] == 0:
                for item in items:
                    item_status = str(item.get("status", "UNKNOWN"))
                    if item_status not in REPORT_STATUSES: item_status = "UNKNOWN"
                    conn.execute(
                        "insert into check_items(report_id,check_id,category,status,title,value,reason,action,repairable,details_json) values(?,?,?,?,?,?,?,?,?,?)",
                        (report_id, str(item.get("check_id", ""))[:100], str(item.get("category", ""))[:50], item_status, str(item.get("title", ""))[:200], str(item.get("value", ""))[:500], str(item.get("reason", ""))[:1000], str(item.get("action", ""))[:1000], 1 if item.get("repairable") else 0, json.dumps(item.get("details", {}), ensure_ascii=False)[:5000]),
                    )
        self.send_json({"ok": True, "report_id": report_id})

    def client_latest_report(self) -> None:
        device = self.require_device()
        if not device: return
        with connect() as conn:
            row = conn.execute("select * from check_reports where device_id=? order by checked_at desc limit 1", (device["device_id"],)).fetchone()
        self.send_json({"report": dict(row) if row else None})

    # ---- admin API ----
    def admin_login(self) -> None:
        ip = self.client_address[0]; now = time.time()
        recent = [x for x in LOGIN_ATTEMPTS.get(ip, []) if now - x < 600]
        if len(recent) >= 10:
            return self.send_json({"error": "登录尝试过于频繁，请稍后再试"}, 429)
        LOGIN_ATTEMPTS[ip] = recent + [now]
        length = int(self.headers.get("Content-Length", "0")); data = parse_qs(self.rfile.read(min(length, 8192)).decode("utf-8"))
        if data.get("username", [""])[0] != ADMIN_USER or not password_ok(data.get("password", [""])[0]):
            return self.send_json({"error": "账号或密码错误"}, 403)
        token = secrets.token_urlsafe(32); csrf = secrets.token_urlsafe(24)
        SESSIONS[token] = {"user": ADMIN_USER, "csrf": csrf, "last_seen": now}
        secure = "; Secure" if PUBLIC_BASE.startswith("https://") else ""
        body = json.dumps({"ok": True, "csrf": csrf}).encode()
        self.send_body(200, body, "application/json; charset=utf-8", {"Set-Cookie": f"tk_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}"})

    def admin_logout(self) -> None:
        session = self.require_admin(True)
        if not session: return
        for key, value in list(SESSIONS.items()):
            if value is session: SESSIONS.pop(key, None)
        self.send_body(200, b'{"ok":true}', "application/json", {"Set-Cookie": "tk_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})

    def admin_session(self) -> None:
        session = self.session(); self.send_json({"logged_in": bool(session), "csrf": session["csrf"] if session else ""})

    def admin_stats(self) -> None:
        if not self.require_admin(): return
        today = datetime.now(timezone.utc).date().isoformat()
        with connect() as conn:
            counts = {
                "customers": conn.execute("select count(*) from customers").fetchone()[0],
                "rooms": conn.execute("select count(*) from live_rooms").fetchone()[0],
                "devices": conn.execute("select count(*) from devices").fetchone()[0],
                "reports_today": conn.execute("select count(*) from check_reports where checked_at like ?", (today + "%",)).fetchone()[0],
                "support_open": conn.execute("select count(*) from support_cases where status not in ('closed','resolved')").fetchone()[0],
                "codes_available": conn.execute("select count(*) from codes where status='available'").fetchone()[0],
            }
            statuses = {row[0]: row[1] for row in conn.execute("select overall_status,count(*) from check_reports where checked_at like ? group by overall_status", (today + "%",))}
            faults = [dict(row) for row in conn.execute("select title,check_id,count(*) count from check_items where status='FAIL' group by check_id,title order by count desc limit 5")]
            versions = [dict(row) for row in conn.execute("select app_version,count(*) count from devices group by app_version order by count desc limit 8")]
        release = active_release()
        self.send_json({**counts, "report_statuses": statuses, "top_faults": faults, "versions": versions, "active_release": release})

    def admin_settings(self) -> None:
        if not self.require_admin(): return
        with connect() as conn:
            values = {row[0]: row[1] for row in conn.execute("select key,value from settings")}
        self.send_json(values)

    def admin_list(self, kind: str, query: dict) -> None:
        if not self.require_admin(): return
        q = str(query.get("q", [""])[0])[:100]; like = f"%{q}%"
        status = str(query.get("status", [""])[0])[:30]
        with connect() as conn:
            if kind == "customers":
                rows = conn.execute("select c.*,(select count(*) from live_rooms r where r.customer_id=c.id) room_count from customers c where (?='' or c.name like ? or c.contact like ?) order by c.id desc limit 1000", (q, like, like)).fetchall()
            elif kind == "rooms":
                rows = conn.execute("select r.*,c.name customer from live_rooms r left join customers c on c.id=r.customer_id where (?='' or r.name like ? or c.name like ?) order by r.id desc limit 1000", (q, like, like)).fetchall()
            elif kind == "devices":
                rows = conn.execute("select d.*,c.name customer,r.name room from devices d left join customers c on c.id=d.customer_id left join live_rooms r on r.id=d.room_id where (?='' or d.device_id like ? or d.customer_name like ? or d.room_name like ?) order by d.last_seen desc limit 1000", (q, like, like, like)).fetchall()
            elif kind == "reports":
                rows = conn.execute("select * from check_reports where (?='' or overall_status=?) and (?='' or customer_name like ? or room_name like ? or device_id like ?) order by checked_at desc limit 2000", (status, status, q, like, like, like)).fetchall()
            elif kind == "support":
                rows = conn.execute("select * from support_cases where (?='' or status=?) and (?='' or title like ? or device_id like ?) order by updated_at desc limit 1000", (status, status, q, like, like)).fetchall()
            elif kind == "codes":
                tier = str(query.get("tier", [""])[0])[:10]
                rows = conn.execute("select * from codes where (?='' or status=?) and (?='' or tier=?) and (?='' or code like ? or customer_note like ?) order by created_at desc limit 2000", (status, status, tier, tier, q, like, like)).fetchall()
            elif kind == "releases":
                rows = conn.execute("select * from releases order by created_at desc").fetchall()
            elif kind == "audit":
                rows = conn.execute("select * from audit_logs order by id desc limit 1000").fetchall()
            else:
                raise ValueError("未知列表")
        self.send_json({kind: [dict(row) for row in rows]})

    def admin_report(self, query: dict) -> None:
        if not self.require_admin(): return
        report_id = str(query.get("id", [""])[0])
        with connect() as conn:
            report = conn.execute("select * from check_reports where report_id=?", (report_id,)).fetchone()
            items = conn.execute("select * from check_items where report_id=? order by id", (report_id,)).fetchall()
        if not report: return self.send_json({"error": "报告不存在"}, 404)
        self.send_json({"report": dict(report), "items": [dict(row) for row in items]})

    def admin_profile(self) -> None:
        if not self.require_admin(): return
        self.send_json({"profile": active_profile()})

    def admin_generate_codes(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(64 * 1024); tier = str(data.get("tier", "")); count = int(data.get("count", 1)); note = str(data.get("note", ""))[:300]
        if tier not in TIERS or not 1 <= count <= 500: raise ValueError("档次或数量不正确")
        values = [make_code(tier) for _ in range(count)]; now = utc_now()
        with connect() as conn:
            conn.executemany("insert into codes(code,tier,credits,status,created_at,customer_note,updated_at) values(?,?,?,?,?,?,?)", [(code, tier, TIERS[tier][0], "available", now, note, now) for code in values])
        audit(session["user"], "codes.generate", "code", tier, f"count={count}; note={note}")
        self.send_json({"codes": values})

    def admin_code_status(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(); code = str(data.get("code", "")); status = str(data.get("status", "")); note = str(data.get("note", ""))[:300]
        if status not in CODE_STATUSES: raise ValueError("激活码状态不正确")
        with connect() as conn:
            cur = conn.execute("update codes set status=?,customer_note=case when ?='' then customer_note else ? end,updated_at=? where code=?", (status, note, note, utc_now(), code))
        if not cur.rowcount: raise ValueError("激活码不存在")
        audit(session["user"], "code.status", "code", code, status)
        self.send_json({"ok": True})

    def admin_save_customer(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(); row_id = int(data.get("id") or 0); name = str(data.get("name", "")).strip()[:100]
        if not name: raise ValueError("客户名称不能为空")
        values = (name, str(data.get("contact", ""))[:200], str(data.get("notes", ""))[:2000], str(data.get("status", "active"))[:30])
        with connect() as conn:
            if row_id:
                conn.execute("update customers set name=?,contact=?,notes=?,status=? where id=?", (*values, row_id))
            else:
                cur = conn.execute("insert into customers(name,contact,notes,status,created_at) values(?,?,?,?,?)", (*values, utc_now())); row_id = cur.lastrowid
        audit(session["user"], "customer.save", "customer", str(row_id), name)
        self.send_json({"ok": True, "id": row_id})

    def admin_save_room(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(); row_id = int(data.get("id") or 0); name = str(data.get("name", "")).strip()[:100]
        if not name: raise ValueError("直播间名称不能为空")
        values = (int(data.get("customer_id") or 0) or None, name, str(data.get("region", ""))[:100], max(1000, int(data.get("bitrate_kbps") or 6000)), str(data.get("notes", ""))[:2000])
        with connect() as conn:
            if row_id: conn.execute("update live_rooms set customer_id=?,name=?,region=?,bitrate_kbps=?,notes=? where id=?", (*values, row_id))
            else: row_id = conn.execute("insert into live_rooms(customer_id,name,region,bitrate_kbps,notes,created_at) values(?,?,?,?,?,?)", (*values, utc_now())).lastrowid
        audit(session["user"], "room.save", "room", str(row_id), name)
        self.send_json({"ok": True, "id": row_id})

    def admin_save_support(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(); row_id = int(data.get("id") or 0); title = str(data.get("title", "")).strip()[:200]
        if not title: raise ValueError("故障标题不能为空")
        now = utc_now(); values = (str(data.get("report_id", "")) or None, str(data.get("device_id", "")) or None, title, str(data.get("status", "open"))[:30], str(data.get("owner", ""))[:100], str(data.get("notes", ""))[:5000])
        with connect() as conn:
            if row_id: conn.execute("update support_cases set report_id=?,device_id=?,title=?,status=?,owner=?,notes=?,updated_at=? where id=?", (*values, now, row_id))
            else: row_id = conn.execute("insert into support_cases(report_id,device_id,title,status,owner,notes,created_at,updated_at) values(?,?,?,?,?,?,?,?)", (*values, now, now)).lastrowid
        audit(session["user"], "support.save", "support", str(row_id), title)
        self.send_json({"ok": True, "id": row_id})

    def admin_save_settings(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(); allowed = set(DEFAULT_SETTINGS)
        with connect() as conn:
            for key in allowed:
                if key in data: conn.execute("insert or replace into settings(key,value) values(?,?)", (key, str(data[key])[:20000]))
        audit(session["user"], "settings.save")
        self.send_json({"ok": True})

    def admin_save_profile(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(); profile = dict(DEFAULT_PROFILE)
        for key in profile:
            if key in data: profile[key] = data[key]
        numeric = [key for key in profile if key != "profile_name"]
        for key in numeric: profile[key] = float(profile[key]) if key not in {"upload_test_bytes"} else int(profile[key])
        if not 0 <= profile["packet_loss_warning"] <= profile["packet_loss_fail"] <= 100: raise ValueError("丢包阈值不正确")
        if not 0 <= profile["jitter_warning_ms"] <= profile["jitter_fail_ms"]: raise ValueError("抖动阈值不正确")
        if not 0 <= profile["latency_warning_ms"] <= profile["latency_fail_ms"]: raise ValueError("延迟阈值不正确")
        now = utc_now()
        with connect() as conn:
            conn.execute("update check_profiles set active=0")
            conn.execute("insert into check_profiles(name,region,bitrate_kbps,rules_json,active,created_at,updated_at) values(?,?,?,?,1,?,?)", (str(profile["profile_name"])[:100], "*", 6000, json.dumps(profile, ensure_ascii=False), now, now))
        audit(session["user"], "profile.save")
        self.send_json({"ok": True, "profile": profile})

    def admin_release(self) -> None:
        session = self.require_admin(True)
        if not session: return
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")})
        version = (form.getfirst("version") or "").strip(); title = (form.getfirst("title") or "").strip(); notes = (form.getfirst("notes") or "").strip(); details = (form.getfirst("details") or "").strip(); item = form["file"] if "file" in form else None
        if not re.fullmatch(r"\d+\.\d+\.\d+", version) or not title or not notes or not details or item is None or not getattr(item, "file", None):
            raise ValueError("版本号、更新标题、摘要、详细内容和 EXE 文件均为必填")
        filename = f"client-{version}.exe"; temp = DOWNLOADS / (filename + ".tmp"); final = DOWNLOADS / filename; digest = hashlib.sha256(); total = 0
        with temp.open("wb") as output:
            while True:
                block = item.file.read(1024 * 1024)
                if not block: break
                total += len(block)
                if total > 300 * 1024 * 1024: raise ValueError("更新文件不能超过 300MB")
                output.write(block); digest.update(block)
        os.replace(temp, final); now = utc_now()
        with connect() as conn:
            conn.execute("update releases set active=0")
            conn.execute("insert or replace into releases(version,title,notes,details,filename,installer_filename,sha256,created_at,active) values(?,?,?,?,?,?,?,?,1)", (version, title[:200], notes[:1000], details[:10000], filename, f"setup-{version}.exe", digest.hexdigest(), now))
            conn.execute("insert or replace into settings(key,value) values('latest_changelog',?)", (f"{version}：{title}\n{details}"[:20000],))
        audit(session["user"], "release.publish", "release", version, title)
        self.send_json({"ok": True, "version": version, "sha256": digest.hexdigest()})

    def admin_activate_release(self) -> None:
        session = self.require_admin(True)
        if not session: return
        data = self.read_json(); version = str(data.get("version", ""))
        with connect() as conn:
            if not conn.execute("select 1 from releases where version=?", (version,)).fetchone(): raise ValueError("版本不存在")
            conn.execute("update releases set active=case when version=? then 1 else 0 end", (version,))
        audit(session["user"], "release.activate", "release", version)
        self.send_json({"ok": True})

    def export_codes(self, query: dict) -> None:
        if not self.require_admin(): return
        with connect() as conn: rows = conn.execute("select code,tier,credits,status,bound_device_id,activated_at,used_count,customer_note,created_at from codes order by created_at desc").fetchall()
        text = "激活码\t档次\t剩余次数\t状态\t绑定设备\t激活时间\t使用次数\t备注\t生成时间\n" + "\n".join("\t".join(str(value or "") for value in row) for row in rows)
        self.send_body(200, text.encode("utf-8-sig"), "text/tab-separated-values; charset=utf-8", {"Content-Disposition": "attachment; filename=codes.tsv"})

    def export_reports(self, query: dict) -> None:
        if not self.require_admin(): return
        with connect() as conn: rows = conn.execute("select report_id,customer_name,room_name,device_id,checked_at,overall_status,conclusion,app_version from check_reports order by checked_at desc").fetchall()
        text = "报告编号\t客户\t直播间\t设备\t检查时间\t状态\t结论\t版本\n" + "\n".join("\t".join(str(value or "") for value in row) for row in rows)
        self.send_body(200, text.encode("utf-8-sig"), "text/tab-separated-values; charset=utf-8", {"Content-Disposition": "attachment; filename=reports.tsv"})

    def backup_database(self) -> None:
        session = self.require_admin()
        if not session: return
        name = "platform-backup-" + time.strftime("%Y%m%d-%H%M%S") + ".sqlite3"; target = BACKUPS / name
        with connect() as conn:
            backup = sqlite3.connect(target)
            try:
                conn.backup(backup)
            finally:
                backup.close()
        audit(session["user"], "database.backup", "backup", name)
        self.send_json({"ok": True, "file": name})

    # ---- pages/files ----
    def download_file(self, path: str) -> None:
        name = path.removeprefix("/downloads/")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name): return self.send_json({"error": "not found"}, 404)
        file_path = DOWNLOADS / name
        if not file_path.is_file(): return self.send_json({"error": "not found"}, 404)
        size = file_path.stat().st_size; self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream"); self.send_header("Content-Length", str(size)); self.send_header("Content-Disposition", f'attachment; filename="{name}"'); self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers()
        with file_path.open("rb") as stream: shutil.copyfileobj(stream, self.wfile, 1024 * 1024)

    def download_page(self) -> None:
        with connect() as conn: settings = {row[0]: row[1] for row in conn.execute("select key,value from settings")}
        release = active_release(); version = release["version"] if release else "暂无版本"; filename = (release.get("installer_filename") or f"setup-{version}.exe") if release else ""; link = f"/downloads/{quote(filename)}" if filename else "#"
        features = "".join(f"<li>{html.escape(line)}</li>" for line in settings.get("product_features", "").splitlines() if line.strip())
        page = f"""<!doctype html><html lang=zh-CN><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{html.escape(settings.get('product_name',''))}</title><style>{PUBLIC_CSS}</style></head><body><header><b>维度光年 · TikTok 直播技术保障</b><a href=#faq>常见问题</a></header><main><section class=hero><span class=eyebrow>开播前 3 分钟技术检查</span><h1>{html.escape(settings.get('product_name',''))}</h1><p>{html.escape(settings.get('product_intro',''))}</p><a class=download href='{link}'>下载正式安装程序</a><small>当前版本 {html.escape(version)} · 安装后自动创建桌面快捷方式</small></section><section class=features><div><h2>开播之前，先把技术问题找出来</h2><ul>{features}</ul></div><div class=report><strong>检测结果</strong><p class=pass>通过 · 可以开播</p><p class=warn>风险 · 建议处理</p><p class=fail>失败 · 不建议开播</p></div></section><section id=faq><h2>使用说明</h2><p>{html.escape(settings.get('product_faq','')).replace(chr(10),'<br>')}</p><p class=notice>本软件只判断电脑、网络、设备和直播软件的技术准备情况，不代表平台账号审核、流量或开播权限结果。</p></section></main></body></html>"""
        self.send_body(200, page.encode(), "text/html; charset=utf-8")

    def admin_page(self) -> None:
        self.send_body(200, ADMIN_HTML.encode(), "text/html; charset=utf-8")


PUBLIC_CSS = """
*{box-sizing:border-box}body{margin:0;background:#070d19;color:#eef4ff;font-family:Inter,'Microsoft YaHei UI',sans-serif}header{height:68px;padding:0 max(24px,calc((100% - 1120px)/2));display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #22304b}header a{color:#9eb2d4;text-decoration:none}main{max-width:1120px;margin:auto;padding:70px 24px}.hero{padding:64px;border-radius:28px;background:radial-gradient(circle at 80% 10%,#2866c955,transparent 35%),linear-gradient(135deg,#101c34,#11192b);border:1px solid #26395c}.eyebrow{color:#65a0ff;font-weight:700}h1{font-size:48px;max-width:760px;margin:18px 0}p{line-height:1.9;color:#aebbd2}.download{display:inline-block;margin:22px 14px 18px 0;padding:16px 28px;border-radius:12px;background:#4388ff;color:white;text-decoration:none;font-weight:700}.hero small{display:block;color:#7284a4}.features{display:grid;grid-template-columns:1.3fr .7fr;gap:24px;margin:28px 0}.features>div,#faq{padding:34px;border-radius:22px;background:#101827;border:1px solid #22304b}li{margin:14px 0;color:#b9c7de}.report p{padding:12px;border-radius:10px;color:white}.pass{background:#123c35}.warn{background:#493d20}.fail{background:#4b2230}.notice{padding:16px;border-left:4px solid #f5c451;background:#171d2a}@media(max-width:720px){h1{font-size:34px}.hero{padding:34px}.features{grid-template-columns:1fr}}
"""


ADMIN_HTML = r"""<!doctype html><html lang=zh-CN><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>维度 TK 管理中心</title><style>
*{box-sizing:border-box}body{margin:0;background:#080d18;color:#edf3ff;font-family:Inter,'Microsoft YaHei UI',sans-serif}button,input,select,textarea{font:inherit}button{cursor:pointer}.login{max-width:430px;margin:12vh auto;background:#121b2d;padding:36px;border:1px solid #293b5c;border-radius:22px}.login input,.form input,.form select,.form textarea,.toolbar input,.toolbar select{width:100%;background:#0c1424;color:#eef4ff;border:1px solid #2a3a57;border-radius:9px;padding:11px;margin:5px 0}.primary{border:0;background:#4388ff;color:white;border-radius:9px;padding:11px 16px;font-weight:700}.secondary{border:1px solid #354866;background:#172238;color:#dce8ff;border-radius:9px;padding:10px 14px}.shell{display:grid;grid-template-columns:230px 1fr;min-height:100vh}.side{background:#0d1423;border-right:1px solid #202d45;padding:24px 14px}.brand{font-size:18px;font-weight:800;margin:0 10px 24px}.nav button{display:block;width:100%;text-align:left;padding:12px 14px;margin:3px 0;color:#9fb0cd;background:transparent;border:0;border-radius:9px}.nav button.on,.nav button:hover{background:#1a2944;color:white}.main{padding:28px;min-width:0}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.top h1{font-size:25px;margin:0}.muted{color:#8496b5}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:20px}.card,.panel{background:#111a2b;border:1px solid #22324d;border-radius:14px;padding:18px}.card b{font-size:25px;display:block;margin-top:8px}.panel{margin-bottom:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.toolbar{display:flex;gap:8px;margin-bottom:14px}.toolbar input,.toolbar select{width:auto;min-width:140px}.tablewrap{overflow:auto;max-height:63vh}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:11px;border-bottom:1px solid #22304a;text-align:left;white-space:nowrap}th{color:#8fa1c0;position:sticky;top:0;background:#111a2b}.badge{padding:4px 8px;border-radius:20px;background:#293650}.PASS,.available{color:#42d6aa}.WARNING,.distributed{color:#f3c65c}.FAIL,.revoked,.exhausted{color:#ff6b82}.modal{position:fixed;inset:0;background:#0009;display:flex;align-items:center;justify-content:center}.modal>div{background:#121b2d;border:1px solid #314568;border-radius:18px;padding:24px;width:min(620px,92vw);max-height:90vh;overflow:auto}.hide{display:none}.toast{position:fixed;right:24px;bottom:24px;background:#edf3ff;color:#111827;padding:12px 18px;border-radius:10px}@media(max-width:1000px){.cards{grid-template-columns:repeat(3,1fr)}.shell{grid-template-columns:190px 1fr}}@media(max-width:720px){.shell{display:block}.side{position:static}.nav{display:flex;overflow:auto}.nav button{min-width:110px}.cards,.grid{grid-template-columns:1fr 1fr}.main{padding:16px}}
</style></head><body><div id=app></div><div id=modal></div><script>
let csrf='',page='dashboard';const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opt={}){let r=await fetch(url,opt),x=await r.json().catch(()=>({error:'请求失败'}));if(!r.ok)throw Error(x.error||'请求失败');return x}function toast(s){let e=document.createElement('div');e.className='toast';e.textContent=s;document.body.append(e);setTimeout(()=>e.remove(),2200)}
async function boot(){let s=await api('/tk-api/session');if(!s.logged_in){$('app').innerHTML=`<div class=login><h1>维度 TK 管理中心</h1><p class=muted>直播间、设备、检查报告、激活码和版本发布</p><input id=u placeholder=管理员账号><input id=p type=password placeholder=密码><button class=primary style='width:100%;margin-top:12px' onclick=login()>登录后台</button></div>`;return}csrf=s.csrf;layout();go('dashboard')}
async function login(){try{await api('/tk-api/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'username='+encodeURIComponent(u.value)+'&password='+encodeURIComponent(p.value)});location.reload()}catch(e){toast(e.message)}}
function layout(){$('app').innerHTML=`<div class=shell><aside class=side><div class=brand>◈ 维度直播保障</div><nav class=nav>${[['dashboard','工作台'],['customers','客户'],['rooms','直播间'],['devices','设备'],['reports','检查报告'],['support','故障处理'],['codes','激活码'],['releases','版本发布'],['settings','产品资料'],['profile','系统设置']].map(x=>`<button id=n-${x[0]} onclick="go('${x[0]}')">${x[1]}</button>`).join('')}</nav></aside><main class=main><div class=top><div><h1 id=title></h1><span class=muted id=subtitle></span></div><button class=secondary onclick=location.reload()>刷新</button></div><div id=content></div></main></div>`}
async function go(p){page=p;document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('on'));$('n-'+p)?.classList.add('on');let names={dashboard:'工作台',customers:'客户管理',rooms:'直播间管理',devices:'设备管理',reports:'检查报告',support:'故障处理',codes:'激活码管理',releases:'版本发布',settings:'产品资料',profile:'检测规则'};$('title').textContent=names[p];$('subtitle').textContent='';$('content').innerHTML='<div class=panel>正在加载…</div>';try{await window['load_'+p]()}catch(e){$('content').innerHTML='<div class=panel>'+esc(e.message)+'</div>'}}
async function load_dashboard(){let x=await api('/tk-api/stats'),s=x.report_statuses||{};$('content').innerHTML=`<div class=cards>${[['客户',x.customers],['直播间',x.rooms],['设备',x.devices],['今日检查',x.reports_today],['待处理',x.support_open],['可用激活码',x.codes_available]].map(a=>`<div class=card><span class=muted>${a[0]}</span><b>${a[1]}</b></div>`).join('')}</div><div class=grid><div class=panel><h3>今日检查结果</h3><p class=PASS>通过 ${s.PASS||0}</p><p class=WARNING>风险 ${s.WARNING||0}</p><p class=FAIL>失败 ${s.FAIL||0}</p></div><div class=panel><h3>最常见失败项目</h3>${x.top_faults.map(f=>`<p>${esc(f.title)} <span class=muted>${f.count} 次</span></p>`).join('')||'<p class=muted>暂无数据</p>'}</div><div class=panel><h3>客户端版本</h3>${x.versions.map(v=>`<p>${esc(v.app_version||'未知')} <span class=muted>${v.count} 台</span></p>`).join('')}</div><div class=panel><h3>当前发布</h3><p>${esc(x.active_release?.version||'暂无版本')}</p><p class=muted>${esc(x.active_release?.title||x.active_release?.notes||'')}</p></div></div>`}
function table(head,rows){return `<div class='panel tablewrap'><table><thead><tr>${head.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
async function load_customers(){let x=await api('/tk-api/customers');$('content').innerHTML=`<div class=toolbar><button class=primary onclick=customerModal()>新增客户</button><input id=q placeholder=搜索客户><button class=secondary onclick=searchCustomers()>搜索</button></div>`+table(['客户','联系方式','直播间','状态','备注'],x.customers.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.contact)}</td><td>${c.room_count}</td><td>${esc(c.status)}</td><td>${esc(c.notes)}</td></tr>`))}
async function searchCustomers(){let x=await api('/tk-api/customers?q='+encodeURIComponent(q.value));document.querySelector('tbody').innerHTML=x.customers.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.contact)}</td><td>${c.room_count}</td><td>${esc(c.status)}</td><td>${esc(c.notes)}</td></tr>`).join('')}
function customerModal(){modal('新增客户',`<div class=form><input id=cn placeholder=客户名称><input id=cc placeholder=联系方式><textarea id=cnotes placeholder=备注></textarea><button class=primary onclick=saveCustomer()>保存</button></div>`)}async function saveCustomer(){await post('/tk-api/customer/save',{name:cn.value,contact:cc.value,notes:cnotes.value,status:'active'});closeModal();go('customers')}
async function load_rooms(){let [x,c]=await Promise.all([api('/tk-api/rooms'),api('/tk-api/customers')]);window.customers=c.customers;$('content').innerHTML=`<div class=toolbar><button class=primary onclick=roomModal()>新增直播间</button></div>`+table(['直播间','客户','地区','码率','备注'],x.rooms.map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(r.customer)}</td><td>${esc(r.region)}</td><td>${r.bitrate_kbps} Kbps</td><td>${esc(r.notes)}</td></tr>`))}
function roomModal(){modal('新增直播间',`<div class=form><select id=rc>${(window.customers||[]).map(c=>`<option value=${c.id}>${esc(c.name)}</option>`).join('')}</select><input id=rn placeholder=直播间名称><input id=rr placeholder='目标地区，例如 US-Los Angeles'><input id=rb type=number value=6000 placeholder=码率><textarea id=rnotes placeholder=备注></textarea><button class=primary onclick=saveRoom()>保存</button></div>`)}async function saveRoom(){await post('/tk-api/room/save',{customer_id:+rc.value,name:rn.value,region:rr.value,bitrate_kbps:+rb.value,notes:rnotes.value});closeModal();go('rooms')}
async function load_devices(){let x=await api('/tk-api/devices');$('content').innerHTML=table(['设备编号','客户/直播间','版本','激活码','免费次数','最后在线'],x.devices.map(d=>`<tr><td>${esc(d.device_id)}</td><td>${esc(d.customer||d.customer_name)} / ${esc(d.room||d.room_name)}</td><td>${esc(d.app_version)}</td><td>${esc(d.license_code||'-')}</td><td>${d.free_uses_remaining}</td><td>${esc(d.last_seen)}</td></tr>`))}
async function load_reports(){let status=`<select id=rs><option value=''>全部状态</option><option>PASS</option><option>WARNING</option><option>FAIL</option><option>UNKNOWN</option></select>`;$('content').innerHTML=`<div class=toolbar>${status}<input id=rq placeholder='客户/直播间/设备'><button class=secondary onclick=filterReports()>筛选</button><button class=secondary onclick="location.href='/tk-api/reports/export'">导出</button></div><div id=rt></div>`;filterReports()}async function filterReports(){let x=await api('/tk-api/reports?status='+encodeURIComponent(rs.value)+'&q='+encodeURIComponent(rq.value));rt.innerHTML=table(['时间','客户/直播间','设备','结果','结论','操作'],x.reports.map(r=>`<tr><td>${esc(r.checked_at)}</td><td>${esc(r.customer_name)} / ${esc(r.room_name)}</td><td>${esc(r.device_id)}</td><td class=${r.overall_status}>${r.overall_status}</td><td>${esc(r.conclusion)}</td><td><button class=secondary onclick="reportModal('${r.report_id}')">详情</button></td></tr>`))}async function reportModal(id){let x=await api('/tk-api/report?id='+id);modal('报告 '+id,`<p>${esc(x.report.conclusion)}</p>`+table(['分类','状态','项目','值','建议'],x.items.map(i=>`<tr><td>${esc(i.category)}</td><td class=${i.status}>${i.status}</td><td>${esc(i.title)}</td><td>${esc(i.value)}</td><td>${esc(i.action||i.reason)}</td></tr>`)))}
async function load_support(){let x=await api('/tk-api/support');$('content').innerHTML=`<div class=toolbar><button class=primary onclick=supportModal()>新增故障单</button></div>`+table(['标题','设备','状态','负责人','更新时间','备注'],x.support.map(s=>`<tr><td>${esc(s.title)}</td><td>${esc(s.device_id)}</td><td>${esc(s.status)}</td><td>${esc(s.owner)}</td><td>${esc(s.updated_at)}</td><td>${esc(s.notes)}</td></tr>`))}function supportModal(){modal('新增故障单',`<div class=form><input id=st placeholder=故障标题><input id=sd placeholder=设备编号><input id=so placeholder=负责人><textarea id=sn placeholder=处理记录></textarea><button class=primary onclick=saveSupport()>保存</button></div>`)}async function saveSupport(){await post('/tk-api/support/save',{title:st.value,device_id:sd.value,owner:so.value,notes:sn.value,status:'open'});closeModal();go('support')}
async function load_codes(){let x=await api('/tk-api/codes');$('content').innerHTML=`<div class='panel grid'><div class=form><h3>批量生成</h3><select id=ct><option>TK1</option><option>TKX</option><option>TKV</option></select><input id=ccount type=number min=1 max=500 value=1><input id=cnote placeholder=客户或批次备注><button class=primary onclick=genCodes()>生成</button><textarea id=cout rows=6 placeholder=生成结果></textarea></div><div><h3>分类筛选</h3><div class=toolbar><select id=cs><option value=''>全部状态</option><option value=available>未使用</option><option value=distributed>已分发</option><option value=used>已激活</option><option value=exhausted>已耗尽</option><option value=revoked>已作废</option></select><select id=ctier><option value=''>全部档次</option><option>TK1</option><option>TKX</option><option>TKV</option></select></div><button class=secondary onclick=filterCodes()>筛选</button> <button class=secondary onclick="location.href='/tk-api/codes/export'">导出</button> <button class=secondary onclick=backup()>备份</button></div></div><div id=codetable></div>`;renderCodes(x.codes)}function renderCodes(rows){codetable.innerHTML=table(['激活码','档次','剩余','状态','绑定设备','使用','备注','操作'],rows.map(c=>`<tr><td>${esc(c.code)}</td><td>${c.tier}</td><td>${c.credits<0?'永久':c.credits}</td><td class=${c.status}>${c.status}</td><td>${esc(c.bound_device_id||'-')}</td><td>${c.used_count||0}</td><td>${esc(c.customer_note)}</td><td><select onchange="codeStatus('${c.code}',this.value)"><option value=''>切换</option><option value=available>未使用</option><option value=distributed>已分发</option><option value=used>已激活</option><option value=revoked>已作废</option></select></td></tr>`))}async function filterCodes(){let x=await api('/tk-api/codes?status='+cs.value+'&tier='+ctier.value);renderCodes(x.codes)}async function genCodes(){let x=await post('/tk-api/codes/generate',{tier:ct.value,count:+ccount.value,note:cnote.value});cout.value=x.codes.join('\n');filterCodes();toast('已生成 '+x.codes.length+' 个')}async function codeStatus(code,status){if(!status)return;await post('/tk-api/codes/status',{code,status});filterCodes();toast('状态已更新')}async function backup(){let x=await api('/tk-api/backup');toast('备份完成 '+x.file)}
async function load_releases(){let x=await api('/tk-api/releases');$('content').innerHTML=`<div class=grid><div class='panel form'><h3>发布新版本</h3><input id=rv placeholder='版本号，例如 2.0.0'><input id=rtitle placeholder=更新标题><textarea id=rnotes placeholder=更新摘要></textarea><textarea id=rdetails rows=7 placeholder=详细更新内容></textarea><input id=rfile type=file accept=.exe><button class=primary onclick=release()>上传并设为当前版本</button></div><div class=panel><h3>发布记录</h3>${x.releases.map(r=>`<div class=card><b>${esc(r.version)} ${r.active?'· 当前':''}</b><p>${esc(r.title||r.notes)}</p><small class=muted>SHA256 ${esc(r.sha256)}</small>${r.active?'':`<p><button class=secondary onclick="activateRelease('${r.version}')">回滚到此版本</button></p>`}</div>`).join('')}</div></div>`}async function release(){let fd=new FormData();fd.append('version',rv.value);fd.append('title',rtitle.value);fd.append('notes',rnotes.value);fd.append('details',rdetails.value);fd.append('file',rfile.files[0]);let r=await fetch('/tk-api/release',{method:'POST',headers:{'X-CSRF-Token':csrf},body:fd}),x=await r.json();if(!r.ok)throw Error(x.error);toast('发布成功');go('releases')}async function activateRelease(version){await post('/tk-api/release/activate',{version});go('releases')}
async function load_settings(){let x=await api('/tk-api/settings');$('content').innerHTML=`<div class='panel form'><input id=pn value='${esc(x.product_name)}' placeholder=产品名称><textarea id=pi rows=4 placeholder=产品介绍>${esc(x.product_intro)}</textarea><textarea id=pf rows=7 placeholder='产品特点，每行一项'>${esc(x.product_features)}</textarea><textarea id=pfaq rows=8 placeholder=常见问题>${esc(x.product_faq)}</textarea><textarea id=ps rows=3 placeholder=客服说明>${esc(x.support_text)}</textarea><textarea id=pc rows=5 placeholder=最新更新说明>${esc(x.latest_changelog)}</textarea><button class=primary onclick=saveSettings()>保存并同步下载页/关于页面</button></div>`}async function saveSettings(){await post('/tk-api/settings',{product_name:pn.value,product_intro:pi.value,product_features:pf.value,product_faq:pfaq.value,support_text:ps.value,latest_changelog:pc.value});toast('产品资料已保存')}
async function load_profile(){let x=await api('/tk-api/profile'),p=x.profile;$('content').innerHTML=`<div class='panel form'><p class=muted>客户端每次联网检测前读取当前规则。</p><input id=prn value='${esc(p.profile_name)}' placeholder=规则名称><div class=grid><label>上传倍数<input id=pum type=number step=.1 value=${p.upload_multiplier}></label><label>测速数据字节<input id=pub type=number value=${p.upload_test_bytes}></label><label>丢包风险 %<input id=plw type=number step=.1 value=${p.packet_loss_warning}></label><label>丢包失败 %<input id=plf type=number step=.1 value=${p.packet_loss_fail}></label><label>抖动风险 ms<input id=pjw type=number value=${p.jitter_warning_ms}></label><label>抖动失败 ms<input id=pjf type=number value=${p.jitter_fail_ms}></label><label>延迟风险 ms<input id=platw type=number value=${p.latency_warning_ms}></label><label>延迟失败 ms<input id=platf type=number value=${p.latency_fail_ms}></label></div><button class=primary onclick=saveProfile()>保存检测规则</button></div>`}async function saveProfile(){await post('/tk-api/profile',{profile_name:prn.value,upload_multiplier:+pum.value,upload_test_bytes:+pub.value,packet_loss_warning:+plw.value,packet_loss_fail:+plf.value,jitter_warning_ms:+pjw.value,jitter_fail_ms:+pjf.value,latency_warning_ms:+platw.value,latency_fail_ms:+platf.value,min_free_disk_gb:10});toast('检测规则已下发')}
async function post(url,data){return api(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)})}function modal(title,body){$('modal').innerHTML=`<div class=modal onclick="if(event.target===this)closeModal()"><div><div class=top><h2>${title}</h2><button class=secondary onclick=closeModal()>关闭</button></div>${body}</div></div>`}function closeModal(){$('modal').innerHTML=''}boot();
</script></body></html>"""


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"TK Live Platform listening on {LISTEN_HOST}:{LISTEN_PORT}")
    server.serve_forever()
