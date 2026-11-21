#!/usr/bin/env python3
"""Try: is the XP3 adlr hash == tjsHash(unicode string)?
Test against known sb_fg hashed filenames with candidate path forms."""
import sys
from pathlib import Path


import hashlib
import sys
from pathlib import Path


fg = {p.name for p in Path("NanoApps/build/sb_fg").iterdir()}
names = ["cg_みづは.stand", "cg_アイキャッチ_レナ", "cg_sd003aa",
         "cg_bar1", "cg_芳乃.stand"]
forms = [
    lambda n: n,
    lambda n: n + ".png",
    lambda n: n + ".tlg",
    lambda n: "fgimage/" + n,
    lambda n: "fgimage/" + n + ".png",
    lambda n: "fgimage720/" + n,
    lambda n: n.upper(),
    lambda n: n.lower(),
]
for n in names:
    for i, f in enumerate(forms):
        v = f(n)
        for enc in ("utf-8", "utf-16-le", "shift_jis"):
            h = hashlib.md5(v.encode(enc)).hexdigest()
            if h in fg:
                print(f"MATCH: {n!r} form{i} {enc} {v!r} -> {h}")
                break
        else:
            continue
        break
    else:
        print(f"no match for {n[:20]!r}")
