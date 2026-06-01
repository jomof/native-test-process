"""Rust toolchain: cargo.

Always builds with an explicit --target (even for the host) so the output path
is uniform: target/<triple>/debug/<bin>. The dev profile (opt-level=0,
debug=2) lives in Cargo.toml. WASM drops the default `threads` feature; Android
points cargo at the NDK clang as linker.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..matrix import Config
from ..util import ROOT, run
from . import BuildResult, ndk_clang


def build(config: Config, build_root: Path) -> BuildResult:
    triple = config.platform.rust_target
    if not triple:
        raise RuntimeError(f"platform {config.platform.id} has no rust_target")

    cmd = ["cargo", "build", "--bin", config.program, "--target", triple]
    if config.platform.kind == "wasm":
        cmd.append("--no-default-features")  # no std::thread on wasm32-wasip1

    env = os.environ.copy()
    if config.platform.kind == "android":
        _set_android_env(env, config)

    run(cmd, env=env, cwd=ROOT)

    out_dir = ROOT / "target" / triple / "debug"
    binary = out_dir / _bin_name(config)
    if not binary.exists():
        raise FileNotFoundError(f"cargo did not produce {binary}")

    sidecars: list[Path] = []
    if config.platform.object_format == "pe":
        pdb = out_dir / f"{config.program}.pdb"
        if pdb.exists():
            sidecars.append(pdb)
    return BuildResult(binary=binary, sidecars=sidecars)


def _bin_name(config: Config) -> str:
    fmt = config.platform.object_format
    if fmt == "pe":
        return f"{config.program}.exe"
    if fmt == "wasm":
        return f"{config.program}.wasm"
    return config.program


def _set_android_env(env: dict, config: Config) -> None:
    """Tell cargo to link with the NDK clang for this target triple."""
    triple = config.platform.rust_target
    linker = ndk_clang(config.platform)
    key = "CARGO_TARGET_" + triple.upper().replace("-", "_") + "_LINKER"
    env[key] = linker
    env[f"CC_{triple}"] = linker
