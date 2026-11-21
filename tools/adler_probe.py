#!/usr/bin/env python3
"""Reverse-engineer the XP3 adler formula using a KNOWN pair:
data.xp3 has entry name c257cbcd... whose true path is
sound/↑ジャンプ１.ogg (proven by identical content). Find which
string spelling hashes (adler32) to the entry's stored hash."""
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import unpack_xp3 as ux

xp3 = "K:/千恋＊万花/data.xp3"
target_name = "c257cbcd4b46e2ae"
true_path_variants = []

with open(xp3, "rb") as f:
    t = ux.read_index(f)
    entries = list(ux.parse_table(t))

ent = next(e for e in entries if e[0] and e[0].startswith(target_name))
name, fsize, segs, adler = ent
print(f"entry {name[:16]} adler={adler:08x}")

# candidate spellings of the true path
p = "sound/↑ジャンプ１.ogg"
stem = "↑ジャンプ１"
cands = [p, p.lower(), p.upper(), stem, stem + ".ogg", "sound\\" + stem +
         ".ogg", "/" + p, "data/" + p]
cands += [c.replace("/", "\\") for c in list(cands)]
cands += ["sound\\" + stem + ".ogg"]
for enc in ("utf-8", "utf-16-le", "shift_jis", "cp932"):
    for c in cands:
        try:
            b = c.encode(enc)
        except Exception:
            continue
        h = zlib.adler32(b) & 0xFFFFFFFF
        if h == adler:
            print(f"ADLER MATCH: {c!r} ({enc}) -> {h:08x}")
            break
    else:
        continue
    break
else:
    print("no match; adler may be of the CONTENT, not the name")
    # check content adler of the extracted file
    import struct
    f2 = Path("NanoApps/build/sb_sys") / target_name
    if f2.exists():
        print("content adler:", f"{zlib.adler32(f2.read_bytes()):08x}")
