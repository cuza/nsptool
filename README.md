# nsptool

CLI to organize a Nintendo Switch NSP/NSZ library into a clean per-game layout
and convert between NSP and NSZ (delegating to
[nsz](https://github.com/nicoboss/nsz)).

## Library layout

```
Library/
  Game Name [0100XXXXXXXX0000] [US]/
    Game Name [0100XXXXXXXX0000][v0] [US].nsp            <- base game
    Game Name [0100XXXXXXXX0800][v65536] [US].nsp        <- update
    Game Name (DLC Name)[0100XXXXXXXX1234][v] [US].nsp   <- DLC
```

Files are identified by decrypting the CNMT metadata inside the container
(authoritative), falling back to filename parsing (`[titleid][vN]`) when the
title uses a master key that isn't in your `prod.keys`. Display names come
from an existing library folder for the same title first, then from
[titledb](https://github.com/blawar/titledb).

## Install

```sh
uv tool install nsptool     # or: pipx install nsptool / pip install nsptool
```

Requirements:

- `prod.keys` dumped from your own console (Lockpick_RCM or similar). Titles
  newer than your dump's highest master key can't be decrypted, so keep it
  current.

## Setup

The first run opens a short wizard asking for your library directory, the
path to `prod.keys`, and the region tag, saved to
`~/.config/nsptool/config.toml`. Re-run it anytime with
`nsptool config --setup`.

```sh
nsptool config              # show current settings
nsptool update-titledb      # one-time (~150 MB) download, cached as a small index
```

nsptool links your keys file to `~/.switch/prod.keys`, where nsz expects it.

## Commands

```sh
# inspect files (titleid, version, type, name)
nsptool scan ~/Downloads/incoming

# add new files to the library; dry run by default, shows the full plan
nsptool library add ~/Downloads/incoming
nsptool library add ~/Downloads/incoming --apply          # move for real
nsptool library add ~/Downloads/incoming --apply --copy   # copy instead
nsptool library add ~/Downloads/incoming --library /path  # different target

# normalize the library itself (fix drifted names/locations); dry run by default
nsptool library organize
nsptool library organize --apply

# per-game overview of the library (games, versions, DLC counts, sizes)
nsptool library list

# find redundant files; dry run by default, deletes only with --apply
nsptool library dedupe                       # exact duplicates
nsptool library dedupe --prune-old-versions  # + superseded update/DLC versions
nsptool library dedupe --prefer nsz          # + nsp/nsz doubles, keeping nsz
nsptool library dedupe --prefer nsp          # + nsp/nsz doubles, keeping nsp
nsptool library dedupe --apply               # actually delete

# validate files: quick structural check, or full NCA hash verification
nsptool verify                   # whole library, quick (seconds)
nsptool verify ~/Downloads/incoming
nsptool verify --full            # hash everything via nsz; results are cached
nsptool verify --full --recheck  # ignore the cache and re-hash

# NSP <-> NSZ (verified by default)
nsptool compress "Game [0100...][v0] [US].nsp" --rm-source
nsptool decompress "Game [0100...][v0] [US].nsz" -o ./out
```

`library add`/`library organize` never overwrite: files whose titleid+version
already exist in the library are reported as `duplicate`, and name collisions
as `conflict`, both left untouched. `--fast` trusts filenames and skips
decryption.

## Dev

```sh
uv sync
uv run pytest tests/
uv run ruff check src/ tests/
uv run ty check src/
```

CI (`.github/workflows/ci.yml`) runs the same three checks on every push.

## License

[MIT](LICENSE). Depends on [nsz](https://github.com/nicoboss/nsz) (MIT).
This tool manages backups of games you own, dumped with your own console
keys; it contains no keys and no copyrighted content.
