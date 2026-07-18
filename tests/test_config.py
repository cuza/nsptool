import tomllib
from pathlib import Path

import pytest

from nsptool import config as config_mod
from nsptool.config import Config, render_config, run_wizard


def make_config(tmp_path: Path) -> Config:
    return Config(
        library=tmp_path / 'weird "quoted" \\ library',
        keys=tmp_path / "prod.keys",
        region="US",
        titledb_region="US",
        titledb_language="en",
        titledb_url=config_mod.DEFAULT_TITLEDB_URL,
    )


def test_render_config_round_trips_through_toml(tmp_path):
    cfg = make_config(tmp_path)
    data = tomllib.loads(render_config(cfg))
    assert Path(data["library"]) == cfg.library
    assert Path(data["keys"]) == cfg.keys
    assert data["region"] == "US"
    assert data["titledb_url"] == config_mod.DEFAULT_TITLEDB_URL


def test_wizard_creates_library_and_writes_config(tmp_path, monkeypatch):
    keys = tmp_path / "prod.keys"
    keys.touch()
    library = tmp_path / "library"

    answers = iter(
        [
            str(library),  # library dir
            "y",  # create it
            str(keys),  # prod.keys
            "us",  # region tag
            "",  # titledb region (default: region)
            "",  # titledb language (default: en)
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "config" / "config.toml")

    cfg = run_wizard()

    assert library.is_dir()
    assert cfg.region == "US"
    assert cfg.titledb_region == "US"
    assert cfg.titledb_language == "en"
    written = tomllib.loads((tmp_path / "config" / "config.toml").read_text())
    assert Path(written["library"]) == library
    assert Path(written["keys"]) == keys


def test_load_config_rejects_missing_required_keys(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('region = "US"\n')
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)

    with pytest.raises(SystemExit, match="library"):
        config_mod.load_config()
