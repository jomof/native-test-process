"""Small shared helpers: repo paths, command execution, hashing, host info."""
from __future__ import annotations

import hashlib
import platform as _platform
import shutil
import subprocess
import sys
from pathlib import Path

# Repo root = parent of the builder/ package.
ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def log(msg: str) -> None:
    print(f"[builder] {msg}", flush=True)


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command, echoing it first. Raises on non-zero exit when check."""
    log("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        check=check,
        text=True,
        capture_output=capture,
    )


def which(name: str) -> str | None:
    return shutil.which(name)


def require_tool(*names: str) -> str:
    """Return the first tool found on PATH, or raise a clear error."""
    for name in names:
        found = which(name)
        if found:
            return found
    raise RuntimeError(f"None of these required tools are on PATH: {', '.join(names)}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def host_os() -> str:
    """Normalized host OS: linux | macos | windows."""
    system = _platform.system().lower()
    if system.startswith("darwin"):
        return "macos"
    if system.startswith("win"):
        return "windows"
    return "linux"


def host_arch() -> str:
    machine = _platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine


def rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def die(msg: str) -> None:
    print(f"[builder] error: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)
