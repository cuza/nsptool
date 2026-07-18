"""Library deduplication: find and (with --apply) delete redundant files.

Three categories, from always-actionable to opt-in:

- exact:   same titleid+version+extension in more than one place; the copy at
           the canonical path is kept, the rest are deleted on --apply.
- double:  same titleid+version as both .nsp and .nsz; only resolved when a
           preferred format is given (--prefer nsp|nsz).
- old:     UPDATE/DLC versions superseded by a newer version of the same
           titleid; only deleted with --prune-old-versions. Base games are
           never candidates: the newest update still requires the base.

Everything is filename-based (the library is expected to be organized), and
nothing is ever deleted without --apply.
"""

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .meta import TitleType, find_game_files, parse_filename
from .organize import nfc, resolve_base_name, target_path
from .term import term


@dataclass
class DedupeItem:
    path: Path
    status: str  # delete, double, old, unrecognized
    note: str
    size: int


def _canonical_keeper(cfg: Config, paths: list[Path]) -> Path:
    """Pick which of several identical copies to keep: the one already at its
    canonical location if any, otherwise the lexicographically first."""
    meta = parse_filename(paths[0])
    assert meta is not None
    base_name, _ = resolve_base_name(cfg, meta.base_id, paths[0], cfg.library)
    canonical = nfc(str(target_path(cfg, meta, base_name)))
    for path in paths:
        if nfc(str(path)) == canonical:
            return path
    return sorted(paths)[0]


def plan(
    cfg: Config, prune_old_versions: bool = False, prefer: str | None = None
) -> list[DedupeItem]:
    # (titleid, version, ext) -> paths, plus titleid -> type for the old-version pass
    groups: dict[tuple[str, int, str], list[Path]] = {}
    items: list[DedupeItem] = []

    for path in find_game_files(cfg.library):
        meta = parse_filename(path)
        if meta is None:
            items.append(DedupeItem(path, "unrecognized", "no titleid in filename", 0))
            continue
        groups.setdefault((meta.title_id, meta.version, path.suffix.lower()), []).append(path)

    deleted: set[Path] = set()

    # Pass 1: exact duplicates within the same extension.
    for paths in groups.values():
        if len(paths) < 2:
            continue
        keeper = _canonical_keeper(cfg, paths)
        for path in paths:
            if path != keeper:
                items.append(
                    DedupeItem(path, "delete", f"exact duplicate of {keeper}", path.stat().st_size)
                )
                deleted.add(path)

    def survivors(title_id: str, version: int, ext: str) -> list[Path]:
        return [p for p in groups.get((title_id, version, ext), []) if p not in deleted]

    # Pass 2: the same release in both formats.
    for title_id, version, ext in list(groups):
        if ext != ".nsp":
            continue
        nsps = survivors(title_id, version, ".nsp")
        nszs = survivors(title_id, version, ".nsz")
        if not nsps or not nszs:
            continue
        if prefer:
            drop, keep = (nszs, nsps) if prefer == "nsp" else (nsps, nszs)
            for path in drop:
                items.append(
                    DedupeItem(path, "delete", f"format double of {keep[0]}", path.stat().st_size)
                )
                deleted.add(path)
        else:
            for path in nsps + nszs:
                items.append(
                    DedupeItem(path, "double", "both nsp and nsz exist; use --prefer to resolve", 0)
                )

    # Pass 3: superseded UPDATE/DLC versions.
    by_title: dict[str, list[tuple[int, Path]]] = {}
    for (title_id, version, ext), paths in groups.items():
        meta = parse_filename(paths[0])
        if meta is None or meta.title_type == TitleType.BASE:
            continue
        for path in survivors(title_id, version, ext):
            by_title.setdefault(title_id, []).append((version, path))
    for versioned in by_title.values():
        newest = max(version for version, _ in versioned)
        for version, path in versioned:
            if version == newest:
                continue
            if prune_old_versions:
                items.append(
                    DedupeItem(path, "delete", f"superseded by v{newest}", path.stat().st_size)
                )
                deleted.add(path)
            else:
                items.append(
                    DedupeItem(
                        path, "old", f"superseded by v{newest}; use --prune-old-versions", 0
                    )
                )

    order = {"delete": 0, "double": 1, "old": 2, "unrecognized": 3}
    return sorted(items, key=lambda i: (order[i.status], str(i.path)))


STATUS_STYLES = {
    "delete": term.red,
    "double": term.yellow,
    "old": term.yellow,
    "unrecognized": term.dim,
}


def print_plan(items: list[DedupeItem]) -> None:
    if not items:
        print("No duplicates found.")
        return
    for item in items:
        style = STATUS_STYLES[item.status]
        print(f"[{style(f'{item.status:12}')}] {item.path}")
        print(term.dim(f"               {item.note}"))

    reclaim = sum(i.size for i in items if i.status == "delete")
    counts: dict[str, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"\n{summary}; {reclaim / 1e9:.2f} GB reclaimable with --apply")


def apply(items: list[DedupeItem]) -> int:
    removed = 0
    for item in items:
        if item.status != "delete":
            continue
        item.path.unlink()
        removed += 1
        print(f"  deleted: {item.path}")
    return removed
