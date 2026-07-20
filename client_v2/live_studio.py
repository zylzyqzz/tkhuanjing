from __future__ import annotations

import os
from pathlib import Path
import subprocess


def candidate_paths(custom_path: str = "") -> list[Path]:
    values = [custom_path, os.environ.get("TIKTOK_LIVE_STUDIO_PATH", "")]
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    programs = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    values += [
        str(local / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe"),
        str(local / "Programs" / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe"),
        str(programs / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe"),
    ]
    seen: set[str] = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(Path(value))
    return result


def find_live_studio(custom_path: str = "") -> Path | None:
    return next((path for path in candidate_paths(custom_path) if path.is_file()), None)


def launch_live_studio(custom_path: str = "") -> Path:
    path = find_live_studio(custom_path)
    if not path:
        raise FileNotFoundError("未检测到 TikTok LIVE Studio")
    subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
    return path
