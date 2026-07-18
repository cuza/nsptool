"""titledb name lookups.

Downloads blawar/titledb's {REGION}.{lang}.json, reduces it to a small
titleid->name index cached under ~/.cache/nsptool/, and serves lookups from
that. The full file (~150 MB) is deleted after indexing.
"""

import json
import sys
import urllib.request

from .config import CACHE_DIR, Config

_index_cache: dict[str, str] | None = None


def update(cfg: Config) -> None:
    url = cfg.resolved_titledb_url()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_DIR / "titledb-download.json"

    print(f"Downloading {url} ...")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                progress = f"\r  {done / (1 << 20):.0f}/{total / (1 << 20):.0f} MB"
                print(progress, end="", file=sys.stderr)
    print(file=sys.stderr)

    print("Building name index ...")
    with open(tmp, encoding="utf-8") as f:
        full = json.load(f)

    index: dict[str, str] = {}
    for entry in full.values():
        tid = entry.get("id")
        name = entry.get("name")
        if tid and name:
            index[tid.upper()] = name

    with open(cfg.titledb_index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    tmp.unlink()
    print(f"Indexed {len(index)} titles -> {cfg.titledb_index_path}")


def lookup(cfg: Config, title_id: str) -> str | None:
    global _index_cache
    if _index_cache is None:
        if not cfg.titledb_index_path.is_file():
            return None
        with open(cfg.titledb_index_path, encoding="utf-8") as f:
            _index_cache = json.load(f)
    return _index_cache.get(title_id.upper())


def is_available(cfg: Config) -> bool:
    return cfg.titledb_index_path.is_file()
