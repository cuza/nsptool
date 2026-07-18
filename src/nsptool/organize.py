"""Library organization: sort NSP/NSZ files into a per-game layout.

Target layout:

    Library/
      Game Name [0100XXXXXXXX0000] [US]/
        Game Name [0100XXXXXXXX0000][v0] [US].nsp          (base)
        Game Name [0100XXXXXXXX0800][v65536] [US].nsp      (update)
        Game Name (DLC Name)[0100XXXXXXXX1234][v] [US].nsp (DLC)
"""

import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import titledb
from .config import Config
from .meta import (
    TITLE_ID_RE,
    VERSION_RE,
    MissingMasterKeyError,
    TitleMeta,
    TitleType,
    find_game_files,
    parse_file,
    parse_filename,
)

_ILLEGAL = re.compile(r'[<>:"|?*!]')
_TRADEMARKS = re.compile(r"[™®©]")  # ™ ® ©


def nfc(s: str) -> str:
    """NFC-normalize; macOS filesystems return NFD names, titledb uses NFC."""
    return unicodedata.normalize("NFC", s)


def sanitize(name: str) -> str:
    name = nfc(name)
    name = _TRADEMARKS.sub("", name)
    name = name.replace("/", " ").replace("\\", " ")
    name = _ILLEGAL.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name


@dataclass
class PlanItem:
    src: Path
    meta: TitleMeta | None
    dest: Path | None
    status: str  # move, in-place, duplicate, conflict, error
    note: str = ""


def build_library_index(library: Path) -> dict[str, dict[int, Path]]:
    """titleid -> {version -> path} for everything already in the library."""
    index: dict[str, dict[int, Path]] = {}
    for path in find_game_files(library):
        id_match = TITLE_ID_RE.search(path.name)
        if not id_match:
            continue
        version_match = VERSION_RE.search(path.name)
        version = int(version_match.group(1)) if version_match else 0
        index.setdefault(id_match.group(1).upper(), {})[version] = path
    return index


def _name_from_filename(path: Path) -> str | None:
    """Best-effort game name from a source filename: text before the first bracket."""
    stem = path.stem
    cut = min((i for i in (stem.find("["), stem.find("(")) if i >= 0), default=len(stem))
    name = stem[:cut].strip(" -_.")
    return name or None


def resolve_base_name(cfg: Config, base_id: str, src: Path, library: Path) -> tuple[str, str]:
    """Return (name, origin) for the base game a file belongs to.

    An existing library folder takes priority over titledb: titledb names drift
    over time (e.g. "... - Nintendo Switch 2 Edition" suffixes) and new content
    should land next to the base game it belongs to, not in a second folder.
    """
    for folder in library.glob(f"*[[]{base_id}[]]*"):
        existing = nfc(folder.name).split(f" [{base_id}]")[0].strip()
        if folder.is_dir() and existing:
            return existing, "library"
    name = titledb.lookup(cfg, base_id)
    if name:
        return sanitize(name), "titledb"
    from_file = _name_from_filename(src)
    if from_file:
        return sanitize(from_file), "filename"
    return base_id, "titleid"


def target_path(cfg: Config, meta: TitleMeta, base_name: str) -> Path:
    region = cfg.region
    ext = meta.path.suffix.lower()
    folder = f"{base_name} [{meta.base_id}] [{region}]"

    if meta.title_type == TitleType.DLC:
        dlc_name = titledb.lookup(cfg, meta.title_id)
        # Existing library writes DLC v0 as "[v]".
        version = str(meta.version) if meta.version else ""
        if dlc_name:
            filename = (
                f"{base_name} ({sanitize(dlc_name)})"
                f"[{meta.title_id}][v{version}] [{region}]{ext}"
            )
        else:
            filename = f"{base_name} [{meta.title_id}][v{version}] [{region}]{ext}"
    else:
        filename = f"{base_name} [{meta.title_id}][v{meta.version}] [{region}]{ext}"

    return cfg.library / folder / filename


def plan(cfg: Config, source: Path, fast: bool = False) -> list[PlanItem]:
    files = find_game_files(source)
    if not files:
        print(f"No .nsp/.nsz files found under {source}", file=sys.stderr)
        return []

    library_index = build_library_index(cfg.library)
    items: list[PlanItem] = []

    for src in files:
        try:
            meta = parse_file(src, fast=fast)
        except MissingMasterKeyError as e:
            items.append(PlanItem(src, None, None, "error", str(e)))
            continue
        except Exception as e:
            items.append(PlanItem(src, None, None, "error", f"unreadable: {e}"))
            continue

        base_name, origin = resolve_base_name(cfg, meta.base_id, src, cfg.library)
        dest = target_path(cfg, meta, base_name)
        note = meta.warning or ""
        if origin != "titledb":
            note = (note + "; " if note else "") + f"name from {origin}"

        if nfc(str(dest)) == nfc(str(src)):
            items.append(PlanItem(src, meta, dest, "in-place", note))
            continue

        existing = library_index.get(meta.title_id, {}).get(meta.version)
        if existing and nfc(str(existing)) != nfc(str(src)) and existing.suffix == src.suffix:
            items.append(
                PlanItem(src, meta, dest, "duplicate", f"already in library: {existing}")
            )
            continue
        if dest.exists():
            items.append(PlanItem(src, meta, dest, "conflict", "destination exists"))
            continue

        items.append(PlanItem(src, meta, dest, "move", note))

    return items


def apply(items: list[PlanItem], copy: bool = False) -> int:
    moved = 0
    for item in items:
        if item.status != "move" or item.dest is None:
            continue
        item.dest.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copy2(item.src, item.dest)
        else:
            shutil.move(str(item.src), str(item.dest))
        moved += 1
        print(f"  {'copied' if copy else 'moved'}: {item.dest}")
    return moved


def summarize_library(library: Path) -> None:
    """Print a per-game overview of the library based on filenames."""
    games: dict[str, dict] = {}
    unrecognized: list[Path] = []

    for path in find_game_files(library):
        meta = parse_filename(path)
        if meta is None:
            unrecognized.append(path)
            continue
        entry = games.setdefault(
            meta.base_id, {"name": None, "base": [], "update": [], "dlc": [], "size": 0}
        )
        key = {"BASE": "base", "UPDATE": "update", "DLC": "dlc"}[meta.title_type.value]
        entry[key].append(meta.version)
        entry["size"] += path.stat().st_size
        if entry["name"] is None:
            entry["name"] = nfc(path.parent.name).split(f" [{meta.base_id}]")[0]

    def human(size: int) -> str:
        return f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"

    total = 0
    for base_id, entry in sorted(games.items(), key=lambda kv: (kv[1]["name"] or "").lower()):
        parts = []
        if entry["base"]:
            parts.append("base " + ", ".join(f"v{v}" for v in sorted(entry["base"])))
        if entry["update"]:
            parts.append("update " + ", ".join(f"v{v}" for v in sorted(entry["update"])))
        if entry["dlc"]:
            parts.append(f"{len(entry['dlc'])} DLC")
        total += entry["size"]
        print(f"{entry['name']} [{base_id}]  ({human(entry['size'])})")
        print(f"    {' · '.join(parts) if parts else 'empty'}")

    for path in unrecognized:
        print(f"unrecognized: {path}")
    print(f"\n{len(games)} game(s), {human(total)} total")


def print_plan(items: list[PlanItem]) -> None:
    order = {"move": 0, "in-place": 1, "duplicate": 2, "conflict": 3, "error": 4}
    for item in sorted(items, key=lambda i: order.get(i.status, 9)):
        print(f"[{item.status:9}] {item.src.name}")
        if item.dest and item.status in ("move", "conflict"):
            print(f"            -> {item.dest}")
        if item.note:
            print(f"            note: {item.note}")

    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"\n{len(items)} file(s): {summary}")
