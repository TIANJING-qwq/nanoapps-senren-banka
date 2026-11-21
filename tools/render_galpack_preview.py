#!/usr/bin/env python3
"""Render preview PNGs of every GalPack screen, mimicking apps/vn/vn.c.

Landscape contact sheet: title / dialogue / choices / CG gallery /
flowchart / settings, one 432x240 render each, laid out 3x2.
"""
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCR_W, SCR_H = 432, 240
BOX_X, BOX_Y, BOX_W, BOX_H = 16, 130, 400, 104
TXT_X, TXT_Y = BOX_X + 14, BOX_Y + 34
THUMB_W, THUMB_H = 84, 48

BG = (0x0B, 0x13, 0x2B)
BTN = (0x1D, 0x35, 0x57)
INK = (0xF1, 0xFA, 0xEE)
GOLD = (0xFF, 0xD1, 0x66)
BLUE = (0x3A, 0x86, 0xFF)
ROSE = (0xE0, 0x7A, 0x5F)
SLATE = (0x45, 0x7B, 0x9D)
GREEN = (0x6F, 0xCF, 0x97)


def load_vnbi(path: Path):
    b = path.read_bytes()
    assert b[:4] == b"VNBI"
    w, h, fmt = struct.unpack_from("<HHB", b, 4)
    px = w * h
    off = 9
    img = Image.new("RGBA", (w, h))
    p = img.load()
    for j in range(h):
        for i in range(w):
            v = struct.unpack_from("<H", b, off + (j * w + i) * 2)[0]
            r = (v >> 11) & 0x1F
            g = (v >> 5) & 0x3F
            bb = v & 0x1F
            a = b[off + px * 2 + j * w + i] if fmt == 1 else 255
            p[i, j] = (r << 3 | r >> 2, g << 2 | g >> 4, bb << 3 | bb >> 2, a)
    return img


def font(sz: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", sz)
    except OSError:
        return ImageFont.load_default()


def button(d, x, y, w, h, label, border=SLATE, f=None):
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=BTN, outline=border, width=2)
    if label:
        f = f or font(16)
        bb = d.textbbox((0, 0), label, font=f)
        d.text((x + (w - bb[2]) // 2, y + (h - bb[3]) // 2 - 2), label,
               font=f, fill=INK)


def menu_item(d, x, y, w, h, label, active=False):
    """Yuzusoft-style: translucent band + left accent bar (draw_menu_item)."""
    accent = (0xE8, 0x99, 0x8D) if active else (0xB0, 0x52, 0x6D)
    text = (0xFF, 0xE9, 0xE4) if active else (0xF5, 0xF2, 0xF0)
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=(26, 20, 33, 165))
    d.rectangle([x, y, x + 2, y + h - 1], fill=accent)
    f = font(15)
    d.text((x + 14, y + (h - 15) // 2 - 2), label, font=f, fill=text)


def r_title(root: Path, save_valid: bool) -> Image.Image:
    img = load_vnbi(root / "ui" / "title.bin").convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    items = [("开始游戏", True), ("继续游戏", save_valid), ("读档", False),
             ("CG鉴赏", False), ("流程图", False), ("设置", False)]
    y = 42
    for label, hot in items:
        menu_item(d, 14, y, 118, 26, label, hot)
        y += 31
    return img


def r_igmenu(root: Path) -> Image.Image:
    img = r_dialogue(root)
    px = img.load()
    for y in range(SCR_H):
        for x in range(SCR_W):
            r, g, b, a = px[x, y]
            px[x, y] = (r * 80 >> 8, g * 80 >> 8, b * 80 >> 8, 255)
    d = ImageDraw.Draw(img, "RGBA")
    left = [("返回游戏", False), ("自动播放", False), ("快进模式", False),
            ("上一句", False), ("设置", False), ("返回标题", False)]
    right = [("存档", False), ("读档", False), ("快速存档", False),
             ("快速读档", False), ("CG鉴赏", False), ("流程图", False)]
    for i, (label, hot) in enumerate(left):
        menu_item(d, 24, 22 + i * 35, 186, 28, label, hot)
    for i, (label, hot) in enumerate(right):
        menu_item(d, 222, 22 + i * 35, 186, 28, label, hot)
    return img


def r_saveload(root: Path) -> Image.Image:
    img = Image.new("RGBA", (SCR_W, SCR_H), (0x14, 0x10, 0x21, 255))
    d = ImageDraw.Draw(img, "RGBA")
    d.text((14, 6), "存档", font=font(16), fill=INK)
    previews = ["对了，听说神社的樱花开了，周末一起去", "她的笑容一如既往。",
                None, "风很大呢……但很舒服。", None, None, None, None]
    for i, prev in enumerate(previews):
        y = 26 + i * 20
        have = prev is not None
        d.rectangle([10, y, 421, y + 17], fill=(0x2A, 0x24, 0x38, 255) if have
                    else (0x1B, 0x18, 0x26, 255))
        d.rectangle([10, y, 12, y + 17], fill=(0xB0, 0x52, 0x6D) if have
                    else (0x3A, 0x33, 0x48))
        d.text((18, y + 3), str(i + 1), font=font(11), fill=INK)
        if have:
            d.text((34, y + 1), prev, font=font(12), fill=(0xD8, 0xD2, 0xDC))
        else:
            d.text((34, y + 1), "--- 空 ---", font=font(12),
                   fill=(0x50, 0x55, 0x5E))
    yq = 26 + 8 * 20
    for k, lab in enumerate(["快速", "自动"]):
        y = yq + k * 20
        have = k == 0
        d.rectangle([10, y, 421, y + 17], fill=(0x2A, 0x24, 0x38, 255) if have
                    else (0x1B, 0x18, 0x26, 255))
        d.rectangle([10, y, 12, y + 17], fill=(0xE8, 0x99, 0x8D) if have
                    else (0x3A, 0x33, 0x48))
        d.text((18, y + 1), lab, font=font(12), fill=INK)
        if have:
            d.text((52, y + 1), "风很大呢……但很舒服。", font=font(12),
                   fill=(0xD8, 0xD2, 0xDC))
    return img


def r_dialogue(root: Path) -> Image.Image:
    img = load_vnbi(root / "bg" / "bg_school.bin").convert("RGBA")
    spr = load_vnbi(root / "spr" / "spr_demo.bin")
    img.alpha_composite(spr, ((SCR_W - spr.width) // 2, SCR_H - spr.height))
    px = img.load()
    for y in range(BOX_Y, BOX_Y + BOX_H):
        for x in range(BOX_X, BOX_X + BOX_W):
            r, g, b, a = px[x, y]
            px[x, y] = (r * 70 >> 8, g * 70 >> 8, b * 70 >> 8, 255)
    d = ImageDraw.Draw(img)
    d.rectangle([BOX_X, BOX_Y, BOX_X + BOX_W - 1, BOX_Y + BOX_H - 1],
                outline=BLUE, width=1)
    f = font(16)
    # name plate
    nb = d.textbbox((0, 0), "小雨", font=f)
    d.rectangle([BOX_X + 8, BOX_Y - 24, BOX_X + 24 + nb[2], BOX_Y - 2],
                fill=(0x2B, 0x2D, 0x42), outline=ROSE, width=1)
    d.text((BOX_X + 16, BOX_Y - 22), "小雨", font=f, fill=GOLD)
    d.text((TXT_X, TXT_Y), "“早呀！今天天气真好，要一起", font=f, fill=(0xF5, 0xF6, 0xFA))
    d.text((TXT_X, TXT_Y + 20), "去天台吗？”", font=f, fill=(0xF5, 0xF6, 0xFA))
    # menu affordance
    d.rectangle([SCR_W - 34, 6, SCR_W - 6, 26], fill=BTN)
    d.text((SCR_W - 30, 10), "MENU", font=font(10), fill=INK)
    return img


def r_choice(root: Path) -> Image.Image:
    img = r_dialogue(root)
    px = img.load()
    for y in range(0, 110):
        for x in range(SCR_W):
            r, g, b, a = px[x, y]
            px[x, y] = (r * 90 >> 8, g * 90 >> 8, b * 90 >> 8, 255)
    d = ImageDraw.Draw(img)
    button(d, 66, 18, 300, 32, "一起去天台", ROSE)
    button(d, 66, 58, 300, 32, "留在教室", ROSE)
    return img


def r_gallery(root: Path) -> Image.Image:
    img = Image.new("RGBA", (SCR_W, SCR_H), BG + (255,))
    d = ImageDraw.Draw(img)
    d.text((12, 6), "CG鉴赏", font=font(16), fill=INK)
    names = ["bg_school", "bg_room"]
    for i, nm in enumerate(names * 2):
        gx, gy = 14 + (i % 4) * 100, 30 + (i // 4) * 66
        if i < 2:
            th = load_vnbi(root / "cgt" / f"{nm}.bin")
            img.paste(th.convert("RGBA"), (gx, gy))
            d.rectangle([gx, gy, gx + THUMB_W - 1, gy + THUMB_H - 1],
                        outline=SLATE, width=1)
        else:
            d.rectangle([gx, gy, gx + THUMB_W - 1, gy + THUMB_H - 1],
                        fill=BTN, outline=(0x30, 0x34, 0x3B), width=1)
            f = font(16)
            bb = d.textbbox((0, 0), "?", font=f)
            d.text((gx + (THUMB_W - bb[2]) // 2, gy + (THUMB_H - bb[3]) // 2),
                   "?", font=f, fill=(0x50, 0x55, 0x5E))
    d.text((12, SCR_H - 20), "页 1/2", font=font(14), fill=(0x8D, 0x99, 0xAE))
    return img


def r_flow(root: Path) -> Image.Image:
    img = Image.new("RGBA", (SCR_W, SCR_H), BG + (255,))
    d = ImageDraw.Draw(img)
    d.text((12, 6), "流程图", font=font(16), fill=INK)
    items = [("一起去天台", True), ("留在教室", True), ("???", False),
             ("???", False), ("???", False)]
    y = 32
    for label, seen in items:
        if seen:
            button(d, 20, y, 300, 24, label)
            d.rectangle([340, y + 4, 348, y + 20], fill=GREEN)
        else:
            d.rectangle([20, y, 319, y + 23], fill=(0x1A, 0x1E, 0x2B),
                        outline=(0x30, 0x34, 0x3B))
            f = font(14)
            bb = d.textbbox((0, 0), "???", font=f)
            d.text((170 - bb[2] // 2, y + 4), "???", font=f,
                   fill=(0x50, 0x55, 0x5E))
        y += 26
    return img


def r_settings() -> Image.Image:
    img = Image.new("RGBA", (SCR_W, SCR_H), BG + (255,))
    d = ImageDraw.Draw(img)
    d.text((12, 6), "设置", font=font(16), fill=INK)
    button(d, 20, 40, 392, 30, "文字速度")
    d.text((330, 48), "普通", font=font(16), fill=GOLD)
    button(d, 20, 78, 392, 30, "自动播放")
    d.text((330, 86), "关", font=font(16), fill=GOLD)
    button(d, 20, 116, 392, 30, "音量")
    for i in range(8):
        c = GREEN if i < 6 else (0x30, 0x34, 0x3B)
        d.rectangle([320 + i * 12, 124, 327 + i * 12, 141], fill=c)
    return img


def main(root: Path, out_png: Path):
    root = Path(root)
    cells = [
        ("title", r_title(root, True)),
        ("dialogue", r_dialogue(root)),
        ("igmenu", r_igmenu(root)),
        ("saveload", r_saveload(root)),
        ("choice", r_choice(root)),
        ("gallery", r_gallery(root)),
        ("flowchart", r_flow(root)),
        ("settings", r_settings()),
    ]
    sheet = Image.new("RGBA", (SCR_W * 3 + 16, SCR_H * 3 + 24), (16, 16, 20, 255))
    d = ImageDraw.Draw(sheet)
    f = font(12)
    for i, (name, cell) in enumerate(cells):
        x = (i % 3) * (SCR_W + 4)
        y = (i // 3) * (SCR_H + 6)
        sheet.paste(cell, (x, y))
        d.text((x + 4, y + 2), name, font=f, fill=GOLD)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_png)
    print(f"wrote {out_png} ({sheet.width}x{sheet.height}, {len(cells)} screens)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/galpack-demo"),
         Path(sys.argv[2]) if len(sys.argv) > 2
         else Path("build/galpack-preview.png"))
