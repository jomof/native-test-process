"""Per-language build dispatch.

Each toolchain builds one configuration and returns a BuildResult pointing at
the freshly built primary artifact (with maximal native debug info) plus any
sidecars the *compiler* produced at build time (notably a Windows .pdb).
Symbol *placement* for ELF/Mach-O is finalized later in builder.symbols.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..matrix import Config, Platform
from ..util import host_os


@dataclass
class BuildResult:
    binary: Path
    sidecars: list[Path] = field(default_factory=list)


def build(config: Config, build_root: Path) -> BuildResult:
    from . import cpp, go, rust

    if config.language == "cpp":
        return cpp.build(config, build_root)
    if config.language == "rust":
        return rust.build(config, build_root)
    if config.language == "go":
        return go.build(config, build_root)
    raise ValueError(f"unknown language: {config.language}")


# --- Shared Android NDK helpers -------------------------------------------

def ndk_root() -> str:
    for var in ("ANDROID_NDK_HOME", "ANDROID_NDK_ROOT", "ANDROID_NDK"):
        value = os.environ.get(var)
        if value:
            return value
    raise RuntimeError(
        "Android build requires the NDK: set ANDROID_NDK_HOME to its install root."
    )


def ndk_host_tag() -> str:
    # The NDK ships prebuilt toolchains under a host tag; CI builds Android on
    # the linux runner, but support macOS hosts for local builds too.
    return "darwin-x86_64" if host_os() == "macos" else "linux-x86_64"


def ndk_bin() -> Path:
    return Path(ndk_root()) / "toolchains" / "llvm" / "prebuilt" / ndk_host_tag() / "bin"


def ndk_clang(platform: Platform) -> str:
    """Path to the NDK clang wrapper for this ABI+API (used as CC/linker)."""
    triple = platform.android["ndk_triple"]
    api = platform.android["api"]
    suffix = ".cmd" if host_os() == "windows" else ""
    return str(ndk_bin() / f"{triple}{api}-clang{suffix}")
