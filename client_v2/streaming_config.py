from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from typing import Any


def discover_obs_profiles(appdata: Path | None = None) -> list[dict[str, Any]]:
    root = (appdata or Path(os.environ.get("APPDATA", Path.home()))) / "obs-studio" / "basic" / "profiles"
    profiles: list[dict[str, Any]] = []
    if not root.exists():
        return profiles
    for ini in root.glob("*/basic.ini"):
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(ini, encoding="utf-8-sig")
            output = parser["SimpleOutput"] if parser.has_section("SimpleOutput") else {}
            video = parser["Video"] if parser.has_section("Video") else {}
            bitrate = int(output.get("VBitrate", 0) or 0)
            profiles.append({
                "software": "OBS Studio", "profile": ini.parent.name, "bitrate_kbps": bitrate or None,
                "encoder": output.get("StreamEncoder", ""), "resolution": f"{video.get('OutputCX', '?')}×{video.get('OutputCY', '?')}",
                "fps": video.get("FPSCommon", ""), "source": str(ini),
            })
        except (OSError, ValueError, configparser.Error):
            continue
    return profiles


def discover_tiktok_profiles(localappdata: Path | None = None) -> list[dict[str, Any]]:
    base = localappdata or Path(os.environ.get("LOCALAPPDATA", Path.home()))
    roots = [base / "TikTok LIVE Studio", base / "TikTokLiveStudio"]
    profiles: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in list(root.rglob("*.json"))[:100]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw = json.dumps(data, ensure_ascii=False)
                candidates = []
                for key in ("bitrate", "videoBitrate", "video_bitrate"):
                    if isinstance(data, dict) and isinstance(data.get(key), (int, float)):
                        candidates.append(int(data[key]))
                if candidates:
                    profiles.append({"software": "TikTok LIVE Studio", "profile": path.stem, "bitrate_kbps": candidates[0], "source": str(path), "raw_size": len(raw)})
                    break
            except (OSError, ValueError, TypeError):
                continue
    return profiles


def discover_streaming_profiles() -> list[dict[str, Any]]:
    return discover_obs_profiles() + discover_tiktok_profiles()

