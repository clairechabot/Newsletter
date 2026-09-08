"""
Ad / commerce filter
--------------------
The Larder's food feeds (The Kitchn especially, and The Guardian's affiliate
"Filter" vertical) mix genuine cooking writing with shopping content: deal
round-ups, clearance sales, sponsored product launches and "My Honest Review of
<brand> for 2026" affiliate reviews. Those read as adverts in the newsletter and
in The Grove, so they're kept out at two points:

  * `fetcher.fetch_larder` skips them when gathering, so they never enter an
    edition (or `history.json`) in the first place;
  * `webpage.build_grove` skips them when rebuilding The Grove from the saved
    editions, which retires the ones already archived.

Deliberately stdlib-only so both the fetcher and the (dependency-free) page
builder can import it.
"""
from __future__ import annotations

import re
from html import unescape as _unescape
from urllib.parse import urlparse

# --- Publisher verticals that exist to sell things -------------------------
# Whole sections whose entire output is shopping content, matched on the URL
# path. The Guardian's "The Filter" is its affiliate product-recommendation
# desk; The Kitchn tags its commerce posts in the slug.
_COMMERCE_URL_RE = re.compile(
    r"""
      /thefilter/                     # Guardian affiliate vertical
    | product-review                  # "…-spice-rack-product-review-…"
    | -(?:sale|sales|deal|deals)[-/]  # "…-labor-day-sale-2026", "…-deals-…"
    | clearance
    | (?:black-friday|prime-day|cyber-monday|amazon-prime)
    | gift-guide | gifts-for
    | coupon | discount
    | \bqvc\b
    """,
    re.I | re.X,
)

# --- Title/summary tells ---------------------------------------------------
# Each pattern on its own is enough. They're written tightly so editorial food
# writing ("The Cheap 1-Ingredient Glaze…", "Essential Vietnamese Coffee
# Drinks") doesn't trip them.
_COMMERCE_TEXT_RES = [
    re.compile(p, re.I) for p in (
        # price tags and discounts
        r"\$\s?\d",
        r"\b\d{1,3}\s?%\s?off\b",
        r"\bup to \d{1,3}\s?%",
        r"\b(?:on|for) sale\b",
        r"\bsale(?:s)?\b(?=[^.]*\b(?:shop|deal|off|price|buy|early|kitchen|summer|clearance)\b)",
        r"\bclearance\b",
        r"\bdeals\b",
        r"\bdeal of the (?:day|week)\b",
        r"\bdiscount(?:ed|s)?\b",
        r"\bcoupon\b",
        r"\bbreak the bank\b",
        r"\bunder \$?\d+\b",
        r"\b(?:black friday|prime day|cyber monday)\b",
        # affiliate review formats
        r"\b(?:my |our )?(?:honest|unfiltered|candid) review\b",
        r"\bproduct review\b",
        r"\breview(?:ed)? (?:of|for) \d{4}\b",
        r"\breview\b[^.]*\bfor \d{4}\b",
        r"\bi tried\b[^.]*\breview\b",
        r"\btop-rated\b",
        r"\btasted and rated\b",
        r"\bbest \(and worst\)\b",
        r"\bworth (?:the money|buying|the splurge)\b",
        r"\bwell worth (?:it|the)\b",
        # shopping language
        r"\bshopper(?:s)?\b",
        r"\bshopping\b",
        r"\bgift guide\b",
        r"\bgifts for\b",
        r"\bwhere to buy\b",
        r"\byou can buy\b",
        r"\bmembership fees\b",
        # product-launch PR
        r"\bjust launched\b",
        r"\b(?:newest|latest|new) launch\b",
        r"\bjust brought back\b",
        r"\b(?:guaranteed to |before it )?sell(?:s)? out\b",
        r"\bgiving away\b",
        r"\bgiveaway\b",
        r"\bsponsored\b",
        # product round-ups dressed as favourites ("Our Favorite Savory Scented
        # Candles…") — the noun list keeps recipe round-ups out of it
        r"\b(?:best|favou?rite|top|essential)\b[^.]{0,60}\b(?:organi[sz]ers?"
        r"|scented candles?|gadgets?|cookware|air fryers?|blenders?|appliances?"
        r"|dinnerware|stand mixers?|knife sets?|storage containers?|coolers?)\b",
    )
]

# Publisher RSS categories that mark a post as commerce outright. Taken from
# The Kitchn's own tagging, which is more reliable than any headline reading:
# its deal round-ups carry "shopping" / "sales & events" / "product roundup".
# Deliberately excludes "product module" and "product text link" — those mark an
# affiliate widget inside an otherwise ordinary recipe post.
_COMMERCE_TAGS = {
    "shopping", "deals", "deal", "sale", "sales", "sales & events",
    "affiliate", "sponsored", "gift guide", "gift guides",
    "product review", "product reviews", "product roundup", "product catalog",
    "the filter",
}


def _norm(text: str) -> str:
    """Decode entities and curly punctuation so the patterns see plain ASCII."""
    s = _unescape(_unescape(text or ""))
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"')
             .replace("—", " ").replace("–", " ")
             .replace("\xa0", " "))


def is_commerce(title: str = "", url: str = "", summary: str = "",
                tags: "list[str] | None" = None) -> bool:
    """True when an item is shopping content rather than something to read.

    Matches on the URL's publisher vertical/slug, on the title, and on any
    feed categories. The summary is checked only for the unmistakable tells
    (prices, discounts, "on sale") — RSS excerpts are noisy enough that the
    softer patterns produce false positives there.
    """
    if any((t or "").strip().lower() in _COMMERCE_TAGS for t in (tags or [])):
        return True

    if url:
        parsed = urlparse(url)
        path = _norm(parsed.path + "?" + (parsed.query or ""))
        if _COMMERCE_URL_RE.search(path):
            return True

    title_n = _norm(title)
    if title_n and any(rx.search(title_n) for rx in _COMMERCE_TEXT_RES):
        return True

    summary_n = _norm(summary)
    if summary_n:
        for rx in _COMMERCE_TEXT_RES[:8]:      # price/discount/sale patterns only
            if rx.search(summary_n):
                return True
    return False
