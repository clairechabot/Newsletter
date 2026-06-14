# The Curated Canopy

An automated, twice-daily newsletter curated by **Fern**, an AI editor with a warm,
cozy, slightly-witty voice. Each edition gathers videos, music, good news, archive
oddities, one good long-read, and a small seasonal garden almanac, then ships a short
email "cover" that links out to a richer interactive web edition.

- **Morning Rise** (AM) and **Evening Wind-down** (PM) editions, named like a periodical.
- **Email** is a deliberately short cover: Fern's note, a garden almanac line, today's
  opening feature, and a linked table of contents.
- **Web edition** is the full browsable magazine (masthead, sticky section tabs, music
  genre filter, large imagery), published to GitHub Pages.

---

## How it works

```
fetcher.py  ──►  curator.py  ──►  renderer.py  ──►  email (SMTP)
   │               (Claude)            └─► webpage.py ──► docs/index.html (web edition)
   │
   └─ gathers + dedups content      writes curated_data.json
```

1. **`fetcher.py`** — gathers raw content from every source, dedups it against
   `history.json`, and writes `fetched_data.json` (raw snapshot) and, after curation,
   `curated_data.json`. AM vs PM is decided by the Zurich hour (`< 12` = AM).
2. **`curator.py`** — uses Claude (`claude-sonnet-4-6`) to audit and enrich the raw
   content: "why watch" blurbs, creative theme names, music vibe checks, good-news
   "reasons to be hopeful", Fern's archive notes, the long-read blurb, the garden note,
   and Fern's daily greeting + edition title.
3. **`renderer.py`** — builds the **email** (bulletproof, email-client-safe table
   layout) and sends it via SMTP. Also orchestrates the web edition.
4. **`webpage.py`** — builds the self-contained interactive **web edition**
   (`docs/index.html`).

Helpers: `http_fetch.py` (hardened browser-UA fetch with retries) and `claude_fetch.py`
(Claude web-fetch music extractor).

---

## Sections

| Section | Source | Runs |
|---|---|---|
| **A note from Fern** | Claude-generated greeting | AM + PM |
| **From the Garden** | Deterministic almanac (season + moon phase, no network) + Claude note | AM + PM |
| **Today's opening** (hero) | First curated YouTube video | AM + PM |
| **The Morning Soundtrack** | 7 music RSS feeds (NPR, Pitchfork, Stereogum, Bandcamp Daily, JazzTimes, No Depression, Sofar) | AM |
| **Worth Watching** | 32 YouTube channels (1 video each) + 1 trending wildcard | AM (+ wildcard PM) |
| **Global Silver Linings** | Good News Network, Positive News, Upworthy | AM + PM |
| **From the Archives** | Atlas Obscura, Smithsonian, Science News, Fermat's Library | AM + PM |
| **One Good Read** | The Marginalian, Aeon, Nautilus (single best essay) | AM + PM |

Music items are filtered to the reader's taste (`MUSIC_GENRES` in `fetcher.py`) by Claude.

### No repeats — history dedup
`history.json` tracks everything already shown so nothing recurs across editions, in
five buckets: `video_ids`, `good_news_urls`, `discovery_urls`, `reads_urls`,
`music_urls`. The evergreen music fallback is intentionally exempt (it may recur on
quiet days).

### Bot-blocked feeds — proxy fallback
Some publishers (Atlas Obscura, Science News) are Cloudflare-fronted and 403 datacenter
IPs like GitHub Actions runners. `fetcher.py` fetches feeds directly first and, only
when blocked, retries through public read-through relays (`api.codetabs.com`, then
`api.allorigins.win`). Non-blocked feeds always take the fast direct path.

---

## Running locally

```bash
pip install -r requirements.txt

# Generate curated_data.json (needs YouTube + Claude keys)
python fetcher.py

# Build the email + web edition. ALLOW_NO_EMAIL=1 previews without sending.
ALLOW_NO_EMAIL=1 python renderer.py
# → writes newsletter.html (email) and docs/index.html (web edition)
```

`curated_data.json`, `fetched_data.json`, and `newsletter.html` are per-run artifacts
(git-ignored); `history.json`, `docs/index.html`, `docs/archive.html`, and
`docs/editions/` persist (committed back each run).

---

## Configuration (environment variables)

**Required**
- `YOUTUBE_API_KEY` — YouTube Data API v3 key.
- `CLAUDE_API_KEY` — Anthropic API key (curation).

**Email delivery** (renderer.py — both naming conventions accepted)
- `SMTP_USER` / `EMAIL_USER`, `SMTP_PASS`, `SMTP_SERVER` / `SMTP_HOST`, `SMTP_PORT`
- `EMAIL_TO` / `NEWSLETTER_RECIPIENTS` / `RECIPIENTS` — comma-separated recipients.

**Optional**
- `EDITION_URL` — public URL of the web edition (linked from the email).
- `GARDEN_LOCALE` — shown in the "From the Garden" eyebrow (default `Zürich`).
- `FERN_LOGO_URL` — optional masthead logo.
- `ALLOW_NO_EMAIL=1` — render only, skip sending (local previews / CI dry runs).
- `EDITION_DEPLOY_TOKEN` — PAT to publish the edition to the public Pages repo.

---

## Automation

`.github/workflows/daily_digest.yml` runs on a cron schedule (`0 5` and `0 16` UTC),
installs deps, runs `fetcher.py` then `renderer.py`, uploads the email artifact,
publishes `docs/index.html` to the public edition repo (`canopy-edition`), and commits
the updated `history.json`, `docs/index.html`, `docs/archive.html`, and the dated
edition file (`docs/editions/`) back to the branch. Secrets are configured in the
repository settings. The workflow can also be triggered manually via `workflow_dispatch`.

### Edition archive

Every run saves a permanent copy of the web edition to `docs/editions/YYYY-MM-DD-morning.html`
or `docs/editions/YYYY-MM-DD-evening.html`, and rebuilds `docs/archive.html` — a browsable
index of all past issues. GitHub Pages must be enabled (Settings → Pages → Source: branch
`main`, folder `/docs`) for the archive to be public at
`https://clairechabot.github.io/Newsletter/archive.html`.
The newsletter footer's "The Archive" link points there automatically.

---

## Layout

```
fetcher.py        gather + dedup content, write curated_data.json
curator.py        Claude audit + curation (voice, blurbs, themes, greeting)
renderer.py       email (table-safe) + SMTP send + orchestration
webpage.py        interactive web edition → docs/index.html
http_fetch.py     hardened HTTP fetch (browser UA, retries)
claude_fetch.py   Claude web-fetch music extractor
history.json      seen-content memory (dedup)
docs/index.html   current web edition (GitHub Pages)
docs/archive.html browsable index of every past edition
docs/editions/    one HTML file per edition, named YYYY-MM-DD-{morning|evening}.html
design/           Botanical Editorial design references + handoff mockups
```
