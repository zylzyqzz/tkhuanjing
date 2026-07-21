#!/usr/bin/env bash
set -euo pipefail

root="${TK_DEPLOY_ROOT:-/opt/tk-platform}"
stamp="$(date +%Y%m%d-%H%M%S)"
target="$root/backups/verified-$stamp"
mkdir -p "$target"
cp -a "$root/current/deploy/.env.production" "$target/env.production"
readlink -f "$root/current" > "$target/current-release.txt"
python3 - "$root/runtime/platform.sqlite3" "$target/platform.sqlite3" <<'PY'
import sqlite3, sys
source = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
destination = sqlite3.connect(sys.argv[2])
try:
    source.backup(destination)
finally:
    destination.close()
    source.close()
with sqlite3.connect(sys.argv[2]) as db:
    assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
    db.execute("select 1 from check_reports limit 1").fetchall()
print("backup database verified")
PY
chmod -R go-rwx "$target"
echo "$target"
