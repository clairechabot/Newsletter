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
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Configuration — replace the placeholder lists before running
# ---------------------------------------------------------------------------


YOUTUBE_CHANNEL_IDS: list[str] = [
    "UCsaGKqPZnGp_7N80hcHySGQ", "UCHL9bfHTxCMi-7vfxQ-AYtg", "UCSbyncU597LMwb3HhnAI_4w",
    "UC-pkCUlaRDMA--8LTWQDuHA", "UCZwU2G-KVl-P-O-B35chZOQ", "UC4sEmXUuWIFlxRIFBRV6VXQ",
    "UCDdi0yUyGW1PKzYXaIACnuA", "UCNvsIonJdJ5E4EXMa65VYpA", "UCXcTkcC_H4XeDGfJ7rQGJaw",
    "UCvQECJukTDE2i6aCoMnS-Vg", "UCUA99fY1YylIrjeL9IH9SaA", "UC_-hYjoNe4PJNFa9iZ4lraA",
    "UCtBzfGaJzGGNJVOVM0mK4uQ", "UCIWGaKFnTIv97liBxlQ2Otw", "UC-SrCCzkGq0wmSAuRs7EBFg",
    "UCSwwoUNvQWgZDC8a_O6Qs_A", "UCqrqFLPh4cRM1VomUzG24sQ", "UCSHtaUm-FjUps090S7crO4Q",
    "UCLuYADJ6hESLHX87JnsGbjA", "UCzH5n3Ih5kgQoiDAQt2FwLw", "UCvy6TA5egUGHnZXVRYDKOhg",
    "UC4HRlp7zs7UpIFM67eGjhow", "UC9r61qohBg1qgGty4_WzojA", "UC_8x1VmhDgsU72Yktd9Ukeg",
    "UC6nSFpj9HTCZ5t-N3Rm3-HA", "UCEqU-Ts-hxmpnlWgRMgd2MQ", "UCmGSJVG3mCRXVOP4yZrU1Dw",
    "UC-lHJZR3Gqxm24_Vd_AJ5Yw", "UC3cpN6gcJQqcCM6mxRUo_dA", "UCJI86v9et-IZd1KJSfahN8g",
    "UCwQnoax3HWID1WOzZ4mqLPQ", "UC2Kyj04yISmHr1V-UlJz4eg", "UCRhQsN8AVIfZuBNeRV1A37w",
    "UCftwRNsjfRo08xYE31tkiyw", "UCNwZIGnHkzy6KpHPQtserzQ", "UCuu8TaJ-CPGV0_dJ-7OEY3A",
    "UCjz8uBTLs0f7Fnlxc5nzT5g", "UC_HF-dqn4lCs4fEA4GB210g",
]

HISTORY_FILE = Path(__file__).parent / "history.json"
YOUTUBE_VIDEOS_PER_CHANNEL = 1        # 1 per channel conserves quota for wildcard search
YOUTUBE_MIN_DURATION_SECONDS = 61
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

# Music scraper — 3 articles per source, AM email only
MUSIC_SOURCES: list[dict] = [
    {
        "name": "Sofar Sounds",
        "url": "https://www.sofarsounds.com/blog",
    },
    {
        "name": "Bandcamp Daily",
        "url": "https://daily.bandcamp.com/",
    },
]
MUSIC_ARTICLES_PER_SOURCE = 3
SCRAPER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) FernDigest/1.2",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT":             "1",
}

UTC = ZoneInfo("UTC")
ZURICH = ZoneInfo("Europe/Zurich")


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def load_history() -> tuple[set[str], set[str], set[str]]:
    """Return (video_ids, good_news_urls, discovery_urls) seen in previous runs."""
    if HISTORY_FILE.exists():
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return (
            set(data.get("video_ids", [])),
            set(data.get("good_news_urls", [])),
            set(data.get("discovery_urls", [])),
        )
    return set(), set(), set()


def save_history(
    seen_ids: set[str],
    seen_good_news_urls: set[str],
    seen_discovery_urls: set[str],
) -> None:
    """Persist seen video IDs, Good News URLs, and Discovery URLs back to disk."""
    existing: dict = {}
    if HISTORY_FILE.exists():
        existing = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    existing["video_ids"]       = sorted(seen_ids)
    existing["good_news_urls"]  = sorted(seen_good_news_urls)
    existing["discovery_urls"]  = sorted(seen_discovery_urls)
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

    `backoff` is the base wait in seconds; each retry doubles it.
    `referer` is injected as a Referer header when provided.
    Returns the Response on success, or None after all retries are exhausted.
    """
    headers = {"Referer": referer} if referer else {}
    delay = backoff

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=15)
            if resp.status_code in _RETRY_STATUSES:
                raise requests.HTTPError(response=resp)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            print(f"  [retry {attempt}/{retries}] Connection error for {url}: {exc}")
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            print(f"  [retry {attempt}/{retries}] HTTP {code} for {url}")

        if attempt < retries:
            time.sleep(delay)
            delay *= 2  # exponential back-off

    print(f"  [warn] Gave up fetching {url} after {retries} attempts.")
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
        duration_str = item.get("contentDetails", {}).get("duration", "PT0S")
        duration_sec = _parse_iso8601_duration(duration_str)
        url = f"https://www.youtube.com/watch?v={vid_id}"

        if _is_short(vid_id, url, duration_sec):
            print(f"  [skip/short] {vid_id} — {duration_sec}s < {YOUTUBE_MIN_DURATION_SECONDS}s")
            continue

        title = snippet["title"]
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
                "view_count": item["statistics"].get("viewCount"),
                "description": snippet.get("description", "")[:500],
            }
        )
    return videos


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
    Return the latest video IDs from an uploads playlist.
    Costs 1 quota unit per call (vs 100 for search.list).
    """
    resp = (
        youtube.playlistItems()
        .list(part="contentDetails", playlistId=playlist_id, maxResults=max_results)
        .execute()
    )
    return [item["contentDetails"]["videoId"] for item in resp.get("items", [])]


def fetch_channel_videos(youtube, seen_ids: set[str]) -> list[dict]:
    """
    Fetch the latest YOUTUBE_VIDEOS_PER_CHANNEL videos per channel.

    Quota cost breakdown (38 channels):
      - 1 call  to channels.list  for all 38 IDs  →  1 unit
      - 1 call  to playlistItems.list per channel  → 38 units
      - 1 call  to videos.list per ~50 fresh IDs   →  1 unit
      Total: ~40 units  (vs ~7,600 with the old search.list approach)

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
                youtube, playlist_id, max_results=YOUTUBE_VIDEOS_PER_CHANNEL * 3
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
            details = _fetch_video_details(youtube, fresh_ids)
            filtered = []
            for v in details:
                if _is_political(v["title"], v.get("description", "")):
                    print(f"  [skip/blocked] channel {v['video_id']} — '{v['title']}'")
                    continue
                if _is_clickbait(v["title"]):
                    print(f"  [skip/clickbait] channel {v['video_id']} — '{v['title']}'")
                    continue
                filtered.append(v)
            accepted = filtered[:YOUTUBE_VIDEOS_PER_CHANNEL]
            for v in accepted:
                seen_ids.add(v["video_id"])
            all_results.extend(accepted)
    except HttpError as exc:
        if "quotaExceeded" in str(exc):
            print("[YouTube] Quota exceeded during video detail fetch — using partial results.")
        else:
            raise

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

            details = _fetch_video_details(youtube, candidate_ids)

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

def _find_music_embed(article_url: str, session: requests.Session) -> str | None:
    """
    Fetch an article page and return the first distraction-free embed URL found.

    Priority order:
      1. Bandcamp EmbeddedPlayer iframe  → bandcamp.com/EmbeddedPlayer/...
      2. YouTube iframe                  → youtube.com/embed/VIDEO_ID
      3. Bare YouTube watch link         → converted to youtube.com/embed/VIDEO_ID
      4. Bare Bandcamp album/track link  → converted to EmbeddedPlayer URL

    Returns None if nothing playable is found or the page fetch fails.
    """
    if not article_url or article_url == "#":
        return None
    # Derive a plausible Referer from the article URL's origin
    parsed_origin = urlparse(article_url)
    referer = f"{parsed_origin.scheme}://{parsed_origin.netloc}/"
    resp = _fetch_with_retry(article_url, session, referer=referer)
    if resp is None:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for iframe in soup.find_all("iframe", src=True):
        src: str = iframe["src"]
        if "bandcamp.com/EmbeddedPlayer" in src:
            # Ensure it's https and strip any extra query cruft
            return src if src.startswith("http") else "https:" + src
        if "youtube.com/embed/" in src or "youtube-nocookie.com/embed/" in src:
            # Normalise to plain embed URL (strip autoplay etc.)
            vid_id = src.split("/embed/")[1].split("?")[0].split("&")[0]
            return f"https://www.youtube.com/embed/{vid_id}"

    # Fallback: bare YouTube watch links in the page body
    yt_match = re.search(
        r'https?://(?:www\.)?youtube\.com/watch\?v=([\w-]{11})', resp.text
    )
    if yt_match:
        return f"https://www.youtube.com/embed/{yt_match.group(1)}"

    # Fallback: Bandcamp album/track page link → convert to EmbeddedPlayer
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if re.search(r'bandcamp\.com/(album|track)/', href):
            # No numeric ID available from the link alone; return the clean page
            # URL — the renderer will show a "Listen on Bandcamp" button.
            return href.split("?")[0].rstrip("/")

    return None


def _scrape_sofar_sounds(limit: int, session: requests.Session) -> list[dict]:
    """
    Scrape latest articles from sofarsounds.com/blog.
    Returns a list of {title, url, snippet, embed_url, source_name} dicts.
    """
    url = MUSIC_SOURCES[0]["url"]
    resp = _fetch_with_retry(url, session, referer="https://www.sofarsounds.com/")
    if resp is None:
        print("  [warn] Sofar Sounds fetch failed after retries.")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: list[dict] = []

    candidates = (
        soup.select("article.post-card")
        or soup.select("[class*='post-card']")
        or soup.select("article")
        or soup.select(".post")
    )

    for el in candidates[:limit * 2]:
        title_el = (
            el.select_one("h2 a")
            or el.select_one("h3 a")
            or el.select_one("h2")
            or el.select_one("h3")
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        link_el = title_el if title_el.name == "a" else title_el.find("a")
        href = link_el["href"] if link_el and link_el.get("href") else ""
        if href and href.startswith("/"):
            href = "https://www.sofarsounds.com" + href

        snippet_el = (
            el.select_one("p")
            or el.select_one("[class*='excerpt']")
            or el.select_one("[class*='summary']")
        )
        snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""

        if not title:
            continue

        article_url = href or url
        time.sleep(1)  # polite delay before fetching article page
        try:
            embed_url = _find_music_embed(article_url, session)
            if embed_url:
                print(f"    [embed] found for '{title[:50]}'")
        except Exception as exc:
            print(f"    [warn] embed lookup failed for '{title[:50]}': {exc}")
            embed_url = None

        articles.append(
            {
                "source": "music",
                "source_name": "Sofar Sounds",
                "title": title,
                "url": article_url,
                "snippet": snippet,
                "embed_url": embed_url,
            }
        )
        if len(articles) >= limit:
            break

    print(f"[Music] Sofar Sounds → {len(articles)} article(s)")
    return articles


def _scrape_bandcamp_daily(limit: int, session: requests.Session) -> list[dict]:
    """
    Scrape latest articles from daily.bandcamp.com.
    Returns a list of {title, url, snippet, embed_url, source_name} dicts.
    """
    url = MUSIC_SOURCES[1]["url"]
    resp = _fetch_with_retry(url, session, referer="https://daily.bandcamp.com/")
    if resp is None:
        print("  [warn] Bandcamp Daily fetch failed after retries.")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: list[dict] = []

    candidates = (
        soup.select("article.story")
        or soup.select(".story")
        or soup.select("[class*='story']")
        or soup.select("article")
    )

    for el in candidates[:limit * 2]:
        title_el = (
            el.select_one("h2 a")
            or el.select_one("h3 a")
            or el.select_one(".story-title a")
            or el.select_one("h2")
            or el.select_one("h3")
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        link_el = title_el if title_el.name == "a" else title_el.find("a")
        href = link_el["href"] if link_el and link_el.get("href") else ""
        if href and href.startswith("/"):
            href = "https://daily.bandcamp.com" + href

        snippet_el = (
            el.select_one(".story-excerpt")
            or el.select_one("[class*='excerpt']")
            or el.select_one("p")
        )
        snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""

        if not title:
            continue

        article_url = href or url
        time.sleep(1)
        try:
            embed_url = _find_music_embed(article_url, session)
            if embed_url:
                print(f"    [embed] found for '{title[:50]}'")
        except Exception as exc:
            print(f"    [warn] embed lookup failed for '{title[:50]}': {exc}")
            embed_url = None

        articles.append(
            {
                "source": "music",
                "source_name": "Bandcamp Daily",
                "title": title,
                "url": article_url,
                "snippet": snippet,
                "embed_url": embed_url,
            }
        )
        if len(articles) >= limit:
            break

    print(f"[Music] Bandcamp Daily → {len(articles)} article(s)")
    return articles


MUSIC_EVERGREEN: list[dict] = [
    {
        "source": "music",
        "source_name": "Sofar Sounds",
        "title": "Best of Sofar: Sessions Worth Revisiting",
        "url": "https://www.sofarsounds.com/blog",
        "snippet": "The archives were a bit quiet this morning, so I've pulled a timeless favorite for your coffee.",
        "embed_url": None,
    },
    {
        "source": "music",
        "source_name": "Bandcamp",
        "title": "Bandcamp: Cozy — Music to Settle Into",
        "url": "https://bandcamp.com/tag/cozy",
        "snippet": "The archives were a bit quiet this morning, so I've pulled a timeless favorite for your coffee.",
        "embed_url": None,
    },
]


def fetch_music_articles() -> list[dict]:
    """Fetch MUSIC_ARTICLES_PER_SOURCE articles from each music source."""
    print("[Music] Scraping music sources …")
    session = _scraper_session()
    results  = _scrape_sofar_sounds(MUSIC_ARTICLES_PER_SOURCE, session)
    results += _scrape_bandcamp_daily(MUSIC_ARTICLES_PER_SOURCE, session)
    if not results:
        print("[Music] Both scrapers returned 0 results — using evergreen fallback.")
        results = MUSIC_EVERGREEN
    print(f"[Music] Total articles collected: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# Good News — RSS feeds (structured XML, never breaks on redesigns)
# ---------------------------------------------------------------------------

GOOD_NEWS_TOTAL = 3   # one article per source

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
]

DISCOVERY_FEEDS = [
    {
        "url":         "https://www.atlasobscura.com/feeds/latest",
        "source_name": "Atlas Obscura",
        "category":    "history",
    },
    {
        "url":         "https://www.britishmuseum.org/blog/rss.xml",
        "source_name": "British Museum",
        "category":    "history",
    },
    {
        "url":         "https://www.quantamagazine.org/feed",
        "source_name": "Quanta Magazine",
        "category":    "science",
    },
]
DISCOVERY_CANDIDATES_PER_SOURCE = 8
DISCOVERY_ARTICLES_PER_SOURCE   = 2

_MYSTERY_KEYWORDS = {
    "mystery", "unknown", "discovery", "ancient", "secret",
    "lost", "hidden", "forgotten", "rare", "unearthed",
}


def _first_sentences(text: str, n: int = 3) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(sentences[:n])


def _mystery_score(title: str) -> int:
    return int(bool(_MYSTERY_KEYWORDS & set(title.lower().split())))


def _fetch_rss_articles(
    feed_url: str, source_name: str, limit: int, session: requests.Session,
    source_tag: str = "good_news",
) -> list[dict]:
    """
    Fetch up to `limit` articles from an RSS feed using xml.etree (stdlib).
    Far more reliable than HTML scraping — RSS is a stable, published contract.
    """
    resp = _fetch_with_retry(feed_url, session)
    if resp is None:
        print(f"  [warn] RSS fetch failed after retries ({source_name}).")
        return []

    try:
        root = ET.fromstring(resp.content)
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


def fetch_good_news_articles(seen_urls: set[str]) -> list[dict]:
    """
    Fetch one article from each feed in GOOD_NEWS_FEEDS independently.
    Each source always contributes its own slot; failures produce 0 from that source.
    Skips any article whose URL was already seen in a previous run.
    Runs on both AM and PM emails.
    """
    print("[GoodNews] Fetching good news RSS feeds …")
    session = _scraper_session()
    results = []

    for feed in GOOD_NEWS_FEEDS:
        fetched = _fetch_rss_articles(feed["url"], feed["source_name"], 1, session)
        for article in fetched:
            url = article["url"]
            if url in seen_urls:
                print(f"  [skip/dup] Good News article already in history: {url}")
                continue
            seen_urls.add(url)
            results.append(article)

    print(f"[GoodNews] Collected {len(results)} article(s).")
    return results


def fetch_discovery(seen_urls: set[str]) -> list[dict]:
    """
    Fetch History/Mystery and Science articles from curated RSS feeds.
    Fetches DISCOVERY_CANDIDATES_PER_SOURCE candidates per source, priority-sorts
    by mystery keywords, then keeps DISCOVERY_ARTICLES_PER_SOURCE per source.
    Deduplicates against seen_urls (backed by history.json).
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
            if url in seen_urls:
                print(f"  [skip/dup] Discovery article already in history: {url}")
                continue
            seen_urls.add(url)
            results.append({**article, "category": feed["category"]})
            taken += 1

    print(f"[Discovery] Collected {len(results)} article(s).")
    return results


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

    # Determine AM/PM — based on Zurich hour; AM runs at 10:00, PM runs at 22:00 CEST
    now_ch = datetime.datetime.now(ZURICH)
    is_am_email: bool = now_ch.hour < 12
    print(f"[fetch] Run type: {'AM' if is_am_email else 'PM'} (Zurich hour {now_ch.hour})")

    seen_ids, seen_good_news_urls, seen_discovery_urls = load_history()

    # --- YouTube ---
    youtube = build_youtube_client()
    channel_videos = fetch_channel_videos(youtube, seen_ids)
    if is_am_email:
        print("[YouTube] AM email — skipping wildcard search.")
        trending_video = None
    else:
        try:
            trending_video = fetch_trending_video(youtube, seen_ids)
        except HttpError as exc:
            if "quotaExceeded" in str(exc):
                print("[YouTube] Quota exceeded during wildcard search — skipping trending video.")
                trending_video = None
            else:
                raise

    youtube_results = channel_videos + ([trending_video] if trending_video else [])

    # --- Music (AM only) ---
    music_articles: list[dict] = []
    if is_am_email:
        music_articles = fetch_music_articles()
    else:
        print("[Music] PM email — skipping music section.")

    # --- Good News (every run) ---
    good_news_articles = fetch_good_news_articles(seen_good_news_urls)

    # --- Discovery: History/Mystery + Science (every run) ---
    discovery_articles = fetch_discovery(seen_discovery_urls)

    # --- Persist history ---
    save_history(seen_ids, seen_good_news_urls, seen_discovery_urls)

    raw_payload = {
        "fetched_at": now_ch.isoformat(),
        "is_am_email": is_am_email,
        "youtube_videos": youtube_results,
        "music_articles": music_articles,
        "good_news_articles": good_news_articles,
        "discovery_articles": discovery_articles,
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
        f"{len(discovery_articles)} discovery articles)"
    )

    # --- Audit & Curation ---
    from curator import run_curation  # local import keeps startup fast when testing fetcher alone

    print("\n[curator] Starting audit & curation …")
    curated = run_curation(raw_payload)

    curated_file = Path(__file__).parent / "curated_data.json"
    curated_file.write_text(json.dumps(curated, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = curated["audit_summary"]
    music_line = (
        f" | Music: {summary.get('music_articles', 0)} articles"
        if is_am_email else ""
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
