import unicodedata
from pathlib import Path

import pytest

from nsptool import organize, titledb
from nsptool.config import Config
from nsptool.meta import TitleMeta, TitleType
from nsptool.organize import build_library_index, plan, resolve_base_name, sanitize, target_path

TITLEDB = {
    "0100BF00112C0000": "Catherine: Full Body",
    "01005D100807A000": "Pokémon™ Quest",
    "01005D100807B001": "Expedition Pack",
    "01004D300C5AE000": "Kirby and the Forgotten Land – Nintendo Switch 2 Edition",
}


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


def meta_for(name: str, tid: str, version: int, ttype: TitleType) -> TitleMeta:
    return TitleMeta(Path(name), tid, version, ttype, "test")


def test_sanitize_strips_marks_and_illegal_chars():
    assert sanitize("Diablo® II: Resurrected™") == "Diablo II Resurrected"
    assert sanitize("Fate/EXTELLA: The Umbral Star") == "Fate EXTELLA The Umbral Star"
    assert sanitize("  spaced   out  ") == "spaced out"


def test_sanitize_normalizes_nfd_to_nfc():
    nfd = unicodedata.normalize("NFD", "Pokémon")
    assert sanitize(nfd) == "Pokémon"
    assert sanitize(nfd) == unicodedata.normalize("NFC", "Pokémon")


def test_target_path_base(cfg):
    meta = meta_for("in.nsp", "0100BF00112C0000", 0, TitleType.BASE)
    assert target_path(cfg, meta, "Catherine Full Body") == (
        cfg.library
        / "Catherine Full Body [0100BF00112C0000] [US]"
        / "Catherine Full Body [0100BF00112C0000][v0] [US].nsp"
    )


def test_target_path_update_keeps_extension(cfg):
    meta = meta_for("in.nsz", "0100BF00112C0800", 131072, TitleType.UPDATE)
    dest = target_path(cfg, meta, "Catherine Full Body")
    assert dest.name == "Catherine Full Body [0100BF00112C0800][v131072] [US].nsz"
    assert dest.parent.name == "Catherine Full Body [0100BF00112C0000] [US]"


def test_target_path_dlc_v0_uses_empty_version(cfg):
    meta = meta_for("in.nsp", "01005D100807B001", 0, TitleType.DLC)
    dest = target_path(cfg, meta, "Pokémon Quest")
    assert dest.name == "Pokémon Quest (Expedition Pack)[01005D100807B001][v] [US].nsp"


def test_target_path_dlc_nonzero_version(cfg):
    meta = meta_for("in.nsp", "01005D100807B001", 65536, TitleType.DLC)
    dest = target_path(cfg, meta, "Pokémon Quest")
    assert dest.name == "Pokémon Quest (Expedition Pack)[01005D100807B001][v65536] [US].nsp"


def test_target_path_dlc_without_titledb_name(cfg):
    meta = meta_for("in.nsp", "0100AAAA11112064", 0, TitleType.DLC)
    dest = target_path(cfg, meta, "Some Game")
    assert dest.name == "Some Game [0100AAAA11112064][v] [US].nsp"


def test_resolve_base_name_prefers_existing_library_folder(cfg):
    (cfg.library / "Kirby and the Forgotten Land [01004D300C5AE000] [US]").mkdir()
    name, origin = resolve_base_name(
        cfg, "01004D300C5AE000", Path("in.nsp"), cfg.library
    )
    assert name == "Kirby and the Forgotten Land"
    assert origin == "library"


def test_resolve_base_name_titledb_fallback(cfg):
    name, origin = resolve_base_name(cfg, "0100BF00112C0000", Path("in.nsp"), cfg.library)
    assert name == "Catherine Full Body"
    assert origin == "titledb"


def test_resolve_base_name_filename_fallback(cfg):
    src = Path("Some Unknown Game [0100DEAD11112000][v0].nsp")
    name, origin = resolve_base_name(cfg, "0100DEAD11112000", src, cfg.library)
    assert name == "Some Unknown Game"
    assert origin == "filename"


def test_build_library_index(cfg):
    folder = cfg.library / "Pokémon Quest [01005D100807A000] [US]"
    folder.mkdir()
    (folder / "Pokémon Quest [01005D100807A000][v0] [US].nsp").touch()
    (folder / "Pokémon Quest (Expedition Pack)[01005D100807B001][v] [US].nsp").touch()

    index = build_library_index(cfg.library)
    assert "01005D100807A000" in index
    assert 0 in index["01005D100807A000"]
    assert index["01005D100807B001"][0].name.startswith("Pokémon Quest (Expedition")


def _plan_statuses(items):
    return {item.src.name: item.status for item in items}


def test_plan_moves_new_file_into_new_folder(cfg, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    src = staging / "Catherine Full Body [0100BF00112C0000][v0].nsp"
    src.touch()

    items = plan(cfg, staging, fast=True)
    assert _plan_statuses(items) == {src.name: "move"}
    assert items[0].dest == (
        cfg.library
        / "Catherine Full Body [0100BF00112C0000] [US]"
        / "Catherine Full Body [0100BF00112C0000][v0] [US].nsp"
    )


def test_plan_detects_duplicate_and_in_place(cfg, tmp_path):
    folder = cfg.library / "Catherine Full Body [0100BF00112C0000] [US]"
    folder.mkdir()
    in_lib = folder / "Catherine Full Body [0100BF00112C0000][v0] [US].nsp"
    in_lib.touch()

    staging = tmp_path / "staging"
    staging.mkdir()
    incoming = staging / "Catherine Full Body [0100BF00112C0000][v0].nsp"
    incoming.touch()

    items = plan(cfg, staging, fast=True)
    assert _plan_statuses(items) == {incoming.name: "duplicate"}

    items = plan(cfg, cfg.library, fast=True)
    assert _plan_statuses(items) == {in_lib.name: "in-place"}


def test_plan_and_apply_move(cfg, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    src = staging / "Catherine Full Body [0100BF00112C0800][v131072].nsp"
    src.write_bytes(b"data")

    items = plan(cfg, staging, fast=True)
    moved = organize.apply(items)
    assert moved == 1
    assert not src.exists()
    dest = (
        cfg.library
        / "Catherine Full Body [0100BF00112C0000] [US]"
        / "Catherine Full Body [0100BF00112C0800][v131072] [US].nsp"
    )
    assert dest.read_bytes() == b"data"
