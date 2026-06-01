"""native-test-process build orchestrator.

A thin, readable Python layer over idiomatic per-language toolchains (CMake,
Cargo, go build). It reads matrix.toml, builds each configuration, splits
symbols, resolves @dap markers to line numbers, packs one zip per config with
a fixture.json, self-tests debuggability, and writes the aggregate manifest.

Entry point: ``python3 -m builder``.
"""

__version__ = "0.1.0"
