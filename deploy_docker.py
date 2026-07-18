"""部署到服务器 Docker 容器"""
import paramiko, os, hashlib

HOST = "111.170.171.25"
USER = "root"
PASSWORD = os.environ.get("TK_DEPLOY_PASSWORD", "")
BASE = r"C:\Users\Administrator\Documents\Codex\2026-07-12\c-users-administrator-desktop-pro\work\tk_platform"
LOCAL_EXE = os.path.join(BASE, "dist", "VD开播助手.exe")

def main():
    if not PASSWORD:
        raise RuntimeError("请通过 TK_DEPLOY_PASSWORD 环境变量提供部署密码")
    h = hashlib.sha256(open(LOCAL_EXE, "rb").read()).hexdigest()
    s = os.path.getsize(LOCAL_EXE)

    print("正在连接服务器...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15, look_for_keys=False, allow_agent=False)

    # 1. Copy server code into container
    print("[1/4] 上传后端代码到 Docker...")
    server_dir = os.path.join(BASE, "server")
    for root, dirs, files in os.walk(server_dir):
        for f in files:
            if not f.endswith(".py"):
                continue
            local = os.path.join(root, f)
            rel = os.path.relpath(local, server_dir)
            dest = rel.replace(os.sep, "/")
            cmd = 'docker cp "%s" tk-platform:/app/server/%s' % (local.replace("\\", "/"), dest)
            ssh.exec_command(cmd, timeout=10)

    # 2. Upload EXE
    print("[2/4] 上传安装包到 Docker...")
    cmd = 'docker cp "%s" tk-platform:/app/downloads/VD开播助手-V2.8.1.exe' % LOCAL_EXE.replace("\\", "/")
    ssh.exec_command(cmd, timeout=30)

    # 3. Update database
    print("[3/4] 更新数据库...")
    sql = 'INSERT OR REPLACE INTO releases(version,title,notes,filename,sha256,file_size,channel,active,created_at) VALUES("2.8.1","VD开播助手 V2.8.1","全局品牌升级、账号系统、84地区、UI优化、联系客服","VD开播助手-V2.8.1.exe","%s",%d,"stable",1,datetime("now")); UPDATE releases SET active=0 WHERE version!="2.8.1";' % (h, s)
    cmd = 'docker exec tk-platform sqlite3 /app/database/platform.sqlite3 "%s"' % sql.replace('"', '\\"')
    _, out, err = ssh.exec_command(cmd, timeout=15)
    r = (out.read().decode() + err.read().decode()).strip()
    if r:
        print("  DB:", r[:200])

    # 4. Restart container
    print("[4/4] 重启容器...")
    _, out, _ = ssh.exec_command("docker restart tk-platform", timeout=15)
    print("  ", out.read().decode().strip()[:100])

    ssh.close()

    # 5. Verify
    import time
    print("\n等待服务启动...")
    time.sleep(5)
    import urllib.request
    try:
        resp = urllib.request.urlopen("https://tk.aimj.xin/", timeout=10)
        html = resp.read().decode()
        import re
        m = re.search(r"下载 V([0-9.]+)", html)
        if m:
            print("主页版本: V" + m.group(1))
            if m.group(1) == "2.8.1":
                print("✅ 部署成功！")
            else:
                print("⚠️ 版本不对，可能需要重启容器或检查后等待")
        else:
            print("页面已更新")
    except Exception as e:
        print("验证时出错:", e)
        print("可能 HTTPS 需要时间生效，手动访问 https://tk.aimj.xin 确认")

if __name__ == "__main__":
    main()
