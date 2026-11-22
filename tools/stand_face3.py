#!/usr/bin/env python3
"""v6: list ALL skin row-runs from the very top (previous attempt only kept
runs whose width looked face-like and so started at the torso) and place the
face on the topmost genuine head run."""
import numpy as np
from pathlib import Path

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")
OUT = Path("NanoApps/build")


def bgra(p):
    b = np.fromfile(p, dtype=np.uint8)
    w = int.from_bytes(b[18:22], "little")
    h = int.from_bytes(b[22:26], "little")
    return b[54:54 + w * 4 * h].reshape(h, w, 4)[::-1].copy()


def to_png(px, bgv=235):
    from PIL import Image
    a = px[..., 3:4].astype(np.float32) / 255.0
    v = px[..., 2::-1].astype(np.float32)
    return Image.fromarray((v * a + np.full_like(v, bgv) * (1 - a)).astype(np.uint8), "RGB")


def runs(sk, minpix=40, minh=50):
    H = sk.shape[0]
    out, cur = [], None
    for y in range(H):
        xs = np.where(sk[y])[0]
        if len(xs) >= minpix:
            if cur is None:
                cur = [y, y, xs.min(), xs.max(), len(xs)]
            else:
                cur[1] = y
                cur[2] = min(cur[2], xs.min())
                cur[3] = max(cur[3], xs.max())
                cur[4] = max(cur[4], len(xs))
        else:
            if cur and cur[1] - cur[0] >= minh:
                out.append(tuple(cur))
            cur = None
    if cur and cur[1] - cur[0] >= minh:
        out.append(tuple(cur))
    return out


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


def main():
    from PIL import Image
    body = bgra(SRC / "芳乃a_0_1905.tlg")
    a = body[..., 2::-1].astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    sk = (body[..., 3] > 128) & (r > 150) & (g > 110) & (b > 90) & \
         (r > g + 12) & (g > b + 5) & (r - b > 25)
    rr = runs(sk)
    print(f"{len(rr)} skin row-runs:")
    for y0, y1, x0, x1, mx in rr:
        print(f"   y{y0:5d}-{y1:<5d} h={y1 - y0:4d} x={x0:4d}..{x1:4d} "
              f"w={x1 - x0:4d} peak={mx}")
    head = rr[0] if rr else None
    if not head:
        print("no head run"); return
    y0, y1, x0, x1, _ = head
    fh, fw = y1 - y0, x1 - x0
    cx = (x0 + x1) / 2
    print(f"head run y{y0}-{y1} h={fh} x{x0}-{x1} w={fw} cx={cx:.0f}")

    eyes, mouths = [], []
    for p in sorted(SRC.glob("芳乃a_0_*.tlg")):
        b2 = np.fromfile(p, dtype=np.uint8)
        if int.from_bytes(b2[18:22], "little") >= 400:
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
        dx, dy = int(cx - ww / 2), int(y0 + fh * 0.44 - hh / 2)
        print(f"eye {nm} at ({dx},{dy})")
        blit(comp, px, dx, dy)
    if mouths:
        _, nm, px = mouths[0]
        hh, ww = px.shape[:2]
        dx, dy = int(cx - ww / 2), int(y0 + fh * 0.78 - hh / 2)
        print(f"mouth {nm} at ({dx},{dy})")
        blit(comp, px, dx, dy)

    bx0, bx1 = max(0, int(cx) - int(fw * 1.15)), min(comp.shape[1], int(cx) + int(fw * 1.15))
    by0, by1 = max(0, int(y0 - fh * 0.5)), min(comp.shape[0], int(y0 + fh * 2.3))
    print(f"bust crop ({bx0},{by0})..({bx1},{by1})")
    im = to_png(comp[by0:by1, bx0:bx1])
    sc = max(160 / im.width, 220 / im.height)
    im = im.resize((max(160, round(im.width * sc)), max(220, round(im.height * sc))),
                   Image.LANCZOS)
    im = im.crop(((im.width - 160) // 2, 0, (im.width - 160) // 2 + 160, 220))
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / "face_v6_bust.png")
    L = np.asarray(im.convert("L")).astype(int)
    print(f"dark px: upper={int((L[:110] < 90).sum())} lower={int((L[110:] < 90).sum())}")
    ramp = " .:-=+*#%@"
    sm = np.asarray(Image.fromarray(L.astype(np.uint8)).resize((56, 30)))
    for row in sm:
        print("".join(ramp[min(9, int(v) * 10 // 256)] for v in row))
    print("wrote", OUT / "face_v6_bust.png")


if __name__ == "__main__":
    main()
