#!/usr/bin/env python3
"""Composite the stand with TRUE alpha (the .tlg files are 32bpp BMPs whose
4th byte is real alpha, which PIL discards and KrkrExtract's PNGs lost).

Placement: alpha-weighted correlation of each part's opaque mask against the
body's skin mask, so eyes land on the face instead of on black background."""
import sys
from pathlib import Path

import numpy as np

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")
OUT = Path("NanoApps/build")


def bgra(p):
    b = np.fromfile(p, dtype=np.uint8)
    w = int.from_bytes(b[18:22], "little")
    h = int.from_bytes(b[22:26], "little")
    return b[54:54 + w * 4 * h].reshape(h, w, 4)[::-1].copy()  # B,G,R,A


def rgb(px):
    return px[..., 2::-1]


def skin_mask(px):
    a = rgb(px).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (px[..., 3] > 128) & (r > 150) & (g > 110) & (b > 90) & \
           (r > g + 12) & (g > b + 5) & (r - b > 25)


def xcorr(big, ker):
    H, W = big.shape
    h, w = ker.shape
    fh, fw = 1 << (H - 1).bit_length(), 1 << (W - 1).bit_length()
    A = np.fft.rfft2(big.astype(np.float32), (fh, fw))
    K = np.fft.rfft2(ker[::-1, ::-1].astype(np.float32), (fh, fw))
    C = np.fft.irfft2(A * K, (fh, fw))
    return C[h - 1:h - 1 + (H - h + 1), w - 1:w - 1 + (W - w + 1)]


def best_place(body_skin, part_alpha):
    """where should the part go so its opaque pixels sit on skin?"""
    pm = (part_alpha > 128)
    n = float(pm.sum())
    if n < 30:
        return None
    sc = xcorr(body_skin, pm) / n
    dy, dx = np.unravel_index(np.argmax(sc), sc.shape)
    return float(sc[dy, dx]), int(dx), int(dy)


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


def write_png(px, path):
    from PIL import Image
    Image.fromarray(rgb(px), "RGB").save(path.with_name(path.stem + "_rgb.png"))
    im = Image.fromarray(px[..., 3], "L")
    im.save(path.with_name(path.stem + "_a.png"))
    # composite over a light background for viewing
    rgbv = rgb(px).astype(np.float32)
    a = px[..., 3:4].astype(np.float32) / 255.0
    bg = np.full_like(rgbv, 235)
    out = (rgbv * a + bg * (1 - a)).astype(np.uint8)
    Image.fromarray(out, "RGB").save(path)


def main():
    body_p = SRC / "芳乃a_0_1905.tlg"
    body = bgra(body_p)
    sk = skin_mask(body)
    print("body", body.shape, "skin px", int(sk.sum()))

    files = sorted(SRC.glob("芳乃a_0_*.tlg"))
    parts = []
    for p in files:
        b = np.fromfile(p, dtype=np.uint8)
        w = int.from_bytes(b[18:22], "little")
        if w >= 400:
            continue
        px = bgra(p)
        if (px[..., 3] > 128).sum() < 200:
            continue
        bp = best_place(sk, px[..., 3])
        if bp:
            parts.append((bp[0], p.name, bp[1], bp[2], px))
    parts.sort(reverse=True)
    print(f"{len(parts)} parts scored; top:")
    for sc, nm, dx, dy, px in parts[:16]:
        print(f"  {sc:6.2f} {nm:28s} at=({dx:4d},{dy:4d}) {px.shape[1]}x{px.shape[0]}")

    # default face: best eye part + mouth part
    eyes = [p for p in parts if p[4].shape[1] > 140 and p[4].shape[0] > 90]
    mouths = [p for p in parts if p[4].shape[0] <= 60]
    comp = body.copy()
    if eyes:
        sc, nm, dx, dy, px = eyes[0]
        print(f"\nusing eye  {nm} at ({dx},{dy})")
        blit(comp, px, dx, dy)
        eyec = (dx + px.shape[1] // 2, dy + px.shape[0] // 2)
    if mouths:
        sc, nm, dx, dy, px = mouths[0]
        # mouth: centre x under eyes, one eye-height below
        mdx = eyec[0] - px.shape[1] // 2
        mdy = eyec[1] + int((eyes[0][4].shape[0]) * 0.55)
        print(f"using mouth {nm} at ({mdx},{mdy})")
        blit(comp, px, mdx, mdy)

    OUT.mkdir(parents=True, exist_ok=True)
    write_png(comp, OUT / "face_v2.png")
    print("wrote", OUT / "face_v2.png")

    # bust preview
    from PIL import Image
    ys, xs = np.where(comp[..., 3] > 8)
    crop = comp[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    crop = crop[:int(crop.shape[0] * 0.32)]
    rgbv = rgb(crop).astype(np.float32)
    a = crop[..., 3:4].astype(np.float32) / 255.0
    bg = np.full_like(rgbv, 235)
    out = (rgbv * a + bg * (1 - a)).astype(np.uint8)
    im = Image.fromarray(out, "RGB")
    sc = max(160 / im.width, 220 / im.height)
    im = im.resize((max(160, round(im.width * sc)), max(220, round(im.height * sc))),
                   Image.LANCZOS)
    im = im.crop(((im.width - 160) // 2, 0, (im.width - 160) // 2 + 160, 220))
    im.save(OUT / "face_v2_bust.png")
    print("wrote", OUT / "face_v2_bust.png")


if __name__ == "__main__":
    main()
