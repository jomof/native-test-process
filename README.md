# native-test-process

Prebuilt, published, **known-debuggable** native processes for driving Debug
Adapter Protocol (DAP) integration tests.

This project compiles a handful of tiny fixture programs across a declarative
matrix of dimensions, proves each artifact is actually debuggable, and
publishes **one zip per configuration** plus a `manifest.json` to a pinned
GitHub Release. A consumer (the [dap](https://github.com/jomof/dap) plugin)
downloads exactly the configurations it wants to test against, instead of
compiling fixtures on the fly.

## Why

Debuggers behave differently across operating systems, languages, symbol
layouts, optimization levels, and remote topologies. A DAP bridge needs to be
tested against that whole space. Compiling fixtures inline (the old approach)
only ever exercises the host's native toolchain. Prebuilding them here lets a
single test run pull a Linux/separate-symbols/Rust binary, an Android arm64
binary, or an architecture-neutral WASM module and drive a debugger against it.

## The shape of it

```
matrix.toml ──► builder (Python) ──► {cmake│cargo│go} ──► symbol split
            ──► marker→line map ──► per-config zip + fixture.json
            ──► lldb / wasmtime self-test ──► manifest.json ──► GitHub Release
```

Everything is driven by [`matrix.toml`](matrix.toml): every testable
configuration is the cross product `program × language × platform × symbols`,
pruned by capability rules. Nothing about the configuration set is hard-coded
in code.

## Dimensions

| Dimension | Values (today) |
|-----------|----------------|
| OS / arch | linux-x86_64, macos-arm64, windows-x86_64, android-{arm64-v8a,armeabi-v7a,x86_64,x86}, wasm32 |
| Language  | C++, Rust, Go |
| Symbols   | embedded, separate (ELF `.debug` / Mach-O `.dSYM` / PE `.pdb`) |

See [docs/DESIGN.md](docs/DESIGN.md) for the roadmap of further dimensions
(optimization level, stripped, static/musl, split-DWARF, sanitizers, big-endian,
…), the catalogue of remote-debugging topologies (Android, SSH/`lldb-server`,
containers, embedded/MCU, QEMU, core dumps, time-travel), and the **WASM
investigation** (one artifact, every host).

## Fixtures

| Program | Purpose |
|---------|---------|
| `hello` | Print, flush, exit 0 — launch / output / exit-code coverage. |
| `spin`  | Tick loop with typed locals, recursion, a global, and worker threads. |
| `crash` | Deterministic fault (`--mode=segv|abort|divzero`) for exception / postmortem tests. |

Each source carries `// @dap:<marker>` sentinel comments. The builder resolves
them to line numbers and records `marker → line` in each fixture's
`fixture.json`, so DAP tests reference breakpoints by **name**, never by a
brittle hard-coded line number.

## Usage

```bash
# Build every configuration this host can produce, into dist/.
python3 -m builder build

# Build a subset.
python3 -m builder build --program spin --language rust --platform linux-x86_64

# List what the matrix expands to (no building).
python3 -m builder list

# Prove the built artifacts are debuggable.
python3 -m builder selftest

# Write dist/manifest.json from everything in dist/.
python3 -m builder manifest
```

Requirements: Python 3.11+ (uses stdlib `tomllib`). Per-language toolchains are
needed only for the languages/platforms you build (CMake + clang for C++,
`cargo` for Rust, `go` for Go; the NDK for Android, wasi-sdk / `wasm32-wasip1`
for WASM).

## Publishing

`.github/workflows/build.yml` builds and self-tests the whole matrix on every
push. `.github/workflows/release.yml` runs on a tag, gathers every runner's
zips, writes the aggregate `manifest.json`, and attaches them to a GitHub
Release named by `release_tag` in `matrix.toml`.
