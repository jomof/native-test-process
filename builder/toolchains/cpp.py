"""C++ toolchain: CMake + clang.

Using CMake (rather than a bare clang invocation) is deliberate: the produced
artifacts carry build-ids and -fdebug-prefix-map'd source paths, so they look
like real debuggees and exercise the consumer's source-path remapping. Android
and WASM go through their SDK toolchain files; everything else is a host build.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..matrix import Config
from ..util import ROOT, run, which
from . import BuildResult


def build(config: Config, build_root: Path) -> BuildResult:
    bdir = build_root / "cmake" / config.platform.id / config.symbols
    bdir.mkdir(parents=True, exist_ok=True)

    args = [
        "cmake",
        "-S", ROOT,
        "-B", bdir,
        "-DCMAKE_BUILD_TYPE=Debug",
        f"-DFIXTURE_SYMBOLS={config.symbols}",
    ]
    if which("ninja"):
        args += ["-G", "Ninja"]

    env = os.environ.copy()
    plat = config.platform
    if plat.kind == "android":
        args += [
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake' / 'toolchains' / 'android.cmake'}",
            f"-DANDROID_ABI={plat.android['abi']}",
            f"-DANDROID_PLATFORM=android-{plat.android['api']}",
        ]
    elif plat.kind == "wasm":
        args += [
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake' / 'toolchains' / 'wasi.cmake'}",
        ]
    else:
        # Prefer clang for predictable -fdebug-prefix-map / DWARF behaviour and
        # so Windows DWARF/PDB selection in CMakeLists works.
        cxx = os.environ.get("CXX") or which("clang++") or which("clang")
        if cxx:
            args.append(f"-DCMAKE_CXX_COMPILER={cxx}")

    run(args, env=env)
    run(["cmake", "--build", bdir, "--target", config.program], env=env)

    binary = _locate(bdir, config)
    sidecars: list[Path] = []
    if config.platform.object_format == "pe" and config.symbols == "separate":
        pdb = binary.with_suffix(".pdb")
        if pdb.exists():
            sidecars.append(pdb)
    return BuildResult(binary=binary, sidecars=sidecars)


def _locate(bdir: Path, config: Config) -> Path:
    """Find the built executable; CMake's output name depends on the platform."""
    candidates = [
        bdir / config.artifact_name,  # spin / spin.exe / spin.wasm
        bdir / config.program,
        bdir / f"{config.program}.wasm",
        bdir / f"{config.program}.exe",
        # Multi-config generators (avoided via Ninja, but be defensive).
        bdir / "Debug" / config.artifact_name,
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    # Last resort: recursive search for the target name.
    for found in bdir.rglob(config.program + "*"):
        if found.is_file() and found.suffix in ("", ".exe", ".wasm"):
            return found
    raise FileNotFoundError(
        f"could not find built {config.program} under {bdir}"
    )
