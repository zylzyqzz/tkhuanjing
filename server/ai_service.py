from __future__ import annotations

from datetime import datetime, timezone
import json
import httpx

from .config import get_settings


def rule_fallback(summary: dict, provider: dict | None = None) -> dict:
    network = summary["network_summary"]
    advice = "当前线路表现稳定，可继续观察。" if network == "稳定" else "建议进行持续上传测试，并将报告提供给网络服务商核查。" if network != "待核实" else "数据不足，请稍后复测；待核实不代表网络不合格。"
    return {"customer_summary": summary["conclusion"], "network_advice": advice,
            "repair_guidance": summary["next_action"], "support_summary": "；".join(summary["issue_tags"]) or "当前无需跟进",
            "issue_tags": summary["issue_tags"], "model": "rule-template", "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_version": 1, "citations": ["readiness_level", "network_summary", "issue_tags"]}


def explain(summary: dict, provider: dict | None = None) -> dict:
    settings = get_settings()
    fallback = rule_fallback(summary, provider)
    if not settings.ai_enabled or not settings.ai_api_key or not settings.ai_base_url or not settings.ai_model:
        return fallback
    payload = {"summary": summary, "provider": provider or {}}
    try:
        response = httpx.post(settings.ai_base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai_api_key}"}, timeout=settings.ai_timeout_seconds,
            json={"model": settings.ai_model, "temperature": 0.1, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": "你是直播网络报告解释器。只解释输入指标，不改变开播判定。返回JSON字段customer_summary,network_advice,repair_guidance,support_summary,issue_tags,citations。"},
                               {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]})
        response.raise_for_status(); content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content); result.update({"model": settings.ai_model, "generated_at": datetime.now(timezone.utc).isoformat(), "input_version": 1})
        result["issue_tags"] = summary["issue_tags"]
        return result
    except Exception:
        return fallback
