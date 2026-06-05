"""Hardened HTTP fetch, ported from the daily-briefing engine
(briefing/sources/_fetch.py, itself ported from Ellipsis athena/scrapers).

Browser User-Agent + retries with backoff + timeout + raise_for_status.
This is the single chokepoint every scraping request should go through so a
flaky site or a bot-wall on one attempt doesn't silently yield a generic
front page (the root cause of the old music-scraper bugs)."""
from __future__ import annotations
import time
import requests

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url, method="GET", headers=None, timeout=60, retries=3,
          retry_delay=5, **kwargs):
    """GET (or other method) `url` with a real browser UA and retry/backoff.

    Returns the `requests.Response` on success (after raise_for_status), or
    re-raises the last error after exhausting `retries`."""
    hdrs = {**BROWSER_HEADERS, **(headers or {})}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(method, url, headers=hdrs, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(retry_delay)
    raise last_err
