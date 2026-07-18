from nsptool.convert import expand_paths


def test_expand_paths_recurses_into_game_folders(tmp_path):
    game_a = tmp_path / "Game A [0100AAAA00002000] [US]"
    game_b = tmp_path / "Game B [0100BBBB00002000] [US]"
    game_a.mkdir()
    game_b.mkdir()
    a_base = game_a / "Game A [0100AAAA00002000][v0] [US].nsp"
    b_update = game_b / "Game B [0100BBBB00002800][v65536] [US].nsp"
    b_nsz = game_b / "Game B [0100BBBB00002000][v0] [US].nsz"
    for f in (a_base, b_update, b_nsz):
        f.touch()
    (game_a / "._Game A [0100AAAA00002000][v0] [US].nsp").touch()

    assert expand_paths([tmp_path], ".nsp") == [a_base, b_update]
    assert expand_paths([tmp_path], ".nsz") == [b_nsz]


def test_expand_paths_keeps_explicit_files(tmp_path):
    f = tmp_path / "whatever.nsp"
    f.touch()
    assert expand_paths([f], ".nsz") == [f]


def test_expand_paths_empty_dir_warns_and_returns_nothing(tmp_path, capsys):
    assert expand_paths([tmp_path], ".nsp") == []
    assert "no .nsp files" in capsys.readouterr().err
