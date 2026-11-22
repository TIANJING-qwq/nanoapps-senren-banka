#!/usr/bin/env python3
"""Batch-compose every character's bust with a face and write engine sprites.

Per character:
  * pick the largest stand layer (.tlg = 32bpp BMP, true alpha)
  * find the head skin band -> face centre
  * pick the best eye part (165x129-ish) and mouth part, scale them to
    0.82 (chosen visually on 芳乃), place eye centroid on the face centre and
    the mouth 0.62*eye_height below
  * crop a 160:220 bust around the face and pack as VNBI (RGB565 + alpha)
"""
import re
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")
PACK = Path("NanoApps/build/sb_full")
W, H = 160, 220
PART_SCALE = 0.82
MOUTH_DY = 0.62          # mouth top = eye top + 0.62 * eye height


def bgra(p):
    b = np.fromfile(p, dtype=np.uint8)
    w = int.from_bytes(b[18:22], "little")
    h = int.from_bytes(b[22:26], "little")
    return b[54:54 + w * 4 * h].reshape(h, w, 4)[::-1].copy()


def isize(p):
    with open(p, "rb") as fh:
        hdr = fh.read(26)
    return (int.from_bytes(hdr[18:22], "little"),
            int.from_bytes(hdr[22:26], "little"))


def skin(px):
    a = px[..., 2::-1].astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (px[..., 3] > 128) & (r > 150) & (g > 110) & (b > 90) & \
           (r > g + 12) & (g > b + 5) & (r - b > 25)


def face_centre(px):
    """skin centroid of the head band (the face, not the chest)"""
    sk = skin(px)
    h = px.shape[0]
    y0, y1 = int(h * 0.06), int(h * 0.30)
    sub = sk[y0:y1]
    n = int(sub.sum())
    if n < 500:
        return None
    ys, xs = np.where(sub)
    return float(xs.mean()), float(y0 + ys.mean()), (int(xs.min()), int(xs.max()),
                                                    y0 + int(ys.min()),
                                                    y0 + int(ys.max()))


def blit(dst, src, dx, dy):
    hh, ww = src.shape[:2]
    Hh, Ww = dst.shape[:2]
    x0, y0 = max(0, dx), max(0, dy)
    x1, y1 = min(Ww, dx + ww), min(Hh, dy + hh)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - dy:y1 - dy, x0 - dx:x1 - dx].astype(np.float32)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    a = s[..., 3:4] / 255.0
    d[..., :3] = s[..., :3] * a + d[..., :3] * (1 - a)
    d[..., 3:4] = np.clip(s[..., 3:4] + d[..., 3:4] * (1 - a), 0, 255)
    dst[y0:y1, x0:x1] = d.astype(np.uint8)


def scale_part(px, k):
    im = Image.fromarray(px, "RGBA").resize(
        (max(1, round(px.shape[1] * k)), max(1, round(px.shape[0] * k))),
        Image.LANCZOS)
    return np.asarray(im).copy()


def pack(canvas):
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
    return bytes(bytearray(b"VNBI") + struct.pack("<HHB", W, H, 1)) + \
        bytes(col) + bytes(alp)


def main():
    # prefer the "_0_" pose variant: that is the layout validated on 芳乃
    files = sorted(SRC.glob("*_0_*.tlg")) or sorted(SRC.glob("*.tlg"))
    groups = {}
    for p in files:
        base = p.stem.split("_")[0]
        if not base:
            continue
        try:
            w, h = isize(p)
        except Exception:
            continue
        if w < 300 or h < 600:
            continue
        area = w * h
        if base not in groups or area > groups[base][0]:
            groups[base] = (area, p)

    names = []
    tsv = PACK / "spr_names.tsv"
    if tsv.exists():
        names = [ln.split("\t") for ln in
                 tsv.read_text(encoding="utf-8").splitlines() if "\t" in ln]
    order = {b: n for b, n in names}

    # parts for each base ("芳乃a_0_*" -> parts of base "芳乃a")
    part_cache = {}
    for base in groups:
        eyes, mouths = [], []
        for p in SRC.glob(f"{base}_*.tlg"):
            try:
                w, h = isize(p)
            except Exception:
                continue
            if w >= 400:
                continue
            px = bgra(p)
            soft = int((px[..., 3] > 24).sum())
            if soft < 40:
                continue
            if 90 <= h <= 170 and 140 <= w <= 230 and soft > 2500:
                eyes.append((soft, p, px))
            elif h <= 70 and w >= 60:
                mouths.append((soft, p, px))
        eyes.sort(key=lambda t: -t[0])
        mouths.sort(key=lambda t: -t[0])
        part_cache[base] = (eyes[0][2] if eyes else None,
                            mouths[0][2] if mouths else None)

    out = PACK / "spr"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, base in enumerate(sorted(groups)):
        name = order.get(base, f"ch{i:02d}")
        body = bgra(groups[base][1])
        fc = face_centre(body)
        eye, mouth = part_cache[base]
        ok = fc is not None and eye is not None and len(np.where(eye[..., 3] > 128)[0]) > 0
        if ok:
            cx, cy, box = fc
            comp = body.copy()
            e = scale_part(eye, PART_SCALE)
            ys, xs = np.where(e[..., 3] > 128)
            if len(xs) == 0:
                ys, xs = np.where(e[..., 3] > 24)
            if len(xs) == 0:
                raise ValueError("empty eye part")
            eyx = int(round(cx - xs.mean()))
            eyy = int(round(cy - ys.mean()))
            blit(comp, e, eyx, eyy)
            if mouth is not None:
                m = scale_part(mouth, PART_SCALE)
                ys2, xs2 = np.where(m[..., 3] > 24)
                if len(xs2) == 0:
                    ys2, xs2 = np.where(m[..., 3] > 8)
                blit(comp, m, int(round(cx - xs2.mean())),
                     int(round(eyy + e.shape[0] * MOUTH_DY - ys2.mean())))
            fh = box[3] - box[2]
            y_top = max(0, box[2] - int(fh * 0.5))
            y_bot = min(comp.shape[0], box[3] + int(fh * 0.5))
            hc = y_bot - y_top
            wc = int(round(hc * W / H))
            x0 = int(round(cx - wc / 2))
            x0 = max(0, min(comp.shape[1] - wc, x0))
            crop = comp[y_top:y_top + hc, x0:x0 + wc]
            im = Image.fromarray(crop, "RGBA").resize((W, H), Image.LANCZOS)
            rows.append(f"{base}\t{name}\tface=({cx:.0f},{cy:.0f}) "
                        f"crop=({x0},{y_top},{wc},{hc})")
        else:
            # no face evidence on this stand: fall back to a full-body thumb
            a = body[..., 3]
            bb = Image.fromarray((a > 8).astype(np.uint8) * 255).getbbox()
            im2 = Image.fromarray(body, "RGBA")
            if bb:
                im2 = im2.crop(bb)
            sc = min(W / im2.width, H / im2.height)
            im2 = im2.resize((max(1, round(im2.width * sc)),
                              max(1, round(im2.height * sc))), Image.LANCZOS)
            im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            im.paste(im2, ((W - im2.width) // 2, H - im2.height))
            rows.append(f"{base}\t{name}\tfallback=fullbody")
        (out / (name + ".bin")).write_bytes(pack(im))

    (PACK / "spr_names.tsv").write_text(
        "\n".join(r.split("\t")[0] + "\t" + r.split("\t")[1] for r in rows),
        encoding="utf-8")
    print(f"{len(rows)} sprites -> {out}")
    for r in rows:
        print("  " + r)


if __name__ == "__main__":
    main()
