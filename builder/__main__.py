"""Command-line entry point: `python3 -m builder <command>`.

Commands:
  list      Print the configurations the matrix expands to (no building).
  build     Build configurations into dist/ (one zip each) + a manifest.
  selftest  Drive a debugger against built zips to prove they work.
  manifest  (Re)write dist/manifest.json from the zips already in dist/.

All commands accept the same filters: --program, --language, --platform,
--symbols (each repeatable or comma-separated).
"""
from __future__ import annotations

import argparse
import sys

from . import manifest as manifest_mod
from . import matrix as matrix_mod
from . import pack as pack_mod
from . import selftest as selftest_mod
from . import symbols as symbols_mod
from . import toolchains
from .util import BUILD, DIST, log, rmtree


def _split(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    out: list[str] = []
    for value in values:
        out.extend(part for part in value.split(",") if part)
    return out or None


def _add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--program", action="append", help="program name (repeatable)")
    parser.add_argument("--language", action="append", help="cpp|rust|go (repeatable)")
    parser.add_argument("--platform", action="append", help="platform id (repeatable)")
    parser.add_argument("--symbols", action="append", help="embedded|separate (repeatable)")
    parser.add_argument("--runner", action="append", help="CI runner label, e.g. ubuntu-latest (repeatable)")


def _expand(args) -> list[matrix_mod.Config]:
    matrix = matrix_mod.load()
    return matrix_mod.expand(
        matrix,
        programs=_split(args.program),
        languages=_split(args.language),
        platforms=_split(args.platform),
        symbols=_split(args.symbols),
        runners=_split(getattr(args, "runner", None)),
    )


def cmd_list(args) -> int:
    configs = _expand(args)
    for config in configs:
        print(f"{config.id:48}  {config.platform.runner}")
    print(f"\n{len(configs)} configuration(s)")
    return 0


def cmd_build(args) -> int:
    matrix = matrix_mod.load()
    configs = _expand(args)
    if not configs:
        log("no configurations match the given filters")
        return 1
    if args.clean:
        rmtree(BUILD)
        rmtree(DIST)

    failures = 0
    for config in configs:
        log(f"=== build {config.id} ===")
        try:
            built = toolchains.build(config, BUILD)
            stage_dir = BUILD / "stage" / config.id
            rmtree(stage_dir)
            staged = symbols_mod.finalize(config, built, stage_dir)
            zip_path = pack_mod.pack(config, staged, stage_dir, matrix.release_tag)
            log(f"packed {zip_path.relative_to(DIST.parent)}")
        except Exception as exc:  # noqa: BLE001 - keep building the rest
            failures += 1
            log(f"FAILED {config.id}: {type(exc).__name__}: {exc}")

    if not args.no_manifest and failures == 0:
        out = manifest_mod.write(release_tag=matrix.release_tag)
        log(f"wrote {out.relative_to(DIST.parent)}")

    if failures:
        log(f"{failures} configuration(s) failed to build")
        return 1
    return 0


def cmd_selftest(args) -> int:
    configs = _expand(args)
    results = selftest_mod.run(configs, allow_skip=args.allow_skip)
    failed = [r for r in results if r.status == "fail"]
    passed = [r for r in results if r.status == "pass"]
    skipped = [r for r in results if r.status == "skip"]
    log(f"selftest summary: {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
    return 1 if failed else 0


def cmd_manifest(args) -> int:
    matrix = matrix_mod.load()
    out = manifest_mod.write(release_tag=matrix.release_tag)
    log(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="builder", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list configurations")
    _add_filters(p_list)
    p_list.set_defaults(func=cmd_list)

    p_build = sub.add_parser("build", help="build configurations into dist/")
    _add_filters(p_build)
    p_build.add_argument("--clean", action="store_true", help="wipe build/ and dist/ first")
    p_build.add_argument("--no-manifest", action="store_true", help="don't write manifest.json")
    p_build.set_defaults(func=cmd_build)

    p_self = sub.add_parser("selftest", help="prove built zips are debuggable")
    _add_filters(p_self)
    p_self.add_argument("--allow-skip", action="store_true", help="treat missing tools as skips, not failures")
    p_self.set_defaults(func=cmd_selftest)

    p_man = sub.add_parser("manifest", help="(re)write dist/manifest.json")
    p_man.set_defaults(func=cmd_manifest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
