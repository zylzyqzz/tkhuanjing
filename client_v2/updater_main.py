from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

import psutil


def wait_process(pid: int, timeout: int = 60) -> None:
    try:
        process = psutil.Process(pid); process.wait(timeout=timeout)
    except (psutil.NoSuchProcess, psutil.TimeoutExpired):
        return


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--installer", type=Path, required=True); parser.add_argument("--wait-pid", type=int, required=True); parser.add_argument("--restart", type=Path, required=True); args = parser.parse_args()
    wait_process(args.wait_pid)
    if not args.installer.is_file(): return 2
    result = subprocess.run([str(args.installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS", "/NORESTART"], timeout=300)
    if result.returncode != 0: return result.returncode
    if args.restart.exists(): subprocess.Popen([str(args.restart)], close_fds=True)
    time.sleep(1); return 0


if __name__ == "__main__":
    raise SystemExit(main())
