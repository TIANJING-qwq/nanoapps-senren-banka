#!/usr/bin/env python3
"""Precise bg import: PSB logical bg names (from scenario dumps) matched
1:1 by name against KrkrExtract's real-name bgimage PNGs -> VNBI bg files
+ exact bg_map.tsv. Falls back to previous heuristic map for misses."""
import struct
import sys
from pathlib import Path

from PIL import Image

BG_SRC = Path("K:/千恋＊万花/outPath/bgimage720.xp3")
PACK = Path(sys.argv[1])
W, H = 432, 240

# 1) real-name PNGs (skip masks: extremely dark/bright)
reals = {}
for p in BG_SRC.glob("*.png"):
    nm = p.stem
    if nm.startswith(("ev", "rule")):
        continue
    reals[nm] = p

# 2) logical names used by the story (from psb string tables, saved earlier)
logical = []
for ln in Path("NanoApps/build/bg_names.txt").read_text(
        encoding="utf-8").splitlines():
    if ln and not ln.startswith("#"):
        logical.append(ln.split("\t")[0])
print(f"{len(reals)} real bg PNGs; {len(logical)} logical names")


def to_vnbi(img):
    im = img.convert("RGB")
    sc = min(W / im.width, H / im.height)
    im = im.resize((max(1, round(im.width * sc)),
                    max(1, round(im.height * sc))), Image.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H))
    px = im.load()
    out = bytearray(b"VNBI" + struct.pack("<HHB", W, H, 0))
    for yy in range(H):
        for xx in range(W):
            r, g, b = px[xx, yy]
            out += struct.pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
    return bytes(out), im


# 3) exact-name matches (base name without trailing a/b/c variant letter)
import re
def base_of(nm):
    return re.sub(r"[a-z]$", "", nm)


matched = {}
for lg in logical:
    if lg in reals:
        matched[lg] = reals[lg]
    elif base_of(lg) in reals:
        matched[lg] = reals[base_of(lg)]
print(f"exact matches: {len(matched)} / {len(logical)}")

(PACK / "bg").mkdir(parents=True, exist_ok=True)
rows = []
for i, (lg, p) in enumerate(sorted(matched.items())):
    with Image.open(p) as img:
        blob, im2 = to_vnbi(img)
        px = list(im2.resize((8, 8)).getdata())
        lum = sum(sum(c) for c in px) // (64 * 3)
    if lum < 6 or lum > 250:            # mask/solid images
        continue
    fid = f"bb{i:02d}"
    (PACK / f"bg/{fid}.bin").write_bytes(blob)
    rows.append(f"{lg}\t{fid}")

# keep old heuristic rows for logical names we could not match precisely
old = {}
for ln in Path("NanoApps/build/bg_map.tsv").read_text(
        encoding="utf-8").splitlines():
    if "\t" in ln:
        k, v = ln.split("\t", 1)
        old[k] = v
for lg in logical:
    if lg not in matched and lg in old:
        rows.append(f"{lg}\t{old[lg]}")
Path("NanoApps/build/bg_map.tsv").write_text("\n".join(rows),
                                              encoding="utf-8")
print(f"bg_map.tsv: {len(rows)} rows ({len(matched)} exact); "
      f"bg files written to {PACK}/bg")
