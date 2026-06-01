# DAP test catalogue

The DAP behaviours these fixtures are designed to exercise, and which
fixture + `@dap` marker serves each. The consumer references breakpoints by
marker name via `fixture.json["breakpoints"][<marker>]` (file + resolved
line), never by a hard-coded line.

## Markers

| Fixture | Marker | Where | Serves |
|---------|--------|-------|--------|
| hello | `hello` | the single `print` line | launch, output, exit, terminate |
| spin | `global` | `g_ticks` global declaration | data/watchpoints, global eval |
| spin | `recurse_base` | `descend()` base case | deep stackTrace, step-out |
| spin | `step_into` | `doubler()` body | step-in, stepInTargets |
| spin | `step_over` | call to `doubler()` in `step_demo()` | step-over |
| spin | `loop_body` | per-iteration statement before the print | breakpoints, pause/resume, variables |
| crash | `before_crash` | null-deref store (segv) | exception / stop-on-signal |
| crash | `before_crash_abort` | `abort()` (C++/Rust) | abort handling |
| crash | `before_crash_div` | divide-by-zero | SIGFPE / divide-by-zero stop |

## Lifecycle / flow

- **launch** (request=launch) and **attach** to a running process — `hello`,
  `spin`.
- **stopOnEntry** then `configurationDone` — any fixture.
- **terminate / disconnect** semantics, **restart** — `spin` (long-running).
- **output events** (stdout/stderr forwarding, exit code) — `hello`, `spin`.

## Breakpoints

- **source breakpoints** at a marker line — `spin@loop_body` (hit every
  iteration; the classic pause/resume and mid-session-install case).
- **function breakpoints** by symbol — `descend`, `doubler`.
- **conditional breakpoints** — `spin@loop_body` with `counter == 5`.
- **hit-count breakpoints** — `spin@loop_body` with hit count N.
- **logpoints** — `spin@loop_body` logging `{counter}`.
- **breakpoints on stripped binaries** — any `*-separate` after detaching, and
  the future "no-debug" dimension (function/address breakpoints only).
- **mid-session breakpoint install while running** — `spin` (the motivating
  bug behind the consumer's synthetic-pause wrapper).

## Execution control

- **pause / continue** repeatedly — `spin`.
- **step over / into / out** — `spin@step_over`, `spin@step_into`,
  `spin@recurse_base` (step out of deep recursion).
- **stepInTargets / smart step-into** — `spin@step_over` (choose `doubler`).
- **goto / jump** — `spin` loop body.
- **reverse-continue / reverse-step** — future, against `rr` (native) or
  wasmtime record/replay (wasm).

## State inspection

- **stackTrace** incl. depth and paging — `spin@recurse_base` (depth ~5+
  frames), worker-thread stacks.
- **scopes + variables** across types — `spin@loop_body` exposes int, double,
  string, fixed array, struct (`Point`), pointer; nested/structured variables.
- **memory read / `readMemory`** — `spin` array and struct addresses.
- **setVariable / setExpression** — `spin@loop_body` locals.
- **evaluate** in watch / repl / hover contexts — `spin` locals and `g_ticks`.
- **data / watchpoints** — `spin@global` on `g_ticks` (mutated every tick by
  main + workers).
- **completions** — repl completion against `spin` symbols.

## Threads

- **threads list > 1** — `spin` spawns two workers (except single-threaded
  WASM/`FIXTURE_SINGLE_THREADED`).
- **per-thread stepping / freezing**, **thread-specific stops** — `spin`.

## Low level

- **disassembly** + **instruction stepping** — any fixture; WASM exercises
  Wasm-bytecode disassembly specifically.
- **modules / loadedSources** — separate-symbol configs (the `.debug`/`.dSYM`/
  `.pdb` shows up as a distinct module/source).

## Source mapping

- **path remapping** — every CMake C++ build is compiled with
  `-fdebug-prefix-map=<srcroot>=.`, so debug-info paths are normalized and the
  consumer must remap them back to the shipped `source` file. The
  separate-symbol and remote (Android) configs stress this hardest.

## Postmortem / remote

- **core-file debugging** (`target create --core`) — future `crash` core-dump
  artifacts.
- **remote attach** — Android zips (`gdb-remote` via `lldb-server` + `adb
  forward`); the recipe is in each `fixture.json["debug_recipe"]`.

## reverse requests

- **runInTerminal** — `spin`/`hello` launched in an integrated terminal.
- **startDebugging** (child sessions) — future multi-process fixture.
