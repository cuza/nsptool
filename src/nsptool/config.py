"""Configuration handling for nsptool.

Config lives at ~/.config/nsp-tool/config.toml. On first run (no config file)
an interactive wizard asks for the library and keys locations and writes the
file; every command reads it afterwards.
"""

import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "nsp-tool"
CONFIG_PATH = CONFIG_DIR / "config.toml"
CACHE_DIR = Path.home() / ".cache" / "nsp-tool"

DEFAULT_TITLEDB_URL = (
    "https://raw.githubusercontent.com/blawar/titledb/master/{region}.{language}.json"
)

CONFIG_TEMPLATE = """\
# nsptool configuration

# Your organized library. `library add` moves files into here.
library = {library}

# Console keys dumped from your own Switch (Lockpick_RCM or similar).
keys = {keys}

# Region tag used in file/folder names, e.g. "Game [titleid] [US]".
region = {region}

# titledb region/language used for game and DLC display names.
titledb_region = {titledb_region}
titledb_language = {titledb_language}
titledb_url = {titledb_url}
"""


@dataclass
class Config:
    library: Path
    keys: Path
    region: str
    titledb_region: str
    titledb_language: str
    titledb_url: str

    @property
    def titledb_index_path(self) -> Path:
        return CACHE_DIR / f"names.{self.titledb_region}.{self.titledb_language}.json"

    def resolved_titledb_url(self) -> str:
        return self.titledb_url.format(
            region=self.titledb_region, language=self.titledb_language
        )


def render_config(cfg: Config) -> str:
    # json.dumps produces valid TOML basic strings (quoting, escapes).
    return CONFIG_TEMPLATE.format(
        library=json.dumps(str(cfg.library)),
        keys=json.dumps(str(cfg.keys)),
        region=json.dumps(cfg.region),
        titledb_region=json.dumps(cfg.titledb_region),
        titledb_language=json.dumps(cfg.titledb_language),
        titledb_url=json.dumps(cfg.titledb_url),
    )


def write_config(cfg: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(render_config(cfg), encoding="utf-8")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def run_wizard() -> Config:
    print(f"nsptool setup — answers are saved to {CONFIG_PATH}")

    while True:
        library = _ask("Library directory (where organized games live)")
        if not library:
            print("A library directory is required.")
            continue
        library_path = Path(library).expanduser()
        if library_path.is_dir():
            break
        if _ask(f"{library_path} does not exist. Create it? (y/n)", "y").lower().startswith("y"):
            library_path.mkdir(parents=True, exist_ok=True)
            break

    default_keys = Path.home() / ".switch" / "prod.keys"
    while True:
        keys = _ask("Path to prod.keys", str(default_keys) if default_keys.is_file() else "")
        if not keys:
            print("A prod.keys file is required (dump it from your own console).")
            continue
        keys_path = Path(keys).expanduser()
        if keys_path.is_file():
            break
        print(f"{keys_path} is not a file.")

    region = _ask("Region tag for file names", "US").upper()
    titledb_region = _ask("titledb region for display names", region).upper()
    titledb_language = _ask("titledb language for display names", "en").lower()

    cfg = Config(
        library=library_path,
        keys=keys_path,
        region=region,
        titledb_region=titledb_region,
        titledb_language=titledb_language,
        titledb_url=DEFAULT_TITLEDB_URL,
    )
    write_config(cfg)
    print(f"Wrote {CONFIG_PATH}\nNext: run 'nsptool update-titledb' to enable proper game names.")
    return cfg


def load_config() -> Config:
    if not CONFIG_PATH.is_file():
        if sys.stdin.isatty():
            return run_wizard()
        sys.exit(
            f"error: no config at {CONFIG_PATH} and not running interactively; "
            "run 'nsptool config --setup' in a terminal first"
        )

    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    missing = [k for k in ("library", "keys") if not data.get(k)]
    if missing:
        sys.exit(
            f"error: {CONFIG_PATH} is missing required setting(s): {', '.join(missing)}; "
            "run 'nsptool config --setup' to regenerate it"
        )

    return Config(
        library=Path(data["library"]),
        keys=Path(data["keys"]),
        region=data.get("region", "US"),
        titledb_region=data.get("titledb_region", "US"),
        titledb_language=data.get("titledb_language", "en"),
        titledb_url=data.get("titledb_url", DEFAULT_TITLEDB_URL),
    )
