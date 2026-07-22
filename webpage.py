"""
Newsletter — Companion "full edition" web page (GitHub Pages)
------------------------------------------------------------
Reads curated_data.json -> writes docs/index.html, a self-contained interactive
page the email links out to: a "Forest & Brass · Belle Époque" magazine with a
gilt-framed forest masthead, Fern's note (drop cap), a hero feature, sticky
section tabs, a music genre filter, and four browsable sections.

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
    "cozy", "curious", "wonder", "playful",
    "Romantic", "Crafty / Creative", "Cheer Up!", "Calm Down",
    "Energize", "Inspire",
]


def _dedash(s: str) -> str:
    """Remove em/en dashes from Fern's prose (reads less machine-made)."""
    if not s:
        return s
    s = s.replace(" — ", ", ").replace(" – ", ", ")
    s = s.replace("—", ", ").replace("–", "-")
    while ", ," in s:
        s = s.replace(", ,", ",")
    return s.strip()


# Running issue number, like a real periodical ("No. 248").
# Set this to the date of your VERY FIRST edition. Editions go out twice a day,
# so the number climbs by 2 each day on its own — no manual tracking needed.
CANOPY_LAUNCH = datetime.date(2026, 6, 10)  # first edition; No. 1 = 2026-06-10 morning

# Where Fern's garden lives — shown in the "From the Garden" eyebrow.
import os
GARDEN_LOCALE = os.environ.get("GARDEN_LOCALE", "Zürich")
# Edition timezone (env-overridable for regional editions; default = primary).
EDITION_TZ = ZoneInfo(os.environ.get("EDITION_TZ", "Europe/Zurich"))


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

    ld = curated.get("larder") or {}
    _lrec = ld.get("recipe") or {}
    # The seasonal note is locale-curated (e.g. Zürich markets) and belongs only in the
    # per-recipient emails, not the single shared web edition — so it's not emitted here.
    larder = {
        "recipe": ({
            "title":  _lrec.get("title", ""),
            "note":   _dedash(_lrec.get("blurb") or _lrec.get("snippet", "")),
            "url":    _lrec.get("url", "#"),
            "cover":  _lrec.get("cover_url", ""),
            "source": _lrec.get("source_name", ""),
        } if _lrec.get("title") else None),
        "news": [{
            "title":  n.get("title", ""),
            "note":   _dedash(n.get("blurb") or n.get("snippet", "")),
            "url":    n.get("url", "#"),
            "cover":  n.get("cover_url", ""),
            "source": n.get("source_name", ""),
        } for n in (ld.get("news") or []) if n.get("title")],
    } if (_lrec.get("title") or ld.get("news")) else None

    g = curated.get("garden_note") or {}
    garden = {
        "note":        _dedash(g.get("note", "")),
        "in_season":   [s for s in (g.get("in_season") or []) if s],
        "sky_tonight": _dedash(g.get("sky_tonight", "")),
        "sun_range":   g.get("sun_range", ""),   # structured range — keep the dash
        "moon_label":  g.get("moon_label", ""),
        "illum_pct":   g.get("illum_pct", 0),
    } if g.get("note") else None

    pz = curated.get("puzzle") or {}
    puzzle = {
        "label":  pz.get("label", ""),
        "prompt": _dedash(pz.get("prompt", "")),
        "answer": _dedash(pz.get("answer", "")),
        "hint":   _dedash(pz.get("hint", "")),
        "source": pz.get("source", ""),
        "credit": _dedash(pz.get("credit", "")),
    } if pz.get("prompt") and pz.get("answer") else None

    pp = curated.get("previous_puzzle") or {}
    prev_puzzle = {
        "label":  pp.get("label", ""),
        "prompt": _dedash(pp.get("prompt", "")),
        "answer": _dedash(pp.get("answer", "")),
    } if pp.get("answer") else None

    return {
        "is_am":    curated.get("is_am_email", False),
        "greeting": _dedash(curated.get("fern_data", {}).get("greeting", "")),
        "garden":    garden,
        "puzzle":    puzzle,
        "prev_puzzle": prev_puzzle,
        "featured_read": featured_read,
        "music":     music,
        "videos":    videos,
        "good_news": good_news,
        "discovery": discovery,
        "larder":    larder,
    }


# Whiplash flourish (Art Nouveau) — reused under each wordmark and as dividers.
_FLOURISH = ('<span class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="190" height="19">'
             '<g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round">'
             '<path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/>'
             '<path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/>'
             '<path d="M38 10 H10"/><path d="M162 10 H190"/></g>'
             '<g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/>'
             '<circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/>'
             '<circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></span>')


# Token-replaced (NOT str.format) so CSS/JS braces stay single.
_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Curated Canopy — Full Edition</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#EFE7D6;--paper-deep:#E5DCC4;--surface:#FCF7EB;
    --ink:#1B2716;--ink-soft:#3C4433;--ink-mute:#79735C;
    --forest:#1E2E1A;--forest-deep:#162313;
    --brass:#C09433;--brass-deep:#A87E28;--brass-soft:#D9B968;
    --clay:#B6541F;--clay-deep:#984417;
    --line:#DCD0B4;--line-on-dark:rgba(216,185,104,0.32);
    --cream:#F2EAD6;--cream-mute:#C6C3A6;--radius:10px;
    --display:'Cormorant Garamond',Georgia,'Times New Roman',serif;
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  /* Canvas matches the paper page, so overscroll and pinch-zoom-out show cream on the
     sides/top rather than a band of forest. The sticky footer (below) keeps the footer
     flush at the bottom, so no dead space returns beneath it. */
  html{scroll-behavior:smooth;background:var(--paper);overflow-x:clip;}
  body{font-family:var(--sans);background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh;display:flex;flex-direction:column;overflow-wrap:break-word;}
  /* Sticky footer: the tab deck absorbs any slack so the footer sits flush at the
     bottom even when an edition is short — no dead cream space beneath the banner. */
  main{flex:1 0 auto;}
  /* Keep the flex column from letting the horizontal card decks blow out the page
     width: fill the viewport rather than shrink-to-content, and let the .grid
     scrollers shrink so their own overflow-x scroll takes over. */
  body>*{width:100%;min-width:0;}
  img{max-width:100%;display:block;}
  a{color:inherit;text-decoration:none;}
  .wrap{max-width:1120px;margin:0 auto;padding:0 40px;}
  .eyebrow{font-size:11px;font-weight:600;letter-spacing:0.24em;text-transform:uppercase;color:var(--brass-deep);}

  /* ---- ornaments ---- */
  .flr{display:inline-flex;color:var(--brass-deep);line-height:0;}
  .flr svg{display:block;}
  .rule-flr{display:flex;justify-content:center;padding:30px 0;}
  .eyebrow.orn{display:inline-flex;align-items:center;gap:11px;}
  .eyebrow.orn::before,.eyebrow.orn::after{content:"";width:6px;height:6px;background:var(--brass);transform:rotate(45deg);flex:none;}

  /* ---- image placeholders ---- */
  .img,.photo{position:relative;width:100%;overflow:hidden;}
  .img{background:linear-gradient(135deg,rgba(255,255,255,0.16),rgba(255,255,255,0) 60%),repeating-linear-gradient(135deg,rgba(27,39,22,0.04) 0 2px,transparent 2px 11px),linear-gradient(160deg,var(--ph-a,#C9CBB0),var(--ph-b,#9DA882));}
  .img::after{content:attr(data-label);position:absolute;left:12px;bottom:11px;font-family:var(--sans);font-size:9px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:rgba(247,242,230,0.92);background:rgba(22,35,19,0.42);padding:3px 9px;}
  .img.t0{--ph-a:#D7CBA8;--ph-b:#AE9C6A;} .img.t1{--ph-a:#D8A87C;--ph-b:#9E5A2E;}
  .img.t2{--ph-a:#A9BB83;--ph-b:#5E6E3A;} .img.t3{--ph-a:#6E7E5C;--ph-b:#33472A;}
  .photo img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;}
  .play{position:absolute;inset:0;margin:auto;width:60px;height:60px;border-radius:50%;border:1.5px solid rgba(247,242,230,0.92);background:rgba(22,35,19,0.22);display:flex;align-items:center;justify-content:center;transition:transform .25s ease,background .25s ease;}
  .play::after{content:"";margin-left:3px;border-style:solid;border-width:9px 0 9px 15px;border-color:transparent transparent transparent rgba(247,242,230,0.95);}

  /* ---- masthead (forest + gilt frame) ---- */
  .cover{position:relative;background:var(--forest);color:var(--cream);text-align:center;padding:66px 40px 56px;overflow:hidden;}
  .cover::before{content:"";position:absolute;inset:14px;border:1px solid var(--line-on-dark);pointer-events:none;}
  .cover::after{content:"";position:absolute;inset:19px;border:1px solid rgba(216,185,104,0.14);pointer-events:none;}
  .cover-in{position:relative;}
  .cover .eyebrow{color:var(--brass-soft);margin-bottom:20px;}
  .cover .eyebrow.orn::before,.cover .eyebrow.orn::after{background:var(--brass-soft);}
  .cover h1{font-family:var(--display);font-weight:600;font-size:clamp(54px,9vw,108px);line-height:0.94;letter-spacing:0.005em;color:var(--cream);}
  .cover .tagline{font-family:var(--display);font-style:italic;font-weight:500;font-size:clamp(19px,2.7vw,27px);color:var(--cream-mute);margin-top:14px;}
  .cover .flr{color:var(--brass-soft);margin-top:22px;}
  .cover .meta{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:15px;margin-top:24px;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:var(--cream-mute);}
  .cover .meta .dot{width:4px;height:4px;border-radius:50%;background:var(--brass-soft);}

  /* ---- Fern's note (drop cap) ---- */
  .fern{max-width:740px;margin:46px auto 0;padding:0 40px;display:flex;gap:24px;align-items:flex-start;}
  .monogram{flex-shrink:0;width:54px;height:54px;border-radius:50%;border:1px solid var(--brass);color:var(--brass-deep);font-family:var(--display);font-weight:600;font-size:27px;display:flex;align-items:center;justify-content:center;margin-top:8px;box-shadow:0 0 0 4px var(--paper),0 0 0 5px rgba(192,148,51,0.35);}
  .fern .eyebrow{margin-bottom:11px;}
  .fern p{font-family:var(--serif);font-size:20px;line-height:1.62;color:var(--ink-soft);}
  .fern p.lead::first-letter{font-family:var(--display);font-weight:600;font-size:3.9em;line-height:0.8;float:left;color:var(--brass-deep);margin:0.04em 0.11em 0 0;}
  .fern .sign{font-family:var(--display);font-style:italic;font-size:1.15em;color:var(--forest);}

  /* ---- almanac ---- */
  .almanac{max-width:740px;margin:0 auto;padding:26px 40px 4px;}
  .almanac .eyebrow{margin-bottom:12px;}
  .almanac p{font-family:var(--serif);font-size:18px;line-height:1.62;color:var(--ink-soft);}
  .almanac-sky{font-family:var(--serif);font-style:italic;font-size:16px;line-height:1.55;color:var(--ink-mute);margin-top:10px;}
  .almanac-foot{display:flex;flex-wrap:wrap;align-items:center;gap:12px 22px;margin-top:18px;}
  .almanac-meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;font-size:11px;letter-spacing:0.15em;text-transform:uppercase;color:var(--ink-mute);}
  .almanac-meta .dot{width:4px;height:4px;border-radius:50%;background:var(--brass);}
  .history-link{display:inline-block;clear:both;margin-top:18px;font-family:var(--sans);font-size:11px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:var(--clay-deep);}

  /* ---- Fern's daily puzzle ---- */
  .puzzle{max-width:740px;margin:0 auto;padding:26px 40px 4px;}
  .puzzle .eyebrow{margin-bottom:12px;}
  .puzzle p{font-family:var(--serif);font-size:18px;line-height:1.62;color:var(--ink-soft);white-space:pre-line;}
  .puzzle .hint{font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:var(--ink-mute);margin-top:12px;}
  .puzzle details{margin-top:16px;}
  .puzzle summary{display:inline-block;cursor:pointer;font-family:var(--sans);font-size:11.5px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;padding:8px 18px;border:1px solid var(--brass);color:var(--brass-deep);transition:all .18s ease;list-style:none;}
  .puzzle summary::-webkit-details-marker{display:none;}
  .puzzle summary:hover{background:var(--brass);color:var(--forest-deep);}
  .puzzle details[open] summary{display:none;}
  .puzzle .answer{font-family:var(--display);font-style:italic;font-size:21px;color:var(--forest);border-left:2px solid var(--brass);padding-left:16px;}
  .puzzle .prev{margin-top:18px;padding-top:14px;border-top:1px solid var(--line);font-size:14px;line-height:1.55;color:var(--ink-soft);}
  .puzzle .prev .lbl{display:block;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-mute);margin-bottom:4px;}
  .puzzle .prev b{color:var(--brass-deep);font-weight:600;}
  .puzzle .source{margin-top:10px;font-family:var(--sans);font-size:10.5px;letter-spacing:0.06em;color:var(--ink-mute);}
  /* Desktop: Fern's note and the puzzle sit side by side within the 1120 frame so the
     top fills the width. Phone keeps the stacked single-column look (below). */
  @media (min-width:821px){
    .intro{max-width:1120px;margin:0 auto;padding:46px 40px 0;display:flex;gap:56px;align-items:flex-start;}
    .intro .fern{flex:1.4 1 0;min-width:0;max-width:none;margin:0;padding:0;}
    .intro .puzzle{flex:1 1 0;min-width:0;max-width:none;margin:0;padding:0 0 0 56px;border-left:1px solid var(--line);}
  }

  /* ---- FIP live radio bar (gilt double frame + diamond accents) ---- */
  .radio-bar{position:relative;display:flex;align-items:center;gap:18px;background:var(--forest);border:1px solid var(--brass);color:var(--cream);padding:18px 30px;margin-bottom:30px;flex-wrap:wrap;}
  .radio-bar::before{content:"";position:absolute;inset:5px;border:1px solid rgba(216,185,104,0.30);pointer-events:none;}
  .radio-bar::after{content:"";position:absolute;right:14px;top:50%;width:6px;height:6px;margin-top:-3px;background:var(--brass-soft);transform:rotate(45deg);pointer-events:none;}
  .radio-orn{position:absolute;left:14px;top:50%;width:6px;height:6px;margin-top:-3px;background:var(--brass-soft);transform:rotate(45deg);pointer-events:none;}
  @media (max-width:700px){.radio-bar::after,.radio-orn{display:none;}.radio-bar{padding:14px 18px;}}
  .radio-play{flex:none;width:44px;height:44px;border-radius:50%;border:1.5px solid var(--brass-soft);background:transparent;color:var(--brass-soft);font-size:15px;line-height:1;cursor:pointer;transition:all .18s ease;display:flex;align-items:center;justify-content:center;padding-left:3px;}
  .radio-play:hover{background:var(--brass);border-color:var(--brass);color:var(--forest-deep);}
  .radio-info{flex:1;min-width:200px;}
  .radio-name{font-family:var(--display);font-weight:600;font-size:22px;line-height:1.1;color:var(--cream);}
  .radio-live{font-family:var(--sans);font-size:10px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:var(--brass-soft);margin-left:12px;vertical-align:middle;}
  .radio-live::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--brass-soft);margin-right:7px;vertical-align:middle;}
  body.radio-on .radio-live::before{animation:onair 1.4s ease-in-out infinite;}
  @keyframes onair{0%,100%{opacity:1;}50%{opacity:0.25;}}
  @media (prefers-reduced-motion:reduce){body.radio-on .radio-live::before{animation:none;}}
  .radio-tag{font-family:var(--serif);font-style:italic;font-size:14px;color:var(--cream-mute);margin-top:3px;}
  .radio-link{flex:none;font-family:var(--sans);font-size:10.5px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:var(--brass-soft);transition:color .15s ease;}
  .radio-link:hover{color:var(--cream);}
  @media (max-width:600px){.radio-link{display:none;}.radio-bar{gap:14px;padding:14px 16px;}}

  /* ---- hero + feature ---- */
  .hero{margin-top:14px;}
  .hero-grid,.feature-read{display:grid;border-top:1px solid var(--brass);border-bottom:1px solid var(--brass);}
  .hero-grid{grid-template-columns:1.5fr 1fr;}
  .feature-read{grid-template-columns:1fr 1.5fr;margin-top:8px;}
  .hero-grid .cell,.feature-read .cell{min-height:430px;border-right:1px solid var(--line);}
  .feature-read .cell{min-height:350px;}
  .hero-text{padding:46px 50px;display:flex;flex-direction:column;justify-content:center;}
  .hero-text .eyebrow{margin-bottom:18px;}
  .hero-text h2{font-family:var(--display);font-weight:600;font-size:clamp(30px,3.6vw,44px);line-height:1.06;letter-spacing:0.005em;color:var(--forest);}
  .hero-text p{font-family:var(--serif);font-size:16.5px;color:var(--ink-soft);margin-top:16px;max-width:42ch;}
  .textlink{display:inline-flex;align-items:center;gap:9px;margin-top:26px;font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--clay-deep);}
  .textlink .arr{transition:transform .2s ease;color:var(--brass-deep);} .textlink:hover .arr{transform:translateX(5px);}

  /* ---- sticky tabs ---- */
  .tabbar{position:sticky;top:0;z-index:50;background:rgba(239,231,214,0.9);backdrop-filter:blur(10px) saturate(120%);border-bottom:1px solid var(--brass);margin-top:8px;}
  .tabbar-inner{max-width:1120px;margin:0 auto;padding:0 40px;display:flex;align-items:center;gap:28px;height:62px;}
  .tabs{display:flex;gap:6px;flex:1;min-width:0;overflow-x:auto;scrollbar-width:none;}
  .tabs::-webkit-scrollbar{display:none;}
  .tab{position:relative;white-space:nowrap;cursor:pointer;padding:20px 15px;font-size:12px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-mute);background:none;border:0;font-family:var(--sans);transition:color .2s ease;}
  .tab:hover{color:var(--ink);} .tab.active{color:var(--forest);}
  .tab .ix{font-family:var(--display);font-style:italic;font-size:14px;color:var(--brass-deep);margin-right:6px;font-weight:600;text-transform:none;letter-spacing:0;}
  .tab::after{content:"";position:absolute;left:15px;right:15px;bottom:-1px;height:2px;background:var(--brass);transform:scaleX(0);transition:transform .25s ease;}
  .tab.active::after{transform:scaleX(1);}

  /* ---- panels ---- */
  .panel{display:none;padding:54px 0 20px;}
  .panel.active{display:block;animation:fade .4s ease;}
  @keyframes fade{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:none;}}
  @media (prefers-reduced-motion:reduce){.panel.active{animation:none;}}
  .sec-head{margin-bottom:36px;}
  .sec-head .eyebrow{display:inline-flex;}
  .sec-head h3{font-family:var(--display);font-weight:600;font-size:clamp(32px,4.4vw,50px);line-height:1.02;letter-spacing:0.005em;color:var(--forest);margin-top:14px;}
  .sec-head .lede{font-family:var(--serif);font-style:italic;font-size:18px;color:var(--ink-mute);margin-top:9px;max-width:54ch;}

  .chips{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:30px;}
  .chips:empty{display:none;margin:0;padding:0;}
  .chip{cursor:pointer;font-family:var(--sans);font-size:11.5px;font-weight:600;letter-spacing:0.04em;padding:8px 16px;border:1px solid var(--line);background:var(--surface);color:var(--ink-soft);transition:all .18s ease;}
  .chip:hover{border-color:var(--brass);color:var(--forest);} .chip.active{background:var(--forest);border-color:var(--forest);color:var(--cream);}
  .chip.static{cursor:default;} .chip.static:hover{border-color:var(--line);color:var(--ink-soft);}

  /* Horizontal swipe carousels — one scroll-snapping row per section. */
  .grid{display:flex;gap:26px;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding-bottom:16px;scrollbar-width:thin;scrollbar-color:var(--line) transparent;}
  .grid::-webkit-scrollbar{height:8px;}
  .grid::-webkit-scrollbar-thumb{background:var(--line);border-radius:100px;}
  .grid::-webkit-scrollbar-track{background:transparent;}
  .card{display:flex;flex-direction:column;flex:0 0 auto;scroll-snap-align:start;}
  .grid.music .card{width:220px;}
  .grid.watch .card{width:360px;}
  .grid.read .card{width:320px;}
  .card .cv{position:relative;}
  .card .cv::after{content:"";position:absolute;inset:0;border:1px solid rgba(192,148,51,0);transition:border-color .2s ease;pointer-events:none;}
  .card:hover .cv::after{border-color:var(--brass);}
  .card.music .cv{aspect-ratio:1/1;} .card.watch .cv{aspect-ratio:16/9;} .card.read .cv{aspect-ratio:3/2;}
  .card .cv .play{width:52px;height:52px;} .card:hover .cv .play{transform:scale(1.06);background:rgba(22,35,19,0.34);}
  .card .meta-line{display:flex;align-items:center;gap:10px;margin-top:15px;font-size:10px;font-weight:600;letter-spacing:0.14em;text-transform:uppercase;color:var(--brass-deep);}
  .card .meta-line .sep{color:var(--line);} .card .meta-line .dur{margin-left:auto;color:var(--ink-mute);letter-spacing:0.08em;}
  .card h4{font-family:var(--display);font-weight:600;font-size:23px;line-height:1.14;color:var(--forest);margin-top:8px;letter-spacing:0.005em;}
  .card.music h4{font-size:21px;}
  .card .note{font-family:var(--serif);font-size:14.5px;color:var(--ink-soft);margin-top:8px;line-height:1.55;}
  .card .go{margin-top:14px;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--clay-deep);display:inline-flex;align-items:center;gap:7px;}
  .card .go .arr{transition:transform .2s ease;color:var(--brass-deep);} .card:hover .go .arr{transform:translateX(4px);}
  .badge{font-size:9.5px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:3px 9px;border:1px solid var(--brass);color:var(--brass-deep);}
  .badge.wildcard{border-color:var(--clay-deep);color:var(--clay-deep);background:rgba(152,68,23,0.07);}
  .empty{color:var(--ink-mute);font-style:italic;font-family:var(--serif);padding:30px 0;}

  /* ---- footer (forest) ---- */
  footer{margin-top:60px;background:var(--forest);color:var(--cream);padding:54px 40px 60px;text-align:center;position:relative;}
  footer::before{content:"";position:absolute;inset:12px;border:1px solid var(--line-on-dark);pointer-events:none;}
  footer .flr{color:var(--brass-soft);margin-bottom:20px;}
  footer .fmark{font-family:var(--display);font-weight:600;font-size:32px;color:var(--cream);}
  footer .ftag{font-family:var(--display);font-style:italic;font-size:18px;color:var(--cream-mute);margin-top:6px;}
  footer .links{margin-top:22px;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;color:var(--cream-mute);display:flex;gap:18px;justify-content:center;flex-wrap:wrap;}
  footer .links a{color:var(--brass-soft);}

  @media (max-width:820px){
    .hero-grid,.feature-read{grid-template-columns:1fr;}
    .hero-grid .cell,.feature-read .cell{border-right:0;border-bottom:1px solid var(--line);min-height:280px;}
    .feature-read .read-cover{order:-1;}
    .hero-text{padding:34px 6px;}
  }
  @media (max-width:600px){
    .wrap,.tabbar-inner{padding-left:22px;padding-right:22px;}
    .cover{padding:48px 22px 40px;} .fern{padding:0 22px;gap:16px;} .fern p{font-size:18px;}
    .almanac{padding:20px 22px 4px;} .almanac p{font-size:16.5px;}
    .panel{padding-top:40px;} .grid{gap:18px;}
    .grid.music .card{width:160px;}
    .grid.watch .card{width:280px;}
    .grid.read .card{width:260px;}
    .tabbar-inner{gap:0;} .tab{padding:20px 12px;}
  }
</style>
</head>
<body>
  <header class="cover">
    <div class="cover-in">
      <div class="eyebrow orn">__EDITION_LABEL__ &nbsp;&middot;&nbsp; __ISSUE____DATE_STR__</div>
      <h1>The Curated Canopy</h1>
      <div class="tagline">Human stories, good news &amp; the natural world</div>
      <div class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="200" height="20"><g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"><path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/><path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/><path d="M38 10 H10"/><path d="M162 10 H190"/></g><g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/><circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/><circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></div>
      <div class="meta" id="meta"></div>
    </div>
  </header>

  <div class="intro">
  <section class="fern" id="fern" style="display:none;">
    <div class="monogram">F</div>
    <div>
      <div class="eyebrow orn">A note from Fern</div>
      <p class="lead"><span id="greeting"></span> <span class="sign">Yours, Fern</span></p>
      <a class="history-link" id="history-link" href="https://www.britannica.com/on-this-day" target="_blank" rel="noopener" style="display:none;">This day in history &rarr;</a>
    </div>
  </section>

  <section class="puzzle" id="puzzle" style="display:none;">
    <div class="eyebrow orn" id="puzzle-label"></div>
    <p id="puzzle-prompt"></p>
    <div class="hint" id="puzzle-hint" style="display:none;"></div>
    <details>
      <summary>Reveal the answer</summary>
      <div class="answer" id="puzzle-answer"></div>
    </details>
    <div class="source" id="puzzle-source" style="display:none;"></div>
    <div class="prev" id="puzzle-prev" style="display:none;"></div>
  </section>
  </div>

  <div class="rule-flr"><span class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="190" height="19"><g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"><path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/><path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/><path d="M38 10 H10"/><path d="M162 10 H190"/></g><g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/><circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/><circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></span></div>

  <div class="wrap hero" id="hero-wrap" style="display:none;">
    <a class="hero-grid" id="hero" href="#"></a>
  </div>

  <div class="wrap" id="read-wrap" style="display:none;">
    <a class="feature-read" id="read" href="#" target="_blank"></a>
  </div>

  <nav class="tabbar" id="tabbar">
    <div class="tabbar-inner">
      <div class="tabs" id="tabs"></div>
    </div>
  </nav>

  <main class="wrap">
    <section class="panel active" data-panel="music">
      <div class="sec-head"><div class="eyebrow orn">Section One</div><h3>__SOUNDTRACK_LABEL__</h3>
        <div class="lede">Fresh picks from the music world to set the tone for your day.</div></div>
      <div class="chips" id="genres"></div>
      <div class="radio-bar">
        <span class="radio-orn" aria-hidden="true"></span>
        <button class="radio-play" id="radio-play" aria-label="Play FIP live radio">&#9654;</button>
        <div class="radio-info">
          <div class="radio-name">FIP<span class="radio-live">Live from Paris</span></div>
          <div class="radio-tag">Eclectic radio with famously good taste, streaming ad-free.</div>
        </div>
        <a class="radio-link" href="https://www.radiofrance.fr/fip" target="_blank" rel="noopener">radiofrance.fr/fip &rarr;</a>
      </div>
      <div class="grid music" id="music-grid"></div>
    </section>
    <section class="panel" data-panel="watch">
      <div class="sec-head"><div class="eyebrow orn">Section Two</div><h3>Worth Watching</h3>
        <div class="lede">Long, patient films for when you have a little time to spend.</div></div>
      <div class="grid watch" id="watch-grid"></div>
    </section>
    <section class="panel" data-panel="good_news">
      <div class="sec-head"><div class="eyebrow orn">Section Three</div><h3>Global Silver Linings</h3>
        <div class="lede">Stories that remind you the world is still full of good.</div></div>
      <div class="grid read" id="good_news-grid"></div>
    </section>
    <section class="panel" data-panel="discovery">
      <div class="sec-head"><div class="eyebrow orn">Section Four</div><h3>From the Archives</h3>
        <div class="lede">Forgotten places, hidden histories, and the science that rewires how you see the world.</div></div>
      <div class="grid read" id="discovery-grid"></div>
    </section>
    <section class="panel" data-panel="larder">
      <div class="sec-head"><div class="eyebrow orn">The Larder</div><h3>The Larder</h3>
        <div class="lede" id="larder-lede">Food news, trends, and a recipe worth cooking, gathered for the morning.</div></div>
      <div class="grid read" id="larder-grid"></div>
    </section>
  </main>

  <footer>
    <div class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="200" height="20"><g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"><path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/><path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/><path d="M38 10 H10"/><path d="M162 10 H190"/></g><g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/><circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/><circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></div>
    <div class="fmark">The Curated Canopy</div>
    <div class="ftag">Gathered twice daily by Fern</div>
    <div class="links"><a href="#">About</a><a href="./archive.html">The Archive</a><a href="./grove.html">The Grove</a><a href="#">Preferences</a></div>
  </footer>

<script id="data" type="application/json">__DATA_JSON__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const $ = (s,r=document)=>r.querySelector(s);
const ARR = '<span class="arr">&rarr;</span>';
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function safeUrl(u){try{const p=new URL(u,location.href);return ['http:','https:','mailto:'].includes(p.protocol)?p.href:'#';}catch(e){return '#';}}
function ytThumb(id){return 'https://img.youtube.com/vi/'+id+'/mqdefault.jpg';}
function ytWatch(id){return 'https://www.youtube.com/watch?v='+id;}

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
  // Morning-only, live edition only: reveal the self-updating "This day in history"
  // link. Hidden on archived /editions/ pages so old editions don't link to *today*.
  if(DATA.is_am && !/\/editions\//.test(location.pathname)) $('#history-link').style.display='';
})();

// Fern's daily puzzle — tap-to-reveal answer + last edition's answer
(function(){
  const p = DATA.puzzle, prev = DATA.prev_puzzle;
  if(!p && !prev) return;
  if(p){
    $('#puzzle-label').textContent = p.label || "Fern's Puzzle";
    $('#puzzle-prompt').textContent = p.prompt;
    $('#puzzle-answer').textContent = p.answer;
    if(p.hint){ $('#puzzle-hint').textContent = 'Hint: '+p.hint; $('#puzzle-hint').style.display=''; }
    var credit = p.credit || (p.source ? 'via '+p.source : '');
    if(credit){ $('#puzzle-source').textContent = credit; $('#puzzle-source').style.display=''; }
  } else {
    $('#puzzle-label').textContent = 'The Puzzle Corner';
    $('#puzzle-prompt').textContent = '';
    document.querySelector('#puzzle details').style.display='none';
  }
  if(prev && prev.answer){
    $('#puzzle-prev').innerHTML = '<span class="lbl">Last edition\\u2019s answer</span><b>'+esc(prev.answer)+'</b>';
    $('#puzzle-prev').style.display='';
  }
  $('#puzzle').style.display='';
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
    + '<div class="hero-text"><div class="eyebrow orn">'+kick+'</div><h2>'+esc(v.title)+'</h2>'
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
    + '<div class="hero-text"><div class="eyebrow orn">One Good Read'+(r.source?' &nbsp;&middot;&nbsp; '+esc(r.source):'')+'</div>'
    + '<h2>'+esc(r.title)+'</h2><p>'+esc(r.note)+'</p>'
    + '<span class="textlink">Read the essay '+ARR+'</span></div>';
  $('#read-wrap').style.display='';
})();

// Tabs
const TABS=[{k:'music',l:'Soundtrack'},{k:'watch',l:'Watch'},{k:'good_news',l:'Good News'},{k:'discovery',l:'Archives'}];
if(DATA.larder && ((DATA.larder.recipe)||(DATA.larder.news&&DATA.larder.news.length))) TABS.push({k:'larder',l:'The Larder'});
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
  +'<div class="meta-line">'+(v.wild?'<span class="badge wildcard">Random Pick</span>':'')+'<span>'+esc(v.channel||'Video')+'</span></div>'
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

// The Larder — the recipe (badged) first, then food news (morning only)
(function(){
  const L=DATA.larder; if(!L) return;
  const items=[];
  if(L.recipe && L.recipe.title) items.push({...L.recipe, _recipe:true});
  (L.news||[]).forEach(n=>items.push(n));
  if(!items.length) return;
  $('#larder-grid').innerHTML=items.map((it,i)=>
    '<a class="card read" href="'+esc(safeUrl(it.url))+'" target="_blank">'+cover(it.cover,i%4,'Food image',false)
    +'<div class="meta-line">'+(it._recipe?'<span class="badge">Recipe</span>':'')+'<span>'+esc(it.source||'')+'</span></div>'
    +'<h4>'+esc(it.title)+'</h4><div class="note">'+esc(it.note)+'</div>'
    +'<span class="go">'+(it._recipe?'Get the recipe ':'Read ')+ARR+'</span></a>').join('');
})();

renderGenres(); renderMusic();

// FIP live radio — lazy-created stream, toggled by the brass button
const RADIO_SRC='https://icecast.radiofrance.fr/fip-midfi.mp3';
let radio=null;
$('#radio-play').onclick=()=>{
  if(!radio){ radio=new Audio(RADIO_SRC); radio.preload='none'; }
  if(radio.paused){
    radio.play();
    $('#radio-play').innerHTML='&#9646;&#9646;';
    $('#radio-play').style.paddingLeft='0';
    document.body.classList.add('radio-on');
  } else {
    radio.pause();
    $('#radio-play').innerHTML='&#9654;';
    $('#radio-play').style.paddingLeft='3px';
    document.body.classList.remove('radio-on');
  }
};

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
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#EFE7D6;--paper-deep:#E5DCC4;--surface:#FCF7EB;
    --ink:#1B2716;--ink-soft:#3C4433;--ink-mute:#79735C;
    --forest:#1E2E1A;--forest-deep:#162313;
    --brass:#C09433;--brass-deep:#A87E28;--brass-soft:#D9B968;
    --clay:#B6541F;--clay-deep:#984417;
    --line:#DCD0B4;--line-on-dark:rgba(216,185,104,0.32);
    --cream:#F2EAD6;--cream-mute:#C6C3A6;
    --display:'Cormorant Garamond',Georgia,'Times New Roman',serif;
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  html{scroll-behavior:smooth;}
  body{font-family:var(--sans);background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh;}
  a{color:inherit;text-decoration:none;}
  .wrap{max-width:820px;margin:0 auto;padding:0 40px;}
  .eyebrow{font-size:11px;font-weight:600;letter-spacing:0.24em;text-transform:uppercase;color:var(--brass-soft);}
  .flr{display:inline-flex;color:var(--brass-soft);line-height:0;}
  .flr svg{display:block;}

  /* masthead */
  .cover{position:relative;background:var(--forest);color:var(--cream);text-align:center;padding:60px 40px 50px;overflow:hidden;}
  .cover::before{content:"";position:absolute;inset:14px;border:1px solid var(--line-on-dark);pointer-events:none;}
  .cover::after{content:"";position:absolute;inset:19px;border:1px solid rgba(216,185,104,0.14);pointer-events:none;}
  .cover-in{position:relative;}
  .cover .eyebrow{display:inline-flex;align-items:center;gap:11px;margin-bottom:18px;}
  .cover .eyebrow::before,.cover .eyebrow::after{content:"";width:6px;height:6px;background:var(--brass-soft);transform:rotate(45deg);}
  .cover h1{font-family:var(--display);font-weight:600;font-size:clamp(42px,7vw,74px);line-height:0.98;letter-spacing:0.01em;color:var(--cream);}
  .cover .tagline{font-family:var(--display);font-style:italic;font-weight:500;font-size:clamp(17px,2.3vw,22px);color:var(--cream-mute);margin-top:12px;}
  .cover .flr{margin-top:18px;}
  .cover .nav{margin-top:18px;display:flex;gap:22px;justify-content:center;flex-wrap:wrap;font-size:11.5px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;}
  .cover .nav a{color:var(--brass-soft);transition:color .15s ease;}
  .cover .nav a:hover{color:var(--cream);}

  /* year groups */
  .yeartag{display:flex;align-items:center;gap:16px;margin:40px 0 4px;}
  .yeartag .y{font-family:var(--display);font-style:italic;font-size:22px;color:var(--brass-deep);white-space:nowrap;}
  .yeartag .line{flex:1;height:1px;background:var(--brass);opacity:0.5;}

  .edition-list{border-top:1px solid var(--brass);}
  .edition-row{display:flex;align-items:center;gap:22px;padding:19px 4px;border-bottom:1px solid var(--line);transition:background .15s ease;}
  .edition-row:hover{background:var(--surface);}
  .edition-row:hover .edition-title{color:var(--clay-deep);}
  .edition-no{font-family:var(--display);font-style:italic;font-size:16px;color:var(--brass-deep);min-width:64px;flex-shrink:0;}
  .edition-info{flex:1;}
  .edition-title{font-family:var(--display);font-weight:600;font-size:23px;color:var(--forest);line-height:1.2;transition:color .15s ease;}
  .edition-title sup{font-size:0.5em;}
  .edition-tag{display:inline-block;padding:2px 11px;border:1px solid var(--brass);font-size:10px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--brass-deep);margin-left:12px;vertical-align:middle;}
  .edition-meta{font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:var(--ink-mute);margin-top:5px;}
  .edition-arr{color:var(--brass-deep);font-size:18px;flex-shrink:0;transition:transform .15s ease;}
  .edition-row:hover .edition-arr{transform:translateX(4px);}
  .empty{padding:60px 0;text-align:center;font-family:var(--display);font-style:italic;color:var(--ink-mute);font-size:21px;}

  footer{margin-top:60px;background:var(--forest);color:var(--cream);padding:48px 40px 56px;text-align:center;position:relative;}
  footer::before{content:"";position:absolute;inset:12px;border:1px solid var(--line-on-dark);pointer-events:none;}
  footer .flr{margin-bottom:18px;}
  footer .fmark{font-family:var(--display);font-weight:600;font-size:28px;color:var(--cream);}
  footer .ftag{font-family:var(--display);font-style:italic;font-size:17px;color:var(--cream-mute);margin-top:6px;}

  @media (max-width:600px){
    .wrap{padding:0 22px;} .cover{padding:42px 22px 38px;}
    .edition-row{gap:14px;} .edition-no{min-width:48px;font-size:14px;}
    .edition-title{font-size:19px;}
  }
</style>
</head>
<body>
<header class="cover">
  <div class="cover-in">
    <div class="eyebrow">The Curated Canopy &nbsp;&middot;&nbsp; The Archive</div>
    <h1>Every Edition</h1>
    <div class="tagline">All past issues, gathered here.</div>
    <div class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="190" height="19"><g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"><path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/><path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/><path d="M38 10 H10"/><path d="M162 10 H190"/></g><g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/><circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/><circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></div>
    <div class="nav">
      <a href="./index.html">&larr; Current edition</a>
      <a href="./grove.html">Wander The Grove &rarr;</a>
    </div>
  </div>
</header>
<div class="wrap">
__EDITION_LIST__
</div>
<footer>
  <div class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="200" height="20"><g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"><path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/><path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/><path d="M38 10 H10"/><path d="M162 10 H190"/></g><g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/><circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/><circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></div>
  <div class="fmark">The Curated Canopy</div>
  <div class="ftag">Gathered twice daily by Fern</div>
</footer>
</body>
</html>"""


def write_archive(editions_dir: Path, archive_path: Path) -> Path:
    """Scan editions_dir for saved editions and rebuild archive.html.

    Rows are grouped under italic 'Month Year' dividers, newest first.
    """
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
        groups: list[tuple[str, list[str]]] = []
        cur_key = None
        for d, is_am, fname in entries:
            key = (d.year, d.month)
            if key != cur_key:
                cur_key = key
                groups.append((f"{d.strftime('%B')} {d.year}", []))
            dt_fake = datetime.datetime(d.year, d.month, d.day, 7 if is_am else 18)
            ed_no = _edition_no(dt_fake, is_am)
            suffix = _day_suffix(d.day)
            date_str = f"{d.strftime('%B')} {d.day}<sup>{suffix}</sup> {d.year}"
            tag = "Morning" if is_am else "Evening"
            weekday = d.strftime("%A")
            groups[-1][1].append(
                f'<a class="edition-row" href="./editions/{fname}">'
                f'<div class="edition-no">{ed_no}</div>'
                f'<div class="edition-info">'
                f'<div class="edition-title">{date_str}<span class="edition-tag">{tag}</span></div>'
                f'<div class="edition-meta">{weekday}</div>'
                f'</div>'
                f'<span class="edition-arr">&rarr;</span>'
                f'</a>'
            )
        list_html = "\n".join(
            f'<div class="yeartag"><span class="y">{label}</span><span class="line"></span></div>'
            f'<div class="edition-list">{"".join(rows)}</div>'
            for label, rows in groups
        )

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
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#EFE7D6;--paper-deep:#E5DCC4;--surface:#FCF7EB;
    --ink:#1B2716;--ink-soft:#3C4433;--ink-mute:#79735C;
    --forest:#1E2E1A;--forest-deep:#162313;
    --brass:#C09433;--brass-deep:#A87E28;--brass-soft:#D9B968;
    --clay:#B6541F;--clay-deep:#984417;
    --line:#DCD0B4;--line-on-dark:rgba(216,185,104,0.32);
    --cream:#F2EAD6;--cream-mute:#C6C3A6;--radius:10px;
    --display:'Cormorant Garamond',Georgia,'Times New Roman',serif;
    --serif:'Newsreader',Georgia,'Times New Roman',serif;
    --sans:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  html{scroll-behavior:smooth;}
  body{font-family:var(--sans);background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh;}
  img{max-width:100%;display:block;}
  a{color:inherit;text-decoration:none;}
  .wrap{max-width:1180px;margin:0 auto;padding:0 36px;}
  .eyebrow{font-size:11px;font-weight:600;letter-spacing:0.24em;text-transform:uppercase;color:var(--brass-soft);}

  .flr{display:inline-flex;color:var(--brass-soft);line-height:0;}
  .flr svg{display:block;}

  /* masthead */
  .cover{position:relative;background:var(--forest);color:var(--cream);text-align:center;padding:54px 36px 44px;overflow:hidden;}
  .cover::before{content:"";position:absolute;inset:13px;border:1px solid var(--line-on-dark);pointer-events:none;}
  .cover::after{content:"";position:absolute;inset:18px;border:1px solid rgba(216,185,104,0.14);pointer-events:none;}
  .cover-in{position:relative;}
  .cover .eyebrow{display:inline-flex;align-items:center;gap:11px;margin-bottom:16px;}
  .cover .eyebrow::before,.cover .eyebrow::after{content:"";width:6px;height:6px;background:var(--brass-soft);transform:rotate(45deg);}
  .cover h1{font-family:var(--display);font-weight:600;font-size:clamp(46px,8vw,84px);line-height:0.98;letter-spacing:0.01em;color:var(--cream);}
  .cover .tagline{font-family:var(--display);font-style:italic;font-weight:500;font-size:clamp(17px,2.3vw,23px);color:var(--cream-mute);margin-top:12px;}
  .cover .flr{margin-top:18px;}
  .cover .nav{margin-top:18px;display:flex;gap:22px;justify-content:center;flex-wrap:wrap;font-size:11.5px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;}
  .cover .nav a{color:var(--brass-soft);transition:color .15s ease;}
  .cover .nav a:hover{color:var(--cream);}

  /* controls */
  .controls{position:sticky;top:0;z-index:50;background:rgba(239,231,214,0.92);backdrop-filter:blur(10px) saturate(120%);border-bottom:1px solid var(--brass);padding:15px 0;}
  .controls .wrap{display:flex;flex-direction:column;gap:11px;}
  .search{width:100%;font-family:var(--sans);font-size:14px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:100px;padding:12px 20px;outline:none;transition:border-color .15s ease;}
  .search:focus{border-color:var(--brass);}
  .search::placeholder{color:var(--ink-mute);}
  .chips{display:flex;flex-wrap:wrap;gap:7px;}
  .chip{cursor:pointer;font-family:var(--sans);font-size:11.5px;font-weight:600;letter-spacing:0.03em;padding:7px 14px;border:1px solid var(--line);background:var(--surface);color:var(--ink-soft);transition:all .16s ease;text-transform:capitalize;}
  .chip:hover{border-color:var(--brass);color:var(--forest);}
  .chip.active{background:var(--forest);border-color:var(--forest);color:var(--cream);}
  .chip.mood.active{background:var(--brass);border-color:var(--brass);color:var(--forest-deep);}
  .chip-row-label{font-size:9.5px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:var(--ink-mute);align-self:center;margin-right:4px;}

  .count{padding:22px 0 4px;font-family:var(--display);font-style:italic;font-size:19px;color:var(--ink-mute);}

  /* feed */
  .feed{column-count:3;column-gap:24px;padding:8px 0 24px;}
  .card{break-inside:avoid;margin-bottom:24px;background:var(--surface);border:1px solid var(--line);overflow:hidden;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease;}
  .card:hover{transform:translateY(-3px);box-shadow:0 12px 30px rgba(22,35,19,0.13);border-color:var(--brass);}
  .card-link{display:block;color:inherit;}
  .cv{position:relative;width:100%;overflow:hidden;}
  .cv .ph{display:block;width:100%;}
  .cv::after{content:"";position:absolute;inset:0;border:1px solid rgba(192,148,51,0);transition:border-color .2s ease;pointer-events:none;}
  .card:hover .cv::after{border-color:rgba(192,148,51,0.55);}
  .play{position:absolute;inset:0;margin:auto;width:50px;height:50px;border-radius:50%;border:1.5px solid rgba(247,242,230,0.92);background:rgba(22,35,19,0.24);display:flex;align-items:center;justify-content:center;}
  .play::after{content:"";margin-left:3px;border-style:solid;border-width:7px 0 7px 12px;border-color:transparent transparent transparent rgba(247,242,230,0.95);}
  .body{padding:16px 18px 0;}
  .meta-line{display:flex;align-items:center;gap:9px;font-size:9.5px;font-weight:600;letter-spacing:0.13em;text-transform:uppercase;color:var(--brass-deep);flex-wrap:wrap;}
  .meta-line .sep{color:var(--line);}
  .badge{font-size:8.5px;font-weight:700;letter-spacing:0.11em;text-transform:uppercase;padding:2px 8px;border:1px solid var(--brass);color:var(--brass-deep);}
  .badge.wildcard{border-color:var(--clay-deep);color:var(--clay-deep);background:rgba(152,68,23,0.07);}
  .card h4{font-family:var(--display);font-weight:600;font-size:21px;line-height:1.16;color:var(--forest);margin-top:9px;letter-spacing:0.005em;}
  .note{font-family:var(--serif);font-size:14px;color:var(--ink-soft);margin-top:8px;line-height:1.52;}
  .moods{display:flex;flex-wrap:wrap;gap:9px;margin-top:11px;}
  .moodtag{font-size:8.5px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--brass-deep);opacity:0.8;}
  .from{padding:13px 18px 16px;font-size:10px;letter-spacing:0.05em;color:var(--ink-mute);text-transform:uppercase;}
  .from a{color:var(--brass-deep);font-weight:600;}

  footer{margin-top:30px;background:var(--forest);color:var(--cream);padding:46px 36px 54px;text-align:center;position:relative;}
  footer::before{content:"";position:absolute;inset:12px;border:1px solid var(--line-on-dark);pointer-events:none;}
  footer .flr{margin-bottom:18px;}
  footer .fmark{font-family:var(--display);font-weight:600;font-size:28px;color:var(--cream);}
  footer .ftag{font-family:var(--display);font-style:italic;font-size:17px;color:var(--cream-mute);margin-top:6px;}

  @media (max-width:900px){ .feed{column-count:2;} }
  @media (max-width:700px){
    /* Keep the sticky filter bar compact: one swipeable line per chip row. */
    .controls{padding:10px 0;}
    .controls .wrap{gap:8px;}
    .search{padding:9px 16px;font-size:13px;}
    .chips{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;padding-bottom:2px;}
    .chips::-webkit-scrollbar{display:none;}
    .chip{flex:0 0 auto;white-space:nowrap;}
    .chip-row-label{flex:0 0 auto;}
  }
  @media (max-width:600px){ .wrap{padding:0 22px;} .cover{padding:40px 22px 30px;} .feed{column-count:1;} }
</style>
</head>
<body>
<header class="cover">
  <div class="cover-in">
    <div class="eyebrow">The Curated Canopy &nbsp;&middot;&nbsp; The Grove</div>
    <h1>The Grove</h1>
    <div class="tagline">Wander every story, song &amp; film we&#39;ve ever gathered.</div>
    <div class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="190" height="19"><g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"><path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/><path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/><path d="M38 10 H10"/><path d="M162 10 H190"/></g><g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/><circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/><circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></div>
    <div class="nav">
      <a href="./index.html">&larr; Current edition</a>
      <a href="./archive.html">The Archive</a>
    </div>
  </div>
</header>

<div class="controls">
  <div class="wrap">
    <input class="search" id="search" type="search" placeholder="Search The Grove — a title, a source, a feeling…" autocomplete="off">
    <div class="chips" id="section-chips"></div>
    <div class="chips" id="mood-chips"></div>
    <div class="chips"><button class="chip" id="shuffle-btn" type="button">&#8635;&nbsp; Shuffle</button></div>
  </div>
</div>

<main class="wrap">
  <div class="count" id="count"></div>
  <div class="feed" id="feed"></div>
  <div id="sentinel" style="height:1px;"></div>
</main>

<footer>
  <div class="flr" aria-hidden="true"><svg viewBox="0 0 200 20" width="200" height="20"><g fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"><path d="M100 10 C84 10 78 3.5 64 3.5 C52 3.5 48 10 38 10"/><path d="M100 10 C116 10 122 3.5 136 3.5 C148 3.5 152 10 162 10"/><path d="M38 10 H10"/><path d="M162 10 H190"/></g><g fill="currentColor"><path d="M100 4 l4.5 6 l-4.5 6 l-4.5 -6 z"/><circle cx="10" cy="10" r="1.6"/><circle cx="190" cy="10" r="1.6"/><circle cx="64" cy="3.5" r="1.7"/><circle cx="136" cy="3.5" r="1.7"/></g></svg></div>
  <div class="fmark">The Curated Canopy</div>
  <div class="ftag">Gathered twice daily by Fern</div>
</footer>

<script>
const $ = (s,r=document)=>r.querySelector(s);
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function safeUrl(u){try{const p=new URL(u,location.href);return ['http:','https:','mailto:'].includes(p.protocol)?p.href:'#';}catch(e){return '#';}}
const SECTION_LABEL={music:'Soundtrack',videos:'Worth Watching',good_news:'Good News',discovery:'From the Archives',featured_read:'One Good Read',food:'The Larder'};

let ALL=[], MOODS=[], SECTIONS=[];
let activeSection=null, activeMoods=new Set(), query='';
let filtered=[], shown=0;
const BATCH=24;

// The Grove opens SHUFFLED — a serendipitous wander, not newest-first. ALL is
// shuffled once on load (and on demand via the Shuffle button); applyFilters()
// preserves that order, so Everything and every section/mood filter come up
// randomized. Shuffling once keeps the order stable while you scroll (load-more
// won't reorder what's on screen); reloading gives a fresh order.
function shuffle(a){
  for(let i=a.length-1;i>0;i--){ const j=Math.floor(Math.random()*(i+1)); [a[i],a[j]]=[a[j],a[i]]; }
  return a;
}

function fmtDate(iso,ampm){
  try{const d=new Date(iso+'T12:00:00');
    return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})+' · '+(ampm==='morning'?'Morning':'Evening');
  }catch(e){return iso;}
}

function cardHTML(it){
  const isVid=it.section==='videos';
  const cv=it.image
    ? '<div class="cv"><img class="ph" src="'+esc(safeUrl(it.image))+'" alt="" loading="lazy">'+(isVid?'<span class="play"></span>':'')+'</div>'
    : '';
  const moods=(it.moods||[]).map(m=>'<span class="moodtag">'+esc(m)+'</span>').join('');
  const src=it.source?'<span>'+esc(it.source)+'</span><span class="sep">·</span>':'';
  return '<div class="card"><a class="card-link" href="'+esc(safeUrl(it.url))+'" target="_blank" rel="noopener">'
    + cv
    + '<div class="body">'
    +   '<div class="meta-line">'+(it.wild?'<span class="badge wildcard">Random Pick</span>':'')+src+'<span>'+esc(SECTION_LABEL[it.section]||it.section)+'</span></div>'
    +   '<h4>'+esc(it.title)+'</h4>'
    +   (it.note?'<div class="note">'+esc(it.note)+'</div>':'')
    +   (moods?'<div class="moods">'+moods+'</div>':'')
    + '</div></a>'
    + '<div class="from">From the <a href="./editions/'+esc(it.edition)+'">'+esc(fmtDate(it.date,it.ampm))+'</a> edition</div></div>';
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
  if(n===0){ $('#feed').innerHTML='<div class="count">Nothing matches just yet — try a different mood or search.</div>'; return; }
  renderMore();
}

function renderMore(){
  const next=filtered.slice(shown,shown+BATCH);
  if(!next.length) return;
  const frag=document.createElement('div');
  frag.innerHTML=next.map(it=>cardHTML(it)).join('');
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
$('#shuffle-btn').addEventListener('click',()=>{shuffle(ALL);applyFilters();window.scrollTo({top:0,behavior:'smooth'});});

new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting)renderMore();});},{rootMargin:'600px'}).observe($('#sentinel'));

fetch('./grove.json',{cache:'no-cache'}).then(r=>r.json()).then(d=>{
  ALL=shuffle(d.items||[]); MOODS=d.moods||[]; SECTIONS=d.sections||[];
  // hide mood chips entirely until at least one item carries a mood
  if(!ALL.some(it=>(it.moods||[]).length)) MOODS=[];
  renderChips(); applyFilters();
}).catch(()=>{ $('#feed').innerHTML='<div class="count">The Grove is still growing — check back soon.</div>'; });
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
    ("food",          "The Larder"),
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

    def add(section, title, note, url, image, source, genre="", wild=False):
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
            "wild":    bool(wild),
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
            f"https://img.youtube.com/vi/{vid}/mqdefault.jpg" if vid else "",
            v.get("channel"), wild=v.get("wild", False))
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
    ld = data.get("larder") or {}
    rec = ld.get("recipe")
    if rec and rec.get("title"):
        add("food", rec.get("title"), rec.get("note"), rec.get("url"),
            rec.get("cover"), rec.get("source"))
    for n in (ld.get("news") or []):
        add("food", n.get("title"), n.get("note"), n.get("url"),
            n.get("cover"), n.get("source"))
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
        "generated_at": datetime.datetime.now(EDITION_TZ).isoformat(),
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
        dt = datetime.datetime.fromisoformat(fetched_at).astimezone(EDITION_TZ)
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
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )

    return (
        _PAGE
        .replace("__EDITION_LABEL__", edition_label)
        .replace("__ISSUE__", issue)
        .replace("__DATE_STR__", date_str)
        .replace("__SOUNDTRACK_LABEL__",
                 "The Morning Soundtrack" if is_am else "The Evening Soundtrack")
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
        dt = datetime.datetime.fromisoformat(fetched_at).astimezone(EDITION_TZ)
        slug = _edition_slug(dt, is_am)
        (EDITIONS_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
    except Exception as exc:
        print(f"[webpage] Could not save dated edition: {exc}")

    write_archive(EDITIONS_DIR, ARCHIVE_HTML)

    # Rebuild The Grove (aggregates every saved edition) and AUTOMATICALLY
    # mood-tag this edition's new items so they're immediately sortable by mood
    # in the Grove. tag_grove_moods() is incremental — it only tags items that
    # don't yet have moods — so every edition's freshly-added items get tagged
    # on the same run, and a transient failure self-heals on the next run
    # (the still-untagged items are simply retried). Tagging never blocks the
    # edition from publishing: if there's no CLAUDE_API_KEY we skip quietly,
    # and any real error is logged as a warning rather than raised.
    build_grove()
    _autotag_grove()

    return EDITION_HTML


def _autotag_grove() -> None:
    """Mood-tag any untagged Grove items (best-effort, never raises)."""
    if not os.environ.get("CLAUDE_API_KEY"):
        print("[webpage] No CLAUDE_API_KEY — Grove items will be mood-tagged on the next run with a key.")
        return
    try:
        import curator
        tagged = curator.tag_grove_moods(GROVE_JSON)
        print(f"[webpage] Grove auto-tagged {tagged} new item(s) with moods.")
    except Exception as exc:
        print(f"[webpage] WARN — Grove mood tagging failed (will retry next run): {exc}")


def main() -> None:
    if not CURATED_FILE.exists():
        raise FileNotFoundError(f"{CURATED_FILE} not found. Run fetcher.py first.")
    curated = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
    path = write_edition(curated)
    print(f"[webpage] Full edition written -> {path}")


if __name__ == "__main__":
    main()
