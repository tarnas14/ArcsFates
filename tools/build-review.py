#!/usr/bin/env python3
"""generate a Markdown review file from card-metadata.json + the images.

Usage:
    tools/build-review.py <output-name> <path-prefix> [<path-prefix> ...]

Writes ``review/<output-name>.md`` — one block per matching card: a heading keyed to
the image's docs path, the image itself (so a Markdown preview shows the art), and an
editable fenced ``yaml`` payload. A human corrects the YAML; ``tools/apply-review.py``
 writes it back into the manifest. Overview entries are skipped.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "userGuide", "card-metadata.json")
REVIEW_DIR = os.path.join(ROOT, "review")
SCALARS = ("name", "type", "bottom_left", "bottom_right")


def scalar(v):
    if v is None:
        return "null"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def block(key, meta):
    out = [f"## {key}", "", f'![{meta.get("name", "card")}](../userGuide/docs/{key})', "", "```yaml"]
    out += [f"{f}: {scalar(meta.get(f))}" for f in SCALARS]
    out.append("description: |")
    for line in (meta.get("description") or "").rstrip("\n").split("\n"):
        out.append(f"  {line}" if line else "")
    out.append("```")
    return "\n".join(out)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: build-review.py <output-name> <path-prefix> [<path-prefix> ...]")
    name, prefixes = sys.argv[1], sys.argv[2:]
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    keys = sorted(k for k, v in manifest.items()
                  if not v.get("overview") and any(k.startswith(p) for p in prefixes))
    os.makedirs(REVIEW_DIR, exist_ok=True)
    out = os.path.join(REVIEW_DIR, f"{name}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(f"# Review: {name}\n\n")
        fh.write("<!-- Edit ONLY inside the ```yaml blocks. Do not change the `## <path>`\n"
                 "     headings or the image lines. Then run tools/apply-review.py. -->\n\n")
        fh.write("\n\n".join(block(k, manifest[k]) for k in keys))
        fh.write("\n")
    print(f"wrote {out}  ({len(keys)} cards)")


if __name__ == "__main__":
    main()
