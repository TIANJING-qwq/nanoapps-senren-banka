#!/usr/bin/env python3
"""Validate the positional-alignment hypothesis: XP3 table order (=
unpack/creation order) should equal sorted voice-name order. Test:
Spearman correlation between line length (from tjs, per voice name in
sorted order) and audio duration (granule of last OGG page)."""
import re
import struct
import sys
from pathlib import Path

V = Path("NanoApps/build/sb_voice")
tjs = Path("NanoApps/build/sb_tjs.tsv")

# voice name -> text length (first occurrence)
name_len = {}
for ln in tjs.read_text(encoding="utf-8").splitlines():
    p = ln.split("\t")
    if len(p) >= 4 and p[3]:
        name_len.setdefault(p[3], len(p[2]))
names_sorted = sorted(name_len)
print(f"tjs voices: {len(name_len)}; first: {names_sorted[:3]}")


def ogg_dur(path):
    b = path.read_bytes()
    i = b.rfind(b"OggS")
    if i < 0 or i + 14 > len(b):
        return None
    gran = struct.unpack_from("<q", b, i + 6)[0]
    return gran / 44100.0


files = [p for p in V.iterdir() if p.name[0] != "$"]
files.sort(key=lambda p: p.stat().st_ctime)
print(f"voice files (ctime=table order): {len(files)}; "
      f"first: {files[0].name[:12]}")

# compare in windows: take the first 400 of each (assuming same start)
N = 400
durs = []
for p in files[:N]:
    d = ogg_dur(p)
    if d is None:
        durs.append(0.0)
    else:
        durs.append(d)
lens = [name_len.get(n, 0) for n in names_sorted[:N]]
pairs = [(a, b) for a, b in zip(lens, durs) if b > 0]
if len(pairs) < 50:
    print("too few durations parsed"); sys.exit(1)


def rank(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0] * len(v)
    for i, ix in enumerate(order):
        r[ix] = i
    return r


xs = [a for a, b in pairs]
ys = [b for a, b in pairs]
rx, ry = rank(xs), rank(ys)
n = len(xs)
mx, my = sum(rx) / n, sum(ry) / n
cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
vx = sum((a - mx) ** 2 for a in rx) ** .5
vy = sum((b - my) ** 2 for b in ry) ** .5
print(f"rho = {cov / (vx * vy):.3f} over {n} pairs "
      f"(>0.6 = aligned, ~0 = wrong)")
print("sample (len, dur):", list(zip(xs[:6], [round(y, 1) for y in ys[:6]])))
