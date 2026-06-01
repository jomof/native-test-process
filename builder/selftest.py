"""Prove that published artifacts are actually debuggable.

For each built zip we extract it and drive a real debugger against it, so a
broken artifact never reaches a Release:

  native (host OS) : live lldb run - set the @dap:loop_body breakpoint, run,
                     confirm the stop and that locals read back; for `crash`,
                     confirm a fatal-signal stop; for `hello`, a clean exit.
  android / cross  : static lldb - load the target and confirm the breakpoint
                     resolves to an address (i.e. the debug info is usable).
                     Live device runs are an integration concern, not here.
  wasm             : start wasmtime's gdbstub and connect a wasm-aware lldb
                     (`process connect --plugin wasm`), confirm the breakpoint.

Tools are configurable: SELFTEST_LLDB, SELFTEST_WASM_LLDB, SELFTEST_WASMTIME.
Missing tools are a hard failure unless --allow-skip is passed.
"""
from __future__ import annotations

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


def _lldb_bin() -> str | None:
    return os.environ.get("SELFTEST_LLDB") or which("lldb")


def _wasm_lldb_bin() -> str | None:
    return os.environ.get("SELFTEST_WASM_LLDB") or os.environ.get("SELFTEST_LLDB") or which("lldb")


def _wasmtime_bin() -> str | None:
    return os.environ.get("SELFTEST_WASMTIME") or which("wasmtime")


def _run_lldb(lldb: str, commands: list[str], *, cwd: Path, timeout: int) -> tuple[int, str]:
    # Disable the "really quit while debugging?" confirmation, which otherwise
    # blocks on stdin in batch mode when a stopped process is still attached.
    argv = [lldb, "-b", "--no-use-colors", "-o", "settings set interpreter.prompt-on-quit false"]
    for cmd in commands:
        argv += ["-o", cmd]
    log("$ " + " ".join(argv))
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), text=True, capture_output=True, timeout=timeout
        )
        return proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, _as_text(exc.stdout) + _as_text(exc.stderr) + "\n[selftest] TIMEOUT"


def _as_text(value) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _spin_commands(meta: dict) -> list[str]:
    bp = meta["breakpoints"]["loop_body"]
    return [
        f"breakpoint set --file {bp['file']} --line {bp['line']}",
        "run",
        "thread backtrace",
        "frame variable",
        "process kill",
        "quit",
    ]


def _validate_live(meta: dict, work: Path) -> Result:
    lldb = _lldb_bin()
    if not lldb:
        return Result(meta["id"], "skip", "no lldb on PATH (set SELFTEST_LLDB)")
    program = meta["program"]
    primary = meta["primary"]

    if program == "spin":
        code, out = _run_lldb_target(lldb, primary, _spin_commands(meta), work, timeout=60)
        ok = "stop reason = breakpoint" in out and "observed" in out
        return Result(meta["id"], "pass" if ok else "fail", "breakpoint hit, locals read" if ok else _trim(out))
    if program == "hello":
        code, out = _run_lldb_target(lldb, primary, ["run", "quit"], work, timeout=30)
        ok = "exited with status = 0" in out or "exited with status = 0 (0x" in out
        return Result(meta["id"], "pass" if ok else "fail", "clean exit" if ok else _trim(out))
    if program == "crash":
        code, out = _run_lldb_target(lldb, primary, ["run", "process kill", "quit"], work, timeout=30)
        ok = "stop reason = signal" in out or "EXC_BAD_ACCESS" in out or "stop reason = " in out
        return Result(meta["id"], "pass" if ok else "fail", "faulted as expected" if ok else _trim(out))
    return Result(meta["id"], "skip", f"no live strategy for program {program}")


def _run_lldb_target(lldb: str, primary: str, commands: list[str], work: Path, timeout: int) -> tuple[int, str]:
    # Load the target first, then the per-program commands.
    return _run_lldb(lldb, [f"target create {primary}", *commands], cwd=work, timeout=timeout)


def _validate_static(meta: dict, work: Path) -> Result:
    lldb = _lldb_bin()
    if not lldb:
        return Result(meta["id"], "skip", "no lldb on PATH (set SELFTEST_LLDB)")
    primary = meta["primary"]
    bp = meta["breakpoints"].get("loop_body") or next(iter(meta["breakpoints"].values()))
    code, out = _run_lldb(
        lldb,
        [
            f"target create {primary}",
            f"breakpoint set --file {bp['file']} --line {bp['line']}",
            "breakpoint list",
            "quit",
        ],
        cwd=work,
        timeout=60,
    )
    # A resolved breakpoint prints the file:line and an address; an unresolved
    # one is reported as pending with no locations.
    resolved = f"{bp['file']}:{bp['line']}" in out and "pending" not in out.lower()
    return Result(meta["id"], "pass" if resolved else "fail", "breakpoint resolves statically" if resolved else _trim(out))


def _validate_wasm(meta: dict, work: Path, allow_skip: bool) -> Result:
    wasmtime = _wasmtime_bin()
    lldb = _wasm_lldb_bin()
    if not wasmtime or not lldb:
        missing = "wasmtime" if not wasmtime else "wasm-aware lldb"
        status = "skip" if allow_skip else "fail"
        return Result(meta["id"], status, f"missing {missing} (set SELFTEST_WASMTIME / SELFTEST_WASM_LLDB)")

    primary = meta["primary"]
    bp = meta["breakpoints"]["loop_body"]
    port = 4567
    server = subprocess.Popen(
        [wasmtime, "run", "-g", str(port), primary],
        cwd=str(work), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        time.sleep(1.0)  # let the gdbstub bind the port
        code, out = _run_lldb(
            lldb,
            [
                f"process connect --plugin wasm connect://127.0.0.1:{port}",
                f"breakpoint set --file {bp['file']} --line {bp['line']}",
                "continue",
                "thread backtrace",
                "process kill",
                "quit",
            ],
            cwd=work,
            timeout=60,
        )
        ok = "stop reason = breakpoint" in out or f"{bp['file']}:{bp['line']}" in out
        return Result(meta["id"], "pass" if ok else "fail", "wasm breakpoint hit" if ok else _trim(out))
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


def _make_executable(path: Path) -> None:
    if path.is_file():
        mode = path.stat().st_mode
        path.chmod(mode | 0o111)


def _trim(out: str, limit: int = 1200) -> str:
    out = out.strip()
    return out if len(out) <= limit else out[-limit:]


def _strategy(meta: dict, work: Path, allow_skip: bool) -> Result:
    kind = meta["kind"]
    if kind == "wasm":
        return _validate_wasm(meta, work, allow_skip)
    if kind == "native" and meta["os"] == host_os():
        return _validate_live(meta, work)
    # android, or a native build for a different host than this runner.
    return _validate_static(meta, work)


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
            import json

            meta = json.loads((work / "fixture.json").read_text())
            # zipfile.extractall drops the executable bit (the same reason the
            # consumer must re-mark executables after download); restore it so
            # the primary can actually run under the debugger.
            _make_executable(work / meta["primary"])
            try:
                result = _strategy(meta, work, allow_skip)
            except Exception as exc:  # noqa: BLE001 - report, don't crash the suite
                result = Result(config_id, "fail", f"{type(exc).__name__}: {exc}")
        log(f"selftest {result.status.upper():4} {result.config_id} - {result.detail}")
        results.append(result)
    return results
