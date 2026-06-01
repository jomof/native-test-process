"""Assemble one downloadable zip per configuration.

Each zip contains the primary artifact, any detached debug file(s), the
fixture source (so the debugger can show it), and a self-describing
fixture.json: identity, resolved @dap breakpoint lines, a run/attach recipe,
and per-file checksums. The aggregate manifest (manifest.py) is built later by
reading these zips back.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from . import __version__
from .markers import extract
from .matrix import Config
from .symbols import Staged
from .util import DIST, FIXTURES, sha256


def _debug_recipe(config: Config) -> dict:
    artifact = config.artifact_name
    kind = config.platform.kind
    if kind == "android":
        abi = config.platform.android["abi"]
        return {
            "type": "remote-android",
            "abi": abi,
            "steps": [
                f"adb push {artifact} /data/local/tmp/{artifact}",
                "adb push <lldb-server> /data/local/tmp/lldb-server",
                "adb shell /data/local/tmp/lldb-server platform --listen '*:1234' --server &",
                "adb forward tcp:1234 tcp:1234",
                "lldb-dap (attach) attachCommands: ["
                "'platform select remote-android',"
                "'platform connect connect://127.0.0.1:1234',"
                f"'file /data/local/tmp/{artifact}','run']",
            ],
            "requires": "lldb-server matching the device ABI on the device; lldb-dap on the host",
        }
    if kind == "wasm":
        return {
            "type": "wasm",
            "steps": [
                f"wasmtime run -g 1234 {artifact}",
                "lldb: process connect --plugin wasm connect://127.0.0.1:1234",
            ],
            "requires": "wasm-aware lldb (LLVM v32+/wasi-sdk) and a wasmtime built with the gdbstub feature",
            "alt_native": f"lldb -- wasmtime run -D debug-info {artifact}  (debug the JIT-compiled native; flaky)",
        }
    return {
        "type": "local",
        "launch": {"program": artifact},
        "note": "Launch directly under lldb-dap (request=launch) or attach to a running instance.",
    }


def _default_argv(config: Config) -> list[str]:
    if config.program == "crash":
        return ["--mode=segv"]
    return []


def build_fixture_json(config: Config, staged: Staged, stage_dir: Path, release_tag: str) -> dict:
    source = FIXTURES / config.source
    markers = extract(source)
    breakpoints = {name: {"file": config.source_name, "line": line} for name, line in markers.items()}

    files: list[dict] = []
    for name in [*staged.files, config.source_name]:
        path = stage_dir / name
        if path.is_dir():
            files.append({"name": name, "kind": "directory"})
        elif path.is_file():
            files.append({"name": name, "kind": "file", "size": path.stat().st_size, "sha256": sha256(path)})

    return {
        "schema": 1,
        "builder_version": __version__,
        "id": config.id,
        "release_tag": release_tag,
        "program": config.program,
        "description": config.description,
        "language": config.language,
        "platform": config.platform.id,
        "os": config.platform.os,
        "arch": config.platform.arch,
        "kind": config.platform.kind,
        "object_format": config.platform.object_format,
        "symbols": config.symbols,
        "primary": staged.primary,
        "debug": staged.debug,
        "source": config.source_name,
        "markers": markers,
        "breakpoints": breakpoints,
        "run": {"argv": _default_argv(config), "cwd": "."},
        "debug_recipe": _debug_recipe(config),
        "files": files,
    }


def pack(config: Config, staged: Staged, stage_dir: Path, release_tag: str, dist_dir: Path | None = None) -> Path:
    dist_dir = dist_dir or DIST
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Stage the source next to the artifacts, then write fixture.json.
    source = FIXTURES / config.source
    (stage_dir / config.source_name).write_bytes(source.read_bytes())
    meta = build_fixture_json(config, staged, stage_dir, release_tag)
    (stage_dir / "fixture.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    zip_path = dist_dir / f"{config.id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(stage_dir.rglob("*")):
            if entry.is_file():
                zf.write(entry, entry.relative_to(stage_dir).as_posix())
    return zip_path
