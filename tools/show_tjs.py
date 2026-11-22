#!/usr/bin/env python3
"""Print the stand/face handling code from the game's own TJS files."""
import re
from pathlib import Path

PATCH = Path(r"K:/千恋＊万花/outPath/patch.xp3")


def decode_any(b: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "utf-8", "cp932"):
        try:
            t = b.decode(enc)
            if t.count("\x00") < len(t) // 8:
                return t
        except (UnicodeDecodeError, UnicodeError):
            continue
    return b.decode("utf-8", "replace")


def show(name, words, ctx=12):
    t = decode_any((PATCH / name).read_bytes())
    lines = t.splitlines()
    used = set()
    for i, ln in enumerate(lines):
        if any(re.search(w, ln, re.I) for w in words):
            for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1)):
                used.add(j)
    prev = None
    for j in sorted(used):
        if prev is not None and j > prev + 1:
            print(f"  ... ({j - prev - 1} lines skipped) ...")
        print(f"{j+1:5d}| {lines[j]}")
        prev = j


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "custom.tjs"
    words = sys.argv[2:] or [r"stand", r"\bface\b"]
    print(f"===== {name} =====")
    show(name, words)
