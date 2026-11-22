#!/usr/bin/env python3
"""Composite a stand from its .fgi table using krkrFgiEditor's documented
column layout (left/top/opacity/layer_id/group_layer_id) and verify the
result visually/numerically."""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")
OUT = Path("NanoApps/build")


def fields(p):
    b = p.read_bytes()
    out, cur = [], []
    i = 1                                   # stream starts at odd offset
    while i + 1 < len(b):
        v = b[i] | (b[i + 1] << 8)
        if v == 0x0006:
            out.append("".join(chr(c) if 32 <= c < 127 else "\x00" for c in cur))
            cur = []
        else:
            cur.append(v & 0xFF)
        i += 2
    out.append("".join(chr(c) if 32 <= c < 127 else "\x00" for c in cur))
    return out


def num(s):
    """the table substitutes ':' for 0 and ';' for 1"""
    s = s.replace(":", "0").replace(";", "1").strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def bgra(p):
    b = np.fromfile(p, dtype=np.uint8)
    w = int.from_bytes(b[18:22], "little")
    h = int.from_bytes(b[22:26], "little")
    px = b[54:54 + w * 4 * h].reshape(h, w, 4)[::-1]
    return np.dstack([px[..., 2], px[..., 1], px[..., 0], px[..., 3]]).copy()


def rows_of(fs):
    """a row starts at a 4-digit id"""
    rows, cur = [], None
    for i, f in enumerate(fs):
        s = f.replace(":", "0").replace(";", "1")
        if re.fullmatch(r"\d{4}", s) and i > 10:
            if cur:
                rows.append(cur)
            cur = [(i, f)]
        elif cur is not None:
            cur.append((i, f))
    if cur:
        rows.append(cur)
    return rows


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "芳乃a"
    fs = fields(SRC / f"{base}_0.txt")
    rows = rows_of(fs)
    print(f"{len(rows)} rows, {len(fs)} fields")

    # show the numeric tail of a few rows so the column meaning is visible
    print("row tails (id, then last 7 fields):")
    for r in rows[:6]:
        tail = [f for _, f in r[-7:]]
        print("  ", r[0][1], "|", " | ".join(t.replace("\x00", ".") for t in tail))

    import collections
    tailnums = [[num(t) for _, t in r[-7:]] for r in rows]
    ok = [x for x in tailnums if len(x) == 7 and all(v is not None for v in x)]
    print("column stats over", len(ok), "numeric rows:")
    for c in range(7):
        col = [x[c] for x in ok]
        print(f"  field{c}: min={min(col):5d} max={max(col):5d} "
              f"mean={sum(col)/len(col):7.1f} uniq={len(set(col))}")

    # layer images: <base>_0_<layerid>.tlg
    imgs = {}
    for p in SRC.glob(f"{base}_0_*.tlg"):
        m = re.search(r"_0_(\d+)\.tlg$", p.name)
        if m:
            imgs[int(m.group(1))] = p
    print(f"{len(imgs)} layer images, ids {min(imgs)}..{max(imgs)}")
    if not imgs:
        return

    # hypothesise: tail = [left, top, w, h, ?, opacity, type]
    built = []
    for r in rows:
        nums = [num(t) for _, t in r[-7:]]
        if len(nums) != 7 or any(v is None for v in nums):
            continue
        left, top, w, h, _, op, typ = nums
        built.append((r[0][1], left, top, w, h, op, typ))
    print(f"{len(built)} rows with a numeric tail")
    if built:
        print("  sample:", built[:4])

    # place every layer file at its row position, in row order
    ids = sorted(imgs)
    rows_sorted = sorted(built, key=lambda t: t[0])
    canvas_w = max(max(imgs[i].name and 0 or 0 for i in ids), 1200)
    canvas_w, canvas_h = 1400, 2000
    canvas = np.zeros((canvas_h, canvas_w, 4), np.uint8)
    placed = 0
    for k, (rid, left, top, w_, h_, op, typ) in enumerate(rows_sorted[:len(ids)]):
        p = imgs[ids[k]]
        part = bgra(p)
        if op < 255:
            part = part.copy()
            part[..., 3] = (part[..., 3].astype(np.uint16) * op // 100).clip(0, 255).astype(np.uint8)
        hh, ww = part.shape[:2]
        x0, y0 = left, top
        x1, y1 = min(canvas_w, x0 + ww), min(canvas_h, y0 + hh)
        if x1 <= x0 or y1 <= y0 or x0 < 0 or y0 < 0:
            continue
        s = part[:y1 - y0, :x1 - x0].astype(np.float32)
        d = canvas[y0:y1, x0:x1].astype(np.float32)
        a = s[..., 3:4] / 255.0
        d[..., :3] = s[..., :3] * a + d[..., :3] * (1 - a)
        d[..., 3:4] = np.clip(s[..., 3:4] + d[..., 3:4] * (1 - a), 0, 255)
        canvas[y0:y1, x0:x1] = d.astype(np.uint8)
        placed += 1
    ys, xs = np.where(canvas[..., 3] > 8)
    print(f"placed {placed}; content bbox x{xs.min()}-{xs.max()} y{ys.min()}-{ys.max()}")
    im = Image.fromarray(canvas, "RGBA")
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    al = im.split()[3]
    bg = Image.new("RGB", im.size, (235, 235, 235))
    bg.paste(im, (0, 0), im)
    bg.save(OUT / "fgi_test.png")
    print("wrote", OUT / "fgi_test.png", im.size)


if __name__ == "__main__":
    main()
