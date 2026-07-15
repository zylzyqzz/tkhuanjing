from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegionProfile:
    region_id: str
    label: str
    country_code: str
    windows_timezone: str
    iana_timezone: str
    culture: str
    probes: tuple[str, ...]


REGIONS: tuple[RegionProfile, ...] = (
    RegionProfile("us-los-angeles", "美国·洛杉矶 / US · Los Angeles", "US", "Pacific Standard Time", "America/Los_Angeles", "en-US", ("us-west-2.console.aws.amazon.com", "ec2.us-west-2.amazonaws.com", "www.tiktok.com")),
    RegionProfile("us-new-york", "美国·纽约 / US · New York", "US", "Eastern Standard Time", "America/New_York", "en-US", ("us-east-1.console.aws.amazon.com", "ec2.us-east-1.amazonaws.com", "www.tiktok.com")),
    RegionProfile("ca-toronto", "加拿大·多伦多 / Canada · Toronto", "CA", "Eastern Standard Time", "America/Toronto", "en-CA", ("ca-central-1.console.aws.amazon.com", "ec2.ca-central-1.amazonaws.com", "www.tiktok.com")),
    RegionProfile("uk-london", "英国·伦敦 / UK · London", "GB", "GMT Standard Time", "Europe/London", "en-GB", ("eu-west-2.console.aws.amazon.com", "ec2.eu-west-2.amazonaws.com", "www.tiktok.com")),
    RegionProfile("de-frankfurt", "德国·法兰克福 / Germany · Frankfurt", "DE", "W. Europe Standard Time", "Europe/Berlin", "de-DE", ("eu-central-1.console.aws.amazon.com", "ec2.eu-central-1.amazonaws.com", "www.tiktok.com")),
    RegionProfile("fr-paris", "法国·巴黎 / France · Paris", "FR", "Romance Standard Time", "Europe/Paris", "fr-FR", ("eu-west-3.console.aws.amazon.com", "ec2.eu-west-3.amazonaws.com", "www.tiktok.com")),
    RegionProfile("jp-tokyo", "日本·东京 / Japan · Tokyo", "JP", "Tokyo Standard Time", "Asia/Tokyo", "ja-JP", ("ap-northeast-1.console.aws.amazon.com", "ec2.ap-northeast-1.amazonaws.com", "www.tiktok.com")),
    RegionProfile("kr-seoul", "韩国·首尔 / Korea · Seoul", "KR", "Korea Standard Time", "Asia/Seoul", "ko-KR", ("ap-northeast-2.console.aws.amazon.com", "ec2.ap-northeast-2.amazonaws.com", "www.tiktok.com")),
    RegionProfile("sg-singapore", "新加坡 / Singapore", "SG", "Singapore Standard Time", "Asia/Singapore", "en-SG", ("ap-southeast-1.console.aws.amazon.com", "ec2.ap-southeast-1.amazonaws.com", "www.tiktok.com")),
    RegionProfile("id-jakarta", "印度尼西亚·雅加达 / Indonesia · Jakarta", "ID", "SE Asia Standard Time", "Asia/Jakarta", "id-ID", ("ap-southeast-3.console.aws.amazon.com", "ec2.ap-southeast-3.amazonaws.com", "www.tiktok.com")),
    RegionProfile("th-bangkok", "泰国·曼谷 / Thailand · Bangkok", "TH", "SE Asia Standard Time", "Asia/Bangkok", "th-TH", ("ap-southeast-1.console.aws.amazon.com", "ec2.ap-southeast-1.amazonaws.com", "www.tiktok.com")),
    RegionProfile("au-sydney", "澳大利亚·悉尼 / Australia · Sydney", "AU", "AUS Eastern Standard Time", "Australia/Sydney", "en-AU", ("ap-southeast-2.console.aws.amazon.com", "ec2.ap-southeast-2.amazonaws.com", "www.tiktok.com")),
)

REGION_BY_ID = {region.region_id: region for region in REGIONS}


def get_region(region_id: str | None) -> RegionProfile:
    return REGION_BY_ID.get(region_id or "", REGIONS[0])
