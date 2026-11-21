#!/usr/bin/env python3
"""Find sprite-logical-name -> hash pairs in TJS bytecode files."""
import re
import sys
from pathlib import Path

for f in sys.argv[1:]:
    d = Path(f).read_bytes()
    for m in re.finditer(rb"cg_[\w\xa0-\xff]+?\.stand[\w\.]*", d):
        lo = max(0, m.start() - 120)
        hi = min(len(d), m.end() + 160)
        ctx = d[lo:hi]
        # any 32-hex nearby?
        h = re.findall(rb"[0-9a-f]{32}", ctx)
        print(f"{Path(f).name[:12]} @{m.start():#08x} "
              f"{m.group(0)[:40].decode('utf-8', 'replace')!r}")
        for x in h[:3]:
            print(f"    hash: {x.decode()}")
        if not h:
            txt = re.findall(rb"[\x20-\x7e\xb0-\xff]{8,}", ctx)
            for t in txt[:3]:
                print(f"    ctx: {t[:60]!r}")
