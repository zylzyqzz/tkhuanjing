from __future__ import annotations

from client_v2.models import CheckReport, CheckResult, Status
from client_v2.storage import baseline_delta
from client_v2.ui.theme import THEMES, apply_theme

from test_backend_api import admin_login, build_client


def test_home_has_no_fake_download_and_unknown_pages_are_branded(tmp_path):
    with build_client(tmp_path) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "开播前" in home.text and "/api/v1/client/update" not in home.text
        assert client.get("/download/latest").status_code == 503
        legacy = client.get("/download/", follow_redirects=False)
        assert legacy.status_code == 308 and legacy.headers["location"] == "/"
        missing = client.get("/definitely-not-a-page")
        assert missing.status_code == 404 and "返回主页" in missing.text


def test_candidate_release_activation_latest_download_and_stats(tmp_path):
    with build_client(tmp_path) as client:
        csrf = admin_login(client); headers = {"X-CSRF-Token": csrf}
        bad = client.post("/tk-api/release", headers=headers, data={"version":"2.5.0","title":"候选版","details":"完整说明","channel":"stable"}, files={"file":("bad.exe", b"not-an-exe", "application/octet-stream")})
        assert bad.status_code == 415
        installer = b"MZ" + b"v25-product-installer" * 300
        uploaded = client.post("/tk-api/release", headers=headers, data={"version":"2.5.0","title":"产品精修版","notes":"摘要","details":"完整更新说明","channel":"stable"}, files={"file":("setup.exe", installer, "application/octet-stream")})
        assert uploaded.status_code == 200 and uploaded.json()["status"] == "pending"
        assert client.get("/api/v1/client/update").json()["available"] is False
        assert client.post("/tk-api/release/activate", headers=headers, json={"version":"2.5.0"}).status_code == 200
        home = client.get("/")
        assert "/download/latest" in home.text and "V2.5.0" in home.text
        download = client.get("/download/latest")
        assert download.status_code == 200 and download.content == installer
        partial = client.get("/download/latest", headers={"Range":"bytes=0-9"})
        assert partial.status_code == 206 and len(partial.content) == 10
        stats = client.get("/tk-api/download-stats").json()["stats"]
        assert stats[0]["version"] == "2.5.0" and stats[0]["count"] == 2
        assert client.get("/api/v1/client/changelog").json()["releases"][0]["version"] == "2.5.0"


def test_homepage_content_is_admin_managed_and_protected(tmp_path):
    with build_client(tmp_path) as client:
        assert client.get("/tk-api/homepage").status_code == 401
        csrf = admin_login(client); headers = {"X-CSRF-Token": csrf}
        current = client.get("/tk-api/homepage").json()
        current["home_hero_title"] = "开播稳定，从检查开始"
        saved = client.post("/tk-api/homepage", headers=headers, json={"values": current})
        assert saved.status_code == 200
        assert "开播稳定，从检查开始" in client.get("/").text
        current.update({"product_name": "????????", "product_intro": "????????????", "product_faq": "????????\n????????"})
        assert client.post("/tk-api/homepage", headers=headers, json={"values": current}).status_code == 200
        repaired_home = client.get("/").text
        assert "维度 TikTok 直播开播助手" in repaired_home
        assert "为什么每天开播前都要检查" in repaired_home
        invalid = client.post("/tk-api/homepage", headers=headers, json={"values":{"unknown":"x"}})
        assert invalid.status_code == 422


def test_v5_readiness_priorities_baseline_and_themes():
    blocked = CheckReport("device", "2.5.0", [CheckResult("devices.camera", "设备", Status.FAIL, "摄像头")])
    blocked.finalize()
    assert blocked.readiness_level == "NOT_READY" and blocked.blocking_count == 1
    incomplete = CheckReport("device", "2.5.0", [CheckResult("network.throughput", "网络", Status.UNKNOWN, "稳定上传")])
    incomplete.finalize()
    assert incomplete.readiness_level == "INCOMPLETE"
    advisory = CheckReport("device", "2.5.0", [CheckResult("system.timezone", "系统", Status.WARNING, "时区")])
    advisory.finalize()
    assert advisory.readiness_level == "READY_WITH_RISK"
    payload = blocked.to_dict()
    assert payload["schema_version"] == 5 and payload["items"][0]["priority"] == "BLOCKING"
    delta = baseline_delta({"network_snapshot":{"network.throughput":{"upload_mbps":20}},"items":[]}, {"network_snapshot":{"network.throughput":{"upload_mbps":12}},"items":[]})
    assert delta["upload_mbps"]["change"] == 8
    assert set(THEMES) == {"obsidian", "cyber", "daylight"}
    assert "#EAF1F8" in apply_theme("daylight") and "#7A74FF" in apply_theme("cyber")
