"""Build dist/manifest.json by reading back every zip in dist/.

The manifest is the single index a consumer downloads first: it lists every
published configuration with its zip name, size, and checksum, so the consumer
can pick a config, fetch `<release_base>/<release_tag>/<zip>`, and verify it.
Generating it from the zips (rather than from the in-memory build) means the
release job can merge artifacts uploaded by several runners and still produce
one correct manifest.
"""
from __future__ import annotations

import datetime as _dt
import json
import zipfile
from pathlib import Path

from .util import DIST, sha256


def _read_fixture_json(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("fixture.json") as f:
            return json.load(f)


def build(dist_dir: Path | None = None, release_tag: str | None = None) -> dict:
    dist_dir = dist_dir or DIST
    zips = sorted(p for p in dist_dir.glob("*.zip"))
    configurations = []
    tag = release_tag
    for zip_path in zips:
        meta = _read_fixture_json(zip_path)
        tag = tag or meta.get("release_tag")
        configurations.append(
            {
                "id": meta["id"],
                "zip": zip_path.name,
                "size": zip_path.stat().st_size,
                "sha256": sha256(zip_path),
                "program": meta["program"],
                "language": meta["language"],
                "platform": meta["platform"],
                "os": meta["os"],
                "arch": meta["arch"],
                "kind": meta["kind"],
                "object_format": meta["object_format"],
                "symbols": meta["symbols"],
                "primary": meta["primary"],
            }
        )

    manifest = {
        "schema": 1,
        "release_tag": tag,
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "count": len(configurations),
        "configurations": configurations,
    }
    return manifest


def write(dist_dir: Path | None = None, release_tag: str | None = None) -> Path:
    dist_dir = dist_dir or DIST
    manifest = build(dist_dir, release_tag)
    out = dist_dir / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out
