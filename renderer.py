"""
Newsletter Renderer & Sender — "Forest & Brass · Belle Époque" email
--------------------------------------------------------------------
Reads curated_data.json -> generates newsletter.html -> sends via SMTP.

The email is a short, elegant "cover": a gilt-framed forest masthead, Fern's
note (with a drop cap), today's opening feature, and a contents list that links
out to the full web edition. All browsable content lives on the interactive
edition (docs/index.html via webpage.py).

Gmail-safe: table layout, fully inline styles, hardcoded hex colors (no var()),
no SVG/flexbox/grid/::before, explicit image dimensions, and Georgia/Helvetica
fallbacks for the (progressively-enhanced) Cormorant/Newsreader/Hanken fonts.

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
from email.utils import formataddr, getaddresses
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

# Where Fern's garden lives — shown in the "From the Garden" eyebrow and used by
# curator.py to ground the seasonal note + night sky. Override with GARDEN_LOCALE.
GARDEN_LOCALE = os.environ.get("GARDEN_LOCALE", "Zürich")
# Edition timezone (env-overridable for regional editions; default = primary).
EDITION_TZ = ZoneInfo(os.environ.get("EDITION_TZ", "Europe/Zurich"))


# Running issue number, like a real periodical ("No. 248").
# Set this to the date of your VERY FIRST edition. Editions go out twice a day,
# so the number climbs by 2 each day on its own — no manual tracking needed.
CANOPY_LAUNCH = datetime.date(2026, 6, 10)  # first edition; No. 1 = 2026-06-10 morning


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
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _dedash(s: str) -> str:
    """Remove em/en dashes from Fern's prose (reads less machine-made).
    Em dashes become commas; en dashes inside number ranges stay hyphens."""
    if not s:
        return s
    s = s.replace(" — ", ", ").replace(" – ", ", ")
    s = s.replace("—", ", ").replace("–", "-")
    while ", ," in s:
        s = s.replace(", ,", ",")
    return s.strip()


def _top_titles(items, n=2, key="title") -> str:
    out = [(_esc(it.get(key, "")) or "").strip() for it in items[:n]]
    return _clip(" · ".join(t for t in out if t), 78)


# ---------------------------------------------------------------------------
# Email-safe rendering — Forest & Brass palette + type stacks
# ---------------------------------------------------------------------------
DISPLAY = "'Cormorant Garamond',Georgia,'Times New Roman',serif"   # headings, wordmark, numerals
SERIF   = "'Newsreader',Georgia,'Times New Roman',serif"           # running text
SANS    = "'Hanken Grotesk',Helvetica,Arial,sans-serif"            # small UI labels

# Palette (hardcoded — Gmail strips var()).
PAPER      = "#EFE7D6"
PAPER_DEEP = "#E5DCC4"
SURFACE    = "#FCF7EB"
INK        = "#1B2716"
INK_SOFT   = "#3C4433"
INK_MUTE   = "#79735C"
FOREST     = "#1E2E1A"
BRASS      = "#C09433"
BRASS_DEEP = "#A87E28"
BRASS_SOFT = "#D9B968"
CLAY       = "#B6541F"
CLAY_DEEP  = "#984417"
LINE       = "#DCD0B4"
CREAM      = "#F2EAD6"
CREAM_MUTE = "#C6C3A6"

_DIAMOND = "&#9670;"  # ◆ — typographic ornament (no emoji, no image)

_HEAD = f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<title>The Curated Canopy</title>
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
<![endif]-->
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; width:100% !important; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table {{ border-collapse:collapse; }}
  img {{ border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; }}
  a {{ color:{CLAY_DEEP}; }}
  .hover-cta:hover {{ background:{CLAY_DEEP} !important; }}
  @media only screen and (max-width:600px) {{
    .container {{ width:100% !important; }}
    .px {{ padding-left:22px !important; padding-right:22px !important; }}
    .wordmark {{ font-size:44px !important; }}
    .hero-h {{ font-size:25px !important; }}
  }}
</style>
</head>"""


def _flourish(color: str = BRASS) -> str:
    """Typographic whiplash substitute: gold rule — diamond — gold rule."""
    rule = (f'<td width="62" style="width:62px;"><div style="height:1px;'
            f'background-color:{color};font-size:0;line-height:0;">&nbsp;</div></td>')
    return (
        '<table role="presentation" align="center" cellpadding="0" cellspacing="0" '
        'style="margin:0 auto;"><tr>'
        f'{rule}'
        f'<td style="padding:0 11px;font-family:Georgia,serif;font-size:12px;'
        f'color:{color};line-height:1;">{_DIAMOND}</td>'
        f'{rule}'
        '</tr></table>'
    )


def _eyebrow(text: str, color: str) -> str:
    """Diamond-flanked label text (inline)."""
    d = f'<span style="font-family:Georgia,serif;color:{color};">{_DIAMOND}</span>'
    return f'{d}&nbsp;&nbsp;{text}&nbsp;&nbsp;{d}'


def _render_fern_note(greeting: str) -> str:
    greeting = _dedash(greeting).strip()
    if not greeting:
        greeting = ("Today's gathering is a quiet one. Pour something warm, "
                    "and take it at your own pace.")
    for tail in ("Fern", "— Fern", "- Fern", "Yours, Fern"):
        if greeting.endswith(tail):
            greeting = greeting[: -len(tail)].rstrip(" ,—-").strip()
    cap, rest = (greeting[:1] or "T"), greeting[1:]
    return f"""
        <tr>
          <td class="px" style="padding:30px 32px 32px 32px; background-color:{SURFACE}; border-top:1px solid {LINE}; border-bottom:1px solid {LINE};">
            <div style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:3px; text-transform:uppercase; color:{BRASS_DEEP}; padding-bottom:14px;">{_eyebrow("A note from Fern", BRASS_DEEP)}</div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td valign="top" width="50" style="width:50px; font-family:{DISPLAY}; font-weight:600; font-size:56px; line-height:0.74; color:{BRASS_DEEP};">{_esc(cap)}</td>
                <td valign="top" style="font-family:{SERIF}; font-size:17.5px; line-height:1.62; color:{INK_SOFT};">
                  {_esc(rest)} <span style="font-family:{DISPLAY}; font-style:italic; font-size:21px; color:{FOREST};">Yours, Fern</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""


def _render_hero(video: dict) -> str:
    title   = _esc(video.get("title", ""))
    note    = _esc(_dedash(video.get("why_watch", video.get("description", ""))))
    channel = _esc(video.get("channel_title", ""))
    vid     = video.get("video_id", "")
    href    = _safe_url(EDITION_URL) if EDITION_URL else _yt_embed(vid)
    kicker  = "Watch" + (f" &nbsp;&middot;&nbsp; {channel}" if channel else "")
    if vid:
        media = (f'<img src="{_safe_url(_yt_thumbnail(vid))}" alt="" width="536" '
                 f'style="display:block; width:100%; max-width:536px; height:auto;">')
    else:
        media = (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td align="center" valign="middle" height="300" bgcolor="{FOREST}" style="height:300px; background-color:{FOREST};">'
            f'<table role="presentation" cellpadding="0" cellspacing="0" width="60" height="60" style="width:60px; height:60px; border:2px solid {CREAM}; border-radius:50%;">'
            f'<tr><td align="center" valign="middle" style="height:60px; font-family:Georgia,serif; font-size:20px; color:{CREAM}; padding-left:5px;">&#9658;</td></tr>'
            '</table></td></tr></table>'
        )
    return f"""
        <tr>
          <td class="px" style="padding:34px 32px 0 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
              <td style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:3px; text-transform:uppercase; color:{BRASS_DEEP}; white-space:nowrap;">Today's opening</td>
              <td width="100%" style="padding-left:14px;"><div style="height:1px; background-color:{BRASS}; font-size:0; line-height:0;">&nbsp;</div></td>
            </tr></table>
          </td>
        </tr>
        <tr>
          <td class="px" style="padding:16px 32px 6px 32px;">
            <a href="{href}" style="text-decoration:none; color:{FOREST};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="border:1px solid {BRASS};">{media}</td></tr></table>
              <div style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:1.8px; text-transform:uppercase; color:{BRASS_DEEP}; padding-top:18px;">{kicker}</div>
              <div class="hero-h" style="font-family:{DISPLAY}; font-weight:600; font-size:30px; line-height:1.12; color:{FOREST}; padding-top:7px;">{title}</div>
              <div style="font-family:{SERIF}; font-size:15.5px; line-height:1.55; color:{INK_SOFT}; padding-top:9px;">{note}</div>
            </a>
          </td>
        </tr>"""


ON_THIS_DAY_URL = "https://www.britannica.com/on-this-day"


def _render_garden(garden: dict, is_am: bool = False) -> str:
    """Compact 'From the Garden' almanac block (email-safe, no emoji).
    In the morning it carries a small self-updating 'This day in history' link to
    Britannica's on-this-day page (always shows the current date)."""
    if not garden or not garden.get("note"):
        return ""
    note = _esc(_dedash(garden.get("note", "")))
    in_season = [s for s in (garden.get("in_season") or []) if s]
    season_txt = _clip(" · ".join(_esc(s) for s in in_season), 60)
    # Compose a short moon token, e.g. "Waxing crescent (13% illuminated)".
    moon_label = garden.get("moon_label", "")
    illum = garden.get("illum_pct", 0)
    # Guard against a label that already carries "(NN% illuminated)".
    if moon_label and illum and "illumin" not in moon_label.lower():
        moon_txt = f"{moon_label} ({illum}% illuminated)"
    else:
        moon_txt = moon_label
    sun_txt = garden.get("sun_range", "")
    sun_txt = f"Sun {sun_txt}" if sun_txt else ""
    # Small uppercase meta row holds only SHORT tokens (moon · sun · in-season).
    bits = [b for b in (_esc(moon_txt), _esc(sun_txt), season_txt) if b]
    meta = (
        f'<div style="font-family:{SANS}; font-size:11px; letter-spacing:1.4px; '
        f'text-transform:uppercase; color:{INK_MUTE}; padding-top:12px;">'
        + " &nbsp;&middot;&nbsp; ".join(bits) + "</div>"
    ) if bits else ""
    # The sky-tonight sentence reads as normal-case prose, not an uppercase chip.
    sky = _esc(_dedash(garden.get("sky_tonight", "")))
    sky_html = (
        f'<div style="font-family:{SERIF}; font-style:italic; font-size:15px; '
        f'line-height:1.55; color:{INK_MUTE}; padding-top:10px;">{sky}</div>'
    ) if sky else ""
    # Morning-only: a self-updating link to Britannica's "On This Day".
    history_html = (
        f'<div style="padding-top:14px;"><a href="{ON_THIS_DAY_URL}" '
        f'style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:1.2px; '
        f'text-transform:uppercase; color:{CLAY_DEEP}; text-decoration:none;">'
        f'This day in history &rarr;</a></div>'
    ) if is_am else ""
    return f"""
        <tr>
          <td class="px" style="padding:24px 32px 26px 32px; background-color:{SURFACE}; border-bottom:1px solid {LINE};">
            <div style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:3px; text-transform:uppercase; color:{BRASS_DEEP}; padding-bottom:9px;">{_eyebrow(f"From the Garden &nbsp;&middot;&nbsp; {_esc(GARDEN_LOCALE)}", BRASS_DEEP)}</div>
            <div style="font-family:{SERIF}; font-size:16px; line-height:1.58; color:{INK_SOFT};">{note}</div>
            {sky_html}
            {meta}
            {history_html}
          </td>
        </tr>"""


def _render_puzzle(puzzle: dict, prev: dict) -> str:
    """Fern's daily puzzle block (email-safe). The answer lives behind a link to
    the full edition's tap-to-reveal, plus the previous edition's answer inline."""
    puzzle = puzzle or {}
    prev = prev or {}
    if not puzzle.get("prompt") and not prev.get("answer"):
        return ""
    rows = []
    if puzzle.get("prompt"):
        label = _esc(puzzle.get("label") or "Fern's Puzzle")
        prompt = _esc(_dedash(puzzle["prompt"])).replace("\n", "<br>")
        hint = _esc(_dedash(puzzle.get("hint", "")))
        hint_html = (
            f'<div style="font-family:{SANS}; font-size:10.5px; letter-spacing:1.2px; '
            f'text-transform:uppercase; color:{INK_MUTE}; padding-top:10px;">Hint: {hint}</div>'
        ) if hint else ""
        credit = _esc(puzzle.get("credit", "")) or (
            f'via {_esc(puzzle["source"])}' if puzzle.get("source") else "")
        source_html = (
            f'<div style="font-family:{SANS}; font-size:10px; letter-spacing:1px; '
            f'color:{INK_MUTE}; padding-top:8px;">{credit}</div>'
        ) if credit else ""
        href = _safe_url(EDITION_URL) if EDITION_URL else "#"
        rows.append(
            f'<div style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:3px; '
            f'text-transform:uppercase; color:{BRASS_DEEP}; padding-bottom:10px;">{_eyebrow(label, BRASS_DEEP)}</div>'
            f'<div style="font-family:{SERIF}; font-size:16px; line-height:1.6; color:{INK_SOFT};">{prompt}</div>'
            f'{hint_html}'
            f'<div style="padding-top:14px;"><a href="{href}" style="font-family:{SANS}; font-size:11px; '
            f'font-weight:600; letter-spacing:1.2px; text-transform:uppercase; color:{CLAY_DEEP}; '
            f'text-decoration:none;">Reveal the answer in the full edition &rarr;</a></div>'
            f'{source_html}'
        )
    if prev.get("answer"):
        border = f'border-top:1px solid {LINE}; margin-top:16px; padding-top:12px;' if rows else ""
        rows.append(
            f'<div style="{border}">'
            f'<div style="font-family:{SANS}; font-size:11px; letter-spacing:1.2px; '
            f'text-transform:uppercase; color:{INK_MUTE}; padding-bottom:4px;">Last edition&#39;s answer</div>'
            f'<div style="font-family:{SERIF}; font-size:15px; line-height:1.55; color:{INK_SOFT};">'
            f'{_esc(_dedash(prev["answer"]))}</div>'
            f'</div>'
        )
    return f"""
        <tr>
          <td class="px" style="padding:24px 32px 26px 32px; background-color:{SURFACE}; border-bottom:1px solid {LINE};">
            {''.join(rows)}
          </td>
        </tr>"""


def _toc_row(num: str, cat: str, lead: str, count: str, href: str, last: bool = False) -> str:
    border = "" if last else f" border-bottom:1px solid {LINE};"
    return f"""
        <tr><td class="px" style="padding:0 32px;">
          <a href="{href}" style="text-decoration:none; color:{FOREST}; display:block;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{border}"><tr>
            <td valign="top" width="30" style="font-family:{DISPLAY}; font-style:italic; font-size:17px; color:{BRASS_DEEP}; padding:18px 0;">{num}</td>
            <td valign="top" style="padding:18px 0;">
              <div style="font-family:{DISPLAY}; font-weight:600; font-size:21px; color:{FOREST}; line-height:1.18;">{cat}</div>
              <div style="font-family:{SANS}; font-size:13px; color:{INK_MUTE}; padding-top:3px;">{lead}</div>
            </td>
            <td valign="top" align="right" width="84" style="font-family:{SANS}; font-size:10px; font-weight:600; letter-spacing:1px; text-transform:uppercase; color:{BRASS_DEEP}; padding:22px 0; white-space:nowrap;">{count}</td>
          </tr></table>
          </a>
        </td></tr>"""


def _render_larder(larder: dict) -> str:
    """The Larder — the seasonal note + a single recipe card (morning only). Gmail-safe.
    The email keeps it to one thing to cook: the locale-aware seasonal note (which is
    re-localized per recipient) plus the one featured recipe with its photo. The extra
    food-news headlines live only in the full web section (The Grove), never the email.
    Renders only when there's a recipe (the PM edition never carries a larder)."""
    larder = larder or {}
    recipe = larder.get("recipe") or {}
    if not recipe.get("title"):
        return ""

    note = _esc(_dedash(larder.get("seasonal_note", "")))
    note_html = (
        f'<div style="font-family:{SERIF}; font-style:italic; font-size:15.5px; '
        f'line-height:1.55; color:{INK_SOFT}; padding-bottom:16px;">{note}</div>'
    ) if note else ""

    blocks = []
    # Recipe card — cover image (if any) + label + title + blurb + link.
    if recipe.get("title"):
        href = _safe_url(recipe.get("url", "#"))
        cover = _safe_url(recipe.get("cover_url", "")) if recipe.get("cover_url") else ""
        img = (
            f'<a href="{href}"><img src="{cover}" alt="" width="536" '
            f'style="display:block; width:100%; max-width:536px; height:auto; '
            f'border:1px solid {BRASS}; margin-bottom:14px;"></a>'
        ) if cover else ""
        src = _esc(recipe.get("source_name", ""))
        title = _esc(_dedash(recipe["title"]))
        blurb = _esc(_dedash(recipe.get("blurb", "")))
        blocks.append(
            f'{img}'
            f'<div style="font-family:{SANS}; font-size:10.5px; font-weight:600; letter-spacing:2px; '
            f'text-transform:uppercase; color:{CLAY_DEEP}; padding-bottom:6px;">Recipe &nbsp;&middot;&nbsp; {src}</div>'
            f'<div style="font-family:{DISPLAY}; font-weight:600; font-size:23px; line-height:1.15; color:{FOREST};">'
            f'<a href="{href}" style="color:{FOREST}; text-decoration:none;">{title}</a></div>'
            + (f'<div style="font-family:{SERIF}; font-size:15px; line-height:1.55; color:{INK_SOFT}; padding-top:8px;">{blurb}</div>' if blurb else "")
            + f'<div style="padding-top:12px;"><a href="{href}" style="font-family:{SANS}; font-size:11px; '
              f'font-weight:600; letter-spacing:1.2px; text-transform:uppercase; color:{CLAY_DEEP}; '
              f'text-decoration:none;">Get the recipe &rarr;</a></div>'
        )

    # Food-news headlines are intentionally omitted from the email — they live only in
    # the full web section (The Grove). The email carries just note + one recipe.

    return f"""
        <tr>
          <td class="px" style="padding:24px 32px 26px 32px; background-color:{SURFACE}; border-bottom:1px solid {LINE};">
            <div style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:3px; text-transform:uppercase; color:{BRASS_DEEP}; padding-bottom:12px;">{_eyebrow("The Larder", BRASS_DEEP)}</div>
            {note_html}{''.join(blocks)}
          </td>
        </tr>"""


def _render_contents(videos, music, good_news, discovery, read=None, is_am=True) -> str:
    href = _safe_url(EDITION_URL) if EDITION_URL else "#"
    soundtrack_label = "The Morning Soundtrack" if is_am else "The Evening Soundtrack"
    specs = [
        (soundtrack_label,         music,     _top_titles(music),     "Tracks"),
        ("Worth Watching",         videos,    _top_titles(videos),    "Films"),
        ("Global Silver Linings",  good_news, _top_titles(good_news), "Stories"),
        ("From the Archives",      discovery, _top_titles(discovery), "Finds"),
    ]
    present = [(c, items, lead, unit) for c, items, lead, unit in specs if items]
    has_read = bool(read and read.get("title"))
    if not present and not has_read:
        return ""
    total = len(present) + (1 if has_read else 0)
    rows, n = [], 0
    for cat, items, lead, unit in present:
        n += 1
        rows.append(_toc_row(f"{n:02d}", cat, lead or "&nbsp;",
                             f"{len(items)} {unit}", href, last=(n == total)))
    if has_read:
        n += 1
        rows.append(_toc_row(f"{n:02d}", "One Good Read",
                             _clip(_esc(read.get("title", "")), 78),
                             _esc(read.get("source_name", "")) or "Essay", href, last=(n == total)))
    return f"""
        <tr>
          <td class="px" style="padding:36px 32px 4px 32px;">
            <div style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:3px; text-transform:uppercase; color:{BRASS_DEEP};">{_eyebrow("In this edition", BRASS_DEEP)}</div>
          </td>
        </tr>{''.join(rows)}"""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def build_html(curated: dict) -> str:
    themes    = curated.get("themes", [])
    music     = curated.get("morning_soundtrack", [])
    good_news = curated.get("global_silver_linings", [])
    discovery = curated.get("discovery_articles", [])
    read      = curated.get("featured_read", {})
    garden    = curated.get("garden_note", {})
    fern      = curated.get("fern_data", {})
    is_am     = curated.get("is_am_email", False)
    fetched   = curated.get("fetched_at", "")

    videos = [v for t in themes for v in t.get("items", [])]

    edition_label = "Morning Edition" if is_am else "Evening Edition"
    gathered      = "Gathered at dawn" if is_am else "Gathered at dusk"
    try:
        dt = datetime.datetime.fromisoformat(fetched).astimezone(EDITION_TZ)
        date_str = f"{dt.strftime('%a, %B')} {dt.day}"
        issue_html = f"No. {_edition_no(dt, is_am)} &nbsp;&middot;&nbsp; "
    except Exception:
        date_str = fetched or ""
        issue_html = ""

    counts = []
    if music:  counts.append(f"{len(music)} tracks")
    if videos: counts.append(f"{len(videos)} films")
    extra = len(good_news) + len(discovery)
    if extra:  counts.append(f"{extra} stories &amp; finds")
    sep = "&nbsp;&nbsp;&middot;&nbsp;&nbsp;"
    meta_line = sep.join([gathered] + counts)

    preheader = _esc(_clip(_dedash(fern.get("greeting", "")) or
                           "A quiet gathering, music, good news, and the natural world.", 110))

    hero_html   = _render_hero(videos[0]) if videos else ""
    fern_html   = _render_fern_note(fern.get("greeting", ""))
    garden_html = _render_garden(garden, is_am=is_am)
    larder_html = _render_larder(curated.get("larder"))
    puzzle_html = _render_puzzle(curated.get("puzzle"), curated.get("previous_puzzle"))
    toc_html    = _render_contents(videos, music, good_news, discovery, read, is_am=is_am)

    logo_html = (
        f'<img src="{_safe_url(FERN_LOGO_URL)}" alt="" width="96" '
        f'style="display:block; margin:0 auto 18px auto; max-width:96px; height:auto;">'
        if FERN_LOGO_URL else ""
    )
    cta_html = (
        f"""
        <tr>
          <td align="center" style="padding:34px 32px 8px 32px;">
            <table role="presentation" cellpadding="0" cellspacing="0" align="center"><tr>
              <td class="hover-cta" align="center" bgcolor="{CLAY}" style="background-color:{CLAY};">
                <a href="{_safe_url(EDITION_URL)}" style="display:inline-block; font-family:{SANS}; font-size:13px; font-weight:600; letter-spacing:1px; text-transform:uppercase; color:{CREAM}; text-decoration:none; padding:15px 34px; white-space:nowrap;">Open the full edition</a>
              </td>
            </tr></table>
            <div style="font-family:{SANS}; font-size:11px; letter-spacing:1.6px; text-transform:uppercase; color:{INK_MUTE}; padding-top:14px;">Covers, films &amp; the complete collection</div>
          </td>
        </tr>"""
        if EDITION_URL else ""
    )

    return f"""{_HEAD}
<body style="margin:0; padding:0; background-color:{PAPER_DEEP};">
<div style="display:none; max-height:0; overflow:hidden; opacity:0; mso-hide:all; font-size:1px; line-height:1px; color:{PAPER_DEEP};">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{PAPER_DEEP};">
  <tr>
    <td align="center" style="padding:0;">
      <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" style="width:600px; max-width:600px; background-color:{PAPER};">
        <tr>
          <td align="center" bgcolor="{FOREST}" style="background-color:{FOREST}; padding:30px 22px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BRASS};">
              <tr>
                <td class="px" align="center" style="padding:42px 28px 38px 28px;">
                  {logo_html}
                  <div style="font-family:{SANS}; font-size:11px; font-weight:600; letter-spacing:3px; text-transform:uppercase; color:{BRASS_SOFT}; padding-bottom:18px;">{_eyebrow(f"{edition_label} &nbsp;&middot;&nbsp; {issue_html}{date_str}", BRASS_SOFT)}</div>
                  <div class="wordmark" style="font-family:{DISPLAY}; font-weight:600; font-size:54px; line-height:0.98; color:{CREAM};">The&nbsp;Curated&nbsp;Canopy</div>
                  <div style="font-family:{DISPLAY}; font-style:italic; font-size:19px; color:{CREAM_MUTE}; padding-top:12px;">Human stories, good news &amp; the natural world</div>
                  <div style="padding-top:20px;">{_flourish(BRASS_SOFT)}</div>
                  <div style="font-family:{SANS}; font-size:11px; letter-spacing:1.6px; text-transform:uppercase; color:{CREAM_MUTE}; padding-top:20px;">{meta_line}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>{fern_html}{garden_html}{larder_html}{puzzle_html}{hero_html}{toc_html}{cta_html}
        <tr>
          <td align="center" bgcolor="{FOREST}" style="background-color:{FOREST}; padding:30px 22px 36px 22px; margin-top:40px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BRASS};">
              <tr>
                <td class="px" align="center" style="padding:38px 28px 40px 28px;">
                  <div style="padding-bottom:18px;">{_flourish(BRASS_SOFT)}</div>
                  <div style="font-family:{DISPLAY}; font-weight:600; font-size:26px; color:{CREAM};">The Curated Canopy</div>
                  <div style="font-family:{DISPLAY}; font-style:italic; font-size:16px; color:{CREAM_MUTE}; padding-top:6px;">Gathered twice daily by Fern</div>
                  <div style="font-family:{SANS}; font-size:11px; color:{CREAM_MUTE}; line-height:1.8; padding-top:18px;">
                    You're receiving this because you asked for a quieter inbox.<br>
                    <a href="#" style="color:{BRASS_SOFT}; text-decoration:none;">Preferences</a>&nbsp;&nbsp;&middot;&nbsp;&nbsp;<a href="#" style="color:{BRASS_SOFT}; text-decoration:none;">Unsubscribe</a>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# SMTP sender  (unchanged behaviour)
# ---------------------------------------------------------------------------
def _env_recipient_pairs() -> list[tuple[str, str]]:
    """Parse EMAIL_TO (or NEWSLETTER_RECIPIENTS / RECIPIENTS) into (name, email)
    pairs, honouring the standard `Name <email>` format so the main list can
    carry per-reader names. Bare `email` entries come back with an empty name."""
    raw_to = (
        os.environ.get("EMAIL_TO")
        or os.environ.get("NEWSLETTER_RECIPIENTS")
        or os.environ.get("RECIPIENTS")
        or ""
    )
    return [(n.strip(), e.strip()) for (n, e) in getaddresses([raw_to]) if e.strip()]


def send_email(html_body: str, subject: str,
               recipients: "list[str] | None" = None,
               to_name: str = "", to_addr: str = "") -> None:
    """Send one HTML message. `recipients` is the SMTP envelope (bare addresses);
    when None it's parsed from EMAIL_TO. `to_name`/`to_addr` set the visible To —
    used to address a single reader personally; otherwise recipients are effectively
    BCC'd behind the sender label."""
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

    if recipients is None:
        recipients = [e for (_n, e) in _env_recipient_pairs()] or [smtp_user]
    if not recipients:
        raise SystemExit("ERROR: No recipient. Set EMAIL_TO.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = formataddr(("Fern | The Curated Canopy", smtp_user))
    # A personalized single send shows the reader's own address in To:; a batch
    # send hides everyone behind the sender label (BCC via the envelope below).
    msg["To"]      = (formataddr((to_name, to_addr)) if to_addr
                      else formataddr(("The Curated Canopy readers", smtp_user)))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"[SMTP] Connecting to {smtp_host}:{smtp_port} …")
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipients, msg.as_bytes())
    who = to_addr or f"{len(recipients)} recipient(s)"
    print(f"[SMTP] Sent to {who}.")


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
        subject  = f"{prefix} | {top_pick}" if top_pick else f"{prefix} · The Curated Canopy"

        pairs   = _env_recipient_pairs()
        named   = [(n, e) for (n, e) in pairs if n]
        unnamed = [e for (n, e) in pairs if not n]

        if not named:
            # No per-reader names — one send to the whole list, as before.
            send_email(html, subject=subject)
            return

        # Personalize Fern's note per named reader. Generate ONE greeting with a
        # {{NAME}} slot, then substitute each reader's name (natural, one Claude
        # call). If the slot doesn't survive, fall back to a simple salutation.
        placeholder = ""
        try:
            import curator
            tmpl = curator.generate_fern_greeting(
                curator.build_claude_client(), is_am,
                curated.get("themes", []), curated.get("morning_soundtrack", []),
                curated.get("global_silver_linings", []), curated.get("discovery_articles", []),
                curated.get("featured_read", {}),
                date_str=curated.get("fetched_at", "") or "",
                recipient="{{NAME}}",
            )
            if "{{NAME}}" in (tmpl.get("greeting") or ""):
                placeholder = tmpl["greeting"]
        except Exception as exc:
            print(f"[render] Personalized greeting template failed ({exc}) — using salutation.")

        base_greeting = fern.get("greeting", "")

        def _note_for(name: str) -> str:
            if placeholder:
                return placeholder.replace("{{NAME}}", name)
            salute = ("Good morning, " if is_am else "Good evening, ") + name + ". "
            return (salute + base_greeting).strip()

        for name, email in named:
            c2 = json.loads(json.dumps(curated))
            c2.setdefault("fern_data", {})["greeting"] = _note_for(name)
            send_email(build_html(c2), subject=subject,
                       recipients=[email], to_name=name, to_addr=email)

        if unnamed:
            # Everyone without a name gets the shared (generic) note in one batch.
            send_email(html, subject=subject, recipients=unnamed)
        return

    msg = "[render] EMAIL NOT SENT — missing SMTP secrets."
    if os.environ.get("ALLOW_NO_EMAIL") == "1":
        print(msg + " (ALLOW_NO_EMAIL=1 — preview only)")
    else:
        raise SystemExit(msg)


def _subject_for(curated: dict) -> str:
    is_am    = curated.get("is_am_email", False)
    top_pick = _dedash(curated.get("fern_data", {}).get("top_pick_title", "")).strip()
    prefix   = "The Morning Rise" if is_am else "The Evening Wind-down"
    return f"{prefix} | {top_pick}" if top_pick else f"{prefix} · The Curated Canopy"


def send_regional() -> None:
    """
    Regional re-send: reuse the primary edition's committed content, re-localize
    only "From the Garden" (to GARDEN_LOCALE / EDITION_TZ), and email it to this
    region's recipient list (EMAIL_TO). No web publish, no history writes.

    Guards (skip cleanly rather than send a wrong/duplicate email):
      - curated_data.json must exist and be TODAY's (in EDITION_TZ);
      - its AM/PM must match this region's local time (morning reuses a morning
        edition, evening an evening one).
    """
    if not CURATED_FILE.exists():
        raise SystemExit(f"[regional] {CURATED_FILE} not found — primary edition hasn't run yet.")
    curated = json.loads(CURATED_FILE.read_text(encoding="utf-8"))

    now = datetime.datetime.now(EDITION_TZ)
    fetched = curated.get("fetched_at", "")
    try:
        content_date = datetime.datetime.fromisoformat(fetched).astimezone(EDITION_TZ).date()
    except Exception:
        content_date = None
    if content_date != now.date():
        print(f"[regional] Skipping: curated content date {content_date} != today {now.date()} "
              f"({GARDEN_LOCALE}). Primary edition may not have run yet.")
        return
    want_am = now.hour < 12
    if bool(curated.get("is_am_email", False)) != want_am:
        print(f"[regional] Skipping: content is {'AM' if curated.get('is_am_email') else 'PM'} "
              f"but {GARDEN_LOCALE} wants {'AM' if want_am else 'PM'}.")
        return

    # Re-localize the garden note for this region (season/moon are identical;
    # locale flavour + sky framing differ). Best-effort: keep the primary note on
    # any failure so the edition still goes out.
    try:
        import curator
        from fetcher import _season, _moon_phase, _sun_times  # real almanac implementations
        seed = {
            "date":   now.date().isoformat(),
            "season": _season(now),
            "moon":   _moon_phase(now),
            "sun":    _sun_times(GARDEN_LOCALE, now.date()),
            "is_am":  want_am,
            "locale": GARDEN_LOCALE,
        }
        note = curator.generate_garden_note(curator.build_claude_client(), seed)
        if note.get("note"):
            curated["garden_note"] = note
            print(f"[regional] Re-localized From the Garden for {GARDEN_LOCALE}.")
        else:
            print("[regional] Garden regen returned empty — keeping the primary note.")
    except Exception as exc:
        print(f"[regional] Garden regen skipped ({exc}) — keeping the primary note.")

    # Re-localize The Larder's seasonal food note for this region (the recipe +
    # news are shared, only Fern's seasonal comment differs). Morning only, since
    # that's the only edition that carries a larder. Best-effort.
    larder = curated.get("larder") or {}
    if larder.get("news") or larder.get("recipe"):
        try:
            import curator
            from fetcher import _season
            food_note = curator.generate_larder_note(
                curator.build_claude_client(), GARDEN_LOCALE, _season(now), want_am)
            if food_note:
                larder["seasonal_note"] = food_note
                curated["larder"] = larder
                print(f"[regional] Re-localized The Larder note for {GARDEN_LOCALE}.")
        except Exception as exc:
            print(f"[regional] Larder note regen skipped ({exc}).")

    # Personalize Fern's opening note to this edition's single recipient, if a name
    # is provided (RECIPIENT_NAME). Re-generates the greeting from the same shared
    # content so Fern addresses them by name. Best-effort: keep the shared note on failure.
    recipient = os.environ.get("RECIPIENT_NAME", "").strip()
    if recipient:
        try:
            import curator
            from fetcher import _season
            fern = curator.generate_fern_greeting(
                curator.build_claude_client(),
                want_am,
                curated.get("themes", []),
                curated.get("morning_soundtrack", []),
                curated.get("global_silver_linings", []),
                curated.get("discovery_articles", []),
                curated.get("featured_read", {}),
                date_str=curated.get("fetched_at", "") or "",
                season=_season(now),
                recipient=recipient,
            )
            if fern.get("greeting"):
                # keep the shared subject-line title; only swap the personalized note
                fern["top_pick_title"] = curated.get("fern_data", {}).get("top_pick_title", fern.get("top_pick_title", ""))
                curated["fern_data"] = fern
                print(f"[regional] Personalized Fern's note for {recipient}.")
        except Exception as exc:
            print(f"[regional] Greeting personalization skipped ({exc}).")

    html = build_html(curated)
    OUTPUT_HTML.write_text(html, encoding="utf-8")

    smtp_ready = (
        (os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER"))
        and os.environ.get("SMTP_PASS")
        and (os.environ.get("SMTP_SERVER") or os.environ.get("SMTP_HOST"))
    )
    if not smtp_ready:
        if os.environ.get("ALLOW_NO_EMAIL") == "1":
            print("[regional] EMAIL NOT SENT (ALLOW_NO_EMAIL=1 — preview only).")
            return
        raise SystemExit("[regional] EMAIL NOT SENT — missing SMTP secrets.")
    send_email(html, subject=_subject_for(curated))


if __name__ == "__main__":
    import sys
    if "--regional" in sys.argv:
        send_regional()
    else:
        main()
