"""NSP <-> NSZ conversion, delegated to the nsz CLI (same virtualenv).

nsz handles the heavy lifting: NCA decryption, zstandard (de)compression,
multithreading and verification. We shell out to its console script so its
progress bars and multiprocessing work exactly as upstream intends.
"""

import subprocess
import sys
from pathlib import Path


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
    args += [str(p) for p in paths]
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
    args += [str(p) for p in paths]
    return run_nsz(args)
