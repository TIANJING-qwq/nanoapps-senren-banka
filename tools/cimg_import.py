#!/usr/bin/env python3
"""Transcode the Mi Band pack's assets into our engine formats.

  common/bcgi/*.jpg  -> bg/<name>.bin     432x240  (VNBI, RGB565 + alpha)
  common/evig/*.jpg  -> cg/<name>.bin     432x240
  common/cimg/*.png  -> spr/<name>.bin    160x220  (every expression variant,
                                                 named exactly as the script
                                                 references it: lh01_2, fn01_3)
"""
import io
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image

ZIP = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"C:\Users\TIANJING\.dsh\attachments\v1\files\57\5726a9dcf9cbe9aaf66848e430eb94e2f08c0bc7a827ac6200b41e9806fe3bd4\千恋万花.zip")
OUT = Path("NanoApps/build/sb_full")


def pack(im, W, H, alpha=True):
    im = im.convert("RGBA")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    px = im.load()
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


def fit_sprite(im, W=160, H=220):
    im = im.convert("RGBA")
    bb = im.split()[3].getbbox()
    if bb:
        im = im.crop(bb)
    im = im.crop((0, 0, im.width, max(1, int(im.height * 0.46))))
    sc = max(W / im.width, H / im.height)
    nw, nh = max(W, round(im.width * sc)), max(H, round(im.height * sc))
    im = im.resize((nw, nh), Image.LANCZOS)
    return im.crop(((nw - W) // 2, 0, (nw - W) // 2 + W, H))


def main():
    z = zipfile.ZipFile(ZIP)
    jobs = [("bcgi", "bg", 432, 240, False),
            ("evig", "cg", 432, 240, False),
            ("cimg", "spr", 160, 220, True)]
    for src, dst, W, H, sprite in jobs:
        n = 0
        out = OUT / dst
        out.mkdir(parents=True, exist_ok=True)
        for i in z.infolist():
            if f"/{src}/" not in i.filename or not i.file_size:
                continue
            name = i.filename.split("/")[-1].rsplit(".", 1)[0]
            try:
                im = Image.open(io.BytesIO(z.read(i.filename)))
            except Exception:
                continue
            if sprite:
                im = fit_sprite(im, W, H)
            (out / (name + ".bin")).write_bytes(pack(im, W, H, sprite))
            n += 1
        print(f"{src}: {n} -> {out}")


if __name__ == "__main__":
    main()
