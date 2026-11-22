#!/usr/bin/env python3
"""Render a 1:1 preview of the title and settings screens using the exact
coordinates from vn.c, so layout can be checked without the device."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 432, 240
SCALE = 2

FONT_PATHS = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msgothic.ttc",
]


def cjk_font(size):
    for p in FONT_PATHS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def new_page():
    img = Image.new("RGB", (W * SCALE, H * SCALE), (11, 19, 43))
    return img, ImageDraw.Draw(img)


def px(v):
    return int(v * SCALE)


def band(d, x, y, w, h, fill, outline=None, t=2):
    d.rectangle([px(x), px(y), px(x + w) - 1, px(y + h) - 1],
                fill=fill, outline=outline, width=px(t) if outline else 0)


def text_center(d, s, cx, y, font, fill):
    bb = d.textbbox((0, 0), s, font=font)
    tw = bb[2] - bb[0]
    d.text((px(cx) - tw // 2, px(y)), s, font=font, fill=fill)


def title_page():
    img, d = new_page()
    # background art placeholder: dark blue forest gradient
    for i in range(H * SCALE):
        v = 20 + int(40 * (i / (H * SCALE)))
        d.line([(0, i), (W * SCALE, i)], fill=(6, v, v + 20))
    font = cjk_font(16 * SCALE // 2 * 2)
    items = ["开始游戏", "继续游戏", "章节选择", "读档", "CG鉴赏", "流程图", "设置"]
    X, Wd, Y0, DY, Hh = 14, 118, 38, 27, 26
    for i, name in enumerate(items):
        y = Y0 + i * DY
        band(d, X, y, Wd, Hh, (29, 53, 87), (69, 123, 157), 2)
        # accent bar on the left
        d.rectangle([px(X), px(y), px(X + 3), px(y + Hh)], fill=(232, 153, 141))
        bb = d.textbbox((0, 0), name, font=font)
        tw = bb[2] - bb[0]
        d.text((px(X + Wd // 2) - tw // 2, px(y + 4)), name, font=font,
               fill=(241, 250, 238))
    d.text((px(6), px(H - 12)), "SENREN*BANKA", font=cjk_font(8 * SCALE),
           fill=(200, 200, 210))
    return img


def settings_page():
    img, d = new_page()
    font = cjk_font(16 * SCALE // 2 * 2)
    small = cjk_font(8 * SCALE)
    d.text((px(12), px(6)), "设置", font=font, fill=(241, 250, 238))
    rows = [("文字速度", "普通"), ("自动播放", "关"), ("音量", None),
            ("全部解锁", "开"), ("语音", "开")]
    ys = [34, 68, 102, 136, 170]
    for (label, val), y in zip(rows, ys):
        band(d, 20, y, 392, 28, (29, 53, 87), (69, 123, 157), 2)
        bb = d.textbbox((0, 0), label, font=font)
        tw = bb[2] - bb[0]
        d.text((px(216) - tw // 2, px(y + 4)), label, font=font,
               fill=(241, 250, 238))
        if val:
            bb2 = d.textbbox((0, 0), val, font=font)
            d.text((px(356), px(y + 4)), val, font=font, fill=(255, 209, 102))
        else:
            for i in range(8):
                c = (111, 207, 151) if i < 6 else (48, 52, 59)
                d.rectangle([px(340 + i * 9), px(108), px(340 + i * 9 + 6),
                             px(108 + 16)], fill=c)
    d.text((px(20), px(208)), "tap row = change   vol = back", font=small,
           fill=(141, 153, 174))
    return img


t = title_page()
st = settings_page()
out = Image.new("RGB", (W * SCALE * 2 + 20, H * SCALE), (0, 0, 0))
out.paste(t, (0, 0))
out.paste(st, (W * SCALE + 20, 0))
p = Path("NanoApps/build/ui_preview.png")
out.save(p)
print("wrote", p, out.size)
