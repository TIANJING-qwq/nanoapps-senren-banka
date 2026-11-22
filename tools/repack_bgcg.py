#!/usr/bin/env python3
"""Repack bg + cg from the Mi Band pack as fmt 0 with aspect-preserving
cover-fit (the old code stretched them to 432x240, distorting the art)."""
import io
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image

ZIP = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"C:\Users\TIANJING\.dsh\attachments\v1\files\57\5726a9dcf9cbe9aaf66848e430eb94e2f08c0bc7a827ac6200b41e9806fe3bd4\千恋万花.zip")
OUT = Path("NanoApps/build/sb_full")
W, H = 432, 240


def cover(im):
    """Landscape art: cover-fill. Portrait/odd art: fit inside and letterbox,
    otherwise it degenerates into a thin vertical strip."""
    im = im.convert("RGB")
    ar = im.width / im.height
    if False:                                   # keep plain cover everywhere
        sc = min(W / im.width, H / im.height)
        nw, nh = max(1, round(im.width * sc)), max(1, round(im.height * sc))
        out = Image.new("RGB", (W, H), (0, 0, 0))
        out.paste(im.resize((nw, nh), Image.LANCZOS),
                  ((W - nw) // 2, (H - nh) // 2))
        return out
    sc = max(W / im.width, H / im.height)
    nw, nh = max(W, round(im.width * sc)), max(H, round(im.height * sc))
    im = im.resize((nw, nh), Image.LANCZOS)
    return im.crop(((nw - W) // 2, (nh - H) // 2,
                    (nw - W) // 2 + W, (nh - H) // 2 + H))


def pack0(im):
    im = cover(im)
    px = im.load()
    col = bytearray(W * H * 2)
    i = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            col[i] = v & 0xFF
            col[i + 1] = v >> 8
            i += 2
    return bytes(bytearray(b"VNBI") + struct.pack("<HHB", W, H, 0)) + bytes(col)


def main():
    z = zipfile.ZipFile(ZIP)
    for src, dst in (("bcgi", "bg"), ("evig", "cg")):
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
            (out / (name + ".bin")).write_bytes(pack0(im))
            n += 1
        print(f"{src}: {n} -> {out} (fmt 0, cover)")
    maps = dict(l.split("\t") for l in
                Path("NanoApps/build/bg_ascii.tsv").read_text(encoding="utf-8").splitlines()
                if "\t" in l)
    k = 0
    for jp, asc in maps.items():
        s = OUT / "bg" / (jp + ".bin")
        if s.exists():
            (OUT / "bg" / (asc + ".bin")).write_bytes(s.read_bytes())
            k += 1
    print(f"bg aliases refreshed: {k}")


if __name__ == "__main__":
    main()
