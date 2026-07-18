from __future__ import annotations

import html

from .models import Release


DISCLAIMER = "本产品仅判断电脑、网络、设备和直播软件的技术准备情况，不代表平台账号审核、流量或开播权限结果。"
SITE_VERSION = "2.9.1"


def _lines(value: str, fallback: list[str]) -> list[str]:
    values = [line.strip() for line in (value or "").splitlines() if line.strip()]
    return values or fallback


def _safe_text(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    # Windows shell/code-page mistakes used to write Chinese fields as rows of question marks.
    # Never expose corrupted editable content on the public page.
    if not text or text.count("?") >= max(3, len(text) // 4):
        return fallback
    return text


CSS = """
:root{
    --bg:#050a13; --panel:#0a141f; --panel-2:#0d1926;
    --line:#152840; --line-soft:#0f1c2f;
    --text:#e6eef9; --muted:#7c8ea6; --dim:#556277;
    --blue:#4ea1ff; --cyan:#4cd0d6; --gold:#f2c77d; --green:#5be0a4;
    --radius-lg:18px; --radius:14px; --radius-sm:10px;
    --shadow:0 22px 60px -24px rgba(0,0,0,.75);
    --wrap:1180px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);
    font:16px/1.7 Inter,"PingFang SC","Microsoft YaHei UI",system-ui,sans-serif;
    -webkit-font-smoothing:antialiased;overflow-x:hidden}
.gridbg{position:fixed;inset:0;z-index:-1;opacity:.06;pointer-events:none;
    background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);
    background-size:56px 56px;mask-image:linear-gradient(#000,transparent 92%)}
body:after{content:'';position:fixed;inset:0;z-index:-1;pointer-events:none;
    background:radial-gradient(70% 45% at 78% 8%,rgba(78,161,255,.14),transparent 60%),
               radial-gradient(60% 40% at 12% 88%,rgba(242,199,125,.08),transparent 55%),
               linear-gradient(180deg,transparent,rgba(3,7,14,.9) 90%)}
a{color:inherit;text-decoration:none}
img{max-width:100%;display:block}

/* Nav */
nav{position:sticky;top:0;z-index:20;height:68px;display:flex;align-items:center;
    padding:0 32px;background:rgba(5,10,19,.72);
    backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
    border-bottom:1px solid var(--line-soft)}
nav .inner{width:100%;max-width:var(--wrap);margin:0 auto;
    display:flex;align-items:center;justify-content:space-between;gap:20px}
.brand{display:inline-flex;align-items:center;gap:12px;
    font-weight:800;font-size:17px;letter-spacing:.3px;color:var(--text)}
.brand img{width:38px;height:38px;object-fit:cover;border-radius:10px;
    box-shadow:0 8px 24px -6px rgba(242,199,125,.45)}
.nav-links{display:flex;align-items:center;gap:28px;color:var(--muted);font-size:14px}
.nav-links a{transition:color .2s}
.nav-links a:hover{color:var(--text)}

/* Buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;
    padding:12px 22px;border-radius:var(--radius-sm);
    font-weight:700;font-size:14px;letter-spacing:.3px;
    cursor:pointer;transition:transform .2s,box-shadow .2s,background .2s,border-color .2s;
    border:1px solid transparent;white-space:nowrap}
.btn-primary{color:#051224;background:linear-gradient(120deg,var(--blue),var(--cyan));
    box-shadow:0 10px 28px -10px rgba(78,161,255,.7)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 18px 40px -12px rgba(78,161,255,.85)}
.btn-primary.disabled{filter:grayscale(1) brightness(.7);pointer-events:none}
.btn-ghost{color:var(--text);border-color:var(--line);background:rgba(255,255,255,.02)}
.btn-ghost:hover{border-color:var(--blue);background:rgba(78,161,255,.06)}
.btn-lg{padding:15px 28px;font-size:15px}

/* Hero */
.hero{max-width:var(--wrap);margin:0 auto;padding:88px 32px 56px;
    display:grid;grid-template-columns:1.1fr .9fr;gap:64px;align-items:center}
.eyebrow{display:inline-flex;align-items:center;gap:8px;
    padding:6px 14px;border-radius:999px;
    border:1px solid rgba(78,161,255,.28);background:rgba(78,161,255,.06);
    color:var(--cyan);font-size:12px;font-weight:700;letter-spacing:1.2px}
.eyebrow .dot{width:6px;height:6px;border-radius:50%;background:var(--green);
    box-shadow:0 0 12px var(--green)}
h1{font-size:60px;line-height:1.08;letter-spacing:-1.5px;margin:22px 0 20px;font-weight:800}
h1 em{font-style:normal;background:linear-gradient(90deg,#fff 15%,var(--blue) 60%,var(--gold));
    -webkit-background-clip:text;background-clip:text;color:transparent}
.lead{font-size:17px;line-height:1.75;color:var(--muted);max-width:560px;margin:0 0 32px}
.cta-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.cta-hint{color:var(--dim);font-size:13px;margin-top:18px}

/* Hero visual */
.core{position:relative;aspect-ratio:1;min-height:380px;display:grid;place-items:center}
.orbit{position:absolute;border:1px dashed rgba(78,161,255,.22);border-radius:50%;
    animation:spin 24s linear infinite}
.o1{width:100%;height:100%}
.o2{width:74%;height:74%;animation-duration:18s;animation-direction:reverse;
    border-style:solid;border-color:rgba(76,208,214,.18)}
.o3{width:50%;height:50%;animation-duration:30s}
.orbit:before{content:'';position:absolute;width:8px;height:8px;border-radius:50%;
    background:var(--blue);top:-4px;left:50%;box-shadow:0 0 16px var(--blue)}
.chip{position:relative;width:42%;aspect-ratio:1;
    border:1px solid rgba(78,161,255,.35);border-radius:22px;
    display:grid;place-items:center;text-align:center;
    background:linear-gradient(150deg,rgba(20,38,63,.9),rgba(10,20,31,.9));
    box-shadow:inset 0 0 40px rgba(78,161,255,.14),0 20px 60px -20px rgba(0,0,0,.8);
    font-weight:800;font-size:15px;letter-spacing:.5px;line-height:1.5}
.chip small{display:block;color:var(--cyan);font-size:11px;
    letter-spacing:2px;margin-bottom:6px;font-weight:700}

/* Trust strip */
.trust{max-width:var(--wrap);margin:0 auto;padding:0 32px 12px}
.trust-inner{display:grid;grid-template-columns:repeat(4,1fr);
    border:1px solid var(--line-soft);border-radius:var(--radius);
    background:linear-gradient(180deg,var(--panel),var(--panel-2));overflow:hidden}
.trust-cell{padding:18px 22px;display:flex;align-items:center;gap:12px;
    border-right:1px solid var(--line-soft);font-size:13px;color:var(--muted)}
.trust-cell:last-child{border-right:0}
.trust-cell i{font-style:normal;font:800 11px/1 monospace;color:var(--blue);
    padding:5px 8px;border-radius:6px;background:rgba(78,161,255,.08)}
.trust-cell b{color:var(--text);font-weight:700}

/* Sections */
section.block{max-width:var(--wrap);margin:0 auto;padding:72px 32px}
.section-head{display:flex;align-items:flex-end;justify-content:space-between;
    gap:32px;margin-bottom:36px}
.section-head p{color:var(--muted);max-width:480px;margin:0}
h2{font-size:34px;line-height:1.2;letter-spacing:-.8px;margin:14px 0 0;font-weight:800}

/* Free access path */
.tiers{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}
.tier{padding:32px 30px;border:1px solid var(--line);
    background:linear-gradient(180deg,var(--panel),var(--panel-2));
    border-radius:var(--radius-lg);position:relative;
    transition:transform .25s,border-color .25s,box-shadow .25s}
.tier:hover{transform:translateY(-4px);border-color:rgba(78,161,255,.4);box-shadow:var(--shadow)}
.tier .tag{font:700 11px/1 monospace;letter-spacing:2px;color:var(--blue);text-transform:uppercase}
.tier .price{font:800 32px/1 Inter,sans-serif;color:var(--text);margin:14px 0 6px}
.tier .price small{font-size:14px;color:var(--muted);font-weight:500;margin-left:6px}
.tier .desc{color:var(--muted);margin:0 0 8px;font-size:14px}
.tier ul{list-style:none;padding:0;margin:16px 0 0}
.tier li{padding:6px 0 6px 22px;color:var(--text);font-size:14px;position:relative}
.tier li:before{content:'✓';position:absolute;left:0;top:6px;
    color:var(--green);font-weight:800;font-size:12px}
.tier.featured{border-color:rgba(242,199,125,.45);
    background:linear-gradient(180deg,rgba(242,199,125,.06),var(--panel-2));
    box-shadow:0 30px 80px -30px rgba(242,199,125,.25)}
.tier.featured .tag{color:var(--gold)}
.tier.featured .badge{position:absolute;top:-12px;right:22px;
    padding:5px 12px;font-size:11px;font-weight:800;letter-spacing:1.5px;
    color:#1a1408;background:var(--gold);border-radius:999px}

/* Dual mode */
.modes{display:grid;grid-template-columns:1fr 1fr;gap:22px}
.mode{padding:40px 36px;border:1px solid var(--line);background:var(--panel);
    border-radius:var(--radius-lg);position:relative;overflow:hidden;
    transition:transform .25s,border-color .25s;min-height:240px}
.mode:hover{transform:translateY(-3px);border-color:rgba(78,161,255,.4)}
.mode strong{font:700 12px/1 monospace;letter-spacing:2px;color:var(--blue)}
.mode.gold strong{color:var(--gold)}
.mode h3{font-size:26px;margin:14px 0 12px;letter-spacing:-.4px}
.mode p{color:var(--muted);margin:0;max-width:92%}
.mode:after{content:'';position:absolute;width:220px;height:220px;
    right:-60px;top:-80px;border-radius:50%;filter:blur(6px);
    background:radial-gradient(circle,rgba(78,161,255,.18),transparent 60%)}
.mode.gold:after{background:radial-gradient(circle,rgba(242,199,125,.18),transparent 60%)}

/* Capabilities grid */
.caps{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.cap{padding:26px 24px;border:1px solid var(--line);background:var(--panel);
    border-radius:var(--radius);transition:border-color .25s,transform .25s;min-height:160px}
.cap:hover{border-color:rgba(78,161,255,.4);transform:translateY(-2px)}
.cap span{display:block;font:800 26px/1 monospace;color:var(--line)}
.cap h3{font-size:16px;margin:16px 0 6px;letter-spacing:-.1px}
.cap p{color:var(--muted);margin:0;font-size:13px}

/* Flow */
.flow{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.flow li{padding:22px 20px;background:var(--panel);border:1px solid var(--line);
    border-top:2px solid var(--blue);border-radius:0 0 var(--radius) var(--radius)}
.flow b{display:block;font:800 12px/1 monospace;color:var(--gold);letter-spacing:2px;margin-bottom:10px}
.flow span{color:var(--text);font-size:14px;font-weight:600}

/* Sample report */
.report{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;
    padding:28px;border:1px solid var(--line);border-radius:var(--radius-lg);
    background:linear-gradient(180deg,var(--panel),var(--panel-2))}
.metric{padding:20px;border-radius:var(--radius);
    background:rgba(255,255,255,.015);border:1px solid var(--line-soft)}
.metric span{display:block;color:var(--muted);font-size:12px;letter-spacing:.5px}
.metric b{display:block;font-size:22px;margin-top:8px;font-weight:800}
.metric b.good{color:var(--green)}

/* Release card */
.release{display:flex;align-items:center;justify-content:space-between;
    gap:32px;padding:34px 36px;border:1px solid var(--line);
    background:linear-gradient(120deg,var(--panel),var(--panel-2));border-radius:var(--radius-lg)}
.release h3{font-size:32px;margin:6px 0 4px;letter-spacing:-.5px}
.release .meta{color:var(--muted);font-size:13px;line-height:1.7}

/* FAQ */
.faq{display:grid;gap:10px}
details{padding:20px 24px;border:1px solid var(--line);
    background:var(--panel);border-radius:var(--radius);transition:border-color .2s}
details[open]{border-color:rgba(78,161,255,.35)}
summary{cursor:pointer;font-weight:700;list-style:none;
    display:flex;align-items:center;justify-content:space-between;gap:20px}
summary::-webkit-details-marker{display:none}
summary:after{content:'+';color:var(--muted);font-size:22px;
    font-weight:400;transition:transform .25s;line-height:1}
details[open] summary:after{transform:rotate(45deg)}
details p{color:var(--muted);margin:12px 0 0}

/* Footer */
footer{max-width:var(--wrap);margin:40px auto 80px;padding:32px;
    border-top:1px solid var(--line);color:var(--muted);font-size:13px;line-height:1.8}
footer b{display:block;color:var(--text);margin-bottom:8px;font-weight:700;letter-spacing:.2px}
footer .foot-links{margin-top:16px;display:flex;gap:20px;flex-wrap:wrap}
footer .foot-links a{color:var(--dim)}
footer .foot-links a:hover{color:var(--blue)}

/* Sticky mobile CTA */
.sticky{display:none}

@keyframes spin{to{transform:rotate(360deg)}}

/* Responsive */
@media(max-width:960px){
    h1{font-size:44px}
    .hero{grid-template-columns:1fr;gap:40px;padding-top:60px}
    .core{min-height:320px;max-width:400px;margin:0 auto}
    .caps{grid-template-columns:repeat(2,1fr)}
    .modes,.tiers{grid-template-columns:1fr}
    .flow{grid-template-columns:1fr}
    .report{grid-template-columns:repeat(2,1fr)}
    .release{flex-direction:column;align-items:flex-start}
    .trust-inner{grid-template-columns:repeat(2,1fr)}
    .trust-cell:nth-child(2){border-right:0}
    .nav-links a:not(.btn){display:none}
}
@media(max-width:560px){
    h1{font-size:36px}
    section.block{padding:48px 24px}
    .hero{padding:48px 24px 40px}
    .modes,.caps,.tiers,.report{grid-template-columns:1fr}
    .trust-inner{grid-template-columns:1fr}
    .trust-cell{border-right:0;border-bottom:1px solid var(--line-soft)}
    .trust-cell:last-child{border-bottom:0}
    .sticky{display:block;position:fixed;left:16px;right:16px;bottom:16px;z-index:30}
    .sticky .btn{width:100%}
    nav .btn{padding:10px 16px;font-size:13px}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def render_home(settings: dict[str, str], release: Release | None) -> str:
    esc = html.escape
    name = _safe_text(settings.get("product_name"), "VD开播助手")
    title = _safe_text(settings.get("home_hero_title"), "开播前，先检查")
    subtitle = _safe_text(settings.get("home_hero_subtitle"), "让每一次 TikTok 电脑直播，从技术准备充分开始。")
    intro = _safe_text(settings.get("product_intro"), "面向 TikTok / 跨境电脑直播公司和工作室的开播前技术准备度检测工具。")

    default_features = [
        "IP 与目标地区", "网络质量与真实测速", "Windows 直播环境",
        "电脑性能与后台占用", "GPU 与硬件编码器",
        "直播设备与插件", "直播软件与客户端完整性",
    ]
    features = _lines(settings.get("product_features", ""), default_features)
    if len(features) != 7:
        features = default_features
    steps = _lines(settings.get("home_steps", ""),
                   ["发现真实问题", "判断问题来源", "安全处理或给出方案", "自动复检", "判断能否开播"])

    default_faq = (
        "为什么每天开播前都要检查？\n提前发现网络波动、设备占用、编码异常和系统配置变化。\n"
        "检测通过是否代表平台一定允许开播？\n不是，本工具只判断电脑、网络、设备和直播软件的技术准备情况。\n"
        "软件收费吗？\n完全免费。注册赠送 3 天使用权限，填写完整资料后自动获得永久免费使用权限。"
    )
    faq_raw = _safe_text(settings.get("product_faq"), default_faq)
    if any(word in faq_raw for word in ("付费", "续费", "套餐", "付款", "激活码")):
        faq_raw = default_faq
    faq = _lines(faq_raw, [])

    version = release.version if release else "尚未发布"
    size = f"{release.file_size / 1048576:.1f} MB" if release and release.file_size else "--"
    date = (release.created_at or "")[:10] if release else "--"
    dl_cls = "btn btn-primary" if release else "btn btn-primary disabled"
    dl_href = "/download/latest" if release else "#unavailable"

    feature_html = "".join(
        f"<article class='cap'><span>{i:02d}</span><h3>{esc(item)}</h3>"
        f"<p>真实采样 · 明确证据 · 可复检</p></article>"
        for i, item in enumerate(features[:7], 1)
    )
    step_html = "".join(
        f"<li><b>STEP {i:02d}</b><span>{esc(item)}</span></li>"
        for i, item in enumerate(steps[:5], 1)
    )
    faq_pairs = [
        (faq[i], faq[i + 1] if i + 1 < len(faq) else "软件会展示检测证据、影响与下一步处理建议。")
        for i in range(0, min(len(faq), 12), 2)
    ]
    faq_html = "".join(
        f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>"
        for q, a in faq_pairs
    )
    trust_cells = (
        ("01", "完全免费"),
        ("02", "真实网络采样"),
        ("03", "七组开播检查"),
        ("04", "不读取账号数据"),
    )
    trust_html = "".join(
        f"<div class='trust-cell'><i>{i}</i><b>{t}</b></div>" for i, t in trust_cells
    )

    tiers_html = """
<article class='tier featured'>
    <span class='badge'>第一步</span>
    <span class='tag'>REGISTER · 注册即用</span>
    <div class='price'>3<small> 天免费使用</small></div>
    <p class='desc'>使用手机号和邮箱完成注册，立即获得完整功能。</p>
    <ul>
        <li>完整 7 组开播检查</li>
        <li>一键配置环境</li>
        <li>历史报告同步与对比</li>
    </ul>
</article>
<article class='tier'>
    <span class='tag'>PERMANENT · 完善资料</span>
    <div class='price'>永久<small> · 自动生效</small></div>
    <p class='desc'>填写公司、国家、业务类型和微信号后自动获得。</p>
    <ul>
        <li>永久免费使用</li>
        <li>持续跟进版本更新</li>
        <li>无需付款或输入激活码</li>
    </ul>
</article>
"""

    return f"""<!doctype html><html lang='zh-CN'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{esc(name)}｜开播前技术准备度检测 · 完全免费</title>
<meta name='description' content='{esc(intro)} 注册赠送 3 天使用权限，填写完整资料后永久免费。'>
<style>{CSS}</style></head><body>
<div class='gridbg'></div>

<nav><div class='inner'>
    <a class='brand' href='/'><img src='/assets/logo.png' width='38' height='38' alt='VD Logo'>{esc(name)}</a>
    <div class='nav-links'>
        <a href='#tiers'>免费使用</a>
        <a href='#modes'>核心能力</a>
        <a href='#faq'>常见问题</a>
        <a class='{dl_cls}' href='{dl_href}'>下载 V{esc(version)}</a>
    </div>
</div></nav>

<main>
<section class='hero'>
    <div>
        <span class='eyebrow'><span class='dot'></span>V{SITE_VERSION} · 注册赠送 3 天 · 完善资料永久免费</span>
        <h1>{esc(title)}<br><em>技术准备好，再点开播</em></h1>
        <p class='lead'>{esc(subtitle)}<br>{esc(intro)}</p>
        <div class='cta-row'>
            <a class='{dl_cls} btn-lg' href='{dl_href}'>免费下载 V{esc(version)} →</a>
            <a class='btn btn-ghost btn-lg' href='#tiers'>了解免费使用规则</a>
        </div>
        <p class='cta-hint'>Windows 10 / 11 · 硬安装程序 · {esc(size)}</p>
    </div>
    <div class='core'>
        <div class='orbit o1'></div><div class='orbit o2'></div><div class='orbit o3'></div>
        <div class='chip'><small>PREFLIGHT CORE</small>直播环境<br>检测核心</div>
    </div>
</section>

<section class='trust'><div class='trust-inner'>{trust_html}</div></section>

<section class='block' id='tiers'>
    <div class='section-head'>
        <div><span class='eyebrow'>FREE ACCESS</span><h2>注册赠送 3 天 · 完善资料永久免费</h2></div>
        <p>不设置收费套餐、不展示付款二维码。填写完整资料后，永久免费权限自动生效。</p>
    </div>
    <div class='tiers'>{tiers_html}</div>
</section>

<section class='block' id='modes'>
    <div class='section-head'>
        <div><span class='eyebrow'>DUAL MODE</span><h2>两种模式，只解决开播前的实际问题</h2></div>
        <p>日常检查保持只读；环境配置需要确认后执行。产品不读取账号密码、Cookie 或个人文件。</p>
    </div>
    <div class='modes'>
        <article class='mode'><strong>DAILY PREFLIGHT</strong><h3>一键开播检查</h3>
            <p>{esc(settings.get('home_daily_text', '每天开播前跑一次，检出网络、编码、设备、系统的真实状况。'))}</p></article>
        <article class='mode gold'><strong>ENVIRONMENT SETUP</strong><h3>一键配置环境</h3>
            <p>{esc(settings.get('home_setup_text', '首次接入或换电脑后使用，一次性把 Windows 直播环境配到位。'))}</p></article>
    </div>
</section>

<section class='block'>
    <div class='section-head'>
        <div><span class='eyebrow'>REAL CHECKS</span><h2>七组真实检查，不靠一句笼统结论</h2></div>
        <p>每个异常都给出检测值、证据、问题定位、不处理的影响、解决步骤与复检入口。</p>
    </div>
    <div class='caps'>{feature_html}</div>
</section>

<section class='block'>
    <div class='section-head'>
        <div><span class='eyebrow'>CLOSED LOOP</span><h2>从发现问题，到确认能否开播</h2></div>
    </div>
    <ol class='flow'>{step_html}</ol>
</section>

<section class='block'>
    <div class='section-head'>
        <div><span class='eyebrow'>REPORT SAMPLE</span><h2>关键数据摆出来，再给结论</h2></div>
    </div>
    <div class='report'>
        <div class='metric'><span>稳定上传</span><b>真实采样</b></div>
        <div class='metric'><span>目标地区延迟</span><b>多节点</b></div>
        <div class='metric'><span>编码与设备</span><b>本机读取</b></div>
        <div class='metric'><span>技术准备度</span><b class='good'>明确分级</b></div>
    </div>
</section>

<section class='block'>
    <div class='release'>
        <div>
            <span class='eyebrow'>CURRENT RELEASE</span>
            <h3>V{esc(version)}</h3>
            <div class='meta'>安装包 {esc(size)} · 发布于 {esc(date)}<br>{esc(settings.get('home_system_requirements', 'Windows 10 / 11 · 4GB RAM 及以上'))}</div>
        </div>
        <a class='{dl_cls} btn-lg' href='{dl_href}'>免费下载安装程序 ↓</a>
    </div>
</section>

<section class='block' id='faq'>
    <div class='section-head'>
        <div><span class='eyebrow'>FAQ</span><h2>使用说明</h2></div>
    </div>
    <div class='faq'>{faq_html}</div>
</section>
</main>

<footer>
    <b>{esc(DISCLAIMER)}</b>
    {esc(settings.get('home_extra_notice', ''))}
    <div class='foot-links'>
        <a href='/'>主页</a>
        <a href='/tk-admin/'>管理后台</a>
        <a href='{dl_href}'>下载最新版</a>
    </div>
</footer>

<div class='sticky'><a class='{dl_cls}' href='{dl_href}'>免费下载 V{esc(version)}</a></div>

</body></html>"""


def unavailable_page() -> str:
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>暂不可下载</title>
<style>body{margin:0;display:grid;place-items:center;min-height:100vh;background:#050a13;color:#e6eef9;font-family:"Microsoft YaHei UI",sans-serif;text-align:center;padding:24px}
.box{padding:44px 40px;border:1px solid #152840;border-radius:18px;background:linear-gradient(180deg,#0a141f,#0d1926);max-width:520px}
h1{margin:0 0 12px;font-size:24px}p{color:#7c8ea6;line-height:1.7;margin:0}
a{color:#4ea1ff;display:inline-block;margin-top:22px;padding:10px 22px;border:1px solid #152840;border-radius:10px;text-decoration:none;font-weight:600;transition:border-color .2s}
a:hover{border-color:#4ea1ff}</style></head><body>
<div class='box'><h1>正式版本正在准备中</h1><p>当前没有可用的正式安装程序，请稍后重试或联系技术支持。</p><a href='/'>返回产品主页</a></div>
</body></html>"""
