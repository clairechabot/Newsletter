"""
Newsletter Data Fetcher
-----------------------
Fetches Reddit posts and YouTube videos with deduplication and OP context extraction,
then runs the AI audit + curation layer (curator.py).

Required environment variables:
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
    YOUTUBE_API_KEY
    ANTHROPIC_API_KEY
    SMTP_USER, SMTP_PASS (reserved for downstream use)

Install dependencies:
    pip install praw google-api-python-client python-dateutil anthropic
"""

import os
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import praw
from googleapiclient.discovery import build
from dateutil import parser as dateutil_parser

# ---------------------------------------------------------------------------
# Configuration — replace the placeholder lists before running
# ---------------------------------------------------------------------------

SUBREDDITS: list[str] = [
    # e.g. "Cooking", "EatCheapAndHealthy", "MealPrepSunday"
    # [Paste Subreddit List Here]
]

YOUTUBE_CHANNEL_IDS: list[str] = [
    # e.g. "UCxxxxxxxxxxxxxxxxxxxxxx"
    # [Paste Channel ID List Here]
]

HISTORY_FILE = Path(__file__).parent / "history.json"
REDDIT_WINDOW_HOURS = 12
YOUTUBE_VIDEOS_PER_CHANNEL = 2
YOUTUBE_MIN_DURATION_SECONDS = 60
YOUTUBE_DOUBLE_CHECK_SLEEP = 300  # 5 minutes

UTC = ZoneInfo("UTC")


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def load_history() -> set[str]:
    """Return the set of already-seen video IDs."""
    if HISTORY_FILE.exists():
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return set(data.get("video_ids", []))
    return set()


def save_history(seen_ids: set[str]) -> None:
    """Persist seen video IDs back to disk."""
    existing: dict = {}
    if HISTORY_FILE.exists():
        existing = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    existing["video_ids"] = sorted(seen_ids)
    HISTORY_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------

def build_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "newsletter-fetcher/1.0"),
    )


def _within_window(utc_timestamp: float, hours: int = REDDIT_WINDOW_HOURS) -> bool:
    cutoff = datetime.datetime.now(UTC) - datetime.timedelta(hours=hours)
    post_time = datetime.datetime.fromtimestamp(utc_timestamp, tz=UTC)
    return post_time >= cutoff


def fetch_op_context(submission: praw.models.Submission) -> str | None:
    """
    Walk top-level comments; return the first one written by OP, or None.
    The text is flagged as OP_Context for recipe/link analysis downstream.
    """
    try:
        submission.comments.replace_more(limit=0)
        for comment in submission.comments:
            if (
                comment.author is not None
                and submission.author is not None
                and comment.author.name == submission.author.name
            ):
                return comment.body
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] Could not fetch comments for '{submission.title}': {exc}")
    return None


def fetch_reddit_posts(reddit: praw.Reddit) -> list[dict]:
    """
    Fetch top posts from the last REDDIT_WINDOW_HOURS hours across all configured
    subreddits using the 'day' time filter, then apply exact datetime filtering.
    """
    results: list[dict] = []

    for sub_name in SUBREDDITS:
        print(f"[Reddit] Fetching r/{sub_name} …")
        subreddit = reddit.subreddit(sub_name)

        try:
            # 'top' with time_filter='day' is the closest Reddit API window;
            # we then trim to exactly 12 hours via datetime comparison.
            for submission in subreddit.top(time_filter="day", limit=100):
                if not _within_window(submission.created_utc):
                    continue  # older than our window

                op_context = fetch_op_context(submission)

                results.append(
                    {
                        "source": "reddit",
                        "subreddit": sub_name,
                        "id": submission.id,
                        "title": submission.title,
                        "url": submission.url,
                        "score": submission.score,
                        "author": str(submission.author) if submission.author else "[deleted]",
                        "created_utc": submission.created_utc,
                        "selftext": submission.selftext or None,
                        "op_context": op_context,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            print(f"  [error] r/{sub_name}: {exc}")

    print(f"[Reddit] Collected {len(results)} posts within the last {REDDIT_WINDOW_HOURS}h.")
    return results


# ---------------------------------------------------------------------------
# YouTube helpers
# ---------------------------------------------------------------------------

def build_youtube_client():
    return build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])


def _parse_iso8601_duration(duration: str) -> int:
    """Convert ISO 8601 duration (PT4M13S) to total seconds."""
    import re
    pattern = re.compile(
        r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
    )
    match = pattern.fullmatch(duration)
    if not match:
        return 0
    parts = match.groupdict(default="0")
    return (
        int(parts["hours"]) * 3600
        + int(parts["minutes"]) * 60
        + int(parts["seconds"])
    )


def _is_short(video_id: str, url: str, duration_seconds: int) -> bool:
    return "/shorts/" in url or duration_seconds < YOUTUBE_MIN_DURATION_SECONDS


def _fetch_video_details(youtube, video_ids: list[str]) -> list[dict]:
    """Retrieve full metadata for a batch of video IDs."""
    if not video_ids:
        return []

    response = (
        youtube.videos()
        .list(part="snippet,contentDetails,statistics", id=",".join(video_ids))
        .execute()
    )

    videos: list[dict] = []
    for item in response.get("items", []):
        vid_id = item["id"]
        snippet = item["snippet"]
        duration_str = item["contentDetails"]["duration"]
        duration_sec = _parse_iso8601_duration(duration_str)
        url = f"https://www.youtube.com/watch?v={vid_id}"

        if _is_short(vid_id, url, duration_sec):
            print(f"  [skip] {vid_id} — short/under 60s ({duration_sec}s)")
            continue

        videos.append(
            {
                "source": "youtube",
                "video_id": vid_id,
                "title": snippet["title"],
                "channel_id": snippet["channelId"],
                "channel_title": snippet["channelTitle"],
                "published_at": snippet["publishedAt"],
                "url": url,
                "duration_seconds": duration_sec,
                "view_count": item["statistics"].get("viewCount"),
                "description": snippet.get("description", "")[:500],
            }
        )
    return videos


def fetch_channel_videos(youtube, seen_ids: set[str]) -> list[dict]:
    """
    Fetch the latest YOUTUBE_VIDEOS_PER_CHANNEL videos per channel,
    double-check after a sleep, and filter against history.
    """
    def _get_latest_ids(channel_id: str) -> list[str]:
        response = (
            youtube.search()
            .list(
                part="id",
                channelId=channel_id,
                order="date",
                type="video",
                maxResults=YOUTUBE_VIDEOS_PER_CHANNEL * 2,  # extra buffer for filtering
            )
            .execute()
        )
        return [item["id"]["videoId"] for item in response.get("items", [])]

    # First fetch
    channel_id_map: dict[str, list[str]] = {}
    for ch_id in YOUTUBE_CHANNEL_IDS:
        print(f"[YouTube] Fetching channel {ch_id} …")
        channel_id_map[ch_id] = _get_latest_ids(ch_id)

    # Double-check after sleep to catch metadata updates
    print(f"[YouTube] Sleeping {YOUTUBE_DOUBLE_CHECK_SLEEP}s for double-check …")
    time.sleep(YOUTUBE_DOUBLE_CHECK_SLEEP)

    for ch_id in YOUTUBE_CHANNEL_IDS:
        refreshed = _get_latest_ids(ch_id)
        # Merge: prefer the refreshed list but keep any IDs only in the first pass
        merged = list(dict.fromkeys(refreshed + channel_id_map[ch_id]))
        channel_id_map[ch_id] = merged

    all_results: list[dict] = []

    for ch_id, vid_ids in channel_id_map.items():
        # Filter already-seen
        fresh_ids = [v for v in vid_ids if v not in seen_ids]
        details = _fetch_video_details(youtube, fresh_ids)

        # Take only the configured number of non-short videos per channel
        accepted = details[:YOUTUBE_VIDEOS_PER_CHANNEL]
        for v in accepted:
            seen_ids.add(v["video_id"])

        all_results.extend(accepted)

    print(f"[YouTube] Collected {len(all_results)} channel videos.")
    return all_results


def fetch_trending_video(youtube, subreddits: list[str], seen_ids: set[str]) -> dict | None:
    """
    Fetch ONE trending video whose topic aligns with the subreddit interests.
    Uses the YouTube mostPopular chart, filtered by a derived topic keyword.
    """
    # Derive a simple keyword from subreddit names (first non-empty subreddit)
    keyword = subreddits[0].replace("_", " ") if subreddits else "food"
    print(f"[YouTube] Fetching trending video for topic: '{keyword}' …")

    response = (
        youtube.videos()
        .list(
            part="snippet,contentDetails,statistics",
            chart="mostPopular",
            regionCode="US",
            videoCategoryId="",  # all categories; narrow if needed
            maxResults=25,
        )
        .execute()
    )

    keyword_lower = keyword.lower()
    for item in response.get("items", []):
        vid_id = item["id"]
        if vid_id in seen_ids:
            continue

        snippet = item["snippet"]
        title = snippet["title"].lower()
        description = snippet.get("description", "").lower()
        tags = " ".join(snippet.get("tags", [])).lower()

        relevance_text = f"{title} {description} {tags}"
        if keyword_lower not in relevance_text:
            continue

        duration_sec = _parse_iso8601_duration(item["contentDetails"]["duration"])
        url = f"https://www.youtube.com/watch?v={vid_id}"

        if _is_short(vid_id, url, duration_sec):
            continue

        seen_ids.add(vid_id)
        print(f"[YouTube] Trending pick: {snippet['title']}")
        return {
            "source": "youtube_trending",
            "video_id": vid_id,
            "title": snippet["title"],
            "channel_id": snippet["channelId"],
            "channel_title": snippet["channelTitle"],
            "published_at": snippet["publishedAt"],
            "url": url,
            "duration_seconds": duration_sec,
            "view_count": item["statistics"].get("viewCount"),
            "description": snippet.get("description", "")[:500],
        }

    print("[YouTube] No on-topic trending video found.")
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> dict:
    # Validate required env vars early
    missing = [
        var
        for var in (
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "YOUTUBE_API_KEY",
            "ANTHROPIC_API_KEY",
        )
        if not os.environ.get(var)
    ]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    if not SUBREDDITS:
        raise ValueError("SUBREDDITS list is empty. Add subreddit names before running.")
    if not YOUTUBE_CHANNEL_IDS:
        raise ValueError("YOUTUBE_CHANNEL_IDS list is empty. Add channel IDs before running.")

    seen_ids = load_history()

    # --- Reddit ---
    reddit = build_reddit_client()
    reddit_posts = fetch_reddit_posts(reddit)

    # --- YouTube ---
    youtube = build_youtube_client()
    channel_videos = fetch_channel_videos(youtube, seen_ids)
    trending_video = fetch_trending_video(youtube, SUBREDDITS, seen_ids)

    youtube_results = channel_videos + ([trending_video] if trending_video else [])

    # --- Persist history ---
    save_history(seen_ids)

    raw_payload = {
        "fetched_at": datetime.datetime.now(UTC).isoformat(),
        "reddit_posts": reddit_posts,
        "youtube_videos": youtube_results,
    }

    # Write raw fetch snapshot (useful for debugging / re-running curation without re-fetching)
    raw_file = Path(__file__).parent / "fetched_data.json"
    raw_file.write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\n[fetch] Raw data → {raw_file} "
        f"({len(reddit_posts)} Reddit posts | "
        f"{len(channel_videos)} channel videos | "
        f"{'1 trending video' if trending_video else 'no trending video'})"
    )

    # --- Audit & Curation ---
    from curator import run_curation  # local import keeps startup fast when testing fetcher alone

    print("\n[curator] Starting audit & curation …")
    curated = run_curation(raw_payload)

    curated_file = Path(__file__).parent / "curated_data.json"
    curated_file.write_text(json.dumps(curated, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = curated["audit_summary"]
    print(
        f"\n[done] Curated data → {curated_file}\n"
        f"       Reddit: {summary['reddit_accepted']}/{summary['reddit_raw']} accepted "
        f"({summary['reddit_discarded']} discarded) | "
        f"YouTube: {summary['youtube_videos']} videos | "
        f"Themes: {summary['themes']}"
    )
    return curated


if __name__ == "__main__":
    main()
