from __future__ import annotations

import re
from typing import Any


# The knowledge base deliberately classifies network operators, not individual IP
# "purity".  An ASN owner can operate several products, so every conclusion remains
# advisory and records why it was reached.
ACCESS_KEYWORDS = (
    "telecom", "communications", "broadband", "fiber", "fibre", "cable",
    "wireless", "mobile", "unicom", "telefonica", "vodafone", "comcast",
    "spectrum", "verizon", "at&t", "t-mobile", "orange", "singtel",
    "starhub", "telstra", "optus", "china mobile", "china netcom",
)
HOSTING_KEYWORDS = (
    "hosting", "host", "cloud", "server", "datacenter", "data center", "vps",
    "colo", "digitalocean", "amazon", "google cloud", "microsoft azure",
    "alibaba cloud", "tencent cloud", "oracle", "ovh", "hetzner", "leaseweb",
)
PROXY_KEYWORDS = ("proxy", "vpn", "tunnel", "anonymous", "residential proxy")


def _normalized(*parts: Any) -> str:
    return " ".join(str(part or "").strip().lower() for part in parts)


def assess_provider(profile: dict[str, Any]) -> dict[str, Any]:
    """Return a short, evidence-based operator assessment.

    `reliable` here means suitable as an ordinary access-network identity, not a
    promise about TikTok account outcomes or the historical reputation of one IP.
    """
    connection_type = _normalized(profile.get("network_type"), profile.get("connection_type"))
    text = _normalized(profile.get("isp"), profile.get("org"), profile.get("asn_name"), connection_type)
    evidence: list[str] = []

    if any(word in text for word in PROXY_KEYWORDS):
        category, level, confidence = "proxy_or_vpn", "caution", "medium"
        summary = "识别到代理或 VPN 网络特征。可测速，但 IP 身份稳定性需要向线路商确认。"
        evidence.append("运营商或连接类型包含代理/VPN特征")
    elif connection_type in {"hosting", "datacenter", "data center"} or any(word in text for word in HOSTING_KEYWORDS):
        category, level, confidence = "hosting", "caution", "medium"
        summary = "更像云主机或机房网络。速度可能很好，但不等同于真实家庭宽带，只作为风险提示。"
        evidence.append("连接类型或运营商名称呈现托管/云网络特征")
    elif connection_type in {"cable/dsl", "cable", "dsl", "isp", "residential", "mobile"} or any(word in text for word in ACCESS_KEYWORDS):
        category, level, confidence = "access_network", "suitable", "medium"
        summary = "更像正规宽带或移动接入运营商，可作为直播线路使用；仍需结合实测上传和稳定性。"
        evidence.append("连接类型或运营商名称符合接入网络特征")
    else:
        category, level, confidence = "unclassified", "verify", "low"
        summary = "已识别运营商，但公开数据不足以判断网络类型。不会因此判定不能开播。"
        evidence.append("未命中接入、托管或代理分类规则")

    asn = str(profile.get("asn") or "").upper()
    if asn and not asn.startswith("AS") and re.fullmatch(r"\d+", asn):
        asn = f"AS{asn}"
    return {
        "provider": profile.get("isp") or profile.get("org") or "未识别服务商",
        "asn": asn or "未识别",
        "category": category,
        "level": level,
        "confidence": confidence,
        "summary": summary,
        "evidence": evidence,
        "disclaimer": "服务商分类是线路建议，不是账号风控或单个 IP 历史信誉保证。",
        "knowledge_version": 1,
    }
