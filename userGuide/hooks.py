"""mkdocs build hook: caption card thumbnails and render fate overviews inline.

Card metadata lives in ``card-metadata.json`` (next to ``mkdocs.yml``), keyed by the
image's path relative to ``docs/``. This hook does two things at build time:

* For each gallery thumbnail (``<a ...><img ...></a>``) whose image is in the
  manifest, it adds a ``data-title`` to the wrapping ``<a>``. Lightbox2 renders that
  as the caption under the enlarged card (``sanitizeTitle`` is off, so it may contain
  HTML) and we end it with a link to the card's standalone page (from ``gen_cards.py``).
* For a fate overview (``<figure><img ...></figure>`` whose entry has ``overview:
  true``), it appends a VISIBLE metadata block after the figure, on the fate page —
  the overview has no standalone page (that's its home).

Searchability of the card text comes from those visible pages/blocks, not from the
``data-title`` (an attribute isn't indexed). This hook only wires the galleries and
overviews up to that text.
"""

import html
import json
import os
import posixpath
import re
from urllib.parse import unquote

from mkdocs.utils import get_relative_url

_MANIFEST = {}
_IMG_SRC = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"')
# A gallery thumbnail: <a ...><img ...></a>. Captures the <a> attributes and the
# inner <img> so we can re-emit the anchor with an added data-title.
_ANCHOR_IMG = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<inner>\s*<img\b[^>]*?>\s*)</a>", re.S)
# A fate overview: <figure><img src="...FateN.jpg" ...></figure> (no anchor).
_FIGURE_IMG = re.compile(r'<figure\b[^>]*>\s*<img\b[^>]*?\bsrc="([^"]+)"[^>]*?>\s*</figure>', re.S)


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
    # card-metadata.json lives outside docs/, so mkdocs doesn't watch it by default.
    server.watch(_manifest_path(config))
    return server


def _slug(text):
    # Keep in sync with _slug in gen_cards.py, which names the card pages we link to.
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "card"


# Icon placeholder tags (e.g. <timer>) are shown as code so they don't vanish as
# unknown HTML elements; matches the escaped form produced by html.escape.
_ICON_TAG = re.compile(r"&lt;([a-z][a-z0-9-]*)&gt;")


def _render_description(text):
    # Render description text as HTML, preserving the review file's line composition:
    # blank lines separate paragraphs, single newlines become <br>. Icon placeholder
    # tags like <timer> are wrapped in <code>. Keep in sync with gen_cards.py.
    blocks = []
    for para in re.split(r"\n[ \t]*\n", text.strip("\n")):
        lines = [
            _ICON_TAG.sub(r"<code>&lt;\1&gt;</code>", html.escape(line, quote=False))
            for line in para.split("\n")
        ]
        rendered = "<br>".join(lines)
        if rendered:
            blocks.append(f"<p>{rendered}</p>")
    return "".join(blocks)


def _card_ns(docs_path):
    # Namespace pages so same-named cards in different sections/fates don't collide.
    # Keep in sync with gen_cards.py.
    parts = docs_path.split("/")
    if len(parts) > 1 and parts[0] == "Campaign" and parts[1].isdigit() and 1 <= int(parts[1]) <= 24:
        return "campaign/" + parts[1]
    return parts[0].lower()


def _card_src(docs_path, name):
    return "cards/" + _card_ns(docs_path) + "/" + _slug(name) + ".md"


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


def _card_href(docs_path, name, page, files):
    src = _card_src(docs_path, name)
    found = files.get_file_from_path(src)
    target = found.url if found is not None else posixpath.splitext(src)[0] + ".html"
    return get_relative_url(target, page.file.url)


def _caption_attr(name, values, card_href):
    esc = lambda s: html.escape(s, quote=False)
    rest = list(values)
    if name in rest:
        rest.remove(name)
    parts = [f"<strong>{esc(name)}</strong>"]
    if rest:
        parts.append(esc(" — ".join(rest)))
    parts.append(f'<a class="lb-card-link" href="{card_href}">Open card page →</a>')
    caption = "<br>".join(parts)
    # data-title is decoded twice before it is shown: once when the browser parses
    # the attribute, then again when Lightbox re-injects it via jQuery .html(). This
    # second escaping of & and " (on top of the text escaping above) survives both
    # passes, so real card text containing & or " renders instead of breaking the
    # caption. Do not collapse it into a single escape.
    return caption.replace("&", "&amp;").replace('"', "&quot;")


def _overview_block(meta):
    # A VISIBLE block rendered under the fate overview card; its text is indexed and
    # highlightable in place (the overview has no standalone page).
    esc = lambda s: html.escape(s, quote=False)
    head = f"<strong>{esc(meta.get('name') or 'Fate')}</strong>"
    if meta.get("type"):
        head += f" — {esc(meta['type'])}"
    parts = [f"<p>{head}</p>"]
    if meta.get("description"):
        parts.append(_render_description(meta["description"]))
    return '<div class="fate-overview">' + "".join(parts) + "</div>"


def on_page_content(html_content, page, config, files, **kwargs):
    if not _MANIFEST:
        return html_content

    url_dir = posixpath.dirname(page.file.url)

    def _resolve(src):
        return _MANIFEST.get(posixpath.normpath(posixpath.join(url_dir, unquote(src))))

    def caption_anchor(match):
        attrs = match.group("attrs")
        inner = match.group("inner")
        if "data-title" in attrs:  # respect an author-provided caption
            return match.group(0)
        src_match = _IMG_SRC.search(inner)
        if not src_match:
            return match.group(0)
        docs_path = posixpath.normpath(posixpath.join(url_dir, unquote(src_match.group(1))))
        meta = _MANIFEST.get(docs_path)
        if not meta:
            return match.group(0)
        values = list(_text_values(meta))
        if not values:
            return match.group(0)
        name = meta.get("name") or values[0]
        data_title = _caption_attr(name, values, _card_href(docs_path, name, page, files))
        return f'<a{attrs} data-title="{data_title}">{inner}</a>'

    def render_overview(match):
        meta = _resolve(match.group(1))
        if not meta or not meta.get("overview"):
            return match.group(0)
        return match.group(0) + _overview_block(meta)

    html_content = _ANCHOR_IMG.sub(caption_anchor, html_content)
    html_content = _FIGURE_IMG.sub(render_overview, html_content)
    return html_content
