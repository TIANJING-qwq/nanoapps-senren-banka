#!/usr/bin/env python3
"""Compose a layered Yuzusoft event CG (ev*.pimg dump: layer TLGs + psb.tjs)."""
import re
import struct
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, "NanoApps/tools")
from tlg5_decode import decode as tlg_decode  # noqa: E402

EV_DIR = Path(r"K:/千恋＊万花/outPath/evimage720.xp3")


def parse_layers(psb: Path):
    t = psb.read_text(encoding="utf-8", errors="replace")
    layers = []
    for m in re.finditer(
            r'\(const\) %\[\s*"height" => (\d+),\s*"layer_id" => (\d+),.*?'
            r'"left" => (-?\d+),.*?"name" => "([^"]*)",.*?'
            r'"opacity" => (\d+),.*?"top" => (-?\d+),.*?'
            r'"visible" => (\d+),.*?"width" => (\d+)', t, re.S):
        layers.append({
            "height": int(m.group(1)), "id": int(m.group(2)),
            "left": int(m.group(3)), "name": m.group(4),
            "opacity": int(m.group(5)), "top": int(m.group(6)),
            "visible": int(m.group(7)), "width": int(m.group(8)),
        })
    # canvas = union of every layer's rectangle (the top-level "width"
    # in the file belongs to the first layer, not the canvas)
    w = max((L["left"] + L["width"]) for L in layers) if layers else 1
    h = max((L["top"] + L["height"]) for L in layers) if layers else 1
    w = max(w, 1920)
    h = max(h, 1080)
    return w, h, layers


def main(ev_name):
    d = EV_DIR / ev_name
    psb = EV_DIR / f"{ev_name}.psb.tjs"
    w, h, layers = parse_layers(psb)
    print(f"{ev_name}: {w}x{h}, {len(layers)} layers")

    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # the .psb.tjs lists layers FRONT-TO-BACK (highest layer_id first), so
    # compositing in file order buries everything under the base plate.
    # Draw back-to-front instead: lowest layer_id first.
    for L in sorted(layers, key=lambda x: x["id"]):
        if not L["visible"]:
            continue
        f = d / f'{L["id"]}.tlg'
        if not f.exists():
            print("  missing", f)
            continue
        lw, lh, lc, ldata = tlg_decode(f)
        # opaque layers ship alpha == 0 everywhere (the channel simply is not
        # stored); treat an all-zero alpha plane as fully opaque
        if lc == 4:
            amax = max(ldata[3::4]) if ldata else 0
            if amax == 0:
                ba = bytearray(ldata)
                ba[3::4] = bytes([255]) * (len(ba) // 4)
                ldata = bytes(ba)
        piece = Image.frombytes("RGBA", (lw, lh), ldata, "raw", "BGRA")
        if L["opacity"] < 255:
            a = piece.getchannel("A").point(
                lambda v: v * L["opacity"] // 255)
            piece.putalpha(a)
        canvas.alpha_composite(piece, (L["left"], L["top"]))
        print(f'  layer {L["id"]:2d} {L["name"]:4s} ' +
              f'{lw}x{lh} @({L["left"]},{L["top"]})')

    out = canvas.convert("RGB")
    out.thumbnail((820, 600))
    dst = Path(f"NanoApps/build/ev_{ev_name}.png")
    out.save(dst)
    print("wrote", dst, out.size)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ev101a")
