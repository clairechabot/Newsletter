"""
Newsletter Renderer & Sender
-----------------------------
Reads curated_data.json → generates newsletter.html → sends via SMTP.

Required environment variables:
    EMAIL_USER              — sender address (also used as SMTP login)
    SMTP_PASS              — SMTP password / app password
    NEWSLETTER_RECIPIENTS  — comma-separated recipient addresses
    SMTP_HOST              — optional, default: smtp.gmail.com
    SMTP_PORT              — optional, default: 587
"""

import os
import re
import json
import random
import smtplib
import datetime
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR      = Path(__file__).parent
CURATED_FILE  = BASE_DIR / "curated_data.json"
OUTPUT_HTML   = BASE_DIR / "newsletter.html"

# Set to an externally-hosted URL or a data:image/png;base64,... URI to display the Fern logo.
# Leave empty to show only the emoji brand mark.
FERN_LOGO_URL = os.environ.get("FERN_LOGO_URL", "")

# ---------------------------------------------------------------------------
# Image extraction helpers
# ---------------------------------------------------------------------------

_IMAGE_EXTENSIONS = re.compile(r"\.(jpg|jpeg|png|gif|webp)(\?.*)?$", re.IGNORECASE)
_MARKDOWN_IMG     = re.compile(r"!\[.*?\]\((https?://\S+?)\)")
_BARE_URL         = re.compile(r"https?://\S+\.(?:jpg|jpeg|png|gif|webp)(?:\?\S*)?", re.IGNORECASE)


def _extract_images(post: dict) -> list[str]:
    """Return a de-duplicated list of image URLs found in a Reddit post."""
    found: list[str] = []

    # Direct link to an image
    url = post.get("url", "")
    if _IMAGE_EXTENSIONS.search(url):
        found.append(url)

    # Images embedded in selftext
    selftext = post.get("selftext") or ""
    found.extend(_MARKDOWN_IMG.findall(selftext))
    found.extend(_BARE_URL.findall(selftext))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for img in found:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    return unique


def _yt_thumbnail(video_id: str) -> str:
    return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"


def _yt_embed(video_id: str) -> str:
    return f"https://www.youtube.com/embed/{video_id}"


# ---------------------------------------------------------------------------
# HTML building blocks
# ---------------------------------------------------------------------------

_CSS = """
/* ── Reset & Base ────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background: #F9F7F2;
  color: #2C3E50;
  line-height: 1.6;
  padding: 0;
}
a { color: #5D6D7E; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Wrapper ─────────────────────────────────────────────── */
.wrapper {
  max-width: 680px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

/* ── Masthead / Brand Header ─────────────────────────────── */
.masthead {
  background: #FFFFFF;
  border-radius: 16px;
  padding: 32px 32px 0;
  margin-bottom: 32px;
  text-align: center;
  border: 1px solid #E0E0E0;
  overflow: hidden;
}
.brand-logo {
  font-size: 38px;
  line-height: 1;
  margin-bottom: 10px;
}
.brand-title {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 28px;
  font-weight: bold;
  color: #5D6D7E;
  letter-spacing: 0.3px;
  margin: 0;
}
.brand-tagline {
  font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px;
  color: #666666;
  margin: 6px 0 0;
}
.brand-date {
  font-size: 12px;
  color: #9CA3AF;
  margin-top: 4px;
}
.brand-separator {
  height: 2px;
  background: #82954B;
  margin: 20px -32px 0;
}
.masthead .stats {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
  background: #F9F7F2;
  margin: 0 -32px;
  padding: 12px 32px;
}
.masthead .stat-pill {
  background: rgba(93, 109, 126, 0.10);
  border: 1px solid rgba(93, 109, 126, 0.18);
  border-radius: 999px;
  padding: 3px 12px;
  font-size: 12px;
  color: #5D6D7E;
}

/* ── Theme Section ───────────────────────────────────────── */
.theme-section {
  margin-bottom: 32px;
}
.theme-header {
  border: none;
  border-left: 6px solid #82954B;
  background: #F9FAF9;
  border-radius: 0 12px 12px 0;
  padding: 10px 16px;
  margin-bottom: 12px;
}
.theme-header h2 {
  font-family: Georgia, serif;
  font-size: 18px;
  font-weight: 700;
  color: #2C3E50;
}
.theme-header .tagline {
  font-size: 13px;
  color: #6B7280;
  margin-top: 2px;
}

/* ── Content Card ────────────────────────────────────────── */
.card {
  background: #F9FAF9;
  border: none;
  border-left: 6px solid #82954B;
  border-radius: 0 12px 12px 0;
  margin-bottom: 20px;
  overflow: hidden;
  transition: border-left-color 0.15s;
}
.card:hover { border-left-color: #6B7C3A; }

/* ── <details> / <summary> ───────────────────────────────── */
details { }
summary {
  list-style: none;
  cursor: pointer;
  padding: 20px 24px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  user-select: none;
}
summary::-webkit-details-marker { display: none; }
summary::before {
  content: "▶";
  font-size: 10px;
  color: #9CA3AF;
  margin-top: 4px;
  flex-shrink: 0;
  transition: transform 0.2s;
}
details[open] > summary::before {
  transform: rotate(90deg);
}

.summary-body { flex: 1; min-width: 0; }
.summary-title {
  font-size: 14px;
  font-weight: 600;
  font-family: Georgia, serif;
  color: #2C3E50;
  line-height: 1.4;
}
.summary-desc {
  font-size: 13px;
  color: #6B7280;
  margin-top: 3px;
  line-height: 1.6;
}
.badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 3px;
}
.badge-reddit   { background: #FFF4F0; color: #C0392B; border: 1px solid #FFCCC7; }
.badge-youtube  { background: #FFF1F0; color: #C0392B; border: 1px solid #FFC9C9; }
.badge-ai       { background: #FFFBEB; color: #92400E; border: 1px solid #FDE68A; }
.badge-wildcard { background: #F0FDF4; color: #3F6212; border: 1px solid #BBF7D0; }

/* ── Expanded Content ────────────────────────────────────── */
.card-body {
  padding: 24px;
  border-top: 1px solid #EEEEEE;
}
.post-text {
  font-size: 13px;
  color: #374151;
  margin-top: 0;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
  line-height: 1.65;
}
.post-link {
  display: inline-block;
  margin-top: 12px;
  font-size: 12px;
  color: #82954B;
  font-weight: 500;
  text-decoration: none;
}

/* ── Image Grid ──────────────────────────────────────────── */
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
  margin-top: 14px;
}
.image-grid img {
  width: 100%;
  height: 130px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #E0E0E0;
}

/* ── YouTube Embed Block ─────────────────────────────────── */
.yt-container {
  margin-top: 0;
  position: relative;
  display: block;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #E0E0E0;
}
.yt-container img {
  width: 100%;
  display: block;
  aspect-ratio: 16/9;
  object-fit: cover;
}
.yt-play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.25);
  transition: background 0.15s;
}
.yt-container:hover .yt-play-overlay { background: rgba(0,0,0,0.4); }
.yt-play-btn {
  width: 62px;
  height: 44px;
  background: #ff0000e6;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.yt-play-btn::after {
  content: "";
  border-style: solid;
  border-width: 10px 0 10px 20px;
  border-color: transparent transparent transparent #fff;
  margin-left: 4px;
}

/* ── Morning Soundtrack Section ──────────────────────────── */
.soundtrack-section {
  margin-bottom: 32px;
}
.soundtrack-header {
  border: none;
  border-left: 6px solid #82954B;
  background: #F9FAF9;
  border-radius: 0 12px 12px 0;
  padding: 10px 16px;
  margin-bottom: 12px;
}
.soundtrack-header h2 {
  font-family: Georgia, serif;
  font-size: 18px;
  font-weight: 700;
  color: #2C3E50;
}
.soundtrack-header .tagline {
  font-size: 13px;
  color: #6B7280;
  margin-top: 2px;
}
.badge-music {
  background: #FDF4FF;
  color: #86198F;
  border: 1px solid #E9D5FF;
}
.vibe-check {
  font-size: 12px;
  color: #A0647A;
  margin-top: 6px;
  font-style: italic;
}
.music-listen-btn {
  display: inline-block;
  margin-top: 12px;
  padding: 7px 16px;
  background: rgba(160, 100, 122, 0.08);
  border: 1px solid #87A878;
  border-radius: 999px;
  color: #A0647A;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}
.music-listen-btn:hover { background: rgba(160, 100, 122, 0.15); }

/* ── Global Silver Linings Section ───────────────────────── */
.goodnews-section {
  margin-bottom: 32px;
}
.goodnews-header {
  border: none;
  border-left: 6px solid #82954B;
  background: #F9FAF9;
  border-radius: 0 12px 12px 0;
  padding: 10px 16px;
  margin-bottom: 12px;
}
.goodnews-header h2 {
  font-family: Georgia, serif;
  font-size: 18px;
  font-weight: 700;
  color: #2C3E50;
}
.goodnews-header .tagline {
  font-size: 13px;
  color: #6B7280;
  margin-top: 2px;
}
.badge-goodnews {
  background: #F0FDF4;
  color: #3F6212;
  border: 1px solid #BEF264;
}

/* ── Section-level collapsible ───────────────────────────── */
.section-details > summary {
  padding: 0;
  display: block;
  list-style: none;
}
.section-details > summary::-webkit-details-marker { display: none; }
.section-details > summary::before { display: none; }
.section-header-toggle {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
}
.section-details[open] .section-header-toggle {
  margin-bottom: 12px;
}
.section-chevron {
  font-size: 14px;
  color: #9CA3AF;
  margin-left: 12px;
  flex-shrink: 0;
  transition: transform 0.2s;
  line-height: 1;
}
.section-details[open] > summary .section-chevron {
  transform: rotate(180deg);
}

/* ── Fern Greeting ───────────────────────────────────────── */
.fern-greeting {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  background: #F9FAF9;
  border: none;
  border-left: 6px solid #82954B;
  border-radius: 0 12px 12px 0;
  padding: 16px 20px;
  margin-bottom: 20px;
}
.fern-avatar {
  font-size: 26px;
  flex-shrink: 0;
  line-height: 1.3;
}
.fern-byline {
  font-size: 11px;
  font-weight: 700;
  color: #82954B;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 4px;
}
.fern-greeting p {
  font-size: 14px;
  color: #374151;
  line-height: 1.65;
  margin: 0;
  font-style: italic;
}

/* ── Energy Spectrum Bar (inline-only — kept for browser view) ── */
/* Rendered entirely with inline styles for email-client compatibility. */

/* ── Footer ──────────────────────────────────────────────── */
.footer {
  text-align: center;
  font-size: 11px;
  color: #9CA3AF;
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid #E0E0E0;
}
"""

# Accent colours cycle per theme section
_ACCENTS = ["#5D6D7E", "#82954B", "#C17F3A", "#7B6FA0", "#3A7D85"]



# Mood score buckets — subreddit names lowercased
_EMERALD_SUBREDDITS = frozenset({"containergardening", "simpleliving", "breadmachines"})
_AMBER_SUBREDDITS   = frozenset({"obsidianmd", "oldrecipes", "vintagemenus"})
_CRIMSON_SUBREDDITS = frozenset({"hobbydrama", "pettyrevenge", "maliciouscompliance", "amitheangel"})

# Fern's energy-aware opening lines, keyed by dominant mood
_FERN_ENERGY_LINES: dict[str, list[str]] = {
    "emerald": [
        "I've kept things soft and slow today — the kind of reading that pairs well with warm tea and an open window.",
        "Everything today feels like it's quietly growing; I hope this collection gives you a gentle landing.",
        "It's a peaceful one in the archive — I've gathered the slower, softer corners of the internet for you.",
    ],
    "amber": [
        "My curiosity got the better of me today, so I followed a few rabbit holes and brought back the best ones.",
        "Today's collection has a wonderfully wandering quality to it — the kind of reading that makes you want to learn something new.",
        "There's a lot of interesting texture in today's curation, so settle in with something to sip.",
    ],
    "crimson": [
        "It's a bit of a spicy evening in the archives, so I've brewed a strong tea for you.",
        "The internet had opinions today — I've collected the most entertaining ones so you don't have to wade in yourself.",
        "A little more dramatic than usual in the stacks today; consider this your permission to enjoy the chaos from a safe distance.",
    ],
    "balanced": [
        "Today's mix is a little bit of everything — calm corners, curious detours, and just enough drama to keep things interesting.",
        "I couldn't settle on a single mood today, so I brought a bit of everything; I hope something here finds you well.",
    ],
}


def _fern_energy_line(emerald_pct: int, amber_pct: int, crimson_pct: int) -> str:
    """Return a Fern opening sentence that reflects the dominant energy type."""
    scores = [("emerald", emerald_pct), ("amber", amber_pct), ("crimson", crimson_pct)]
    scores.sort(key=lambda x: x[1], reverse=True)
    dominant, top_val = scores[0]
    second_val = scores[1][1]
    # Within 10 points at the top → call it balanced
    if top_val - second_val <= 10:
        dominant = "balanced"
    return random.choice(_FERN_ENERGY_LINES[dominant])



def _calculate_mood_score(
    themes: list,
    global_silver_linings: list,
    music_articles: list | None = None,
) -> tuple[int, int, int]:
    """Return (emerald_pct, amber_pct, crimson_pct) as integers summing to 100.

    Scoring rules:
      Emerald (Growth)   — r/ContainerGardening, r/SimpleLiving, r/BreadMachines,
                           Good News articles, Sofar Sounds music articles (+2 each)
      Amber   (Curiosity)— r/ObsidianMD, r/OldRecipes, r/Vintagemenus,
                           curated YouTube channel videos, Bandcamp Daily articles (+2 each)
      Crimson (Chaos)    — r/HobbyDrama, r/pettyrevenge, r/MaliciousCompliance, r/AmITheAngel
    Items that match none of the above are unscored (do not affect percentages).
    """
    emerald = amber = crimson = 0

    for theme in themes:
        for item in theme.get("items", []):
            sub    = item.get("subreddit", "").lower()
            source = item.get("source", "")
            if sub in _EMERALD_SUBREDDITS:
                emerald += 1
            elif sub in _AMBER_SUBREDDITS:
                amber += 1
            elif sub in _CRIMSON_SUBREDDITS:
                crimson += 1
            elif source == "youtube":
                # Curated hobby/interest channel videos → Curiosity
                amber += 1

    # Good News articles always count as Emerald growth
    emerald += len(global_silver_linings)

    # Music articles: Sofar Sounds → Emerald (+2), Bandcamp Daily → Amber (+2)
    for article in (music_articles or []):
        source_name = article.get("source_name", "")
        if source_name == "Sofar Sounds":
            emerald += 2
        elif source_name == "Bandcamp Daily":
            amber += 2

    total = emerald + amber + crimson
    if total == 0:
        return 34, 33, 33

    e_pct = round(emerald / total * 100)
    a_pct = round(amber   / total * 100)
    c_pct = round(crimson / total * 100)

    # Correct any rounding drift so the three values always sum to exactly 100
    diff = 100 - (e_pct + a_pct + c_pct)
    if diff != 0:
        # Apply correction to whichever bucket is largest
        if emerald >= amber and emerald >= crimson:
            e_pct += diff
        elif amber >= crimson:
            a_pct += diff
        else:
            c_pct += diff

    return e_pct, a_pct, c_pct


def _render_fern_greeting(greeting: str, energy_line: str = "") -> str:
    if not greeting and not energy_line:
        return ""

    def _e(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    energy_html  = (
        f'<p style="font-style:italic;margin:0 0 8px;color:#5a6e52;">{_e(energy_line)}</p>'
        if energy_line else ""
    )
    greeting_html = f"<p>{_e(greeting)}</p>" if greeting else ""

    return f"""
<div class="fern-greeting">
  <span class="fern-avatar">🌿</span>
  <div>
    <div class="fern-byline">A note from Fern</div>
    {energy_html}{greeting_html}
  </div>
</div>"""




def _render_mood_score(emerald_pct: int, amber_pct: int, crimson_pct: int) -> str:
    """
    Renders the Energy Spectrum bar using a single linear-gradient div + inline styles.
    All styles are inline so the bar survives email-client <style> stripping.
    """
    stop2 = emerald_pct
    stop3 = emerald_pct + amber_pct

    # Hard colour stops: duplicate each boundary to get a clean edge (no bleed)
    gradient = (
        f"linear-gradient(to right,"
        f" #50C878 0%, #50C878 {stop2}%,"
        f" #FFBF00 {stop2}%, #FFBF00 {stop3}%,"
        f" #DC143C {stop3}%, #DC143C 100%)"
    )

    # Shared inline style fragments
    _font = "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    _lbl  = f"display:block;font-size:11px;font-weight:600;letter-spacing:0.2px;{_font}"
    _pct  = f"display:block;font-size:10px;color:#9CA3AF;margin-top:1px;{_font}"

    def _cell(pct: int, emoji: str, name: str, color: str) -> str:
        # Suppress label content if segment is too narrow to fit text
        inner = (
            f'<span style="{_lbl}color:{color};">{emoji}&nbsp;{name}</span>'
            f'<span style="{_pct}">{pct}%</span>'
        ) if pct >= 10 else f'<span style="{_pct}text-align:center;">{pct}%</span>'
        return (
            f'<td style="width:{pct}%;vertical-align:top;text-align:center;'
            f'padding:0 2px;overflow:hidden;">{inner}</td>'
        )

    cells = "".join([
        _cell(emerald_pct, "🌿", "Tranquil", "#2d8a50"),
        _cell(amber_pct,   "✦",  "Engaged",  "#9a6200"),
        _cell(crimson_pct, "🌶", "Spicy",    "#B94040"),
    ])

    return f"""
<div style="margin-bottom:24px;">
  <div style="font-size:10px;color:#9CA3AF;letter-spacing:0.8px;text-transform:uppercase;margin-bottom:8px;{_font}">
    Today&rsquo;s Energy Spectrum
  </div>
  <div style="height:10px;border-radius:999px;overflow:hidden;background:{gradient};background-color:#82954B;"></div>
  <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;margin-top:8px;table-layout:fixed;">
    <tr>{cells}</tr>
  </table>
</div>"""


def _render_reddit_card(post: dict) -> str:
    title      = post.get("title", "(no title)")
    summary    = post.get("summary", "")
    ai_score   = post.get("ai_score")
    url        = post.get("url", "#")
    selftext   = (post.get("selftext") or "").strip()[:5000]
    images     = _extract_images(post)
    subreddit  = post.get("subreddit", "")
    is_wildcard = post.get("is_wildcard", False)

    ai_badge = (
        f'<span class="badge badge-ai">🤖 {ai_score}% AI</span>'
        if ai_score is not None else ""
    )
    wildcard_badge = (
        '<span class="badge badge-wildcard">✦ Wildcard</span>'
        if is_wildcard else ""
    )
    sub_badge = f'<span class="badge badge-reddit">r/{subreddit}</span>' if subreddit else ""

    image_grid = ""
    if images:
        imgs = "".join(
            f'<img src="{img}" alt="" loading="lazy">' for img in images[:6]
        )
        image_grid = f'<div class="image-grid">{imgs}</div>'

    post_body = ""
    if selftext:
        escaped = selftext.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        post_body = f'<div class="post-text">{escaped}</div>'

    return f"""
<div class="card">
  <details>
    <summary>
      <div class="summary-body">
        <div class="summary-title">{title}</div>
        <div class="summary-desc">{summary}</div>
      </div>
      {sub_badge}{ai_badge}{wildcard_badge}
    </summary>
    <div class="card-body">
      {post_body}
      {image_grid}
      <a class="post-link" href="{url}" target="_blank">Read full story →</a>
    </div>
  </details>
</div>"""


def _render_youtube_card(video: dict) -> str:
    title       = video.get("title", "(no title)")
    why_watch   = video.get("why_watch", video.get("description", ""))
    video_id    = video.get("video_id", "")
    channel     = video.get("channel_title", "")
    is_wildcard = video.get("is_wildcard", False)
    duration    = video.get("duration_seconds", 0)
    mins, secs  = divmod(duration, 60)

    thumb_url   = _yt_thumbnail(video_id)
    embed_url   = _yt_embed(video_id)

    yt_badge = '<span class="badge badge-youtube">▶ YouTube</span>'
    wildcard_badge = (
        '<span class="badge badge-wildcard">✦ Wildcard</span>'
        if is_wildcard else ""
    )

    return f"""
<div class="card">
  <details>
    <summary>
      <div class="summary-body">
        <div class="summary-title">{title}</div>
        <div class="summary-desc">{why_watch}</div>
      </div>
      {yt_badge}{wildcard_badge}
    </summary>
    <div class="card-body">
      <a class="yt-container" href="{embed_url}" target="_blank" title="{channel} · {mins}m {secs:02d}s">
        <img src="{thumb_url}" alt="{title}" loading="lazy">
        <span class="yt-play-overlay"><span class="yt-play-btn"></span></span>
      </a>
    </div>
  </details>
</div>"""


def _render_music_embed(embed_url: str, title: str) -> str:
    """
    Return an embed block for the given URL.
    - YouTube embed  → thumbnail + play overlay (same pattern as YouTube cards)
    - Bandcamp embed → inline iframe player
    - Bandcamp page  → styled listen button (fallback when we only have the page URL)
    """
    if not embed_url:
        return ""

    if "youtube.com/embed/" in embed_url:
        vid_id = embed_url.split("/embed/")[1].split("?")[0].split("&")[0]
        thumb  = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
        return (
            f'<a class="yt-container" href="{embed_url}" target="_blank" '
            f'title="Watch: {title}" style="border:2px solid #87A878;">'
            f'<img src="{thumb}" alt="{title}" loading="lazy">'
            f'<span class="yt-play-overlay"><span class="yt-play-btn"></span></span>'
            f'</a>'
        )

    if "bandcamp.com/EmbeddedPlayer" in embed_url:
        return (
            f'<iframe class="bc-player" src="{embed_url}" '
            f'seamless title="{title}" loading="lazy" '
            f'style="border:2px solid #87A878;width:100%;height:120px;border-radius:8px;'
            f'margin-top:12px;"></iframe>'
        )

    # Bare Bandcamp page link — render as a button
    if "bandcamp.com" in embed_url:
        return (
            f'<a class="music-listen-btn" href="{embed_url}" target="_blank">'
            f'♫ Listen on Bandcamp</a>'
        )

    return ""


def _render_music_card(article: dict) -> str:
    title       = article.get("title", "(no title)")
    source_name = article.get("source_name", "Music")
    url         = article.get("url", "#")
    snippet     = (article.get("snippet") or "").strip()
    vibe_check  = article.get("vibe_check", "")
    embed_url   = article.get("embed_url") or ""

    source_badge = f'<span class="badge badge-music">♪ {source_name}</span>'

    embed_html = _render_music_embed(embed_url, title)

    return f"""
<div class="card">
  <details>
    <summary>
      <div class="summary-body">
        <div class="summary-title">{title}</div>
        <div class="summary-desc">{vibe_check}</div>
      </div>
      {source_badge}
    </summary>
    <div class="card-body">
      {embed_html}
      <a class="post-link" href="{url}" target="_blank">Read full story →</a>
    </div>
  </details>
</div>"""


def _render_morning_soundtrack(articles: list[dict]) -> str:
    if not articles:
        return ""

    cards = "".join(_render_music_card(a) for a in articles)

    return f"""
<section class="soundtrack-section">
  <details class="section-details">
    <summary>
      <div class="soundtrack-header section-header-toggle">
        <div>
          <h2>🎵 The Morning Soundtrack</h2>
          <div class="tagline">Fresh picks from the music world to set the tone for your day.</div>
        </div>
        <span class="section-chevron">▾</span>
      </div>
    </summary>
    {cards}
  </details>
</section>"""


def _render_good_news_card(article: dict) -> str:
    raw_title   = article.get("title", "(no title)")
    source_name = article.get("source_name", "Good News")
    url         = article.get("url", "#")
    raw_reason  = article.get("reason", "")

    def _e(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    title  = _e(raw_title)
    reason = _e(raw_reason)

    source_badge = '<span class="badge badge-goodnews">🌿 Good News</span>'

    return f"""
<div class="card">
  <details>
    <summary>
      <div class="summary-body">
        <div class="summary-title">{title}</div>
        <div class="summary-desc">{reason}</div>
      </div>
      {source_badge}
    </summary>
    <div class="card-body">
      <a class="post-link" href="{url}" target="_blank">Read full story →</a>
    </div>
  </details>
</div>"""


def _render_global_silver_linings(articles: list[dict]) -> str:
    if not articles:
        return ""
    cards = "".join(_render_good_news_card(a) for a in articles)
    return f"""
<section class="goodnews-section">
  <details class="section-details">
    <summary>
      <div class="goodnews-header section-header-toggle">
        <div>
          <h2>🌿 Global Silver Linings</h2>
          <div class="tagline">Two stories that remind you the world is still full of good.</div>
        </div>
        <span class="section-chevron">▾</span>
      </div>
    </summary>
    {cards}
  </details>
</section>"""


def _render_theme(theme: dict, accent: str) -> str:
    name    = theme.get("name", "Untitled")
    tagline = theme.get("tagline", "")
    emoji   = theme.get("emoji", "")
    items   = theme.get("items", [])

    heading = f"{emoji} {name}" if emoji else name

    cards = []
    for item in items:
        source = item.get("source", "")
        if source in ("youtube", "youtube_trending"):
            cards.append(_render_youtube_card(item))
        else:
            cards.append(_render_reddit_card(item))

    return f"""
<section class="theme-section" style="--accent: {accent}">
  <details class="section-details">
    <summary>
      <div class="theme-header section-header-toggle">
        <div>
          <h2>{heading}</h2>
          <div class="tagline">{tagline}</div>
        </div>
        <span class="section-chevron">▾</span>
      </div>
    </summary>
    {"".join(cards)}
  </details>
</section>"""


def build_html(curated: dict) -> str:
    themes                 = curated.get("themes", [])
    summary                = curated.get("audit_summary", {})
    fetched_at             = curated.get("fetched_at", "")
    morning_soundtrack     = curated.get("morning_soundtrack", [])
    global_silver_linings  = curated.get("global_silver_linings", [])

    try:
        dt = datetime.datetime.fromisoformat(fetched_at).astimezone(ZoneInfo("Europe/Zurich"))
        tz_abbr = "CEST" if int(dt.utcoffset().total_seconds() / 3600) == 2 else "CET"
        date_str = f"{dt.strftime('%A, %B')} {dt.day}, {dt.strftime('%Y')} | {dt.strftime('%H:%M')} {tz_abbr}"
    except Exception:
        date_str = fetched_at

    music_pill = (
        f'<span class="stat-pill">♪ {len(morning_soundtrack)} Music</span>'
        if morning_soundtrack else ""
    )
    goodnews_pill = (
        f'<span class="stat-pill">🌿 {len(global_silver_linings)} Good News</span>'
        if global_silver_linings else ""
    )
    stats_html = "".join([
        f'<span class="stat-pill">✓ {summary.get("reddit_accepted", 0)} Reddit posts</span>',
        f'<span class="stat-pill">▶ {summary.get("youtube_videos", 0)} Videos</span>',
        f'<span class="stat-pill">🗂 {summary.get("themes", len(themes))} Themes</span>',
        f'<span class="stat-pill">🚫 {summary.get("reddit_discarded", 0)} filtered</span>',
        music_pill,
        goodnews_pill,
    ])

    # Mood scores first — used both for the spectrum bar and Fern's opening line
    emerald_pct, amber_pct, crimson_pct = _calculate_mood_score(themes, global_silver_linings, morning_soundtrack)
    mood_score_html       = _render_mood_score(emerald_pct, amber_pct, crimson_pct)

    fern_data             = curated.get("fern_data", {})
    energy_line           = _fern_energy_line(emerald_pct, amber_pct, crimson_pct)
    fern_greeting_html    = _render_fern_greeting(fern_data.get("greeting", ""), energy_line)


    theme_html = "".join(
        _render_theme(theme, _ACCENTS[i % len(_ACCENTS)])
        for i, theme in enumerate(themes)
    )

    soundtrack_html       = _render_morning_soundtrack(morning_soundtrack)
    silver_linings_html   = _render_global_silver_linings(global_silver_linings)

    logo_html = (
        f'<img src="{FERN_LOGO_URL}" alt="Fern" '
        f'style="display:block;margin:0 auto 20px;max-width:110px;height:auto;">'
        if FERN_LOGO_URL else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>The Curated Canopy</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
  <style>{_CSS}</style>
</head>
<body>
<div class="wrapper">

  <div class="masthead">
    {logo_html}
    <div class="brand-logo">🍞🌿🐚</div>
    <h1 class="brand-title">The Curated Canopy</h1>
    <p class="brand-tagline">Your 12-hour curation of Human Stories, Good News, and Nature.</p>
    <div class="brand-date">{date_str}</div>
    <div class="brand-separator"></div>
    <div class="stats">{stats_html}</div>
  </div>

  {fern_greeting_html}

  {mood_score_html}

  {silver_linings_html}

  {soundtrack_html}

  {theme_html}

  <div class="footer">
    Generated automatically · AI audit threshold 75% · Curated by Claude
  </div>

</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------

def send_email(html_body: str, subject: str) -> None:
    # Support both SMTP_USER / EMAIL_USER and SMTP_SERVER / SMTP_HOST secret names
    smtp_user = os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_host = os.environ.get("SMTP_SERVER") or os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))

    # Debug — visible in GitHub Actions logs so we can confirm what the runner sees
    print(f"DEBUG: Attempting to connect to host: '{smtp_host}' on port: '{smtp_port}'")
    print(f"DEBUG: smtp_user set: {bool(smtp_user)} | smtp_pass set: {bool(smtp_pass)}")

    # Bail out with a clear message rather than a cryptic socket error
    if not smtp_host or smtp_host.strip() == "":
        print("ERROR: SMTP_SERVER environment variable is empty. Check GitHub Secrets!")
        return
    if not smtp_user:
        print("ERROR: SMTP_USER / EMAIL_USER environment variable is empty. Check GitHub Secrets!")
        return

    # Try every common naming convention for the recipient list
    raw_to = (
        os.environ.get("EMAIL_TO")
        or os.environ.get("NEWSLETTER_RECIPIENTS")
        or os.environ.get("RECIPIENTS")
        or smtp_user  # last resort: send to the sender address
    )
    if not raw_to or raw_to.strip() == "":
        print("❌ ERROR: Fern cannot find a recipient email. Ensure 'EMAIL_TO' is in your .yml 'env' section.")
        return
    recipients = [r.strip() for r in raw_to.split(",") if r.strip()]
    print(f"✅ Fern is delivering to: {recipients}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = formataddr(("Fern | The Morning Crust", smtp_user))
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"[SMTP] Connecting to {smtp_host}:{smtp_port} …")
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
        raise FileNotFoundError(
            f"{CURATED_FILE} not found. Run fetcher.py first."
        )

    curated = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
    html    = build_html(curated)

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"[render] HTML written → {OUTPUT_HTML}")

    # Send only when all required SMTP credentials are present
    smtp_ready = (
        (os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER"))
        and os.environ.get("SMTP_PASS")
        and (os.environ.get("SMTP_SERVER") or os.environ.get("SMTP_HOST"))
    )
    if smtp_ready:
        is_am      = curated.get("is_am_email", False)
        fern_data  = curated.get("fern_data", {})
        top_pick   = fern_data.get("top_pick_title", "").strip()
        prefix     = "☀️ The Morning Rise" if is_am else "🌙 The Evening Wind-down"
        subject    = f"{prefix} | {top_pick}" if top_pick else f"{prefix} · The Curated Canopy"
        send_email(html, subject=subject)
    else:
        missing = []
        if not (os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER")):
            missing.append("SMTP_USER / EMAIL_USER")
        if not os.environ.get("SMTP_PASS"):
            missing.append("SMTP_PASS")
        if not (os.environ.get("SMTP_SERVER") or os.environ.get("SMTP_HOST")):
            missing.append("SMTP_SERVER / SMTP_HOST")
        print(f"[render] Skipping send — missing secrets: {', '.join(missing)}")


if __name__ == "__main__":
    main()
