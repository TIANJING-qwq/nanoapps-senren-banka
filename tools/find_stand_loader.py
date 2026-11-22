#!/usr/bin/env python3
"""Scan the game's own TJS system files (patch.xp3) for the code that loads
the layered stand definitions, so we can read the format from the source
instead of guessing the number encoding."""
import re
import sys
from pathlib import Path

PATCH = Path(r"K:/千恋＊万花/outPath/patch.xp3")

KEYS = [r"stand", r"\bface\b", r"0x06", r"\\x06", r"leveloffset",
        r"\bmtn\b", r"emote", r"partlayer", r"filemtn"]


def decode_any(b: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "utf-8", "cp932"):
        try:
            t = b.decode(enc)
            if t.count("\x00") < len(t) // 8:
                return t
        except (UnicodeDecodeError, UnicodeError):
            continue
    return b.decode("utf-8", "replace")


def main():
    tjs = sorted(PATCH.glob("*.tjs"))
    print(f"{len(tjs)} tjs files")
    hits = {}
    for p in tjs:
        t = decode_any(p.read_bytes())
        for k in KEYS:
            n = len(re.findall(k, t, re.I))
            if n:
                hits.setdefault(p.name, {})[k] = n
    for name, ks in sorted(hits.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"{name:24s} {ks}")


if __name__ == "__main__":
    main()
