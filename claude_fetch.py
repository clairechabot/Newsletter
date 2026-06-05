"""Claude server-side web-fetch extractor.

Adapted from the daily-briefing engine (briefing/sources/claude_fetch.py).
Instead of fragile CSS scraping, we ask Claude to fetch a music site and
return the *actual* newest posts — real artist name, album/track title,
genre, and a cover image — as strict JSON. This is the fix for the old
"generic front page, no real titles" music bug.

Reconciled to Newsletter conventions:
  - reads CLAUDE_API_KEY (not ANTHROPIC_API_KEY)
  - returns plain Newsletter music dicts (not briefing.models.Item)
  - hardcodes claude-sonnet-4-6 to match curator.CLAUDE_MODEL
"""
from __future__ import annotations
import os
import json
import re

import anthropic

MODEL = "claude-sonnet-4-6"  # matches curator.CLAUDE_MODEL


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])


_PROMPT = (
    "Fetch this music site and extract its NEWEST posts/features: {url}\n"
    "For each post, identify the ACTUAL artist name, the album / track / session "
    "title, the primary genre, and the post's cover or lead image URL.\n"
    "Skip site navigation, ads, and 'about'/'shop' pages — only real music posts.\n"
    "Return ONLY valid JSON, no markdown fences:\n"
    '{{"items": [{{"title": "Artist — Album/Track", "url": "https://...", '
    '"summary": "one evocative line", "genre": "primary genre", '
    '"cover_url": "https://..."}}]}}'
)


def fetch_music_items(url: str, source_name: str, max_items: int = 8) -> list[dict]:
    """Return up to `max_items` real music posts from `url` as Newsletter dicts.

    Raises on hard API/JSON failure so the caller can fall back per-source."""
    client = _client()
    # Anthropic server-side web-fetch tool. If a future SDK changes the tool
    # type string or beta header, update these two values per Anthropic docs.
    msg = client.messages.create(
        model=MODEL, max_tokens=1500,
        tools=[{"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3}],
        extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        messages=[{"role": "user", "content": _PROMPT.format(url=url)}],
    )
    text = "".join(
        b.text for b in msg.content if getattr(b, "type", "") == "text"
    )
    text = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)
    data = json.loads(text)

    out: list[dict] = []
    for it in data.get("items", [])[:max_items]:
        if not it.get("url"):
            continue
        out.append({
            "source": "music",
            "source_name": source_name,
            "title": it.get("title", "(untitled)"),
            "url": it["url"],
            "snippet": it.get("summary", ""),
            "genre": it.get("genre", ""),
            "cover_url": it.get("cover_url", ""),
            "embed_url": None,  # filled later by _find_music_embed
        })
    return out
