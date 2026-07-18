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
    group: str


REGIONS: tuple[RegionProfile, ...] = (
    # 北美 — 14 个地区
    RegionProfile("us-los-angeles", "美国·洛杉矶 / US · Los Angeles", "US", "Pacific Standard Time", "America/Los_Angeles", "en-US", "north_america"),
    RegionProfile("us-new-york", "美国·纽约 / US · New York", "US", "Eastern Standard Time", "America/New_York", "en-US", "north_america"),
    RegionProfile("us-chicago", "美国·芝加哥 / US · Chicago", "US", "Central Standard Time", "America/Chicago", "en-US", "north_america"),
    RegionProfile("us-dallas", "美国·达拉斯 / US · Dallas", "US", "Central Standard Time", "America/Chicago", "en-US", "north_america"),
    RegionProfile("us-miami", "美国·迈阿密 / US · Miami", "US", "Eastern Standard Time", "America/New_York", "en-US", "north_america"),
    RegionProfile("us-seattle", "美国·西雅图 / US · Seattle", "US", "Pacific Standard Time", "America/Los_Angeles", "en-US", "north_america"),
    RegionProfile("us-san-francisco", "美国·旧金山 / US · San Francisco", "US", "Pacific Standard Time", "America/Los_Angeles", "en-US", "north_america"),
    RegionProfile("us-houston", "美国·休斯顿 / US · Houston", "US", "Central Standard Time", "America/Chicago", "en-US", "north_america"),
    RegionProfile("us-atlanta", "美国·亚特兰大 / US · Atlanta", "US", "Eastern Standard Time", "America/New_York", "en-US", "north_america"),
    RegionProfile("us-boston", "美国·波士顿 / US · Boston", "US", "Eastern Standard Time", "America/New_York", "en-US", "north_america"),
    RegionProfile("us-washington-dc", "美国·华盛顿 / US · Washington D.C.", "US", "Eastern Standard Time", "America/New_York", "en-US", "north_america"),
    RegionProfile("ca-toronto", "加拿大·多伦多 / Canada · Toronto", "CA", "Eastern Standard Time", "America/Toronto", "en-CA", "north_america"),
    RegionProfile("ca-vancouver", "加拿大·温哥华 / Canada · Vancouver", "CA", "Pacific Standard Time", "America/Vancouver", "en-CA", "north_america"),
    RegionProfile("ca-montreal", "加拿大·蒙特利尔 / Canada · Montreal", "CA", "Eastern Standard Time", "America/Toronto", "fr-CA", "north_america"),

    # 欧洲 — 18 个地区
    RegionProfile("gb-london", "英国·伦敦 / UK · London", "GB", "GMT Standard Time", "Europe/London", "en-GB", "europe"),
    RegionProfile("gb-manchester", "英国·曼彻斯特 / UK · Manchester", "GB", "GMT Standard Time", "Europe/London", "en-GB", "europe"),
    RegionProfile("de-frankfurt", "德国·法兰克福 / Germany · Frankfurt", "DE", "W. Europe Standard Time", "Europe/Berlin", "de-DE", "europe"),
    RegionProfile("de-berlin", "德国·柏林 / Germany · Berlin", "DE", "W. Europe Standard Time", "Europe/Berlin", "de-DE", "europe"),
    RegionProfile("fr-paris", "法国·巴黎 / France · Paris", "FR", "Romance Standard Time", "Europe/Paris", "fr-FR", "europe"),
    RegionProfile("es-madrid", "西班牙·马德里 / Spain · Madrid", "ES", "Romance Standard Time", "Europe/Madrid", "es-ES", "europe"),
    RegionProfile("it-milan", "意大利·米兰 / Italy · Milan", "IT", "W. Europe Standard Time", "Europe/Rome", "it-IT", "europe"),
    RegionProfile("nl-amsterdam", "荷兰·阿姆斯特丹 / Netherlands · Amsterdam", "NL", "W. Europe Standard Time", "Europe/Amsterdam", "nl-NL", "europe"),
    RegionProfile("pl-warsaw", "波兰·华沙 / Poland · Warsaw", "PL", "Central European Standard Time", "Europe/Warsaw", "pl-PL", "europe"),
    RegionProfile("se-stockholm", "瑞典·斯德哥尔摩 / Sweden · Stockholm", "SE", "W. Europe Standard Time", "Europe/Stockholm", "sv-SE", "europe"),
    RegionProfile("no-oslo", "挪威·奥斯陆 / Norway · Oslo", "NO", "W. Europe Standard Time", "Europe/Oslo", "nb-NO", "europe"),
    RegionProfile("dk-copenhagen", "丹麦·哥本哈根 / Denmark · Copenhagen", "DK", "Romance Standard Time", "Europe/Copenhagen", "da-DK", "europe"),
    RegionProfile("fi-helsinki", "芬兰·赫尔辛基 / Finland · Helsinki", "FI", "FLE Standard Time", "Europe/Helsinki", "fi-FI", "europe"),
    RegionProfile("pt-lisbon", "葡萄牙·里斯本 / Portugal · Lisbon", "PT", "GMT Standard Time", "Europe/Lisbon", "pt-PT", "europe"),
    RegionProfile("at-vienna", "奥地利·维也纳 / Austria · Vienna", "AT", "W. Europe Standard Time", "Europe/Vienna", "de-AT", "europe"),
    RegionProfile("ch-zurich", "瑞士·苏黎世 / Switzerland · Zurich", "CH", "W. Europe Standard Time", "Europe/Zurich", "de-CH", "europe"),
    RegionProfile("cz-prague", "捷克·布拉格 / Czech · Prague", "CZ", "Central European Standard Time", "Europe/Prague", "cs-CZ", "europe"),
    RegionProfile("ie-dublin", "爱尔兰·都柏林 / Ireland · Dublin", "IE", "GMT Standard Time", "Europe/Dublin", "en-IE", "europe"),

    # 东南亚 — 11 个地区
    RegionProfile("id-jakarta", "印度尼西亚·雅加达 / Indonesia · Jakarta", "ID", "SE Asia Standard Time", "Asia/Jakarta", "id-ID", "southeast_asia"),
    RegionProfile("id-surabaya", "印度尼西亚·泗水 / Indonesia · Surabaya", "ID", "SE Asia Standard Time", "Asia/Jakarta", "id-ID", "southeast_asia"),
    RegionProfile("th-bangkok", "泰国·曼谷 / Thailand · Bangkok", "TH", "SE Asia Standard Time", "Asia/Bangkok", "th-TH", "southeast_asia"),
    RegionProfile("vn-ho-chi-minh", "越南·胡志明市 / Vietnam · Ho Chi Minh City", "VN", "SE Asia Standard Time", "Asia/Ho_Chi_Minh", "vi-VN", "southeast_asia"),
    RegionProfile("vn-hanoi", "越南·河内 / Vietnam · Hanoi", "VN", "SE Asia Standard Time", "Asia/Ho_Chi_Minh", "vi-VN", "southeast_asia"),
    RegionProfile("ph-manila", "菲律宾·马尼拉 / Philippines · Manila", "PH", "Singapore Standard Time", "Asia/Manila", "en-PH", "southeast_asia"),
    RegionProfile("my-kuala-lumpur", "马来西亚·吉隆坡 / Malaysia · Kuala Lumpur", "MY", "Singapore Standard Time", "Asia/Kuala_Lumpur", "ms-MY", "southeast_asia"),
    RegionProfile("sg-singapore", "新加坡 / Singapore", "SG", "Singapore Standard Time", "Asia/Singapore", "en-SG", "southeast_asia"),
    RegionProfile("kh-phnom-penh", "柬埔寨·金边 / Cambodia · Phnom Penh", "KH", "SE Asia Standard Time", "Asia/Phnom_Penh", "km-KH", "southeast_asia"),
    RegionProfile("mm-yangon", "缅甸·仰光 / Myanmar · Yangon", "MM", "Myanmar Standard Time", "Asia/Yangon", "my-MM", "southeast_asia"),
    RegionProfile("la-vientiane", "老挝·万象 / Laos · Vientiane", "LA", "SE Asia Standard Time", "Asia/Vientiane", "lo-LA", "southeast_asia"),

    # 东亚 — 8 个地区
    RegionProfile("jp-tokyo", "日本·东京 / Japan · Tokyo", "JP", "Tokyo Standard Time", "Asia/Tokyo", "ja-JP", "east_asia"),
    RegionProfile("jp-osaka", "日本·大阪 / Japan · Osaka", "JP", "Tokyo Standard Time", "Asia/Tokyo", "ja-JP", "east_asia"),
    RegionProfile("kr-seoul", "韩国·首尔 / Korea · Seoul", "KR", "Korea Standard Time", "Asia/Seoul", "ko-KR", "east_asia"),
    RegionProfile("tw-taipei", "台湾·台北 / Taiwan · Taipei", "TW", "Taipei Standard Time", "Asia/Taipei", "zh-TW", "east_asia"),
    RegionProfile("hk-hong-kong", "香港 / Hong Kong", "HK", "China Standard Time", "Asia/Hong_Kong", "zh-HK", "east_asia"),
    RegionProfile("cn-shanghai", "中国·上海 / China · Shanghai", "CN", "China Standard Time", "Asia/Shanghai", "zh-CN", "east_asia"),
    RegionProfile("mo-macau", "澳门 / Macau", "MO", "China Standard Time", "Asia/Macau", "zh-MO", "east_asia"),
    RegionProfile("mn-ulaanbaatar", "蒙古·乌兰巴托 / Mongolia · Ulaanbaatar", "MN", "Ulaanbaatar Standard Time", "Asia/Ulaanbaatar", "mn-MN", "east_asia"),

    # 中东 — 7 个地区
    RegionProfile("ae-dubai", "阿联酋·迪拜 / UAE · Dubai", "AE", "Arabian Standard Time", "Asia/Dubai", "ar-AE", "middle_east"),
    RegionProfile("sa-riyadh", "沙特阿拉伯·利雅得 / Saudi Arabia · Riyadh", "SA", "Arab Standard Time", "Asia/Riyadh", "ar-SA", "middle_east"),
    RegionProfile("tr-istanbul", "土耳其·伊斯坦布尔 / Turkey · Istanbul", "TR", "Turkey Standard Time", "Europe/Istanbul", "tr-TR", "middle_east"),
    RegionProfile("il-tel-aviv", "以色列·特拉维夫 / Israel · Tel Aviv", "IL", "Israel Standard Time", "Asia/Jerusalem", "he-IL", "middle_east"),
    RegionProfile("qa-doha", "卡塔尔·多哈 / Qatar · Doha", "QA", "Arab Standard Time", "Asia/Qatar", "ar-QA", "middle_east"),
    RegionProfile("kw-kuwait-city", "科威特·科威特城 / Kuwait · Kuwait City", "KW", "Arab Standard Time", "Asia/Kuwait", "ar-KW", "middle_east"),
    RegionProfile("om-muscat", "阿曼·马斯喀特 / Oman · Muscat", "OM", "Arabian Standard Time", "Asia/Muscat", "ar-OM", "middle_east"),

    # 南美 — 9 个地区
    RegionProfile("br-sao-paulo", "巴西·圣保罗 / Brazil · Sao Paulo", "BR", "E. South America Standard Time", "America/Sao_Paulo", "pt-BR", "south_america"),
    RegionProfile("br-rio-de-janeiro", "巴西·里约热内卢 / Brazil · Rio de Janeiro", "BR", "E. South America Standard Time", "America/Sao_Paulo", "pt-BR", "south_america"),
    RegionProfile("mx-mexico-city", "墨西哥·墨西哥城 / Mexico · Mexico City", "MX", "Central Standard Time", "America/Mexico_City", "es-MX", "south_america"),
    RegionProfile("ar-buenos-aires", "阿根廷·布宜诺斯艾利斯 / Argentina · Buenos Aires", "AR", "Argentina Standard Time", "America/Argentina/Buenos_Aires", "es-AR", "south_america"),
    RegionProfile("co-bogota", "哥伦比亚·波哥大 / Colombia · Bogota", "CO", "SA Pacific Standard Time", "America/Bogota", "es-CO", "south_america"),
    RegionProfile("pe-lima", "秘鲁·利马 / Peru · Lima", "PE", "SA Pacific Standard Time", "America/Lima", "es-PE", "south_america"),
    RegionProfile("cl-santiago", "智利·圣地亚哥 / Chile · Santiago", "CL", "Pacific SA Standard Time", "America/Santiago", "es-CL", "south_america"),
    RegionProfile("ec-quito", "厄瓜多尔·基多 / Ecuador · Quito", "EC", "SA Pacific Standard Time", "America/Guayaquil", "es-EC", "south_america"),
    RegionProfile("uy-montevideo", "乌拉圭·蒙得维的亚 / Uruguay · Montevideo", "UY", "Montevideo Standard Time", "America/Montevideo", "es-UY", "south_america"),

    # 大洋洲 — 4 个地区
    RegionProfile("au-sydney", "澳大利亚·悉尼 / Australia · Sydney", "AU", "AUS Eastern Standard Time", "Australia/Sydney", "en-AU", "oceania"),
    RegionProfile("au-melbourne", "澳大利亚·墨尔本 / Australia · Melbourne", "AU", "AUS Eastern Standard Time", "Australia/Melbourne", "en-AU", "oceania"),
    RegionProfile("nz-auckland", "新西兰·奥克兰 / New Zealand · Auckland", "NZ", "New Zealand Standard Time", "Pacific/Auckland", "en-NZ", "oceania"),
    RegionProfile("fj-suva", "斐济·苏瓦 / Fiji · Suva", "FJ", "Fiji Standard Time", "Pacific/Fiji", "en-FJ", "oceania"),

    # 南亚 — 5 个地区
    RegionProfile("in-mumbai", "印度·孟买 / India · Mumbai", "IN", "India Standard Time", "Asia/Kolkata", "en-IN", "south_asia"),
    RegionProfile("in-new-delhi", "印度·新德里 / India · New Delhi", "IN", "India Standard Time", "Asia/Kolkata", "en-IN", "south_asia"),
    RegionProfile("pk-karachi", "巴基斯坦·卡拉奇 / Pakistan · Karachi", "PK", "Pakistan Standard Time", "Asia/Karachi", "ur-PK", "south_asia"),
    RegionProfile("bd-dhaka", "孟加拉国·达卡 / Bangladesh · Dhaka", "BD", "Bangladesh Standard Time", "Asia/Dhaka", "bn-BD", "south_asia"),
    RegionProfile("lk-colombo", "斯里兰卡·科伦坡 / Sri Lanka · Colombo", "LK", "Sri Lanka Standard Time", "Asia/Colombo", "si-LK", "south_asia"),

    # 非洲 — 5 个地区
    RegionProfile("za-johannesburg", "南非·约翰内斯堡 / South Africa · Johannesburg", "ZA", "South Africa Standard Time", "Africa/Johannesburg", "en-ZA", "africa"),
    RegionProfile("za-cape-town", "南非·开普敦 / South Africa · Cape Town", "ZA", "South Africa Standard Time", "Africa/Johannesburg", "en-ZA", "africa"),
    RegionProfile("ng-lagos", "尼日利亚·拉各斯 / Nigeria · Lagos", "NG", "W. Central Africa Standard Time", "Africa/Lagos", "en-NG", "africa"),
    RegionProfile("ke-nairobi", "肯尼亚·内罗毕 / Kenya · Nairobi", "KE", "E. Africa Standard Time", "Africa/Nairobi", "en-KE", "africa"),
    RegionProfile("eg-cairo", "埃及·开罗 / Egypt · Cairo", "EG", "Egypt Standard Time", "Africa/Cairo", "ar-EG", "africa"),

    # 中亚与高加索 — 3 个地区
    RegionProfile("kz-almaty", "哈萨克斯坦·阿拉木图 / Kazakhstan · Almaty", "KZ", "Central Asia Standard Time", "Asia/Almaty", "kk-KZ", "central_asia"),
    RegionProfile("uz-tashkent", "乌兹别克斯坦·塔什干 / Uzbekistan · Tashkent", "UZ", "West Asia Standard Time", "Asia/Tashkent", "uz-UZ", "central_asia"),
    RegionProfile("ge-tbilisi", "格鲁吉亚·第比利斯 / Georgia · Tbilisi", "GE", "Georgian Standard Time", "Asia/Tbilisi", "ka-GE", "central_asia"),
)

REGION_BY_ID = {region.region_id: region for region in REGIONS}

# 向后兼容映射：旧版 uk-london → gb-london
REGION_BY_ID["uk-london"] = REGION_BY_ID["gb-london"]


def get_region(region_id: str | None) -> RegionProfile:
    return REGION_BY_ID.get(region_id or "", REGIONS[0])
