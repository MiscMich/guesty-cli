"""Property photo management for guesty-cli.

Upload, list, reorder, and delete listing photos via the Guesty
``properties-api`` photo endpoints. Uploads use multipart/form-data and are
sent sequentially with a small delay + retry, because firing them back-to-back
triggers transient connection resets on Guesty's side.
"""
import os
import re
import time

from guesty_cli.core.client import GuestyClient
from guesty_cli.core.config import load_config
from guesty_cli.core.database import get_db
from guesty_cli.core.output import bold, cyan, dim, green, print_json, red, yellow

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")
_PHOTOS_PATH = "properties-api/property-photos/property-photos/{lid}"
_ID_RE = re.compile(r"^[a-f0-9]{24}$", re.I)


def register(subparsers):
    """Register photo commands with the argument parser."""
    parser = subparsers.add_parser(
        "photos", help="Manage listing photos (upload, list, reorder, delete)"
    )
    sub = parser.add_subparsers(dest="photos_action")

    list_parser = sub.add_parser("list", help="List photos for a listing")
    list_parser.add_argument("listing", help="Listing ID or nickname")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.set_defaults(func=run_list)

    up = sub.add_parser("upload", help="Upload photo(s) from a file or directory")
    up.add_argument("listing", help="Listing ID or nickname")
    up.add_argument("paths", nargs="+", help="Image file(s) or a directory of images")
    up.add_argument("--order-by-name", action="store_true",
                    help="After upload, reorder ALL photos on the listing by filename (natural sort; first = cover)")
    up.add_argument("--retries", type=int, default=4,
                    help="Retries per file on transient failure (default: 4)")
    up.add_argument("--delay", type=float, default=0.4,
                    help="Seconds to wait between uploads (default: 0.4)")
    up.add_argument("--dry-run", action="store_true",
                    help="List what would be uploaded without uploading")
    up.add_argument("--json", action="store_true", help="Output as JSON")
    up.set_defaults(func=run_upload)

    order_parser = sub.add_parser("order", help="Set photo display order (first = cover)")
    order_parser.add_argument("listing", help="Listing ID or nickname")
    order_parser.add_argument("ids", nargs="+",
                              help="Photo IDs in desired order (comma- or space-separated; first = cover)")
    order_parser.add_argument("--json", action="store_true", help="Output as JSON")
    order_parser.set_defaults(func=run_order)

    del_parser = sub.add_parser("delete", help="Delete photo(s) by ID")
    del_parser.add_argument("listing", help="Listing ID or nickname")
    del_parser.add_argument("ids", nargs="+", help="Photo ID(s) to delete (comma- or space-separated)")
    del_parser.add_argument("--force", "-y", action="store_true", help="Skip confirmation")
    del_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    del_parser.add_argument("--json", action="store_true", help="Output as JSON")
    del_parser.set_defaults(func=run_delete)


# ---------------------------------------------------------------- helpers

def _resolve_listing(identifier):
    """Resolve a listing nickname/ID to (id, nickname).

    Tries the local DB first; falls back to treating a 24-hex string as a raw
    listing ID (new listings may not be synced into the local DB yet).
    """
    try:
        db = get_db()
        row = db.execute(
            "SELECT id, nickname FROM listings WHERE id = ?", (identifier,)
        ).fetchone()
        if row:
            return row["id"], row["nickname"]
        row = db.execute(
            "SELECT id, nickname FROM listings WHERE LOWER(nickname) LIKE LOWER(?)",
            (f"%{identifier}%",),
        ).fetchone()
        if row:
            return row["id"], row["nickname"]
    except Exception:
        pass
    if _ID_RE.match(identifier or ""):
        return identifier, identifier
    return None, None


def _natural_key(text):
    """Natural sort key so EmeraldPalms-2 sorts before EmeraldPalms-10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text or "")]


def _collect_images(paths):
    """Expand the given file/dir paths into a natural-sorted list of image files."""
    files = []
    for path in paths:
        if os.path.isdir(path):
            for name in os.listdir(path):
                if name.lower().endswith(IMAGE_EXTS) and not name.startswith("."):
                    files.append(os.path.join(path, name))
        elif os.path.isfile(path):
            files.append(path)
    files.sort(key=lambda f: _natural_key(os.path.basename(f)))
    return files


def _source_name(source):
    """Original filename embedded in a Guesty photo ``source`` URL.

    Guesty appends a ``-<hash>`` suffix, e.g. ``.../EmeraldPalms-50-zdCl1`` ->
    ``EmeraldPalms-50``.
    """
    base = (source or "").rstrip("/").split("/")[-1]
    return re.sub(r"-[A-Za-z0-9]{4,}$", "", base)


def _list_photos(client, listing_id):
    resp = client.api_get(_PHOTOS_PATH.format(lid=listing_id))
    if isinstance(resp, dict):
        return resp.get("photos", [])
    return resp if isinstance(resp, list) else []


def _order_by_source_name(photos):
    """Photo IDs ordered by the natural sort of their source filename."""
    ordered = sorted(photos, key=lambda p: _natural_key(_source_name(p.get("source", ""))))
    return [p["_id"] for p in ordered]


def _flatten_ids(raw_ids):
    out = []
    for chunk in raw_ids:
        out.extend([x.strip() for x in chunk.split(",") if x.strip()])
    return out


# ---------------------------------------------------------------- commands

def run_list(args):
    """List photos for a listing."""
    config = load_config()
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    listing_id, nickname = _resolve_listing(args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found."))
        return
    client = GuestyClient(config)
    try:
        photos = _list_photos(client, listing_id)
    except Exception as e:
        print(red(f"Error listing photos: {e}"))
        return

    if getattr(args, "json", False):
        print_json(photos)
        return

    print()
    print(bold(f"Photos: {nickname or listing_id} ({len(photos)})"))
    for photo in sorted(photos, key=lambda p: p.get("index", 0)):
        idx = photo.get("index", "?")
        tag = green(" (cover)") if idx == 0 else ""
        caption = (photo.get("caption") or "")[:40]
        print(f"  {str(idx):>3}{tag}  {dim(photo.get('_id', ''))}  "
              f"{_source_name(photo.get('source', ''))}  {dim(caption)}")


def run_upload(args):
    """Upload one or more photos to a listing."""
    config = load_config()
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    listing_id, nickname = _resolve_listing(args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found."))
        return

    files = _collect_images(args.paths)
    if not files:
        print(red("No image files found in the given path(s)."))
        return

    as_json = getattr(args, "json", False)
    missing = [p for p in args.paths if not os.path.exists(p)]
    if not as_json:
        print()
        print(bold(f"Upload to: {nickname or listing_id}"))
        print(f"  Files: {len(files)}")
        if missing:
            print(yellow(f"  Skipping {len(missing)} path(s) that don't exist: {', '.join(missing)}"))

    if args.dry_run:
        if as_json:
            print_json({"would_upload": [os.path.basename(f) for f in files]})
        else:
            print(cyan("[DRY RUN] Would upload, in this order:"))
            for f in files:
                print(f"  • {os.path.basename(f)}")
            if args.order_by_name:
                print(cyan("  Then set photo order by filename."))
        return

    client = GuestyClient(config)
    uploaded, failed = [], []
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        last_err = ""
        for attempt in range(1, max(1, args.retries) + 1):
            try:
                client.upload_photo(listing_id, path)
                last_err = ""
                break
            except Exception as e:  # transient resets, rate limits, etc.
                last_err = str(e)
                time.sleep(args.delay * attempt)
        if last_err:
            failed.append((name, last_err))
            if not as_json:
                print(f"  {red('✗')} {i}/{len(files)} {name} — {last_err}")
        else:
            uploaded.append(name)
            if not as_json:
                print(f"  {green('✓')} {i}/{len(files)} {name}")
            time.sleep(args.delay)  # pace between successes; failures already backed off

    photos = _list_photos(client, listing_id)
    ordered = False
    if args.order_by_name and not failed:
        order_ids = _order_by_source_name(photos)
        try:
            client.api_post(_PHOTOS_PATH.format(lid=listing_id) + "/order", {"order": order_ids})
            ordered = True
        except Exception as e:
            if not as_json:
                print(yellow(f"  Photo order not set: {e}"))

    if as_json:
        print_json({
            "uploaded": uploaded,
            "failed": [{"file": n, "error": e} for n, e in failed],
            "total_photos": len(photos),
            "ordered_by_name": ordered,
        })
        return

    print()
    print(bold("Upload complete"))
    print(f"  Uploaded: {green(len(uploaded))}  |  "
          f"Failed: {red(len(failed)) if failed else 0}  |  "
          f"Total photos now: {len(photos)}")
    if ordered:
        print(green(f"  ✓ Reordered all {len(photos)} photos on the listing by filename"))
    if failed:
        print(yellow("  Failed (re-run the same command to retry just these):"))
        for name, err in failed:
            print(f"   - {name}: {err}")


def run_order(args):
    """Set the photo display order (first id becomes the cover)."""
    config = load_config()
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    listing_id, nickname = _resolve_listing(args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found."))
        return
    ids = _flatten_ids(args.ids)
    if not ids:
        print(red("No photo IDs provided."))
        return
    client = GuestyClient(config)
    try:
        client.api_post(_PHOTOS_PATH.format(lid=listing_id) + "/order", {"order": ids})
    except Exception as e:
        print(red(f"Error setting order: {e}"))
        return
    if getattr(args, "json", False):
        print_json({"listing": listing_id, "ordered": len(ids), "cover": ids[0]})
        return
    print(green(f"✓ Order set on '{nickname or listing_id}' "
                f"({len(ids)} photos; cover = {ids[0]})"))


def run_delete(args):
    """Delete one or more photos by ID."""
    config = load_config()
    if not config:
        print(red("Error: Not configured. Run 'guesty init' first."))
        return
    listing_id, nickname = _resolve_listing(args.listing)
    if not listing_id:
        print(red(f"Listing '{args.listing}' not found."))
        return
    ids = _flatten_ids(args.ids)
    if not ids:
        print(red("No photo IDs provided."))
        return

    as_json = getattr(args, "json", False)
    if args.dry_run:
        if as_json:
            print_json({"would_delete": ids})
        else:
            print(cyan(f"[DRY RUN] Would delete {len(ids)} photo(s) from '{nickname or listing_id}':"))
            for pid in ids:
                print(f"  • {pid}")
        return

    if not args.force:
        if os.environ.get("GUESTY_NO_INPUT") or getattr(args, "no_input", False):
            print(red("Refusing to delete without --force in non-interactive mode."))
            return
        answer = input(f"Delete {len(ids)} photo(s) from '{nickname or listing_id}'? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    client = GuestyClient(config)
    deleted = 0
    results = []
    for pid in ids:
        try:
            client.api_delete(_PHOTOS_PATH.format(lid=listing_id) + f"/{pid}")
            deleted += 1
            results.append({"id": pid, "deleted": True})
            if not as_json:
                print(f"  {green('✓')} deleted {pid}")
        except Exception as e:
            results.append({"id": pid, "deleted": False, "error": str(e)})
            if not as_json:
                print(f"  {red('✗')} {pid} — {e}")
    if as_json:
        print_json({"deleted": deleted, "total": len(ids), "results": results})
    else:
        print(bold(f"Deleted {deleted}/{len(ids)} photo(s)."))
