# encoding: utf-8
import paramiko, hashlib, os, sys, time, urllib.request, re

sys.stdout.reconfigure(encoding='utf-8')

HOST = '111.170.171.25'
USER = 'root'
PASSWORD = os.environ.get('TK_DEPLOY_PASSWORD', '')
BASE = r'C:\Users\Administrator\Desktop\VD开播助手_V2.8.1'

if not PASSWORD:
    raise RuntimeError('请通过 TK_DEPLOY_PASSWORD 环境变量提供部署密码')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15, look_for_keys=False, allow_agent=False)
sftp = ssh.open_sftp()

# === STEP 1: Upload server code to container ===
print('[1/5] Upload server code to container...')
server_dir = os.path.join(BASE, 'server')
sftp.put(os.path.join(BASE, 'server', 'public_page.py'), '/tmp/tk-public_page.py')
sftp.put(os.path.join(BASE, 'server', 'main.py'), '/tmp/tk-main.py')
sftp.put(os.path.join(BASE, 'server', 'models.py'), '/tmp/tk-models.py')
sftp.put(os.path.join(BASE, 'server', 'config.py'), '/tmp/tk-config.py')
sftp.put(os.path.join(BASE, 'server', 'database.py'), '/tmp/tk-database.py')
sftp.put(os.path.join(BASE, 'server', 'email_utils.py'), '/tmp/tk-email_utils.py')
sftp.put(os.path.join(BASE, 'server', 'manage.py'), '/tmp/tk-manage.py')
sftp.put(os.path.join(BASE, 'server', 'migrate.py'), '/tmp/tk-migrate.py')
sftp.put(os.path.join(BASE, 'server', 'schemas.py'), '/tmp/tk-schemas.py')
sftp.put(os.path.join(BASE, 'server', 'security.py'), '/tmp/tk-security.py')
sftp.put(os.path.join(BASE, 'server', 'services.py'), '/tmp/tk-services.py')
sftp.put(os.path.join(BASE, 'server', '__init__.py'), '/tmp/tk-__init__.py')
sftp.put(os.path.join(BASE, 'server', 'routers', 'admin.py'), '/tmp/tk-routers-admin.py')
sftp.put(os.path.join(BASE, 'server', 'routers', 'client.py'), '/tmp/tk-routers-client.py')
sftp.put(os.path.join(BASE, 'server', 'routers', '__init__.py'), '/tmp/tk-routers-__init__.py')

# docker cp into container
files_map = [
    ('/tmp/tk-public_page.py', '/app/server/public_page.py'),
    ('/tmp/tk-main.py', '/app/server/main.py'),
    ('/tmp/tk-models.py', '/app/server/models.py'),
    ('/tmp/tk-config.py', '/app/server/config.py'),
    ('/tmp/tk-database.py', '/app/server/database.py'),
    ('/tmp/tk-email_utils.py', '/app/server/email_utils.py'),
    ('/tmp/tk-manage.py', '/app/server/manage.py'),
    ('/tmp/tk-migrate.py', '/app/server/migrate.py'),
    ('/tmp/tk-schemas.py', '/app/server/schemas.py'),
    ('/tmp/tk-security.py', '/app/server/security.py'),
    ('/tmp/tk-services.py', '/app/server/services.py'),
    ('/tmp/tk-__init__.py', '/app/server/__init__.py'),
    ('/tmp/tk-routers-admin.py', '/app/server/routers/admin.py'),
    ('/tmp/tk-routers-client.py', '/app/server/routers/client.py'),
    ('/tmp/tk-routers-__init__.py', '/app/server/routers/__init__.py'),
]
for src, dst in files_map:
    ssh.exec_command('docker cp ' + src + ' tk-platform:' + dst)
    print('  ' + dst.split('/')[-1])
print('  Server code done')

# === STEP 2: Upload EXE ===
print('[2/5] Upload EXE...')
local_exe = os.path.join(BASE, 'dist', 'VD开播助手.exe')
h = hashlib.sha256(open(local_exe, 'rb').read()).hexdigest()
sz = os.path.getsize(local_exe)
sftp.put(local_exe, '/tmp/VD开播助手-V2.8.1.exe')
ssh.exec_command('docker cp /tmp/VD开播助手-V2.8.1.exe tk-platform:/app/downloads/VD开播助手-V2.8.1.exe')
print('  SHA256: ' + h[:16] + '... Size: ' + str(sz))

# === STEP 3: Update DB on host (mounted at /data) ===
print('[3/5] Update DB...')
db_path = '/opt/tk-platform/runtime/database/platform.sqlite3'
cmd = 'sqlite3 ' + db_path + ' "SELECT version,active FROM releases;"'
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
print('  Before: ' + stdout.read().decode().strip())

sql = "INSERT OR REPLACE INTO releases(version,title,notes,filename,sha256,file_size,channel,active,created_at) VALUES('2.8.1','VD开播助手 V2.8.1','新版UI品牌升级','VD开播助手-V2.8.1.exe','" + h + "'," + str(sz) + ",'stable',1,datetime('now')); UPDATE releases SET active=0 WHERE version!='2.8.1';"
escaped = sql.replace('"', '\\"')
cmd = 'sqlite3 ' + db_path + ' "' + escaped + '"'
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
err_out = stderr.read().decode().strip()
if err_out:
    print('  DB err: ' + err_out[:200])

stdin, stdout, stderr = ssh.exec_command('sqlite3 ' + db_path + ' "SELECT version,active FROM releases;"', timeout=15)
print('  After: ' + stdout.read().decode().strip())

# === STEP 4: Restart ===
print('[4/5] Restart container...')
ssh.exec_command('docker restart tk-platform')
print('  Restarted')

sftp.close()
ssh.close()

# === STEP 5: Verify ===
print('\n[5/5] Verify...')
time.sleep(12)
try:
    resp = urllib.request.urlopen('https://tk.aimj.xin/', timeout=20)
    html = resp.read().decode('utf-8')
    m = re.search(r'下载 V([0-9.]+)', html)
    if m:
        v = m.group(1)
        print('Homepage version: V' + v)
        if v == '2.8.1':
            print('*** DEPLOY SUCCESS! ***')
        else:
            print('WARNING: version mismatch, expected 2.8.1 got ' + v)
    else:
        print('No version found on page')
except Exception as e:
    print('Verify error: ' + str(e))

print('\nDone.')
