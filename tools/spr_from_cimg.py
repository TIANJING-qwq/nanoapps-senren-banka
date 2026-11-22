#!/usr/bin/env python3
"""Build our engine sprites from the Mi Band port's finished cimg PNGs
(real drawn characters with faces) instead of the faceless E-mote layers."""
import io
import re
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image

ZIP = Path(r"C:\Users\TIANJING\.dsh\attachments\v1\files\57\5726a9dcf9cbe9aaf66848e430eb94e2f08c0bc7a827ac6200b41e9806fe3bd4\千恋万花.zip")
PACK = Path("NanoApps/build/sb_full")
W, H = 160, 220

# our stand base name -> their cimg prefix
MAP = [
    ("芳乃", "fn"), ("茉子", "mz"), ("ムラサメ", "cy"), ("叢雨", "cy"),
    ("丛雨", "cy"), ("レナ", "ln"), ("蕾娜", "ln"), ("芦花", "lh"),
    ("小春", "xc"), ("安晴", "aq"), ("心子", "xz"), ("白狗", "bnm"),
    ("祟り神", "ss"), ("みづは", "xsl"), ("比奈実", "ltl"), ("玄十郎", "mjy"),
    ("廉太郎", "g"), ("将臣", "g"),
]


def prefix_for(base):
    for key, pre in MAP:
        if key in base:
            return pre
    return None


def pack(im):
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


def fit(img):
    img = img.convert("RGBA")
    a = img.split()[3]
    bb = a.getbbox()
    if bb:
        img = img.crop(bb)
    # these are complete character artworks: keep the upper body (head +
    # torso) so the figure is large enough to read on a 160x220 slot
    img = img.crop((0, 0, img.width, max(1, int(img.height * 0.46))))
    sc = min(W / img.width, H / img.height)
    nw, nh = max(1, round(img.width * sc)), max(1, round(img.height * sc))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(img, ((W - nw) // 2, H - nh))
    return canvas


def main():
    z = zipfile.ZipFile(ZIP)
    by_pre = {}
    for i in z.infolist():
        if "/cimg/" not in i.filename or not i.file_size:
            continue
        n = i.filename.split("/")[-1]
        m = re.match(r"([a-zA-Z]+)\d+_(\d+)\.png$", n)
        if not m:
            continue
        by_pre.setdefault(m.group(1), []).append((int(m.group(2)), n))
    for k in by_pre:
        by_pre[k].sort()

    names = [ln.split("\t") for ln in
             (PACK / "spr_names.tsv").read_text(encoding="utf-8").splitlines()
             if "\t" in ln]
    out = PACK / "spr"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    used = {}
    for base, ch in names:
        pre = prefix_for(base)
        files = by_pre.get(pre, [])
        if not files:
            rows.append(f"{base}\t{ch}\tKEEP (no cimg for {base})")
            continue
        # each base of the same prefix gets a different set (a->set1, b->set2)
        sets = sorted({int(re.match(r"[a-zA-Z]+(\d+)_", fn).group(1))
                       for var, fn in files})
        k = used.get(pre, 0)
        used[pre] = k + 1
        want = "{%d}" % sets[min(k, len(sets) - 1)]
        pick = None
        for var, fn in files:
            if re.match(r"[a-zA-Z]+(\d+)_", fn).group(1) == want.strip("{}") and var == 1:
                pick = fn
                break
        if pick is None:
            pick = next((fn for var, fn in files if var == 1), files[0][1])
        data = z.read(f"common/cimg/{pick}")
        im = fit(Image.open(io.BytesIO(data)))
        (out / (ch + ".bin")).write_bytes(pack(im))
        rows.append(f"{base}\t{ch}\tcimg={pick}")
    print(f"{len(rows)} sprites")
    for r in rows:
        print("  " + r)


if __name__ == "__main__":
    main()
