"""
Newsletter — Companion "full edition" web page (GitHub Pages)
------------------------------------------------------------
Reads curated_data.json -> writes docs/index.html, a self-contained interactive
page the email links out to: a Botanical-Editorial magazine with a masthead,
Fern's note, a hero feature, sticky section tabs, a music genre filter, and
four browsable sections rendered with large imagery.

Run standalone:  python webpage.py
Or call write_edition(curated) from renderer.py.
"""
from __future__ import annotations

import json
import re
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR     = Path(__file__).parent
CURATED_FILE = BASE_DIR / "curated_data.json"
DOCS_DIR     = BASE_DIR / "docs"
EDITION_HTML = DOCS_DIR / "index.html"
EDITIONS_DIR = DOCS_DIR / "editions"
ARCHIVE_HTML = DOCS_DIR / "archive.html"
GROVE_HTML   = DOCS_DIR / "grove.html"
GROVE_JSON   = DOCS_DIR / "grove.json"

# The fixed mood vocabulary used across The Grove. Claude tags each item with
# 1–3 of these at build time (see curator.tag_grove_moods); the page exposes
# them as filter chips. Keep this list in sync with curator.GROVE_MOODS.
GROVE_MOODS: list[str] = [
    "cozy", "curious", "uplifting", "wonder",
    "hopeful", "energizing", "reflective", "playful",
    "Romantic", "Crafty / Creative", "Cheer Up!", "Calm Down",
    "Energize", "Inspire",
]


def _dedash(s: str) -> str:
    """Remove em/en dashes from Fern's prose (reads less machine-made)."""
    if not s:
        return s
    s = s.replace(" — ", ", ").replace(" – ", ", ")
    s = s.replace("\u2014", ", ").replace("\u2013", "-")
    while ", ," in s:
        s = s.replace(", ,", ",")
    return s.strip()


# Running issue number, like a real periodical ("No. 248").
# Set this to the date of your VERY FIRST edition. Editions go out twice a day,
# so the number climbs by 2 each day on its own — no manual tracking needed.
CANOPY_LAUNCH = datetime.date(2025, 1, 1)

# Where Fern's garden lives — shown in the "From the Garden" eyebrow.
import os
GARDEN_LOCALE = os.environ.get("GARDEN_LOCALE", "Zürich")


def _edition_no(dt: datetime.datetime, is_am: bool) -> int:
    days = (dt.date() - CANOPY_LAUNCH).days
    return max(1, days * 2 + (0 if is_am else 1) + 1)


def _payload(curated: dict) -> dict:
    """Flatten curated data into the shape the page's JS consumes."""
    videos: list[dict] = []
    for theme in curated.get("themes", []):
        for v in theme.get("items", []):
            videos.append({
                "title":    v.get("title", ""),
                "note":     _dedash(v.get("why_watch", v.get("description", ""))),
                "video_id": v.get("video_id", ""),
                "channel":  v.get("channel_title", ""),
                "wild":     bool(v.get("is_wildcard", False)),
            })

    music = [{
        "title":  m.get("title", ""),
        "note":   _dedash(m.get("vibe_check") or (m.get("snippet") or "")),
        "url":    m.get("embed_url") or m.get("url", "#"),
        "cover":  m.get("cover_url", ""),
        "genre":  (m.get("genre") or "").strip(),
        "source": m.get("source_name", ""),
    } for m in curated.get("morning_soundtrack", [])]

    good_news = [{
        "title":  g.get("title", ""),
        "note":   _dedash(g.get("reason", "")),
        "url":    g.get("url", "#"),
        "cover":  g.get("cover_url", ""),
        "source": g.get("source_name", ""),
    } for g in curated.get("global_silver_linings", [])]

    discovery = [{
        "title":  d.get("title", ""),
        "note":   _dedash(d.get("ferns_note") or d.get("snippet", "")),
        "url":    d.get("url", "#"),
        "cover":  d.get("cover_url", ""),
        "source": d.get("source_name", ""),
        "cat":    (d.get("category", "history") or "history").title(),
    } for d in curated.get("discovery_articles", [])]

    fr = curated.get("featured_read") or {}
    featured_read = {
        "title":  fr.get("title", ""),
        "note":   _dedash(fr.get("blurb") or fr.get("snippet", "")),
        "url":    fr.get("url", "#"),
        "cover":  fr.get("cover_url", ""),
        "source": fr.get("source_name", ""),
    } if fr.get("title") else None

    g = curated.get("garden_note") or {}
    garden = {
        "note":        _dedash(g.get("note", "")),
        "in_season":   [s for s in (g.get("in_season") or []) if s],
        "sky_tonight": _dedash(g.get("sky_tonight", "")),
        "moon_label":  g.get("moon_label", ""),
    } if g.get("note") else None

    return {
        "is_am":    curated.get("is_am_email", False),
        "greeting": _dedash(curated.get("fern_data", {}).get("greeting", "")),
        "garden":    garden,
        "featured_read": featured_read,
        "music":     music,
        "videos":    videos,
        "good_news": good_news,
        "discovery": discovery,
    }


# Token-replaced (NOT str.format) so CSS/JS braces stay single.
_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Curated Canopy — Full Edition</title>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#F4EEE2;--paper-deep:#E9E1D1;--surface:#FBF7EE;
    --ink:#20271F;--ink-soft:#4A4A3E;--ink-mute:#7C7565;
    --forest:#2C3A2B;--moss:#6E7B4B;--moss-deep:#55603A;
    --clay:#A85A36;--clay-deep:#8E4A2C;--line:#D9CFBC;--line-soft:#E5DCCB;--radius:12px;
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  html{scroll-behavior:smooth;}
  body{font-family:var(--sans);background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;}
  img{max-width:100%;display:block;}
  a{color:inherit;text-decoration:none;}
  .wrap{max-width:1120px;margin:0 auto;padding:0 40px;}
  .eyebrow{font-size:11px;font-weight:600;letter-spacing:0.22em;text-transform:uppercase;color:var(--moss-deep);}

  .img,.photo{position:relative;width:100%;overflow:hidden;}
  .img{background:linear-gradient(135deg,rgba(255,255,255,0.18),rgba(255,255,255,0) 60%),repeating-linear-gradient(135deg,rgba(32,39,31,0.035) 0 2px,transparent 2px 11px),linear-gradient(160deg,var(--ph-a,#C9CBB0),var(--ph-b,#9DA882));border:1px solid rgba(32,39,31,0.10);}
  .img::after{content:attr(data-label);position:absolute;left:12px;bottom:11px;font-family:ui-monospace,Menlo,monospace;font-size:9px;letter-spacing:0.12em;text-transform:uppercase;color:rgba(255,255,255,0.92);background:rgba(32,39,31,0.32);padding:3px 8px;border-radius:100px;}
  .img.t0{--ph-a:#D9CFB8;--ph-b:#B3A684;} .img.t1{--ph-a:#D8B59B;--ph-b:#B0764F;}
  .img.t2{--ph-a:#B7C29A;--ph-b:#7E8C5A;} .img.t3{--ph-a:#7E8C6E;--ph-b:#46553E;}
  .photo{border:1px solid rgba(32,39,31,0.10);}
  .photo img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;}
  .play{position:absolute;inset:0;margin:auto;width:60px;height:60px;border-radius:50%;border:1.5px solid rgba(255,255,255,0.92);background:rgba(32,39,31,0.16);display:flex;align-items:center;justify-content:center;transition:transform .25s ease,background .25s ease;}
  .play::after{content:"";margin-left:3px;border-style:solid;border-width:9px 0 9px 15px;border-color:transparent transparent transparent rgba(255,255,255,0.95);}

  .cover{text-align:center;padding:60px 40px 40px;}
  .cover .eyebrow{color:var(--clay-deep);margin-bottom:22px;}
  .cover h1{font-family:var(--serif);font-weight:500;font-size:clamp(46px,8vw,84px);line-height:0.98;letter-spacing:-0.015em;color:var(--forest);}
  .cover .tagline{font-family:var(--serif);font-style:italic;font-size:clamp(17px,2.4vw,22px);color:var(--ink-soft);margin-top:18px;}
  .cover .meta{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:16px;margin-top:30px;font-size:11.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--ink-mute);}
  .cover .meta .dot{width:3px;height:3px;border-radius:50%;background:var(--clay);}

  .fern{max-width:720px;margin:0 auto;padding:0 40px 8px;display:flex;gap:22px;align-items:flex-start;}
  .monogram{flex-shrink:0;width:52px;height:52px;border-radius:50%;border:1px solid var(--moss);color:var(--moss-deep);font-family:var(--serif);font-size:24px;display:flex;align-items:center;justify-content:center;margin-top:6px;}
  .fern .eyebrow{margin-bottom:9px;}
  .fern p{font-family:var(--serif);font-size:20px;line-height:1.6;color:var(--ink-soft);}
  .fern .sign{font-style:italic;color:var(--forest);}

  .almanac{max-width:720px;margin:0 auto;padding:18px 40px 4px;}
  .almanac .eyebrow{color:var(--moss-deep);margin-bottom:11px;}
  .almanac p{font-family:var(--serif);font-size:18px;line-height:1.6;color:var(--ink-soft);}
  .almanac-foot{display:flex;flex-wrap:wrap;align-items:center;gap:12px 22px;margin-top:18px;}
  .almanac-meta{display:flex;align-items:center;gap:12px;font-size:11.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-mute);}
  .almanac-meta .dot{width:3px;height:3px;border-radius:50%;background:var(--clay);}
  .chip.static{cursor:default;}

  .hero{margin-top:52px;}
  .hero-grid,.feature-read{display:grid;border-top:1px solid var(--line);border-bottom:1px solid var(--line);}
  .hero-grid{grid-template-columns:1.5fr 1fr;}
  .feature-read{grid-template-columns:1fr 1.5fr;margin-top:8px;}
  .hero-grid .cell,.feature-read .cell{min-height:420px;border-right:1px solid var(--line);}
  .feature-read .cell{min-height:340px;}
  .hero-text{padding:44px 48px;display:flex;flex-direction:column;justify-content:center;}
  .hero-text .eyebrow{color:var(--clay-deep);margin-bottom:18px;}
  .hero-text h2{font-family:var(--serif);font-weight:500;font-size:clamp(28px,3.4vw,40px);line-height:1.1;letter-spacing:-0.01em;color:var(--forest);}
  .hero-text p{font-size:16.5px;color:var(--ink-soft);margin-top:18px;max-width:42ch;}
  .textlink{display:inline-flex;align-items:center;gap:8px;margin-top:26px;font-size:13px;font-weight:600;letter-spacing:0.04em;color:var(--clay-deep);}
  .textlink .arr{transition:transform .2s ease;} .textlink:hover .arr{transform:translateX(4px);}

  .tabbar{position:sticky;top:0;z-index:50;background:rgba(244,238,226,0.86);backdrop-filter:blur(10px) saturate(120%);border-bottom:1px solid var(--line);margin-top:56px;}
  .tabbar-inner{max-width:1120px;margin:0 auto;padding:0 40px;display:flex;align-items:center;gap:28px;height:60px;}
  .tabmark{font-family:var(--serif);font-size:18px;color:var(--forest);white-space:nowrap;opacity:0;width:0;overflow:hidden;transition:opacity .3s ease;}
  .tabbar.stuck .tabmark{opacity:1;width:auto;margin-right:8px;}
  .tabs{display:flex;gap:4px;flex:1;overflow-x:auto;scrollbar-width:none;}
  .tabs::-webkit-scrollbar{display:none;}
  .tab{position:relative;white-space:nowrap;cursor:pointer;padding:19px 14px;font-size:13px;font-weight:600;letter-spacing:0.04em;color:var(--ink-mute);background:none;border:0;font-family:var(--sans);transition:color .2s ease;}
  .tab:hover{color:var(--ink);} .tab.active{color:var(--forest);}
  .tab .ix{font-family:var(--serif);font-size:11px;color:var(--moss);margin-right:6px;font-weight:400;}
  .tab::after{content:"";position:absolute;left:14px;right:14px;bottom:-1px;height:2px;background:var(--clay);transform:scaleX(0);transition:transform .25s ease;}
  .tab.active::after{transform:scaleX(1);}

  .panel{display:none;padding:56px 0 20px;}
  .panel.active{display:block;animation:fade .4s ease;}
  @keyframes fade{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:none;}}
  @media (prefers-reduced-motion:reduce){.panel.active{animation:none;}}
  .sec-head{margin-bottom:34px;}
  .sec-head .eyebrow{display:flex;align-items:center;gap:16px;color:var(--clay-deep);}
  .sec-head .eyebrow::after{content:"";flex:1;height:1px;background:var(--line);}
  .sec-head h3{font-family:var(--serif);font-weight:500;font-size:clamp(30px,4vw,44px);line-height:1.05;letter-spacing:-0.01em;color:var(--forest);margin-top:16px;}
  .sec-head .lede{font-family:var(--serif);font-style:italic;font-size:18px;color:var(--ink-mute);margin-top:10px;max-width:54ch;}

  .chips{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:30px;}
  .chip{cursor:pointer;font-family:var(--sans);font-size:12px;font-weight:600;letter-spacing:0.03em;padding:8px 16px;border-radius:100px;border:1px solid var(--line);background:var(--surface);color:var(--ink-soft);transition:all .18s ease;}
  .chip:hover{border-color:var(--moss);color:var(--forest);} .chip.active{background:var(--forest);border-color:var(--forest);color:var(--paper);}

  /* Horizontal swipe carousels — one scroll-snapping row per section. */
  .grid{display:flex;gap:26px;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding-bottom:16px;scrollbar-width:thin;scrollbar-color:var(--line) transparent;}
  .grid::-webkit-scrollbar{height:8px;}
  .grid::-webkit-scrollbar-thumb{background:var(--line);border-radius:100px;}
  .grid::-webkit-scrollbar-track{background:transparent;}
  .card{display:flex;flex-direction:column;flex:0 0 auto;scroll-snap-align:start;}
  .grid.music .card{width:220px;}
  .grid.watch .card{width:360px;}
  .grid.read .card{width:320px;}
  .card .cv{border-radius:var(--radius);}
  .card.music .cv{aspect-ratio:1/1;} .card.watch .cv{aspect-ratio:16/9;} .card.read .cv{aspect-ratio:3/2;}
  .card .cv .play{width:52px;height:52px;} .card:hover .cv .play{transform:scale(1.06);background:rgba(32,39,31,0.32);}
  .card .meta-line{display:flex;align-items:center;gap:10px;margin-top:16px;font-size:10.5px;font-weight:600;letter-spacing:0.13em;text-transform:uppercase;color:var(--moss-deep);}
  .card .meta-line .sep{color:var(--line);} .card .meta-line .dur{margin-left:auto;color:var(--ink-mute);letter-spacing:0.08em;}
  .card h4{font-family:var(--serif);font-weight:500;font-size:21px;line-height:1.2;color:var(--forest);margin-top:9px;letter-spacing:-0.005em;}
  .card.music h4{font-size:19px;}
  .card .note{font-size:14.5px;color:var(--ink-soft);margin-top:8px;line-height:1.55;}
  .card .go{margin-top:14px;font-size:12px;font-weight:600;letter-spacing:0.04em;color:var(--clay-deep);display:inline-flex;align-items:center;gap:7px;}
  .card .go .arr{transition:transform .2s ease;} .card:hover .go .arr{transform:translateX(4px);}
  .badge{font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;padding:3px 9px;border-radius:100px;border:1px solid var(--line);color:var(--moss-deep);}
  .empty{color:var(--ink-mute);font-style:italic;font-family:var(--serif);padding:30px 0;}

  footer{margin-top:80px;border-top:1px solid var(--line);padding:50px 40px 60px;text-align:center;}
  footer .fmark{font-family:var(--serif);font-size:26px;color:var(--forest);}
  footer .ftag{font-family:var(--serif);font-style:italic;color:var(--ink-mute);margin-top:8px;}
  footer .links{margin-top:22px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-mute);display:flex;gap:18px;justify-content:center;flex-wrap:wrap;}
  footer .links a{color:var(--ink-soft);}

  @media (max-width:820px){
    .hero-grid,.feature-read{grid-template-columns:1fr;}
    .hero-grid .cell,.feature-read .cell{border-right:0;border-bottom:1px solid var(--line);min-height:280px;}
    .feature-read .read-cover{order:-1;}
    .hero-text{padding:34px 0;}
  }
  @media (max-width:600px){
    .wrap,.tabbar-inner{padding-left:22px;padding-right:22px;}
    .cover{padding:44px 22px 30px;} .fern{padding:0 22px 8px;gap:16px;} .fern p{font-size:18px;}
    .almanac{padding:14px 22px 4px;} .almanac p{font-size:16.5px;}
    .hero{margin-top:36px;} .panel{padding-top:40px;} .grid{gap:18px;}
    .grid.music .card{width:160px;}
    .grid.watch .card{width:280px;}
    .grid.read .card{width:260px;}
    .tabbar-inner{gap:0;} .tab{padding:19px 12px;}
  }
</style>
</head>
<body>
  <header class="cover">
    <div class="eyebrow">__EDITION_LABEL__ &nbsp;&middot;&nbsp; __ISSUE____DATE_STR__</div>
    <h1>The Curated Canopy</h1>
    <div class="tagline">Human stories, good news &amp; the natural world</div>
    <div class="meta" id="meta"></div>
  </header>

  <section class="fern" id="fern" style="display:none;">
    <div class="monogram">F</div>
    <div>
      <div class="eyebrow">A note from Fern</div>
      <p><span id="greeting"></span> <span class="sign">Yours, Fern</span></p>
    </div>
  </section>

  <section class="almanac" id="almanac" style="display:none;">
    <div class="eyebrow">From the Garden &middot; __GARDEN_LOCALE__</div>
    <p id="garden-note"></p>
    <div class="almanac-foot">
      <div class="chips" id="garden-season"></div>
      <div class="almanac-meta" id="garden-meta"></div>
    </div>
  </section>

  <div class="wrap hero" id="hero-wrap" style="display:none;">
    <a class="hero-grid" id="hero" href="#"></a>
  </div>

  <div class="wrap" id="read-wrap" style="display:none;">
    <a class="feature-read" id="read" href="#" target="_blank"></a>
  </div>

  <nav class="tabbar" id="tabbar">
    <div class="tabbar-inner">
      <span class="tabmark">Canopy</span>
      <div class="tabs" id="tabs"></div>
    </div>
  </nav>

  <main class="wrap">
    <section class="panel active" data-panel="music">
      <div class="sec-head"><div class="eyebrow">Section One</div><h3>The Morning Soundtrack</h3>
        <div class="lede">Fresh picks from the music world to set the tone for your day.</div></div>
      <div class="chips" id="genres"></div>
      <div class="grid music" id="music-grid"></div>
    </section>
    <section class="panel" data-panel="watch">
      <div class="sec-head"><div class="eyebrow">Section Two</div><h3>Worth Watching</h3>
        <div class="lede">Long, patient films for when you have a little time to spend.</div></div>
      <div class="grid watch" id="watch-grid"></div>
    </section>
    <section class="panel" data-panel="good_news">
      <div class="sec-head"><div class="eyebrow">Section Three</div><h3>Global Silver Linings</h3>
        <div class="lede">Stories that remind you the world is still full of good.</div></div>
      <div class="grid read" id="good_news-grid"></div>
    </section>
    <section class="panel" data-panel="discovery">
      <div class="sec-head"><div class="eyebrow">Section Four</div><h3>From the Archives</h3>
        <div class="lede">Forgotten places, hidden histories, and the science that rewires how you see the world.</div></div>
      <div class="grid read" id="discovery-grid"></div>
    </section>
  </main>

  <footer>
    <div class="fmark">The Curated Canopy</div>
    <div class="ftag">Gathered twice daily by Fern</div>
    <div class="links"><a href="#">About</a><a href="./archive.html">The Archive</a><a href="./grove.html">The Grove</a><a href="#">Preferences</a><a href="#">Unsubscribe</a></div>
  </footer>

<script id="data" type="application/json">__DATA_JSON__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const $ = (s,r=document)=>r.querySelector(s);
const ARR = '<span class="arr">&rarr;</span>';
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function safeUrl(u){try{const p=new URL(u,location.href);return ['http:','https:','mailto:'].includes(p.protocol)?p.href:'#';}catch(e){return '#';}}
function ytThumb(id){return 'https://img.youtube.com/vi/'+id+'/hqdefault.jpg';}
function ytWatch(id){return 'https://www.youtube.com/watch?v='+id;}

// cover: real image when present, else a toned placeholder tile
function cover(url,tone,label,play){
  const p = play?'<span class="play"></span>':'';
  if(url) return '<div class="cv photo"><img src="'+esc(safeUrl(url))+'" alt="" loading="lazy">'+p+'</div>';
  return '<div class="cv img t'+tone+'" data-label="'+label+'">'+p+'</div>';
}

// Masthead meta + Fern note
(function(){
  const bits=[];
  bits.push(DATA.is_am?'Gathered at dawn':'Gathered at dusk');
  if(DATA.music.length) bits.push(DATA.music.length+' tracks');
  if(DATA.videos.length) bits.push(DATA.videos.length+' films');
  const extra=DATA.good_news.length+DATA.discovery.length;
  if(extra) bits.push(extra+' stories &amp; finds');
  $('#meta').innerHTML = bits.map((b,i)=>(i?'<span class="dot"></span>':'')+'<span>'+b+'</span>').join('');
  if(DATA.greeting){ $('#greeting').textContent = DATA.greeting; $('#fern').style.display=''; }
})();

// From the Garden almanac
(function(){
  const g = DATA.garden; if(!g || !g.note) return;
  $('#garden-note').textContent = g.note;
  const season=(g.in_season||[]);
  $('#garden-season').innerHTML = season.map(s=>'<span class="chip static">'+esc(s)+'</span>').join('');
  const meta=[]; if(g.moon_label) meta.push(g.moon_label); if(g.sky_tonight) meta.push(g.sky_tonight);
  $('#garden-meta').innerHTML = meta.map((b,i)=>(i?'<span class="dot"></span>':'')+'<span>'+esc(b)+'</span>').join('');
  $('#almanac').style.display='';
})();

// Hero feature = first video
(function(){
  const v = DATA.videos[0]; if(!v) return;
  const kick = "Today's opening" + (v.channel?' &nbsp;&middot;&nbsp; '+esc(v.channel):'');
  $('#hero').href = v.video_id?esc(safeUrl(ytWatch(v.video_id))):'#';
  $('#hero').innerHTML =
    '<div class="cell">'+(v.video_id
        ? '<div class="photo" style="height:100%"><img src="'+esc(safeUrl(ytThumb(v.video_id)))+'" alt=""><span class="play"></span></div>'
        : '<div class="img t3" data-label="Video still" style="height:100%"><span class="play"></span></div>')+'</div>'
    + '<div class="hero-text"><div class="eyebrow">'+kick+'</div><h2>'+esc(v.title)+'</h2>'
    + '<p>'+esc(v.note)+'</p><span class="textlink">Watch the film '+ARR+'</span></div>';
  $('#hero-wrap').style.display='';
})();

// One Good Read = a single featured essay
(function(){
  const r = DATA.featured_read; if(!r || !r.title) return;
  $('#read').href = esc(safeUrl(r.url));
  $('#read').innerHTML =
    '<div class="cell read-cover">'+(r.cover
        ? '<div class="photo" style="height:100%"><img src="'+esc(safeUrl(r.cover))+'" alt="" loading="lazy"></div>'
        : '<div class="img t1" data-label="One Good Read" style="height:100%"></div>')+'</div>'
    + '<div class="hero-text"><div class="eyebrow">One Good Read'+(r.source?' &nbsp;&middot;&nbsp; '+esc(r.source):'')+'</div>'
    + '<h2>'+esc(r.title)+'</h2><p>'+esc(r.note)+'</p>'
    + '<span class="textlink">Read the essay '+ARR+'</span></div>';
  $('#read-wrap').style.display='';
})();

// Tabs
const TABS=[{k:'music',l:'Soundtrack'},{k:'watch',l:'Watch'},{k:'good_news',l:'Good News'},{k:'discovery',l:'Archives'}];
const tabsEl=$('#tabs');
TABS.forEach((t,i)=>{
  const b=document.createElement('button');
  b.className='tab'+(i===0?' active':'');
  b.innerHTML='<span class="ix">0'+(i+1)+'</span>'+t.l;
  b.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.dataset.panel===t.k));
    const top=$('#tabbar').getBoundingClientRect().top+window.scrollY;
    if(window.scrollY>top) window.scrollTo({top:top,behavior:'smooth'});
  };
  tabsEl.appendChild(b);
});

// Music + genre filter
const GENRES=[...new Set(DATA.music.map(m=>m.genre).filter(Boolean))];
let activeGenre=null;
function renderGenres(){
  const all=[{g:null,l:'All'}].concat(GENRES.map(g=>({g,l:g})));
  $('#genres').innerHTML=all.map(x=>'<button class="chip'+(x.g===activeGenre?' active':'')+'" data-g="'+esc(x.g||'')+'">'+esc(x.l)+'</button>').join('');
  $('#genres').querySelectorAll('.chip').forEach(c=>c.onclick=()=>{activeGenre=c.dataset.g||null;renderGenres();renderMusic();});
  if(!GENRES.length) $('#genres').innerHTML='';
}
function renderMusic(){
  const items=activeGenre?DATA.music.filter(m=>m.genre===activeGenre):DATA.music;
  $('#music-grid').innerHTML=items.length?items.map((m,i)=>
    '<a class="card music" href="'+esc(safeUrl(m.url))+'" target="_blank">'+cover(m.cover,i%4,'Album cover',false)
    +'<div class="meta-line"><span>'+esc(m.source||'Music')+'</span>'+(m.genre?'<span class="sep">&middot;</span><span>'+esc(m.genre)+'</span>':'')+'</div>'
    +'<h4>'+esc(m.title)+'</h4><div class="note">'+esc(m.note)+'</div><span class="go">Listen '+ARR+'</span></a>').join('')
    :'<div class="empty">No tracks in this edition.</div>';
}
$('#watch-grid').innerHTML=DATA.videos.length?DATA.videos.map((v,i)=>
  '<a class="card watch" href="'+(v.video_id?esc(safeUrl(ytWatch(v.video_id))):'#')+'" target="_blank">'+cover(v.video_id?ytThumb(v.video_id):'',i%4,'Video still',true)
  +'<div class="meta-line"><span>'+esc(v.channel||'Video')+'</span>'+(v.wild?'<span class="sep">&middot;</span><span>Wildcard</span>':'')+'</div>'
  +'<h4>'+esc(v.title)+'</h4><div class="note">'+esc(v.note)+'</div><span class="go">Watch '+ARR+'</span></a>').join('')
  :'<div class="empty">No films in this edition.</div>';
$('#good_news-grid').innerHTML=DATA.good_news.length?DATA.good_news.map((g,i)=>
  '<a class="card read" href="'+esc(safeUrl(g.url))+'" target="_blank">'+cover(g.cover,i%4,'Feature image',false)
  +'<div class="meta-line"><span>'+esc(g.source||'Good News')+'</span></div>'
  +'<h4>'+esc(g.title)+'</h4><div class="note">'+esc(g.note)+'</div><span class="go">Read the story '+ARR+'</span></a>').join('')
  :'<div class="empty">Nothing here in this edition.</div>';
$('#discovery-grid').innerHTML=DATA.discovery.length?DATA.discovery.map((d,i)=>
  '<a class="card read" href="'+esc(safeUrl(d.url))+'" target="_blank">'+cover(d.cover,i%4,'Feature image',false)
  +'<div class="meta-line">'+(d.cat?'<span class="badge">'+esc(d.cat)+'</span>':'')+'<span>'+esc(d.source||'')+'</span></div>'
  +'<h4>'+esc(d.title)+'</h4><div class="note">'+esc(d.note)+'</div><span class="go">Read the story '+ARR+'</span></a>').join('')
  :'<div class="empty">Nothing here in this edition.</div>';

renderGenres(); renderMusic();

const tabbar=$('#tabbar');
const sentinel=tabbar.offsetTop;
window.addEventListener('scroll',()=>{tabbar.classList.toggle('stuck',window.scrollY>sentinel+4);},{passive:true});
</script>
</body>
</html>"""


def _edition_slug(dt: datetime.datetime, is_am: bool) -> str:
    return f"{dt.date().isoformat()}-{'morning' if is_am else 'evening'}"


def _parse_edition_slug(stem: str) -> "tuple[datetime.date, bool] | None":
    for suffix, is_am in (("-morning", True), ("-evening", False)):
        if stem.endswith(suffix):
            try:
                return datetime.date.fromisoformat(stem[: -len(suffix)]), is_am
            except ValueError:
                return None
    return None


def _day_suffix(d: int) -> str:
    if 11 <= d <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")


_ARCHIVE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Archive — The Curated Canopy</title>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#F4EEE2;--paper-deep:#E9E1D1;--surface:#FBF7EE;
    --ink:#20271F;--ink-soft:#4A4A3E;--ink-mute:#7C7565;
    --forest:#2C3A2B;--moss:#6E7B4B;--moss-deep:#55603A;
    --clay:#A85A36;--clay-deep:#8E4A2C;--line:#D9CFBC;--line-soft:#E5DCCB;--radius:12px;
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  html{scroll-behavior:smooth;}
  body{font-family:var(--sans);background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh;}
  a{color:inherit;text-decoration:none;}
  .wrap{max-width:800px;margin:0 auto;padding:0 40px;}
  .eyebrow{font-size:11px;font-weight:600;letter-spacing:0.22em;text-transform:uppercase;color:var(--moss-deep);}
  .cover{text-align:center;padding:60px 40px 50px;}
  .cover .eyebrow{color:var(--clay-deep);margin-bottom:22px;}
  .cover h1{font-family:var(--serif);font-weight:500;font-size:clamp(36px,6vw,60px);line-height:1.05;letter-spacing:-0.015em;color:var(--forest);}
  .cover .tagline{font-family:var(--serif);font-style:italic;font-size:18px;color:var(--ink-soft);margin-top:14px;}
  .back{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--clay-deep);margin-top:24px;transition:color .15s ease;}
  .back:hover{color:var(--clay);}
  .edition-list{border-top:1px solid var(--line);margin-top:8px;}
  .edition-row{display:flex;align-items:center;gap:20px;padding:20px 0;border-bottom:1px solid var(--line-soft);cursor:pointer;}
  .edition-row:hover .edition-title{color:var(--clay-deep);}
  .edition-no{font-family:var(--serif);font-size:13px;color:var(--ink-mute);min-width:56px;flex-shrink:0;}
  .edition-info{flex:1;}
  .edition-title{font-family:var(--serif);font-size:20px;color:var(--forest);line-height:1.25;transition:color .15s ease;}
  .edition-meta{font-size:11.5px;letter-spacing:0.12em;text-transform:uppercase;color:var(--ink-mute);margin-top:4px;}
  .edition-tag{display:inline-block;padding:2px 10px;border-radius:100px;border:1px solid var(--line);font-size:10.5px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--moss-deep);margin-left:10px;vertical-align:middle;}
  .edition-arr{color:var(--clay);font-size:18px;flex-shrink:0;transition:transform .15s ease;}
  .edition-row:hover .edition-arr{transform:translateX(4px);}
  .empty{padding:60px 0;text-align:center;font-family:var(--serif);font-style:italic;color:var(--ink-mute);font-size:18px;}
  footer{margin-top:80px;border-top:1px solid var(--line);padding:40px 40px 60px;text-align:center;}
  footer .fmark{font-family:var(--serif);font-size:24px;color:var(--forest);}
  footer .ftag{font-family:var(--serif);font-style:italic;color:var(--ink-mute);margin-top:6px;}
  @media (max-width:600px){
    .wrap{padding:0 22px;} .cover{padding:40px 22px 36px;}
    .edition-row{gap:14px;} .edition-no{min-width:44px;font-size:12px;}
    .edition-title{font-size:17px;}
  }
</style>
</head>
<body>
<header class="cover">
  <div class="eyebrow">The Curated Canopy &nbsp;&middot;&nbsp; Archive</div>
  <h1>Every Edition</h1>
  <div class="tagline">All past issues, gathered here.</div>
  <a class="back" href="./index.html">&larr; Current edition</a>
  <a class="back" href="./grove.html" style="margin-left:18px;">Wander The Grove &rarr;</a>
</header>
<div class="wrap">
__EDITION_LIST__
</div>
<footer>
  <div class="fmark">The Curated Canopy</div>
  <div class="ftag">Gathered twice daily by Fern</div>
</footer>
</body>
</html>"""


def write_archive(editions_dir: Path, archive_path: Path) -> Path:
    """Scan editions_dir for saved editions and rebuild archive.html."""
    entries = []
    for p in editions_dir.glob("*.html"):
        parsed = _parse_edition_slug(p.stem)
        if parsed is None:
            continue
        d, is_am = parsed
        entries.append((d, is_am, p.name))

    entries.sort(key=lambda e: (e[0], not e[1]), reverse=True)

    if not entries:
        list_html = '<div class="empty">No past editions yet — check back soon.</div>'
    else:
        rows = []
        for d, is_am, fname in entries:
            dt_fake = datetime.datetime(d.year, d.month, d.day, 7 if is_am else 18)
            ed_no = _edition_no(dt_fake, is_am)
            suffix = _day_suffix(d.day)
            date_str = f"{d.strftime('%B')} {d.day}<sup>{suffix}</sup> {d.year}"
            tag = "Morning" if is_am else "Evening"
            weekday = d.strftime("%A")
            rows.append(
                f'<a class="edition-row" href="./editions/{fname}">'
                f'<div class="edition-no">No.&nbsp;{ed_no}</div>'
                f'<div class="edition-info">'
                f'<div class="edition-title">{date_str}<span class="edition-tag">{tag}</span></div>'
                f'<div class="edition-meta">{weekday}</div>'
                f'</div>'
                f'<span class="edition-arr">&rarr;</span>'
                f'</a>'
            )
        list_html = '<div class="edition-list">' + "\n".join(rows) + "</div>"

    archive_path.write_text(
        _ARCHIVE_PAGE.replace("__EDITION_LIST__", list_html),
        encoding="utf-8",
    )
    return archive_path


# ---------------------------------------------------------------------------
# The Grove — a scrollable, filterable feed of every item across all editions
# ---------------------------------------------------------------------------

_GROVE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Grove — The Curated Canopy</title>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#F4EEE2;--paper-deep:#E9E1D1;--surface:#FBF7EE;
    --ink:#20271F;--ink-soft:#4A4A3E;--ink-mute:#7C7565;
    --forest:#2C3A2B;--moss:#6E7B4B;--moss-deep:#55603A;
    --clay:#A85A36;--clay-deep:#8E4A2C;--line:#D9CFBC;--line-soft:#E5DCCB;--radius:12px;
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  html{scroll-behavior:smooth;}
  body{font-family:var(--sans);background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh;}
  img{max-width:100%;display:block;}
  a{color:inherit;text-decoration:none;}
  .wrap{max-width:1120px;margin:0 auto;padding:0 40px;}
  .eyebrow{font-size:11px;font-weight:600;letter-spacing:0.22em;text-transform:uppercase;color:var(--moss-deep);}

  .cover{text-align:center;padding:58px 40px 30px;}
  .cover .eyebrow{color:var(--clay-deep);margin-bottom:20px;}
  .cover h1{font-family:var(--serif);font-weight:500;font-size:clamp(40px,7vw,70px);line-height:1.02;letter-spacing:-0.015em;color:var(--forest);}
  .cover .tagline{font-family:var(--serif);font-style:italic;font-size:clamp(16px,2.2vw,20px);color:var(--ink-soft);margin-top:14px;}
  .cover .nav{margin-top:22px;display:flex;gap:18px;justify-content:center;flex-wrap:wrap;font-size:12px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;}
  .cover .nav a{color:var(--clay-deep);transition:color .15s ease;}
  .cover .nav a:hover{color:var(--clay);}

  .controls{position:sticky;top:0;z-index:50;background:rgba(244,238,226,0.9);backdrop-filter:blur(10px) saturate(120%);border-bottom:1px solid var(--line);padding:16px 0;}
  .controls .wrap{display:flex;flex-direction:column;gap:12px;}
  .search{width:100%;font-family:var(--sans);font-size:15px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:100px;padding:12px 20px;outline:none;transition:border-color .15s ease;}
  .search:focus{border-color:var(--moss);}
  .search::placeholder{color:var(--ink-mute);}
  .chips{display:flex;flex-wrap:wrap;gap:8px;}
  .chip{cursor:pointer;font-family:var(--sans);font-size:12px;font-weight:600;letter-spacing:0.03em;padding:7px 15px;border-radius:100px;border:1px solid var(--line);background:var(--surface);color:var(--ink-soft);transition:all .16s ease;text-transform:capitalize;}
  .chip:hover{border-color:var(--moss);color:var(--forest);}
  .chip.active{background:var(--forest);border-color:var(--forest);color:var(--paper);}
  .chip.mood.active{background:var(--clay-deep);border-color:var(--clay-deep);}
  .chip-row-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:var(--ink-mute);align-self:center;margin-right:4px;}

  .count{padding:24px 0 6px;font-family:var(--serif);font-style:italic;color:var(--ink-mute);font-size:15px;}

  .feed{column-count:3;column-gap:26px;padding:8px 0 20px;}
  .card{break-inside:avoid;margin-bottom:26px;display:block;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease;}
  .card:hover{transform:translateY(-3px);box-shadow:0 10px 30px rgba(32,39,31,0.10);border-color:var(--moss);}
  .card .cv{position:relative;width:100%;overflow:hidden;background:linear-gradient(160deg,var(--ph-a,#C9CBB0),var(--ph-b,#9DA882));}
  .card .cv img{width:100%;height:100%;object-fit:cover;display:block;}
  .card .cv.t0{--ph-a:#D9CFB8;--ph-b:#B3A684;} .card .cv.t1{--ph-a:#D8B59B;--ph-b:#B0764F;}
  .card .cv.t2{--ph-a:#B7C29A;--ph-b:#7E8C5A;} .card .cv.t3{--ph-a:#7E8C6E;--ph-b:#46553E;}
  .card .cv.ph{aspect-ratio:16/10;}
  .play{position:absolute;inset:0;margin:auto;width:54px;height:54px;border-radius:50%;border:1.5px solid rgba(255,255,255,0.92);background:rgba(32,39,31,0.22);display:flex;align-items:center;justify-content:center;transition:transform .2s ease;}
  .play::after{content:"";margin-left:3px;border-style:solid;border-width:8px 0 8px 13px;border-color:transparent transparent transparent rgba(255,255,255,0.95);}
  .card:hover .play{transform:scale(1.08);}
  .card .body{padding:18px 20px 20px;}
  .card .meta-line{display:flex;align-items:center;gap:9px;font-size:10px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:var(--moss-deep);flex-wrap:wrap;}
  .card .meta-line .sep{color:var(--line);}
  .card .meta-line .date{color:var(--ink-mute);}
  .card h4{font-family:var(--serif);font-weight:500;font-size:20px;line-height:1.22;color:var(--forest);margin-top:10px;letter-spacing:-0.005em;}
  .card .note{font-size:14px;color:var(--ink-soft);margin-top:9px;line-height:1.55;}
  .card .moods{display:flex;flex-wrap:wrap;gap:10px;margin-top:11px;}
  .card .moodtag{font-size:9px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;color:rgba(124,117,101,0.55);}
  .card .from{margin-top:14px;font-size:11px;letter-spacing:0.06em;color:var(--ink-mute);}
  .card .from a{color:var(--clay-deep);font-weight:600;}

  .empty{text-align:center;font-family:var(--serif);font-style:italic;color:var(--ink-mute);font-size:19px;padding:70px 0;}
  #sentinel{height:1px;}

  footer{margin-top:40px;border-top:1px solid var(--line);padding:40px 40px 60px;text-align:center;}
  footer .fmark{font-family:var(--serif);font-size:24px;color:var(--forest);}
  footer .ftag{font-family:var(--serif);font-style:italic;color:var(--ink-mute);margin-top:6px;}

  @media (max-width:900px){ .feed{column-count:2;} }
  @media (max-width:600px){
    .wrap{padding:0 22px;} .cover{padding:42px 22px 24px;}
    .feed{column-count:1;}
  }
</style>
</head>
<body>
<header class="cover">
  <div class="eyebrow">The Curated Canopy &nbsp;&middot;&nbsp; The Grove</div>
  <h1>The Grove</h1>
  <div class="tagline">Wander every story, song &amp; film we&#39;ve ever gathered.</div>
  <div class="nav">
    <a href="./index.html">&larr; Current edition</a>
    <a href="./archive.html">The Archive</a>
  </div>
</header>

<div class="controls">
  <div class="wrap">
    <input class="search" id="search" type="search" placeholder="Search The Grove — a title, a source, a feeling…" autocomplete="off">
    <div class="chips" id="section-chips"></div>
    <div class="chips" id="mood-chips"></div>
  </div>
</div>

<main class="wrap">
  <div class="count" id="count"></div>
  <div class="feed" id="feed"></div>
  <div id="sentinel"></div>
</main>

<footer>
  <div class="fmark">The Curated Canopy</div>
  <div class="ftag">Gathered twice daily by Fern</div>
</footer>

<script>
const $ = (s,r=document)=>r.querySelector(s);
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function safeUrl(u){try{const p=new URL(u,location.href);return ['http:','https:','mailto:'].includes(p.protocol)?p.href:'#';}catch(e){return '#';}}
const SECTION_LABEL={music:'Soundtrack',videos:'Worth Watching',good_news:'Good News',discovery:'From the Archives',featured_read:'One Good Read'};
const ARR='<span>&rarr;</span>';

let ALL=[], MOODS=[], SECTIONS=[];
let activeSection=null, activeMoods=new Set(), query='';
let filtered=[], shown=0;
const BATCH=24;

function fmtDate(iso,ampm){
  try{const d=new Date(iso+'T12:00:00');
    return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})+' · '+(ampm==='morning'?'Morning':'Evening');
  }catch(e){return iso;}
}

function cardHTML(it,idx){
  const tone='t'+(idx%4);
  const isVid=it.section==='videos';
  const cv=it.image
    ? '<div class="cv photo"><img src="'+esc(safeUrl(it.image))+'" alt="" loading="lazy">'+(isVid?'<span class="play"></span>':'')+'</div>'
    : '<div class="cv ph '+tone+'">'+(isVid?'<span class="play"></span>':'')+'</div>';
  const moods=(it.moods||[]).map(m=>'<span class="moodtag">'+esc(m)+'</span>').join('');
  const src=it.source?'<span>'+esc(it.source)+'</span><span class="sep">&middot;</span>':'';
  return '<a class="card" href="'+esc(safeUrl(it.url))+'" target="_blank" rel="noopener">'
    + cv
    + '<div class="body">'
    +   '<div class="meta-line">'+src+'<span>'+esc(SECTION_LABEL[it.section]||it.section)+'</span></div>'
    +   '<h4>'+esc(it.title)+'</h4>'
    +   (it.note?'<div class="note">'+esc(it.note)+'</div>':'')
    +   (moods?'<div class="moods">'+moods+'</div>':'')
    +   '<div class="from">From the <a href="./editions/'+esc(it.edition)+'">'+esc(fmtDate(it.date,it.ampm))+'</a> edition</div>'
    + '</div></a>';
}

function applyFilters(){
  const q=query.trim().toLowerCase();
  filtered=ALL.filter(it=>{
    if(activeSection && it.section!==activeSection) return false;
    if(activeMoods.size){ const ms=it.moods||[]; let ok=false; for(const m of activeMoods){ if(ms.includes(m)){ok=true;break;} } if(!ok) return false; }
    if(q){ const hay=(it.title+' '+it.note+' '+it.source+' '+(it.moods||[]).join(' ')).toLowerCase(); if(!hay.includes(q)) return false; }
    return true;
  });
  shown=0;
  $('#feed').innerHTML='';
  const n=filtered.length;
  $('#count').textContent = n===0 ? '' : (n+' '+(n===1?'thing':'things')+' to wander through');
  if(n===0){ $('#feed').innerHTML='<div class="empty">Nothing matches just yet — try a different mood or search.</div>'; return; }
  renderMore();
}

function renderMore(){
  const next=filtered.slice(shown,shown+BATCH);
  if(!next.length) return;
  const frag=document.createElement('div');
  frag.innerHTML=next.map((it,i)=>cardHTML(it,shown+i)).join('');
  while(frag.firstChild) $('#feed').appendChild(frag.firstChild);
  shown+=next.length;
}

function renderChips(){
  const sc=$('#section-chips');
  const all=[{k:null,l:'Everything'}].concat(SECTIONS.map(s=>({k:s.key,l:s.label})));
  sc.innerHTML=all.map(x=>'<button class="chip'+(x.k===activeSection?' active':'')+'" data-k="'+esc(x.k||'')+'">'+esc(x.l)+'</button>').join('');
  sc.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{activeSection=c.dataset.k||null;renderChips();applyFilters();});
  const mc=$('#mood-chips');
  if(!MOODS.length){ mc.innerHTML=''; return; }
  mc.innerHTML='<span class="chip-row-label">Mood</span>'+MOODS.map(m=>'<button class="chip mood'+(activeMoods.has(m)?' active':'')+'" data-m="'+esc(m)+'">'+esc(m)+'</button>').join('');
  mc.querySelectorAll('.chip.mood').forEach(c=>c.onclick=()=>{const m=c.dataset.m;activeMoods.has(m)?activeMoods.delete(m):activeMoods.add(m);renderChips();applyFilters();});
}

$('#search').addEventListener('input',e=>{query=e.target.value;applyFilters();});

new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting)renderMore();});},{rootMargin:'600px'}).observe($('#sentinel'));

fetch('./grove.json',{cache:'no-cache'}).then(r=>r.json()).then(d=>{
  ALL=d.items||[]; MOODS=d.moods||[]; SECTIONS=d.sections||[];
  // hide mood chips entirely until at least one item carries a mood
  if(!ALL.some(it=>(it.moods||[]).length)) MOODS=[];
  renderChips(); applyFilters();
}).catch(()=>{ $('#feed').innerHTML='<div class="empty">The Grove is still growing — check back soon.</div>'; });
</script>
</body>
</html>"""


# Human-facing labels per section, used by the page's chips and card meta.
_GROVE_SECTIONS = [
    ("music",         "Soundtrack"),
    ("videos",        "Worth Watching"),
    ("good_news",     "Good News"),
    ("discovery",     "From the Archives"),
    ("featured_read", "One Good Read"),
]


def _extract_payload(html: str) -> "dict | None":
    """Pull the embedded JSON payload out of a rendered edition HTML file."""
    m = re.search(
        r'<script id="data" type="application/json">(.*?)</script>', html, re.S
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _grove_rank(entry: dict) -> tuple:
    """Sort key: (date, morning=0/evening=1). Larger = more recent."""
    return (entry["date"], 0 if entry["ampm"] == "morning" else 1)


def _grove_entries(data: dict, d: datetime.date, is_am: bool) -> list[dict]:
    """Flatten one edition payload into a list of feed entries."""
    date_iso = d.isoformat()
    ampm = "morning" if is_am else "evening"
    edition_file = f"{date_iso}-{ampm}.html"
    out: list[dict] = []

    def add(section, title, note, url, image, source, genre=""):
        if not title:
            return
        out.append({
            "section": section,
            "title":   title,
            "note":    note or "",
            "url":     url or "#",
            "image":   image or "",
            "source":  source or "",
            "genre":   genre or "",
            "date":    date_iso,
            "ampm":    ampm,
            "edition": edition_file,
            "moods":   [],
        })

    for m in data.get("music", []):
        add("music", m.get("title"), m.get("note"), m.get("url"),
            m.get("cover"), m.get("source"), m.get("genre"))
    for v in data.get("videos", []):
        vid = v.get("video_id", "")
        add("videos", v.get("title"), v.get("note"),
            f"https://www.youtube.com/watch?v={vid}" if vid else "#",
            f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else "",
            v.get("channel"))
    for g in data.get("good_news", []):
        add("good_news", g.get("title"), g.get("note"), g.get("url"),
            g.get("cover"), g.get("source"))
    for x in data.get("discovery", []):
        add("discovery", x.get("title"), x.get("note"), x.get("url"),
            x.get("cover"), x.get("source"))
    fr = data.get("featured_read")
    if fr and fr.get("title"):
        add("featured_read", fr.get("title"), fr.get("note"), fr.get("url"),
            fr.get("cover"), fr.get("source"))
    return out


def build_grove(
    editions_dir: Path = EDITIONS_DIR,
    grove_json: Path = GROVE_JSON,
    grove_html: Path = GROVE_HTML,
) -> Path:
    """
    Aggregate every item from every saved edition into docs/grove.json and
    (re)write docs/grove.html. Items are deduped on URL (keeping the earliest
    appearance) and sorted newest-first. Any moods already computed for an item
    are preserved across rebuilds so we never re-tag what Claude has seen.
    """
    DOCS_DIR.mkdir(exist_ok=True)

    # Preserve previously-tagged moods (keyed by URL) across regenerations.
    prev_moods: dict[str, list[str]] = {}
    if grove_json.exists():
        try:
            old = json.loads(grove_json.read_text(encoding="utf-8"))
            for it in old.get("items", []):
                if it.get("moods"):
                    prev_moods[it["url"]] = it["moods"]
        except Exception:
            pass

    collected: dict[str, dict] = {}
    order: list[str] = []
    for p in sorted(editions_dir.glob("*.html")):
        parsed = _parse_edition_slug(p.stem)
        if parsed is None:
            continue
        d, is_am = parsed
        data = _extract_payload(p.read_text(encoding="utf-8"))
        if not data:
            continue
        for entry in _grove_entries(data, d, is_am):
            key = entry["url"]
            if key in ("", "#"):
                key = entry["section"] + "|" + entry["title"]
            existing = collected.get(key)
            if existing is None:
                collected[key] = entry
                order.append(key)
            elif _grove_rank(entry) < _grove_rank(existing):
                # keep the earliest appearance's date/edition
                collected[key] = entry

    items = [collected[k] for k in order]
    for it in items:
        if it["url"] in prev_moods:
            it["moods"] = prev_moods[it["url"]]
    items.sort(key=_grove_rank, reverse=True)

    payload = {
        "generated_at": datetime.datetime.now(ZoneInfo("Europe/Zurich")).isoformat(),
        "moods": GROVE_MOODS,
        "sections": [{"key": k, "label": l} for k, l in _GROVE_SECTIONS],
        "items": items,
    }
    grove_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    grove_html.write_text(_GROVE_PAGE, encoding="utf-8")
    return grove_json


def build_edition(curated: dict) -> str:
    fetched_at = curated.get("fetched_at", "")
    is_am = curated.get("is_am_email", False)
    edition_label = "Morning Edition" if is_am else "Evening Edition"
    try:
        dt = datetime.datetime.fromisoformat(fetched_at).astimezone(ZoneInfo("Europe/Zurich"))
        date_str = f"{dt.strftime('%a, %B')} {dt.day}, {dt.strftime('%Y')}"
        issue = f"No. {_edition_no(dt, is_am)} &nbsp;&middot;&nbsp; "
    except Exception:
        date_str = fetched_at or ""
        issue = ""

    # Harden JSON for embedding in an HTML <script> element.
    data_json = (
        json.dumps(_payload(curated))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    return (
        _PAGE
        .replace("__EDITION_LABEL__", edition_label)
        .replace("__ISSUE__", issue)
        .replace("__DATE_STR__", date_str)
        .replace("__GARDEN_LOCALE__", GARDEN_LOCALE)
        .replace("__DATA_JSON__", data_json)
    )


def write_edition(curated: dict) -> Path:
    DOCS_DIR.mkdir(exist_ok=True)
    EDITIONS_DIR.mkdir(exist_ok=True)

    html = build_edition(curated)
    EDITION_HTML.write_text(html, encoding="utf-8")

    # Persist this edition to the dated archive
    fetched_at = curated.get("fetched_at", "")
    is_am = curated.get("is_am_email", False)
    try:
        dt = datetime.datetime.fromisoformat(fetched_at).astimezone(ZoneInfo("Europe/Zurich"))
        slug = _edition_slug(dt, is_am)
        (EDITIONS_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
    except Exception as exc:
        print(f"[webpage] Could not save dated edition: {exc}")

    write_archive(EDITIONS_DIR, ARCHIVE_HTML)

    # Rebuild The Grove (aggregates every saved edition), then best-effort
    # mood-tag any new/untagged items. Tagging is optional: it needs a Claude
    # key and never blocks the edition from publishing.
    build_grove()
    try:
        import curator
        curator.tag_grove_moods(GROVE_JSON)
    except Exception as exc:
        print(f"[webpage] Skipped Grove mood tagging: {exc}")

    return EDITION_HTML


def main() -> None:
    if not CURATED_FILE.exists():
        raise FileNotFoundError(f"{CURATED_FILE} not found. Run fetcher.py first.")
    curated = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
    path = write_edition(curated)
    print(f"[webpage] Full edition written -> {path}")


if __name__ == "__main__":
    main()
