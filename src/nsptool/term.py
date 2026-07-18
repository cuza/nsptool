"""Minimal ANSI color helpers.

Colors are enabled only when stdout is a terminal and NO_COLOR is unset
(https://no-color.org/), so piped/redirected output stays clean.
"""

import os
import sys

_CODES = {
    "green": "32",
    "yellow": "33",
    "red": "31",
    "blue": "34",
    "magenta": "35",
    "dim": "2",
    "bold": "1",
}


def color_enabled() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def paint(text: str, color: str) -> str:
    if not color_enabled():
        return text
    return f"\033[{_CODES[color]}m{text}\033[0m"
