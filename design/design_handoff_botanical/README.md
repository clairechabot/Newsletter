# Handoff: The Curated Canopy — "Botanical Editorial" Redesign

## Overview
This package redesigns the visual output of **The Curated Canopy** newsletter (the
`clairechabot/Newsletter` repo). It replaces the look of both deliverables:

1. **The email** (`renderer.py`) — a short, elegant "cover" sent via SMTP.
2. **The full web edition** (`webpage.py`) — the interactive GitHub Pages page
   (`docs/index.html`) the email links out to.

The new direction is **"Botanical Editorial"**: warm stone paper, deep forest-green
ink, moss + clay accents, a literary serif for headlines and a clean grotesque for
UI. It removes all emojis (including the 🌱 in "From the Garden"), the old left-border
accent cards, and the "Energy Spectrum" mood bar. Fern's curator voice and **all six**
content sections are kept.

> **Reconciled against the live repo (important).** These files were diffed against the
> current `clairechabot/Newsletter@main`. The deployed version renders SIX sections
> (not four): the earlier redesign draft had dropped **From the Garden** and **One Good
> Read** — both are restored here, emoji-free. The email is also rebuilt to be
> Gmail-safe (see the CRITICAL section below); the previous email used CSS that Gmail
> strips, which is why it rendered plain.

## About the Design Files
This bundle is **not** generic HTML to drop on a server. The two `.py` files
(`renderer.py`, `webpage.py`) are **finished, drop-in replacements** for the files
of the same name already in the repo — they keep the existing data pipeline and
SMTP plumbing and only change the generated markup/styling. The two
`reference_*.html` files are **static visual references** showing the exact intended
output (rendered with sample data) so you can verify your result pixel-for-pixel.

**The task:** integrate the two rebuilt Python files into the repo so the newsletter
renders in this design, without breaking the existing fetch → curate → render → send
pipeline.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and layout are final. Match the
`reference_*.html` files exactly.

---

## How to integrate (the actual task)

The rebuilt files are designed to need **no other code changes**. Recommended steps:

1. **Replace `renderer.py`** at the repo root with the one in this bundle.
2. **Replace `webpage.py`** at the repo root with the one in this bundle.
3. **Set the launch date** (one line, in BOTH files):
   ```python
   CANOPY_LAUNCH = datetime.date(2025, 1, 1)   # <-- set to the date of edition No. 1
   ```
   The masthead "No. NNNN" issue number is computed from this date assuming a
   twice-daily cadence. Pick the true date of the first edition (or the repo's first
   commit date) so the number is accurate.
4. **Do not touch** the rest of the pipeline: `fetcher.py`/`curator.py`,
   `curated_data.json`, the GitHub Actions workflow, or the SMTP env vars. The
   rebuilt files read the same `curated_data.json` shape and write to the same
   outputs (`newsletter.html` + `docs/index.html`).
5. Run a dry render to confirm:
   ```bash
   ALLOW_NO_EMAIL=1 python renderer.py      # writes newsletter.html and docs/index.html, skips send
   python webpage.py                         # rebuilds docs/index.html on its own
   ```
   Open `newsletter.html` and `docs/index.html` and compare against the reference files.

### Data contract (unchanged — for your reference)
The rebuilt files consume exactly the keys the current code already produces:
- `curated["themes"][n]["items"]` → videos, each with `title`, `why_watch` /
  `description`, `video_id`, `channel_title`, `is_wildcard`.
- `curated["morning_soundtrack"]` → music: `title`, `vibe_check`/`snippet`,
  `embed_url`/`url`, `cover_url`, `genre`, `source_name`.
- `curated["global_silver_linings"]` → good news: `title`, `reason`, `url`,
  `cover_url`, `source_name`.
- `curated["discovery_articles"]` → archives: `title`, `ferns_note`/`snippet`,
  `url`, `cover_url`, `source_name`, `category`.
- `curated["featured_read"]` → One Good Read: `title`, `blurb`/`snippet`, `url`,
  `cover_url`, `source_name`.
- `curated["garden_note"]` → From the Garden: `note`, `in_season` (list),
  `sky_tonight`, `moon_label`.
- `curated["fern_data"]["greeting"]`, `["top_pick_title"]`.
- `curated["is_am_email"]`, `curated["fetched_at"]`.

Note: `morning_soundtrack` items are music *articles* (no `genre`/`cover_url` in
practice) and `featured_read`/`garden_note` carry no images — the renderers handle
all of this gracefully (placeholder tiles, hidden genre filter, omitted empty
sections).

---

## CRITICAL: why the email is built the way it is

The **email must not use modern CSS** — Gmail (the primary client) silently strips
it. The previous version looked broken in Gmail for exactly this reason. The rebuilt
`renderer.py` therefore uses **table-based layout, fully inline styles, hardcoded hex
colors, explicit image dimensions, and web-safe font fallbacks**. When editing the
email, you MUST preserve these rules:

- **No CSS custom properties** (`var(--x)`). Gmail deletes them → all colors fall
  back to defaults. Use hardcoded hex everywhere.
- **No web fonts as a requirement.** A `<link>` to Newsreader/Hanken is included as
  progressive enhancement (Apple Mail/iOS honor it), but every element declares a
  full fallback stack inline: serif → `Georgia`, sans → `Helvetica, Arial`. Gmail
  renders Georgia/Arial — this is expected and looks correct.
- **No flexbox/grid.** Use nested `<table role="presentation">` for layout.
- **No `aspect-ratio`.** Images use explicit `width`/`height`; the hero `<img>` uses
  `width="536" style="height:auto"`.
- Keep the total HTML well under ~100KB so Gmail doesn't clip it.

The **web edition** (`webpage.py`) is viewed in a real browser, so it uses normal
modern CSS (custom properties, grid, sticky positioning, JS interactivity). Do **not**
apply the email's table constraints to the web edition.

---

## Design Tokens (both deliverables)

| Token        | Hex       | Use                                        |
|--------------|-----------|--------------------------------------------|
| paper        | `#F4EEE2` | email/page background (warm stone)         |
| paper-deep   | `#E9E1D1` | outer margin behind the 600px email frame  |
| surface      | `#FBF7EE` | Fern's note panel / cards                  |
| ink          | `#20271F` | darkest text                               |
| ink-soft     | `#4A4A3E` | body text                                  |
| ink-mute     | `#7C7565` | metadata / captions                        |
| forest       | `#2C3A2B` | headlines, wordmark (primary)              |
| moss         | `#6E7B4B` | index numerals, monogram border            |
| moss-deep    | `#55603A` | small labels                               |
| clay         | `#A85A36` | CTA button, link/accent                    |
| clay-deep    | `#8E4A2C` | eyebrow labels, link text                  |
| line         | `#D9CFBC` | hairline rules                             |
| line-soft    | `#E5DCCB` | soft dividers                              |

**Typography**
- Headlines & Fern's voice: **Newsreader** (serif), weight 500, tight letter-spacing
  (`-0.3px`→`-0.5px` on large sizes). Email fallback: **Georgia**.
- Labels, metadata, body, UI: **Hanken Grotesk** (sans), weights 400–700; eyebrows
  are 11px / 600 / `letter-spacing:3px` / uppercase. Email fallback: **Helvetica, Arial**.
- Eyebrow accent color is `clay-deep`; section index numerals are `moss`.

**Other**
- Card / image radius: `12px`. Pills (CTA, chips, badges): `100px`.
- No emojis anywhere — use typographic marks (`·` `→`) and the placeholder tiles.

---

## Screens / Views

### 1. The Email (`renderer.py` → `newsletter.html`)
A 600px-wide centered "cover", top to bottom:
- **Masthead** (centered): clay eyebrow `MORNING/EVENING EDITION · No. NNNN · <date>`,
  the serif wordmark "The Curated Canopy" (46px), an italic serif tagline, and a
  muted uppercase meta line (`Gathered at dawn · N tracks · N films · N stories & finds`).
- **Fern's note**: surface-colored panel bordered top & bottom; a circular "F"
  monogram (moss border) beside the eyebrow "A note from Fern" and her greeting in
  serif, signed *"Yours, Fern"* in italic forest. **All em/en dashes are stripped
  from Fern's prose at render time** (see Behavior).
- **From the Garden** (`_render_garden`): a compact almanac on the same surface tint —
  eyebrow "From the Garden" (NO emoji), Fern's 1–2 sentence seasonal note in serif,
  and an uppercase meta line joining `moon_label · in_season items · sky_tonight`.
  Omitted entirely if `garden_note` has no `note`.
- **Today's opening (hero)**: eyebrow with a trailing hairline rule, then the top
  video — its YouTube thumbnail (`hqdefault`) with a circular play affordance, a moss
  kicker (`Watch · <channel>`), a 27px serif headline, and a one-line description.
  If a video has no `video_id`, a solid `#46553E` block stands in.
- **In this edition**: eyebrow, then numbered rows (01…) — each a serif section name,
  a muted one-line teaser of its top items, and a moss count. Order:
  `The Morning Soundtrack` (Tracks), `Worth Watching` (Films), `Global Silver Linings`
  (Stories), `From the Archives` (Finds), and finally **One Good Read** (the featured
  essay — shows the essay title + its source). Sections with no items are skipped and
  numbering re-flows; the last row drops its divider.
- **CTA**: centered clay pill "Open the full edition" + uppercase subtitle. Links to
  `EDITION_URL`.
- **Footer**: serif "The Curated Canopy", curation note, Preferences · Unsubscribe.

### 2. The Web Edition (`webpage.py` → `docs/index.html`)
A full-width responsive magazine (max 1120px content), top to bottom:
- **Masthead**: same eyebrow/issue line, a huge serif "The Curated Canopy"
  (`clamp(46px,8vw,84px)`), italic tagline, meta line.
- **Fern's note**: centered ~720px, circular monogram + greeting, signed "Yours, Fern".
- **From the Garden** almanac: eyebrow (NO emoji), Fern's seasonal note, the `in_season`
  items as static pill chips, and a `moon_label · sky_tonight` meta line. Hidden if no
  garden note.
- **Hero feature**: a two-column band (image | text) with a top & bottom hairline;
  collapses to one column under 820px. Uses the top video's YouTube thumbnail.
- **One Good Read**: a second two-column band for the featured essay (clay-toned
  placeholder when no cover), eyebrow `One Good Read · <source>`, serif title, blurb,
  and a "Read the essay →" link. Hidden if no featured read.
- **Sticky tab bar**: condenses on scroll (shows a small "Canopy" wordmark when
  stuck). Tabs: `01 Soundtrack`, `02 Watch`, `03 Good News`, `04 Archives`. Active
  tab has a clay underline; clicking swaps the panel and scrolls to the bar.
- **Four panels** (one visible at a time, fade-in):
  - **Soundtrack**: an optional genre filter (clay-fill active chip) above a grid of
    square cards. NOTE: the real `morning_soundtrack` items are music *articles* and
    carry no `genre` or `cover_url`, so the genre filter auto-hides and cards use the
    toned placeholder tile — this is expected, not a bug.
  - **Watch**: 16:9 video cards with play affordance, channel, optional "Wildcard" tag.
  - **Good News**: 3:2 feature cards.
  - **Archives**: 3:2 cards with a category badge (`Archives`/`Science`/`Museum`…).
  - Each card: image (real thumbnail/`cover_url` when present, else toned placeholder),
    an uppercase meta line, a serif title, a short note, and a clay "Listen/Watch/Read →".
- **Footer**: serif wordmark, "Gathered twice daily by Fern", links.

> The web edition is browser-rendered, so it uses normal modern CSS (custom
> properties, grid, sticky, JS). The repo's existing `webpage.py` already rendered
> correctly — the only change here is **removing the 🌱 emoji** from "From the Garden".
> Do NOT apply the email's table/inline-style constraints to the web edition.

---

## Interactions & Behavior (web edition)
- **Tabs**: click → set `.active` on the tab + matching `.panel`; if scrolled past the
  tab bar, smooth-scroll back up to it. Panels fade in (`@keyframes fade`, disabled
  under `prefers-reduced-motion`).
- **Genre filter** (music only): `All` + one chip per distinct `genre`; clicking
  filters the music grid. Hidden if no genres present.
- **Sticky condense**: on scroll past the tab bar's offset, add `.stuck` (reveals the
  small wordmark).
- **Images**: `cover()` helper renders a real `<img>` when a URL/thumbnail exists,
  else a toned placeholder `<div>` (`.t0`–`.t3`) with a small label. Card hover
  enlarges the play circle and nudges the "→".
- **Links**: every card/row links out (`target="_blank"`), URL-sanitized to
  http/https/mailto.

## Behavior shared by both (already implemented)
- **Em-dash stripping**: `_dedash()` converts `—`/`–` in Fern's generated prose to
  commas (number ranges keep a hyphen) so her voice doesn't read as machine-made.
  Applied to the greeting, video notes, music/news/discovery notes.
- **Sign-off**: any trailing "Fern"/"— Fern" the model added is stripped and replaced
  with a consistent italic *"Yours, Fern"*.
- **Issue number**: `_edition_no(dt, is_am)` = `days_since_launch * 2 + (0 if AM else 1) + 1`.
- **Graceful empties**: empty sections are omitted; missing images fall back to tiles.
- **(Optional) source-side fix**: consider adding one line to `curator.py`'s prompt
  instructing the model to avoid em-dashes, so the `_dedash` net is rarely needed.

## State Management
- Email: none (static HTML string built server-side from `curated_data.json`).
- Web edition: all state is client-side and ephemeral — `activeGenre` (music filter)
  and which tab/panel is active. Data is embedded as JSON in a `<script
  type="application/json" id="data">` block and read on load. No persistence, no
  fetching at runtime.

## Assets
- **Video imagery**: YouTube thumbnails via `https://img.youtube.com/vi/<id>/hqdefault.jpg`.
- **Album/feature imagery**: whatever `cover_url` the pipeline supplies; absent → a
  toned CSS placeholder tile (no external asset needed).
- **Fonts**: Google Fonts (Newsreader, Hanken Grotesk) via `<link>` on the web
  edition; email progressively enhances and otherwise uses Georgia/Helvetica.
- **Logo (optional)**: if you set `FERN_LOGO_URL`, the email shows it centered above
  the eyebrow at 96px wide. No logo asset is required.

## Files in this bundle
- `renderer.py` — drop-in replacement for the repo's email renderer + SMTP sender.
- `webpage.py` — drop-in replacement for the repo's GitHub Pages edition builder.
- `reference_email.html` — static visual reference for the email (sample data).
- `reference_web_edition.html` — static visual reference for the web edition (sample data).

## Environment variables (unchanged from the current repo)
`EMAIL_USER`/`SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`/`NEWSLETTER_RECIPIENTS`,
`SMTP_HOST`/`SMTP_SERVER`, `SMTP_PORT`, `EDITION_URL`, optional `FERN_LOGO_URL`,
optional `ALLOW_NO_EMAIL=1` (preview render without sending).

## From the Garden — location
The "From the Garden" almanac is grounded in **Zürich, Switzerland**:
- Both `renderer.py` and `webpage.py` define `GARDEN_LOCALE` (default `"Zürich"`,
  overridable via the `GARDEN_LOCALE` env var). It's shown in the section eyebrow as
  `From the Garden · Zürich`.
- The seasonal note + night sky are written by `curator.py`'s `_GARDEN_SYSTEM` prompt,
  which already instructs the model to ground everything in a temperate Northern-
  Hemisphere garden in Zurich, fed by the real date, season, and moon phase.
- **Optional source-side polish:** to make the note even more local, you can tighten
  that prompt to reference Zürich specifics (Lake Zürich, the Sihl/Limmat, the Alps on
  the horizon, linden blossom) and confirm the locale line reads
  `Locale: Zürich, Switzerland (Northern Hemisphere, temperate, ~400m)`.
