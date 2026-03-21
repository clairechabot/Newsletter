"""
Newsletter Curator — Audit & Curation Layer
--------------------------------------------
Uses Claude (claude-3-5-sonnet) to:
  1. Audit Reddit posts for Dead Internet / AI-generated patterns (hard-discard ≥ 75%).
  2. Generate "Why Watch" descriptions for YouTube videos.
  3. Cluster all accepted content into 3-4 cross-platform creative themes.

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

CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
AI_SCORE_DISCARD_THRESHOLD = 75       # percent
REDDIT_BATCH_SIZE = 6                 # posts per audit API call
THEME_COUNT_MIN, THEME_COUNT_MAX = 3, 4


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def build_claude_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])


# ---------------------------------------------------------------------------
# Reddit Audit
# ---------------------------------------------------------------------------

_REDDIT_AUDIT_SYSTEM = textwrap.dedent("""
You are a sharp editorial assistant for a curated human-interest newsletter.
Your job is to audit Reddit posts for authenticity and summarize the genuine ones.

## Dead Internet / AI-Generated Content — Detection Criteria
Score each post on a 0-100 scale (AI-Generated Likelihood). Look for:

HIGH-RISK signals (push score up significantly):
- Unnaturally flawless grammar/spelling in a casual subreddit context
- Generic non-specific personal anecdotes ("I was walking one day and I realized...")
- Emotionally performative language with zero concrete detail
- List-heavy, perfectly balanced structure that reads like product copy
- Title engineered for maximum engagement ("This changed everything", "You won't believe...")
- OP comment is a suspiciously clean, step-by-step recipe or guide without any personal voice
- Broad mass-appeal with no community-specific jargon or in-jokes
- The post could have been written about ANY subreddit, not THIS one specifically

LOW-RISK signals (push score down):
- Typos, slang, or casual phrasing
- Highly specific personal detail ("my 2003 Honda Civic", "my aunt Linda's kitchen")
- Direct reply to or reference of another user or recent event
- Genuine frustration, confusion, or emotion that is clearly unscripted
- Niche knowledge or jargon specific to the community

## Output Format
Return ONLY a valid JSON array. Each element corresponds to one post in the input order:
[
  {
    "id": "<post id>",
    "ai_score": <integer 0-100>,
    "discard": <true if ai_score >= 75, else false>,
    "summary": "<1-2 sentence newsletter summary. If discard=true, write 'DISCARD'. If OP_Context contains a recipe or link, reference it explicitly in the summary.>"
  },
  ...
]

Do not include any text outside the JSON array.
""").strip()


def _build_reddit_audit_user_message(batch: list[dict]) -> str:
    posts_text = []
    for i, post in enumerate(batch, 1):
        op_ctx = post.get("op_context") or "(none)"
        selftext = (post.get("selftext") or "").strip()[:400] or "(link/image post)"
        posts_text.append(
            f"--- Post {i} ---\n"
            f"ID: {post['id']}\n"
            f"Subreddit: r/{post['subreddit']}\n"
            f"Title: {post['title']}\n"
            f"Score: {post['score']}\n"
            f"Body: {selftext}\n"
            f"OP_Context (OP's own comment): {op_ctx[:600]}"
        )
    return "\n\n".join(posts_text)


def audit_reddit_posts(client: anthropic.Anthropic, posts: list[dict]) -> list[dict]:
    """
    Run Dead Internet audit on all Reddit posts in batches.
    Returns only posts that pass (ai_score < 75), each enriched with
    'ai_score' and 'summary' fields.
    """
    accepted: list[dict] = []
    discarded_count = 0

    for batch_start in range(0, len(posts), REDDIT_BATCH_SIZE):
        batch = posts[batch_start : batch_start + REDDIT_BATCH_SIZE]
        print(
            f"[Audit/Reddit] Auditing posts {batch_start + 1}–"
            f"{batch_start + len(batch)} of {len(posts)} …"
        )

        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=_REDDIT_AUDIT_SYSTEM,
            messages=[{"role": "user", "content": _build_reddit_audit_user_message(batch)}],
        )

        raw = message.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            results: list[dict] = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"  [warn] JSON parse error in Reddit audit batch: {exc}. Skipping batch.")
            continue

        id_to_result = {r["id"]: r for r in results}

        for post in batch:
            result = id_to_result.get(post["id"])
            if result is None:
                print(f"  [warn] No audit result for post {post['id']}. Keeping as-is.")
                accepted.append(post)
                continue

            score = int(result.get("ai_score", 0))
            discard = score >= AI_SCORE_DISCARD_THRESHOLD

            if discard:
                discarded_count += 1
                print(
                    f"  [discard] '{post['title'][:60]}' — AI score {score}%"
                )
            else:
                enriched = {**post, "ai_score": score, "summary": result.get("summary", "")}
                accepted.append(enriched)

    print(
        f"[Audit/Reddit] {len(accepted)} accepted, {discarded_count} discarded "
        f"(threshold ≥{AI_SCORE_DISCARD_THRESHOLD}%)."
    )
    return accepted


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
        items.append(
            f"--- Video {i}{label} ---\n"
            f"ID: {v['video_id']}\n"
            f"Title: {v['title']}\n"
            f"Channel: {v['channel_title']}\n"
            f"Duration: {v['duration_seconds'] // 60}m {v['duration_seconds'] % 60}s\n"
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

You will receive a mixed batch of Reddit posts and YouTube videos.
Your task: group all items into exactly 3 or 4 thematic clusters that will become
newsletter sections. The themes must be:

  • FUN and CREATIVE — real section names (e.g. "The Daily Crust", "Digital Zen",
    "Cozy Corners", "Rabbit Holes Worth Falling Down") — NOT generic labels like
    "Food Content" or "Tech Videos".
  • CROSS-PLATFORM — each theme MUST mix Reddit and YouTube items where possible.
    Do NOT create Reddit-only or YouTube-only sections.
  • THEMATICALLY COHERENT — items grouped by subject matter, mood, or angle,
    not by source platform.
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
          "item_id": "<post 'id' or video 'video_id'>",
          "platform": "reddit" | "youtube",
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


def _build_cluster_user_message(
    reddit_posts: list[dict], youtube_videos: list[dict]
) -> str:
    lines = ["## Reddit Posts\n"]
    for p in reddit_posts:
        lines.append(
            f"- ID: {p['id']} | r/{p['subreddit']} | \"{p['title']}\"\n"
            f"  Summary: {p.get('summary', p['title'])}"
        )

    lines.append("\n## YouTube Videos\n")
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
    reddit_posts: list[dict],
    youtube_videos: list[dict],
) -> list[dict]:
    """
    Group all accepted content into 3-4 cross-platform creative themes.
    Returns a list of theme dicts, each with full item objects embedded.
    """
    total = len(reddit_posts) + len(youtube_videos)
    print(f"[Curator] Clustering {total} items into {THEME_COUNT_MIN}–{THEME_COUNT_MAX} themes …")

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=_CLUSTER_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": _build_cluster_user_message(reddit_posts, youtube_videos),
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
                "items": reddit_posts + youtube_videos,
            }
        ]

    # Build lookup maps for fast item resolution
    reddit_map: dict[str, dict] = {p["id"]: p for p in reddit_posts}
    youtube_map: dict[str, dict] = {v["video_id"]: v for v in youtube_videos}

    themes: list[dict] = []
    for theme in cluster_data.get("themes", []):
        resolved_items: list[dict] = []
        for ref in theme.get("items", []):
            item_id = ref.get("item_id", "")
            platform = ref.get("platform", "")
            full_item: dict[str, Any] | None = None

            if platform == "reddit":
                full_item = reddit_map.get(item_id)
            elif platform == "youtube":
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
# Orchestrator
# ---------------------------------------------------------------------------

def run_curation(raw_data: dict) -> dict:
    """
    Full audit + curation pipeline.

    Input:  the dict produced by fetcher.main()
    Output: enriched dict with 'themes' and optional 'morning_soundtrack' section
    """
    client = build_claude_client()

    # 1. Reddit audit — discard AI-generated posts
    reddit_posts = raw_data.get("reddit_posts", [])
    accepted_reddit = audit_reddit_posts(client, reddit_posts)

    # 2. YouTube audit — generate Why Watch
    youtube_videos = raw_data.get("youtube_videos", [])
    enriched_youtube = audit_youtube_videos(client, youtube_videos)

    # 3. Cross-platform clustering
    themes = cluster_content(client, accepted_reddit, enriched_youtube)

    # 4. Music Vibe Check (AM only — presence of articles signals AM run)
    music_articles = raw_data.get("music_articles", [])
    morning_soundtrack: list[dict] = []
    if music_articles:
        morning_soundtrack = audit_music_articles(client, music_articles)

    # 5. Good News — Reason to be Hopeful (every run)
    good_news_raw = raw_data.get("good_news_articles", [])
    global_silver_linings = audit_good_news_articles(client, good_news_raw)

    return {
        "fetched_at": raw_data.get("fetched_at"),
        "is_am_email": raw_data.get("is_am_email", False),
        "audit_summary": {
            "reddit_raw": len(reddit_posts),
            "reddit_accepted": len(accepted_reddit),
            "reddit_discarded": len(reddit_posts) - len(accepted_reddit),
            "youtube_videos": len(enriched_youtube),
            "themes": len(themes),
            "music_articles": len(morning_soundtrack),
            "good_news_articles": len(global_silver_linings),
        },
        "themes": themes,
        "morning_soundtrack": morning_soundtrack,
        "global_silver_linings": global_silver_linings,
    }
