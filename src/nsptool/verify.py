"""File validation.

Two tiers:

- quick (default): structural check using the container metadata we already
  decrypt — PFS0 parses, every NCA header decrypts with an available master
  key, and each content NCA the CNMT declares is present (with the declared
  size, for uncompressed NSPs). Catches truncation, missing NCAs and
  wrong-key files in milliseconds per file.
- full (--full): delegates to `nsz -V`, which hashes every NCA against the
  SHA-256 digests in the CNMT (decompressing NCZ streams as needed). Catches
  bit rot; costs a full read of every file.

Full results are cached by (path, mtime, size) so re-runs only hash files
that changed; failures are never served from cache.
"""

import io
import json
import subprocess
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from .config import CACHE_DIR

CACHE_PATH = CACHE_DIR / "verify.json"

DELTA_FRAGMENT = 6  # commonly stripped from dumps and by nsz; absence is fine


@dataclass
class VerifyResult:
    path: Path
    ok: bool
    detail: str
    cached: bool = False


def verify_structure(path: Path) -> VerifyResult:
    from nsz.Fs import Nca, Pfs0, Type, factory
    from nsz.nut import Keys

    contained: dict[str, int] = {}
    cnmts = []
    try:
        with redirect_stdout(io.StringIO()):
            container = factory(path)
            container.open(str(path), "rb")
            try:
                for nspf in container:
                    contained[nspf._path] = nspf.size
                    if not isinstance(nspf, Nca.Nca):
                        continue
                    if not Keys.existsMasterKey(nspf.header.masterKey):
                        return VerifyResult(
                            path, False, f"missing master_key_{nspf.header.masterKey:02x}"
                        )
                    if nspf.header.contentType == Type.Content.META:
                        for section in nspf:
                            if isinstance(section, Pfs0.Pfs0):
                                cnmts.append(section.getCnmt())
            finally:
                container.close()
    except Exception as e:
        return VerifyResult(path, False, f"unreadable: {e}")

    if not cnmts:
        return VerifyResult(path, False, "no CNMT found")

    compressed = path.suffix.lower() == ".nsz"
    problems = []
    for cnmt in cnmts:
        for entry in cnmt.contentEntries:
            if entry.type == DELTA_FRAGMENT:
                continue
            nca = f"{entry.ncaId}.nca"
            if nca in contained:
                if not compressed and contained[nca] != entry.size:
                    problems.append(f"{nca}: size {contained[nca]} != cnmt {entry.size}")
            elif not (compressed and f"{entry.ncaId}.ncz" in contained):
                problems.append(f"missing {nca}")
    if problems:
        return VerifyResult(path, False, "; ".join(problems[:3]))
    return VerifyResult(path, True, "structure ok")


def verify_full(path: Path) -> VerifyResult:
    from .convert import _nsz_bin

    proc = subprocess.run([_nsz_bin(), "-V", str(path)], capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    if proc.returncode == 0 and "Traceback" not in output:
        return VerifyResult(path, True, "hashes verified")
    lines = [line for line in output.splitlines() if line.strip()]
    return VerifyResult(path, False, lines[-1] if lines else f"nsz exited {proc.returncode}")


class Cache:
    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def _key_and_stat(self, path: Path) -> tuple[str, dict]:
        stat = path.stat()
        return str(path.resolve()), {"mtime": stat.st_mtime, "size": stat.st_size}

    def lookup(self, path: Path) -> VerifyResult | None:
        """A previously verified-good result for an unchanged file, else None."""
        key, stat = self._key_and_stat(path)
        entry = self.data.get(key)
        if entry and entry["ok"] and {k: entry[k] for k in ("mtime", "size")} == stat:
            return VerifyResult(path, True, "hashes verified", cached=True)
        return None

    def store(self, result: VerifyResult) -> None:
        key, stat = self._key_and_stat(result.path)
        self.data[key] = {**stat, "ok": result.ok}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
