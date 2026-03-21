"""
Newsletter Data Fetcher
-----------------------
Fetches Reddit posts (via public .json endpoints — no API key required),
YouTube videos, and music articles with deduplication and OP context extraction,
then runs the AI audit + curation layer (curator.py).

Required environment variables:
    YOUTUBE_API_KEY
    CLAUDE_API_KEY
    EMAIL_USER, SMTP_PASS (reserved for downstream use)

Optional environment variables:
    REDDIT_USER_AGENT  — default: "newsletter-fetcher/1.0 (personal digest bot)"
                         Reddit's ToS requires a descriptive UA; add your username
                         e.g. "newsletter-fetcher/1.0 by u/YourUsername"

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
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Configuration — replace the placeholder lists before running
# ---------------------------------------------------------------------------

SUBREDDITS: list[str] = [
    "BreadMachines",
    "ObsidianMD",
    "BestofRedditorUpdates",
    "AmITheAngel",
    "pettyrevenge",
    "BenignExistence",
    "MaliciousCompliance",
    "ContainerGardening",
    "HobbyDrama",
    "LifeofNorman",
    "Vintagemenus",
    "OldRecipes",
    "CozyPlaces",
    "SimpleLiving",
]

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
REDDIT_WINDOW_HOURS = 12
REDDIT_REQUEST_DELAY = 2.0   # seconds between public API calls — stay well under rate limit
YOUTUBE_VIDEOS_PER_CHANNEL = 1        # 1 per channel conserves quota for wildcard search
YOUTUBE_MIN_DURATION_SECONDS = 60
YOUTUBE_WILDCARD_MIN_SECONDS = 300    # wildcard must be ≥ 5 minutes
YOUTUBE_DOUBLE_CHECK_SLEEP = 300  # 5 minutes

# Wildcard categories — one is chosen at random each run
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

# Reddit public API — no OAuth needed
REDDIT_USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT",
    "newsletter-fetcher/1.0 (personal digest bot)",
)

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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

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
# Reddit  (public .json endpoints — no API key required)
# ---------------------------------------------------------------------------

def _reddit_session() -> requests.Session:
    """Return a requests Session pre-configured with the required User-Agent."""
    session = requests.Session()
    session.headers.update({"User-Agent": REDDIT_USER_AGENT})
    return session


def _reddit_get(session: requests.Session, url: str) -> dict | None:
    """
    GET a Reddit .json URL, retrying once on 429.
    Returns the parsed JSON dict or None on failure.
    """
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            print(f"  [warn] Reddit rate-limited — sleeping {retry_after}s …")
            time.sleep(retry_after)
            resp = session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] Reddit request failed ({url}): {exc}")
        return None


def _within_window(utc_timestamp: float, hours: int = REDDIT_WINDOW_HOURS) -> bool:
    cutoff = datetime.datetime.now(UTC) - datetime.timedelta(hours=hours)
    post_time = datetime.datetime.fromtimestamp(utc_timestamp, tz=UTC)
    return post_time >= cutoff


def _fetch_op_context(
    session: requests.Session, sub_name: str, post_id: str, op_author: str
) -> str | None:
    """
    Fetch the comments listing for a post and return the first top-level comment
    written by the OP, or None.  Uses depth=1 to limit payload size.
    """
    url = (
        f"https://www.reddit.com/r/{sub_name}/comments/{post_id}.json"
        f"?limit=50&depth=1&sort=top"
    )
    time.sleep(REDDIT_REQUEST_DELAY)
    data = _reddit_get(session, url)
    if not data or len(data) < 2:
        return None

    for child in data[1].get("data", {}).get("children", []):
        c = child.get("data", {})
        if c.get("author") == op_author and c.get("body"):
            return c["body"]
    return None


def fetch_reddit_posts(session: requests.Session) -> list[dict]:
    """
    Fetch top posts from the last REDDIT_WINDOW_HOURS hours across all configured
    subreddits via Reddit's public /top.json endpoint (no auth required).
    Uses the 'day' time filter then trims to exactly 12 hours via datetime comparison.
    """
    results: list[dict] = []

    for sub_name in SUBREDDITS:
        print(f"[Reddit] Fetching r/{sub_name} …")
        url = f"https://www.reddit.com/r/{sub_name}/top.json?t=day&limit=100"

        try:
            data = _reddit_get(session, url)
            time.sleep(REDDIT_REQUEST_DELAY)
            if not data:
                continue

            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})

                if not _within_window(post.get("created_utc", 0)):
                    continue

                post_id = post.get("id", "")
                author  = post.get("author") or "[deleted]"

                op_context: str | None = None
                if author not in ("[deleted]", "AutoModerator"):
                    op_context = _fetch_op_context(session, sub_name, post_id, author)

                results.append(
                    {
                        "source": "reddit",
                        "subreddit": sub_name,
                        "id": post_id,
                        "title": post.get("title", ""),
                        "url": post.get("url", ""),
                        "score": post.get("score", 0),
                        "author": author,
                        "created_utc": post.get("created_utc", 0),
                        "selftext": post.get("selftext") or None,
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
        # Deduplicate: compare each videoId string against history
        skipped = [v for v in vid_ids if v in seen_ids]
        fresh_ids = [v for v in vid_ids if v not in seen_ids]
        if skipped:
            print(f"  [skip/dup] {len(skipped)} video(s) already in history for {ch_id}")
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

def _find_music_embed(article_url: str) -> str | None:
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
    try:
        resp = requests.get(article_url, headers=SCRAPER_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
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


def _scrape_sofar_sounds(limit: int) -> list[dict]:
    """
    Scrape latest articles from sofarsounds.com/blog.
    Returns a list of {title, url, snippet, embed_url, source_name} dicts.
    """
    url = MUSIC_SOURCES[0]["url"]
    try:
        resp = requests.get(url, headers=SCRAPER_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [warn] Sofar Sounds fetch failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: list[dict] = []

    candidates = (
        soup.select("article")
        or soup.select(".post")
        or soup.select(".blog-post")
        or soup.select("[class*='post-card']")
        or soup.select("[class*='blog-card']")
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
        embed_url = _find_music_embed(article_url)
        if embed_url:
            print(f"    [embed] found for '{title[:50]}'")

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


def _scrape_bandcamp_daily(limit: int) -> list[dict]:
    """
    Scrape latest articles from daily.bandcamp.com.
    Returns a list of {title, url, snippet, embed_url, source_name} dicts.
    """
    url = MUSIC_SOURCES[1]["url"]
    try:
        resp = requests.get(url, headers=SCRAPER_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [warn] Bandcamp Daily fetch failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: list[dict] = []

    candidates = (
        soup.select(".story")
        or soup.select("article")
        or soup.select(".daily-story")
        or soup.select("[class*='story']")
        or soup.select("[class*='post']")
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
        embed_url = _find_music_embed(article_url)
        if embed_url:
            print(f"    [embed] found for '{title[:50]}'")

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


def fetch_music_articles() -> list[dict]:
    """Fetch MUSIC_ARTICLES_PER_SOURCE articles from each music source."""
    print("[Music] Scraping music sources …")
    results = _scrape_sofar_sounds(MUSIC_ARTICLES_PER_SOURCE)
    results += _scrape_bandcamp_daily(MUSIC_ARTICLES_PER_SOURCE)
    print(f"[Music] Total articles collected: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# Good News Scraper
# ---------------------------------------------------------------------------

GOOD_NEWS_TOTAL = 2   # articles to collect across both sources

def _scrape_source(base_url: str, source_label: str, limit: int) -> list[dict]:
    """
    Generic scraper for news listing pages.
    Tries common article-card patterns; returns up to `limit` items.
    """
    try:
        resp = requests.get(base_url, headers=SCRAPER_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [warn] {source_label} fetch failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    candidates = (
        soup.select("article")
        or soup.select(".entry-title")
        or soup.select(".post")
        or soup.select("[class*='card']")
        or soup.select("[class*='story']")
    )

    articles: list[dict] = []
    for el in candidates[:limit * 3]:
        title_el = (
            el.select_one("h2 a") or el.select_one("h3 a")
            or el.select_one("h2")  or el.select_one("h3")
            or (el if el.name == "a" else None)
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        link_el = title_el if title_el.name == "a" else title_el.find("a")
        href = (link_el.get("href") or "") if link_el else ""
        if href.startswith("/"):
            parsed = urlparse(base_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"

        articles.append(
            {
                "source": "good_news",
                "source_name": source_label,
                "title": title,
                "url": href or base_url,
            }
        )
        if len(articles) >= limit:
            break

    return articles


def fetch_good_news_articles() -> list[dict]:
    """
    Fetch GOOD_NEWS_TOTAL articles from Good News Network, falling back to
    Positive News if the first source yields fewer than needed.
    Runs on both AM and PM emails.
    """
    print("[GoodNews] Scraping good news sources …")

    results = _scrape_source(
        "https://www.goodnewsnetwork.org/", "Good News Network", GOOD_NEWS_TOTAL
    )

    if len(results) < GOOD_NEWS_TOTAL:
        needed = GOOD_NEWS_TOTAL - len(results)
        fallback = _scrape_source(
            "https://www.positive.news/", "Positive News", needed
        )
        results.extend(fallback)

    results = results[:GOOD_NEWS_TOTAL]
    print(f"[GoodNews] Collected {len(results)} article(s).")
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

    if not SUBREDDITS:
        raise ValueError("SUBREDDITS list is empty. Add subreddit names before running.")
    if not YOUTUBE_CHANNEL_IDS:
        raise ValueError("YOUTUBE_CHANNEL_IDS list is empty. Add channel IDs before running.")

    # Determine AM/PM — based on UTC hour; AM runs at 08:00, PM runs at 20:00
    now_utc = datetime.datetime.now(UTC)
    is_am_email: bool = now_utc.hour < 12
    print(f"[fetch] Run type: {'AM' if is_am_email else 'PM'} (UTC hour {now_utc.hour})")

    seen_ids = load_history()

    # --- Reddit ---
    reddit_session = _reddit_session()
    reddit_posts = fetch_reddit_posts(reddit_session)

    # --- YouTube ---
    youtube = build_youtube_client()
    channel_videos = fetch_channel_videos(youtube, seen_ids)
    trending_video = fetch_trending_video(youtube, SUBREDDITS, seen_ids)

    youtube_results = channel_videos + ([trending_video] if trending_video else [])

    # --- Music (AM only) ---
    music_articles: list[dict] = []
    if is_am_email:
        music_articles = fetch_music_articles()
    else:
        print("[Music] PM email — skipping music section.")

    # --- Good News (every run) ---
    good_news_articles = fetch_good_news_articles()

    # --- Persist history ---
    save_history(seen_ids)

    raw_payload = {
        "fetched_at": now_utc.isoformat(),
        "is_am_email": is_am_email,
        "reddit_posts": reddit_posts,
        "youtube_videos": youtube_results,
        "music_articles": music_articles,
        "good_news_articles": good_news_articles,
    }

    # Write raw fetch snapshot (useful for debugging / re-running curation without re-fetching)
    raw_file = Path(__file__).parent / "fetched_data.json"
    raw_file.write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"\n[fetch] Raw data → {raw_file} "
        f"({len(reddit_posts)} Reddit posts | "
        f"{len(channel_videos)} channel videos | "
        f"{'1 trending video' if trending_video else 'no trending video'} | "
        f"{len(music_articles)} music articles | "
        f"{len(good_news_articles)} good news articles)"
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
        f"       Reddit: {summary['reddit_accepted']}/{summary['reddit_raw']} accepted "
        f"({summary['reddit_discarded']} discarded) | "
        f"YouTube: {summary['youtube_videos']} videos | "
        f"Themes: {summary['themes']}{music_line} | "
        f"Good News: {summary.get('good_news_articles', 0)} articles"
    )
    return curated


if __name__ == "__main__":
    main()
