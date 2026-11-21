#!/usr/bin/env python3
"""Import all 21 background PNGs (1280x720) into the pack as bg/bbNN.bin.

Also emits bg_map.tsv: logical scene name (from PSB string tables) ->
bg file, using color heuristics. Edit the TSV and re-run sb_topack to
re-map chapter BG references; nothing else changes.
"""
import struct
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

BG_SRC = Path("NanoApps/build/sb_bg")
SCN = Path("NanoApps/build/sb_scn")
PACK = Path(sys.argv[1])

# ---- 1) collect logical bg names actually referenced by scenario volumes --
# heuristic: strings like "A_B..." with an a/b-suffix letter are bg layer names
bg_names = Counter()
for f in SCN.glob("*.psb"):
    b = f.read_bytes()
    u = struct.unpack_from("<8I", b, 8)
    stroffs, strdata = u[2], u[3]
    n = strdata - stroffs
    best = None
    for stride in (2, 3, 4):
        for skip in range(0, 12):
            cnt = (n - skip) // stride
            if cnt < 8:
                continue
            vals, ok = [], True
            for i in range(cnt):
                o = int.from_bytes(
                    b[stroffs + skip + i * stride:
                     stroffs + skip + i * stride + stride], "little")
                if vals and o < vals[-1] or o > len(b) - strdata:
                    ok = False
                    break
                vals.append(o)
            if ok and vals and vals[0] == 0 and (
                    best is None or len(vals) > len(best[2])):
                best = (stride, skip, vals)
    if not best:
        continue
    for o in best[2]:
        e = b.index(b"\x00", strdata + o)
        raw = b[strdata + o:e]
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        # bg pattern: katakana/kanji + _ + place + trailing lowercase letter
        if 4 <= len(s) <= 20 and s.count("_") == 1 and s[-1] in "abcdef" \
                and not s.startswith(("cg_", "ev", "bgm", "se", "yos", "myk")):
            bg_names[s] += 1

print(f"{len(bg_names)} distinct bg logical names; top 24:")
Path("NanoApps/build/bg_names.txt").write_text(
    "\n".join(f"{n}\t{c}" for n, c in bg_names.most_common()),
    encoding="utf-8")
for nm, c in bg_names.most_common(24):
    print(f"  {nm}  x{c}")

# ---- 2) convert the 21 PNGs -------------------------------------------
def to_vnbi(img: Image.Image) -> bytes:
    W, H = 432, 240
    im = img.convert("RGB")
    r = round(img.height * W / img.width) if img.width > img.height else H
    im = im.resize((W, max(1, round(img.height * W / img.width))), Image.LANCZOS)
    if im.width > W or im.height > H:
        # center crop after scaling to cover
        sc = max(W / img.width, H / img.height)
        im = img.convert("RGB").resize(
            (max(1, round(img.width * sc)), max(1, round(img.height * sc))),
            Image.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H))
    px = im.load()
    out = bytearray(b"VNBI" + struct.pack("<HHB", W, H, 0))
    for yy in range(H):
        for xx in range(W):
            r_, g_, b_ = px[xx, yy]
            out += struct.pack("<H", (r_ >> 3) << 11 | (g_ >> 2) << 5 | (b_ >> 3))
    return bytes(out)


bgs = [p for p in sorted(BG_SRC.glob("*"), key=lambda p: p.stat().st_size)
       if p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"]
(PACK / "bg").mkdir(parents=True, exist_ok=True)
feats = []
for i, p in enumerate(bgs):
    try:
        img = Image.open(p)
        blob = to_vnbi(img)
    except Exception as ex:
        print(f"bb{i:02d} <- {p.name[:16]} SKIP ({ex})")
        continue
    (PACK / f"bg/bb{i:02d}.bin").write_bytes(blob)
    small = img.convert("RGB").resize((8, 5))
    px = list(small.getdata())
    avg = tuple(sum(c[k] for c in px) // len(px) for k in range(3))
    lum = 0.3 * avg[0] + 0.6 * avg[1] + 0.1 * avg[2]
    warm = avg[0] - avg[2]
    feats.append((i, round(lum), warm))
    print(f"bb{i:02d} <- {p.name[:16]} {img.size} lum={lum:.0f} warm={warm:+.0f}")

# ---- 3) heuristic map: logical name -> bbNN -----------------------------
ordered = [i for i, _, _ in feats]
rows = []
names = [nm for nm, _ in bg_names.most_common(len(ordered))]
for k, nm in enumerate(names):
    rows.append(f"{nm}\tbb{ordered[k % len(ordered)]:02d}")
Path("NanoApps/build/bg_map.tsv").write_text("\n".join(rows), encoding="utf-8")
print(f"bg_map.tsv: {len(rows)} rows (heuristic — edit and re-run sb_topack)")
