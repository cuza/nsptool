"""NSP/NSZ metadata extraction.

Authoritative path: decrypt the META (CNMT) NCA inside the container using the
console keys and read titleid/version/type from it. Fallback path: parse the
filename (``*[0100...000][v0]*``) when decryption is impossible, e.g. when the
title uses a newer master key than the prod.keys dump contains.

nsz must not be imported until keys.ensure_keys() has run (see keys.py).
"""

import io
import re
from contextlib import redirect_stdout
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

GAME_EXTENSIONS = {".nsp", ".nsz"}

TITLE_ID_RE = re.compile(r"\[?(01[0-9A-Fa-f]{14})\]?")
VERSION_RE = re.compile(r"\[v(\d+)\]")


class TitleType(Enum):
    BASE = "BASE"
    UPDATE = "UPDATE"
    DLC = "DLC"


class MissingMasterKeyError(Exception):
    def __init__(self, index: int):
        self.index = index
        super().__init__(
            f"prod.keys is missing master_key_{index:02x} (dump is too old for this title)"
        )


@dataclass
class TitleMeta:
    path: Path
    title_id: str  # 16 hex chars, upper
    version: int
    title_type: TitleType
    source: str  # "cnmt" or "filename"
    warning: str | None = None

    @property
    def base_id(self) -> str:
        """Application (base game) title id this content belongs to.

        Base title ids are 0x2000-aligned; updates are base+0x800 and DLC ids
        live in base+0x1000..base+0x1fff, so masking the low 13 bits recovers
        the base id for any content type.
        """
        return f"{int(self.title_id, 16) & ~0x1FFF:016X}"


def type_from_title_id(title_id: str) -> TitleType:
    low = int(title_id, 16) & 0x1FFF
    if low == 0:
        return TitleType.BASE
    if low == 0x800:
        return TitleType.UPDATE
    return TitleType.DLC


CNMT_TYPES = {0x80: TitleType.BASE, 0x81: TitleType.UPDATE, 0x82: TitleType.DLC}


def parse_filename(path: Path) -> TitleMeta | None:
    id_match = TITLE_ID_RE.search(path.name)
    if not id_match:
        return None
    title_id = id_match.group(1).upper()
    version_match = VERSION_RE.search(path.name)
    version = int(version_match.group(1)) if version_match else 0
    return TitleMeta(
        path=path,
        title_id=title_id,
        version=version,
        title_type=type_from_title_id(title_id),
        source="filename",
    )


def parse_cnmt(path: Path) -> TitleMeta:
    """Read titleid/version/type from the decrypted CNMT inside the container."""
    from nsz.Fs import Nca, Pfs0, Type, factory
    from nsz.nut import Keys

    container = factory(path)
    # nsz prints an "[OPEN]" line per contained file; keep our output clean.
    with redirect_stdout(io.StringIO()):
        container.open(str(path), "rb")
        try:
            metas = []
            for nspf in container:
                if not isinstance(nspf, Nca.Nca):
                    continue
                if nspf.header.contentType != Type.Content.META:
                    continue
                if not Keys.existsMasterKey(nspf.header.masterKey):
                    raise MissingMasterKeyError(nspf.header.masterKey)
                for section in nspf:
                    if isinstance(section, Pfs0.Pfs0):
                        cnmt = section.getCnmt()
                        metas.append(cnmt)
        finally:
            container.close()

    if not metas:
        raise ValueError("no CNMT found in container")
    if len(metas) > 1:
        raise ValueError(f"multi-title container ({len(metas)} CNMTs); not supported")

    cnmt = metas[0]
    title_id = cnmt.titleId.upper()
    if not re.fullmatch(r"01[0-9A-F]{14}", title_id):
        raise ValueError(f"decrypted CNMT looks corrupt (titleid {title_id!r})")
    title_type = CNMT_TYPES.get(cnmt.titleType) or type_from_title_id(title_id)
    return TitleMeta(
        path=path,
        title_id=title_id,
        version=cnmt.version,
        title_type=title_type,
        source="cnmt",
    )


def parse_file(path: Path, fast: bool = False) -> TitleMeta:
    """Extract metadata, preferring the CNMT and falling back to the filename.

    With fast=True the order flips: trust a well-formed filename and only open
    the container when the filename lacks the title id.
    """
    from_name = parse_filename(path)
    if fast and from_name:
        return from_name

    try:
        return parse_cnmt(path)
    except Exception as e:
        if from_name:
            from_name.warning = f"CNMT parse failed ({e}); using filename"
            return from_name
        raise


def find_game_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in GAME_EXTENSIONS else []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in GAME_EXTENSIONS and not p.name.startswith("._")
    )
