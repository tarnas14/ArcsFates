# Card text review tools

The searchable text for every card lives in `userGuide/card-metadata.json` (see the "Searchable card text" section of the top-level [`README.md`](../README.md)).
This directory holds the tools for editing that text through a human-review round-trip: you generate a Markdown file that shows each card's art next to its editable text, a person corrects the text, and the corrections are written back into the manifest.

The files under `review/` are the hand-checked source of truth that flows into the manifest.
How the text is first obtained for a review (from a spreadsheet, the card images, or anything else) is out of scope here; each future batch can solve that however it likes, as long as it ends in a review file of the format below.

## Workflow

1. Generate a review file for a set of cards:

   ```sh
   tools/build-review.py <output-name> <path-prefix> [<path-prefix> ...]
   ```

   This writes `review/<output-name>.md` with one block per card whose manifest key starts with any of the prefixes.
   Prefixes are matched against the manifest keys, which are image paths relative to `userGuide/docs/` — for example `Base/1/` for the base lore cards, or `Campaign/0/` for the campaign court cards.
   Overview (fate) cards are skipped, because their text is shown inline on the fate page rather than on a standalone page.

2. A person edits the text inside the review file (see the format below).

3. Preview what would change, then apply it:

   ```sh
   tools/apply-review.py --dry-run             # report changes, write nothing
   tools/apply-review.py                        # apply every review/*.md
   tools/apply-review.py review/base-lore.md    # apply specific files
   ```

   `apply-review.py` writes `name` / `type` / `bottom_left` / `bottom_right` / `description` onto the matching manifest entries.
   It uses only the standard library and is idempotent, so re-running it is safe.

Run both tools from the repository root; neither takes any other configuration.

## Review document format

A review file is Markdown with one block per card.
`build-review.py` produces this shape, and `apply-review.py` parses it back:

````markdown
## Campaign/1/piece_3_3.jpg

![Imperial Authority](../userGuide/docs/Campaign/1/piece_3_3.jpg)

```yaml
name: "Imperial Authority"
type: "Lore"
bottom_left: "F1"
bottom_right: "02"
description: |
  Bury this if you're an Outlaw.
  You may tax any cities you control...
```
````

Each block has three parts:

- A `## <docs-path>` heading whose text is the manifest key — the image path relative to `userGuide/docs/`. It must match an existing key exactly; a heading that names no known card is reported and skipped, never created.
- An image line pointing at that card's art, so a Markdown preview shows the card next to its text. The tool ignores this line.
- A fenced ` ```yaml ` block holding the fields.

Fields inside the yaml block:

- `name` — quoted string. It is also the card page's slug and URL, so a blank or missing `name` is refused to avoid wiping a page URL by accident.
- `type` — quoted string (the card kind).
- `bottom_left` / `bottom_right` — quoted string, or `null` (also `~` or empty) when the corner is blank.
- `description` — the body text, written either as a `|` block scalar (each line indented two spaces; blank lines allowed, and line breaks are preserved) or as a single-line quoted value.

Rules:

- Edit only inside the ` ```yaml ` blocks. Do not change the `## <path>` headings or the image lines.
- Every field is optional. Only the fields present in a block are written; omitted fields leave the manifest entry untouched.
- String values are quoted with `"`; a literal `"` or `\` inside is escaped as `\"` or `\\`. Bare unquoted values are also accepted.
- When `description` uses the `|` block form, it must be the last field in the block, because everything below it up to the closing fence is taken as the description.
- A block whose heading has no following fenced block is reported as malformed and skipped.

## What apply-review reports

- `updated` — entries that changed, each with the list of fields that changed.
- `unchanged` — entries whose values already matched.
- `renames` — a `name` changed. Because the page slug/URL is derived from the name, rebuild the site so that card's page regenerates at its new URL.
- `warnings` — an empty `name` was ignored, or a `description` was cleared.
- `unknown keys (skipped)` — headings that match no manifest entry.
- `malformed blocks (skipped)` — headings with no fenced block.

## Conventions

Inline card icons that have no plain-text equivalent are written as placeholder tags in `description`, e.g. `<timer>`, `<target>`, `<key>` (the circle glyph `◯` is written directly as the character).
On the generated pages these tags render as inline code (so `<timer>` shows literally), pending a later pass that maps them to real glyphs; keep them consistent with the existing review files.

Line composition is preserved: a blank line in a `description` becomes a paragraph break on the page, and a single line break becomes a visible line break.
Compose the text the way it should read on the card.
