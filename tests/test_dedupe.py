from pathlib import Path

import pytest

from nsptool import dedupe, titledb
from nsptool.config import Config

TITLEDB = {"0100BF00112C0000": "Catherine: Full Body"}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(titledb, "lookup", lambda _cfg, tid: TITLEDB.get(tid.upper()))
    library = tmp_path / "library"
    library.mkdir()
    return Config(
        library=library,
        keys=tmp_path / "prod.keys",
        region="US",
        titledb_region="US",
        titledb_language="en",
        titledb_url="unused",
    )


def add_file(library: Path, folder: str, name: str, content: bytes = b"x") -> Path:
    path = library / folder / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(content)
    return path


def by_status(items):
    result: dict[str, list] = {}
    for item in items:
        result.setdefault(item.status, []).append(item)
    return result


def test_exact_duplicate_keeps_canonical_copy(cfg):
    canonical = add_file(
        cfg.library,
        "Catherine Full Body [0100BF00112C0000] [US]",
        "Catherine Full Body [0100BF00112C0000][v0] [US].nsp",
    )
    stray = add_file(
        cfg.library,
        "Catherine [0100BF00112C0000] dump",
        "Catherine Full Body [0100BF00112C0000][v0] [US].nsp",
    )

    items = dedupe.plan(cfg)
    groups = by_status(items)
    assert [i.path for i in groups["delete"]] == [stray]
    assert str(canonical) in groups["delete"][0].note


def test_format_double_reported_without_prefer(cfg):
    folder = "Catherine Full Body [0100BF00112C0000] [US]"
    add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0000][v0] [US].nsp")
    add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0000][v0] [US].nsz")

    items = dedupe.plan(cfg)
    groups = by_status(items)
    assert "delete" not in groups
    assert len(groups["double"]) == 2


@pytest.mark.parametrize("prefer,removed_ext", [("nsz", ".nsp"), ("nsp", ".nsz")])
def test_format_double_resolved_with_prefer(cfg, prefer, removed_ext):
    folder = "Catherine Full Body [0100BF00112C0000] [US]"
    add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0000][v0] [US].nsp")
    add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0000][v0] [US].nsz")

    items = dedupe.plan(cfg, prefer=prefer)
    groups = by_status(items)
    assert len(groups["delete"]) == 1
    assert groups["delete"][0].path.suffix == removed_ext


def test_old_update_reported_and_pruned(cfg):
    folder = "Catherine Full Body [0100BF00112C0000] [US]"
    old = add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0800][v65536] [US].nsp")
    add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0800][v131072] [US].nsp")

    items = dedupe.plan(cfg)
    groups = by_status(items)
    assert "delete" not in groups
    assert [i.path for i in groups["old"]] == [old]

    items = dedupe.plan(cfg, prune_old_versions=True)
    groups = by_status(items)
    assert [i.path for i in groups["delete"]] == [old]
    assert "superseded by v131072" in groups["delete"][0].note


def test_base_versions_never_pruned(cfg):
    folder = "Catherine Full Body [0100BF00112C0000] [US]"
    add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0000][v0] [US].nsp")
    add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0800][v131072] [US].nsp")

    items = dedupe.plan(cfg, prune_old_versions=True)
    assert items == []


def test_apply_deletes_only_delete_items(cfg):
    folder = "Catherine Full Body [0100BF00112C0000] [US]"
    keeper = add_file(cfg.library, folder, "Catherine Full Body [0100BF00112C0000][v0] [US].nsp")
    stray = add_file(
        cfg.library, "strays", "Catherine Full Body [0100BF00112C0000][v0] [US].nsp"
    )

    items = dedupe.plan(cfg)
    removed = dedupe.apply(items)
    assert removed == 1
    assert keeper.exists()
    assert not stray.exists()
