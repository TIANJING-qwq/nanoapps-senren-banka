#!/usr/bin/env python3
"""Full record dump of a .stand file with the 0/1 un-substitution applied.
Record layout hypothesis: 13 fields per part row."""
import sys
from pathlib import Path

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")


def fields(b, start=1):
    out, cur = [], []
    i = start
    while i + 1 < len(b):
        v = b[i] | b[i + 1] << 8
        if v == 0x0006:
            out.append(cur)
            cur = []
        else:
            cur.append(v)
        i += 2
    out.append(cur)
    return out


def show(units):
    """render a field: ascii digits/letters kept, ':'->'0' ';'->'1',
    control units as <hex>"""
    s = ""
    for v in units:
        if 0x20 <= v < 0x7f:
            c = chr(v)
            if c == ":":
                c = "0"
            elif c == ";":
                c = "1"
            s += c
        else:
            s += f"<{v:02x}>"
    return s


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "芳乃a_0.txt"
    b = (SRC / name).read_bytes()
    fs = fields(b)
    print(f"{len(fs)} fields")
    for i, f in enumerate(fs[:140]):
        if i < 20:
            print(f"{i:4d}| {show(f)}")
            continue
        if show(f).isdigit():
            print(f"{i:4d}| {show(f)}   <== row id")
