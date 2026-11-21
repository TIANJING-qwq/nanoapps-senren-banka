#!/usr/bin/env python3
"""Dump context around 'cg_' occurrences in TJS files."""
import re
import sys
from pathlib import Path

f = sys.argv[1]
d = Path(f).read_bytes()
print(f"{len(d)} bytes")
hits = list(re.finditer(rb"cg_", d))
print(f"{len(hits)} cg_ hits")
for m in hits[:12]:
    lo = max(0, m.start() - 60)
    hi = min(len(d), m.start() + 120)
    seg = d[lo:hi]
    txt = seg.decode("utf-8", "replace")
    txt = "".join(c if c.isprintable() else "." for c in txt)
    print(f"@{m.start():#08x}: {txt}")
