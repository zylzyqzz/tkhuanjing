from server.ai_service import rule_fallback
from server.models import CheckItem
from server.report_policy import authoritative_report


def item(check_id: str, status: str, *, blocking: bool = False) -> CheckItem:
    return CheckItem(check_id=check_id, category="测试", status=status, title=check_id, blocking=blocking)


def test_server_ignores_forged_blocking_and_keeps_network_advisory():
    forged = item("network.throughput", "FAIL", blocking=True)
    decision = authoritative_report([forged])
    assert forged.blocking is False
    assert decision["readiness_level"] == "READY_WITH_RISK"
    assert decision["network_summary"] == "建议联系服务商或更换线路"


def test_server_allows_only_whitelisted_failure_to_block():
    decision = authoritative_report([item("streaming.configuration_integrity", "FAIL")])
    assert decision["readiness_level"] == "NOT_READY"
    assert decision["blocking_count"] == 1


def test_ai_fallback_cannot_change_authoritative_decision():
    decision = authoritative_report([item("network.public_ip", "UNKNOWN")])
    result = rule_fallback(decision)
    assert result["model"] == "rule-template"
    assert result["issue_tags"] == decision["issue_tags"]
    assert "readiness_level" not in result
