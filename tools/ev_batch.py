#!/usr/bin/env python3
"""Batch-convert every layered event CG (ev*.pimg dump) into the engine's
full-screen CG asset format (432x240 RGB565 VNBI fmt 0), using a process
pool because the pure-Python TLG5 decode is CPU bound.

Usage: ev_batch.py <pack dir> [workers]
"""
import re
import struct
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tlg5_decode import decode as tlg_decode  # noqa: E402

W, H = 432, 240
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
    return layers


def to_vnbi(img: Image.Image) -> bytes:
    im = img.convert("RGB")
    sc = max(W / im.width, H / im.height)
    im = im.resize((max(W, round(im.width * sc)), max(H, round(im.height * sc))),
                   Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H))
    px = im.load()
    buf = bytearray(W * H * 2)
    i = 0
    for yy in range(H):
        for xx in range(W):
            r, g, b = px[xx, yy]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf[i] = v & 0xFF
            buf[i + 1] = v >> 8
            i += 2
    return bytes(bytearray(b"VNBI") + struct.pack("<HHB", W, H, 0)) + bytes(buf)


def compose_one(ev: str):
    psb = EV_DIR / f"{ev}.psb.tjs"
    d = EV_DIR / ev
    try:
        layers = [L for L in parse_layers(psb) if L["visible"]]
        if not layers:
            return ev, b"", "no layers"
        w = max(1920, max(L["left"] + L["width"] for L in layers))
        h = max(1080, max(L["top"] + L["height"] for L in layers))
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for L in sorted(layers, key=lambda x: x["id"]):     # back-to-front
            f = d / f'{L["id"]}.tlg'
            if not f.exists():
                continue
            lw, lh, lc, ldata = tlg_decode(f)
            if lc == 4 and max(ldata[3::4]) == 0:           # no alpha stored
                ba = bytearray(ldata)
                ba[3::4] = bytes([255]) * (len(ba) // 4)
                ldata = bytes(ba)
            piece = Image.frombytes("RGBA", (lw, lh), ldata, "raw", "BGRA")
            if L["opacity"] < 255:
                a = piece.getchannel("A").point(
                    lambda v: v * L["opacity"] // 255)
                piece.putalpha(a)
            canvas.alpha_composite(piece, (L["left"], L["top"]))
        return ev, to_vnbi(canvas), ""
    except Exception as e:                                  # noqa: BLE001
        return ev, b"", f"{type(e).__name__}: {e}"


def main():
    pack = Path(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    (pack / "cg").mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in EV_DIR.iterdir()
                   if p.is_dir() and re.fullmatch(r"ev\w+", p.name)
                   and (EV_DIR / f"{p.name}.psb.tjs").exists())
    todo = [n for n in names if not (pack / "cg" / f"{n}.bin").exists()]
    print(f"{len(names)} CGs total, {len(todo)} to convert, {workers} workers",
          flush=True)
    rows, done, bad = [], 0, 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(compose_one, ev): ev for ev in todo}
        for fut in as_completed(futs):
            ev, data, err = fut.result()
            if not data:
                bad += 1
                print(f"  FAIL {ev}: {err}", flush=True)
                continue
            (pack / "cg" / f"{ev}.bin").write_bytes(data)
            rows.append(f"{ev}\t{ev}")
            done += 1
            if done % 5 == 0:
                print(f"  [{done}/{len(todo)}] {ev}", flush=True)
    # include previously converted ones (resume case)
    for n in names:
        if (pack / "cg" / f"{n}.bin").exists() and \
                not any(r.startswith(n + "\t") for r in rows):
            rows.append(f"{n}\t{n}")
    rows.sort()
    (pack / "cg_ev_names.tsv").write_text("\n".join(rows), encoding="utf-8")
    print(f"DONE {len(rows)} CGs ({bad} failed) -> {pack / 'cg'}", flush=True)


if __name__ == "__main__":
    main()
