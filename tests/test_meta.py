from pathlib import Path

from nsptool.meta import TitleMeta, TitleType, parse_filename, type_from_title_id


def test_type_from_title_id():
    assert type_from_title_id("01001B300B9BE000") == TitleType.BASE
    assert type_from_title_id("01001B300B9BE800") == TitleType.UPDATE
    assert type_from_title_id("01001B300B9BF064") == TitleType.DLC
    assert type_from_title_id("0100F43008C45002") == TitleType.DLC


def test_base_id_derivation():
    def base_id(tid: str) -> str:
        return TitleMeta(Path("x.nsp"), tid, 0, type_from_title_id(tid), "test").base_id

    assert base_id("01001B300B9BE000") == "01001B300B9BE000"
    assert base_id("01001B300B9BE800") == "01001B300B9BE000"
    assert base_id("01001B300B9BF064") == "01001B300B9BE000"
    assert base_id("0100F43008C45002") == "0100F43008C44000"
    assert base_id("01005D100807B00A") == "01005D100807A000"


def test_parse_filename_full():
    meta = parse_filename(Path("ANIMAL WELL [010020D01AD24800][v589824] [US].nsp"))
    assert meta is not None
    assert meta.title_id == "010020D01AD24800"
    assert meta.version == 589824
    assert meta.title_type == TitleType.UPDATE
    assert meta.source == "filename"


def test_parse_filename_dlc_empty_version():
    meta = parse_filename(Path("Pokémon Quest (Expedition Pack)[01005D100807B001][v] [US].nsp"))
    assert meta is not None
    assert meta.title_id == "01005D100807B001"
    assert meta.version == 0
    assert meta.title_type == TitleType.DLC


def test_parse_filename_lowercase_and_bare():
    meta = parse_filename(Path("0100bf00112c0000.nsz"))
    assert meta is not None
    assert meta.title_id == "0100BF00112C0000"
    assert meta.version == 0
    assert meta.title_type == TitleType.BASE


def test_parse_filename_no_title_id():
    assert parse_filename(Path("mystery-update.nsp")) is None
