#!/usr/bin/env python3
"""Hex-dump one .stand record (13 fields starting at a 4-digit id) to see
the raw units, and test the colon/semicolon substitution hypothesis."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stand_probe import try_decode  # noqa: E402

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")


def field_spans(b, start=1):
    """yield (unit_index, text) for the le-plain stream from byte `start`"""
    fs, cur, i0 = [], [], 0
    i = start
    while i + 1 < len(b):
        v = b[i] | b[i + 1] << 8
        if v == 0x0006:
            fs.append((i0, "".join(chr(c) for c in cur)))
            cur, i0 = [], (i - start) // 2 + 1
        else:
            cur.append(v & 0xFF)
        i += 2
    fs.append((i0, "".join(chr(c) for c in cur)))
    return fs


if __name__ == "__main__":
    b = (SRC / "芳乃a_0.txt").read_bytes()
    fs = field_spans(b)
    # locate the record around field 35 ("2468")
    for k in range(30, 50):
        i0, txt = fs[k]
        byte_off = 1 + i0 * 2
        raw = b[byte_off:byte_off + len(txt) * 2]
        hexs = " ".join(f"{x:02x}" for x in raw[:40])
        print(f"{k:3d} @{byte_off:4d} {txt!r:14s} {hexs}")
