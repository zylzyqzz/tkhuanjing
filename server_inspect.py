import os
import paramiko
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    os.environ["TK_SSH_HOST"],
    username=os.environ["TK_SSH_USER"],
    password=os.environ["TK_SSH_PASSWORD"],
    timeout=15,
)
command = r"""
set -e
echo 'OS:'; . /etc/os-release; echo "$ID $VERSION_ID"
echo 'SERVICES:'; systemctl is-active tk-platform nginx 2>/dev/null || true
echo 'PORTS:'; ss -lntp | grep -E ':(80|443|39999)\b' || true
echo 'NGINX-CONFIGS:'; find /etc/nginx -maxdepth 3 -type f \( -name '*.conf' -o -path '*/sites-enabled/*' \) -print 2>/dev/null
echo 'SERVER-NAMES:'; nginx -T 2>/dev/null | grep -E 'server_name|listen 443|proxy_pass' || true
echo 'DOMAIN-CONFIG:'; cat /etc/nginx/conf.d/v.wdai.cc.conf 2>/dev/null || true
echo 'TK-SERVICE:'; systemctl cat tk-platform 2>/dev/null | sed -E 's/(PASSWORD_HASH|LICENSE_SECRET)=.*/\1=REDACTED/' || true
echo 'NGINX-STATUS:'; systemctl status nginx --no-pager -l 2>/dev/null | tail -20 || true
echo 'CERTBOT:'; certbot --version 2>/dev/null || true
echo 'CERTS:'; find /etc/letsencrypt/live -maxdepth 2 -type l -print 2>/dev/null || true
echo 'FIREWALL:'; (ufw status 2>/dev/null || firewall-cmd --list-all 2>/dev/null || true)
echo 'LOCAL-API:'; curl -fsS --max-time 5 http://127.0.0.1:39999/api/client/update || true
"""
_, stdout, stderr = client.exec_command(command, timeout=40)
print(stdout.read().decode("utf-8", errors="replace"))
errors = stderr.read().decode("utf-8", errors="replace").strip()
if errors:
    print("STDERR:", errors)
client.close()
