"""
Newsletter Data Fetcher
-----------------------
Fetches YouTube videos, music articles, and good news RSS feeds,
then runs the AI audit + curation layer (curator.py).

Required environment variables:
    YOUTUBE_API_KEY
    CLAUDE_API_KEY
    EMAIL_USER, SMTP_PASS (reserved for downstream use)

Install dependencies:
    pip install google-api-python-client python-dateutil anthropic requests beautifulsoup4
"""

import os
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import re
import random
from langdetect import detect, LangDetectException
import defusedxml.ElementTree as ET
from urllib.parse import urlparse, urljoin, quote

import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import http_fetch      # hardened HTTP (browser UA + retries), ported from daily-briefing
import claude_fetch    # Claude web-fetch music extractor (real titles), ported from daily-briefing

# ---------------------------------------------------------------------------
# Configuration — replace the placeholder lists before running
# ---------------------------------------------------------------------------


YOUTUBE_CHANNEL_IDS: list[str] = [
    "UCsaGKqPZnGp_7N80hcHySGQ", "UCHL9bfHTxCMi-7vfxQ-AYtg", "UCSbyncU597LMwb3HhnAI_4w",
    "UCZwU2G-KVl-P-O-B35chZOQ", "UC4sEmXUuWIFlxRIFBRV6VXQ",
    "UCDdi0yUyGW1PKzYXaIACnuA", "UCXcTkcC_H4XeDGfJ7rQGJaw",
    "UCvQECJukTDE2i6aCoMnS-Vg", "UC_-hYjoNe4PJNFa9iZ4lraA",
    "UCtBzfGaJzGGNJVOVM0mK4uQ", "UC-SrCCzkGq0wmSAuRs7EBFg",
    "UCSwwoUNvQWgZDC8a_O6Qs_A", "UCSHtaUm-FjUps090S7crO4Q",
    "UCvy6TA5egUGHnZXVRYDKOhg",
    "UC4HRlp7zs7UpIFM67eGjhow", "UC9r61qohBg1qgGty4_WzojA", "UC_8x1VmhDgsU72Yktd9Ukeg",
    "UC6nSFpj9HTCZ5t-N3Rm3-HA", "UCEqU-Ts-hxmpnlWgRMgd2MQ", "UCmGSJVG3mCRXVOP4yZrU1Dw",
    "UC3cpN6gcJQqcCM6mxRUo_dA", "UCJI86v9et-IZd1KJSfahN8g",
    "UC2Kyj04yISmHr1V-UlJz4eg", "UCftwRNsjfRo08xYE31tkiyw", "UCNwZIGnHkzy6KpHPQtserzQ",
    # Added channels
    "UCnCk_o6ySiM_ZzxubCv899Q", "UCCGtjLbNN7rtBRlAbnKOrBg", "UC1t6kKXoBvjdr8m9KJ2Fx7A",
    "UCZB1r1In9RfE7tpVrYgcjLQ", "UCR2uRTQ53V_egXKFflMMaaw",
    "UCs7nPQIEba0T3tGOWWsZpJQ", "UCNaq5Jh4SQ1oBAjhQ0KPhoA",
    "UCAcoda6jlC-xpxGhwW7yFZw",  # Matt Reconstructs History
    "UCYO_jab_esuFRV4b17AJtAw",  # 3Blue1Brown
    "UCXl4i9dYBrFOabk0xGmbkRA",  # Dwarkesh Patel
]

HISTORY_FILE = Path(__file__).parent / "history.json"
CLAUDE_MODEL = "claude-sonnet-4-6"    # matches curator.CLAUDE_MODEL
YOUTUBE_VIDEOS_PER_CHANNEL = 1        # 1 per channel conserves quota for wildcard search
CHANNEL_SCAN_DEPTH = 50               # uploads scanned back per channel for unseen videos (mines backlog, not just recent)
MAX_VIDEOS_PER_EDITION = 10           # newest-first cap across all channels + wildcard
YOUTUBE_MIN_DURATION_SECONDS = 121    # ≥ 2 min — removes the 0–2 min band where Shorts cluster
YOUTUBE_WILDCARD_MIN_SECONDS = 300    # wildcard must be ≥ 5 minutes

# Wildcard categories — one is chosen at random each run
_POLITICAL_KEYWORDS = frozenset({
    "war", "trump", "biden", "harris", "election", "congress", "senate",
    "iran", "israel", "gaza", "ukraine", "russia", "military", "nato",
    "bombing", "coup", "legislation", "sanctions", "republican", "democrat",
    "whitehouse", "pentagon", "missile", "nuclear", "ceasefire", "protest",
    "assassination", "tariff", "tariffs", "impeach", "geopolitical",
    "kamala", "maga", "liberal", "conservative", "partisan", "filibuster",
    "death", "violence", "conflict", "shooting", "tragedy",
})


def _is_political(title: str, description: str = "") -> bool:
    """Return True if the title or description contains blocked content keywords."""
    title_words = set(re.findall(r'\w+', title.lower()))
    if title_words & _POLITICAL_KEYWORDS:
        return True
    if description:
        desc_words = set(re.findall(r'\w+', description.lower()))
        return bool(desc_words & _POLITICAL_KEYWORDS)
    return False


_CLICKBAIT_PHRASES = frozenset({
    "you won't believe",
    "they don't want you to know",
    "this will shock you",
    "gone wrong",
    "watch till the end",
    "must watch",
    "shocking truth",
    "exposed",
    "the truth about",
    "secret they",
    "doctors hate",
    "one weird trick",
})


def _is_clickbait(title: str) -> bool:
    """Return True if the title shows ALL-CAPS spam or clickbait patterns."""
    if title.count("!") + title.count("?") >= 3:
        return True
    title_lower = title.lower()
    if any(phrase in title_lower for phrase in _CLICKBAIT_PHRASES):
        return True
    # Flag if 60%+ of words with 4+ chars are fully uppercase (requires ≥3 such words)
    words = re.findall(r'[A-Za-z]{4,}', title)
    if len(words) >= 3:
        caps_count = sum(1 for w in words if w.isupper())
        if caps_count / len(words) >= 0.6:
            return True
    return False


WILDCARD_CATEGORIES = [
    {
        "name": "Nature",
        "topic_id": "/m/06mf6",
        "queries": ["wildlife", "ocean life"],
    },
    {
        "name": "Travel",
        "topic_id": "/m/019_rr",
        "queries": ["travel vlog", "scenic journey"],
    },
    {
        "name": "Good News",
        "topic_id": "/m/098wr",
        "queries": ["positive news", "restoring faith in humanity"],
    },
]

# Music sources — RSS feeds preferred (never blocked); scrape fallback where no feed exists.
MUSIC_SOURCES: list[dict] = [
    {"name": "NPR Music",      "rss": "https://feeds.npr.org/1039/rss.xml"},
    {"name": "Stereogum",      "rss": "https://www.stereogum.com/feed/"},
    {"name": "No Depression",  "rss": "https://www.nodepression.com/feed/"},
    {"name": "Pitchfork",      "rss": "https://pitchfork.com/rss/news/"},
    # Bandcamp Daily's RSS was discontinued — replaced with the three below.
    {"name": "Aquarium Drunkard", "rss": "https://aquariumdrunkard.com/feed/"},
    # The Quietus + UK Jazz News were Cloudflare-blocked (403) from GitHub's IP;
    # replaced with non-Cloudflare feeds that serve from GitHub runners.
    {"name": "Consequence",    "rss": "https://consequence.net/feed/"},
    {"name": "Nextbop",        "rss": "https://nextbop.com/feed"},
    {"name": "JazzTimes",      "rss": "https://jazztimes.com/feed/"},
    # Broad, thoughtful reviews + a dedicated home for the Americana / folk /
    # bluegrass / Celtic corner. Both verified non-Cloudflare, fresh feeds.
    {"name": "PopMatters",        "rss": "https://www.popmatters.com/feed"},
    {"name": "Fretboard Journal", "rss": "https://www.fretboardjournal.com/feed/"},
    {"name": "Sofar Sounds",   "url": "https://www.sofarsounds.com/blog"},  # no RSS — scrape
]
MUSIC_ARTICLES_PER_SOURCE = 3          # post-filter cap per source
MUSIC_CANDIDATES_PER_SOURCE = 8        # pull this many, then genre-filter down

# Genres the reader likes — music items are filtered to these by Claude.
# Edit this list to retune taste.
MUSIC_GENRES: list[str] = [
    "jazz", "soul", "neo-soul", "classical", "classical crossover", "acoustic",
    "country", "Americana", "90s", "80s", "rock", "classic rock", "blues rock",
    "folk rock", "alt-rock", "folk", "bluegrass", "Celtic", "world", "roots",
    "pop", "indie pop", "singer-songwriter", "dream pop",
]
SCRAPER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) FernDigest/1.2",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT":             "1",
}

UTC = ZoneInfo("UTC")
# Edition timezone + garden locale are env-overridable so a regional edition can
# reuse the same code (defaults keep the primary Zürich edition unchanged).
EDITION_TZ = ZoneInfo(os.environ.get("EDITION_TZ", "Europe/Zurich"))
ZURICH = EDITION_TZ  # backward-compatible alias
GARDEN_LOCALE = os.environ.get("GARDEN_LOCALE", "Zürich")


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def load_history() -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    """Return (video_ids, good_news_urls, discovery_urls, reads_urls, music_urls)
    seen before. New buckets default to empty so older history.json files load."""
    if HISTORY_FILE.exists():
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
        return (
            set(data.get("video_ids", [])),
            set(data.get("good_news_urls", [])),
            set(data.get("discovery_urls", [])),
            set(data.get("reads_urls", [])),
            set(data.get("music_urls", [])),
        )
    return set(), set(), set(), set(), set()


def save_history(
    seen_ids: set[str],
    seen_good_news_urls: set[str],
    seen_discovery_urls: set[str],
    seen_reads_urls: set[str],
    seen_music_urls: set[str],
    pending_puzzle: "dict | None" = None,
    recent_puzzles: "list | None" = None,
) -> None:
    """Persist seen video IDs and the Good News / Discovery / Reads / Music URLs.

    pending_puzzle carries this edition's puzzle (label/prompt/answer) forward so
    the NEXT edition can print the answer. None leaves any existing pending
    puzzle untouched (so an unanswered puzzle isn't dropped by a puzzle-less run).

    recent_puzzles is a rolling list of recently-used puzzles ({kind/prompt/answer})
    the generator is told to avoid repeating; None leaves it untouched."""
    existing: dict = {}
    if HISTORY_FILE.exists():
        existing = json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
    existing["video_ids"]       = sorted(seen_ids)
    existing["good_news_urls"]  = sorted(seen_good_news_urls)
    existing["discovery_urls"]  = sorted(seen_discovery_urls)
    existing["reads_urls"]      = sorted(seen_reads_urls)
    existing["music_urls"]      = sorted(seen_music_urls)
    if pending_puzzle is not None:
        existing["pending_puzzle"] = pending_puzzle
    if recent_puzzles is not None:
        existing["recent_puzzles"] = recent_puzzles
    HISTORY_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Shared scraper session + retry helper
# ---------------------------------------------------------------------------

# Status codes worth retrying (transient server errors)
_RETRY_STATUSES = {500, 502, 503, 504}


def _scraper_session() -> requests.Session:
    """Return a Session pre-loaded with realistic browser headers.
    Keep-Alive reuse and cookie persistence are automatic with Session."""
    session = requests.Session()
    session.headers.update(SCRAPER_HEADERS)
    return session


def _fetch_with_retry(
    url: str,
    session: requests.Session,
    retries: int = 3,
    backoff: float = 2.0,
    referer: str = "",
) -> requests.Response | None:
    """
    GET `url` via `session`, retrying up to `retries` times on transient
    failures (connection errors, timeouts, 5xx responses).

    `backoff` is the base wait in seconds; passed through as the retry delay.
    `referer` is injected as a Referer header when provided.
    Returns the Response on success, or None after all retries are exhausted.

    The actual request now goes through `http_fetch.fetch` (browser UA +
    retries + raise_for_status), so every scraping call site benefits from the
    hardened path. The `session` arg is kept for signature compatibility but is
    no longer used for the network call.
    """
    headers = {"Referer": referer} if referer else {}
    try:
        return http_fetch.fetch(
            url, headers=headers, timeout=15,
            retries=retries, retry_delay=backoff,
        )
    except requests.RequestException as exc:
        print(f"  [warn] Gave up fetching {url} after {retries} attempts: {exc}")
        return None


# ---------------------------------------------------------------------------
# YouTube helpers
# ---------------------------------------------------------------------------

def build_youtube_client():
    return build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])


def _parse_iso8601_duration(duration: str) -> int:
    """Convert ISO 8601 duration (PT4M13S) to total seconds."""
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


def _is_short(video_id: str, url: str, duration_seconds: int, title: str = "") -> bool:
    """Tightened Shorts detection.

    1. `/shorts/` in the URL — explicit Short.
    2. Under the 2-minute floor — kills the band where Shorts cluster, even when
       the API rounds `contentDetails.duration` to a whole minute.
    3. A sub-3-minute clip whose title carries a #shorts hashtag — catches the
       round-duration edge case without any extra API call.
    """
    if "/shorts/" in url:
        return True
    if duration_seconds < YOUTUBE_MIN_DURATION_SECONDS:
        return True
    if duration_seconds <= 180 and "#short" in title.lower():
        return True
    return False


def _fetch_video_details(youtube, video_ids: list[str]) -> tuple[list[dict], set[str]]:
    """Retrieve full metadata for a batch of video IDs.

    Returns (videos, processed_ids) where processed_ids contains every vid_id
    touched — accepted or skipped — so callers can register skips in seen_ids
    and avoid re-fetching the same video on the next run.
    """
    if not video_ids:
        return [], set()

    response = (
        youtube.videos()
        .list(part="snippet,contentDetails,statistics", id=",".join(video_ids))
        .execute()
    )

    videos: list[dict] = []
    processed_ids: set[str] = set()
    for item in response.get("items", []):
        vid_id = item["id"]
        processed_ids.add(vid_id)
        snippet = item.get("snippet")
        if not snippet:
            print(f"  [skip/no-snippet] {vid_id} — missing snippet metadata")
            continue
        duration_str = item.get("contentDetails", {}).get("duration", "")
        if not duration_str:
            print(f"  [skip/no-duration] {vid_id} — duration metadata absent")
            continue
        duration_sec = _parse_iso8601_duration(duration_str)
        if duration_sec == 0:
            print(f"  [skip/no-duration] {vid_id} — duration unparseable ({duration_str!r})")
            continue
        url = f"https://www.youtube.com/watch?v={vid_id}"
        title = snippet["title"]

        if _is_short(vid_id, url, duration_sec, title):
            print(f"  [skip/short] {vid_id} — {duration_sec}s (min {YOUTUBE_MIN_DURATION_SECONDS}s)")
            continue
        if re.search(r'[^\x00-\x7FÀ-ɏḀ-ỿ]', title):
            print(f"  [skip/non-latin] {vid_id} — non-Latin characters in title")
            continue

        audio_lang = snippet.get("defaultAudioLanguage", "")
        if audio_lang and not audio_lang.startswith("en"):
            print(f"  [skip/lang] {vid_id} — language '{audio_lang}'")
            continue

        desc_text = snippet.get("description", "").strip()
        if desc_text:
            try:
                if detect(desc_text) != "en":
                    print(f"  [skip/lang] {vid_id} — description not English")
                    continue
            except LangDetectException:
                pass

        videos.append(
            {
                "source": "youtube",
                "video_id": vid_id,
                "title": title,
                "channel_id": snippet["channelId"],
                "channel_title": snippet["channelTitle"],
                "published_at": snippet["publishedAt"],
                "url": url,
                "duration_seconds": duration_sec,
                "view_count": item.get("statistics", {}).get("viewCount"),
                "description": snippet.get("description", "")[:500],
            }
        )
    return videos, processed_ids


def _get_uploads_playlist_ids(youtube, channel_ids: list[str]) -> dict[str, str]:
    """
    Map channel_id → uploads_playlist_id using channels.list.
    Costs 1 quota unit per 50 channels (vs 100/channel with search.list).
    """
    result: dict[str, str] = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i : i + 50]
        resp = (
            youtube.channels()
            .list(part="contentDetails", id=",".join(batch))
            .execute()
        )
        for item in resp.get("items", []):
            ch_id = item["id"]
            uploads_id = (
                item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
            if uploads_id:
                result[ch_id] = uploads_id
    return result


def _get_playlist_latest_ids(youtube, playlist_id: str, max_results: int = 5) -> list[str]:
    """
    Return up to `max_results` latest video IDs from an uploads playlist,
    newest first. The API caps a page at 50, so we paginate with pageToken to
    reach the channel's backlog. Costs 1 quota unit per page (vs 100 for
    search.list) — e.g. 1 unit for depth ≤50, 3 for depth 150.
    """
    ids: list[str] = []
    page_token = None
    while len(ids) < max_results:
        resp = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=min(50, max_results - len(ids)),
                pageToken=page_token,
            )
            .execute()
        )
        ids.extend(
            vid_id
            for item in resp.get("items", [])
            if (vid_id := item.get("contentDetails", {}).get("videoId"))
        )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids[:max_results]


def fetch_channel_videos(
    youtube, seen_ids: set[str], max_videos: int = MAX_VIDEOS_PER_EDITION
) -> list[dict]:
    """
    Scan the last CHANNEL_SCAN_DEPTH uploads of every channel for unseen videos,
    accept up to YOUTUBE_VIDEOS_PER_CHANNEL per channel, then keep the
    `max_videos` newest across all channels.

    Seen-marking rules (so no eligible video is ever silently lost):
      - videos rejected for cause (Short/political/clickbait/non-English) are
        marked seen — they will never become eligible;
      - eligible videos NOT chosen this run (per-channel surplus or cut by the
        newest-first cap) are left unseen and compete again next run;
      - only the videos actually returned are marked seen.

    Quota cost breakdown (~35 channels):
      - 1 call  to channels.list  for all IDs      →  1 unit
      - 1 call  to playlistItems.list per channel  → 35 units (depth ≤50 is free)
      - videos.list on fresh IDs, 1 unit per 50    → ~1-3 units
      Total: ~40 units  (vs ~7,000 with the old search.list approach)

    If a quota-exceeded error is hit at any stage, the function returns
    whatever has been collected so far rather than crashing the whole run.
    """
    all_results: list[dict] = []

    try:
        # Step 1: resolve uploads playlist IDs (1 unit per 50 channels)
        print(f"[YouTube] Resolving uploads playlists for {len(YOUTUBE_CHANNEL_IDS)} channels …")
        uploads_map = _get_uploads_playlist_ids(youtube, YOUTUBE_CHANNEL_IDS)
    except HttpError as exc:
        if "quotaExceeded" in str(exc):
            print("[YouTube] Quota exceeded during playlist resolution — skipping channel videos.")
            return all_results
        raise

    # Step 2: fetch latest video IDs from each uploads playlist (1 unit/channel)
    # Skip channels whose most-recent video is already in history — saves a videos.list call.
    fresh_ids_per_channel: dict[str, list[str]] = {}
    for ch_id in YOUTUBE_CHANNEL_IDS:
        playlist_id = uploads_map.get(ch_id)
        if not playlist_id:
            print(f"  [warn] No uploads playlist found for channel {ch_id}")
            continue
        print(f"[YouTube] Fetching channel {ch_id} …")
        try:
            vid_ids = _get_playlist_latest_ids(
                youtube, playlist_id, max_results=CHANNEL_SCAN_DEPTH
            )
        except HttpError as exc:
            if "quotaExceeded" in str(exc):
                print(f"[YouTube] Quota exceeded at channel {ch_id} — stopping channel fetch.")
                break
            print(f"  [warn] playlistItems error for {ch_id}: {exc}")
            continue

        # If every candidate is already in history, skip videos.list entirely
        fresh = [v for v in vid_ids if v not in seen_ids]
        dupes = len(vid_ids) - len(fresh)
        if dupes:
            print(f"  [skip/dup] {dupes} video(s) already in history for {ch_id}")
        if not fresh:
            continue
        fresh_ids_per_channel[ch_id] = fresh

    # Step 3: fetch details and filter per channel (videos.list = 1 unit per 50 videos)
    try:
        for ch_id, fresh_ids in fresh_ids_per_channel.items():
            details, processed_ids = _fetch_video_details(youtube, fresh_ids)
            filtered = []
            for v in details:
                if _is_political(v["title"], v.get("description", "")):
                    print(f"  [skip/blocked] channel {v['video_id']} — '{v['title']}'")
                    continue
                if _is_clickbait(v["title"]):
                    print(f"  [skip/clickbait] channel {v['video_id']} — '{v['title']}'")
                    continue
                filtered.append(v)
            # Register only rejected-for-cause IDs (Shorts, blocked, clickbait,
            # language). Eligible videos stay unseen until actually used, so a
            # channel that posts several videos doesn't lose the surplus.
            eligible_ids = {v["video_id"] for v in filtered}
            seen_ids |= processed_ids - eligible_ids
            accepted = filtered[:YOUTUBE_VIDEOS_PER_CHANNEL]
            if len(filtered) > len(accepted):
                print(f"  [defer] {len(filtered) - len(accepted)} eligible video(s) "
                      f"left for a future edition ({ch_id})")
            all_results.extend(accepted)
    except HttpError as exc:
        if "quotaExceeded" in str(exc):
            print("[YouTube] Quota exceeded during video detail fetch — using partial results.")
        else:
            raise

    # Keep the newest `max_videos` across all channels; videos cut by the cap
    # remain unseen and compete again next run.
    all_results.sort(key=lambda v: v.get("published_at", ""), reverse=True)
    if len(all_results) > max_videos:
        print(f"[YouTube] Capping {len(all_results)} accepted videos to the {max_videos} newest.")
        all_results = all_results[:max_videos]
    for v in all_results:
        seen_ids.add(v["video_id"])

    print(f"[YouTube] Collected {len(all_results)} channel videos.")
    return all_results


def fetch_trending_video(youtube, seen_ids: set[str]) -> dict | None:
    """
    Pick ONE wildcard video by randomly selecting a category (Nature / Travel / Good News),
    then searching with that category's topicId + one of its query strings.

    Constraints:
      - Published within the last 24 hours
      - At least YOUTUBE_WILDCARD_MIN_SECONDS long (5 minutes) — no Shorts
      - Not already in history (seen_ids deduplication)

    Falls back through both query strings and all three categories before giving up.
    """
    published_after = (
        datetime.datetime.now(UTC) - datetime.timedelta(hours=24)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Shuffle so we try a different category each run
    categories = WILDCARD_CATEGORIES.copy()
    random.shuffle(categories)

    for category in categories:
        for query in category["queries"]:
            print(
                f"[YouTube] Wildcard search — category: {category['name']!r}, "
                f"query: {query!r} …"
            )

            search_resp = (
                youtube.search()
                .list(
                    part="id",
                    type="video",
                    topicId=category["topic_id"],
                    q=query,
                    publishedAfter=published_after,
                    order="viewCount",
                    regionCode="US",
                    relevanceLanguage="en",
                    maxResults=20,
                )
                .execute()
            )

            candidate_ids = [
                item["id"]["videoId"]
                for item in search_resp.get("items", [])
                if item["id"]["videoId"] not in seen_ids
            ]

            if not candidate_ids:
                print(f"  [wildcard] No fresh candidates for query {query!r}.")
                continue

            details, processed_ids = _fetch_video_details(youtube, candidate_ids)
            seen_ids |= processed_ids   # register skipped wildcard candidates

            for video in details:
                vid_id = video["video_id"]
                if vid_id in seen_ids:
                    print(f"  [skip/dup] wildcard {vid_id} already in history")
                    continue
                if video["duration_seconds"] < YOUTUBE_WILDCARD_MIN_SECONDS:
                    print(
                        f"  [skip/short] wildcard {vid_id} — "
                        f"{video['duration_seconds']}s < {YOUTUBE_WILDCARD_MIN_SECONDS}s"
                    )
                    continue
                if _is_political(video["title"], video.get("description", "")):
                    print(f"  [skip/political] wildcard {vid_id} — '{video['title']}'")
                    continue
                if _is_clickbait(video["title"]):
                    print(f"  [skip/clickbait] wildcard {vid_id} — '{video['title']}'")
                    continue

                seen_ids.add(vid_id)
                print(
                    f"[YouTube] Wildcard pick ({category['name']} / {query!r}): "
                    f"{video['title']}"
                )
                return {**video, "source": "youtube_trending"}

    print("[YouTube] No wildcard video found after exhausting all categories.")
    return None


# ---------------------------------------------------------------------------
# Music Scraper
# ---------------------------------------------------------------------------

def _embed_from_soup(soup: BeautifulSoup, page_text: str) -> str | None:
    """First distraction-free embed URL found in a parsed article page.

    Priority order:
      1. Bandcamp EmbeddedPlayer iframe  → bandcamp.com/EmbeddedPlayer/...
      2. YouTube iframe                  → youtube.com/embed/VIDEO_ID
      3. Bare YouTube watch link         → converted to youtube.com/embed/VIDEO_ID
      4. Bare Bandcamp album/track link  → cleaned page URL ("Listen on Bandcamp")
    """
    for iframe in soup.find_all("iframe", src=True):
        src: str = iframe["src"]
        if "bandcamp.com/EmbeddedPlayer" in src:
            return src if src.startswith("http") else "https:" + src
        if "youtube.com/embed/" in src or "youtube-nocookie.com/embed/" in src:
            vid_id = src.split("/embed/")[1].split("?")[0].split("&")[0]
            return f"https://www.youtube.com/embed/{vid_id}"

    yt_match = re.search(
        r'https?://(?:www\.)?youtube\.com/watch\?v=([\w-]{11})', page_text
    )
    if yt_match:
        return f"https://www.youtube.com/embed/{yt_match.group(1)}"

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if re.search(r'bandcamp\.com/(album|track)/', href):
            return href.split("?")[0].rstrip("/")

    return None


def _cover_from_soup(soup: BeautifulSoup) -> str | None:
    """The article's social/lead image (og:image, then twitter:image)."""
    for prop in ("og:image", "twitter:image", "twitter:image:src"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _find_embed_and_cover(
    article_url: str, session: requests.Session
) -> tuple[str | None, str | None]:
    """Fetch an article page once and return (embed_url, cover_url).

    Returns (None, None) if the page can't be fetched."""
    if not article_url or article_url == "#":
        return None, None
    parsed_origin = urlparse(article_url)
    referer = f"{parsed_origin.scheme}://{parsed_origin.netloc}/"
    resp = _fetch_with_retry(article_url, session, referer=referer)
    if resp is None:
        return None, None
    soup = BeautifulSoup(resp.text, "html.parser")
    return _embed_from_soup(soup, resp.text), _cover_from_soup(soup)


def _filter_music_by_genre(items: list[dict], client) -> list[dict]:
    """Keep only items whose music plausibly fits the reader's MUSIC_GENRES.

    Claude judges (inclusive of adjacent styles). Fail-open: on any error or
    empty result we return the items unchanged rather than emptying the section.
    """
    if not items:
        return []
    listing = "\n".join(
        f"{i}: {it.get('title','')} | genre hint: {it.get('genre','?')} "
        f"| {it.get('snippet','')[:120]}"
        for i, it in enumerate(items)
    )
    prompt = (
        f"Reader's preferred genres: {', '.join(MUSIC_GENRES)}.\n"
        f"From the list below, return ONLY the indices whose music plausibly "
        f"fits those genres (be inclusive of adjacent styles and eras). Items:\n"
        f"{listing}\n\n"
        'Return ONLY JSON, no fences: {"keep": [<indices>]}'
    )
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            b.text for b in msg.content if getattr(b, "type", "") == "text"
        ).strip()
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw, flags=re.MULTILINE)
        keep = set(json.loads(raw).get("keep", []))
    except Exception as exc:
        print(f"  [warn] genre filter failed ({exc}) — keeping all candidates.")
        return items
    filtered = [it for i, it in enumerate(items) if i in keep]
    return filtered or items  # never empty the section on an over-eager filter


# --- Music dedup helpers ---------------------------------------------------
# Strict dedup so the same article never recurs: we match on a normalized URL
# (case/host/query/trailing-slash insensitive) AND on a title fingerprint, so a
# post slipping through under a variant URL — or the same headline from another
# source — is still caught. Title fingerprints are persisted in the music history
# bucket with a "title::" prefix.
_LANDING_STEMS = {
    "blog", "news", "music", "features", "reviews", "albums",
    "stories", "articles", "posts", "tag", "tags", "category", "categories",
}


def _norm_url(u: str) -> str:
    """Canonical form of a URL for dedup: drop fragment + query, lowercase the
    host (minus www.), and strip a trailing slash."""
    if not u:
        return ""
    p = urlparse(u.strip())
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "").rstrip("/")
    return f"{host}{path}".lower()


def _title_key(t: str) -> str:
    """Alphanumeric-only lowercase fingerprint of a title."""
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def _is_landing_url(u: str) -> bool:
    """True for bare-domain / index / tag pages (e.g. sofarsounds.com/blog,
    bandcamp.com/tag/cozy) — the 'generic front page' links, not real articles."""
    segs = [s for s in urlparse(u or "").path.split("/") if s]
    if not segs:
        return True
    if segs[0].lower() in _LANDING_STEMS and len(segs) == 1:
        return True
    if segs[0].lower() in {"tag", "tags", "category", "categories"}:
        return True
    return False


MUSIC_EVERGREEN: list[dict] = [
    {
        "source": "music",
        "source_name": "Sofar Sounds",
        "title": "Best of Sofar: Sessions Worth Revisiting",
        "url": "https://www.sofarsounds.com/blog",
        "snippet": "The archives were a bit quiet this morning, so I've pulled a timeless favorite for your coffee.",
        "genre": "",
        "cover_url": "",
        "embed_url": None,
    },
    {
        "source": "music",
        "source_name": "Bandcamp",
        "title": "Bandcamp: Cozy — Music to Settle Into",
        "url": "https://bandcamp.com/tag/cozy",
        "snippet": "The archives were a bit quiet this morning, so I've pulled a timeless favorite for your coffee.",
        "genre": "",
        "cover_url": "",
        "embed_url": None,
    },
]


def _scrape_links(page_url: str, session: requests.Session) -> list[tuple[str, str]]:
    """Fetch a page via the hardened helper and return de-duplicated
    (anchor_text, absolute_url) pairs worth showing to Claude."""
    parsed = urlparse(page_url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    resp = _fetch_with_retry(page_url, session, referer=referer)
    if resp is None:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    # Obvious non-article paths to skip so real posts aren't crowded out.
    deny = (
        "/login", "/subscribe", "/signup", "/account", "/products", "/shop",
        "/newsletter", "/category/", "/categories", "/tag/", "/tags",
        "/about", "/contact", "/privacy", "/terms", "/advertise", "/jobs",
        "/feed", "/rss", "/search",
    )
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"].strip()
        if len(text) < 5 or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absu = urljoin(page_url, href).split("#")[0]
        if absu in seen or any(frag in absu.lower() for frag in deny):
            continue
        seen.add(absu)
        links.append((text[:120], absu))
        if len(links) >= 80:
            break
    return links


def _rss_music_items(src: dict, n: int, session: requests.Session) -> list[dict]:
    """Parse an RSS feed and return up to n candidate music items."""
    resp = _fetch_with_retry(src["rss"], session, referer="https://www.google.com/")
    if resp is None:
        return []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        print(f"  [{src['name']}] RSS parse error: {exc}")
        return []
    items = []
    for item in root.findall(".//item")[:n]:
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        desc  = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()[:300]
        if not title or not link:
            continue
        # Try to grab cover from enclosure or media:thumbnail/content
        cover = ""
        enc = item.find("enclosure")
        if enc is not None and (enc.get("type", "").startswith("image") or enc.get("url", "").endswith((".jpg", ".png", ".webp"))):
            cover = enc.get("url", "")
        if not cover:
            for ns_prefix in ("media", "itunes"):
                thumb = item.find(f"{{{ns_prefix}}}thumbnail") or item.find(f"{{{ns_prefix}}}image")
                if thumb is not None:
                    cover = thumb.get("url", "") or (thumb.text or "")
                    break
        items.append({
            "source":      "music",
            "source_name": src["name"],
            "title":       title,
            "snippet":     desc,
            "url":         link,
            "genre":       "",
            "vibe_check":  "",
            "cover_url":   cover,
            "embed_url":   None,
        })
    return items


def fetch_music_articles(
    seen_all_urls: set[str] | None = None,
    seen_music_urls: set[str] | None = None,
) -> list[dict]:
    """Extract real artists/albums from each music source (RSS preferred,
    Claude scrape fallback), filter to the reader's genres, then enrich with an
    embed + cover image.

    Strict dedup so the same article never appears twice across editions: a
    candidate is rejected if its normalized URL OR its title fingerprint has been
    shown before (any section for URLs; the music history for titles). Generic
    front-page / tag / index links are dropped outright. Items actually shown —
    including the evergreen fallback — are registered so they can't recur."""
    seen_all_urls = seen_all_urls if seen_all_urls is not None else set()
    seen_music_urls = seen_music_urls if seen_music_urls is not None else set()

    # Reconstruct the seen sets from history: normalized URLs (cross-section) and
    # title fingerprints (stored in the music bucket with a "title::" prefix).
    seen_titles = {x[len("title::"):] for x in seen_music_urls if x.startswith("title::")}
    seen_norm = {_norm_url(x) for x in seen_all_urls}
    seen_norm |= {_norm_url(x) for x in seen_music_urls if not x.startswith("title::")}
    seen_norm.discard("")

    def _seen(art: dict) -> bool:
        return _norm_url(art.get("url", "")) in seen_norm or _title_key(art.get("title", "")) in seen_titles

    def _register(art: dict) -> None:
        nu, tk = _norm_url(art.get("url", "")), _title_key(art.get("title", ""))
        seen_norm.add(nu); seen_titles.add(tk)
        seen_all_urls.add(art["url"]); seen_music_urls.add(art["url"])
        seen_music_urls.add("title::" + tk)

    print("[Music] Fetching music sources …")
    session = _scraper_session()

    candidates: list[dict] = []
    for src in MUSIC_SOURCES:
        try:
            if "rss" in src:
                items = _rss_music_items(src, MUSIC_CANDIDATES_PER_SOURCE, session)
                print(f"  [{src['name']}] {len(items)} RSS item(s)")
            else:
                links = _scrape_links(src["url"], session)
                if not links:
                    print(f"  [{src['name']}] page fetch returned no links — skipping")
                    continue
                items = claude_fetch.extract_music_from_links(
                    src["name"], src["url"], links, MUSIC_CANDIDATES_PER_SOURCE
                )
                print(f"  [{src['name']}] {len(items)} candidate(s) from {len(links)} links")
            candidates.extend(items)
        except Exception as exc:
            print(f"  [warn] music extraction failed for {src['name']}: {exc}")

    # Drop generic landing/index/tag pages — the "front page" noise, not articles.
    before = len(candidates)
    candidates = [c for c in candidates if c.get("url") and not _is_landing_url(c["url"])]
    dropped_landing = before - len(candidates)

    # Drop anything already shown (normalized URL or title), and any in-batch dupes.
    fresh, batch_seen = [], set()
    for c in candidates:
        key = (_norm_url(c["url"]), _title_key(c.get("title", "")))
        if _seen(c) or key in batch_seen:
            continue
        batch_seen.add(key)
        fresh.append(c)
    print(f"[Music] {len(fresh)} fresh candidate(s) "
          f"(dropped {dropped_landing} landing, {before - dropped_landing - len(fresh)} already-seen/dupes).")
    candidates = fresh

    if not candidates:
        print("[Music] No fresh candidates — trying evergreen fallback.")
        return _evergreen_fallback(_seen, _register)

    # Filter to the reader's taste, then cap per-source.
    from curator import build_claude_client  # reuses CLAUDE_API_KEY client
    kept = _filter_music_by_genre(candidates, build_claude_client())
    print(f"[Music] {len(kept)}/{len(candidates)} candidate(s) match genres.")

    per_source: dict[str, int] = {}
    selected: list[dict] = []
    for art in kept:
        name = art.get("source_name", "")
        if per_source.get(name, 0) >= MUSIC_ARTICLES_PER_SOURCE:
            continue
        per_source[name] = per_source.get(name, 0) + 1
        selected.append(art)
        _register(art)  # never recurs in a future edition (by URL or title)

    # Enrich with a distraction-free embed and a cover image (single fetch each).
    for art in selected:
        try:
            embed_url, cover_url = _find_embed_and_cover(art["url"], session)
        except Exception as exc:
            print(f"    [warn] enrich failed for '{art.get('title','')[:50]}': {exc}")
            embed_url, cover_url = None, None
        art["embed_url"] = embed_url
        if not art.get("cover_url"):
            art["cover_url"] = cover_url or ""

    if not selected:
        print("[Music] Nothing selected after filtering — trying evergreen fallback.")
        return _evergreen_fallback(_seen, _register)
    print(f"[Music] Total music items: {len(selected)}")
    return selected


def _evergreen_fallback(seen, register) -> list[dict]:
    """Return evergreen items not already shown, registering them so even the
    fallback never repeats. Empty if every evergreen entry has been used."""
    out = [e for e in MUSIC_EVERGREEN if not seen(e)]
    for e in out:
        register(e)
    if not out:
        print("[Music] Evergreen exhausted — no fresh music this edition.")
    return out


# ---------------------------------------------------------------------------
# Good News — RSS feeds (structured XML, never breaks on redesigns)
# ---------------------------------------------------------------------------

GOOD_NEWS_TOTAL = 3   # advisory only — fetch_good_news_articles pulls one per feed

GOOD_NEWS_FEEDS = [
    {
        "url":         "https://www.goodnewsnetwork.org/feed/",
        "source_name": "Good News Network",
    },
    {
        "url":         "https://www.positive.news/feed/",
        "source_name": "Positive News",
    },
    {
        "url":         "https://www.upworthy.com/feed/",
        "source_name": "Upworthy",
    },
    {
        # Solutions journalism — uplifting without being saccharine.
        "url":         "https://reasonstobecheerful.world/feed/",
        "source_name": "Reasons to be Cheerful",
    },
    {
        "url":         "https://www.optimistdaily.com/feed/",
        "source_name": "The Optimist Daily",
    },
]

DISCOVERY_FEEDS = [
    {
        "url":         "https://www.atlasobscura.com/feeds/latest",
        "source_name": "Atlas Obscura",
        "category":    "history",
    },
    {
        # British Museum's blog feed hard-403s every request (even via proxy), so it
        # never contributed. Smithsonian fills the same history/culture slot.
        "url":         "https://www.smithsonianmag.com/rss/latest_articles/",
        "source_name": "Smithsonian",
        "category":    "history",
    },
    {
        "url":         "https://www.sciencenews.org/feed",
        "source_name": "Science News",
        "category":    "science",
    },
    # Added for breadth + backlog so the Archive rarely runs dry (RSS is a
    # rolling window; more feeds = more headroom before everything is seen).
    {
        "url":         "https://publicdomainreview.org/rss.xml",
        "source_name": "The Public Domain Review",
        "category":    "history",
    },
    {
        "url":         "https://aeon.co/feed.rss",
        "source_name": "Aeon",
        "category":    "science",
    },
    {
        "url":         "https://daily.jstor.org/feed/",
        "source_name": "JSTOR Daily",
        "category":    "history",
    },
    {
        # Distinct from the /feeds/latest (places) feed above — this is essays.
        "url":         "https://www.atlasobscura.com/feeds/articles",
        "source_name": "Atlas Obscura",
        "category":    "history",
    },
    {
        # Ad-free, foundation-funded math/physics/biology writing.
        "url":         "https://api.quantamagazine.org/feed/",
        "source_name": "Quanta Magazine",
        "category":    "science",
    },
    {
        # Art, craft & design finds — pairs with the Crafty / Creative mood.
        "url":         "https://www.thisiscolossal.com/feed/",
        "source_name": "Colossal",
        "category":    "history",
    },
]
DISCOVERY_CANDIDATES_PER_SOURCE = 15
DISCOVERY_ARTICLES_PER_SOURCE   = 4

# Fermat's Library — one annotated academic paper per week (no RSS; scrape journal_club)
FERMAT_LIBRARY_URL = "https://www.fermatslibrary.com/journal_club"
FERMAT_PAPERS_PER_RUN = 1

# One Good Read — a single reflective essay/longread per edition.
READS_FEEDS = [
    {"url": "https://www.themarginalian.org/feed/", "source_name": "The Marginalian"},
    {"url": "https://aeon.co/feed.rss",             "source_name": "Aeon"},
    {"url": "https://nautil.us/feed/",              "source_name": "Nautilus"},
]
READS_CANDIDATES_PER_SOURCE = 4   # pull a few per feed, then keep the single best

_MYSTERY_KEYWORDS = {
    "mystery", "unknown", "discovery", "ancient", "secret",
    "lost", "hidden", "forgotten", "rare", "unearthed",
}


def _first_sentences(text: str, n: int = 3) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(sentences[:n])


def _mystery_score(title: str) -> int:
    return int(bool(_MYSTERY_KEYWORDS & set(title.lower().split())))


# ---------------------------------------------------------------------------
# From the Garden — deterministic almanac facts (no network)
# ---------------------------------------------------------------------------

# Known new moon (UTC): 2000-01-06 18:14. Synodic month = 29.530588853 days.
_NEW_MOON_EPOCH = datetime.datetime(2000, 1, 6, 18, 14, tzinfo=ZoneInfo("UTC"))
_SYNODIC_MONTH  = 29.530588853

_MOON_PHASES = [
    "New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
    "Full moon", "Waning gibbous", "Last quarter", "Waning crescent",
]


def _moon_phase(dt: datetime.datetime) -> dict:
    """Deterministic moon phase from date — no API. Returns label + % illuminated."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    days = (dt - _NEW_MOON_EPOCH).total_seconds() / 86400.0
    age = days % _SYNODIC_MONTH          # 0..29.53 days into the cycle
    frac = age / _SYNODIC_MONTH          # 0..1 through the cycle
    # 8 named phases, each a 1/8 slice centred on its canonical age.
    label = _MOON_PHASES[int((frac + 1 / 16) % 1.0 * 8)]
    # Illuminated fraction: 0 at new, 100 at full, back to 0 at next new.
    import math
    illum = round((1 - math.cos(2 * math.pi * frac)) / 2 * 100)
    return {"label": label, "illum_pct": illum}


# Northern-hemisphere seasonal label, tuned for a temperate (Zurich) garden.
_SEASON_BY_MONTH = {
    1: "Deep winter", 2: "Late winter", 3: "Early spring", 4: "Mid spring",
    5: "Late spring", 6: "Early summer", 7: "High summer", 8: "Late summer",
    9: "Early autumn", 10: "Mid autumn", 11: "Late autumn", 12: "Deep winter",
}


def _season(dt: datetime.datetime) -> str:
    """Coarse N-hemisphere season label from the month."""
    return _SEASON_BY_MONTH.get(dt.month, "")


# Coordinates per garden locale, so the almanac can carry *real* local sun times
# (sunrise/sunset/twilight) rather than a generic season label. Keyed by the
# GARDEN_LOCALE env value. Add a row here to support a new regional edition.
LOCALE_COORDS = {
    "Zürich":                          (47.37, 8.54),
    "Annapolis Valley, Nova Scotia":   (45.03, -64.50),
}


def _sun_times(locale: str, date: datetime.date) -> dict:
    """
    Real local sunrise/sunset/twilight for a locale via sunrise-sunset.org (free,
    no key). Best-effort: returns {} on any failure so the garden note still
    renders. Times are formatted "HH:MM" in EDITION_TZ.
    """
    coords = LOCALE_COORDS.get(locale)
    if not coords:
        return {}
    lat, lng = coords
    url = (
        "https://api.sunrise-sunset.org/json"
        f"?lat={lat}&lng={lng}&date={date.isoformat()}&formatted=0"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # network, JSON, non-200 — all non-fatal
        print(f"  [warn] sun-times fetch failed for {locale}: {exc}")
        return {}
    if payload.get("status") != "OK":
        return {}
    res = payload.get("results", {})

    def _fmt(key: str) -> str:
        iso = res.get(key)
        if not iso:
            return ""
        try:
            return (
                datetime.datetime.fromisoformat(iso)
                .astimezone(EDITION_TZ)
                .strftime("%H:%M")
            )
        except Exception:
            return ""

    out = {
        "sunrise":       _fmt("sunrise"),
        "sunset":        _fmt("sunset"),
        "dawn":          _fmt("civil_twilight_begin"),
        "dusk":          _fmt("civil_twilight_end"),
    }
    # Drop the whole block if we couldn't resolve the two essentials.
    if not out["sunrise"] or not out["sunset"]:
        return {}
    return out


# Public read-through proxies, tried in order when a feed blocks our egress IP.
# Some publishers (Atlas Obscura, Science News) are fronted by Cloudflare and 403
# datacenter IPs like GitHub Actions runners, even with a browser UA. These relays
# fetch the feed from their own IPs and hand back the raw bytes.
_RSS_PROXY_BUILDERS = [
    lambda u: "https://api.codetabs.com/v1/proxy/?quest=" + quote(u, safe=""),
    lambda u: "https://api.allorigins.win/raw?url=" + quote(u, safe=""),
]


def _rss_item_count(content: bytes) -> int:
    """Number of <item> elements in `content`, or -1 if it isn't parseable RSS."""
    try:
        return len(ET.fromstring(content).findall(".//item"))
    except Exception:
        return -1


def _fetch_feed_bytes(
    feed_url: str, source_name: str, session: requests.Session
) -> bytes | None:
    """Return raw RSS bytes for `feed_url`, trying a direct fetch first and then
    public proxies if the direct path is blocked or returns a non-RSS body
    (e.g. a Cloudflare challenge page). Returns None if every path fails."""
    resp = _fetch_with_retry(feed_url, session, referer="https://www.google.com/")
    if resp is not None and _rss_item_count(resp.content) > 0:
        return resp.content

    for build_proxy in _RSS_PROXY_BUILDERS:
        proxy_url = build_proxy(feed_url)
        try:
            r = http_fetch.fetch(proxy_url, timeout=30, retries=2, retry_delay=3)
        except requests.RequestException:
            continue
        if _rss_item_count(r.content) > 0:
            print(f"  [{source_name}] direct fetch blocked — recovered via proxy.")
            return r.content

    print(f"  [warn] {source_name}: direct and proxy fetches all failed/empty.")
    return None


def _fetch_rss_articles(
    feed_url: str, source_name: str, limit: int, session: requests.Session,
    source_tag: str = "good_news",
) -> list[dict]:
    """
    Fetch up to `limit` articles from an RSS feed using xml.etree (stdlib).
    Far more reliable than HTML scraping — RSS is a stable, published contract.
    Falls back to public read-through proxies when a feed blocks our egress IP.
    """
    content = _fetch_feed_bytes(feed_url, source_name, session)
    if content is None:
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        print(f"  [warn] RSS parse error ({source_name}): {exc}")
        return []

    articles: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url   = (item.findtext("link")  or "").strip()
        if not title or not url:
            continue
        raw_desc = item.findtext("description") or ""
        snippet  = _first_sentences(
            BeautifulSoup(raw_desc, "html.parser").get_text(" ", strip=True)
        )
        articles.append(
            {
                "source":      source_tag,
                "source_name": source_name,
                "title":       title,
                "url":         url,
                "snippet":     snippet,
            }
        )
        if len(articles) >= limit:
            break

    return articles


# Local news feeds per regional edition, keyed by GARDEN_LOCALE. Used only by the
# regional re-send to add a small "Around the Valley" block. CBC's regional feeds
# are reliable, non-Cloudflare, and update frequently.
REGIONAL_FEEDS = {
    "Annapolis Valley, Nova Scotia": {
        "url":         "https://www.cbc.ca/webfeed/rss/rss-canada-novascotia",
        "source_name": "CBC Nova Scotia",
    },
}


def fetch_regional(locale: str, n: int = 2) -> list[dict]:
    """
    Fetch the newest `n` local-news items for a regional edition (e.g. CBC Nova
    Scotia for the Annapolis Valley). Best-effort: returns [] on any failure or if
    the locale has no configured feed, so the regional email simply omits the block.
    """
    feed = REGIONAL_FEEDS.get(locale)
    if not feed:
        return []
    try:
        session = _scraper_session()
        items = _fetch_rss_articles(
            feed["url"], feed["source_name"], n, session, source_tag="regional"
        )
    except Exception as exc:
        print(f"  [warn] regional fetch failed for {locale}: {exc}")
        return []
    print(f"[Regional] Collected {len(items)} local item(s) for {locale}.")
    return items


def fetch_good_news_articles(
    seen_all_urls: set[str],
    seen_good_news_urls: set[str],
) -> list[dict]:
    """
    Fetch one article from each feed in GOOD_NEWS_FEEDS independently.
    Each source always contributes its own slot; failures produce 0 from that source.
    Checks seen_all_urls (full cross-bucket history) to prevent duplicates; writes
    accepted URLs to both seen_all_urls and seen_good_news_urls.
    Runs on both AM and PM emails.
    """
    print("[GoodNews] Fetching good news RSS feeds …")
    session = _scraper_session()
    results = []

    for feed in GOOD_NEWS_FEEDS:
        fetched = _fetch_rss_articles(feed["url"], feed["source_name"], 1, session)
        for article in fetched:
            url = article["url"]
            if url in seen_all_urls:
                print(f"  [skip/dup] Good News article already in history: {url}")
                continue
            seen_all_urls.add(url)
            seen_good_news_urls.add(url)
            results.append(article)

    print(f"[GoodNews] Collected {len(results)} article(s).")

    # Enrich with cover images (og:image) from each article page
    for article in results:
        try:
            _, cover = _find_embed_and_cover(article["url"], session)
            article["cover_url"] = cover or ""
        except Exception as exc:
            print(f"  [warn] cover fetch failed for '{article.get('title','')[:50]}': {exc}")
            article["cover_url"] = ""

    return results


def _scrape_fermat_papers(session: requests.Session, n: int = 1) -> list[dict]:
    """Scrape the Fermat's Library Journal Club page for recent annotated papers.

    Returns up to `n` articles in the standard discovery format. Fermat's Library
    has no RSS feed, so we parse the paper-container elements directly. Fail-silent:
    any network or parsing error returns an empty list.
    """
    resp = _fetch_with_retry(FERMAT_LIBRARY_URL, session, referer="https://www.fermatslibrary.com/")
    if resp is None:
        print("[Fermat] Could not fetch journal_club page — skipping.")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for link_el in soup.select("a.paper-container"):
        if len(results) >= n:
            break
        href = link_el.get("href", "")
        if not href or not href.startswith("/s/"):
            continue
        url = f"https://www.fermatslibrary.com{href}"
        title_el   = link_el.select_one(".paper-title")
        authors_el = link_el.select_one(".paper-author")
        title      = (title_el.get_text(strip=True) if title_el else "").strip()
        # Strip the "- N comments" suffix Fermat appends to author text
        authors    = re.sub(r"\s*-\s*\d+\s*comments?\s*$", "",
                            (authors_el.get_text(strip=True) if authors_el else ""),
                            flags=re.I).strip()
        if not title:
            continue
        snippet = f"By {authors}" if authors else ""
        results.append({
            "source":      "discovery",
            "source_name": "Fermat's Library",
            "title":       title,
            "url":         url,
            "snippet":     snippet,
            "category":    "science",
        })
    print(f"[Fermat] Scraped {len(results)} paper(s).")
    return results


def fetch_discovery(
    seen_all_urls: set[str],
    seen_discovery_urls: set[str],
) -> list[dict]:
    """
    Fetch History/Mystery and Science articles from curated RSS feeds.
    Fetches DISCOVERY_CANDIDATES_PER_SOURCE candidates per source, priority-sorts
    by mystery keywords, then keeps DISCOVERY_ARTICLES_PER_SOURCE per source.
    Checks seen_all_urls (full cross-bucket history) to prevent duplicates; writes
    accepted URLs to both seen_all_urls and seen_discovery_urls.
    Runs on both AM and PM emails.
    """
    print("[Discovery] Fetching discovery RSS feeds …")
    session = _scraper_session()
    results = []

    for feed in DISCOVERY_FEEDS:
        candidates = _fetch_rss_articles(
            feed["url"], feed["source_name"],
            DISCOVERY_CANDIDATES_PER_SOURCE, session,
            source_tag="discovery",
        )
        candidates.sort(key=lambda a: _mystery_score(a["title"]), reverse=True)

        taken = 0
        for article in candidates:
            if taken >= DISCOVERY_ARTICLES_PER_SOURCE:
                break
            url = article["url"]
            if url in seen_all_urls:
                print(f"  [skip/dup] Discovery article already in history: {url}")
                continue
            seen_all_urls.add(url)
            seen_discovery_urls.add(url)
            results.append({**article, "category": feed["category"]})
            taken += 1

    # Fermat's Library — scrape the weekly annotated academic paper
    fermat_session = _scraper_session()
    for paper in _scrape_fermat_papers(fermat_session, n=FERMAT_PAPERS_PER_RUN):
        url = paper["url"]
        if url in seen_all_urls:
            print(f"  [skip/dup] Fermat paper already in history: {url}")
            continue
        seen_all_urls.add(url)
        seen_discovery_urls.add(url)
        results.append(paper)

    print(f"[Discovery] Collected {len(results)} article(s).")

    # Enrich with cover images (og:image) from each article page
    session2 = _scraper_session()
    for article in results:
        try:
            _, cover = _find_embed_and_cover(article["url"], session2)
            article["cover_url"] = cover or ""
        except Exception as exc:
            print(f"  [warn] cover fetch failed for '{article.get('title','')[:50]}': {exc}")
            article["cover_url"] = ""

    return results


def fetch_reads(
    seen_all_urls: set[str],
    seen_reads_urls: set[str],
) -> list[dict]:
    """
    Fetch reflective essays/longreads from READS_FEEDS and return the SINGLE best
    fresh one (this is one featured read, not a grid). Pulls a few candidates per
    feed, dedups against seen_all_urls, and stops at the first unseen item.
    Accepted URL is written to both seen_all_urls and seen_reads_urls.
    Runs on both AM and PM emails.
    """
    print("[Reads] Fetching One Good Read feeds …")
    session = _scraper_session()

    chosen: dict | None = None
    for feed in READS_FEEDS:
        candidates = _fetch_rss_articles(
            feed["url"], feed["source_name"],
            READS_CANDIDATES_PER_SOURCE, session,
            source_tag="reads",
        )
        for article in candidates:
            url = article["url"]
            if url in seen_all_urls:
                continue
            seen_all_urls.add(url)
            seen_reads_urls.add(url)
            chosen = article
            break
        if chosen:
            break

    if not chosen:
        print("[Reads] No fresh read found this run.")
        return []

    try:
        _, cover = _find_embed_and_cover(chosen["url"], session)
        chosen["cover_url"] = cover or ""
    except Exception as exc:
        print(f"  [warn] cover fetch failed for '{chosen.get('title','')[:50]}': {exc}")
        chosen["cover_url"] = ""

    print(f"[Reads] Selected: {chosen.get('title','')[:60]} ({chosen.get('source_name','')})")
    return [chosen]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> dict:
    # Validate required env vars early
    missing = [
        var
        for var in ("YOUTUBE_API_KEY", "CLAUDE_API_KEY")
        if not os.environ.get(var)
    ]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    if not YOUTUBE_CHANNEL_IDS:
        raise ValueError("YOUTUBE_CHANNEL_IDS list is empty. Add channel IDs before running.")

    # Determine AM/PM from the edition timezone's local hour.
    now_ch = datetime.datetime.now(EDITION_TZ)
    is_am_email: bool = now_ch.hour < 12
    print(f"[fetch] Run type: {'AM' if is_am_email else 'PM'} "
          f"({GARDEN_LOCALE} hour {now_ch.hour})")

    (seen_ids, seen_good_news_urls, seen_discovery_urls,
     seen_reads_urls, seen_music_urls) = load_history()

    # Unified URL pool — checked by all RSS fetchers to prevent cross-bucket repeats
    seen_all_urls: set[str] = (
        seen_good_news_urls | seen_discovery_urls | seen_reads_urls | seen_music_urls
    )

    # --- YouTube ---
    # Wildcard runs on BOTH editions (2 × 100 quota units/day — fine within 10k).
    # Channel videos are capped one below MAX so the wildcard fits inside it.
    youtube = build_youtube_client()
    channel_videos = fetch_channel_videos(
        youtube, seen_ids, max_videos=MAX_VIDEOS_PER_EDITION - 1
    )
    try:
        trending_video = fetch_trending_video(youtube, seen_ids)
    except HttpError as exc:
        if "quotaExceeded" in str(exc):
            print("[YouTube] Quota exceeded during wildcard search — skipping trending video.")
            trending_video = None
        else:
            raise

    youtube_results = channel_videos + ([trending_video] if trending_video else [])

    # --- Music (every run) ---
    music_articles: list[dict] = fetch_music_articles(seen_all_urls, seen_music_urls)

    # --- Good News (every run) ---
    good_news_articles = fetch_good_news_articles(seen_all_urls, seen_good_news_urls)

    # --- Discovery: History/Mystery + Science (every run) ---
    discovery_articles = fetch_discovery(seen_all_urls, seen_discovery_urls)

    # --- One Good Read: a single reflective essay (every run) ---
    reads = fetch_reads(seen_all_urls, seen_reads_urls)

    # --- From the Garden: deterministic seasonal almanac (no network) ---
    garden_seed = {
        "date":   now_ch.date().isoformat(),
        "season": _season(now_ch),
        "moon":   _moon_phase(now_ch),
        "sun":    _sun_times(GARDEN_LOCALE, now_ch.date()),
        "is_am":  is_am_email,
        "locale": GARDEN_LOCALE,
    }

    # Last edition's puzzle (so this edition can print its answer) + the rolling
    # recent-puzzles list (so the generator avoids repeating itself).
    previous_puzzle: dict = {}
    recent_puzzles: list = []
    if HISTORY_FILE.exists():
        try:
            _hist = json.loads(HISTORY_FILE.read_text(encoding="utf-8-sig"))
            previous_puzzle = _hist.get("pending_puzzle") or {}
            recent_puzzles = _hist.get("recent_puzzles") or []
        except Exception:
            previous_puzzle, recent_puzzles = {}, []

    raw_payload = {
        "fetched_at": now_ch.isoformat(),
        "is_am_email": is_am_email,
        "youtube_videos": youtube_results,
        "music_articles": music_articles,
        "good_news_articles": good_news_articles,
        "discovery_articles": discovery_articles,
        "reads": reads,
        "garden_seed": garden_seed,
        "previous_puzzle": previous_puzzle,
        "recent_puzzles": recent_puzzles,
    }

    # Write raw fetch snapshot (useful for debugging / re-running curation without re-fetching)
    raw_file = Path(__file__).parent / "fetched_data.json"
    raw_file.write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\n[fetch] Raw data → {raw_file} "
        f"({len(channel_videos)} channel videos | "
        f"{'1 trending video' if trending_video else 'no trending video'} | "
        f"{len(music_articles)} music articles | "
        f"{len(good_news_articles)} good news articles | "
        f"{len(discovery_articles)} discovery articles | "
        f"{len(reads)} featured read)"
    )

    # --- Audit & Curation ---
    from curator import run_curation  # local import keeps startup fast when testing fetcher alone

    print("\n[curator] Starting audit & curation …")
    curated = run_curation(raw_payload)

    # --- Persist history ---
    # Deliberately AFTER curation: if curation raises, the consumed URLs and
    # video IDs are not saved, so the same content is retried next run instead
    # of being marked seen without ever having been published.
    new_puzzle = curated.get("puzzle") or {}
    # Append this edition's puzzle to the rolling anti-repetition memory (last 14).
    updated_recent = None
    if new_puzzle.get("prompt"):
        updated_recent = (recent_puzzles + [{
            "kind":   new_puzzle.get("kind", ""),
            "prompt": new_puzzle.get("prompt", ""),
            "answer": new_puzzle.get("answer", ""),
        }])[-14:]
    save_history(seen_ids, seen_good_news_urls, seen_discovery_urls,
                 seen_reads_urls, seen_music_urls,
                 pending_puzzle=(
                     {k: new_puzzle[k] for k in ("label", "prompt", "answer")}
                     if new_puzzle.get("answer") else None
                 ),
                 recent_puzzles=updated_recent)

    curated_file = Path(__file__).parent / "curated_data.json"
    curated_file.write_text(json.dumps(curated, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = curated["audit_summary"]
    music_line = (
        f" | Music: {summary.get('music_articles', 0)} articles"
    )
    print(
        f"\n[done] Curated data → {curated_file}\n"
        f"       YouTube: {summary['youtube_videos']} videos | "
        f"Themes: {summary['themes']}{music_line} | "
        f"Good News: {summary.get('good_news_articles', 0)} articles | "
        f"Discovery: {summary.get('discovery_articles', 0)} articles"
    )
    return curated


if __name__ == "__main__":
    main()
