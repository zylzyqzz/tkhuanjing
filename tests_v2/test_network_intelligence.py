from client_v2.network_intelligence import lookup_public_ip, measure_throughput, parse_sse
from client_v2.streaming_config import discover_obs_profiles, discover_tiktok_profiles


class Response:
    def __init__(self, text="", content=b"", data=None, headers=None):
        self.text = text; self.content = content; self._data = data or {}; self.headers = headers or {}
    def raise_for_status(self): return None
    def json(self): return self._data


def test_parse_pingip_sse():
    events = parse_sse('event: ipinfo\ndata: {"ip":"1.2.3.4","country_code":"US"}\n\nevent: cleanliness\ndata: {"score":92}\n\n')
    assert events["ipinfo"]["ip"] == "1.2.3.4"
    assert events["cleanliness"]["score"] == 92


def test_lookup_uses_independent_sources_when_pingip_fails():
    class Client:
        def get(self, url, **_kwargs):
            if "trace" in url: return Response(text="ip=8.8.8.8\nloc=US")
            if "ipwho" in url: return Response(data={"success":True,"ip":"8.8.8.8","type":"IPv4","country_code":"US","country":"United States","latitude":1.0,"longitude":2.0,"connection":{"isp":"Example","org":"Example Org","asn":123}})
            if "rdap" in url: return Response(data={"cidr0_cidrs":[{"v4prefix":"8.8.8.0","length":24}],"port43":"whois.arin.net","name":"EXAMPLE"})
            if "pingip" in url: raise RuntimeError("offline")
            raise AssertionError(url)
    result = lookup_public_ip(Client())
    assert result["ip"] == "8.8.8.8" and result["provider_status"] == "ok"
    assert result["cidr"] == "8.8.8.0/24" and result["registry"] == "ARIN"
    assert result["residential_status"] == "unverified"


def test_speed_returns_raw_samples():
    class Client:
        def get(self, *_args, **_kwargs): return Response(content=b"x" * 1000)
        def post(self, *_args, **_kwargs): return Response()
    result = measure_throughput(Client(), samples=2, sample_bytes=1000)
    assert len(result["download_samples_mbps"]) == 2
    assert len(result["upload_samples_mbps"]) == 2


def test_streaming_profiles_are_read_from_real_files(tmp_path):
    obs = tmp_path / "obs-studio" / "basic" / "profiles" / "直播"
    obs.mkdir(parents=True)
    (obs / "basic.ini").write_text("[SimpleOutput]\nVBitrate=6500\nStreamEncoder=nvenc\n[Video]\nOutputCX=1920\nOutputCY=1080\nFPSCommon=30\n", encoding="utf-8")
    profiles = discover_obs_profiles(tmp_path)
    assert profiles[0]["bitrate_kbps"] == 6500
    assert profiles[0]["resolution"] == "1920×1080"

    tiktok = tmp_path / "TikTok LIVE Studio" / "config"
    tiktok.mkdir(parents=True)
    (tiktok / "live.json").write_text('{"videoBitrate": 4800}', encoding="utf-8")
    live = discover_tiktok_profiles(tmp_path)
    assert live[0]["bitrate_kbps"] == 4800
