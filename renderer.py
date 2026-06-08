"""
Newsletter Renderer & Sender — Botanical Editorial redesign
-----------------------------------------------------------
Reads curated_data.json -> generates newsletter.html -> sends via SMTP.

The email is a short, elegant "cover": Fern's note, today's opening feature,
and a contents list that links out to the full web edition. All browsable
content lives on the interactive edition (docs/index.html via webpage.py).

Required environment variables:
    EMAIL_USER / SMTP_USER  — sender address (also SMTP login)
    SMTP_PASS               — SMTP password / app password
    EMAIL_TO / NEWSLETTER_RECIPIENTS — comma-separated recipients
    SMTP_HOST / SMTP_SERVER — optional, default smtp.gmail.com
    SMTP_PORT               — optional, default 587
    EDITION_URL             — public URL of the full web edition
"""

import os
import json
import smtplib
import datetime
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------
BASE_DIR     = Path(__file__).parent
CURATED_FILE = BASE_DIR / "curated_data.json"
OUTPUT_HTML  = BASE_DIR / "newsletter.html"
DOCS_DIR     = BASE_DIR / "docs"

EDITION_URL  = os.environ.get(
    "EDITION_URL", "https://clairechabot.github.io/canopy-edition/"
)
FERN_LOGO_URL = os.environ.get("FERN_LOGO_URL", "")


# Running issue number, like a real periodical ("No. 248").
# Set this to the date of your VERY FIRST edition. Editions go out twice a day,
# so the number climbs by 2 each day on its own — no manual tracking needed.
CANOPY_LAUNCH = datetime.date(2025, 1, 1)


def _edition_no(dt: datetime.datetime, is_am: bool) -> int:
    days = (dt.date() - CANOPY_LAUNCH).days
    return max(1, days * 2 + (0 if is_am else 1) + 1)


def _yt_thumbnail(video_id: str) -> str:
    return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"


def _yt_embed(video_id: str) -> str:
    return f"https://www.youtube.com/embed/{video_id}"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )


def _safe_url(u: str) -> str:
    u = (u or "").strip()
    low = u.lower()
    if low.startswith(("http://", "https://", "mailto:")) or u.startswith(("/", "#")):
        return _esc(u)
    return "#"


def _clip(s: str, n: int = 96) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "\u2026"


def _dedash(s: str) -> str:
    """Remove em/en dashes from Fern's prose (reads less machine-made).
    Em dashes become commas; en dashes inside number ranges stay hyphens."""
    if not s:
        return s
    s = s.replace(" \u2014 ", ", ").replace(" \u2013 ", ", ")
    s = s.replace("\u2014", ", ").replace("\u2013", "-")
    while ", ," in s:
        s = s.replace(", ,", ",")
    return s.strip()


def _top_titles(items, n=2, key="title") -> str:
    out = [(_esc(it.get(key, "")) or "").strip() for it in items[:n]]
    return _clip(" \u00b7 ".join(t for t in out if t), 78)


# ---------------------------------------------------------------------------
# Styles  (Botanical Editorial)
# ---------------------------------------------------------------------------
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Hanken+Grotesk:wght@400;500;600;700&display=swap');
:root{
  --paper:#F4EEE2; --paper-deep:#E9E1D1; --surface:#FBF7EE;
  --ink:#20271F; --ink-soft:#4A4A3E; --ink-mute:#7C7565;
  --forest:#2C3A2B; --moss:#6E7B4B; --moss-deep:#55603A;
  --clay:#A85A36; --clay-deep:#8E4A2C;
  --line:#D9CFBC; --line-soft:#E5DCCB; --radius:12px;
  --serif:'Newsreader',Georgia,'Times New Roman',serif;
  --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{font-family:var(--sans);background:var(--paper-deep);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;}
.frame{max-width:600px;margin:0 auto;background:var(--paper);}
a{color:inherit;text-decoration:none;}
img{max-width:100%;display:block;}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:0.22em;text-transform:uppercase;color:var(--moss-deep);}

.masthead{text-align:center;padding:44px 32px 30px;}
.masthead .eyebrow{color:var(--clay-deep);margin-bottom:18px;}
.wordmark{font-family:var(--serif);font-weight:500;font-size:44px;line-height:1.02;letter-spacing:-0.01em;color:var(--forest);}
.tagline{font-family:var(--serif);font-style:italic;font-size:16px;color:var(--ink-soft);margin-top:12px;}
.meta-row{display:flex;align-items:center;justify-content:center;gap:14px;margin-top:26px;font-size:11.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--ink-mute);flex-wrap:wrap;}
.meta-row .dot{width:3px;height:3px;border-radius:50%;background:var(--clay);}

.note{padding:30px 32px 34px;border-top:1px solid var(--line-soft);border-bottom:1px solid var(--line-soft);background:var(--surface);display:flex;gap:18px;align-items:flex-start;}
.monogram{flex-shrink:0;width:46px;height:46px;border-radius:50%;border:1px solid var(--moss);color:var(--moss-deep);font-family:var(--serif);font-size:22px;display:flex;align-items:center;justify-content:center;margin-top:4px;}
.note .eyebrow{margin-bottom:8px;}
.note p{font-family:var(--serif);font-size:17.5px;line-height:1.62;color:var(--ink-soft);}
.note .sign{font-style:italic;color:var(--forest);}

.lead{padding:36px 32px 0;}
.lead .eyebrow{display:flex;align-items:center;gap:14px;color:var(--clay-deep);}
.lead .eyebrow::after{content:"";flex:1;height:1px;background:var(--line);}

.hero{padding:16px 32px 8px;display:block;}
.hero .kicker{font-size:11px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:var(--moss-deep);margin:18px 0 0;}
.hero h2{font-family:var(--serif);font-weight:500;font-size:27px;line-height:1.16;letter-spacing:-0.01em;color:var(--forest);margin-top:8px;}
.hero p{font-size:15px;color:var(--ink-soft);margin-top:8px;max-width:46ch;}

.img,.img-photo{position:relative;width:100%;overflow:hidden;border-radius:var(--radius);}
.img{background:linear-gradient(135deg,rgba(255,255,255,0.18),rgba(255,255,255,0) 60%),repeating-linear-gradient(135deg,rgba(32,39,31,0.035) 0 2px,transparent 2px 11px),linear-gradient(160deg,var(--ph-a,#C9CBB0),var(--ph-b,#9DA882));border:1px solid rgba(32,39,31,0.10);}
.img::after{content:attr(data-label);position:absolute;left:12px;bottom:11px;font-family:ui-monospace,Menlo,monospace;font-size:9.5px;letter-spacing:0.12em;text-transform:uppercase;color:rgba(255,255,255,0.9);background:rgba(32,39,31,0.34);padding:3px 8px;border-radius:100px;}
.img.deep{--ph-a:#7E8C6E;--ph-b:#46553E;}
.img-photo img{width:100%;height:100%;object-fit:cover;display:block;}
.img-photo{border:1px solid rgba(32,39,31,0.10);}
.play{position:absolute;inset:0;margin:auto;width:56px;height:56px;border-radius:50%;border:1.5px solid rgba(255,255,255,0.92);background:rgba(32,39,31,0.18);display:flex;align-items:center;justify-content:center;}
.play::after{content:"";margin-left:3px;border-style:solid;border-width:8px 0 8px 13px;border-color:transparent transparent transparent rgba(255,255,255,0.95);}

.contents{padding:36px 32px 8px;}
.contents .eyebrow{display:flex;align-items:center;gap:14px;color:var(--clay-deep);margin-bottom:4px;}
.contents .eyebrow::after{content:"";flex:1;height:1px;background:var(--line);}
.toc-row{display:flex;align-items:baseline;gap:16px;padding:18px 0;border-bottom:1px solid var(--line-soft);color:inherit;}
.toc-row:last-child{border-bottom:0;}
.toc-num{font-family:var(--serif);font-size:14px;color:var(--moss);width:24px;flex-shrink:0;}
.toc-body{flex:1;min-width:0;}
.toc-cat{font-family:var(--serif);font-size:19px;color:var(--forest);line-height:1.2;display:block;}
.toc-lead{font-size:13.5px;color:var(--ink-mute);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block;}
.toc-count{font-size:11px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--moss-deep);flex-shrink:0;white-space:nowrap;}

.cta-wrap{padding:34px 32px 8px;text-align:center;}
.cta{display:inline-block;font-size:14px;font-weight:600;letter-spacing:0.04em;color:#FBF7EE;background:var(--clay);padding:15px 34px;border-radius:100px;white-space:nowrap;}
.cta-sub{margin-top:14px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-mute);}

.footer{text-align:center;padding:40px 32px 46px;margin-top:30px;border-top:1px solid var(--line-soft);}
.footer .fmark{font-family:var(--serif);font-size:16px;color:var(--forest);}
.footer p{font-size:12px;color:var(--ink-mute);margin-top:12px;line-height:1.7;}
.footer a{color:var(--ink-soft);text-decoration:underline;text-underline-offset:2px;}

@media (max-width:460px){
  .masthead,.note,.hero,.contents,.cta-wrap,.footer,.lead{padding-left:22px;padding-right:22px;}
  .wordmark{font-size:36px;}.hero h2{font-size:23px;}
}
"""


# ---------------------------------------------------------------------------
# Render fragments
# ---------------------------------------------------------------------------
def _render_fern_note(greeting: str) -> str:
    greeting = _dedash(greeting).strip()
    if not greeting:
        greeting = ("Today's gathering is a quiet one. Pour something warm, "
                    "and take it at your own pace.")
    # Strip a trailing sign-off the curator may have added, then add our own.
    for tail in ("Fern", "\u2014 Fern", "- Fern", "Yours, Fern"):
        if greeting.endswith(tail):
            greeting = greeting[: -len(tail)].rstrip(" ,\u2014-").strip()
    return f"""
  <section class="note">
    <div class="monogram">F</div>
    <div>
      <div class="eyebrow">A note from Fern</div>
      <p>{_esc(greeting)} <span class="sign">Yours, Fern</span></p>
    </div>
  </section>"""


def _render_hero(video: dict) -> str:
    title   = _esc(video.get("title", ""))
    note    = _esc(_dedash(video.get("why_watch", video.get("description", ""))))
    channel = _esc(video.get("channel_title", ""))
    vid     = video.get("video_id", "")
    href    = _safe_url(EDITION_URL) if EDITION_URL else _yt_embed(vid)
    kicker  = "Watch" + (f" &nbsp;\u00b7&nbsp; {channel}" if channel else "")
    if vid:
        cover = (f'<div class="img-photo" style="aspect-ratio:3/2;">'
                 f'<img src="{_yt_thumbnail(vid)}" alt=""><span class="play"></span></div>')
    else:
        cover = ('<div class="img deep" data-label="Video still" '
                 'style="aspect-ratio:3/2;"><span class="play"></span></div>')
    return f"""
  <div class="lead"><div class="eyebrow">Today's opening</div></div>
  <a class="hero" href="{href}" target="_blank">
    {cover}
    <div class="kicker">{kicker}</div>
    <h2>{title}</h2>
    <p>{note}</p>
  </a>"""


def _toc_row(num: str, cat: str, lead: str, count: str, href: str) -> str:
    return f"""
    <a class="toc-row" href="{href}" target="_blank">
      <span class="toc-num">{num}</span>
      <span class="toc-body">
        <span class="toc-cat">{cat}</span>
        <span class="toc-lead">{lead}</span>
      </span>
      <span class="toc-count">{count}</span>
    </a>"""


def _render_contents(videos, music, good_news, discovery) -> str:
    href = _safe_url(EDITION_URL) if EDITION_URL else "#"
    specs = [
        ("The Morning Soundtrack", music,     _top_titles(music),     "Tracks"),
        ("Worth Watching",         videos,    _top_titles(videos),    "Films"),
        ("Global Silver Linings",  good_news, _top_titles(good_news), "Stories"),
        ("From the Archives",      discovery, _top_titles(discovery), "Finds"),
    ]
    rows, n = [], 0
    for cat, items, lead, unit in specs:
        if not items:
            continue
        n += 1
        rows.append(_toc_row(f"{n:02d}", cat, lead or "&nbsp;",
                             f"{len(items)} {unit}", href))
    if not rows:
        return ""
    return f"""
  <section class="contents">
    <div class="eyebrow">In this edition</div>
    {''.join(rows)}
  </section>"""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def build_html(curated: dict) -> str:
    themes    = curated.get("themes", [])
    music     = curated.get("morning_soundtrack", [])
    good_news = curated.get("global_silver_linings", [])
    discovery = curated.get("discovery_articles", [])
    fern      = curated.get("fern_data", {})
    is_am     = curated.get("is_am_email", False)
    fetched   = curated.get("fetched_at", "")

    videos = [v for t in themes for v in t.get("items", [])]

    edition_label = "Morning Edition" if is_am else "Evening Edition"
    gathered      = "Gathered at dawn" if is_am else "Gathered at dusk"
    try:
        dt = datetime.datetime.fromisoformat(fetched).astimezone(ZoneInfo("Europe/Zurich"))
        date_str = f"{dt.strftime('%a, %B')} {dt.day}"
        issue_html = f"No. {_edition_no(dt, is_am)} &nbsp;\u00b7&nbsp; "
    except Exception:
        date_str = fetched or ""
        issue_html = ""

    counts = []
    if music:     counts.append(f"{len(music)} tracks")
    if videos:    counts.append(f"{len(videos)} films")
    extra = len(good_news) + len(discovery)
    if extra:     counts.append(f"{extra} stories &amp; finds")
    meta_bits = [gathered] + counts
    meta_html = '<span class="dot"></span>'.join(f"<span>{b}</span>" for b in meta_bits)

    hero_html = _render_hero(videos[0]) if videos else ""
    fern_html = _render_fern_note(fern.get("greeting", ""))
    toc_html  = _render_contents(videos, music, good_news, discovery)

    logo_html = (
        f'<img src="{_safe_url(FERN_LOGO_URL)}" alt="" '
        f'style="max-width:96px;height:auto;margin:0 auto 18px;">'
        if FERN_LOGO_URL else ""
    )
    cta_html = (
        f'<div class="cta-wrap"><a class="cta" href="{_safe_url(EDITION_URL)}" '
        f'target="_blank">Open the full edition</a>'
        f'<div class="cta-sub">Covers, films &amp; the complete collection</div></div>'
        if EDITION_URL else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Curated Canopy</title>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<div class="frame">
  <header class="masthead">
    {logo_html}
    <div class="eyebrow">{edition_label} &nbsp;\u00b7&nbsp; {issue_html}{date_str}</div>
    <div class="wordmark">The Curated&nbsp;Canopy</div>
    <div class="tagline">Human stories, good news &amp; the natural world</div>
    <div class="meta-row">{meta_html}</div>
  </header>
  {fern_html}
  {hero_html}
  {toc_html}
  {cta_html}
  <footer class="footer">
    <div class="fmark">The Curated Canopy</div>
    <p>
      Curated twice daily by Fern.<br>
      You're receiving this because you asked for a quieter inbox.<br>
      <a href="#">Preferences</a> &nbsp;\u00b7&nbsp; <a href="#">Unsubscribe</a>
    </p>
  </footer>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# SMTP sender  (unchanged behaviour)
# ---------------------------------------------------------------------------
def send_email(html_body: str, subject: str) -> None:
    smtp_user = os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_host = os.environ.get("SMTP_SERVER") or os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))

    if not smtp_host:
        raise SystemExit("ERROR: SMTP_SERVER/SMTP_HOST is empty. Check secrets!")
    if not smtp_user:
        raise SystemExit("ERROR: SMTP_USER/EMAIL_USER is empty. Check secrets!")
    if not smtp_pass:
        raise SystemExit("ERROR: SMTP_PASS is empty. Check secrets!")

    raw_to = (
        os.environ.get("EMAIL_TO")
        or os.environ.get("NEWSLETTER_RECIPIENTS")
        or os.environ.get("RECIPIENTS")
        or smtp_user
    )
    recipients = [r.strip() for r in raw_to.split(",") if r.strip()]
    if not recipients:
        raise SystemExit("ERROR: No recipient. Set EMAIL_TO.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = formataddr(("Fern | The Curated Canopy", smtp_user))
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"[SMTP] Connecting to {smtp_host}:{smtp_port} \u2026")
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipients, msg.as_bytes())
    print(f"[SMTP] Sent to {len(recipients)} recipient(s).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not CURATED_FILE.exists():
        raise FileNotFoundError(f"{CURATED_FILE} not found. Run fetcher.py first.")

    curated = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
    html    = build_html(curated)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"[render] HTML written -> {OUTPUT_HTML}")

    try:
        import webpage
        path = webpage.write_edition(curated)
        print(f"[render] Full edition written -> {path}")
    except Exception as exc:
        print(f"[render] WARN — could not build full edition page: {exc}")

    smtp_ready = (
        (os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER"))
        and os.environ.get("SMTP_PASS")
        and (os.environ.get("SMTP_SERVER") or os.environ.get("SMTP_HOST"))
    )
    if smtp_ready:
        is_am    = curated.get("is_am_email", False)
        fern     = curated.get("fern_data", {})
        top_pick = _dedash(fern.get("top_pick_title", "")).strip()
        prefix   = "The Morning Rise" if is_am else "The Evening Wind-down"
        subject  = f"{prefix} | {top_pick}" if top_pick else f"{prefix} \u00b7 The Curated Canopy"
        send_email(html, subject=subject)
        return

    msg = "[render] EMAIL NOT SENT — missing SMTP secrets."
    if os.environ.get("ALLOW_NO_EMAIL") == "1":
        print(msg + " (ALLOW_NO_EMAIL=1 — preview only)")
    else:
        raise SystemExit(msg)


if __name__ == "__main__":
    main()
