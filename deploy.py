import paramiko, os, hashlib, sys

HOST = "111.170.171.25"
USER = "root"
PASSWORD = os.environ.get("TK_DEPLOY_PASSWORD", "")
BASE = r"C:\Users\Administrator\Documents\Codex\2026-07-12\c-users-administrator-desktop-pro\work\tk_platform"

def main():
    if not PASSWORD:
        raise RuntimeError("请通过 TK_DEPLOY_PASSWORD 环境变量提供部署密码")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15, look_for_keys=False, allow_agent=False)
    sftp = ssh.open_sftp()

    print("[1/3] Uploading server code...")
    for root, dirs, files in os.walk(os.path.join(BASE, "server")):
        for f in files:
            if not f.endswith(".py"): continue
            local = os.path.join(root, f)
            rel = os.path.relpath(local, os.path.join(BASE, "server"))
            remote = "/opt/tk-platform/server/" + rel.replace(os.sep, "/")
            sftp.put(local, remote)
            print("  server/" + rel)

    print("[2/3] Uploading EXE...")
    LOCAL_EXE = os.path.join(BASE, "dist", "VD开播助手.exe")
    h = hashlib.sha256(open(LOCAL_EXE, "rb").read()).hexdigest()
    s = os.path.getsize(LOCAL_EXE)
    sftp.put(LOCAL_EXE, "/opt/tk-platform/downloads/VD开播助手-V2.8.1.exe")
    sftp.chmod("/opt/tk-platform/downloads/VD开播助手-V2.8.1.exe", 0o755)
    sftp.close()

    print("[3/3] Updating DB and restarting...")
    sql = 'INSERT OR REPLACE INTO releases(version,title,notes,details,filename,sha256,file_size,channel,active,created_at) VALUES("2.8.1","VD开播助手 V2.8.1","全局品牌升级、账号注册系统、84全球地区、个人中心、联系客服","完整更新: VD品牌、注册修复、UI优化、客服二维码、开播中心排版优化、关于产品介绍","VD开播助手-V2.8.1.exe","%s",%d,"stable",1,datetime("now")); UPDATE releases SET active=0 WHERE version!="2.8.1";' % (h, s)
    cmd = "cd /opt/tk-platform && sqlite3 database/platform.sqlite3 \"%s\" && systemctl restart tk-platform && echo SUCCESS" % sql.replace('"', '\\"')
    _, out, err = ssh.exec_command(cmd, timeout=30)
    print(out.read().decode()[:500])
    e = err.read().decode().strip()
    if e: print("warn:", e[:200])
    ssh.close()
    print("\nDeploy complete!")
    print("https://tk.aimj.xin")

if __name__ == "__main__":
    main()
