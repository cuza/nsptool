"""NSP <-> NSZ conversion, delegated to the nsz CLI (same virtualenv).

nsz handles the heavy lifting: NCA decryption, zstandard (de)compression,
multithreading and verification. We shell out to its console script so its
progress bars and multiprocessing work exactly as upstream intends.
"""

import subprocess
import sys
from pathlib import Path

from .meta import find_game_files


def expand_paths(paths: list[Path], extension: str) -> list[Path]:
    """Expand directories to all contained files with the given extension.

    nsz's own directory handling is not recursive, so a library organized into
    per-game folders would be skipped entirely; we walk directories ourselves
    and pass explicit file lists. Files given directly are kept as-is.
    """
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            found = find_game_files(path, {extension})
            if not found:
                print(f"warning: no {extension} files under {path}", file=sys.stderr)
            files.extend(found)
        else:
            files.append(path)
    return files


def _nsz_bin() -> str:
    candidate = Path(sys.executable).parent / "nsz"
    if candidate.is_file():
        return str(candidate)
    return "nsz"  # fall back to PATH


def run_nsz(args: list[str]) -> int:
    cmd = [_nsz_bin(), *args]
    print(f"$ {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd)


def compress(
    paths: list[Path],
    out: Path | None,
    level: int,
    threads: int,
    verify: bool,
    rm_source: bool,
    overwrite: bool,
) -> int:
    args = ["-C", "--level", str(level), "--parseCnmt"]
    if threads > 0:
        args += ["--threads", str(threads)]
    if verify:
        # -Q (quick verify) works during compression without --keep.
        args.append("-Q")
    if rm_source:
        args.append("--rm-source")
    if overwrite:
        args.append("-w")
    if out:
        out.mkdir(parents=True, exist_ok=True)
        args += ["-o", str(out)]
    files = expand_paths(paths, ".nsp")
    if not files:
        return 1
    args += [str(p) for p in files]
    return run_nsz(args)


def decompress(
    paths: list[Path],
    out: Path | None,
    verify: bool,
    rm_source: bool,
    overwrite: bool,
) -> int:
    args = ["-D", "--parseCnmt"]
    if verify:
        args.append("-V")
    if rm_source:
        args.append("--rm-source")
    if overwrite:
        args.append("-w")
    if out:
        out.mkdir(parents=True, exist_ok=True)
        args += ["-o", str(out)]
    files = expand_paths(paths, ".nsz")
    if not files:
        return 1
    args += [str(p) for p in files]
    return run_nsz(args)
