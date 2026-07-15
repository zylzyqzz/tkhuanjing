from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import posixpath
import shlex
import sys
import time

import paramiko


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOCAL_ROOT = Path(__file__).resolve().parent
VERSION = "2.0.0"


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(os.environ["TK_SSH_HOST"], username=os.environ["TK_SSH_USER"], password=os.environ["TK_SSH_PASSWORD"], timeout=20)
    return client


def run(client: paramiko.SSHClient, command: str, timeout: int = 120) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace")
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"remote command failed ({status}): {error or output}")
    return output + error


def put_atomic(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    temp = remote + ".uploading"
    sftp.put(str(local), temp)
    sftp.rename(temp, remote)


def main() -> None:
    backend = LOCAL_ROOT / "backend.py"
    client_exe = LOCAL_ROOT / "dist_client" / "TKLiveCheck.exe"
    installer = LOCAL_ROOT / "dist_setup" / "维度TikTok直播开播助手安装程序-2.0.0.exe"
    for path in (backend, client_exe, installer):
        if not path.is_file():
            raise FileNotFoundError(path)
    digest = hashlib.sha256(client_exe.read_bytes()).hexdigest()
    client = connect(); sftp = client.open_sftp()
    try:
        run(client, "mkdir -p /opt/tk-platform/backend /opt/tk-platform/downloads /opt/tk-platform/database /opt/tk-platform/backups /var/www/acme")
        put_atomic(sftp, backend, "/opt/tk-platform/backend.py.new")
        put_atomic(sftp, client_exe, f"/opt/tk-platform/downloads/client-{VERSION}.exe")
        put_atomic(sftp, installer, f"/opt/tk-platform/downloads/setup-{VERSION}.exe")
        command = f"""
set -e
cp -a /opt/tk-platform/backend.py /opt/tk-platform/backups/backend.py.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
mv /opt/tk-platform/backend.py.new /opt/tk-platform/backend.py
chmod 755 /opt/tk-platform/backend.py
python3 -m py_compile /opt/tk-platform/backend.py
systemctl restart tk-platform
sleep 2
systemctl is-active tk-platform
curl -fsS http://127.0.0.1:39200/api/client/update
python3 - <<'PY'
import sqlite3, datetime
p='/opt/tk-platform/database/platform.sqlite3'
c=sqlite3.connect(p)
c.execute("update releases set active=0")
c.execute("insert or replace into releases(version,title,notes,details,filename,installer_filename,sha256,created_at,active) values(?,?,?,?,?,?,?,?,1)", (
  '{VERSION}', '开播检测系统 V1', '全新开播前技术检查、报告与设备管理',
  '新增网络、性能、直播软件、摄像头、麦克风、系统和客户端完整性检查；新增本地报告、后台上传、设备绑定和短期离线授权；重建正式安装程序并嵌入付款二维码、客服二维码和产品 Logo。',
  'client-{VERSION}.exe', 'setup-{VERSION}.exe', '{digest}', datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 1))
c.execute("insert or replace into settings(key,value) values('latest_changelog',?)", ('{VERSION}：开播检测系统 V1\\n新增综合检测、检查报告、设备管理和短期离线授权。',))
c.commit()
PY
"""
        print(run(client, command, 180))
    finally:
        sftp.close(); client.close()


if __name__ == "__main__":
    main()
