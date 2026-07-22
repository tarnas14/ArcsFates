This is a knowledge repository for [Arcs](https://boardgamegeek.com/boardgame/359871/arcs) and [Arcs: The Bligthed Reach Expansion](https://boardgamegeek.com/boardgameexpansion/363757/arcs-the-blighted-reach-expansion)

## Local development

Requires only Docker (no local Python). Builds and serves the `userGuide` docs with live reload:

```sh
docker compose up --build
```

Open http://localhost:3335 — edits to files under `userGuide/` reload the browser automatically.

Use a different host port with `MKDOCS_PORT`:

```sh
MKDOCS_PORT=4000 docker compose up
```

## Searchable card text

Card rules text is printed on the card images, so the site's search cannot read it directly.
To make cards findable, every card's text lives in `userGuide/card-metadata.json`, keyed by the image's path relative to `userGuide/docs/` (for example `Campaign/1/piece_3_3.jpg`).

Each manifest entry holds:

- `name` — the card title; it also becomes the card page's slug and URL.
- `type` — the card kind (e.g. `Guild`, `Vox`, `Lore`, `Setup`, `Objective`, `Fate`).
- `bottom_left` / `bottom_right` — the small markers printed in the card's corners (such as the fate marker `F1` and the catalog number `02`); `null` when the card has none.
- `description` — the card's body text; this is what search matches against. It may span multiple lines.
- `overview` — present and `true` only on a fate's own card (the big character card). Overview cards are rendered inline on the fate page instead of getting a standalone page.

Two build-time pieces turn the manifest into searchable content; nothing is written under `docs/`, it is all generated on each build:

- `userGuide/gen_cards.py` is a MkDocs `gen-files` script that emits one standalone page per non-overview card under `cards/<namespace>/<slug>.md`. Search indexes each of those pages, and mkdocs-material highlights the matched text on them. The namespace keeps same-named cards apart: base cards under `base/`, campaign court/misc under `campaign/`, and each campaign fate under `campaign/<N>/`. Every card page also links back to the gallery page that displays it.
- `userGuide/hooks.py` wires the galleries to that text. It adds a Lightbox caption (ending in an "Open card page →" link) to each gallery thumbnail, and renders the fate overview text inline beneath the fate card.

The generated card pages are hidden from the navigation (`not_in_nav: /cards/**` in `userGuide/mkdocs.yml`); they exist only to be reached through search and the gallery captions.

To change what a card says, edit its entry in `userGuide/card-metadata.json` and rebuild.
For bulk edits with the card art shown next to the text, use the review workflow documented in [`tools/README.md`](tools/README.md).

