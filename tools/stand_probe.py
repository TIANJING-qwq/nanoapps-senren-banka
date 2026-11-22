#!/usr/bin/env python3
"""Brute-force the .stand stream encoding: 4 decodings x 8 start offsets,
ranked by how many printable-ASCII fields the U+0006 split produces."""
import sys
from pathlib import Path

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")


def try_decode(b: bytes, start: int, be: bool, xor: bool):
    """split on U+0006; return list[str] (latin-1 chars, one per unit)"""
    out, cur = [], []
    i = start
    while i + 1 < len(b):
        v = b[i] << 8 | b[i + 1] if be else b[i] | b[i + 1] << 8
        if xor:
            v ^= 0x00FF
        if v == 0x0006:
            out.append("".join(chr(c) for c in cur))
            cur = []
        elif 0 <= v <= 0xFF:
            cur.append(v)
        else:
            cur.append(0xFFFD)
        i += 2
    out.append("".join(chr(c) for c in cur))
    return out


def printable_fields(fs):
    n = 0
    for f in fs:
        if f and all(32 <= ord(c) < 127 for c in f):
            n += 1
    return n


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "芳乃a_0.txt"
    b = (SRC / name).read_bytes()
    results = []
    for start in range(0, 8):
        for be in (True, False):
            for xor in (True, False):
                fs = try_decode(b, start, be, xor)
                n = printable_fields(fs)
                results.append((n, start, "be" if be else "le",
                                "xor" if xor else "plain", fs))
    results.sort(key=lambda r: -r[0])
    for n, start, endian, mode, fs in results[:5]:
        print(f"fields={n:4d} start={start} {endian}-{mode} "
              f"total={len(fs)}")
    print()
    best = results[0]
    print(f"BEST: start={best[1]} {best[2]}-{best[3]} -> showing ascii fields")
    shown = 0
    for i, f in enumerate(best[4]):
        if f and all(32 <= ord(c) < 127 for c in f):
            print(f"{i:5d}: {f[:48]}")
            shown += 1
            if shown >= 60:
                break
