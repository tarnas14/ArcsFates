"""mkdocs-gen-files script: emit one standalone page per card.

Reads ``card-metadata.json`` (next to ``mkdocs.yml``) and, for each entry, writes a
virtual page under ``cards/<name-slug>/`` holding the card image and its transcribed
text as VISIBLE content. Unlike the earlier hidden-text approach, this makes each
card its own search result whose text mkdocs-material can highlight on the page, and
gives every card a shareable URL.

The pages are generated at build time only (nothing is committed under ``docs/``).
Scope today is whatever lives in the manifest — the Leader cards (mock text) plus a
couple of pre-existing entries.
"""

import json
import os
import posixpath
import re

import mkdocs_gen_files

_ROOT = os.path.dirname(__file__)


def _slug(text):
    # Keep in sync with _slug in hooks.py: the gallery hook rebuilds this same path
    # to link each thumbnail's lightbox caption to the card page generated here.
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "card"


def _page_markdown(docs_path, meta):
    name = meta.get("name") or posixpath.splitext(posixpath.basename(docs_path))[0]
    # Card pages live one directory deep (cards/<slug>.md), so images resolve via "../".
    lines = [f"# {name}", ""]
    if meta.get("type"):
        lines += [f"*{meta['type']}*", ""]
    lines += [f'![{name}](../{docs_path}){{ width="320" }}', ""]
    if meta.get("description"):
        lines += [meta["description"], ""]
    for key in ("bottom_left", "bottom_right"):
        if meta.get(key):
            lines += [f"**{key.replace('_', ' ')}:** {meta[key]}", ""]
    return "\n".join(lines)


with open(os.path.join(_ROOT, "card-metadata.json"), encoding="utf-8") as _fh:
    _manifest = json.load(_fh)

for _docs_path, _meta in _manifest.items():
    _name = _meta.get("name") or posixpath.splitext(posixpath.basename(_docs_path))[0]
    _out = f"cards/{_slug(_name)}.md"
    with mkdocs_gen_files.open(_out, "w") as _page:
        _page.write(_page_markdown(_docs_path, _meta))
