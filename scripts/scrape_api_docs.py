#!/usr/bin/env python3
"""Scrape all current Guesty Open API reference pages.

Each page at https://open-api-docs.guesty.com/reference/{slug} has a `.md`
variant that returns raw markdown with an embedded OpenAPI 3.0.3 JSON block
describing one endpoint.

We fetch the slug list dynamically from Guesty's sitemap.xml so the scraper
stays current as Guesty adds endpoints — no hand-edited slug lists going stale.

Output: docs/api-reference/<slug>.md (one file per endpoint, ~320 files)

Usage:
    python scripts/scrape_api_docs.py
    python scripts/scrape_api_docs.py --concurrency 8 --delay-ms 100

Honors Guesty's rate-limit etiquette: 5 concurrent fetches, 200ms inter-batch
sleep. Runs against the public docs site (no auth required).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPO_ROOT = Path(__file__).resolve().parent.parent
SITEMAP_URL = "https://open-api-docs.guesty.com/sitemap.xml"
REFERENCE_BASE = "https://open-api-docs.guesty.com/reference"
OUTPUT_DIR = REPO_ROOT / "docs" / "api-reference"

SLUG_PATTERN = re.compile(r"https://open-api-docs\.guesty\.com/reference/([a-z0-9_-]+)")

# Reasonable fallback if the sitemap is unreachable. Last refreshed 2026-05-10.
# Re-run this script periodically to refresh both the live list and this fallback.
FALLBACK_SLUGS: list[str] = [
    "get_accounts-me",
    "ratestrategycontroller_getlist",
    "ratestrategycontroller_getbyunittypeid",
    # Intentionally short — meant only to verify the scraper still works if
    # sitemap returns 5xx. The real list comes from sitemap.xml at runtime.
]


def fetch_slugs_from_sitemap(url: str = SITEMAP_URL, timeout: int = 30) -> list[str]:
    """Pull every /reference/<slug> URL from Guesty's sitemap.

    Returns sorted, deduplicated slugs. Falls back to FALLBACK_SLUGS on error.
    """
    try:
        req = Request(url, headers={"User-Agent": "guesty-cli scraper"})
        with urlopen(req, timeout=timeout) as resp:
            xml = resp.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"[sitemap] fetch failed ({exc}); using FALLBACK_SLUGS", file=sys.stderr)
        return sorted(set(FALLBACK_SLUGS))

    slugs = sorted(set(SLUG_PATTERN.findall(xml)))
    if len(slugs) < 50:
        print(
            f"[sitemap] only {len(slugs)} slugs found — suspiciously low; using FALLBACK_SLUGS",
            file=sys.stderr,
        )
        return sorted(set(FALLBACK_SLUGS))

    print(f"[sitemap] fetched {len(slugs)} unique reference slugs")
    return slugs


def fetch_markdown(slug: str, timeout: int = 20) -> tuple[str, str | None, str | None]:
    """Fetch one endpoint's markdown.

    Returns (slug, content, error). Exactly one of content/error is non-None.
    """
    url = f"{REFERENCE_BASE}/{slug}.md"
    try:
        req = Request(url, headers={"User-Agent": "guesty-cli scraper"})
        with urlopen(req, timeout=timeout) as resp:
            return slug, resp.read().decode("utf-8"), None
    except HTTPError as exc:
        return slug, None, f"HTTP {exc.code}"
    except (URLError, TimeoutError) as exc:
        return slug, None, str(exc)


def scrape_all(slugs: list[str], output_dir: Path, concurrency: int, delay_ms: int) -> dict:
    """Scrape all slugs into output_dir, respecting concurrency + delay budget."""
    output_dir.mkdir(parents=True, exist_ok=True)
    succeeded: list[tuple[str, int]] = []
    failed: list[tuple[str, str]] = []
    completed = 0
    total = len(slugs)

    # Batch by concurrency to keep load on Guesty's docs site predictable.
    for i in range(0, total, concurrency):
        batch = slugs[i : i + concurrency]
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(fetch_markdown, s) for s in batch]
            for fut in as_completed(futures):
                slug, content, error = fut.result()
                completed += 1
                if content is not None:
                    out_path = output_dir / f"{slug}.md"
                    out_path.write_text(content, encoding="utf-8")
                    succeeded.append((slug, len(content)))
                    if completed % 20 == 0 or completed == total:
                        print(f"  [{completed}/{total}] ...")
                else:
                    print(f"  FAILED {slug}: {error}")
                    failed.append((slug, error or "unknown"))
        time.sleep(delay_ms / 1000.0)

    return {"succeeded": succeeded, "failed": failed, "total": total}


def write_index(output_dir: Path, results: dict) -> None:
    """Write a human-friendly INDEX.md listing all scraped endpoints."""
    lines = [
        "# Guesty API Reference — Scraped Docs",
        "",
        f"Scraped: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"Total: {results['total']}",
        f"Succeeded: {len(results['succeeded'])}",
        f"Failed: {len(results['failed'])}",
        "",
        "## Endpoints",
        "",
    ]
    for slug, size in sorted(results["succeeded"]):
        lines.append(f"- [{slug}](./{slug}.md) ({size / 1024:.1f} KB)")
    if results["failed"]:
        lines.append("")
        lines.append("## Failed")
        lines.append("")
        for slug, err in sorted(results["failed"]):
            lines.append(f"- {slug}: {err}")
    (output_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--concurrency", type=int, default=5, help="Parallel fetches (default 5)")
    parser.add_argument("--delay-ms", type=int, default=200, help="Inter-batch sleep ms (default 200)")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Where .md files go")
    args = parser.parse_args()

    started = time.time()
    slugs = fetch_slugs_from_sitemap()
    print(f"Scraping {len(slugs)} Guesty API doc pages → {args.output_dir}")
    results = scrape_all(slugs, args.output_dir, args.concurrency, args.delay_ms)
    write_index(args.output_dir, results)
    elapsed = time.time() - started

    print()
    print(f"Done in {elapsed:.1f}s. Succeeded: {len(results['succeeded'])}/{results['total']}, failed: {len(results['failed'])}")
    print(f"Next step: python scripts/refresh_api_spec.py")
    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
