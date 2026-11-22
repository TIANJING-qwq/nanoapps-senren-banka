#!/usr/bin/env python3
"""Import character stand sprites from the fgimage1080 PNGs: for each
character take the largest complete sprite image and pack it as a 160x220
VNBI fmt1 (RGB565 + A8 alpha) under spr/<name>.bin + spr_names.tsv.

Usage: sb_sprimport2.py <fgimage1080 dir> <pack dir>
"""
import re
import struct
import sys
from pathlib import Path

from PIL import Image

W, H = 160, 220


def pack_spr(img: Image.Image) -> bytes:
    # Originals are full-body (953x1632). Squeezing that into 160x220 makes
    # the face a few pixels -> "no face". Crop to the upper body (the same
    # framing the original game uses) so the face fills a real area.
    W0, H0 = img.size
    if H0 > W0:                       # portrait stand: take top 55 %
        img = img.crop((0, 0, W0, int(H0 * 0.55)))
    im = img.convert("RGBA")
    # The KrkrExtract PNGs lost the alpha channel — the stand background is
    # solid black. Key near-black out with a soft edge so sprites over
    # backgrounds don't show the black box.
    if im.getextrema()[3][0] == 255:            # fully opaque -> key black
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                r, g, b, _ = px[x, y]
                lum = max(r, g, b)
                if lum < 20:
                    px[x, y] = (0, 0, 0, 0)
                elif lum < 44:                  # soft edge
                    px[x, y] = (r, g, b, int(255 * (lum - 20) / 24))
    # COVER-fill 160x220: the face must fill real pixels, so scale until both
    # dimensions are covered and crop the overflow (never letterbox).
    sc = max(W / im.width, H / im.height)
    nw, nh = max(W, round(im.width * sc)), max(H, round(im.height * sc))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(im, ((W - nw) // 2, (H - nh) // 2))   # centre both axes
    px = canvas.load()
    col = bytearray(W * H * 2)
    alp = bytearray(W * H)
    i = 0
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            col[i] = v & 0xFF
            col[i + 1] = v >> 8
            alp[i // 2] = a
            i += 2
    return (bytes(bytearray(b"VNBI") + struct.pack("<HHB", W, H, 1))
            + bytes(col) + bytes(alp))


src = Path(sys.argv[1])
pack = Path(sys.argv[2])
out = pack / "spr"
out.mkdir(parents=True, exist_ok=True)

# group by base name like "芳乃a" (strip _<digits> suffixes)
groups = {}
for p in src.glob("*.png"):
    stem = p.stem
    if stem.endswith(".tlg"):
        stem = stem[:-4]
    m = re.match(r"^([^_]+?)(?:_\d+)?$", stem)
    if not m:
        continue
    base = m.group(1)
    try:
        im = Image.open(p)
        w, h = im.size
    except Exception:
        continue
    if w < 300 or h < 600:          # full stands only, skip face diffs
        continue
    area = w * h
    if base not in groups or area > groups[base][0]:
        groups[base] = (area, p)

rows = []
for i, (base, (area, p)) in enumerate(sorted(groups.items())):
    name = f"ch{i:02d}"
    with Image.open(p) as im:
        (out / (name + ".bin")).write_bytes(pack_spr(im))
    rows.append(f"{base}\t{name}")
(pack / "spr_names.tsv").write_text("\n".join(rows), encoding="utf-8")
print(f"{len(rows)} characters -> {out}")
for r in rows[:10]:
    print(" ", r)
