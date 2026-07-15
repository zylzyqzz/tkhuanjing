from __future__ import annotations

import ipaddress
import json
import socket
import statistics
import time
from typing import Any, Callable

import httpx


# PingIP is retained only as an optional compatibility source. Its public endpoint
# can present a browser challenge, so the client never depends on it for a result.
PINGIP_STREAM = "https://pingip.cn/api/lookup/stream/me"
CLOUDFLARE_TRACE = "https://www.cloudflare.com/cdn-cgi/trace"
IPWHO = "https://ipwho.is/"
RDAP_BOOTSTRAP = "https://rdap-bootstrap.arin.net/bootstrap/ip/{ip}"
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
        "ip_version": info.get("type") or "",
        "country_code": (info.get("country_code") or info.get("countryCode") or info.get("country") or "").upper(),
        "country": info.get("country_name") or info.get("country") or "",
        "region": info.get("region") or info.get("regionName") or "",
        "city": info.get("city") or "",
        "latitude": info.get("latitude") or info.get("lat"),
        "longitude": info.get("longitude") or info.get("lon"),
        "timezone": info.get("timezone") or "",
        "isp": info.get("isp") or info.get("org") or rdap.get("name") or "",
        "organization": info.get("org") or "",
        "asn": info.get("asn") or rdap.get("handle") or "",
        "cidr": info.get("network") or rdap.get("cidr") or "",
        "network_type": clean.get("network_type") if isinstance(clean, dict) else "",
        "cleanliness": clean if isinstance(clean, dict) else {},
        "suitability": suitability if isinstance(suitability, dict) else {},
        "source": "PingIP",
        "confidence": "medium",
        "raw_events": events,
    }


def _registry_from_port43(port43: str) -> str:
    value = (port43 or "").lower()
    for token, name in (("arin", "ARIN"), ("apnic", "APNIC"), ("ripe", "RIPE NCC"), ("lacnic", "LACNIC"), ("afrinic", "AFRINIC")):
        if token in value:
            return name
    return ""


def _rdap_profile(payload: dict[str, Any]) -> dict[str, Any]:
    cidrs = payload.get("cidr0_cidrs") or []
    cidr = ""
    if cidrs:
        first = cidrs[0]
        prefix = first.get("v4prefix") or first.get("v6prefix")
        if prefix and first.get("length") is not None:
            cidr = f"{prefix}/{first['length']}"
    country = payload.get("country") or ""
    return {
        "cidr": cidr,
        "network_name": payload.get("name") or payload.get("handle") or "",
        "registered_country": country,
        "registry": _registry_from_port43(payload.get("port43", "")),
        "registration_start": payload.get("startAddress") or "",
        "registration_end": payload.get("endAddress") or "",
    }


def lookup_public_ip(client: httpx.Client | None = None) -> dict[str, Any]:
    """Build a source-labelled public IP profile without claiming IP purity.

    Cloudflare provides the observed public IP, IPWho provides geolocation and
    ASN metadata, and RDAP provides registration/CIDR. Any unavailable field is
    left empty instead of being inferred as residential, native or low-risk.
    """
    own_client = client is None
    client = client or httpx.Client(timeout=12, follow_redirects=True)
    errors: list[str] = []
    trace: dict[str, str] = {}
    geo: dict[str, Any] = {}
    rdap: dict[str, Any] = {}
    pingip: dict[str, Any] = {}
    try:
        try:
            response = client.get(CLOUDFLARE_TRACE)
            response.raise_for_status()
            trace = dict(line.split("=", 1) for line in response.text.splitlines() if "=" in line)
        except Exception as exc:
            errors.append(f"Cloudflare Trace: {exc}")

        ip = trace.get("ip", "")
        try:
            response = client.get(IPWHO if not ip else f"https://ipwho.is/{ip}")
            response.raise_for_status()
            candidate = response.json()
            if candidate.get("success", True):
                geo = candidate
                ip = ip or str(candidate.get("ip") or "")
            else:
                errors.append(f"IPWho: {candidate.get('message', 'no result')}")
        except Exception as exc:
            errors.append(f"IPWho: {exc}")

        if ip:
            try:
                response = client.get(RDAP_BOOTSTRAP.format(ip=ip))
                response.raise_for_status()
                rdap = _rdap_profile(response.json())
            except Exception as exc:
                errors.append(f"RDAP: {exc}")

        # Optional enrichment only. A Cloudflare challenge or schema change is
        # treated as a source failure and never as a customer network failure.
        try:
            response = client.get(PINGIP_STREAM, headers={"Accept": "text/event-stream"})
            response.raise_for_status()
            if "text/event-stream" in response.headers.get("content-type", ""):
                pingip = _flatten_pingip(parse_sse(response.text))
        except Exception as exc:
            errors.append(f"PingIP optional: {exc}")

        connection = geo.get("connection") if isinstance(geo.get("connection"), dict) else {}
        timezone = geo.get("timezone") if isinstance(geo.get("timezone"), dict) else {}
        protocol = geo.get("type") or (f"IPv{ipaddress.ip_address(ip).version}" if ip else "")
        clean = pingip.get("cleanliness") if isinstance(pingip.get("cleanliness"), dict) else {}
        suitability = pingip.get("suitability") if isinstance(pingip.get("suitability"), dict) else {}
        sources = [name for name, ok in (("Cloudflare Trace", bool(trace)), ("IPWho", bool(geo)), ("RDAP", bool(rdap)), ("PingIP", bool(pingip))) if ok]
        profile = {
            "ip": ip,
            "ip_version": protocol,
            "country_code": (geo.get("country_code") or trace.get("loc") or pingip.get("country_code") or "").upper(),
            "country": geo.get("country") or pingip.get("country") or "",
            "region": geo.get("region") or pingip.get("region") or "",
            "city": geo.get("city") or pingip.get("city") or "",
            "latitude": geo.get("latitude") if geo.get("latitude") is not None else pingip.get("latitude"),
            "longitude": geo.get("longitude") if geo.get("longitude") is not None else pingip.get("longitude"),
            "timezone": timezone.get("id") or pingip.get("timezone") or "",
            "timezone_utc": timezone.get("utc") or "",
            "isp": connection.get("isp") or pingip.get("isp") or "",
            "organization": connection.get("org") or pingip.get("organization") or "",
            "domain": connection.get("domain") or "",
            "asn": connection.get("asn") or pingip.get("asn") or "",
            "cidr": rdap.get("cidr") or pingip.get("cidr") or "",
            "network_name": rdap.get("network_name") or "",
            "registered_country": rdap.get("registered_country") or "",
            "registry": rdap.get("registry") or "",
            "registration_start": rdap.get("registration_start") or "",
            "registration_end": rdap.get("registration_end") or "",
            "network_type": pingip.get("network_type") or "unknown",
            "cleanliness": clean,
            "suitability": suitability,
            "risk_label": clean.get("risk_label") or clean.get("risk") or "unverified",
            "residential_status": clean.get("residential") if "residential" in clean else "unverified",
            "native_status": clean.get("native") if "native" in clean else "unverified",
            "source": " + ".join(sources) or "No source",
            "sources": sources,
            "confidence": "high" if bool(geo and rdap) else "medium" if bool(geo) else "low",
            "provider_status": "ok" if ip and geo else "degraded",
            "errors": errors,
        }
        return profile
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
