#!/usr/bin/env python3
"""Place the face parts by face geometry (no reliance on the undecoded
.stand transform): fit the face skin oval, then put the eye part centred at
45 % of the face height and the mouth at 72 %."""
import sys
from pathlib import Path

import numpy as np

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")
OUT = Path("NanoApps/build")


def bgra(p):
    b = np.fromfile(p, dtype=np.uint8)
    w = int.from_bytes(b[18:22], "little")
    h = int.from_bytes(b[22:26], "little")
    return b[54:54 + w * 4 * h].reshape(h, w, 4)[::-1].copy()


def rgb(px):
    return px[..., 2::-1]


def skin_mask(px):
    a = rgb(px).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (px[..., 3] > 128) & (r > 150) & (g > 110) & (b > 90) & \
           (r > g + 12) & (g > b + 5) & (r - b > 25)


def face_box(sk):
    """widest dense skin blob in the upper 55 % of the figure"""
    H = sk.shape[0]
    rows = []
    for y in range(int(H * 0.20), int(H * 0.55)):
        xs = np.where(sk[y])[0]
        if len(xs) < 70:
            continue
        span = xs.max() - xs.min()
        if span > len(xs) * 2.0:            # scattered (arms)
            continue
        rows.append((y, xs.min(), xs.max(), len(xs)))
    if not rows:
        return None
    # the face is the contiguous run of rows with the biggest density
    ys = [r[0] for r in rows]
    # take the run containing the row with max skin count
    peak = max(rows, key=lambda r: r[3])
    ys_sel = [y for y in ys if abs(y - peak[0]) <= 130]
    y0, y1 = min(ys_sel), max(ys_sel)
    sel = [r for r in rows if y0 <= r[0] <= y1]
    x0 = min(r[1] for r in sel)
    x1 = max(r[2] for r in sel)
    return x0, y0, x1, y1


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


def to_png(px, path, bgv=235):
    from PIL import Image
    v = rgb(px).astype(np.float32)
    a = px[..., 3:4].astype(np.float32) / 255.0
    return Image.fromarray((v * a + np.full_like(v, bgv) * (1 - a)).astype(np.uint8), "RGB")


def main():
    body = bgra(SRC / "芳乃a_0_1905.tlg")
    sk = skin_mask(body)
    fb = face_box(sk)
    print("face box", fb)
    x0, y0, x1, y1 = fb
    fw, fh = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    print(f"face {fw}x{fh} centre {cx:.0f},{y0 + fh / 2:.0f}")

    files = sorted(SRC.glob("芳乃a_0_*.tlg"))
    eyes, mouths = [], []
    for p in files:
        b = np.fromfile(p, dtype=np.uint8)
        w = int.from_bytes(b[18:22], "little")
        if w >= 400:
            continue
        px = bgra(p)
        n = int((px[..., 3] > 128).sum())
        soft = int((px[..., 3] > 24).sum())
        if soft < 40:
            continue
        hh, ww = px.shape[:2]
        if 90 <= hh <= 170 and 140 <= ww <= 230 and n > 2500:
            eyes.append((soft, p.name, px))
        elif hh <= 70 and ww >= 60 and soft >= 40:
            mouths.append((soft, p.name, px))
    eyes.sort(reverse=True)
    mouths.sort(reverse=True)
    print(f"{len(eyes)} eye candidates, {len(mouths)} mouth candidates")
    for n, nm, px in eyes[:3]:
        print(f"   eye  {nm} {px.shape[1]}x{px.shape[0]} n={n}")
    for n, nm, px in mouths[:3]:
        print(f"   mouth {nm} {px.shape[1]}x{px.shape[0]} n={n}")

    comp = body.copy()
    if eyes:
        n, nm, px = eyes[0]
        hh, ww = px.shape[:2]
        dx = int(cx - ww / 2)
        dy = int(y0 + fh * 0.42 - hh / 2)
        print(f"eye  {nm} at ({dx},{dy})")
        blit(comp, px, dx, dy)
    if mouths:
        n, nm, px = mouths[0]
        hh, ww = px.shape[:2]
        dx = int(cx - ww / 2)
        dy = int(y0 + fh * 0.74 - hh / 2)
        print(f"mouth {nm} at ({dx},{dy})")
        blit(comp, px, dx, dy)

    OUT.mkdir(parents=True, exist_ok=True)
    to_png(comp, OUT / "face_v3.png")

    # Bust framing MUST be anchored on the face, not on a fixed slice of the
    # figure: the face sits at 34-50 % of this stand, so "top 32 %" cut it off.
    pad_x = int(fw * 0.95)
    bx0 = max(0, int(cx) - pad_x)
    bx1 = min(comp.shape[1], int(cx) + pad_x)
    by0 = max(0, int(y0 - fh * 0.45))
    by1 = min(comp.shape[0], int(y0 + fh * 1.95))
    print(f"bust crop ({bx0},{by0})..({bx1},{by1})")
    crop = comp[by0:by1, bx0:bx1]
    im = to_png(crop, OUT / "face_v3_bust.png")
    sc = max(160 / im.width, 220 / im.height)
    im = im.resize((max(160, round(im.width * sc)), max(220, round(im.height * sc))),
                   Image.LANCZOS)
    im = im.crop(((im.width - 160) // 2, 0, (im.width - 160) // 2 + 160, 220))
    im.save(OUT / "face_v3_bust.png")

    # numeric proof that facial features are inside the bust
    arr = np.asarray(im.convert("L")).astype(int)
    eye_band = arr[int(220 * 0.30):int(220 * 0.55)]
    mouth_band = arr[int(220 * 0.62):int(220 * 0.82)]
    print(f"bust {im.size}; dark px eye-band={int((eye_band < 90).sum())} "
          f"mouth-band={int((mouth_band < 90).sum())}")
    print("wrote", OUT / "face_v3_bust.png")


if __name__ == "__main__":
    from PIL import Image  # noqa: F401
    main()
