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

    # Delete a webhook
    guesty raw DELETE /v1/webhooks/<id>

    # Discover what's available
    guesty raw --list                       # all 60+ categories
    guesty raw --list calendar              # endpoints in 'calendar' category
    guesty raw --search "rate-strateg"      # fuzzy search across paths + titles
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from guesty_cli.core.client import GuestyClient, GuestyError
from guesty_cli.core.exit_codes import EXIT_SUCCESS, EXIT_ERROR, EXIT_USAGE
from guesty_cli.core.output import is_json, print_header, red, yellow, cyan, bold

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SPEC_FILE = REPO_ROOT / "api-spec.json"

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
    p.add_argument("--params", help="Query parameters as JSON object")
    p.add_argument("-H", "--header", action="append", default=[], help="Extra header 'Name: value' (repeatable)")
    p.add_argument("--accept", help="Accept header value (e.g. text/csv)")
    p.add_argument("--content-type", help="Content-Type header value")
    p.add_argument("--output", help="Write response body to file (use '-' for stdout)")
    p.add_argument("--list", action="store_true", help="List endpoints (optionally filter by category)")
    p.add_argument("--search", help="Fuzzy-search endpoints by path or title")
    p.add_argument("--category", help="With --list, restrict to one category")


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


def _read_body(args) -> tuple[str | bytes | None, str | None]:
    """Returns (body, error_message). body is bytes/str ready for the request."""
    sources = sum(bool(x) for x in (args.data, args.data_file))
    if sources > 1:
        return None, "Specify at most one of --data, --data-file"
    if args.data:
        return args.data, None
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


def _normalize_path(path: str) -> str:
    """Strip an optional leading /v1/ since GuestyClient.api_base already includes it."""
    if path.startswith("/v1/"):
        return path[len("/v1/") :]
    if path.startswith("v1/"):
        return path[len("v1/") :]
    return path.lstrip("/")


def _print_response(payload, output_path: str | None) -> int:
    if output_path:
        text = (
            json.dumps(payload, indent=2)
            if not isinstance(payload, (bytes, str))
            else payload
        )
        if isinstance(text, str):
            data = text.encode("utf-8")
        else:
            data = text
        if output_path == "-":
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.write(b"\n")
        else:
            Path(output_path).write_bytes(data)
            print(cyan(f"wrote {len(data)} bytes to {output_path}"))
        return EXIT_SUCCESS

    if isinstance(payload, (dict, list)):
        json.dump(payload, sys.stdout, indent=2)
        print()
    elif payload is None:
        print(cyan("(empty response)"))
    else:
        sys.stdout.write(str(payload))
        if not str(payload).endswith("\n"):
            sys.stdout.write("\n")
    return EXIT_SUCCESS


def run_raw(args) -> int:
    # Discovery modes don't need auth
    if args.list:
        return _do_list(args.category)
    if args.search:
        return _do_search(args.search)

    # Validate request inputs
    if not args.method or not args.path:
        print(red("Usage: guesty raw <METHOD> <PATH>  (or --list / --search)"), file=sys.stderr)
        return EXIT_USAGE

    method = args.method.upper()
    if method not in VALID_METHODS:
        print(red(f"Invalid method '{method}'. Must be one of: {', '.join(VALID_METHODS)}"), file=sys.stderr)
        return EXIT_USAGE

    body, body_err = _read_body(args)
    if body_err:
        print(red(body_err), file=sys.stderr)
        return EXIT_USAGE

    params, params_err = _parse_params(args.params)
    if params_err:
        print(red(params_err), file=sys.stderr)
        return EXIT_USAGE

    path = _normalize_path(args.path)
    client = GuestyClient()

    try:
        if method == "GET":
            response = client.api_get(path, params=params)
        elif method in ("POST", "PUT"):
            # Body for POST/PUT — accept JSON-string or pass-through bytes
            data: dict
            if body is None:
                data = {}
            elif isinstance(body, (bytes, bytearray)):
                data = json.loads(body.decode("utf-8"))
            else:
                data = json.loads(body)
            if method == "POST":
                response = client.api_post(path, data)
            else:
                response = client.api_put(path, data)
        elif method == "DELETE":
            response = client.api_delete(path)
        elif method == "PATCH":
            # The base client doesn't expose api_patch; use _make_request directly.
            url = client._get_api_url(path)
            data: dict = {}
            if body is not None:
                if isinstance(body, (bytes, bytearray)):
                    data = json.loads(body.decode("utf-8"))
                else:
                    data = json.loads(body)
            response = client._make_request("PATCH", url, data=data)
            response = client._parse_response(response) if hasattr(client, "_parse_response") else response
        else:
            # Should be unreachable due to validation above
            return EXIT_USAGE
    except GuestyError as exc:
        print(red(f"Guesty API error: {exc}"), file=sys.stderr)
        return EXIT_ERROR
    except json.JSONDecodeError as exc:
        print(red(f"Body is not valid JSON: {exc}"), file=sys.stderr)
        return EXIT_USAGE

    return _print_response(response, args.output)
