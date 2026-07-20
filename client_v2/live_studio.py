from __future__ import annotations

import os
from pathlib import Path
import subprocess

from .checks import powershell


def candidate_paths(custom_path: str = "") -> list[Path]:
    values = [custom_path, os.environ.get("TIKTOK_LIVE_STUDIO_PATH", "")]
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    programs = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    values += [
        str(local / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe"),
        str(local / "Programs" / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe"),
        str(programs / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe"),
    ]
    if os.name == "nt":
        try:
            discovered = powershell(
                "$keys=Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' -ErrorAction SilentlyContinue | "
                "Where-Object {$_.DisplayName -match 'TikTok LIVE Studio'}; ($keys.DisplayIcon -replace ',\\d+$','') -join \"`n\""
            )
            values += discovered.splitlines()
        except Exception:
            pass
    seen: set[str] = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(Path(value))
    return result


def find_live_studio(custom_path: str = "") -> Path | None:
    return next((path for path in candidate_paths(custom_path) if is_trusted_live_studio(path)), None)


def is_trusted_live_studio(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".exe" or "tiktok" not in path.name.lower():
        return False
    if os.name != "nt":
        return True
    try:
        escaped = str(path).replace("'", "''")
        result = powershell(f"(Get-AuthenticodeSignature -LiteralPath '{escaped}').Status")
        return result in {"Valid", "NotSigned"}  # Development builds may be unsigned; surface status separately.
    except Exception:
        return False


def launch_live_studio(custom_path: str = "") -> Path:
    path = find_live_studio(custom_path)
    if not path:
        raise FileNotFoundError("未检测到 TikTok LIVE Studio")
    subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
    return path
