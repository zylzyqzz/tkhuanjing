from __future__ import annotations

import json
import socket
import statistics
import time
from typing import Any, Callable

import httpx


PINGIP_STREAM = "https://pingip.cn/api/lookup/stream/me"
CLOUDFLARE_TRACE = "https://www.cloudflare.com/cdn-cgi/trace"
CLOUDFLARE_DOWN = "https://speed.cloudflare.com/__down"
CLOUDFLARE_UP = "https://speed.cloudflare.com/__up"


def parse_sse(text: str) -> dict[str, Any]:
    events: dict[str, Any] = {}
    name = "message"
    data_lines: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n") + [""]:
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif not line and data_lines:
            raw = "\n".join(data_lines)
            try:
                value: Any = json.loads(raw)
            except json.JSONDecodeError:
                value = raw
            events[name] = value
            name, data_lines = "message", []
    return events


def _flatten_pingip(events: dict[str, Any]) -> dict[str, Any]:
    info = events.get("ipinfo") or events.get("ip") or {}
    rdap = events.get("rdap") or {}
    clean = events.get("cleanliness") or {}
    suitability = events.get("suitability") or {}
    if isinstance(info, dict) and isinstance(info.get("data"), dict):
        info = info["data"]
    if isinstance(rdap, dict) and isinstance(rdap.get("data"), dict):
        rdap = rdap["data"]
    return {
        "ip": info.get("ip") or info.get("query") or "",
        "country_code": (info.get("country_code") or info.get("countryCode") or info.get("country") or "").upper(),
        "country": info.get("country_name") or info.get("country") or "",
        "region": info.get("region") or info.get("regionName") or "",
        "city": info.get("city") or "",
        "timezone": info.get("timezone") or "",
        "isp": info.get("isp") or info.get("org") or rdap.get("name") or "",
        "asn": info.get("asn") or rdap.get("handle") or "",
        "network_type": clean.get("network_type") if isinstance(clean, dict) else "",
        "cleanliness": clean,
        "suitability": suitability,
        "source": "PingIP",
        "confidence": "medium",
        "raw_events": events,
    }


def lookup_public_ip(client: httpx.Client | None = None) -> dict[str, Any]:
    own_client = client is None
    client = client or httpx.Client(timeout=12, follow_redirects=True)
    errors: list[str] = []
    try:
        try:
            response = client.get(PINGIP_STREAM, headers={"Accept": "text/event-stream"})
            response.raise_for_status()
            profile = _flatten_pingip(parse_sse(response.text))
            if profile.get("ip"):
                profile["provider_status"] = "ok"
                return profile
            errors.append("PingIP 未返回 IP")
        except Exception as exc:
            errors.append(f"PingIP: {exc}")

        trace: dict[str, str] = {}
        try:
            response = client.get(CLOUDFLARE_TRACE)
            response.raise_for_status()
            trace = dict(line.split("=", 1) for line in response.text.splitlines() if "=" in line)
        except Exception as exc:
            errors.append(f"Cloudflare: {exc}")
        ip = trace.get("ip", "")
        geo: dict[str, Any] = {}
        if ip:
            try:
                response = client.get(f"https://ipwho.is/{ip}")
                response.raise_for_status()
                geo = response.json()
            except Exception as exc:
                errors.append(f"GeoIP: {exc}")
        return {
            "ip": ip, "country_code": (geo.get("country_code") or trace.get("loc") or "").upper(),
            "country": geo.get("country", ""), "region": geo.get("region", ""), "city": geo.get("city", ""),
            "timezone": (geo.get("timezone") or {}).get("id", "") if isinstance(geo.get("timezone"), dict) else geo.get("timezone", ""),
            "isp": geo.get("connection", {}).get("isp", "") if isinstance(geo.get("connection"), dict) else "",
            "asn": geo.get("connection", {}).get("asn", "") if isinstance(geo.get("connection"), dict) else "",
            "network_type": "unknown", "cleanliness": {}, "suitability": {},
            "source": "Cloudflare + GeoIP fallback", "confidence": "low", "provider_status": "degraded",
            "errors": errors,
        }
    finally:
        if own_client:
            client.close()


def tls_probe(host: str, port: int = 443, timeout: float = 5.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = (time.perf_counter() - started) * 1000
            return {"host": host, "ok": True, "connect_ms": round(elapsed, 1)}
    except OSError as exc:
        return {"host": host, "ok": False, "connect_ms": None, "error": str(exc)}


def measure_throughput(client: httpx.Client | None = None, samples: int = 3, sample_bytes: int = 2_000_000, progress: Callable[[str, int, int, float | None], None] | None = None) -> dict[str, Any]:
    own_client = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True)
    down: list[float] = []
    up: list[float] = []
    errors: list[str] = []
    payload = b"0" * sample_bytes
    try:
        for index in range(samples):
            try:
                started = time.perf_counter()
                response = client.get(CLOUDFLARE_DOWN, params={"bytes": sample_bytes})
                response.raise_for_status()
                down.append(len(response.content) * 8 / max(time.perf_counter() - started, .001) / 1_000_000)
                if progress:
                    progress("download", index + 1, samples, down[-1])
            except Exception as exc:
                errors.append(f"download: {exc}")
                if progress:
                    progress("download", index + 1, samples, None)
            try:
                started = time.perf_counter()
                response = client.post(CLOUDFLARE_UP, content=payload)
                response.raise_for_status()
                up.append(len(payload) * 8 / max(time.perf_counter() - started, .001) / 1_000_000)
                if progress:
                    progress("upload", index + 1, samples, up[-1])
            except Exception as exc:
                errors.append(f"upload: {exc}")
                if progress:
                    progress("upload", index + 1, samples, None)
        return {
            "download_samples_mbps": [round(x, 2) for x in down],
            "upload_samples_mbps": [round(x, 2) for x in up],
            "download_mbps": round(statistics.median(down), 2) if down else None,
            "upload_mbps": round(min(up), 2) if up else None,
            "upload_variation_percent": round((max(up) - min(up)) / max(max(up), .001) * 100, 1) if len(up) > 1 else None,
            "source": "Cloudflare Speed",
            "errors": errors,
        }
    finally:
        if own_client:
            client.close()
