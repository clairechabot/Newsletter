"""
Newsletter — Companion "full edition" web page (GitHub Pages)
------------------------------------------------------------
Reads curated_data.json → writes docs/index.html, a self-contained interactive
page the email links out to. Real JavaScript here (unlike email): a music
carousel with arrows + album covers, section tabs, and a client-side genre
filter over the music items.

Run standalone:  python webpage.py
Or call build_edition(curated) from renderer.py.
"""
from __future__ import annotations

import os
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR     = Path(__file__).parent
CURATED_FILE = BASE_DIR / "curated_data.json"
DOCS_DIR     = BASE_DIR / "docs"
EDITION_HTML = DOCS_DIR / "index.html"


def _payload(curated: dict) -> dict:
    """Flatten curated data into the shape the page's JS consumes."""
    videos: list[dict] = []
    for theme in curated.get("themes", []):
        for v in theme.get("items", []):
            videos.append({
                "title": v.get("title", ""),
                "note": v.get("why_watch", v.get("description", "")),
                "video_id": v.get("video_id", ""),
                "channel": v.get("channel_title", ""),
                "theme": theme.get("name", ""),
            })

    music = [{
        "title": m.get("title", ""),
        "note": m.get("vibe_check") or (m.get("snippet") or ""),
        "url": m.get("embed_url") or m.get("url", "#"),
        "cover": m.get("cover_url", ""),
        "genre": m.get("genre", ""),
        "source": m.get("source_name", ""),
    } for m in curated.get("morning_soundtrack", [])]

    good_news = [{
        "title": g.get("title", ""),
        "note": g.get("reason", ""),
        "url": g.get("url", "#"),
        "source": g.get("source_name", ""),
    } for g in curated.get("global_silver_linings", [])]

    discovery = [{
        "title": d.get("title", ""),
        "note": d.get("ferns_note") or d.get("snippet", ""),
        "url": d.get("url", "#"),
        "source": d.get("source_name", ""),
        "category": d.get("category", "history"),
    } for d in curated.get("discovery_articles", [])]

    return {
        "is_am": curated.get("is_am_email", False),
        "greeting": curated.get("fern_data", {}).get("greeting", ""),
        "music": music,
        "videos": videos,
        "good_news": good_news,
        "discovery": discovery,
    }


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Curated Canopy — Full Edition</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif; background:#F9F7F2;
    color:#2C3E50; line-height:1.6; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:28px 18px 64px; }}
  header {{ text-align:center; margin-bottom:24px; }}
  .brand {{ font-size:40px; }}
  h1 {{ font-family:'Playfair Display',Georgia,serif; font-size:30px; color:#5D6D7E; margin:6px 0; }}
  .greeting {{ color:#7A8794; font-style:italic; max-width:640px; margin:8px auto 0; }}
  .date {{ color:#A9A39A; font-size:13px; margin-top:6px; }}
  /* Tabs */
  .tabs {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin:24px 0; }}
  .tab {{ padding:9px 18px; border-radius:24px; border:1px solid #D9D3C7; background:#fff;
    cursor:pointer; font-weight:bold; font-size:14px; color:#5D6D7E; }}
  .tab.active {{ background:#5D6D7E; color:#fff; border-color:#4A5763; }}
  .panel {{ display:none; }}
  .panel.active {{ display:block; }}
  /* Genre filter */
  .genres {{ display:flex; flex-wrap:wrap; gap:6px; justify-content:center; margin-bottom:18px; }}
  .genre {{ padding:5px 12px; border-radius:18px; border:1px solid #D9D3C7; background:#fff;
    cursor:pointer; font-size:12px; color:#7A8794; }}
  .genre.active {{ background:#87A878; color:#fff; border-color:#6E9162; }}
  /* Carousel */
  .carousel {{ position:relative; }}
  .track {{ display:flex; gap:16px; overflow-x:auto; scroll-behavior:smooth;
    -webkit-overflow-scrolling:touch; padding:6px 2px 16px; scroll-snap-type:x mandatory; }}
  .arrow {{ position:absolute; top:38%; transform:translateY(-50%); z-index:5; border:none;
    background:rgba(93,109,126,.92); color:#fff; width:40px; height:40px; border-radius:50%;
    font-size:18px; cursor:pointer; }}
  .arrow.left {{ left:-6px; }} .arrow.right {{ right:-6px; }}
  /* Cards */
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:16px; }}
  .card {{ flex:0 0 auto; width:230px; scroll-snap-align:start; background:#fff;
    border:1px solid #E0E0E0; border-radius:14px; overflow:hidden; }}
  .grid .card {{ width:auto; }}
  .card a {{ color:#2C3E50; text-decoration:none; display:block; }}
  .cover {{ width:100%; height:200px; object-fit:cover; display:block; background:#EFECE4; }}
  .cover-tile {{ width:100%; height:150px; display:flex; align-items:center; justify-content:center;
    font-size:54px; background:linear-gradient(135deg,#EFE9DD,#E3EDE0); }}
  .body {{ padding:12px 14px 16px; }}
  .badge {{ font-size:10px; color:#87A878; font-weight:bold; text-transform:uppercase; letter-spacing:.4px; }}
  .title {{ font-weight:bold; font-size:15px; margin:5px 0; line-height:1.35; }}
  .note {{ font-size:13px; color:#7A8794; }}
  .empty {{ text-align:center; color:#A9A39A; padding:40px 0; }}
  footer {{ text-align:center; color:#A9A39A; font-size:12px; margin-top:40px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">🍞🌿🐚</div>
    <h1>The Curated Canopy</h1>
    <div class="greeting" id="greeting"></div>
    <div class="date">{date_str}</div>
  </header>

  <div class="tabs" id="tabs"></div>

  <div class="panel active" data-panel="music">
    <div class="genres" id="genres"></div>
    <div class="carousel">
      <button class="arrow left"  onclick="slide(-1)">‹</button>
      <div class="track" id="music-track"></div>
      <button class="arrow right" onclick="slide(1)">›</button>
    </div>
  </div>
  <div class="panel" data-panel="videos"><div class="grid" id="videos-grid"></div></div>
  <div class="panel" data-panel="good_news"><div class="grid" id="good_news-grid"></div></div>
  <div class="panel" data-panel="discovery"><div class="grid" id="discovery-grid"></div></div>

  <footer>Generated automatically · Curated by Claude · Fern | The Morning Crust</footer>
</div>

<script id="data" type="application/json">{data_json}</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
document.getElementById('greeting').textContent = DATA.greeting || '';

const PANELS = [
  {{key:'music',     label:'🎵 Music'}},
  {{key:'videos',    label:'▶ Watch'}},
  {{key:'good_news', label:'🌿 Good News'}},
  {{key:'discovery', label:'📜 Discovery'}},
];
const tabs = document.getElementById('tabs');
PANELS.forEach((p, i) => {{
  const b = document.createElement('div');
  b.className = 'tab' + (i === 0 ? ' active' : '');
  b.textContent = p.label;
  b.onclick = () => selectTab(p.key, b);
  tabs.appendChild(b);
}});
function selectTab(key, btn) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.panel').forEach(pl =>
    pl.classList.toggle('active', pl.dataset.panel === key));
}}

function esc(s) {{ const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }}
function coverHTML(url, emoji) {{
  return url ? `<img class="cover" src="${{esc(url)}}" alt="">`
             : `<div class="cover-tile">${{emoji}}</div>`;
}}
function cardHTML(it, emoji) {{
  return `<div class="card"><a href="${{esc(it.url)}}" target="_blank">${{coverHTML(it.cover, emoji)}}`
    + `<div class="body"><div class="badge">${{esc(it.source || it.theme || '')}}</div>`
    + `<div class="title">${{esc(it.title)}}</div><div class="note">${{esc(it.note)}}</div></div></a></div>`;
}}

// Grids
function fillGrid(id, items, emoji) {{
  const el = document.getElementById(id);
  el.innerHTML = items.length
    ? items.map(it => cardHTML(it, emoji)).join('')
    : '<div class="empty">Nothing here in this edition.</div>';
}}
fillGrid('videos-grid', DATA.videos.map(v => ({{...v, url:'https://www.youtube.com/watch?v=' + v.video_id, cover:'https://img.youtube.com/vi/' + v.video_id + '/hqdefault.jpg'}})), '▶');
fillGrid('good_news-grid', DATA.good_news, '🌿');
fillGrid('discovery-grid', DATA.discovery, '📜');

// Music carousel + genre filter
const GENRES = [...new Set(DATA.music.map(m => (m.genre || '').trim()).filter(Boolean))];
let activeGenre = null;
const genresEl = document.getElementById('genres');
function renderGenres() {{
  const all = [{{g:null, label:'All'}}].concat(GENRES.map(g => ({{g, label:g}})));
  genresEl.innerHTML = all.map(x =>
    `<div class="genre ${{x.g === activeGenre ? 'active' : ''}}" data-g="${{esc(x.g || '')}}">${{esc(x.label)}}</div>`
  ).join('');
  genresEl.querySelectorAll('.genre').forEach(el => el.onclick = () => {{
    activeGenre = el.dataset.g || null; renderGenres(); renderMusic();
  }});
}}
function renderMusic() {{
  const track = document.getElementById('music-track');
  const items = activeGenre
    ? DATA.music.filter(m => (m.genre || '').trim() === activeGenre)
    : DATA.music;
  track.innerHTML = items.length
    ? items.map(it => cardHTML(it, '🎵')).join('')
    : '<div class="empty">No tracks match that genre in this edition.</div>';
}}
function slide(dir) {{
  document.getElementById('music-track').scrollBy({{left: dir * 260, behavior:'smooth'}});
}}
renderGenres();
renderMusic();
</script>
</body>
</html>"""


def build_edition(curated: dict) -> str:
    fetched_at = curated.get("fetched_at", "")
    try:
        dt = datetime.datetime.fromisoformat(fetched_at).astimezone(ZoneInfo("Europe/Zurich"))
        date_str = f"{dt.strftime('%A, %B')} {dt.day}, {dt.strftime('%Y')} · {dt.strftime('%H:%M')}"
    except Exception:
        date_str = fetched_at
    data_json = json.dumps(_payload(curated))
    return _PAGE.format(date_str=date_str, data_json=data_json)


def write_edition(curated: dict) -> Path:
    DOCS_DIR.mkdir(exist_ok=True)
    EDITION_HTML.write_text(build_edition(curated), encoding="utf-8")
    return EDITION_HTML


def main() -> None:
    if not CURATED_FILE.exists():
        raise FileNotFoundError(f"{CURATED_FILE} not found. Run fetcher.py first.")
    curated = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
    path = write_edition(curated)
    print(f"[webpage] Full edition written → {path}")


if __name__ == "__main__":
    main()
