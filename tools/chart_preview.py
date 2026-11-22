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
    ver, nr = struct.unpack_from("<HH", b, 4)
    routes = []
    for i in range(nr):
        off, ln, nb, nc, eb, ec = struct.unpack_from("<HHHHHH", b, 8 + i * 12)
        routes.append({"name_off": off, "name_len": ln, "node_base": nb,
                       "node_count": nc, "edge_base": eb, "edge_count": ec})
    noff = 8 + nr * 12
    total = max(r["node_base"] + r["node_count"] for r in routes)
    eoff = noff + total * 12
    etotal = max(r["edge_base"] + r["edge_count"] for r in routes)
    boff = eoff + etotal * 4
    nodes = []
    for i in range(total):
        x, y, t, rt, ch, o, ln = struct.unpack_from("<hhBBHHH", b, noff + i * 12)
        nodes.append({"x": x, "y": y, "type": t, "route": rt, "chapter": ch,
                      "off": o, "len": ln})
    edges = [struct.unpack_from("<HH", b, eoff + i * 4) for i in range(etotal)]
    blob = b[boff:]
    for nd in nodes:
        nd["title"] = blob[nd["off"]:nd["off"] + nd["len"]].decode("utf-8", "replace")
    for r in routes:
        r["name"] = blob[r["name_off"]:r["name_off"] + r["name_len"]].decode(
            "utf-8", "replace")
    return routes, nodes, edges


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
    routes, nodes, edges = load()
    print(f"{len(nodes)} nodes, {len(edges)} edges, {len(routes)} routes")
    font, small = cjk(13 * SCALE // 2), cjk(8)
    pages = []
    for ri, scroll in ((0, 0), (0, 130), (1, 0)):
        if ri >= len(routes):
            break
        r = routes[ri]
        nb, nc = r["node_base"], r["node_count"]
        eb, ec = r["edge_base"], r["edge_count"]
        sub_nodes = nodes[nb:nb + nc]
        sub_edges = [(a - nb, b - nb) for a, b in edges[eb:eb + ec]
                     if nb <= a < nb + nc and nb <= b < nb + nc]
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

        draw_view(sub_nodes, sub_edges, scroll, D(), font, small)
        for ti, rr in enumerate(routes):
            tx = 4 + ti * 61
            on = ti == ri
            d.rectangle([tx * SCALE, 2 * SCALE, (tx + 58) * SCALE,
                         (2 + 18) * SCALE],
                        fill=(232, 153, 141) if on else (29, 53, 87),
                        outline=(255, 233, 228) if on else (69, 123, 157))
            d.text(((tx + 6) * SCALE, 4 * SCALE), rr["name"], font=font,
                   fill=(27, 36, 51) if on else (241, 250, 238))
        pages.append(img)
    out = Image.new("RGB", (W * SCALE * len(pages) + 10 * (len(pages) - 1),
                            H * SCALE), (0, 0, 0))
    for i, p in enumerate(pages):
        out.paste(p, (i * (W * SCALE + 10), 0))
    dst = Path("NanoApps/build/chart_preview.png")
    out.save(dst)
    print("wrote", dst, out.size, f"({len(pages)} pages)")


if __name__ == "__main__":
    main()
