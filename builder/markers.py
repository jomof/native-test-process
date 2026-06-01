"""Resolve `// @dap:<name>` sentinel comments in fixture sources to line numbers.

This is the small idea that makes the framework pleasant: tests reference
breakpoints by stable *name* (e.g. "loop_body"), and the build records the
current line for each name into fixture.json. Editing a fixture can never
silently break a test's hard-coded line number, because there are none.
"""
from __future__ import annotations

import re
from pathlib import Path

_MARKER_RE = re.compile(r"@dap:([A-Za-z0-9_]+)")


def extract(source: Path) -> dict[str, int]:
    """Map each @dap marker name to its 1-based line number in `source`."""
    markers: dict[str, int] = {}
    text = source.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _MARKER_RE.finditer(line):
            name = match.group(1)
            if name in markers:
                raise ValueError(
                    f"duplicate @dap marker '{name}' in {source} "
                    f"(lines {markers[name]} and {lineno})"
                )
            markers[name] = lineno
    return markers
