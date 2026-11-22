#!/usr/bin/env python3
"""v5: locate the face as the TOPMOST face-shaped skin band (the previous
version started scanning at 20 % of the height and locked onto the belly),
then place eyes/mouth by face proportions and print an ASCII self-check."""
import numpy as np
from pathlib import Path

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


def profile(sk, step=16):
    H = sk.shape[0]
    print("  row profile (skin count / x-span):")
    for y in range(0, H, step):
        band = sk[y:y + step]
        n = int(band.sum())
        if n < 20:
            continue
        xs = np.where(band.any(axis=0))[0]
        print(f"   y{y:5d}-{y + step:<5d} n={n:6d} x={xs.min():4d}..{xs.max():4d}")


def face_band(sk):
    """topmost contiguous run of rows with a face-like skin width"""
    H, W = sk.shape
    counts = sk.sum(axis=1)
    runs, cur = [], None
    for y in range(H):
        xs = np.where(sk[y])[0]
        ok = len(xs) >= 40 and (xs.max() - xs.min()) <= len(xs) * 2.2
        width = (xs.max() - xs.min()) if len(xs) else 0
        if ok and 70 <= width <= 340:
            if cur is None:
                cur = [y, y, xs.min(), xs.max()]
            else:
                cur[1] = y
                cur[2] = min(cur[2], xs.min())
                cur[3] = max(cur[3], xs.max())
        else:
            if cur:
                runs.append(tuple(cur))
                cur = None
    if cur:
        runs.append(tuple(cur))
    # topmost run tall enough to be a face
    for r in runs:
        y0, y1, x0, x1 = r
        if y1 - y0 >= 70:
            return r
    return runs[0] if runs else None


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


def to_png(px, bgv=235):
    from PIL import Image
    v = rgb(px).astype(np.float32)
    a = px[..., 3:4].astype(np.float32) / 255.0
    return Image.fromarray((v * a + np.full_like(v, bgv) * (1 - a)).astype(np.uint8), "RGB")


def main():
    from PIL import Image
    body = bgra(SRC / "芳乃a_0_1905.tlg")
    sk = skin_mask(body)
    print("body", body.shape)
    profile(sk)
    fb = face_band(sk)
    print("topmost face band:", fb)
    if not fb:
        return
    y0, y1, x0, x1 = fb
    fh, fw = y1 - y0, x1 - x0
    cx = (x0 + x1) / 2
    print(f"face {fw}x{fh} at ({x0},{y0}) centre x={cx:.0f}")

    # pick parts
    eyes, mouths = [], []
    for p in sorted(SRC.glob("芳乃a_0_*.tlg")):
        b = np.fromfile(p, dtype=np.uint8)
        if int.from_bytes(b[18:22], "little") >= 400:
            continue
        px = bgra(p)
        soft = int((px[..., 3] > 24).sum())
        if soft < 40:
            continue
        hh, ww = px.shape[:2]
        if 90 <= hh <= 170 and 140 <= ww <= 230 and soft > 2500:
            eyes.append((soft, p.name, px))
        elif hh <= 70 and ww >= 60:
            mouths.append((soft, p.name, px))
    eyes.sort(reverse=True)
    mouths.sort(reverse=True)

    comp = body.copy()
    if eyes:
        _, nm, px = eyes[0]
        hh, ww = px.shape[:2]
        dx = int(cx - ww / 2)
        dy = int(y0 + fh * 0.42 - hh / 2)
        print(f"eye {nm} at ({dx},{dy})")
        blit(comp, px, dx, dy)
    if mouths:
        _, nm, px = mouths[0]
        hh, ww = px.shape[:2]
        dx = int(cx - ww / 2)
        dy = int(y0 + fh * 0.74 - hh / 2)
        print(f"mouth {nm} at ({dx},{dy})")
        blit(comp, px, dx, dy)

    OUT.mkdir(parents=True, exist_ok=True)
    pad_x = int(fw * 1.05)
    bx0 = max(0, int(cx) - pad_x)
    bx1 = min(comp.shape[1], int(cx) + pad_x)
    by0 = max(0, int(y0 - fh * 0.55))
    by1 = min(comp.shape[0], int(y0 + fh * 2.0))
    print(f"bust crop ({bx0},{by0})..({bx1},{by1})")
    im = to_png(comp[by0:by1, bx0:bx1])
    sc = max(160 / im.width, 220 / im.height)
    im = im.resize((max(160, round(im.width * sc)), max(220, round(im.height * sc))),
                   Image.LANCZOS)
    im = im.crop(((im.width - 160) // 2, 0, (im.width - 160) // 2 + 160, 220))
    im.save(OUT / "face_v5_bust.png")

    L = np.asarray(im.convert("L")).astype(int)
    print(f"bust dark px: top-band={int((L[:73] < 90).sum())} "
          f"mid={int((L[73:146] < 90).sum())} low={int((L[146:] < 90).sum())}")
    ramp = " .:-=+*#%@"
    small = np.asarray(Image.fromarray(L.astype(np.uint8)).resize((60, 34)))
    print("ASCII bust:")
    for row in small:
        print("".join(ramp[min(9, int(v) * 10 // 256)] for v in row))
    im.save(OUT / "face_v5_bust.png")
    print("wrote", OUT / "face_v5_bust.png")


if __name__ == "__main__":
    main()
