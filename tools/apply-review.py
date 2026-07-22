#!/usr/bin/env python3
"""Apply reviewed ``review/*.md`` files back into card-metadata.json.

Parses each review block — the ``## <docs-path>`` heading is the manifest key, the
fenced ``yaml`` payload holds the fields — and writes ``name`` / ``type`` /
``bottom_left`` / ``bottom_right`` / ``description`` onto the matching entry. Stdlib
only; idempotent. Unknown keys and malformed blocks are reported and skipped, never
created; an emptied ``name`` is refused so a page URL can't be blanked by accident.

Usage:
    tools/apply-review.py [--dry-run] [review/base-lore.md ...]

With no file arguments it applies every ``review/*.md``. ``--dry-run`` reports what
would change and writes nothing. Pairs with ``tools/build-review.py``.
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "userGuide", "card-metadata.json")
REVIEW_DIR = os.path.join(ROOT, "review")
FIELDS = ("name", "type", "bottom_left", "bottom_right", "description")

HEADING = re.compile(r"^##\s+(\S.*?)\s*$")
FENCE = re.compile(r"^\s*```")
FIELD = re.compile(r"^(name|type|bottom_left|bottom_right|description):\s?(.*)$")


def parse_scalar(s):
    s = s.strip()
    if s in ("", "null", "~"):
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        if s[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return s


def dedent_block(lines):
    lines = list(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    first = next((l for l in lines if l.strip()), lines[0])
    indent = len(first) - len(first.lstrip(" "))
    out = []
    for l in lines:
        if not l.strip():
            out.append("")
        elif l[:indent] == " " * indent:
            out.append(l[indent:])
        else:
            out.append(l.lstrip(" "))
    return "\n".join(out)


def parse_fence_body(body):
    fields, j = {}, 0
    while j < len(body):
        m = FIELD.match(body[j])
        if not m:
            j += 1
            continue
        key, rest = m.group(1), m.group(2)
        if key == "description":
            if rest.strip().startswith("|"):          # block scalar → rest of body
                fields["description"] = dedent_block(body[j + 1:])
                break
            fields["description"] = parse_scalar(rest)  # collapsed onto one line
            j += 1
        else:
            fields[key] = parse_scalar(rest)
            j += 1
    return fields


def parse_review(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    records, i, n = [], 0, len(lines)
    while i < n:
        m = HEADING.match(lines[i])
        if not m:
            i += 1
            continue
        key = m.group(1)
        i += 1
        while i < n and not FENCE.match(lines[i]) and not HEADING.match(lines[i]):
            i += 1
        if i >= n or HEADING.match(lines[i]):
            records.append((key, None))               # no fence → malformed
            continue
        i += 1                                          # past ```yaml
        start = i
        while i < n and not FENCE.match(lines[i]):
            i += 1
        body = lines[start:i]
        if i < n:
            i += 1                                      # past closing ```
        records.append((key, parse_fence_body(body)))
    return records


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    files = [a for a in args if not a.startswith("-")] or sorted(glob.glob(os.path.join(REVIEW_DIR, "*.md")))
    if not files:
        sys.exit("no review files found")
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)

    updated, unchanged, unknown, malformed, renamed, warnings = [], 0, [], [], [], []
    for path in files:
        base = os.path.basename(path)
        for key, fields in parse_review(path):
            if fields is None:
                malformed.append((base, key))
                continue
            if key not in manifest:
                unknown.append((base, key))
                continue
            entry, changes = manifest[key], []
            for f in FIELDS:
                if f not in fields:
                    continue
                val = fields[f]
                if f == "name" and not val:
                    warnings.append((key, "empty name ignored"))
                    continue
                if val != entry.get(f):
                    if f == "name":
                        renamed.append((key, entry.get(f), val))
                    if f == "description" and not val:
                        warnings.append((key, "description cleared"))
                    entry[f] = val
                    changes.append(f)
            if changes:
                updated.append((key, changes))
            else:
                unchanged += 1

    if not dry:
        with open(MANIFEST, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")

    print(f"files: {len(files)}   updated: {len(updated)}   unchanged: {unchanged}")
    for key, ch in updated:
        print(f"    {key}: {', '.join(ch)}")
    if renamed:
        print("renames (regenerate to pick up the new page URL):")
        for key, old, new in renamed:
            print(f"    {key}: {old!r} -> {new!r}")
    if warnings:
        print("warnings:")
        for key, msg in warnings:
            print(f"    {key}: {msg}")
    print(f"unknown keys (skipped): {unknown or 'none'}")
    print(f"malformed blocks (skipped): {malformed or 'none'}")
    print("[dry-run] nothing written" if dry else f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
