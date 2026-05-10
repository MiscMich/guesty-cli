#!/usr/bin/env python3
"""Compile scraped Guesty API docs into api-spec.json.

Reads docs/api-reference/*.md (flat layout produced by scrape_api_docs.py).
Each .md file contains a fenced ```json``` block with an OpenAPI 3.0.3 spec
for a single endpoint. We extract method + path + summary + tag (= category)
and group entries by category in the manifest.

Output: api-spec.json with shape:
    { "<category>": [ {"method", "path", "title", "slug"}, ... ], ... }

The CLI's `raw` command consumes this manifest to validate paths and offer
discovery helpers.

Usage:
    python scripts/refresh_api_spec.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs" / "api-reference"
OUT_FILE = REPO_ROOT / "api-spec.json"

JSON_BLOCK_RE = re.compile(r"```json\n([\s\S]*?)\n```")


def extract_json_block(md: str) -> str | None:
    m = JSON_BLOCK_RE.search(md)
    return m.group(1) if m else None


def parse_endpoint(spec_json: str, slug: str) -> tuple[dict, str] | None:
    """Parse one endpoint's OpenAPI block. Returns (entry, category) or None."""
    spec = json.loads(spec_json)
    paths = spec.get("paths") or {}
    if not paths:
        return None
    api_path, methods = next(iter(paths.items()))
    if not methods:
        return None
    method, details = next(iter(methods.items()))

    # Category derivation: prefer endpoint tags → spec.tags[0].name → "uncategorized"
    category = "uncategorized"
    if details.get("tags"):
        category = str(details["tags"][0])
    elif isinstance(spec.get("tags"), list) and spec["tags"]:
        category = str(spec["tags"][0].get("name") or category)

    # Normalize: lowercase, hyphenate, strip non-[a-z0-9-]
    category = re.sub(r"[^a-z0-9-]", "", category.lower().replace(" ", "-"))

    entry = {
        "method": method.upper(),
        "path": f"/v1{api_path}",
        "title": details.get("summary") or slug,
        "slug": slug,
    }
    return entry, category


def main() -> int:
    if not DOCS_DIR.is_dir():
        print(f"ERROR: {DOCS_DIR} does not exist — run scripts/scrape_api_docs.py first", file=sys.stderr)
        return 1

    result: dict[str, list[dict]] = {}
    errors = 0
    seen = 0
    skipped_no_json = 0

    for md_path in sorted(DOCS_DIR.glob("*.md")):
        if md_path.name == "INDEX.md":
            continue
        slug = md_path.stem
        content = md_path.read_text(encoding="utf-8")
        json_block = extract_json_block(content)
        if not json_block:
            # Overview / guide pages — no endpoint to register
            skipped_no_json += 1
            continue
        try:
            parsed = parse_endpoint(json_block, slug)
            if not parsed:
                continue
            entry, category = parsed
            result.setdefault(category, []).append(entry)
            seen += 1
        except Exception as exc:
            print(f"  SKIP {md_path.name}: {exc}", file=sys.stderr)
            errors += 1

    # Stable sort within each category
    for cat in result:
        result[cat].sort(key=lambda e: (e["path"], e["method"]))
    sorted_result = {k: result[k] for k in sorted(result.keys())}

    OUT_FILE.write_text(json.dumps(sorted_result, indent=2) + "\n", encoding="utf-8")

    total = sum(len(v) for v in sorted_result.values())
    print(f"api-spec.json: {total} endpoints across {len(sorted_result)} categories")
    if skipped_no_json:
        print(f"  ({skipped_no_json} overview/guide pages had no JSON block — expected)")
    if errors:
        print(f"  ({errors} parse errors)")

    # Top 15 categories by endpoint count — useful eyeball check
    print()
    print("Top categories:")
    top = sorted(sorted_result.items(), key=lambda kv: -len(kv[1]))[:15]
    for cat, entries in top:
        print(f"  {len(entries):>4}  {cat}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
