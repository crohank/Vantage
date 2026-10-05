"""Fail when an em or en dash appears in source.

The app's font stack has no glyph for either, so they render as a tofu box
anywhere the text reaches a user: UI copy, docs, commit messages, error
strings. Code is exempt only where a dash is data being matched, which is why
the parser writes them as escapes.

    python scripts/check_dashes.py vantage tests
"""

from __future__ import annotations

import sys
from pathlib import Path

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
SUFFIXES = {".py", ".ts", ".tsx", ".md", ".yaml", ".yml", ".json", ".css", ".html"}


def main(roots: list[str]) -> int:
    offences: list[str] = []
    for root in roots:
        base = Path(root)
        paths = [base] if base.is_file() else base.rglob("*")
        for path in paths:
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            if any(part in {".venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if EM_DASH in line or EN_DASH in line:
                    offences.append(f"{path}:{number}: {line.strip()[:90]}")

    for offence in offences:
        print(f"::error::{offence}")
    if offences:
        print(f"\n{len(offences)} line(s) contain an em or en dash.")
        print("Use a comma, a period, parentheses, or restructure the sentence.")
        return 1
    print("no em or en dashes found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["."]))
