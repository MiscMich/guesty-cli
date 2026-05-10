"""Raw API access — escape hatch for any Guesty Open API endpoint.

The named subcommands (`listings`, `reservations`, `calendar`, etc.) cover the
endpoints we use most. But Guesty's Open API has 315+ endpoints across 60+
categories. `raw` lets you call any of them without waiting for a wrapper.

Examples:
    # Read a listing
    guesty raw GET /v1/listings/<id>

    # List with query params
    guesty raw GET /v1/listings --params '{"limit":5,"fields":"_id title"}'

    # Update calendar (price + min nights for a date range)
    guesty raw PUT /v1/availability-pricing/api/calendar/listings/<id> \\
        --data '{"startDate":"2026-06-01","endDate":"2026-06-07","price":389,"minNights":7}'

    # Mutating call WITH query params (e.g. updateSubUnits flag)
    guesty raw PUT /v1/marketing/languages/<id> --params '{"updateSubUnits":true}' \\
        --data '{"locale":"en"}'

    # Binary / CSV response
    guesty raw POST /v1/reservations.csv --accept text/csv --output reservations.csv

    # Custom header
    guesty raw GET /v1/listings -H 'X-Test-Header: value'

    # Discover what's available
    guesty raw --list                       # all 60+ categories
    guesty raw --list --category calendar   # endpoints in 'calendar' category
    guesty raw --search "rate-strateg"      # fuzzy search across paths + titles

This command bypasses the higher-level GuestyClient.api_* methods (which always
JSON-decode and ignore custom headers/params for mutations) and uses urllib
directly. It still relies on GuestyClient for OAuth token management and rate
limiting, so token caching and the 24h limit still apply.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from guesty_cli.core.client import GuestyClient, GuestyError
from guesty_cli.core.exit_codes import EXIT_SUCCESS, EXIT_ERROR, EXIT_USAGE
from guesty_cli.core.output import is_json, print_header, red, yellow, cyan, bold

# Spec lives inside the installed package, so this path works in editable installs
# AND in wheel installs (where Path(__file__) resolves under site-packages).
SPEC_FILE = Path(__file__).resolve().parent.parent / "api-spec.json"

VALID_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def register(subparsers) -> None:
    """Register the raw command with the argument parser."""
    p = subparsers.add_parser(
        "raw",
        help="Call any Guesty Open API endpoint directly",
        description=(
            "Make a raw HTTP call to any Guesty Open API endpoint. "
            "Use --list/--search to discover endpoints."
        ),
    )
    p.set_defaults(func=run_raw)
    p.add_argument("method", nargs="?", help="HTTP method (GET, POST, PUT, PATCH, DELETE)")
    p.add_argument("path", nargs="?", help="API path, e.g. /v1/listings/<id>")
    p.add_argument("--data", help="JSON request body (string)")
    p.add_argument("--data-file", help="Read request body from a file")
    p.add_argument("--params", help="Query parameters as JSON object (works for ALL methods)")
    p.add_argument("-H", "--header", action="append", default=[], help="Extra header 'Name: value' (repeatable)")
    p.add_argument("--accept", help="Accept header value (e.g. text/csv)")
    p.add_argument("--content-type", help="Content-Type header value (default: application/json)")
    p.add_argument("--output", help="Write response body to file (use '-' for stdout)")
    p.add_argument("--list", action="store_true", help="List endpoints (optionally filter by category)")
    p.add_argument("--search", help="Fuzzy-search endpoints by path or title")
    p.add_argument("--category", help="With --list, restrict to one category")


# ────────────────────────────────────────────────────────────────────────────
# Discovery (no auth required)
# ────────────────────────────────────────────────────────────────────────────


def _load_spec() -> dict | None:
    if not SPEC_FILE.is_file():
        return None
    try:
        return json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(red(f"Failed to load {SPEC_FILE}: {exc}"), file=sys.stderr)
        return None


def _do_list(category: str | None) -> int:
    spec = _load_spec()
    if not spec:
        print(yellow(
            "api-spec.json not found. Run: python scripts/scrape_api_docs.py "
            "&& python scripts/refresh_api_spec.py"
        ), file=sys.stderr)
        return EXIT_ERROR

    if category:
        entries = spec.get(category)
        if entries is None:
            print(red(f"No category '{category}'. Available: {', '.join(sorted(spec.keys()))}"), file=sys.stderr)
            return EXIT_ERROR
        print(bold(f"\n[{category}] {len(entries)} endpoints\n"))
        for e in entries:
            print(f"  {e['method']:6} {e['path']:65} {e['title']}")
        return EXIT_SUCCESS

    if is_json():
        json.dump(spec, sys.stdout, indent=2)
        print()
        return EXIT_SUCCESS

    total = sum(len(v) for v in spec.values())
    print(bold(f"\n{total} endpoints across {len(spec)} categories"))
    print()
    for cat in sorted(spec.keys()):
        print(f"  {len(spec[cat]):>4}  {cat}")
    print()
    print(cyan("Use 'guesty raw --list <category>' to see endpoints, or 'guesty raw --search <term>' to fuzzy-find."))
    return EXIT_SUCCESS


def _do_search(term: str) -> int:
    spec = _load_spec()
    if not spec:
        print(yellow("api-spec.json not found."), file=sys.stderr)
        return EXIT_ERROR

    term_lc = term.lower()
    hits: list[tuple[str, dict]] = []
    for cat, entries in spec.items():
        for e in entries:
            if term_lc in e["path"].lower() or term_lc in e["title"].lower() or term_lc in cat.lower():
                hits.append((cat, e))

    if not hits:
        print(yellow(f"No matches for '{term}'."), file=sys.stderr)
        return EXIT_ERROR

    print(bold(f"\n{len(hits)} matches for '{term}':\n"))
    for cat, e in hits[:200]:
        print(f"  [{cat}] {e['method']:6} {e['path']:65} {e['title']}")
    if len(hits) > 200:
        print(yellow(f"  ... and {len(hits) - 200} more (refine your search)"))
    return EXIT_SUCCESS


# ────────────────────────────────────────────────────────────────────────────
# HTTP request layer (bypasses GuestyClient.api_* to keep full control)
# ────────────────────────────────────────────────────────────────────────────


def _read_body(args) -> tuple[bytes | None, str | None]:
    """Returns (body_bytes, error_message). Both None if no body specified."""
    if args.data and args.data_file:
        return None, "Specify at most one of --data, --data-file"
    if args.data:
        return args.data.encode("utf-8"), None
    if args.data_file:
        try:
            return Path(args.data_file).read_bytes(), None
        except OSError as exc:
            return None, f"Cannot read --data-file: {exc}"
    return None, None


def _parse_params(raw: str | None) -> tuple[dict | None, str | None]:
    if not raw:
        return None, None
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None, "--params must be a JSON object"
        return parsed, None
    except json.JSONDecodeError as exc:
        return None, f"--params is not valid JSON: {exc}"


def _parse_headers(headers: list[str]) -> tuple[dict, str | None]:
    """Parse a list of 'Name: value' strings into a dict."""
    out = {}
    for h in headers:
        if ":" not in h:
            return {}, f"Invalid header (missing ':'): {h!r}"
        name, _, value = h.partition(":")
        out[name.strip()] = value.strip()
    return out, None


def _build_url(client: GuestyClient, path: str, params: dict | None) -> str:
    """Build the full URL, including query string, regardless of HTTP method."""
    # Strip leading /v1/ since client._get_api_url already adds it.
    path = path.lstrip("/")
    if path.startswith("v1/"):
        path = path[len("v1/"):]
    url = client._get_api_url(path)
    if params:
        # Replicate the existing client behavior of JSON-encoding nested values
        query_parts = []
        for key, value in params.items():
            if isinstance(value, (dict, list)):
                query_parts.append((key, json.dumps(value)))
            else:
                query_parts.append((key, value))
        url = f"{url}?{urlencode(query_parts)}"
    return url


def _do_request(
    client: GuestyClient,
    method: str,
    url: str,
    body: bytes | None,
    headers: dict,
    accept: str | None,
    content_type: str | None,
) -> tuple[bytes, str, int]:
    """Make the HTTP call directly via urllib. Returns (body_bytes, content_type, status)."""
    # Get auth token via the existing client (handles caching + rate limits)
    try:
        token = client.get_token()
    except Exception as exc:
        raise GuestyError(f"Auth failed: {exc}")

    # Compose final headers
    req_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept or "application/json",
    }
    if body is not None:
        req_headers["Content-Type"] = content_type or "application/json"
    req_headers.update(headers)  # user-provided headers win

    # Apply the client's rate limit budget (best-effort; client tracks counts)
    if hasattr(client, "_check_rate_limit"):
        try:
            client._check_rate_limit()
        except Exception:
            pass  # don't fail the whole call on rate-limit bookkeeping

    req = Request(url, data=body, method=method, headers=req_headers)
    try:
        ssl_ctx = ssl.create_default_context()
        with urlopen(req, context=ssl_ctx, timeout=60) as resp:
            resp_body = resp.read()
            resp_ct = resp.headers.get("Content-Type", "")
            return resp_body, resp_ct, resp.status
    except HTTPError as exc:
        # Surface the response body so the user sees Guesty's error message
        try:
            err_body = exc.read() or b""
        except Exception:
            err_body = b""
        msg = err_body.decode("utf-8", errors="replace") if err_body else str(exc)
        raise GuestyError(f"HTTP {exc.code}: {msg}")
    except URLError as exc:
        raise GuestyError(f"Network error: {exc}")


def _print_response(body: bytes, content_type: str, output_path: str | None) -> int:
    """Print or write the response, handling text/binary/JSON correctly."""
    if output_path:
        if output_path == "-":
            sys.stdout.buffer.write(body)
            if not body.endswith(b"\n"):
                sys.stdout.buffer.write(b"\n")
        else:
            Path(output_path).write_bytes(body)
            print(cyan(f"wrote {len(body)} bytes to {output_path}"))
        return EXIT_SUCCESS

    # No --output: print to stdout based on content-type
    is_json_resp = "json" in content_type.lower() or content_type.lower().startswith("application/")
    if is_json_resp and body:
        try:
            parsed = json.loads(body.decode("utf-8"))
            json.dump(parsed, sys.stdout, indent=2)
            print()
            return EXIT_SUCCESS
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass  # fall through to text/binary

    # Text-ish: stream as-is
    if body:
        try:
            sys.stdout.write(body.decode("utf-8"))
            if not body.endswith(b"\n"):
                sys.stdout.write("\n")
        except UnicodeDecodeError:
            # Binary response with no --output: warn and dump to stdout buffer
            print(yellow(f"binary response ({len(body)} bytes); use --output to save to a file"), file=sys.stderr)
            sys.stdout.buffer.write(body)
    else:
        print(cyan("(empty response)"))
    return EXIT_SUCCESS


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────


def run_raw(args) -> None:
    """Entry point. Calls sys.exit() with the appropriate code so the shell sees it.

    The parent main() doesn't propagate handler return values, so handlers that
    care about exit codes must call sys.exit() themselves. Discovery commands and
    successful API calls exit via the normal sys.exit(EXIT_SUCCESS) at the end.
    """
    if args.list:
        sys.exit(_do_list(args.category))
    if args.search:
        sys.exit(_do_search(args.search))

    if not args.method or not args.path:
        print(red("Usage: guesty raw <METHOD> <PATH>  (or --list / --search)"), file=sys.stderr)
        sys.exit(EXIT_USAGE)

    method = args.method.upper()
    if method not in VALID_METHODS:
        print(red(f"Invalid method '{method}'. Must be one of: {', '.join(VALID_METHODS)}"), file=sys.stderr)
        sys.exit(EXIT_USAGE)

    body, body_err = _read_body(args)
    if body_err:
        print(red(body_err), file=sys.stderr)
        sys.exit(EXIT_USAGE)

    params, params_err = _parse_params(args.params)
    if params_err:
        print(red(params_err), file=sys.stderr)
        sys.exit(EXIT_USAGE)

    headers, header_err = _parse_headers(args.header)
    if header_err:
        print(red(header_err), file=sys.stderr)
        sys.exit(EXIT_USAGE)

    client = GuestyClient()
    url = _build_url(client, args.path, params)

    try:
        resp_body, resp_ct, _status = _do_request(
            client=client,
            method=method,
            url=url,
            body=body,
            headers=headers,
            accept=args.accept,
            content_type=args.content_type,
        )
    except GuestyError as exc:
        print(red(f"Guesty API error: {exc}"), file=sys.stderr)
        sys.exit(EXIT_ERROR)

    sys.exit(_print_response(resp_body, resp_ct, args.output))
