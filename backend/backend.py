#!/usr/bin/env python3
import cgi
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import shutil
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.environ.get("TK_PLATFORM_ROOT", "/opt/tk-platform")
DB = os.path.join(ROOT, "database", "platform.sqlite3")
DOWNLOADS = os.path.join(ROOT, "downloads")
BACKUPS = os.path.join(ROOT, "backups")
ADMIN_USER = os.environ.get("TK_ADMIN_USER", "admin")
ADMIN_HASH = os.environ["TK_ADMIN_PASSWORD_HASH"]
LICENSE_SECRET = os.environ.get("TK_LICENSE_SECRET", "TKEnvConfigPro2026SecretKey!!").encode()
PUBLIC_BASE = os.environ.get("TK_PUBLIC_BASE", "http://v.wdai.cc:39999")
SESSIONS = {}
LOGIN_ATTEMPTS = {}
TIERS = {"TK1": (1, "1次"), "TKX": (10, "10次"), "TKV": (-1, "永久VIP")}


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("create table if not exists codes (code text primary key, tier text, credits integer, status text, created_at text)")
    c.execute("create table if not exists releases (version text primary key, notes text, filename text, sha256 text, created_at text, active integer default 0)")
    c.commit()
    return c


def password_ok(password):
    try:
        salt, expected = ADMIN_HASH.split("$", 1)
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 240000).hex()
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def sign(rand):
    digest = hmac.new(LICENSE_SECRET, rand.encode(), hashlib.sha256).digest()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = 0
    count = 0
    out = []
    for b in digest[:5]:
        bits = (bits << 8) | b
        count += 8
        while count >= 5:
            count -= 5
            out.append(alphabet[(bits >> count) & 31])
    return "".join(out)[:5]


def make_code(tier):
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        rand = "".join(secrets.choice(chars) for _ in range(5))
        code = f"{tier}-{rand}-{sign(rand)}"
        with db() as c:
            if not c.execute("select 1 from codes where code=?", (code,)).fetchone():
                return code


def version_key(value):
    try:
        return tuple(int(x) for x in value.split("."))
    except Exception:
        return (0,)


def active_release():
    with db() as c:
        row = c.execute("select * from releases where active=1 order by created_at desc limit 1").fetchone()
        if not row:
            row = c.execute("select * from releases order by created_at desc limit 1").fetchone()
        return dict(row) if row else None


def send_json(handler, value, status=200):
    body = json.dumps(value, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "TKPlatform/1.0"

    def log_message(self, fmt, *args):
        pass

    def session(self):
        raw = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie(); jar.load(raw)
        token = jar.get("tk_session")
        return token and SESSIONS.get(token.value)

    def csrf_ok(self):
        return self.headers.get("X-CSRF-Token") == (self.session() or {}).get("csrf")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/client/update":
            release = active_release()
            if not release:
                send_json(self, {"version": "0.0.0", "notes": "暂无更新", "url": "", "sha256": ""})
            else:
                send_json(self, {"version": release["version"], "notes": release["notes"], "url": PUBLIC_BASE + "/downloads/" + release["filename"], "sha256": release["sha256"]})
            return
        if path == "/download/":
            self.download_page(); return
        if path == "/tk-admin/":
            self.admin_page(); return
        if path == "/tk-api/session":
            s = self.session()
            send_json(self, {"logged_in": bool(s), "csrf": s.get("csrf") if s else ""})
            return
        if path == "/tk-api/codes":
            if not self.session(): send_json(self, {"error": "unauthorized"}, 401); return
            with db() as c: rows = [dict(x) for x in c.execute("select * from codes order by created_at desc limit 2000")]
            send_json(self, {"codes": rows}); return
        if path == "/tk-api/codes/export":
            if not self.session(): send_json(self, {"error": "unauthorized"}, 401); return
            with db() as c: rows = c.execute("select code,tier,credits,status,created_at from codes order by created_at desc").fetchall()
            body = ("code\ttier\tcredits\tstatus\tcreated_at\n" + "\n".join("\t".join(str(v) for v in row) for row in rows)).encode()
            self.send_response(200); self.send_header("Content-Type", "text/tab-separated-values; charset=utf-8"); self.send_header("Content-Disposition", "attachment; filename=codes.tsv"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path == "/tk-api/backup":
            if not self.session(): send_json(self, {"error": "unauthorized"}, 401); return
            os.makedirs(BACKUPS, exist_ok=True); name = "platform-backup-" + time.strftime("%Y%m%d-%H%M%S") + ".sqlite3"; target = os.path.join(BACKUPS, name)
            with db() as c: c.execute("vacuum")
            shutil.copy2(DB, target); send_json(self, {"ok": True, "file": name}); return
        if path == "/tk-api/releases":
            if not self.session(): send_json(self, {"error": "unauthorized"}, 401); return
            with db() as c: rows = [dict(x) for x in c.execute("select * from releases order by created_at desc")]
            send_json(self, {"releases": rows}); return
        send_json(self, {"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/tk-api/login": self.login(); return
        if not self.session() or not self.csrf_ok(): send_json(self, {"error": "unauthorized"}, 401); return
        if path == "/tk-api/codes/generate": self.generate(); return
        if path == "/tk-api/release": self.release(); return
        if path == "/tk-api/release/activate": self.activate_release(); return
        send_json(self, {"error": "not found"}, 404)

    def login(self):
        ip = self.client_address[0]; now = time.time(); recent = [x for x in LOGIN_ATTEMPTS.get(ip, []) if now - x < 600]
        if len(recent) >= 10: send_json(self, {"error": "登录尝试过于频繁"}, 429); return
        LOGIN_ATTEMPTS[ip] = recent + [now]
        length = int(self.headers.get("Content-Length", 0)); data = parse_qs(self.rfile.read(length).decode())
        if data.get("username", [""])[0] != ADMIN_USER or not password_ok(data.get("password", [""])[0]): send_json(self, {"error": "账号或密码错误"}, 403); return
        token = secrets.token_urlsafe(32); csrf = secrets.token_urlsafe(24); SESSIONS[token] = {"user": ADMIN_USER, "csrf": csrf, "created": now}
        body = json.dumps({"ok": True, "csrf": csrf}).encode()
        self.send_response(200); self.send_header("Set-Cookie", f"tk_session={token}; HttpOnly; SameSite=Strict; Path=/"); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def generate(self):
        length = int(self.headers.get("Content-Length", 0)); data = json.loads(self.rfile.read(length)); tier = data.get("tier"); count = int(data.get("count", 1))
        if tier not in TIERS or not 1 <= count <= 500: send_json(self, {"error": "参数错误"}, 400); return
        codes = [make_code(tier) for _ in range(count)]
        with db() as c:
            for code in codes: c.execute("insert into codes values (?,?,?,?,datetime('now'))", (code, tier, TIERS[tier][0], "available"))
            c.commit()
        send_json(self, {"codes": codes})

    def release(self):
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")})
        version = (form.getfirst("version") or "").strip(); notes = (form.getfirst("notes") or "").strip(); item = form["file"] if "file" in form else None
        if not re.fullmatch(r"\d+\.\d+\.\d+", version) or not item: send_json(self, {"error": "版本号或文件错误"}, 400); return
        filename = f"client-{version}.exe"; temp = os.path.join(DOWNLOADS, filename + ".tmp"); final = os.path.join(DOWNLOADS, filename); h = hashlib.sha256()
        with open(temp, "wb") as out:
            while True:
                block = item.file.read(1024 * 1024)
                if not block: break
                out.write(block); h.update(block)
        os.replace(temp, final)
        with db() as c:
            current = c.execute("select version from releases where active=1 order by created_at desc limit 1").fetchone()
            def vk(value):
                return tuple(int(x) for x in str(value).split("."))
            activate = 1 if not current or vk(version) >= vk(current[0]) else 0
            c.execute("insert or replace into releases values (?,?,?,?,datetime('now'),?)", (version, notes, filename, h.hexdigest(), activate))
            if activate:
                c.execute("update releases set active=case when version=? then 1 else 0 end", (version,))
            c.commit()
        send_json(self, {"version": version, "sha256": h.hexdigest(), "filename": filename})

    def activate_release(self):
        length = int(self.headers.get("Content-Length", 0)); version = json.loads(self.rfile.read(length)).get("version")
        with db() as c: c.execute("update releases set active=case when version=? then 1 else 0 end", (version,)); c.commit()
        send_json(self, {"ok": True})

    def admin_page(self):
        body = """<!doctype html><meta charset=utf-8><title>TK后台</title><style>body{font-family:Arial;background:#111827;color:#e5e7eb;max-width:1100px;margin:30px auto;padding:0 20px}section{background:#1f2937;padding:20px;margin:14px 0;border-radius:12px}input,select,button{padding:10px;margin:5px;border-radius:6px;border:0}button{background:#60a5fa;cursor:pointer}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #374151;text-align:left}</style><h1>TK 激活码与更新后台</h1><div id=app>加载中...</div><script>
async function j(u,o){let r=await fetch(u,o);let x=await r.json();if(!r.ok)throw Error(x.error||r.status);return x}let csrf='';
async function boot(){let s=await j('/tk-api/session');if(!s.logged_in){document.getElementById('app').innerHTML='<section><h2>管理员登录</h2><input id=u placeholder=账号><input id=p type=password placeholder=密码><button onclick=login()>登录</button><p id=e></p></section>';return}csrf=s.csrf;render()}
async function login(){try{await j('/tk-api/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'username='+encodeURIComponent(u.value)+'&password='+encodeURIComponent(p.value)});location.reload()}catch(e){document.getElementById('e').textContent=e}}
async function render(){let c=await j('/tk-api/codes'),r=await j('/tk-api/releases');document.getElementById('app').innerHTML='<section><h2>生成激活码</h2><select id=t><option>TK1</option><option>TKX</option><option>TKV</option></select><input id=n type=number value=1 min=1 max=500><button onclick=gen()>生成</button><pre id=out></pre></section><section><h2>发布更新</h2><input id=v placeholder=版本号，例如 1.0.2><input id=note placeholder=更新说明><input id=f type=file accept=.exe><button onclick=upload()>上传版本</button></section><section><h2>激活码</h2><table><tr><th>激活码</th><th>档次</th><th>状态</th><th>时间</th></tr>'+c.codes.map(x=>'<tr><td>'+x.code+'</td><td>'+x.tier+'</td><td>'+x.status+'</td><td>'+x.created_at+'</td></tr>').join('')+'</table></section><section><h2>发布记录</h2>'+r.releases.map(x=>'<p>'+x.version+' · '+x.notes+' · SHA256 '+x.sha256+'</p>').join('')+'</section>'}
async function gen(){let x=await j('/tk-api/codes/generate',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({tier:t.value,count:+n.value})});out.textContent=x.codes.join('\\n')}
async function upload(){let fd=new FormData();fd.append('version',v.value);fd.append('notes',note.value);fd.append('file',f.files[0]);let r=await fetch('/tk-api/release',{method:'POST',headers:{'X-CSRF-Token':csrf},body:fd});let x=await r.json();if(!r.ok)throw Error(x.error);alert('上传成功：'+x.version);location.reload()}boot()</script>"""
        data = body.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def download_page(self):
        r = active_release(); version = r["version"] if r else "\u6682\u65e0\u7248\u672c"; link = "/downloads/setup-" + r["version"] + ".exe" if r else "#"
        data = f"""<!doctype html><meta charset=utf-8><title>\u7ef4\u5ea6TK\u73af\u5883\u52a9\u624b\u4e0b\u8f7d</title><style>body{{margin:0;font-family:Arial,'Microsoft YaHei';background:#0f172a;color:#e5e7eb}}main{{max-width:960px;margin:0 auto;padding:72px 22px}}.hero{{background:linear-gradient(135deg,#1d4ed8,#4338ca);padding:46px;border-radius:24px;box-shadow:0 24px 70px #02061788}}h1{{font-size:42px;margin:0 0 14px}}p{{line-height:1.8;color:#cbd5e1}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:22px}}.card{{background:#1e293b;padding:22px;border-radius:16px}}.download{{display:inline-block;margin-top:20px;background:#f8fafc;color:#1e3a8a;padding:15px 34px;border-radius:10px;text-decoration:none;font-weight:bold}}small{{color:#94a3b8}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}</style><main><section class=hero><small>\u8f7b\u91cf\u3001\u7a33\u5b9a\u3001\u6613\u4e8e\u4f7f\u7528</small><h1>\u7ef4\u5ea6 TK \u73af\u5883\u52a9\u624b</h1><p>\u4e3a\u65e5\u5e38\u7535\u8111\u4f7f\u7528\u63d0\u4f9b\u5b9e\u7528\u7684\u73af\u5883\u8f85\u52a9\u3001\u6e05\u7406\u4e0e\u5de5\u5177\u7ba1\u7406\u529f\u80fd\uff0c\u64cd\u4f5c\u7b80\u5355\u3001\u754c\u9762\u6e05\u6670\u3002</p><a class=download href='{html.escape(link)}'>\u4e0b\u8f7d\u5b89\u88c5\u7a0b\u5e8f</a><p><small>\u5f53\u524d\u7248\u672c\uff1a{html.escape(version)}\uff0c\u5b89\u88c5\u540e\u5c06\u81ea\u52a8\u521b\u5efa\u684c\u9762\u5feb\u6377\u65b9\u5f0f</small></p></section><section class=grid><div class=card><h3>\u7b80\u6d01\u64cd\u4f5c</h3><p>\u5e38\u7528\u529f\u80fd\u96c6\u4e2d\u5c55\u793a\uff0c\u6309\u7167\u63d0\u793a\u5373\u53ef\u4f7f\u7528\u3002</p></div><div class=card><h3>\u66f4\u65b0\u65b9\u4fbf</h3><p>\u5ba2\u6237\u7aef\u53ef\u68c0\u67e5\u65b0\u7248\u672c\uff0c\u66f4\u65b0\u524d\u81ea\u52a8\u6821\u9a8c\u6587\u4ef6\u5b8c\u6574\u6027\u3002</p></div><div class=card><h3>\u5b89\u5168\u53ef\u9760</h3><p>\u4e0b\u8f7d\u5305\u4e0e\u66f4\u65b0\u5305\u5747\u4fdd\u7559\u7248\u672c\u8bb0\u5f55\uff0c\u65b9\u4fbf\u7ba1\u7406\u4e0e\u56de\u6eaf\u3002</p></div></section></main>"""
        data = data.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


os.makedirs(os.path.dirname(DB), exist_ok=True); os.makedirs(DOWNLOADS, exist_ok=True); db().close()
ThreadingHTTPServer(("127.0.0.1", 39200), Handler).serve_forever()
