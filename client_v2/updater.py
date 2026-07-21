from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import httpx

from .storage import DATA_DIR


class UpdateError(RuntimeError):
    """Raised when an update cannot be verified or safely installed."""


def manifest_payload(manifest: dict) -> bytes:
    excluded = {"signature", "public_key"}
    core = {key: value for key, value in manifest.items() if key not in excluded}
    return json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def verify_manifest(manifest: dict) -> None:
    signature, public_key = manifest.get("signature", ""), manifest.get("public_key", "")
    if not signature and not public_key:
        raise UpdateError("更新清单未签名，已拒绝下载")
    if not signature or not public_key:
        raise UpdateError("更新签名信息不完整")
    try:
        key = serialization.load_pem_public_key(public_key.encode())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("not Ed25519")
        key.verify(base64.b64decode(signature), manifest_payload(manifest))
    except Exception as exc:
        raise UpdateError("更新清单签名校验失败") from exc


def download_update(manifest: dict, progress: Callable[[int, str], None], cancelled: Callable[[], bool]) -> Path:
    verify_manifest(manifest)
    expected_size = int(manifest.get("file_size", 0)); expected_hash = manifest.get("sha256", "").lower()
    if not expected_size or len(expected_hash) != 64:
        raise UpdateError("更新清单缺少文件大小或 SHA-256")
    folder = DATA_DIR / "updates"; folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(manifest.get("filename") or f"client-{manifest['version']}.exe").name
    temp = target.with_suffix(target.suffix + ".part"); digest = hashlib.sha256(); received = 0
    try:
        with httpx.stream("GET", manifest["url"], timeout=httpx.Timeout(60, connect=10), follow_redirects=True) as response:
            response.raise_for_status()
            with temp.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 256):
                    if cancelled(): raise UpdateError("更新已取消")
                    received += len(chunk)
                    if received > expected_size: raise UpdateError("下载文件大小超过更新清单")
                    digest.update(chunk); output.write(chunk); progress(int(received / expected_size * 100), f"正在下载 {received / 1048576:.1f} / {expected_size / 1048576:.1f} MB")
        if received != expected_size: raise UpdateError("更新文件大小不正确")
        if digest.hexdigest().lower() != expected_hash: raise UpdateError("更新文件 SHA-256 校验失败")
        os.replace(temp, target); return target
    except Exception:
        temp.unlink(missing_ok=True); raise


def launch_helper(installer: Path) -> None:
    base = Path(sys.executable).resolve().parent
    helper = base / "TKUpdater.exe"
    if not helper.exists():
        candidate = Path(__file__).resolve().parents[1] / "dist_updater_v2" / "TKUpdater.exe"
        helper = candidate if candidate.exists() else helper
    if not helper.exists(): raise UpdateError("独立更新助手缺失，请重新安装客户端")
    subprocess.Popen([str(helper), "--installer", str(installer), "--wait-pid", str(os.getpid()), "--restart", str(sys.executable)], close_fds=True)
