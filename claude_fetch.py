"""Claude-assisted music extraction.

Robust two-step replacement for the brittle CSS scrapers:
  1. fetcher fetches the page with the hardened http_fetch (browser UA + retries)
     and hands us the candidate links (anchor text + absolute URL).
  2. Claude (a plain message call — no beta server tools) picks the entries that
     are real, recent music posts and formats them as "Artist — Album/Track"
     with a best-guess genre.

This avoids the server-side web_fetch beta tool (which returned empty responses
in practice) while still getting REAL titles instead of a generic front page.

Reconciled to Newsletter conventions:
  - reads CLAUDE_API_KEY (not ANTHROPIC_API_KEY)
  - returns plain Newsletter music dicts
  - uses claude-sonnet-4-6 (matches curator.CLAUDE_MODEL)
"""
from __future__ import annotations
import os
import json
import re

import anthropic

MODEL = "claude-sonnet-4-6"  # matches curator.CLAUDE_MODEL


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])


def _strip_fences(text: str) -> str:
    return re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)


def extract_music_from_links(
    source_name: str,
    page_url: str,
    links: list[tuple[str, str]],
    max_items: int = 8,
) -> list[dict]:
    """Given (anchor_text, absolute_url) pairs scraped from a music site, return
    up to `max_items` real music posts as Newsletter dicts.

    Raises on hard API/JSON failure so the caller can fall back per-source."""
    if not links:
        return []

    listing = "\n".join(f"- {text} | {url}" for text, url in links)
    prompt = (
        f"These are links scraped from the music site \"{source_name}\" "
        f"({page_url}). Identify the entries that are REAL, recent music posts — "
        f"album reviews, artist features, new releases, live sessions. Ignore "
        f"navigation, categories, tags, shop, about, login, and social links.\n\n"
        f"Links (anchor text | url):\n{listing}\n\n"
        f"Return ONLY JSON, no markdown fences:\n"
        f'{{"items": [{{"title": "Artist — Album/Track (or the post title)", '
        f'"url": "<one of the urls above>", "summary": "one short line", '
        f'"genre": "best-guess primary genre"}}]}}\n'
        f"Limit to the {max_items} most relevant. If none are music posts, "
        f'return {{"items": []}}.'
    )

    msg = _client().messages.create(
        model=MODEL, max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    data = json.loads(_strip_fences(text))

    valid_urls = {u for _, u in links}
    out: list[dict] = []
    for it in data.get("items", [])[:max_items]:
        url = it.get("url", "")
        if url not in valid_urls:  # guard against hallucinated links
            continue
        out.append({
            "source": "music",
            "source_name": source_name,
            "title": it.get("title", "(untitled)"),
            "url": url,
            "snippet": it.get("summary", ""),
            "genre": it.get("genre", ""),
            "cover_url": "",      # filled later by _find_embed_and_cover (og:image)
            "embed_url": None,    # filled later by _find_embed_and_cover
        })
    return out
