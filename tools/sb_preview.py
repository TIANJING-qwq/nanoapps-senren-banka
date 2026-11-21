#!/usr/bin/env python3
"""Render a contact sheet from the FULL pack: real chapter scenes
(bg + sprite + dialogue), flowchart list, save screen mock."""
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PACK = Path(sys.argv[1])
OUT = Path(sys.argv[2])
W, H = 432, 240


def load_vnbi(p: Path) -> Image.Image:
    b = p.read_bytes()
    w, h, fmt = struct.unpack_from("<HHB", b, 4)
    px = b[9:]
    img = Image.new("RGBA", (w, h))
    q = img.load()
    o = 0
    for y in range(h):
        for x in range(w):
            v = px[o] | (px[o + 1] << 8)
            o += 2
            r = ((v >> 11) & 31) << 3
            g = ((v >> 5) & 63) << 2
            bb = (v & 31) << 3
            q[x, y] = (r, g, bb, 255)
    if fmt == 1:
        a = px[o:]
        for y in range(h):
            for x in range(w):
                r, g, bb, _ = q[x, y]
                q[x, y] = (r, g, bb, a[y * w + x])
    return img


def read_str(b, pc):
    ln = struct.unpack_from("<H", b, pc)[0]
    return b[pc + 2:pc + 2 + ln].decode("utf-8", "replace"), pc + 2 + ln


def scene_from(path: Path, n_lines=2):
    b = path.read_bytes()
    nl = struct.unpack_from("<I", b, 8)[0]
    pc = 12 + 4 * nl
    bg = spr = None
    lines = []
    while pc < len(b) and len(lines) < n_lines + 6:
        op = b[pc]; pc += 1
        if op == 0:
            break
        if op == 1:
            pc += 4
        elif op in (2, 5):
            s, pc = read_str(b, pc)
            if op == 2 and not bg:
                bg = s
        elif op == 3:
            pc += 2
            s, pc = read_str(b, pc)
            if not spr:
                spr = s
        elif op == 6:
            nm, pc = read_str(b, pc)
            tx, pc = read_str(b, pc)
            lines.append((nm, tx))
        elif op == 10:
            pc += 2
        else:
            break
    return bg, spr, lines[:n_lines]


def compose(bg, spr, lines, title):
    img = Image.new("RGBA", (W, H))
    if bg and (PACK / f"bg/{bg}.bin").exists():
        img.paste(load_vnbi(PACK / f"bg/{bg}.bin"))
    else:
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, H], fill=(24, 32, 56))
    if spr and (PACK / f"spr/{spr}.bin").exists():
        s = load_vnbi(PACK / f"spr/{spr}.bin")
        img.alpha_composite(s, (W // 2 - s.width // 2, H - s.height))
    d = ImageDraw.Draw(img)
    d.rectangle([8, H - 58, W - 8, H - 8], fill=(12, 14, 22, 210))
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
    y = H - 54
    for nm, tx in lines:
        if nm:
            d.text((16, y), f"{nm}", font=font, fill=(240, 170, 150))
            y += 16
        d.text((16, y), tx[:26], font=font, fill=(240, 240, 238))
        y += 17
    d.text((12, 8), title, font=font, fill=(255, 235, 220))
    return img


cts = PACK / "chapters.tsv"
if not cts.exists():
    cts = PACK.parent / "sb_pack/chapters.tsv"
chapters = []
for ln in cts.read_text(encoding="utf-8").splitlines():
    ks, safe, n, sz = ln.split("\t")
    chapters.append((ks, n))

panels = [
    compose(*scene_from(PACK / "script.bin"), "第1章 " + chapters[0][0][:14]),
    compose(*scene_from(PACK / "ch/0001.bin"), "第2章 " + chapters[1][0][:14]),
    compose(*scene_from(PACK / "ch/0005.bin"), "第6章 レナ登場（立绘）"),
    compose(*scene_from(PACK / "ch/0086.bin"), "第87章"),
]

# flowchart panel
fl = Image.new("RGBA", (W, H), (11, 19, 43))
d = ImageDraw.Draw(fl)
font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 11)
d.text((12, 6), "流程图（88章・已访问可跳转）", font=font, fill=(240, 240, 238))
y = 28
for ks, n in chapters[::9][:13]:
    d.text((24, y), f"· {ks[:22]}", font=font, fill=(200, 214, 240))
    y += 16

# save panel
sv = Image.new("RGBA", (W, H), (11, 19, 43))
d = ImageDraw.Draw(sv)
d.text((12, 6), "存档（8槽+快速+自动）", font=font, fill=(240, 240, 238))
y = 28
for i in range(8):
    d.rectangle([16, y, 26, y + 14], fill=(60, 44, 52))
    d.text((30, y + 1), f"槽位{i + 1}  『「多多指教了哦，主人」…』",
           font=font, fill=(180, 190, 200))
    y += 19

rows = [panels + [fl], [sv, sv, sv, sv][:1] + [panels[1]] * 0]
sheet = Image.new("RGBA", (W * 2 + 8, H * 3 + 16), (8, 8, 12))
for i, im in enumerate(panels + [fl, sv]):
    sheet.alpha_composite(im, ((i % 2) * (W + 8), (i // 2) * (H + 8)))
sheet.convert("RGB").save(OUT)
print(f"wrote {OUT} ({sheet.size[0]}x{sheet.size[1]})")
