#!/usr/bin/env python3
"""Decode a batch of TLG5 sprites, pick representatives by color signature,
convert to engine VNBI fmt1 (RGB565 + A8), emit spr_map.tsv
(speaker name -> spr file)."""
import struct
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from tlg5 import decode_tlg5  # noqa: E402

FG = Path("NanoApps/build/sb_fg")
PNG_DIR = Path("NanoApps/build/sb_spr_png")
PACK = Path(sys.argv[1])
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 240
SPR_W, SPR_H = 54, 200

SPEAKERS = ["芳乃", "茉子", "蕾娜", "小春", "芦花", "将臣", "廉太郎",
            "ムラサメ", "丛雨", "心子", "レナ"]

PNG_DIR.mkdir(parents=True, exist_ok=True)
files = [p for p in FG.iterdir()
         if p.read_bytes()[:4] == b"TLG5"][:LIMIT]
print(f"decoding {len(files)} sprites...")

feats = []
done = 0
for p in files:
    try:
        img = decode_tlg5(p.read_bytes())
    except Exception as ex:
        continue
    out = PNG_DIR / f"{p.stem}.png"
    img.save(out)
    # color signature: avg of opaque body, plus size
    px = list(img.convert("RGBA").getdata())
    body = [c for c in px if c[3] > 240]
    if len(body) < 400:
        continue
    avg = tuple(sum(c[k] for c in body) // len(body) for k in range(3))
    feats.append((avg, img.size, p.stem))
    done += 1
print(f"decoded {done} with enough body; failures skipped")

# pick diverse representatives: greedy max-min distance in RGB space
feats.sort(key=lambda f: (f[0][0] + f[0][1] + f[0][2]))
picks = []
for f in feats:
    if not picks:
        picks.append(f)
        continue
    if all(sum(abs(f[0][k] - q[0][k]) for k in range(3)) > 60
           for q in picks):
        picks.append(f)
    if len(picks) >= 24:
        break
print(f"{len(picks)} representative sprites selected")


def to_vnbi(img: Image.Image) -> bytes:
    W, H = SPR_W, SPR_H
    im = img.convert("RGBA")
    sc = min(W / im.width, H / im.height)
    im = im.resize((max(1, round(im.width * sc)),
                    max(1, round(im.height * sc))), Image.LANCZOS)
    x = (im.width - W) // 2
    y = 0
    im = im.crop((x, y, x + W, y + H))
    px = im.load()
    out = bytearray(b"VNBI" + struct.pack("<HHB", W, H, 1))
    for yy in range(H):
        for xx in range(W):
            r, g, b, a = px[xx, yy]
            out += struct.pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
    for yy in range(H):
        for xx in range(W):
            out.append(px[xx, yy][3])
    return bytes(out)


(PACK / "spr").mkdir(parents=True, exist_ok=True)
rows = []
for i, (avg, size, stem) in enumerate(picks):
    img = Image.open(PNG_DIR / f"{stem}.png")
    (PACK / f"spr/sp{i:02d}.bin").write_bytes(to_vnbi(img))
    if i < len(SPEAKERS):
        rows.append(f"{SPEAKERS[i]}\tsp{i:02d}")
Path("NanoApps/build/spr_map.tsv").write_text("\n".join(rows),
                                              encoding="utf-8")
print(f"pack spr/: {len(picks)} files; spr_map.tsv {len(rows)} speakers")
