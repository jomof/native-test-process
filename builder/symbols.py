"""Finalize symbol placement and stage the files that go into a config's zip.

Given a freshly built binary, produce the staged file set honoring the config's
symbols mode:

  embedded  -> the primary artifact, debug info left inside it.
  separate  -> the primary artifact plus a detached debug sidecar:
                 ELF    : `<name>.debug` (objcopy --only-keep-debug + debuglink)
                 Mach-O : `<name>.dSYM`  (dsymutil)
                 PE     : `<name>.pdb`   (already emitted by the compiler)

WASM is embedded-only. The capability rules in matrix.supported_symbol_modes
guarantee we never reach an impossible combination here.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .matrix import Config
from .toolchains import BuildResult
from .util import log, run, which


@dataclass
class Staged:
    primary: str  # filename of the primary artifact within stage_dir
    files: list[str] = field(default_factory=list)  # all files to include in the zip
    debug: list[str] = field(default_factory=list)  # the detached debug file(s), if any


def finalize(config: Config, built: BuildResult, stage_dir: Path) -> Staged:
    stage_dir.mkdir(parents=True, exist_ok=True)
    primary = stage_dir / config.artifact_name
    shutil.copy2(built.binary, primary)

    staged = Staged(primary=primary.name, files=[primary.name])

    if config.symbols == "embedded":
        return staged

    fmt = config.platform.object_format
    if fmt == "elf":
        _split_elf(config, primary, staged)
    elif fmt == "macho":
        _split_macho(primary, staged)
    elif fmt == "pe":
        _collect_pdb(built, stage_dir, staged)
    else:
        raise RuntimeError(f"no separate-symbols path for object format {fmt}")
    return staged


def _resolve_objcopy() -> str:
    # llvm-objcopy handles every target (incl. cross/Android ELF); prefer it.
    for name in (os.environ.get("OBJCOPY"), "llvm-objcopy", "objcopy"):
        if name and which(name):
            return name  # type: ignore[return-value]
    raise RuntimeError("need llvm-objcopy or objcopy on PATH for ELF symbol split")


def _split_elf(config: Config, primary: Path, staged: Staged) -> None:
    objcopy = _resolve_objcopy()
    debug_name = primary.name + ".debug"
    cwd = primary.parent
    # Run inside the stage dir so --add-gnu-debuglink stores a bare basename,
    # which is what the debugger looks for next to the binary.
    run([objcopy, "--only-keep-debug", primary.name, debug_name], cwd=cwd)
    run([objcopy, "--strip-debug", primary.name], cwd=cwd)
    run([objcopy, f"--add-gnu-debuglink={debug_name}", primary.name], cwd=cwd)
    staged.files.append(debug_name)
    staged.debug.append(debug_name)


def _split_macho(primary: Path, staged: Staged) -> None:
    dsymutil = os.environ.get("DSYMUTIL") or which("dsymutil")
    if not dsymutil:
        raise RuntimeError("need dsymutil on PATH for Mach-O .dSYM generation")
    dsym = primary.parent / (primary.name + ".dSYM")
    run([dsymutil, primary.name, "-o", dsym.name], cwd=primary.parent)
    # Strip debug from the binary so the artifact is genuinely "separate".
    strip = which("strip")
    if strip:
        run([strip, "-S", primary.name], cwd=primary.parent, check=False)
    # The .dSYM is a directory bundle; pack.py walks it.
    staged.files.append(dsym.name)
    staged.debug.append(dsym.name)


def _collect_pdb(built: BuildResult, stage_dir: Path, staged: Staged) -> None:
    pdbs = [s for s in built.sidecars if s.suffix == ".pdb"]
    if not pdbs:
        log("warning: PE separate-symbols build produced no .pdb sidecar")
        return
    for pdb in pdbs:
        dest = stage_dir / pdb.name
        shutil.copy2(pdb, dest)
        staged.files.append(dest.name)
        staged.debug.append(dest.name)
