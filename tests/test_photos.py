"""Tests for the `photos` command: CLI surface + pure helpers."""
import json
import os
import sys

import pytest

CLI_MODULE = "guesty_cli.main"
CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args, env_extra=None):
    """Run guesty-cli as a subprocess and return (returncode, stdout, stderr)."""
    import subprocess
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, "-m", CLI_MODULE] + list(args),
        capture_output=True, text=True, cwd=CLI_DIR, env=env, timeout=15,
    )
    return result.returncode, result.stdout, result.stderr


class TestPhotosCLISurface:
    def test_photos_help_lists_subcommands(self):
        code, out, _ = run_cli("photos", "--help")
        assert code == 0
        for sub in ("list", "upload", "order", "delete"):
            assert sub in out

    def test_upload_help_has_order_by_name(self):
        code, out, _ = run_cli("photos", "upload", "--help")
        assert code == 0
        assert "--order-by-name" in out
        assert "--dry-run" in out

    def test_schema_includes_photos(self):
        code, out, _ = run_cli("schema", "photos")
        assert code == 0
        parsed = json.loads(out)
        assert "photos" in parsed["commands"]


class TestMultipartBuilder:
    def test_build_multipart_body_structure(self):
        from guesty_cli.core.client import build_multipart_body
        body, content_type = build_multipart_body("file", "a.jpg", b"\xff\xd8DATA", "image/jpeg")
        assert content_type.startswith("multipart/form-data; boundary=----guestycli")
        boundary = content_type.split("boundary=")[1]
        assert body.startswith(b"--" + boundary.encode())
        assert b'name="file"; filename="a.jpg"' in body
        assert b"Content-Type: image/jpeg" in body
        assert b"\xff\xd8DATA" in body
        assert body.rstrip().endswith(b"--" + boundary.encode() + b"--")

    def test_build_multipart_body_unique_boundary(self):
        from guesty_cli.core.client import build_multipart_body
        _, ct1 = build_multipart_body("file", "a.jpg", b"x")
        _, ct2 = build_multipart_body("file", "a.jpg", b"x")
        assert ct1 != ct2  # random boundary per call


class TestPhotoHelpers:
    def test_source_name_strips_hash(self):
        from guesty_cli.commands.photos import _source_name
        assert _source_name("https://assets/x/y/EmeraldPalms-50-zdCl1") == "EmeraldPalms-50"
        assert _source_name("https://assets/x/y/cover-AbCdEf") == "cover"

    def test_flatten_ids_handles_comma_and_space(self):
        from guesty_cli.commands.photos import _flatten_ids
        assert _flatten_ids(["a,b", "c", " d , e "]) == ["a", "b", "c", "d", "e"]

    def test_natural_key_orders_numerically(self):
        from guesty_cli.commands.photos import _natural_key
        names = ["x-10.jpg", "x-2.jpg", "x-1.jpg"]
        assert sorted(names, key=_natural_key) == ["x-1.jpg", "x-2.jpg", "x-10.jpg"]

    def test_collect_images_filters_and_sorts(self, tmp_path):
        from guesty_cli.commands.photos import _collect_images
        for name in ["p-10.jpg", "p-2.jpg", ".hidden.jpg", "notes.txt", "c.PNG"]:
            (tmp_path / name).write_bytes(b"x")
        files = _collect_images([str(tmp_path)])
        names = [os.path.basename(f) for f in files]
        assert names == ["c.PNG", "p-2.jpg", "p-10.jpg"]

    def test_collect_images_single_file(self, tmp_path):
        from guesty_cli.commands.photos import _collect_images
        f = tmp_path / "only.jpg"
        f.write_bytes(b"x")
        assert _collect_images([str(f)]) == [str(f)]

    def test_collect_images_empty_for_missing_or_imageless(self, tmp_path):
        from guesty_cli.commands.photos import _collect_images
        assert _collect_images([str(tmp_path / "does-not-exist")]) == []
        (tmp_path / "readme.txt").write_bytes(b"x")
        assert _collect_images([str(tmp_path)]) == []

    def test_order_by_source_name(self):
        # Highest-risk path: ordering is computed from the photos' source
        # filenames (natural sort), NOT the upload response's data[0].
        from guesty_cli.commands.photos import _order_by_source_name
        photos = [
            {"_id": "c", "source": "https://assets/x/Home-10-aaaa"},
            {"_id": "a", "source": "https://assets/x/Home-2-bbbb"},
            {"_id": "b", "source": "https://assets/x/Home-1-cccc"},
        ]
        assert _order_by_source_name(photos) == ["b", "a", "c"]
