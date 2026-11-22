#!/usr/bin/env python3
"""Render chart.idx the same way the engine does, so the tree layout can be
checked (and shown) without a device: 432x240 viewports stacked vertically."""
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

CHART = Path("NanoApps/build/sb_full/chart.idx")
W, H = 432, 240
TOP, BOT = 26, 206
SCALE = 2


from PIL import ImageFont  # noqa: E402


def cjk(size):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def load():
    b = CHART.read_bytes()
    assert b[:4] == b"VNCH", b[:4]
    ver, n, ne, nr = struct.unpack_from("<HHHH", b, 4)
    nodes = []
    off = 12
    for i in range(n):
        x, y, t, rt, ch, o, ln = struct.unpack_from("<hhBBHHH", b, off)
        off += 12
        nodes.append({"x": x, "y": y, "type": t, "chapter": ch, "off": o, "len": ln})
    edges = []
    for i in range(ne):
        a, bb = struct.unpack_from("<HH", b, off)
        off += 4
        edges.append((a, bb))
    routes = []
    for i in range(nr):
        o, ln = struct.unpack_from("<HH", b, off)
        off += 4
        routes.append((o, ln))
    blob = b[off:]
    for nd in nodes:
        nd["title"] = blob[nd["off"]:nd["off"] + nd["len"]].decode("utf-8", "replace")
    return nodes, edges, routes


def draw_view(nodes, edges, scroll, draw, font, small):
    # connectors
    for a, bb in edges:
        A, B = nodes[a], nodes[bb]
        ax, ay = A["x"] + 8, A["y"] + 16 - scroll
        bx, by = B["x"] + 8, B["y"] - scroll
        if (ay < TOP and by < TOP) or (ay > BOT and by > BOT):
            continue
        draw.line([(ax, ay), (ax, by)], fill=(58, 74, 102), width=2)
        draw.line([(ax, by), (bx, by)], fill=(58, 74, 102), width=2)
    for nd in nodes:
        x, y = nd["x"], nd["y"] - scroll
        w = 200 if nd["type"] == 0 else 100
        if y + 18 < TOP or y > BOT:
            continue
        col = {0: (232, 153, 141), 2: (255, 209, 102), 3: (111, 207, 151)}.get(
            nd["type"], (69, 123, 157))
        draw.rectangle([x, y, x + w - 1, y + 17], fill=(29, 53, 87), outline=col)
        draw.rectangle([x, y, x + 2, y + 17], fill=col)
        t = nd["title"][: (w - 12) // 14]
        draw.text((x + 6, y + 1), t, font=font, fill=(241, 250, 238))


def main():
    nodes, edges, routes = load()
    height = max(n["y"] for n in nodes) + 40
    print(f"{len(nodes)} nodes, {len(edges)} edges, height {height}px, "
          f"{len(routes)} routes")
    font, small = cjk(13 * SCALE // 2), cjk(8)
    pages = []
    scroll = 0
    while scroll < height - BOT:
        img = Image.new("RGB", (W * SCALE, H * SCALE), (11, 19, 43))
        d = ImageDraw.Draw(img)

        def px(x, y, _d=d):
            return (x * SCALE, y * SCALE)

        class D:  # tiny scaling wrapper
            def line(self, pts, **kw):
                d.line([(x * SCALE, y * SCALE) for x, y in pts], **kw)

            def rectangle(self, box, **kw):
                d.rectangle([box[0] * SCALE, box[1] * SCALE,
                             box[2] * SCALE, box[3] * SCALE], **kw)

            def text(self, xy, s, **kw):
                d.text((xy[0] * SCALE, xy[1] * SCALE), s, **kw)

        draw_view(nodes, edges, scroll, D(), font, small)
        d.text((10 * SCALE, 3 * SCALE), "流程图  FLOWCHART", font=font,
               fill=(241, 250, 238))
        pages.append(img)
        scroll += (BOT - TOP)
        if len(pages) >= 6:
            break
    out = Image.new("RGB", (W * SCALE * len(pages) + 10 * (len(pages) - 1),
                            H * SCALE), (0, 0, 0))
    for i, p in enumerate(pages):
        out.paste(p, (i * (W * SCALE + 10), 0))
    dst = Path("NanoApps/build/chart_preview.png")
    out.save(dst)
    print("wrote", dst, out.size, f"({len(pages)} pages)")


if __name__ == "__main__":
    main()
