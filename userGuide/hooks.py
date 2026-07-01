"""mkdocs build hook: make text baked into card images searchable.

Card metadata lives in ``card-metadata.json`` (next to ``mkdocs.yml``), keyed by
the image's path relative to ``docs/``. For each rendered page we find the
paragraph(s) holding card images and, immediately BEFORE each such ``<p>``,
insert a hidden section per card: an ``<h3>`` titled with the card name plus a
block holding the transcribed text.

Both are hidden (see ``.card-search-index`` in ``css/extra.css``) but present in
the built HTML, so:

* the mkdocs ``search`` plugin indexes each card as its OWN result, titled with
  the card name and anchored;
* the anchor sits right at the gallery, so following a search result scrolls to
  the card gallery rather than to the bottom of the page; and
* the raw ``<h3>`` is invisible to the Table of Contents extension (which only
  sees Markdown-syntax headings), so it does not clutter the on-page TOC/nav.

The metadata schema is intentionally open: different card types (lore, leader,
court, fate, edict, setup, ...) carry different fields. We index every string leaf
value we find, so adding a new card type only needs JSON, not a hook change.
"""

import html
import json
import os
import posixpath
import re
from urllib.parse import unquote

_MANIFEST = {}
_PARAGRAPH = re.compile(r"<p\b[^>]*>.*?</p>", re.S)
_IMG_SRC = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"')


def _manifest_path(config):
    return os.path.join(os.path.dirname(config["config_file_path"]), "card-metadata.json")


def on_pre_build(config, **kwargs):
    # Reload every build so `mkdocs serve` picks up edits to card-metadata.json.
    global _MANIFEST
    try:
        with open(_manifest_path(config), encoding="utf-8") as fh:
            _MANIFEST = json.load(fh)
    except FileNotFoundError:
        _MANIFEST = {}


def on_serve(server, config, builder, **kwargs):
    # card-metadata.json lives outside docs/, so mkdocs doesn't watch it by
    # default — register it so edits trigger a live rebuild.
    server.watch(_manifest_path(config))
    return server


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "card"


def _text_values(value):
    """Yield every non-empty string/number leaf of a metadata value, in order."""
    if isinstance(value, bool):
        return
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            yield stripped
    elif isinstance(value, (int, float)):
        yield str(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _text_values(item)


def _card_block(docs_path, meta):
    values = list(_text_values(meta))
    if not values:
        return None
    name = meta.get("name") or values[0]
    anchor = "card-" + _slug(posixpath.splitext(docs_path)[0])  # unique per image
    return (
        f'<h3 id="{anchor}" class="card-search-index">{html.escape(name)}</h3>'
        f'<div class="card-search-index">{html.escape(" — ".join(values))}</div>'
    )


def on_page_content(html_content, page, config, files, **kwargs):
    if not _MANIFEST:
        return html_content

    url_dir = posixpath.dirname(page.file.url)  # handles use_directory_urls on/off
    seen = set()

    def prepend_cards(match):
        paragraph = match.group(0)
        blocks = []
        for src in _IMG_SRC.findall(paragraph):
            docs_path = posixpath.normpath(posixpath.join(url_dir, unquote(src)))
            if docs_path in seen:
                continue
            meta = _MANIFEST.get(docs_path)
            if not meta:
                continue
            seen.add(docs_path)
            block = _card_block(docs_path, meta)
            if block:
                blocks.append(block)
        if not blocks:
            return paragraph
        return "".join(blocks) + paragraph

    return _PARAGRAPH.sub(prepend_cards, html_content)
