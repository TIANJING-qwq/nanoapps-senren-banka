#!/usr/bin/env python3
"""Analyze a .stand table end-to-end:
  1. full row table (13 fields, hidden fields as hex)
  2. all sibling TLG layer sizes, to match f3/f4 against part w/h
  3. cross-character comparison of value ranges"""
import re
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
    s = ""
    for v in units:
        if 0x20 <= v < 0x7f:
            c = chr(v)
            s += ("0" if c == ":" else "1" if c == ";" else c)
        else:
            s += f"<{v:x}>"
    return s


def parse_rows(fs):
    """rows start at a 4-digit id field; row = id .. next id (13 fields)"""
    rows, cur = [], None
    for i, f in enumerate(fs):
        s = show(f)
        if re.fullmatch(r"\d{4}", s) and i > 16:
            if cur:
                rows.append(cur)
            cur = [i, s]
        elif cur is not None:
            cur.append(s)
    if cur:
        rows.append(cur)
    return rows


def main():
    import numpy as np
    from PIL import Image

    for char in ("芳乃", "丛雨"):
        base = SRC / f"{char}a_0.txt"
        if not base.exists():
            print(f"{char}: no a_0"); continue
        fs = fields(base.read_bytes())
        rows = parse_rows(fs)
        print(f"===== {char}a_0: {len(rows)} rows =====")
        for r in rows[:14]:
            print("  " + " | ".join(str(c) for c in r))
        # collect numeric columns 2..8 (after idx,id)
        cols = list(zip(*[[c for c in r] for r in rows]))
        print("  col value ranges:")
        for j, c in enumerate(cols[2:9], start=2):
            nums = [int(v) for v in c if re.fullmatch(r"-?\d+", v)]
            if nums:
                print(f"   col{j}: min={min(nums):5d} max={max(nums):5d} "
                      f"n={len(nums)}")
        # sibling TLG sizes
        tlgs = {}
        for p in SRC.glob(f"{char}a_0_*.tlg.png"):
            m = re.search(r"_(\d+)\.tlg\.png$", p.name)
            with Image.open(p) as im:
                tlgs[int(m.group(1))] = im.size
        sizes = sorted(set(s for s in tlgs.values() if s[0] < 500))
        print(f"  tlg layers: {len(tlgs)}; small-part sizes: {sizes[:18]}")
        # do any (f3,f4) match a tlg size?
        pairs = set()
        for r in rows:
            v = [c for c in r[2:] if re.fullmatch(r"-?\d+", c)]
            if len(v) >= 4:
                pairs.add((int(v[2]), int(v[3])))
                pairs.add((int(v[3]), int(v[2])))
        hit = pairs & set(sizes)
        print(f"  (f3,f4) matching tlg sizes: {sorted(hit)[:12]}")
        print()


if __name__ == "__main__":
    main()
