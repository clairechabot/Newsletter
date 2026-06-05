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
DOCS_DIR      = BASE_DIR / "docs"
EDITION_HTML  = DOCS_DIR / "index.html"

# Public GitHub Pages URL for the interactive "full edition". Override via env.
# Set to "" to hide the button (e.g. if Pages isn't enabled yet).
EDITION_URL   = os.environ.get(
    "EDITION_URL", "https://clairechabot.github.io/Newsletter/"
)

# Set to an externally-hosted URL or a data:image/png;base64,... URI to display the Fern logo.
# Leave empty to show only the emoji brand mark.
FERN_LOGO_URL = os.environ.get("FERN_LOGO_URL", "")

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
  padding: 20px 30px;
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
  padding: 20px 30px;
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
  padding: 20px 30px;
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
  padding: 20px 30px;
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

/* ── Discovery sections (From the Archives + The Laboratory) ── */
.archives-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  cursor: pointer;
  padding: 20px 30px;
  border-radius: 10px 10px 0 0;
  background: #f8f5f0;
}
.lab-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  cursor: pointer;
  padding: 20px 30px;
  border-radius: 10px 10px 0 0;
  background: #f0f5f8;
}
.archives-header .tagline,
.lab-header .tagline {
  font-size: 13px;
  color: #6B7280;
  margin-top: 2px;
}
.discovery-card {
  border-left: 4px solid #87a878;
}
.discovery-card-title {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 15px;
  font-weight: 700;
  color: #2c2c2c;
  line-height: 1.4;
}
.discovery-card-snippet {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 13px;
  color: #555;
  margin-top: 6px;
  line-height: 1.6;
}
.badge-archives {
  background: #fdf3e3;
  color: #7a4f00;
  border: 1px solid #c8a96e;
}
.badge-lab {
  background: #e6f4f4;
  color: #1a5f5f;
  border: 1px solid #4a9a9a;
}
.badge-museum {
  background: #eeecf5;
  color: #3d2e6e;
  border: 1px solid #7a6e9a;
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
  padding: 20px 30px;
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
    discovery_articles: list | None = None,
) -> tuple[int, int, int]:
    """Return (emerald_pct, amber_pct, crimson_pct) as integers summing to 100.

    Scoring rules:
      Emerald (Growth)   — Good News articles (+1), all music articles (+2 each)
      Amber   (Curiosity)— YouTube channel videos (+1), Discovery articles (+1 each)
      Crimson (Chaos)    — YouTube trending/wildcard videos (+1)
    """
    emerald = amber = crimson = 0

    for theme in themes:
        for item in theme.get("items", []):
            source = item.get("source", "")
            if source == "youtube_trending":
                crimson += 1
            elif source == "youtube":
                amber += 1

    # Good News articles → Emerald
    emerald += len(global_silver_linings)

    # All music (Sofar Sounds + Bandcamp Daily) → Emerald; music is calming, not curiosity-driven
    emerald += len(music_articles or []) * 2

    # Discovery articles (History/Mystery + Science) → Amber
    amber += len(discovery_articles or [])

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


# ---------------------------------------------------------------------------
# Browsable layout toolkit — hero + horizontal swipe strips + album covers.
# Email-safe (no JS): native horizontal scroll/swipe, works in Gmail/Apple Mail.
# ---------------------------------------------------------------------------

_CSS_EXTRA = """
/* ── Open full edition button ─────────────────────────────── */
.edition-btn-wrap { text-align:center; margin:0 0 28px; }
.edition-btn {
  display:inline-block; background:#5D6D7E; color:#FFFFFF !important;
  padding:12px 24px; border-radius:30px; font-weight:bold; font-size:14px;
  text-decoration:none; border:1px solid #4A5763;
}
/* ── Horizontal swipe strip ───────────────────────────────── */
.strip-wrap { margin:8px 0 4px; }
.swipe-strip {
  display:flex; gap:12px; overflow-x:auto; -webkit-overflow-scrolling:touch;
  padding:4px 2px 12px; scroll-snap-type:x mandatory;
}
.swipe-strip::-webkit-scrollbar { height:6px; }
.swipe-strip::-webkit-scrollbar-thumb { background:#CBC3B5; border-radius:3px; }
.strip-hint { font-size:11px; color:#A9A39A; text-align:right; padding-right:6px; }
.dot { display:inline-block; width:6px; height:6px; border-radius:50%;
  background:#D6CFC2; margin-right:3px; vertical-align:middle; }
.dot.dot-on { background:#87A878; }
.swipe-label { margin-left:6px; }
/* ── Mini cards (in strips) ───────────────────────────────── */
.mini-card {
  flex:0 0 auto; width:160px; scroll-snap-align:start; background:#FFFFFF;
  border:1px solid #E0E0E0; border-radius:12px; overflow:hidden;
}
.mini-card a { display:block; color:#2C3E50; }
.mini-cover { width:100%; height:150px; object-fit:cover; display:block; background:#EFECE4; }
.mini-cover-tile { width:100%; height:120px; display:flex; align-items:center;
  justify-content:center; font-size:42px; background:linear-gradient(135deg,#EFE9DD,#E3EDE0); }
.mini-body { padding:10px 12px 14px; }
.mini-badge { font-size:10px; color:#87A878; font-weight:bold;
  text-transform:uppercase; letter-spacing:.4px; }
.mini-title { font-weight:bold; font-size:14px; line-height:1.35; margin:4px 0; }
.mini-note { font-size:12px; color:#7A8794; line-height:1.4; }
/* ── Hero card (featured first item) ──────────────────────── */
.hero-card { background:#FFFFFF; border:1px solid #E0E0E0; border-radius:14px;
  overflow:hidden; margin-bottom:4px; }
.hero-card a { display:block; color:#2C3E50; }
.hero-cover { width:100%; max-height:240px; object-fit:cover; display:block; background:#EFECE4; }
.hero-cover-tile { width:100%; height:150px; display:flex; align-items:center;
  justify-content:center; font-size:60px; background:linear-gradient(135deg,#EFE9DD,#E3EDE0); }
.hero-body { padding:14px 18px 18px; }
.hero-badge { font-size:11px; color:#87A878; font-weight:bold;
  text-transform:uppercase; letter-spacing:.4px; }
.hero-title { font-family:'Playfair Display', Georgia, serif; font-size:20px;
  font-weight:bold; margin:6px 0; line-height:1.3; }
.hero-note { font-size:14px; color:#5D6D7E; }
"""


def _esc(s: str) -> str:
    """Escape for both text and double-quoted attribute contexts."""
    return (
        (s or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )


def _safe_url(u: str) -> str:
    """Allow only http(s)/mailto/relative URLs; escape for attribute use.
    Blocks javascript:/data: and other script-bearing schemes."""
    u = (u or "").strip()
    low = u.lower()
    if low.startswith(("http://", "https://", "mailto:")) or u.startswith(("/", "#")):
        return _esc(u)
    return "#"


def _cover_html(url: str, emoji: str, *, hero: bool = False) -> str:
    """An <img> cover when a URL is present, else an emoji gradient tile."""
    cls = "hero-cover" if hero else "mini-cover"
    tile_cls = "hero-cover-tile" if hero else "mini-cover-tile"
    if url:
        return f'<img class="{cls}" src="{_safe_url(url)}" alt="" loading="lazy">'
    return f'<div class="{tile_cls}">{emoji}</div>'


def _swipe_strip(cards: list[str]) -> str:
    if not cards:
        return ""
    dots = "".join(
        f'<span class="dot{" dot-on" if i == 0 else ""}"></span>'
        for i in range(min(len(cards), 5))
    )
    body = "".join(cards)
    hint = (
        f'<div class="strip-hint">{dots}<span class="swipe-label">swipe →</span></div>'
        if len(cards) > 1 else ""
    )
    return f'<div class="strip-wrap"><div class="swipe-strip">{body}</div>{hint}</div>'


def _hero_card(*, href: str, cover: str, badge: str, title: str, note: str) -> str:
    return f"""
<div class="hero-card">
  <a href="{_safe_url(href)}" target="_blank">
    {cover}
    <div class="hero-body">
      <div class="hero-badge">{badge}</div>
      <div class="hero-title">{title}</div>
      <div class="hero-note">{note}</div>
    </div>
  </a>
</div>"""


def _mini_card(*, href: str, cover: str, badge: str, title: str, note: str) -> str:
    return f"""
<div class="mini-card">
  <a href="{_safe_url(href)}" target="_blank">
    {cover}
    <div class="mini-body">
      <div class="mini-badge">{badge}</div>
      <div class="mini-title">{title}</div>
      <div class="mini-note">{note}</div>
    </div>
  </a>
</div>"""


def _render_browsable_section(
    items: list[dict],
    *,
    section_class: str,
    heading: str,
    tagline: str,
    hero_fn,
    mini_fn,
    accent_style: str = "",
) -> str:
    """A section as a featured hero + a horizontal swipe strip of the rest,
    inside the existing collapsible <details> shell."""
    if not items:
        return ""
    hero = hero_fn(items[0])
    strip = _swipe_strip([mini_fn(it) for it in items[1:]])
    return f"""
<section class="{section_class}"{accent_style}>
  <details class="section-details" open>
    <summary>
      <div class="section-header-toggle">
        <div>
          <h2>{heading}</h2>
          <div class="tagline">{tagline}</div>
        </div>
        <span class="section-chevron">▾</span>
      </div>
    </summary>
    {hero}
    {strip}
  </details>
</section>"""


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


def _music_badge(article: dict) -> str:
    source_name = _esc(article.get("source_name", "Music"))
    genre = _esc((article.get("genre") or "").strip())
    return f"♪ {source_name}" + (f" · {genre}" if genre else "")


def _music_hero(article: dict) -> str:
    """Featured track: album cover + vibe + an inline player when available."""
    title      = _esc(article.get("title", "(no title)"))
    url        = article.get("embed_url") or article.get("url", "#")
    note       = _esc(article.get("vibe_check") or (article.get("snippet") or "").strip())
    cover      = _cover_html(article.get("cover_url", ""), "🎵", hero=True)
    embed_html = _render_music_embed(article.get("embed_url") or "", title)
    embed_block = f'<div style="padding:0 18px 16px;">{embed_html}</div>' if embed_html else ""
    return f"""
<div class="hero-card">
  <a href="{_safe_url(url)}" target="_blank">
    {cover}
    <div class="hero-body">
      <div class="hero-badge">{_music_badge(article)}</div>
      <div class="hero-title">{title}</div>
      <div class="hero-note">{note}</div>
    </div>
  </a>
  {embed_block}
</div>"""


def _music_mini(article: dict) -> str:
    return _mini_card(
        href=article.get("embed_url") or article.get("url", "#"),
        cover=_cover_html(article.get("cover_url", ""), "🎵"),
        badge=_music_badge(article),
        title=_esc(article.get("title", "(no title)")),
        note=_esc(article.get("vibe_check") or (article.get("snippet") or "").strip()),
    )


def _render_morning_soundtrack(articles: list[dict]) -> str:
    return _render_browsable_section(
        articles,
        section_class="soundtrack-section",
        heading="🎵 The Morning Soundtrack",
        tagline="Fresh picks from the music world to set the tone for your day.",
        hero_fn=_music_hero,
        mini_fn=_music_mini,
    )


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


def _good_news_hero(article: dict) -> str:
    return _hero_card(
        href=article.get("url", "#"),
        cover=_cover_html("", "🌿", hero=True),
        badge="🌿 Good News",
        title=_esc(article.get("title", "(no title)")),
        note=_esc(article.get("reason", "")),
    )


def _good_news_mini(article: dict) -> str:
    return _mini_card(
        href=article.get("url", "#"),
        cover=_cover_html("", "🌿"),
        badge=f"🌿 {_esc(article.get('source_name', 'Good News'))}",
        title=_esc(article.get("title", "(no title)")),
        note=_esc(article.get("reason", "")),
    )


def _render_global_silver_linings(articles: list[dict]) -> str:
    return _render_browsable_section(
        articles,
        section_class="goodnews-section",
        heading="🌿 Global Silver Linings",
        tagline="Stories that remind you the world is still full of good.",
        hero_fn=_good_news_hero,
        mini_fn=_good_news_mini,
    )


def _render_discovery_card(article: dict) -> str:
    def _e(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    title      = _e(article.get("title", "(no title)"))
    url        = article.get("url", "#")
    snippet    = _e(article.get("snippet", ""))
    ferns_note = _e(article.get("ferns_note", ""))
    source     = article.get("source_name", "")
    category   = article.get("category", "history")

    if source == "British Museum":
        badge = '<span class="badge badge-museum">🏛 British Museum Archives</span>'
    elif category == "science":
        badge = '<span class="badge badge-lab">🔬 Science</span>'
    else:
        badge = '<span class="badge badge-archives">📜 Archives</span>'

    return f"""
<div class="card discovery-card">
  <details>
    <summary>
      <div class="summary-body">
        <div class="discovery-card-title">{title}</div>
        <div class="summary-desc">{ferns_note}</div>
      </div>
      {badge}
    </summary>
    <div class="card-body">
      <div class="discovery-card-snippet">{snippet}</div>
      <a class="post-link" href="{url}" target="_blank">Read full story →</a>
    </div>
  </details>
</div>"""


def _discovery_hero(article: dict, emoji: str, badge: str) -> str:
    return _hero_card(
        href=article.get("url", "#"),
        cover=_cover_html("", emoji, hero=True),
        badge=badge,
        title=_esc(article.get("title", "(no title)")),
        note=_esc(article.get("ferns_note") or article.get("snippet", "")),
    )


def _discovery_mini(article: dict, emoji: str, badge: str) -> str:
    return _mini_card(
        href=article.get("url", "#"),
        cover=_cover_html("", emoji),
        badge=badge,
        title=_esc(article.get("title", "(no title)")),
        note=_esc(article.get("ferns_note") or article.get("snippet", "")),
    )


def _render_from_the_curators_desk(articles: list[dict]) -> str:
    items = [a for a in articles if a.get("source_name") == "British Museum"]
    return _render_browsable_section(
        items,
        section_class="goodnews-section",
        heading="🏛 From the Curator's Desk",
        tagline="Dispatches from one of the world's great collections.",
        hero_fn=lambda a: _discovery_hero(a, "🏛", "🏛 British Museum"),
        mini_fn=lambda a: _discovery_mini(a, "🏛", "🏛 British Museum"),
    )


def _render_from_the_archives(articles: list[dict]) -> str:
    items = [a for a in articles if a.get("source_name") == "Atlas Obscura"]
    return _render_browsable_section(
        items,
        section_class="goodnews-section",
        heading="📜 From the Archives",
        tagline="Forgotten places, hidden histories, and mysteries that linger.",
        hero_fn=lambda a: _discovery_hero(a, "📜", "📜 Archives"),
        mini_fn=lambda a: _discovery_mini(a, "📜", "📜 Archives"),
    )


def _render_the_laboratory(articles: list[dict]) -> str:
    items = [a for a in articles if a.get("category") == "science"]
    return _render_browsable_section(
        items,
        section_class="goodnews-section",
        heading="🔬 The Laboratory",
        tagline="The science stories that rewire how you see the world.",
        hero_fn=lambda a: _discovery_hero(a, "🔬", "🔬 Science"),
        mini_fn=lambda a: _discovery_mini(a, "🔬", "🔬 Science"),
    )


def _yt_badge_text(video: dict) -> str:
    return "✦ Wildcard" if video.get("is_wildcard") else "▶ YouTube"


def _yt_note(video: dict) -> str:
    return _esc(video.get("why_watch", video.get("description", "")))


def _youtube_hero(video: dict) -> str:
    return _hero_card(
        href=_yt_embed(video.get("video_id", "")),
        cover=_cover_html(_yt_thumbnail(video.get("video_id", "")), "▶", hero=True),
        badge=_yt_badge_text(video),
        title=_esc(video.get("title", "(no title)")),
        note=_yt_note(video),
    )


def _youtube_mini(video: dict) -> str:
    return _mini_card(
        href=_yt_embed(video.get("video_id", "")),
        cover=_cover_html(_yt_thumbnail(video.get("video_id", "")), "▶"),
        badge=_yt_badge_text(video),
        title=_esc(video.get("title", "(no title)")),
        note=_yt_note(video),
    )


def _render_theme(theme: dict, accent: str) -> str:
    name    = theme.get("name", "Untitled")
    tagline = theme.get("tagline", "")
    emoji   = theme.get("emoji", "")
    items   = theme.get("items", [])
    heading = f"{emoji} {name}" if emoji else name

    return _render_browsable_section(
        items,
        section_class="theme-section",
        heading=heading,
        tagline=tagline,
        hero_fn=_youtube_hero,
        mini_fn=_youtube_mini,
        accent_style=f' style="--accent: {accent}"',
    )


def build_html(curated: dict) -> str:
    themes                 = curated.get("themes", [])
    summary                = curated.get("audit_summary", {})
    fetched_at             = curated.get("fetched_at", "")
    morning_soundtrack     = curated.get("morning_soundtrack", [])
    global_silver_linings  = curated.get("global_silver_linings", [])
    discovery_articles     = curated.get("discovery_articles", [])

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
    discovery_count = len(discovery_articles)
    discovery_pill = (
        f'<span class="stat-pill">📜 {discovery_count} Discoveries</span>'
        if discovery_count else ""
    )
    stats_html = "".join([
        f'<span class="stat-pill">▶ {summary.get("youtube_videos", 0)} Videos</span>',
        f'<span class="stat-pill">🗂 {summary.get("themes", len(themes))} Themes</span>',
        music_pill,
        goodnews_pill,
        discovery_pill,
    ])

    # Mood scores first — used both for the spectrum bar and Fern's opening line
    emerald_pct, amber_pct, crimson_pct = _calculate_mood_score(
        themes, global_silver_linings, morning_soundtrack, discovery_articles
    )
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
    curators_desk_html    = _render_from_the_curators_desk(discovery_articles)
    archives_html         = _render_from_the_archives(discovery_articles)
    lab_html              = _render_the_laboratory(discovery_articles)

    logo_html = (
        f'<img src="{FERN_LOGO_URL}" alt="Fern" '
        f'style="display:block;margin:0 auto 20px;max-width:110px;height:auto;">'
        if FERN_LOGO_URL else ""
    )

    edition_html = (
        f'<div class="edition-btn-wrap">'
        f'<a class="edition-btn" href="{EDITION_URL}" target="_blank">▶ Open today\'s full edition →</a>'
        f'</div>'
        if EDITION_URL else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>The Curated Canopy</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
  <style>{_CSS}{_CSS_EXTRA}</style>
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

  {edition_html}

  {fern_greeting_html}

  {mood_score_html}

  {silver_linings_html}

  {curators_desk_html}

  {archives_html}

  {lab_html}

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

    # Fail LOUD (non-zero exit) rather than silently returning — a missing
    # secret must turn the Actions run RED, not look successful.
    if not smtp_host or smtp_host.strip() == "":
        raise SystemExit("ERROR: SMTP_SERVER/SMTP_HOST is empty. Check GitHub Secrets!")
    if not smtp_user:
        raise SystemExit("ERROR: SMTP_USER/EMAIL_USER is empty. Check GitHub Secrets!")
    if not smtp_pass:
        raise SystemExit("ERROR: SMTP_PASS is empty. Check GitHub Secrets!")

    # Try every common naming convention for the recipient list
    raw_to = (
        os.environ.get("EMAIL_TO")
        or os.environ.get("NEWSLETTER_RECIPIENTS")
        or os.environ.get("RECIPIENTS")
        or smtp_user  # last resort: send to the sender address
    )
    if not raw_to or raw_to.strip() == "":
        raise SystemExit("ERROR: No recipient. Set EMAIL_TO (or NEWSLETTER_RECIPIENTS/RECIPIENTS).")
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

    # Companion interactive "full edition" → docs/index.html (GitHub Pages)
    try:
        import webpage
        path = webpage.write_edition(curated)
        print(f"[render] Full edition written → {path}")
    except Exception as exc:
        print(f"[render] WARN — could not build full edition page: {exc}")

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
        return

    # No secrets present. Allow purely-local HTML/edition previews via
    # ALLOW_NO_EMAIL=1; otherwise fail LOUD so a misconfigured CI run goes RED.
    missing = []
    if not (os.environ.get("SMTP_USER") or os.environ.get("EMAIL_USER")):
        missing.append("SMTP_USER/EMAIL_USER")
    if not os.environ.get("SMTP_PASS"):
        missing.append("SMTP_PASS")
    if not (os.environ.get("SMTP_SERVER") or os.environ.get("SMTP_HOST")):
        missing.append("SMTP_SERVER/SMTP_HOST")
    msg = f"[render] EMAIL NOT SENT — missing secrets: {', '.join(missing)}"
    if os.environ.get("ALLOW_NO_EMAIL") == "1":
        print(msg + " (ALLOW_NO_EMAIL=1 — continuing without sending)")
    else:
        raise SystemExit(msg)


if __name__ == "__main__":
    main()
