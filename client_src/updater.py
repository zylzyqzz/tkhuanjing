from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def wait_for_pid(pid: int, timeout: int = 60) -> None:
    if os.name != "nt":
        time.sleep(2); return
    for _ in range(timeout * 2):
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, creationflags=0x08000000)
        if str(pid).encode() not in result.stdout:
            return
        time.sleep(0.5)


def main() -> int:
    if len(sys.argv) != 5:
        return 2
    pid, target, url, expected = int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4].lower()
    temp = Path(tempfile.gettempdir()) / "weidu-tk-client-update.exe"
    try:
        urllib.request.urlretrieve(url, temp)
        if expected and sha256(temp).lower() != expected:
            temp.unlink(missing_ok=True); return 3
        wait_for_pid(pid)
        backup = target.with_suffix(target.suffix + ".old")
        backup.unlink(missing_ok=True)
        if target.exists(): os.replace(target, backup)
        os.replace(temp, target)
        subprocess.Popen([str(target)], cwd=str(target.parent))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

