"""nsptool command line interface."""

import argparse
import sys
import warnings
from pathlib import Path

from . import __version__
from .config import CONFIG_PATH, load_config
from .keys import ensure_keys, highest_master_key

# nsz 4.6 uses pre-3.12 escape sequences; not our warning to surface. On first
# import the warning's "module" is the source file path, so match that too.
warnings.filterwarnings("ignore", category=SyntaxWarning, module=r".*nsz.*")

# Titles released after ~2021 need master keys well past this; used only to warn.
MASTER_KEY_WARN_THRESHOLD = 0x0F


def _bootstrap_keys(cfg) -> None:
    import contextlib
    import io

    ensure_keys(cfg.keys)
    # nsz loads the keys at import time and prints a checksum line per key it
    # doesn't recognize; do the one-time import here with stdout swallowed.
    with contextlib.redirect_stdout(io.StringIO()):
        import nsz.nut.Keys  # noqa: F401
    highest = highest_master_key(cfg.keys)
    if highest < MASTER_KEY_WARN_THRESHOLD:
        print(
            f"warning: {cfg.keys} only contains master keys up to "
            f"master_key_{highest:02x}; recent titles will fail to decrypt. "
            "Re-dump keys from your console with a current Lockpick_RCM build.",
            file=sys.stderr,
        )


def cmd_scan(cfg, args) -> int:
    _bootstrap_keys(cfg)
    from . import titledb
    from .meta import find_game_files, parse_file

    files = find_game_files(Path(args.source).expanduser())
    if not files:
        print("No .nsp/.nsz files found.", file=sys.stderr)
        return 1

    from .term import term

    type_styles = {"BASE": term.green, "UPDATE": term.blue, "DLC": term.magenta}
    for path in files:
        try:
            meta = parse_file(path, fast=args.fast)
        except Exception as e:
            print(f"{term.red('ERROR ')} {path.name}: {e}")
            continue
        name = titledb.lookup(cfg, meta.title_id) or titledb.lookup(cfg, meta.base_id) or "?"
        warn = term.yellow(f"  ({meta.warning})") if meta.warning else ""
        ttype = type_styles[meta.title_type.value](f"{meta.title_type.value:6}")
        print(f"{ttype} {meta.title_id} v{meta.version:<10} {name}  [{path.name}]{warn}")
    return 0


def _run_library_plan(cfg, source: Path, apply: bool, copy: bool, fast: bool) -> int:
    _bootstrap_keys(cfg)
    from . import organize, titledb

    if not titledb.is_available(cfg):
        print(
            "note: no titledb index found; names will come from filenames or the "
            "existing library. Run 'nsptool update-titledb' for proper names.",
            file=sys.stderr,
        )

    if not cfg.library.is_dir():
        print(f"error: library not found: {cfg.library}", file=sys.stderr)
        return 1

    items = organize.plan(cfg, source, fast=fast)
    if not items:
        return 1
    organize.print_plan(items)

    movable = [i for i in items if i.status == "move"]
    if not apply:
        if movable:
            print("\nDry run. Re-run with --apply to perform these moves.")
        return 0
    if not movable:
        print("\nNothing to do.")
        return 0

    print()
    moved = organize.apply(items, copy=copy)
    print(f"\n{'Copied' if copy else 'Moved'} {moved} file(s) into {cfg.library}")
    return 0


def cmd_library_add(cfg, args) -> int:
    if args.library:
        cfg.library = Path(args.library).expanduser()
    return _run_library_plan(
        cfg, Path(args.source).expanduser(), args.apply, args.copy, args.fast
    )


def cmd_library_organize(cfg, args) -> int:
    if args.library:
        cfg.library = Path(args.library).expanduser()
    return _run_library_plan(cfg, cfg.library, args.apply, copy=False, fast=args.fast)


def cmd_library_list(cfg, args) -> int:
    from .organize import summarize_library

    if args.library:
        cfg.library = Path(args.library).expanduser()
    if not cfg.library.is_dir():
        print(f"error: library not found: {cfg.library}", file=sys.stderr)
        return 1
    summarize_library(cfg.library)
    return 0


def cmd_compress(cfg, args) -> int:
    _bootstrap_keys(cfg)
    from .convert import compress

    return compress(
        [Path(p).expanduser() for p in args.paths],
        Path(args.out).expanduser() if args.out else None,
        level=args.level,
        threads=args.threads,
        verify=not args.no_verify,
        rm_source=args.rm_source,
        overwrite=args.overwrite,
    )


def cmd_decompress(cfg, args) -> int:
    _bootstrap_keys(cfg)
    from .convert import decompress

    return decompress(
        [Path(p).expanduser() for p in args.paths],
        Path(args.out).expanduser() if args.out else None,
        verify=not args.no_verify,
        rm_source=args.rm_source,
        overwrite=args.overwrite,
    )


def cmd_update_titledb(cfg, args) -> int:
    from . import titledb

    titledb.update(cfg)
    return 0


def cmd_config(cfg, args) -> int:
    if args.setup:
        from .config import run_wizard

        cfg = run_wizard()
    print(f"config file: {CONFIG_PATH}")
    print(f"library:     {cfg.library}")
    print(f"keys:        {cfg.keys} (highest master key: "
          f"{highest_master_key(cfg.keys):#04x})" if cfg.keys.is_file()
          else f"keys:        {cfg.keys} (MISSING)")
    print(f"region tag:  {cfg.region}")
    indexed = "indexed" if cfg.titledb_index_path.is_file() else "missing - run update-titledb"
    print(f"titledb:     {cfg.titledb_region}.{cfg.titledb_language} ({indexed})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nsptool",
        description="Organize a Nintendo Switch NSP/NSZ library and convert NSP<->NSZ.",
    )
    parser.add_argument("--version", action="version", version=f"nsptool {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="List NSP/NSZ files with parsed metadata")
    p.add_argument("source", help="File or directory to scan")
    p.add_argument("--fast", action="store_true", help="Trust filenames; only decrypt when needed")
    p.set_defaults(func=cmd_scan)

    lib = sub.add_parser("library", help="Library management (add, organize, list)")
    libsub = lib.add_subparsers(dest="library_command", required=True)

    p = libsub.add_parser("add", help="Sort new NSP/NSZ files into the library")
    p.add_argument("source", help="Directory (or single file) with incoming files")
    p.add_argument("--apply", action="store_true", help="Move files (default is a dry run)")
    p.add_argument("--copy", action="store_true", help="Copy instead of move")
    p.add_argument("--library", help="Override the library directory from the config")
    p.add_argument("--fast", action="store_true", help="Trust filenames; only decrypt when needed")
    p.set_defaults(func=cmd_library_add)

    p = libsub.add_parser("organize", help="Normalize names/locations inside the library itself")
    p.add_argument("--apply", action="store_true", help="Move files (default is a dry run)")
    p.add_argument("--library", help="Override the library directory from the config")
    p.add_argument("--fast", action="store_true", help="Trust filenames; only decrypt when needed")
    p.set_defaults(func=cmd_library_organize)

    p = libsub.add_parser("list", help="Show the library contents per game")
    p.add_argument("--library", help="Override the library directory from the config")
    p.set_defaults(func=cmd_library_list)

    p = sub.add_parser("compress", help="Convert NSP -> NSZ (via nsz)")
    p.add_argument("paths", nargs="+", help="NSP files or directories")
    p.add_argument("-o", "--out", help="Output directory (default: next to source)")
    p.add_argument("--level", type=int, default=18, help="zstd level, max 22 (default 18)")
    p.add_argument("--threads", type=int, default=-1, help="Compression threads")
    p.add_argument("--no-verify", action="store_true", help="Skip verification after compressing")
    p.add_argument("--rm-source", action="store_true", help="Delete the NSP after compressing")
    p.add_argument("-w", "--overwrite", action="store_true", help="Overwrite existing output")
    p.set_defaults(func=cmd_compress)

    p = sub.add_parser("decompress", help="Convert NSZ -> NSP (via nsz)")
    p.add_argument("paths", nargs="+", help="NSZ files or directories")
    p.add_argument("-o", "--out", help="Output directory (default: next to source)")
    p.add_argument("--no-verify", action="store_true", help="Skip verification after decompressing")
    p.add_argument("--rm-source", action="store_true", help="Delete the NSZ after decompressing")
    p.add_argument("-w", "--overwrite", action="store_true", help="Overwrite existing output")
    p.set_defaults(func=cmd_decompress)

    p = sub.add_parser("update-titledb", help="Download/refresh the titledb name index")
    p.set_defaults(func=cmd_update_titledb)

    p = sub.add_parser("config", help="Show current configuration")
    p.add_argument("--setup", action="store_true", help="Re-run the setup wizard")
    p.set_defaults(func=cmd_config)

    args = parser.parse_args()
    cfg = load_config()
    sys.exit(args.func(cfg, args))


if __name__ == "__main__":
    main()
