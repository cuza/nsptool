"""prod.keys bootstrapping.

The nsz package loads keys at *import* time from ~/.switch/prod.keys and calls
sys.exit() if none are found, so this must run before anything imports nsz.
We point ~/.switch/prod.keys at the keys file from the config via a symlink.
"""

import re
import sys
from pathlib import Path

SWITCH_KEYS = Path.home() / ".switch" / "prod.keys"


def ensure_keys(keys_path: Path) -> None:
    if not keys_path.is_file():
        sys.exit(f"error: keys file not found: {keys_path} (set 'keys' in the config)")

    if SWITCH_KEYS.is_file():
        # Already usable; leave the user's setup alone unless it's our stale symlink.
        if SWITCH_KEYS.is_symlink() and SWITCH_KEYS.resolve() != keys_path.resolve():
            SWITCH_KEYS.unlink()
            SWITCH_KEYS.symlink_to(keys_path)
        return

    SWITCH_KEYS.parent.mkdir(parents=True, exist_ok=True)
    if SWITCH_KEYS.is_symlink():  # broken symlink
        SWITCH_KEYS.unlink()
    SWITCH_KEYS.symlink_to(keys_path)
    print(f"Linked {SWITCH_KEYS} -> {keys_path}", file=sys.stderr)


def highest_master_key(keys_path: Path) -> int:
    """Highest master_key_XX index present in the keys file, or -1."""
    highest = -1
    for line in keys_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*master_key_([0-9a-fA-F]{2})\s*=", line)
        if m:
            highest = max(highest, int(m.group(1), 16))
    return highest
