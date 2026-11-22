#!/usr/bin/env python3
"""Render a grid of face-placement candidates so one visual pick settles the
two unknowns (part scale and vertical offset)."""
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")
OUT = Path("NanoApps/build")
FACE_CX = 317

SCALES = [0.62, 0.72, 0.82]
EYE_CY = [175, 195, 215]


def bgra(p):
    b = np.fromfile(p, dtype=np.uint8)
    w = int.from_bytes(b[18:22], "little")
    h = int.from_bytes(b[22:26], "little")
    return b[54:54 + w * 4 * h].reshape(h, w, 4)[::-1].copy()


def to_png(px, bgv=235):
    al = px[..., 3:4].astype(np.float32) / 255.0
    v = px[..., 2::-1].astype(np.float32)
    return Image.fromarray((v * al + np.full_like(v, bgv) * (1 - al)
                            ).astype(np.uint8), "RGB")


def blit(dst, src, dx, dy):
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0 = max(0, dx), max(0, dy)
    x1, y1 = min(W, dx + w), min(H, dy + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - dy:y1 - dy, x0 - dx:x1 - dx].astype(np.float32)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    a = s[..., 3:4] / 255.0
    d[..., :3] = s[..., :3] * a + d[..., :3] * (1 - a)
    d[..., 3:4] = np.clip(s[..., 3:4] + d[..., 3:4] * (1 - a), 0, 255)
    dst[y0:y1, x0:x1] = d.astype(np.uint8)


def scale_part(px, k):
    im = Image.fromarray(px, "RGBA")
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))),
                   Image.LANCZOS)
    return np.asarray(im).copy()


def main():
    body = bgra(SRC / "芳乃a_0_1905.tlg")
    eye = bgra(SRC / "芳乃a_0_1880.tlg")
    mouth = bgra(SRC / "芳乃a_0_1894.tlg")

    cells = []
    for sc in SCALES:
        for ey in EYE_CY:
            e = scale_part(eye, sc)
            m = scale_part(mouth, sc)
            comp = body.copy()
            ys, xs = np.where(e[..., 3] > 128)
            ex = int(round(FACE_CX - xs.mean()))
            eyy = int(round(ey - ys.mean()))
            blit(comp, e, ex, eyy)
            ys2, xs2 = np.where(m[..., 3] > 24)
            my = int(round(ey + (e.shape[0] * 0.62) - ys2.mean()))
            blit(comp, m, int(round(FACE_CX - xs2.mean())), my)
            Hc = 320
            Wc = int(round(Hc * 160 / 220))
            im = to_png(comp[60:60 + Hc, FACE_CX - Wc // 2:FACE_CX - Wc // 2 + Wc])
            im = im.resize((160, 220), Image.LANCZOS)
            cells.append((sc, ey, im))

    cols, rows = 3, len(SCALES)
    pad, label = 6, 14
    sheet = Image.new("RGB", (cols * (160 + pad) + pad,
                              rows * (220 + label + pad) + pad), (28, 32, 44))
    d = ImageDraw.Draw(sheet)
    for i, (sc, ey, im) in enumerate(cells):
        r, c = i // cols, i % cols
        x = pad + c * (160 + pad)
        y = pad + r * (220 + label + pad)
        sheet.paste(im, (x, y + label))
        d.text((x + 2, y), f"scale {sc:.2f}  eye_y {ey}", fill=(240, 240, 240))
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / "face_grid.png")
    print("grid:", sheet.size, "->", OUT / "face_grid.png")
    for i, (sc, ey, _) in enumerate(cells):
        print(f"  cell {i + 1}: scale {sc} eye_y {ey}")


if __name__ == "__main__":
    main()
