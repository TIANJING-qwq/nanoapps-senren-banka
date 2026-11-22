#!/usr/bin/env python3
"""Best-effort face composite: body layer + one eye part at the location the
FFT sweep agreed on, mouth part below it. Renders a 160x220 bust preview so
the placement can be judged visually."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")
OUT = Path("NanoApps/build")


def load_rgba(p):
    """RGB on black -> RGBA with black keyed out"""
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.uint8)
    lum = a.max(axis=2)
    alpha = np.clip((lum.astype(np.int16) - 18) * 255 // 26, 0, 255)
    rgba = np.dstack([a, alpha.astype(np.uint8)])
    return rgba


def place(base, part, dx, dy):
    h, w = part.shape[:2]
    H, W = base.shape[:2]
    x0, y0 = max(0, dx), max(0, dy)
    x1, y1 = min(W, dx + w), min(H, dy + h)
    if x1 <= x0 or y1 <= y0:
        return base
    sub = part[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    dst = base[y0:y1, x0:x1].astype(np.float32)
    src = sub.astype(np.float32)
    alpha = src[..., 3:4] / 255.0
    dst[..., :3] = src[..., :3] * alpha + dst[..., :3] * (1 - alpha)
    dst[..., 3:4] = np.maximum(dst[..., 3:4],
                               src[..., 3:4] * 255.0 / 255.0 * 255.0)
    base[y0:y1, x0:x1] = dst.astype(np.uint8)
    return base


def bust(rgba, out_png, w=160, h=220):
    im = Image.fromarray(rgba, "RGBA")
    alpha = np.asarray(im.getchannel("A"))
    ys, xs = np.where(alpha > 8)
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    # top 32% of the figure = head + shoulders
    im = im.crop((0, 0, im.width, int(im.height * 0.32)))
    sc = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * sc)), max(h, round(im.height * sc))),
                   Image.LANCZOS)
    im = im.crop(((im.width - w) // 2, 0, (im.width - w) // 2 + w, h))
    im.save(out_png)
    return im


if __name__ == "__main__":
    body = SRC / "芳乃a_0_1905.tlg.png"
    eye = SRC / (sys.argv[1] if len(sys.argv) > 1 else "芳乃a_0_1867.tlg.png")
    mouth = SRC / (sys.argv[2] if len(sys.argv) > 2 else "芳乃a_0_1894.tlg.png")

    base = load_rgba(body)
    print("body", base.shape)

    b = load_rgba(eye)
    ey = np.where(b[..., 3] > 20)[0]
    ex = np.where(b[..., 3] > 20)[1]
    print(f"eye content bbox {ex.min()},{ey.min()} .. {ex.max()},{ey.max()}")

    # eye part content sits at the FFT-agreed face slot
    dx = 255 - ex.min()
    dy = 650 - ey.min()
    base = place(base, b[ey.min():ey.max() + 1, ex.min():ex.max() + 1],
                 dx + ex.min(), dy + ey.min())

    m = load_rgba(mouth)
    my = np.where(m[..., 3] > 20)[0]
    mx = np.where(m[..., 3] > 20)[1]
    mh = my.max() - my.min()
    sub = m[my.min():my.max() + 1, mx.min():mx.max() + 1]
    # mouth centred under the eyes, one eye-height below
    mdx = (dx + ex.min()) + (ex.max() - ex.min()) // 2 - sub.shape[1] // 2
    mdy = (dy + ey.min()) + (ey.max() - ey.min()) + mh // 2
    print(f"mouth at ({mdx},{mdy}) size {sub.shape[1]}x{sub.shape[0]}")
    base = place(base, sub, mdx, mdy)

    OUT.mkdir(parents=True, exist_ok=True)
    full = OUT / "face_test_full.png"
    Image.fromarray(base, "RGBA").save(full)
    bust(base, OUT / "face_test_bust.png")
    print("wrote", full, "and", OUT / "face_test_bust.png")
