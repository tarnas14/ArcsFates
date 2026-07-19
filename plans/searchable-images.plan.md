# Execution plan: make card‑image text searchable

Status: **proposal — nothing implemented yet.** This document is the plan; the only
change made to the repo so far is adding this file.

---

## 1. Goal

Almost all card content on the site is baked into images (e.g.
`userGuide/docs/Base/1/b/piece_0_2.jpg` is the "Sprinter Drives" Lore card).
mkdocs' search cannot see any of that text, so a reader searching for **"lore"**,
**"Sprinter Drives"**, a phrase from a card's rules text, or a corner marker like
**"L"** / **"03"** gets nothing back.

We want that text to be findable through the existing search box, **without
changing how the pages look** (the card galleries stay as image grids).

Concretely, for each card we want these to be searchable:

| Field on the card | Example (Sprinter Drives) |
|---|---|
| Name | `Sprinter Drives` |
| Type (bottom band) | `Lore` |
| Rules/flavour text | `When you move fresh Loyal ships, you may move any of them one more time. …` |
| Bottom‑left marker | `L` |
| Bottom‑right marker | `03` |

---

## 2. How search works in mkdocs (verified against this repo)

The site uses `mkdocs-material`, whose search is the built‑in mkdocs `search`
plugin (now listed explicitly in `userGuide/mkdocs.yml`). At **build time** it
walks the rendered HTML of every page and writes `site/search/search_index.json`
— a list of `{location, title, text}` records. In the browser, `lunr.js` searches
that JSON client‑side. **Search only ever sees text that ended up in the built
HTML.**

I confirmed three things by building this site in the dev container and
inspecting the generated `search_index.json`:

1. **`alt` text is NOT indexed.** The cards already carry the card name as `alt`
   (`[![Sprinter Drives](1/b/piece_0_2.jpg)…]`), but a name that appears *only*
   as `alt` — e.g. `Tool-Priests` — returns **0 matches** in the index. The
   card‑gallery pages index with an empty `text: ""`. So today none of the card
   text is searchable.
2. **Visually‑hidden text IS indexed.** Text inside a `display:none` (or
   off‑screen) element still appears in the built HTML, so it lands in
   `search_index.json`. CSS is never evaluated at build time — hiding is purely a
   browser concern. A hidden probe string was indexed.
3. **A build‑time hook can inject that text.** A mkdocs *hook*
   (`on_page_markdown` / `on_page_content`) that appends hidden text to a page is
   picked up by the search plugin, because the plugin reads the page content
   *after* hooks run. An injected probe string was indexed.

**Conclusion / mechanism we'll use:** attach a hidden, screen‑reader‑friendly
text block to each card image containing its name/type/text/markers. It is
invisible on the page but present in the HTML, so search finds it. As a bonus,
`mkdocs-material`'s search dropdown shows the matched snippet, so a search for a
phrase will surface the card's name + rules text in the results preview — the
reader recognises the card before even clicking.

We do **not** need to touch the ~30 markdown gallery files. A hook injects the
text at build time from a single committed data file.

### Why a hook + committed JSON (not editing the markdown)

- **Markdown stays clean.** The gallery files keep their `[![alt](img)]…` lines.
- **One reviewable source of truth.** All transcriptions live in one JSON file
  you can eyeball and hand‑correct.
- **CI needs nothing new.** The GitHub Action just runs `mkdocs build`; the hook
  reads the committed JSON. No API key in CI, no new dependencies (the hook is
  pure stdlib + already‑installed mkdocs).
- **Extraction is a rare, offline step.** You only re‑run it when cards change.

---

## 3. Pipeline overview

```
   (offline, run by a human, needs API key)          (every build, incl. CI)
┌───────────────────────────────────────┐        ┌──────────────────────────────┐
│ tools/extract-card-metadata.sh         │        │ mkdocs build                 │
│  • walks docs/**/*.jpg                  │        │  • hooks.py on_page_markdown │
│  • one Anthropic vision call per card   │  ───▶  │    looks up each <img> in    │
│  • writes userGuide/card-metadata.json  │ commit │    card-metadata.json        │
│    { "Base/1/b/piece_0_2.jpg": {name…}} │        │  • appends hidden caption    │
└───────────────────────────────────────┘        │  • search plugin indexes it  │
                                                   └──────────────────────────────┘
```

Three artefacts get committed: `userGuide/hooks.py`, `userGuide/card-metadata.json`,
and a small CSS rule. `mkdocs.yml` gains a `hooks:` entry.

---

## Step 1 — Extract card metadata from the images (reusable script)

Per repo convention, the API call is encapsulated in a shell script that **you**
run; Claude Code should not run it (it needs your `ANTHROPIC_API_KEY`). It reads
the key from the environment — **never** commit the key or put it in a `.env`
that gets read.

The script is **idempotent / resumable**: it skips any image already present in
the manifest, so you can Ctrl‑C and re‑run freely.

### Model choice (grounded in the current API)

Cards have stylised display fonts and small corner markers, so a vision model
reads them far more reliably than classic OCR. Current model IDs and pricing
(per 1M tokens):

| Model | ID | Input | Output | Notes for this task |
|---|---|---|---|---|
| Haiku 4.5 | `claude-haiku-4-5` | $1.00 | $5.00 | Cheapest; fine for clean body text, but the tiny `L`/`03` corner markers are the weak spot. |
| **Sonnet 5** (recommended) | `claude-sonnet-5` | $3.00 (**$2.00 intro thru 2026‑08‑31**) | $15.00 ($10 intro) | High‑resolution vision (reads the small corner markers well) + reliable structured JSON. Intro pricing is active now. |
| Opus 4.8 | `claude-opus-4-8` | $5.00 | $25.00 | Overkill for transcription; reserve for re‑running a handful of the hardest cards. |

All three support **image input** and **structured outputs** (forced JSON schema).

**Rough cost for the whole set (~568 images):** on Sonnet 5 at intro pricing,
order of **$2–3 total**; roughly half that on Haiku 4.5. The **Batch API** (see
Appendix A) halves it again for bulk re‑runs. Cost is not the constraint here —
accuracy is, because this is a rules reference.

> Recommendation: **Sonnet 5** as the default, spot‑check the output (Step 5),
> and only reach for Opus on specific cards that come back wrong.

### `tools/extract-card-metadata.sh`

```sh
#!/usr/bin/env bash
set -euo pipefail

# Transcribe Arcs card images into userGuide/card-metadata.json via the Anthropic
# vision API. Run this yourself — it needs ANTHROPIC_API_KEY and makes ~one API
# call per image. Idempotent: images already in the manifest are skipped, so it
# is safe to interrupt and re-run.
#
# Usage:
#   export ANTHROPIC_API_KEY=sk-ant-...
#   tools/extract-card-metadata.sh userGuide/docs/Base userGuide/docs/Campaign
#
# Deps: bash, curl, jq, base64

: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY in your shell (do not commit it)}"
MODEL="${MODEL:-claude-sonnet-5}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="$ROOT/userGuide/docs"
MANIFEST="$ROOT/userGuide/card-metadata.json"
[ -f "$MANIFEST" ] || echo '{}' > "$MANIFEST"

read -r -d '' PROMPT <<'EOF' || true
You are transcribing a single card from the board game Arcs.
Return these fields exactly as printed on the card:
- name: the card's title.
- type: the label centred along the bottom band (e.g. LORE, COURT, LEADER).
- description: the full rules and flavour text in the card body, verbatim,
  including any parenthetical clarifications. Preserve wording; join lines with spaces.
- bottom_left: the small marker in the bottom-left corner (e.g. "L"), or null.
- bottom_right: the small marker/number in the bottom-right corner (e.g. "03"), or null.
Transcribe text exactly. Use null for any field not present on the card.
EOF

SCHEMA='{
  "type":"object",
  "properties":{
    "name":{"type":"string"},
    "type":{"type":"string"},
    "description":{"type":"string"},
    "bottom_left":{"type":["string","null"]},
    "bottom_right":{"type":["string","null"]}
  },
  "required":["name","type","description","bottom_left","bottom_right"],
  "additionalProperties":false
}'

find "$@" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | sort | while read -r img; do
  key="${img#"$DOCS"/}"                      # docs-relative path, e.g. Base/1/b/piece_0_2.jpg

  if [ "$(jq --arg k "$key" 'has($k)' "$MANIFEST")" = "true" ]; then
    echo "skip  $key"; continue
  fi

  case "$img" in *.png) media="image/png" ;; *) media="image/jpeg" ;; esac

  b64="$(mktemp)"; req="$(mktemp)"; resp="$(mktemp)"
  base64 < "$img" | tr -d '\n' > "$b64"      # single-line base64 (portable across macOS/Linux)

  jq -n --arg model "$MODEL" --arg media "$media" --rawfile data "$b64" \
        --arg prompt "$PROMPT" --argjson schema "$SCHEMA" '{
    model: $model, max_tokens: 1024,
    messages: [ { role:"user", content: [
      { type:"image", source:{ type:"base64", media_type:$media, data:$data } },
      { type:"text", text:$prompt }
    ] } ],
    output_config: { format: { type:"json_schema", schema:$schema } }
  }' > "$req"

  http=$(curl -sS -o "$resp" -w '%{http_code}' https://api.anthropic.com/v1/messages \
    -H "content-type: application/json" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    --data @"$req")

  if [ "$http" != "200" ]; then
    echo "FAIL  $key (HTTP $http)"; cat "$resp" >&2; rm -f "$b64" "$req" "$resp"; continue
  fi

  # With output_config.format the first text block is guaranteed valid JSON.
  card=$(jq -r '.content[] | select(.type=="text") | .text' "$resp")
  if ! printf '%s' "$card" | jq -e . >/dev/null 2>&1; then
    echo "SKIP  $key (non-JSON response; possible refusal)"; rm -f "$b64" "$req" "$resp"; continue
  fi

  tmp="$(mktemp)"
  jq --arg k "$key" --argjson v "$card" '.[$k] = $v' "$MANIFEST" > "$tmp" && mv "$tmp" "$MANIFEST"
  echo "ok    $key -> $(printf '%s' "$card" | jq -r '.name')"

  rm -f "$b64" "$req" "$resp"
  sleep 0.3                                    # gentle pacing; well under rate limits
done

echo "done -> $MANIFEST"
```

Notes:
- **Which images are "cards"?** Pass the card directories as arguments
  (`userGuide/docs/Base userGuide/docs/Campaign`). Non‑card art (board setup,
  `back.jpg`, etc.) can be left out, or transcribed and ignored — the hook only
  injects for images that resolve to a manifest entry.
- **`card-metadata.json` is hand‑editable.** If a transcription is wrong, fix
  the JSON directly and rebuild — no need to re‑call the API.
- Resulting shape:
  ```json
  {
    "Base/1/b/piece_0_2.jpg": {
      "name": "Sprinter Drives",
      "type": "Lore",
      "description": "When you move fresh Loyal ships, you may move any of them one more time. (Damaged ships can move with them once, but won't move one more time. Resolve this after all Catapult moves.)",
      "bottom_left": "L",
      "bottom_right": "03"
    }
  }
  ```

---

## Step 2 — Inject the hidden captions at build time (`userGuide/hooks.py`)

The hook runs during every `mkdocs build`. For each page it finds the image
references in the source markdown, resolves each to a docs‑relative path (the
same keys the script wrote), looks them up in the manifest, and appends **one
hidden block per page** holding the captions for every card on that page.

Working in `on_page_markdown` lets us match the author‑written paths
(`1/b/piece_0_2.jpg`) directly, avoiding the directory‑URL rewriting that happens
later in the rendered HTML. Search indexes page‑level text, so a single block at
the end of the page is enough to make every card on it findable.

```python
import html
import json
import os
import posixpath
import re

_MANIFEST = None
# Matches the inner image of the lightbox link:  ![alt](1/b/piece_0_2.jpg){ width=... }
_IMG = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?")


def _manifest(config):
    global _MANIFEST
    if _MANIFEST is None:
        path = os.path.join(os.path.dirname(config["config_file_path"]), "card-metadata.json")
        with open(path, encoding="utf-8") as fh:
            _MANIFEST = json.load(fh)
    return _MANIFEST


def on_page_markdown(markdown, page, config, files):
    manifest = _manifest(config)
    page_dir = posixpath.dirname(page.file.src_uri)          # e.g. "Base"

    captions = []
    for src in _IMG.findall(markdown):
        docs_path = posixpath.normpath(posixpath.join(page_dir, src))  # e.g. "Base/1/b/piece_0_2.jpg"
        meta = manifest.get(docs_path)
        if not meta:
            continue
        parts = [meta.get("name"), meta.get("type"),
                 meta.get("bottom_left"), meta.get("bottom_right"),
                 meta.get("description")]
        captions.append(" — ".join(p for p in parts if p))

    if not captions:
        return markdown

    block = ['\n\n<div class="card-search-index" markdown="0">']
    block += [f"<p>{html.escape(c)}</p>" for c in captions]
    block += ["</div>\n"]
    return markdown + "\n".join(block)
```

Register it in `userGuide/mkdocs.yml` (top level, alongside `plugins:`):

```yaml
hooks:
  - hooks.py
```

(`hooks.py` and `card-metadata.json` live next to `mkdocs.yml` in `userGuide/`,
**not** under `docs/` — anything in `docs/` gets copied into the published site.)

---

## Step 3 — Hide the caption visually (CSS)

Append to `userGuide/docs/css/extra.css` (already loaded via `extra_css`). This is
the standard "visually hidden" pattern: invisible on screen, still in the DOM (so
it's indexed) **and** announced by screen readers (an accessibility bonus).

```css
.card-search-index {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

(`display: none` would also be indexed, but the pattern above keeps the text
available to assistive tech.)

---

## Step 4 — Wire‑up summary (what gets committed)

| File | Change |
|---|---|
| `tools/extract-card-metadata.sh` | new — the extraction script (run manually) |
| `userGuide/card-metadata.json` | new — generated, then committed |
| `userGuide/hooks.py` | new — build‑time injector |
| `userGuide/mkdocs.yml` | add `hooks:` block |
| `userGuide/docs/css/extra.css` | add `.card-search-index` rule |

No change to `.github/workflows/main.yml` — CI already runs `mkdocs build`, which
picks up the hook and the committed manifest. No new Python packages.

---

## Step 5 — Verify

Using the docker dev setup already in the repo:

```sh
# 1. Build and confirm a card name that only exists on an image is now indexed:
docker run --rm -v "$PWD/userGuide:/userGuide" -v /tmp/probe:/probe \
  arcsfates-mkdocs mkdocs build -d /probe
grep -c "Tool-Priests" /tmp/probe/search/search_index.json      # expect > 0 (was 0 before)
grep -c "Sprinter Drives" /tmp/probe/search/search_index.json   # expect the card, not just the FAQ

# 2. Serve and search interactively:
docker compose up
#   open http://localhost:3335, search "lore", "sprinter", a rules phrase, "03"
```

**Human QA (important — this is a rules reference):** spot‑check a sample of the
transcriptions in `card-metadata.json` against the images, especially any card
referenced in a FAQ/errata section. Correct mistakes directly in the JSON and
rebuild.

---

## Alternatives considered

- **Rely on `alt` text** — rejected: proven not indexed by mkdocs search.
- **Classic OCR (Tesseract)** — free/offline, but the stylised title fonts and
  decorative layout need per‑region cropping and heavy cleanup, and the tiny
  corner markers are unreliable. For ~568 cards at ~$2–3, the vision model is far
  more accurate for the money. Keep Tesseract in mind only as a zero‑API‑cost
  fallback.
- **Import an existing card dataset** — worth a quick look (BGG / community
  spreadsheets). If a clean structured Arcs card list exists, load it into
  `card-metadata.json` and skip Step 1 entirely. Treat as an optional shortcut to
  investigate first.
- **Pre‑generate captions into the markdown files** — rejected: huge diffs across
  ~30 files, duplicated text, and every card change re‑touches markdown. The hook
  keeps source clean and metadata centralised.
- **Visible captions under each card** — rejected: would bloat the gallery pages
  (dozens of cards per page). Hidden text preserves the current look.

## Open questions / decisions to confirm

1. **Model:** default to `claude-sonnet-5`? (Recommended; intro pricing active
   through 2026‑08‑31.)
2. **Scope of images:** confirm the card directories to transcribe
   (`Base`, `Campaign`, and which subfolders); exclude board/setup art?
3. **Deep‑linking:** v1 lands search hits on the *page* (e.g. the Lore page) and
   shows the matching card in the results preview. Per‑card jump‑to‑anchor would
   require a heading per card (clutters the page + table of contents) and is out
   of scope unless wanted.

---

## Appendix A — Batch API (optional, for cheap bulk re‑runs)

For a full re‑transcription, the **Message Batches API** runs the same requests
asynchronously at **50% cost** (most batches finish within an hour):

1. Build a JSONL where each line is `{custom_id: "<docs-relative path>", params: {…same body as above…}}`.
2. `POST /v1/messages/batches`; poll `processing_status` until `ended`.
3. Stream results; each carries its `custom_id` — key the manifest by it
   (results arrive **unordered**, so never rely on position).

The per‑image script in Step 1 is simpler and resumable, which is why it's the
primary path; the Batch API is the optimisation for large re‑runs.
