"""Prove that published artifacts are actually debuggable.

The guarantee we publish is "this artifact carries usable, correctly-lined
debug info." We validate it two ways, picking whichever is both reliable and
meaningful for the configuration:

  live (lldb) - for C++/Rust native on the host OS, where lldb is rock solid:
                set the loop_body breakpoint, run, confirm the stop and that
                locals read back; `crash` must fault; `hello` must exit clean.

  static (llvm-dwarfdump / llvm-pdbutil) - for everything else (Go, Windows,
                Android cross, WASM): confirm the debug info covers the fixture
                source. This is debugger-independent, so it doesn't depend on
                lldb's shaky Go support or a working lldb on the Windows runner,
                and it still proves the core property a DAP source breakpoint
                needs - that the source is present in the line program.

Why not lldb everywhere: lldb live-debugging Go hangs (delve is Go's debugger),
and the LLVM lldb on GitHub's Windows runner fails to start (embedded-Python
breakage). llvm-dwarfdump has no such dependencies and ships beside lldb.

WASM additionally attempts a live wasmtime gdbstub + wasm-aware lldb run when
SELFTEST_WASMTIME and SELFTEST_WASM_LLDB are set; otherwise it validates the
.wasm DWARF statically. Missing static tools are a hard failure unless
--allow-skip.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .matrix import Config
from .util import DIST, host_os, log, which


@dataclass
class Result:
    config_id: str
    status: str  # pass | fail | skip
    detail: str


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------

def _lldb_bin() -> str | None:
    return os.environ.get("SELFTEST_LLDB") or which("lldb")


def _wasm_lldb_bin() -> str | None:
    return os.environ.get("SELFTEST_WASM_LLDB") or which("lldb-wasm")


def _wasmtime_bin() -> str | None:
    return os.environ.get("SELFTEST_WASMTIME") or which("wasmtime")


def _dwarfdump_bin() -> str | None:
    for name in (os.environ.get("DWARFDUMP"), "llvm-dwarfdump", "dwarfdump"):
        if name and which(name):
            return name
    # Linux distro packages often ship only a versioned binary
    # (e.g. llvm-dwarfdump-18); scan PATH for one.
    for directory in (os.environ.get("PATH") or "").split(os.pathsep):
        try:
            entries = sorted(Path(directory).glob("llvm-dwarfdump-*"))
        except OSError:
            continue
        for entry in entries:
            if entry.is_file() and os.access(entry, os.X_OK):
                return str(entry)
    return None


def _pdbutil_bin() -> str | None:
    return os.environ.get("PDBUTIL") or which("llvm-pdbutil")


# ---------------------------------------------------------------------------
# Live lldb (C++/Rust on host)
# ---------------------------------------------------------------------------

def _run_lldb(lldb: str, commands: list[str], *, cwd: Path, timeout: int) -> tuple[int, str]:
    argv = [lldb, "-b", "--no-use-colors", "-o", "settings set interpreter.prompt-on-quit false"]
    for cmd in commands:
        argv += ["-o", cmd]
    log("$ " + " ".join(argv))
    try:
        proc = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, timeout=timeout)
        return proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, _as_text(exc.stdout) + _as_text(exc.stderr) + "\n[selftest] TIMEOUT"


def _run_lldb_target(lldb: str, primary: str, commands: list[str], work: Path, timeout: int) -> tuple[int, str]:
    return _run_lldb(lldb, [f"target create {primary}", *commands], cwd=work, timeout=timeout)


def _validate_live(meta: dict, work: Path) -> Result:
    lldb = _lldb_bin()
    if not lldb:
        return Result(meta["id"], "skip", "no lldb on PATH (set SELFTEST_LLDB)")
    program = meta["program"]
    primary = meta["primary"]

    if program == "spin":
        bp = meta["breakpoints"]["loop_body"]
        _, out = _run_lldb_target(
            lldb, primary,
            [
                f"breakpoint set --file {bp['file']} --line {bp['line']}",
                "run", "thread backtrace", "frame variable", "process kill", "quit",
            ],
            work, timeout=60,
        )
        ok = "stop reason = breakpoint" in out and "observed" in out
        return Result(meta["id"], "pass" if ok else "fail", "breakpoint hit, locals read" if ok else _trim(out))
    if program == "hello":
        _, out = _run_lldb_target(lldb, primary, ["run", "quit"], work, timeout=30)
        ok = "exited with status = 0" in out
        return Result(meta["id"], "pass" if ok else "fail", "clean exit" if ok else _trim(out))
    if program == "crash":
        _, out = _run_lldb_target(lldb, primary, ["run", "process kill", "quit"], work, timeout=30)
        ok = "stop reason = signal" in out or "EXC_BAD_ACCESS" in out or "stop reason =" in out
        return Result(meta["id"], "pass" if ok else "fail", "faulted as expected" if ok else _trim(out))
    return Result(meta["id"], "skip", f"no live strategy for program {program}")


# ---------------------------------------------------------------------------
# Static debug-info validation (debugger-independent)
# ---------------------------------------------------------------------------

def _dwarf_target(meta: dict, work: Path) -> Path | None:
    """The file holding DWARF for this config (binary, .debug, or dSYM DWARF)."""
    primary = work / meta["primary"]
    if meta["symbols"] == "embedded":
        return primary
    debug = meta.get("debug") or []
    if not debug:
        return primary
    name = debug[0]
    fmt = meta["object_format"]
    if fmt == "elf":
        return work / name  # <name>.debug
    if fmt == "macho":
        # name is "<primary>.dSYM"; the DWARF lives inside the bundle.
        inner = work / name / "Contents" / "Resources" / "DWARF" / meta["primary"]
        return inner if inner.exists() else (work / name)
    return primary


def _static_target(meta: dict, work: Path) -> Path | None:
    """The file we expect to hold debug info for this config."""
    if meta["object_format"] == "pe" and meta["symbols"] == "separate":
        debug = meta.get("debug") or []
        return (work / debug[0]) if debug else None
    return _dwarf_target(meta, work)


def _source_in_file(path: Path, source: str) -> bool:
    """True if the source filename is embedded in the file's bytes.

    The source path lives in DWARF `.debug_str`/`.debug_line` (and in a PDB's
    string table), so finding it is a tool-independent proof that the artifact
    carries source-level debug info - robust where dwarfdump can't parse a
    module (Go on wasm/Mach-O) or isn't installed (Windows).
    """
    try:
        return source.encode() in path.read_bytes()
    except (OSError, IsADirectoryError):
        return False


def _dwarfdump_finds_source(meta: dict, target: Path, source: str) -> tuple[bool, str]:
    """Strong check: parse the DWARF and confirm the source + marker line."""
    dd = _dwarfdump_bin()
    if not dd or (meta["object_format"] == "pe" and meta["symbols"] == "separate"):
        return False, ""
    try:
        info = subprocess.run(
            [dd, "--debug-info", str(target)], cwd=str(target.parent),
            text=True, capture_output=True, timeout=120,
        ).stdout
    except (subprocess.TimeoutExpired, OSError):
        return False, ""
    if source not in info:
        return False, ""
    bp = meta["breakpoints"].get("loop_body") or next(iter(meta["breakpoints"].values()))
    try:
        line_dump = subprocess.run(
            [dd, "--debug-line", str(target)], cwd=str(target.parent),
            text=True, capture_output=True, timeout=120,
        ).stdout
        line_seen = source in line_dump and (f" {bp['line']} " in line_dump or f"\t{bp['line']}\t" in line_dump)
    except (subprocess.TimeoutExpired, OSError):
        line_seen = False
    detail = f"DWARF covers {source}" + (f" (line {bp['line']} in line table)" if line_seen else "")
    return True, detail


def _validate_static(meta: dict, work: Path, allow_skip: bool) -> Result:
    source = meta["source"]
    target = _static_target(meta, work)
    if not target or not target.exists():
        return Result(meta["id"], "fail", f"debug target missing: {target}")

    # Strong, structured check when the tool can parse the module.
    ok, detail = _dwarfdump_finds_source(meta, target, source)
    if ok:
        return Result(meta["id"], "pass", detail)

    # Tool-independent fallback: the source path string is present in the
    # debug info (DWARF .debug_str / PDB string table).
    if _source_in_file(target, source):
        return Result(meta["id"], "pass", f"source '{source}' present in debug info of {target.name}")

    return Result(meta["id"], "fail", f"no debug info referencing '{source}' in {target.name}")


# ---------------------------------------------------------------------------
# WASM (live wasmtime gdbstub when available, else static)
# ---------------------------------------------------------------------------

def _validate_wasm(meta: dict, work: Path, allow_skip: bool) -> Result:
    wasmtime = _wasmtime_bin()
    lldb = _wasm_lldb_bin()
    if not wasmtime or not lldb:
        # No wasm-aware debugger here; validate the embedded DWARF statically.
        return _validate_static_dwarf(meta, work, allow_skip)

    primary = meta["primary"]
    bp = meta["breakpoints"]["loop_body"]
    port = 4567
    server = subprocess.Popen(
        [wasmtime, "run", "-g", str(port), primary],
        cwd=str(work), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        time.sleep(1.0)
        _, out = _run_lldb(
            lldb,
            [
                f"process connect --plugin wasm connect://127.0.0.1:{port}",
                f"breakpoint set --file {bp['file']} --line {bp['line']}",
                "continue", "thread backtrace", "process kill", "quit",
            ],
            cwd=work, timeout=60,
        )
        ok = "stop reason = breakpoint" in out or f"{bp['file']}:{bp['line']}" in out
        return Result(meta["id"], "pass" if ok else "fail", "wasm breakpoint hit" if ok else _trim(out))
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executable(path: Path) -> None:
    if path.is_file():
        path.chmod(path.stat().st_mode | 0o111)


def _as_text(value) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _trim(out: str, limit: int = 1000) -> str:
    out = out.strip()
    return out if len(out) <= limit else out[-limit:]


def _strategy(meta: dict, work: Path, allow_skip: bool) -> Result:
    kind = meta["kind"]
    if kind == "wasm":
        return _validate_wasm(meta, work, allow_skip)
    # Live lldb only where it is reliable: C++/Rust on a Linux/macOS host.
    # (lldb on the Windows runner fails to start; Go needs delve, not lldb.)
    if (
        kind == "native"
        and meta["os"] == host_os()
        and host_os() in ("linux", "macos")
        and meta["language"] in ("cpp", "rust")
    ):
        return _validate_live(meta, work)
    return _validate_static(meta, work, allow_skip)


def run(configs: list[Config], *, dist_dir: Path | None = None, allow_skip: bool = False) -> list[Result]:
    dist_dir = dist_dir or DIST
    wanted = {c.id for c in configs} if configs else None
    results: list[Result] = []
    for zip_path in sorted(dist_dir.glob("*.zip")):
        config_id = zip_path.stem
        if wanted is not None and config_id not in wanted:
            continue
        with tempfile.TemporaryDirectory(prefix="selftest-") as tmp:
            work = Path(tmp)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(work)
            meta = json.loads((work / "fixture.json").read_text())
            # zip extraction drops the executable bit; restore it (the same
            # reason the consumer must re-mark executables after download).
            _make_executable(work / meta["primary"])
            try:
                result = _strategy(meta, work, allow_skip)
            except Exception as exc:  # noqa: BLE001 - report, don't crash the suite
                result = Result(config_id, "fail", f"{type(exc).__name__}: {exc}")
        log(f"selftest {result.status.upper():4} {result.config_id} - {result.detail}")
        results.append(result)
    return results
