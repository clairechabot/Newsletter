"""
Newsletter Curator — Audit & Curation Layer
--------------------------------------------
Uses Claude to:
  1. Generate "Why Watch" descriptions for YouTube videos.
  2. Cluster videos into 3-4 creative themes.
  3. Run Music Vibe Check and Good News silver linings.
  4. Generate Fern's daily greeting.

Required environment variable:
    CLAUDE_API_KEY
"""

import json
import os
import textwrap
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_MODEL = "claude-sonnet-4-6"
THEME_COUNT_MIN, THEME_COUNT_MAX = 3, 4


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def build_claude_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])


# ---------------------------------------------------------------------------
# YouTube Audit
# ---------------------------------------------------------------------------

_YOUTUBE_AUDIT_SYSTEM = textwrap.dedent("""
You are an enthusiastic but discerning video curator writing for a newsletter audience
that values their time. Your tone is warm, specific, and never hypey.

For each YouTube video provided, write a "Why Watch" description: 2-3 tight sentences
that explain exactly what makes this video worth opening — the specific insight,
the creator's angle, the practical takeaway, or the emotional hook.
Avoid vague praise ("this is amazing!"). Be concrete and specific.

Return ONLY a valid JSON array, one element per video in input order:
[
  {
    "video_id": "<video_id>",
    "why_watch": "<2-3 sentence description>"
  },
  ...
]

Do not include any text outside the JSON array.
""").strip()


def _build_youtube_audit_user_message(videos: list[dict]) -> str:
    items = []
    for i, v in enumerate(videos, 1):
        is_wildcard = v.get("source") == "youtube_trending"
        label = " [WILDCARD — Trending Pick]" if is_wildcard else ""
        _dur = v.get("duration_seconds", 0)
        items.append(
            f"--- Video {i}{label} ---\n"
            f"ID: {v['video_id']}\n"
            f"Title: {v['title']}\n"
            f"Channel: {v['channel_title']}\n"
            f"Duration: {_dur // 60}m {_dur % 60}s\n"
            f"Views: {v.get('view_count', 'N/A')}\n"
            f"Description snippet: {v.get('description', '')[:400]}"
        )
    return "\n\n".join(items)


def audit_youtube_videos(client: anthropic.Anthropic, videos: list[dict]) -> list[dict]:
    """
    Generate a 'Why Watch' description for each YouTube video.
    Returns each video enriched with a 'why_watch' field.
    """
    if not videos:
        return []

    print(f"[Audit/YouTube] Generating 'Why Watch' for {len(videos)} video(s) …")

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=_YOUTUBE_AUDIT_SYSTEM,
        messages=[{"role": "user", "content": _build_youtube_audit_user_message(videos)}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        results: list[dict] = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [warn] JSON parse error in YouTube audit: {exc}. Returning videos as-is.")
        return videos

    id_to_why = {r["video_id"]: r.get("why_watch", "") for r in results}
    enriched = []
    for v in videos:
        enriched.append({**v, "why_watch": id_to_why.get(v["video_id"], "")})

    return enriched


# ---------------------------------------------------------------------------
# Cross-Platform Thematic Clustering
# ---------------------------------------------------------------------------

_CLUSTER_SYSTEM = textwrap.dedent("""
You are a creative newsletter editor with a talent for finding unexpected thematic
connections across different types of content.

You will receive a batch of YouTube videos.
Your task: group all items into exactly 3 or 4 thematic clusters that will become
newsletter sections. The themes must be:

  • FUN and CREATIVE — real section names (e.g. "The Daily Crust", "Digital Zen",
    "Cozy Corners", "Rabbit Holes Worth Falling Down") — NOT generic labels like
    "Food Content" or "Tech Videos".
  • THEMATICALLY COHERENT — items grouped by subject matter, mood, or angle.
  • The item marked [WILDCARD] must be placed into whichever theme fits it best.

Return ONLY valid JSON, exactly in this shape:
{
  "themes": [
    {
      "name": "<creative theme name>",
      "emoji": "<single emoji that best represents this theme's mood or subject>",
      "tagline": "<one punchy sentence that teases what's inside>",
      "items": [
        {
          "item_id": "<video 'video_id'>",
          "platform": "youtube",
          "is_wildcard": <true | false>
        },
        ...
      ]
    },
    ...
  ]
}

Do not include any text outside the JSON object.
""").strip()


def _build_cluster_user_message(youtube_videos: list[dict]) -> str:
    lines = ["## YouTube Videos\n"]
    for v in youtube_videos:
        is_wildcard = v.get("source") == "youtube_trending"
        label = " [WILDCARD]" if is_wildcard else ""
        lines.append(
            f"- ID: {v['video_id']}{label} | {v['channel_title']} | \"{v['title']}\"\n"
            f"  Why Watch: {v.get('why_watch', v.get('description', ''))[:200]}"
        )
    return "\n".join(lines)


def cluster_content(
    client: anthropic.Anthropic,
    youtube_videos: list[dict],
) -> list[dict]:
    """
    Group YouTube videos into 3-4 creative themes.
    Returns a list of theme dicts, each with full item objects embedded.
    """
    print(f"[Curator] Clustering {len(youtube_videos)} videos into {THEME_COUNT_MIN}–{THEME_COUNT_MAX} themes …")

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=_CLUSTER_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": _build_cluster_user_message(youtube_videos),
            }
        ],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        cluster_data: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [warn] JSON parse error in clustering: {exc}. Returning flat list.")
        return [
            {
                "name": "This Week's Picks",
                "tagline": "A curated mix of the best content.",
                "items": youtube_videos,
            }
        ]

    youtube_map: dict[str, dict] = {v["video_id"]: v for v in youtube_videos}

    themes: list[dict] = []
    for theme in cluster_data.get("themes", []):
        resolved_items: list[dict] = []
        for ref in theme.get("items", []):
            item_id = ref.get("item_id", "")
            full_item = youtube_map.get(item_id)

            if full_item is None:
                print(f"  [warn] Could not resolve item_id '{item_id}' for theme '{theme['name']}'")
                continue

            resolved_items.append(
                {**full_item, "is_wildcard": ref.get("is_wildcard", False)}
            )

        themes.append(
            {
                "name": theme.get("name", "Untitled Theme"),
                "emoji": theme.get("emoji", ""),
                "tagline": theme.get("tagline", ""),
                "items": resolved_items,
            }
        )

    print(f"[Curator] Created {len(themes)} theme(s):")
    for t in themes:
        print(f"  • {t['name']} ({len(t['items'])} items)")

    return themes


# ---------------------------------------------------------------------------
# Music Audit — Vibe Check
# ---------------------------------------------------------------------------

_MUSIC_AUDIT_SYSTEM = textwrap.dedent("""
You are a music journalist with an ear for mood and atmosphere.
For each music article provided, write a single-sentence "Vibe Check" that captures
the emotional energy of the piece — something evocative and specific, not generic.

Good examples:
  "Perfect for a rainy Sunday morning with something warm in your hands."
  "High-energy indie-pop that makes the commute feel like a montage."
  "The sonic equivalent of golden-hour light through dusty blinds."

Bad examples (too vague):
  "Great music for any occasion."
  "An interesting read about music."

Return ONLY a valid JSON array, one element per article in input order:
[
  {
    "index": <integer, 0-based>,
    "vibe_check": "<one evocative sentence>"
  },
  ...
]

Do not include any text outside the JSON array.
""").strip()


def audit_music_articles(client: anthropic.Anthropic, articles: list[dict]) -> list[dict]:
    """
    Generate a one-sentence Vibe Check for each music article.
    Returns each article enriched with a 'vibe_check' field.
    """
    if not articles:
        return []

    print(f"[Audit/Music] Generating Vibe Checks for {len(articles)} article(s) …")

    items_text = []
    for i, art in enumerate(articles):
        items_text.append(
            f"--- Article {i} ---\n"
            f"Source: {art.get('source_name', 'Unknown')}\n"
            f"Title: {art['title']}\n"
            f"Snippet: {art.get('snippet', '(no snippet)')}"
        )
    user_message = "\n\n".join(items_text)

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=_MUSIC_AUDIT_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        results: list[dict] = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [warn] JSON parse error in Music audit: {exc}. Returning articles as-is.")
        return articles

    index_to_vibe = {r["index"]: r.get("vibe_check", "") for r in results}
    enriched = []
    for i, art in enumerate(articles):
        enriched.append({**art, "vibe_check": index_to_vibe.get(i, "")})

    return enriched


# ---------------------------------------------------------------------------
# Good News Audit — Reason to be Hopeful
# ---------------------------------------------------------------------------

_GOOD_NEWS_SYSTEM = textwrap.dedent("""
You are an optimistic editor writing for a newsletter whose readers appreciate
uplifting, meaningful stories. Your tone is warm, grounded, and never saccharine.

For each news article headline provided, write a "Reason to be Hopeful" summary
of 1-2 tight sentences that explains why this story matters and why it is
genuinely encouraging.

Prioritise the nature/science/animal rescue angle when it exists in the headline —
these resonate most with readers who care about gardening and wholesome content.
Avoid corporate-speak, hype, or empty positivity.

Return ONLY a valid JSON array, one element per article in input order:
[
  {
    "index": <integer, 0-based>,
    "reason": "<1-2 sentence Reason to be Hopeful>"
  },
  ...
]

Do not include any text outside the JSON array.
""").strip()


def audit_good_news_articles(
    client: anthropic.Anthropic, articles: list[dict]
) -> list[dict]:
    """
    Generate a 'Reason to be Hopeful' summary for each good news article.
    Returns each article enriched with a 'reason' field.
    """
    if not articles:
        return []

    print(f"[Audit/GoodNews] Generating summaries for {len(articles)} article(s) …")

    items_text = "\n\n".join(
        f"--- Article {i} ---\nSource: {a.get('source_name', '')}\nHeadline: {a['title']}"
        for i, a in enumerate(articles)
    )

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=_GOOD_NEWS_SYSTEM,
        messages=[{"role": "user", "content": items_text}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        results: list[dict] = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [warn] JSON parse error in Good News audit: {exc}. Returning as-is.")
        return articles

    index_to_reason = {r["index"]: r.get("reason", "") for r in results}
    return [{**a, "reason": index_to_reason.get(i, "")} for i, a in enumerate(articles)]


# ---------------------------------------------------------------------------
# Discovery Audit — Fern's Note (History/Mystery + Science)
# ---------------------------------------------------------------------------

_DISCOVERY_AUDIT_SYSTEM = textwrap.dedent("""
You are Fern — the AI curator behind The Curated Canopy newsletter.
Personality: sophisticated, cozy, warm, slightly witty. Never cringe or hypey.

For each article provided — either a history/mystery piece or a science story —
write a "Fern's Note" of 1-2 tight sentences revealing the most surprising or
evocative angle: the detail that makes it worth stopping for.

History/mystery articles: lean into the eerie, the forgotten, the curious.
Science articles: lean into the wonder, the implication, the human story.

Return ONLY a valid JSON array, one element per article in input order:
[
  {
    "index": <integer, 0-based>,
    "ferns_note": "<1-2 sentence Fern's Note>"
  },
  ...
]

Do not include any text outside the JSON array.
""").strip()


def audit_discovery_articles(
    client: anthropic.Anthropic, articles: list[dict]
) -> list[dict]:
    """
    Generate a "Fern's Note" for each discovery article (history/mystery or science).
    Returns each article enriched with a 'ferns_note' field.
    """
    if not articles:
        return []

    print(f"[Audit/Discovery] Generating Fern's Notes for {len(articles)} article(s) …")

    items_text = "\n\n".join(
        f"--- Article {i} ---\n"
        f"Category: {a.get('category', 'unknown')}\n"
        f"Source: {a.get('source_name', '')}\n"
        f"Headline: {a['title']}\n"
        f"Snippet: {a.get('snippet', '')}"
        for i, a in enumerate(articles)
    )

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=768,
        system=_DISCOVERY_AUDIT_SYSTEM,
        messages=[{"role": "user", "content": items_text}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        results: list[dict] = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [warn] JSON parse error in Discovery audit: {exc}. Returning as-is.")
        return articles

    index_to_note = {r["index"]: r.get("ferns_note", "") for r in results}
    return [{**a, "ferns_note": index_to_note.get(i, "")} for i, a in enumerate(articles)]


# ---------------------------------------------------------------------------
# Fern — Daily Greeting & Top Pick
# ---------------------------------------------------------------------------

_FERN_GREETING_SYSTEM = textwrap.dedent("""
You are Fern — the AI curator behind a newsletter called The Curated Canopy.
Personality: sophisticated, cozy, warm, slightly witty. Never cringe or overly cheerful.

Write ONE sentence as Fern's daily note to open the newsletter.
- AM greeting: reference morning rituals (bread, coffee, birds, morning light) and tease
  the stories inside. Be specific and evocative.
- PM greeting: reference winding down (sunset, closing tabs, soft music) and invite
  quiet reading. Be gentle and slightly poetic.

Also write a short, original title for this edition — Fern's own name for today's
digest, inspired by the themes and mood of the content. Think of it like a newspaper
editor naming an issue. It should be evocative, slightly poetic, and under 50 chars.
Do NOT copy any existing headline — invent something that captures the spirit of the day.

Examples of good edition titles:
  "Quiet Corners & Loud Ideas"
  "The Week the Internet Was Kind"
  "Small Wonders, Big Skies"

Return ONLY valid JSON:
{
  "greeting": "<one sentence daily note from Fern>",
  "top_pick_title": "<Fern's original title for this edition, max 50 chars>"
}

Do not include any text outside the JSON object.
""").strip()


def generate_fern_greeting(
    client: anthropic.Anthropic,
    is_am: bool,
    themes: list[dict],
    morning_soundtrack: list[dict],
    global_silver_linings: list[dict],
    discovery_articles: list[dict] | None = None,
) -> dict:
    """
    Generate Fern's one-sentence daily note and pick the top item title
    for the email subject line.
    """
    time_label = "AM (morning edition)" if is_am else "PM (evening edition)"
    lines = [f"Time of day: {time_label}\n\n## Content in today's digest:\n"]

    for theme in themes:
        lines.append(f"\nTheme: {theme['name']}")
        for item in theme.get("items", []):
            lines.append(f"  - {item.get('title', '')}")

    for art in morning_soundtrack:
        lines.append(f"  - [Music] {art.get('title', '')}")

    for art in global_silver_linings:
        lines.append(f"  - [Good News] {art.get('title', '')}")

    for art in (discovery_articles or []):
        category = art.get("category", "discovery")
        label = "From the Archives" if category == "history" else "The Laboratory"
        lines.append(f"  - [{label}] {art.get('title', '')}")

    print("[Fern] Generating greeting and top pick …")
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        system=_FERN_GREETING_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(lines)}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fallback = (
            "Good morning! Fresh stories are waiting — let's dig in."
            if is_am
            else "The day is winding down. Let's close it with something worth reading."
        )
        return {"greeting": fallback, "top_pick_title": ""}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_curation(raw_data: dict) -> dict:
    """
    Full audit + curation pipeline.

    Input:  the dict produced by fetcher.main()
    Output: enriched dict with 'themes' and optional 'morning_soundtrack' section
    """
    client = build_claude_client()

    # 1. YouTube audit — generate Why Watch
    youtube_videos = raw_data.get("youtube_videos", [])
    enriched_youtube = audit_youtube_videos(client, youtube_videos)

    # 2. Clustering
    themes = cluster_content(client, enriched_youtube)

    # 4. Music Vibe Check (AM only — presence of articles signals AM run)
    music_articles = raw_data.get("music_articles", [])
    morning_soundtrack: list[dict] = []
    if music_articles:
        morning_soundtrack = audit_music_articles(client, music_articles)

    # 5. Good News — Reason to be Hopeful (every run)
    good_news_raw = raw_data.get("good_news_articles", [])
    global_silver_linings = audit_good_news_articles(client, good_news_raw)

    # 6. Discovery — Fern's Note for History/Mystery + Science (every run)
    discovery_raw = raw_data.get("discovery_articles", [])
    discovery_articles = audit_discovery_articles(client, discovery_raw)

    # 7. Fern's daily greeting + top pick for subject line
    fern_data = generate_fern_greeting(
        client,
        raw_data.get("is_am_email", False),
        themes,
        morning_soundtrack,
        global_silver_linings,
        discovery_articles,
    )

    return {
        "fetched_at": raw_data.get("fetched_at"),
        "is_am_email": raw_data.get("is_am_email", False),
        "audit_summary": {
            "youtube_videos": len(enriched_youtube),
            "themes": len(themes),
            "music_articles": len(morning_soundtrack),
            "good_news_articles": len(global_silver_linings),
            "discovery_articles": len(discovery_articles),
        },
        "themes": themes,
        "morning_soundtrack": morning_soundtrack,
        "global_silver_linings": global_silver_linings,
        "discovery_articles": discovery_articles,
        "fern_data": fern_data,
    }
