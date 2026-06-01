"""Load matrix.toml and expand it into the concrete set of configurations.

A configuration is `program x language x platform x symbols`, pruned by the
capability rules in `supported_symbol_modes` (which encode hard platform
truths, e.g. WASM has no separate-symbols mode, clang on Mach-O ships debug
info only as a .dSYM, and Go on Mach-O embeds DWARF in the binary).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .util import ROOT


@dataclass(frozen=True)
class Platform:
    id: str
    os: str
    arch: str
    kind: str  # native | android | wasm
    runner: str
    object_format: str  # elf | macho | pe | wasm
    rust_target: str | None = None
    go: dict = field(default_factory=dict)
    android: dict | None = None
    wasi: dict | None = None


@dataclass(frozen=True)
class Config:
    program: str
    description: str
    language: str  # cpp | rust | go
    platform: Platform
    symbols: str  # embedded | separate
    source: str  # path relative to fixtures/

    @property
    def id(self) -> str:
        return f"{self.program}-{self.platform.id}-{self.language}-{self.symbols}"

    @property
    def artifact_name(self) -> str:
        """Canonical filename of the primary artifact inside the zip."""
        fmt = self.platform.object_format
        if fmt == "pe":
            return f"{self.program}.exe"
        if fmt == "wasm":
            return f"{self.program}.wasm"
        return self.program

    @property
    def source_name(self) -> str:
        return Path(self.source).name


@dataclass
class Matrix:
    release_tag: str
    languages: list[str]
    symbols: list[str]
    programs: dict[str, dict]
    platforms: list[Platform]


def load(path: Path | None = None) -> Matrix:
    path = path or (ROOT / "matrix.toml")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    platforms = [Platform(**entry) for entry in data["platforms"]]
    return Matrix(
        release_tag=data["release_tag"],
        languages=list(data["languages"]),
        symbols=list(data["symbols"]),
        programs=dict(data["programs"]),
        platforms=platforms,
    )


def supported_symbol_modes(language: str, object_format: str) -> list[str]:
    """Which symbol modes are physically meaningful for this lang+format.

    These are not policy choices; they reflect how each toolchain emits debug
    info. Shipping a mode that can't actually be debugged would be worse than
    omitting it, so the matrix prunes here.
    """
    if object_format == "wasm":
        # DWARF is embedded in the .wasm; there is no sidecar convention.
        return ["embedded"]
    if object_format == "elf":
        # objcopy can split any ELF (incl. Go and cross targets) cleanly.
        return ["embedded", "separate"]
    if object_format == "macho":
        # clang/rustc on Mach-O keep DWARF in .o files (debug map); the only
        # portable, relocatable form is a .dSYM => separate-only. Go's linker,
        # by contrast, writes a __DWARF segment into the binary => embedded.
        return ["embedded"] if language == "go" else ["separate"]
    if object_format == "pe":
        if language == "cpp":
            return ["embedded", "separate"]  # clang -gdwarf vs CodeView+PDB
        if language == "rust":
            return ["separate"]  # MSVC toolchain emits a .pdb sidecar
        return ["embedded"]  # Go links DWARF into the PE
    return ["embedded"]


def expand(
    matrix: Matrix,
    *,
    programs: list[str] | None = None,
    languages: list[str] | None = None,
    platforms: list[str] | None = None,
    symbols: list[str] | None = None,
    runners: list[str] | None = None,
) -> list[Config]:
    """Expand the matrix into configs, applying optional filters."""
    configs: list[Config] = []
    for pname, pinfo in matrix.programs.items():
        if programs and pname not in programs:
            continue
        sources = pinfo.get("sources", {})
        for lang in matrix.languages:
            if languages and lang not in languages:
                continue
            src = sources.get(lang)
            if not src:
                continue
            for plat in matrix.platforms:
                if platforms and plat.id not in platforms:
                    continue
                if runners and plat.runner not in runners:
                    continue
                allowed = supported_symbol_modes(lang, plat.object_format)
                for sym in matrix.symbols:
                    if sym not in allowed:
                        continue
                    if symbols and sym not in symbols:
                        continue
                    configs.append(
                        Config(
                            program=pname,
                            description=pinfo.get("description", ""),
                            language=lang,
                            platform=plat,
                            symbols=sym,
                            source=src,
                        )
                    )
    return configs
