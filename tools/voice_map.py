#!/usr/bin/env python3
"""Build voice name -> hash-file mapping from the XP3 index itself.
XP3 file entries carry hash=adler32(lowercase storage path) and the
release-wiped name (md5 hex). We enumerate the tjs voice names, try
their adler32 under several path spellings, and match against the
index hash table. Output: voice_map.tsv (name \t hashfile)"""
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import unpack_xp3 as ux  # reuse its index reader

xp3 = sys.argv[1] if len(sys.argv) > 1 else "K:/千恋＊万花/voice.xp3"
tjs = Path("NanoApps/build/sb_tjs.tsv")
OUT = Path("NanoApps/build/voice_map.tsv")

entries = []
with open(xp3, "rb") as f:
    t = ux.read_index(f)
    entries = list(ux.parse_table(t))   # (name, fsize, segs, adler)
print(f"index: {len(entries)} entries")
by_adler = {}
for name, fsize, segs, adler in entries:
    by_adler[adler & 0xFFFFFFFF] = name

names = set()
for ln in tjs.read_text(encoding="utf-8").splitlines():
    p = ln.split("\t")
    if len(p) >= 4 and p[3]:
        names.add(p[3])
print(f"tjs voice names: {len(names)}")


def variants(n):
    for ext in (".ogg", ".wav", ""):
        for pre in ("voice/", "voice\\", "Voice/", ""):
            yield f"{pre}{n}{ext}"


hit = 0
rows = []
for n in sorted(names):
    for v in variants(n):
        h = zlib.adler32(v.encode("utf-8")) & 0xFFFFFFFF
        if h in by_adler:
            rows.append(f"{n}\t{by_adler[h]}")
            hit += 1
            break
OUT.write_text("\n".join(rows), encoding="utf-8")
print(f"mapped {hit}/{len(names)} -> {OUT}")
