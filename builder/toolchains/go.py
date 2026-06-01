"""Go toolchain: `go build`.

`-gcflags=all=-N -l` disables optimization and inlining so line tables and
locals are faithful (the Go analogue of -O0). Go embeds DWARF in the binary on
every platform; ELF separate-symbols is handled later by builder.symbols.
Android requires cgo + the NDK C compiler; WASM uses GOOS=wasip1.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..matrix import Config
from ..util import FIXTURES, ROOT, run
from . import BuildResult, ndk_clang


def build(config: Config, build_root: Path) -> BuildResult:
    out_dir = build_root / "go" / config.platform.id / config.symbols
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / config.artifact_name

    env = os.environ.copy()
    env.update({k: str(v) for k, v in config.platform.go.items()})  # GOOS/GOARCH

    if config.platform.kind == "android":
        # Android/Go needs cgo and an NDK C compiler.
        env["CGO_ENABLED"] = "1"
        env["CC"] = ndk_clang(config.platform)
    elif config.platform.kind == "wasm":
        env["CGO_ENABLED"] = "0"

    source = FIXTURES / config.source
    cmd = ["go", "build", "-gcflags=all=-N -l", "-o", out, source]
    run(cmd, env=env, cwd=ROOT)

    if not out.exists():
        raise FileNotFoundError(f"go build did not produce {out}")
    return BuildResult(binary=out)
