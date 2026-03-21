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
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR      = Path(__file__).parent
CURATED_FILE  = BASE_DIR / "curated_data.json"
OUTPUT_HTML   = BASE_DIR / "newsletter.html"

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
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
               Helvetica, Arial, sans-serif;
  background: #0f0f11;
  color: #e4e4e7;
  line-height: 1.6;
  padding: 0;
}
a { color: #a78bfa; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Wrapper ─────────────────────────────────────────────── */
.wrapper {
  max-width: 680px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

/* ── Masthead ────────────────────────────────────────────── */
.masthead {
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
  border-radius: 16px;
  padding: 36px 32px;
  margin-bottom: 32px;
  text-align: center;
}
.masthead h1 {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: #fff;
}
.masthead .date {
  color: #c4b5fd;
  font-size: 13px;
  margin-top: 6px;
}
.masthead .stats {
  margin-top: 14px;
  display: flex;
  justify-content: center;
  gap: 18px;
  flex-wrap: wrap;
}
.masthead .stat-pill {
  background: rgba(255,255,255,0.1);
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 12px;
  color: #e0d9ff;
}

/* ── Theme Section ───────────────────────────────────────── */
.theme-section {
  margin-bottom: 36px;
}
.theme-header {
  border-left: 4px solid var(--accent, #7c3aed);
  padding: 10px 16px;
  margin-bottom: 12px;
  background: rgba(124, 58, 237, 0.08);
  border-radius: 0 10px 10px 0;
}
.theme-header h2 {
  font-size: 19px;
  font-weight: 700;
  color: #fff;
}
.theme-header .tagline {
  font-size: 13px;
  color: #a1a1aa;
  margin-top: 2px;
}

/* ── Content Card ────────────────────────────────────────── */
.card {
  background: #18181b;
  border: 1px solid #27272a;
  border-radius: 12px;
  margin-bottom: 10px;
  overflow: hidden;
  transition: border-color 0.15s;
}
.card:hover { border-color: #52525b; }

/* ── <details> / <summary> ───────────────────────────────── */
details { }
summary {
  list-style: none;
  cursor: pointer;
  padding: 14px 16px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  user-select: none;
}
summary::-webkit-details-marker { display: none; }
summary::before {
  content: "▶";
  font-size: 10px;
  color: #71717a;
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
  color: #f4f4f5;
  line-height: 1.4;
}
.summary-desc {
  font-size: 13px;
  color: #a1a1aa;
  margin-top: 3px;
  line-height: 1.5;
}
.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 3px;
}
.badge-reddit  { background: #ff45001a; color: #ff6b35; border: 1px solid #ff450033; }
.badge-youtube { background: #ff00001a; color: #ff4444; border: 1px solid #ff000033; }
.badge-ai      { background: #fbbf2422; color: #fbbf24; border: 1px solid #fbbf2433; }
.badge-wildcard{ background: #10b98122; color: #34d399; border: 1px solid #10b98133; }

/* ── Expanded Content ────────────────────────────────────── */
.card-body {
  padding: 0 16px 16px 16px;
  border-top: 1px solid #27272a;
}
.post-text {
  font-size: 13px;
  color: #d4d4d8;
  margin-top: 14px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
  background: #09090b;
  border-radius: 8px;
  padding: 12px 14px;
  line-height: 1.65;
}
.post-link {
  display: inline-block;
  margin-top: 10px;
  font-size: 12px;
  color: #818cf8;
}

/* ── Image Grid ──────────────────────────────────────────── */
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
  margin-top: 12px;
}
.image-grid img {
  width: 100%;
  height: 130px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #27272a;
}

/* ── YouTube Embed Block ─────────────────────────────────── */
.yt-container {
  margin-top: 14px;
  position: relative;
  display: block;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #27272a;
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
  background: rgba(0,0,0,0.35);
  transition: background 0.15s;
}
.yt-container:hover .yt-play-overlay { background: rgba(0,0,0,0.5); }
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
  margin-bottom: 36px;
}
.soundtrack-header {
  border-left: 4px solid #f472b6;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: rgba(244, 114, 182, 0.08);
  border-radius: 0 10px 10px 0;
}
.soundtrack-header h2 {
  font-size: 19px;
  font-weight: 700;
  color: #fff;
}
.soundtrack-header .tagline {
  font-size: 13px;
  color: #a1a1aa;
  margin-top: 2px;
}
.badge-music {
  background: #f472b61a;
  color: #f472b6;
  border: 1px solid #f472b633;
}
.vibe-check {
  font-size: 12px;
  color: #f472b6;
  margin-top: 6px;
  font-style: italic;
}
.music-listen-btn {
  display: inline-block;
  margin-top: 12px;
  padding: 7px 16px;
  background: rgba(244,114,182,0.12);
  border: 1px solid #f472b633;
  border-radius: 999px;
  color: #f472b6;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}
.music-listen-btn:hover { background: rgba(244,114,182,0.22); }

/* ── Global Silver Linings Section ───────────────────────── */
.goodnews-section {
  margin-bottom: 36px;
}
.goodnews-header {
  border-left: 4px solid #34d399;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: rgba(52, 211, 153, 0.08);
  border-radius: 0 10px 10px 0;
}
.goodnews-header h2 {
  font-size: 19px;
  font-weight: 700;
  color: #fff;
}
.goodnews-header .tagline {
  font-size: 13px;
  color: #a1a1aa;
  margin-top: 2px;
}
.badge-goodnews {
  background: #34d39922;
  color: #34d399;
  border: 1px solid #34d39933;
}

/* ── Footer ──────────────────────────────────────────────── */
.footer {
  text-align: center;
  font-size: 11px;
  color: #52525b;
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid #27272a;
}
"""

# Accent colours cycle per theme section
_ACCENTS = ["#7c3aed", "#0ea5e9", "#f59e0b", "#10b981", "#ec4899"]


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
      <a class="post-link" href="{url}" target="_blank">↗ View on Reddit</a>
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
            f'title="Watch: {title}">'
            f'<img src="{thumb}" alt="{title}" loading="lazy">'
            f'<span class="yt-play-overlay"><span class="yt-play-btn"></span></span>'
            f'</a>'
        )

    if "bandcamp.com/EmbeddedPlayer" in embed_url:
        return (
            f'<iframe class="bc-player" src="{embed_url}" '
            f'seamless title="{title}" loading="lazy" '
            f'style="border:0;width:100%;height:120px;border-radius:8px;'
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

    snippet_html = ""
    if snippet:
        escaped = snippet.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        snippet_html = f'<div class="post-text">{escaped}</div>'

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
      {snippet_html}
      <a class="post-link" href="{url}" target="_blank">↗ Read on {source_name}</a>
    </div>
  </details>
</div>"""


def _render_morning_soundtrack(articles: list[dict]) -> str:
    if not articles:
        return ""

    cards = "".join(_render_music_card(a) for a in articles)

    return f"""
<section class="soundtrack-section">
  <div class="soundtrack-header">
    <h2>The Morning Soundtrack</h2>
    <div class="tagline">Fresh picks from the music world to set the tone for your day.</div>
  </div>
  {cards}
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
      <p style="font-size:13px;color:#d4d4d8;margin-top:14px;line-height:1.6;">{reason}</p>
      <a class="post-link" href="{url}" target="_blank"
         style="margin-top:10px;display:inline-block;">
        ↗ Read Full Story on {source_name}
      </a>
    </div>
  </details>
</div>"""


def _render_global_silver_linings(articles: list[dict]) -> str:
    if not articles:
        return ""
    cards = "".join(_render_good_news_card(a) for a in articles)
    return f"""
<section class="goodnews-section">
  <div class="goodnews-header">
    <h2>Global Silver Linings</h2>
    <div class="tagline">Two stories that remind you the world is still full of good.</div>
  </div>
  {cards}
</section>"""


def _render_theme(theme: dict, accent: str) -> str:
    name    = theme.get("name", "Untitled")
    tagline = theme.get("tagline", "")
    items   = theme.get("items", [])

    cards = []
    for item in items:
        source = item.get("source", "")
        if source in ("youtube", "youtube_trending"):
            cards.append(_render_youtube_card(item))
        else:
            cards.append(_render_reddit_card(item))

    return f"""
<section class="theme-section" style="--accent: {accent}">
  <div class="theme-header">
    <h2>{name}</h2>
    <div class="tagline">{tagline}</div>
  </div>
  {"".join(cards)}
</section>"""


def build_html(curated: dict) -> str:
    themes                 = curated.get("themes", [])
    summary                = curated.get("audit_summary", {})
    fetched_at             = curated.get("fetched_at", "")
    morning_soundtrack     = curated.get("morning_soundtrack", [])
    global_silver_linings  = curated.get("global_silver_linings", [])

    try:
        dt = datetime.datetime.fromisoformat(fetched_at)
        date_str = f"{dt.strftime('%A, %B')} {dt.day} {dt.strftime('%Y · %H:%M')} UTC"
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

    theme_html = "".join(
        _render_theme(theme, _ACCENTS[i % len(_ACCENTS)])
        for i, theme in enumerate(themes)
    )

    soundtrack_html       = _render_morning_soundtrack(morning_soundtrack)
    silver_linings_html   = _render_global_silver_linings(global_silver_linings)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Daily Digest</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="wrapper">

  <div class="masthead">
    <h1>Daily Digest</h1>
    <div class="date">{date_str}</div>
    <div class="stats">{stats_html}</div>
  </div>

  {soundtrack_html}

  {theme_html}

  {silver_linings_html}

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
    smtp_user   = os.environ["EMAIL_USER"]
    smtp_pass   = os.environ["SMTP_PASS"]
    smtp_host   = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port   = int(os.environ.get("SMTP_PORT", "587"))
    recipients_raw = os.environ.get("NEWSLETTER_RECIPIENTS", smtp_user)
    recipients  = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
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

    # Send only when SMTP credentials are present
    if os.environ.get("EMAIL_USER") and os.environ.get("SMTP_PASS"):
        fetched_at = curated.get("fetched_at", "")
        try:
            dt = datetime.datetime.fromisoformat(fetched_at)
            label = f"{dt.strftime('%b')} {dt.day}"
        except Exception:
            label = "Today"
        send_email(html, subject=f"Daily Digest · {label}")
    else:
        print("[render] EMAIL_USER / SMTP_PASS not set — skipping send.")


if __name__ == "__main__":
    main()
