"""mkdocs-gen-files script: emit one standalone page per card.

Reads ``card-metadata.json`` (next to ``mkdocs.yml``) and writes a visible page per
card under ``cards/<namespace>/<name-slug>/``, so mkdocs search indexes each card as
its own result and mkdocs-material highlights matches on the page.

The namespace keeps same-named cards apart (see ``_card_ns``): Base cards under
``base/``, Campaign Court/Misc under ``campaign/``, and each Campaign fate under
``campaign/<N>/``. Overview cards (the fate cards themselves) get NO page here — their
text is rendered inline on the fate page by ``hooks.py``.

Pages are generated at build time only (nothing is committed under ``docs/``).
"""

import html
import json
import os
import posixpath
import re
from urllib.parse import unquote

import mkdocs_gen_files

_ROOT = os.path.dirname(__file__)
_DOCS = os.path.join(_ROOT, "docs")

# A markdown image reference: ![alt](path). Captures the image path so we can map
# each card image back to the gallery page that displays it.
_IMG_LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_FM_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.M)
_HEADING = re.compile(r"^#+\s*(.+?)\s*$", re.M)


def _slug(text):
    # Keep in sync with _slug in hooks.py.
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "card"


# Icon placeholder tags (e.g. <timer>) are shown as code so they don't vanish as
# unknown HTML elements; matches the escaped form produced by html.escape.
_ICON_TAG = re.compile(r"&lt;([a-z][a-z0-9-]*)&gt;")


def _render_description(text):
    # Render description text as HTML, preserving the review file's line composition:
    # blank lines separate paragraphs, single newlines become <br>. Icon placeholder
    # tags like <timer> are wrapped in <code>. Keep in sync with hooks.py.
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


def _gallery_title(text, rel_md):
    # Prefer the frontmatter `title:`; fall back to the first heading, then filename.
    fm = _FRONTMATTER.match(text)
    if fm:
        title = _FM_TITLE.search(fm.group(1))
        if title:
            return title.group(1).strip().strip("\"'")
    heading = _HEADING.search(text)
    if heading:
        return heading.group(1).strip()
    return posixpath.splitext(posixpath.basename(rel_md))[0]


def _gallery_index():
    # Map each card image (docs-relative path, as used to key the manifest) to the
    # gallery page that embeds it: {image_path: (gallery_md_path, gallery_title)}.
    # Gallery pages reference images relative to their own directory.
    index = {}
    for dirpath, _dirs, filenames in os.walk(_DOCS):
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            rel_md = os.path.relpath(os.path.join(dirpath, filename), _DOCS).replace(os.sep, "/")
            with open(os.path.join(dirpath, filename), encoding="utf-8") as fh:
                text = fh.read()
            gallery_dir = posixpath.dirname(rel_md)
            title = _gallery_title(text, rel_md)
            for img in _IMG_LINK.findall(text):
                img_path = posixpath.normpath(posixpath.join(gallery_dir, unquote(img)))
                index.setdefault(img_path, (rel_md, title))
    return index


def _card_ns(docs_path):
    # Namespace pages so same-named cards in different sections/fates don't collide.
    # Keep in sync with hooks.py.
    parts = docs_path.split("/")
    if len(parts) > 1 and parts[0] == "Campaign" and parts[1].isdigit() and 1 <= int(parts[1]) <= 24:
        return "campaign/" + parts[1]
    return parts[0].lower()


def _card_src(docs_path, name):
    return "cards/" + _card_ns(docs_path) + "/" + _slug(name) + ".md"


def _page_markdown(docs_path, meta, page_src, gallery):
    name = meta.get("name") or posixpath.splitext(posixpath.basename(docs_path))[0]
    img_rel = posixpath.relpath(docs_path, posixpath.dirname(page_src))
    lines = [f"# {name}", ""]
    if gallery is not None:
        gallery_md, gallery_title = gallery
        back_rel = posixpath.relpath(gallery_md, posixpath.dirname(page_src))
        # Angle brackets keep the link intact for gallery filenames with spaces
        # (e.g. "11-Planet Breaker.md"); mkdocs still rewrites the .md target to .html.
        lines += [f"[← {gallery_title}](<{back_rel}>)", ""]
    if meta.get("type"):
        lines += [f"*{meta['type']}*", ""]
    lines += [f'![{name}]({img_rel}){{ width="320" }}', ""]
    if meta.get("description"):
        lines += [_render_description(meta["description"]), ""]
    for key in ("bottom_left", "bottom_right"):
        if meta.get(key):
            lines += [f"**{key.replace('_', ' ')}:** {meta[key]}", ""]
    return "\n".join(lines)


with open(os.path.join(_ROOT, "card-metadata.json"), encoding="utf-8") as _fh:
    _manifest = json.load(_fh)

_GALLERY = _gallery_index()

for _docs_path, _meta in _manifest.items():
    if _meta.get("overview"):          # overview text is rendered inline by hooks.py
        continue
    _name = _meta.get("name") or posixpath.splitext(posixpath.basename(_docs_path))[0]
    _src = _card_src(_docs_path, _name)
    with mkdocs_gen_files.open(_src, "w") as _page:
        _page.write(_page_markdown(_docs_path, _meta, _src, _GALLERY.get(_docs_path)))
