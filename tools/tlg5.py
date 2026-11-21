#!/usr/bin/env python3
"""TLG5 decoder (from krkrz SaveTLG5.cpp + LoadTLG.cpp reference).

Format:
  "TLG5.0\\0raw\\x1a\\0" u8 colors u32 w u32 h u32 blockheight
  u32 blocksize[blockcount]            (blockcount = ceil(h/blockheight))
  blocks: for each block, for each channel c:
    u8 mark; u32 size;  mark==0: LZSS(size bytes) -> w*bh bytes
                        mark!=0: raw (w*bh bytes)
LZSS: flag byte LSB-first; bit=1 match:
    len<18: [pos_lo][pos_hi4|len-3<<4] ; else [pos_lo][pos_hi4|0xF0][len-18]
  4096-slide dict shared across channels & blocks (skip on raw).
Color (colors=4, BGRA scanline order): Wisteria + line delta:
  val1=buf1; val0=buf0+val1; val2=buf2+val1; val3=buf3
  cl = val + prevcl (left); px = cl + upper (previous line)
"""
import struct
import sys
from pathlib import Path

from PIL import Image

SLIDE_N = 4096


def decompress_slide(out_len, data, text, r):
    out = bytearray()
    i = 0
    flag = 0
    mask = 0
    n = len(data)
    while len(out) < out_len:
        if mask == 0:
            if i >= n:
                raise ValueError("truncated stream")
            flag = data[i]
            i += 1
            mask = 1
        if flag & mask:
            if i + 2 > n:
                raise ValueError("truncated match")
            pos = data[i] | ((data[i + 1] & 0x0F) << 8)
            lf = (data[i + 1] >> 4) & 0x0F
            i += 2
            if lf == 15:
                ln = data[i] + 18
                i += 1
            else:
                ln = lf + 3
            for k in range(ln):
                c = text[pos + k]
                out.append(c)
                text[r] = c
                if r < SLIDE_N - 1:
                    text[r + SLIDE_N] = c
                r = (r + 1) & (SLIDE_N - 1)
        else:
            c = data[i]
            i += 1
            out.append(c)
            text[r] = c
            if r < SLIDE_N - 1:
                text[r + SLIDE_N] = c
            r = (r + 1) & (SLIDE_N - 1)
        mask <<= 1
        if mask == 0x100:
            mask = 0
    if len(out) != out_len:
        raise ValueError("overrun")
    return bytes(out), r


def decode_tlg5(data: bytes) -> Image.Image:
    assert data[:11] == b"TLG5.0\x00raw\x1a", data[:11].hex()
    colors = data[11]
    w, h, bh = struct.unpack_from("<III", data, 12)
    nblk = (h - 1) // bh + 1
    if colors != 4:
        raise NotImplementedError(f"colors={colors}")
    pos = 24 + 4 * nblk
    text = bytearray(SLIDE_N * 2 + 512)
    r = 0
    planes_total = [[] for _ in range(4)]
    prev = None
    rows = []
    for b in range(nblk):
        y0 = b * bh
        y1 = min(h, y0 + bh)
        nrows = y1 - y0
        chans = []
        for c in range(4):
            mark = data[pos]
            size = struct.unpack_from("<I", data, pos + 1)[0]
            pos += 5
            need = w * nrows
            if mark == 0:
                plane, r = decompress_slide(need, data[pos:pos + size],
                                            text, r)
            else:
                plane = data[pos:pos + size]
            pos += size
            chans.append(plane)
        # compose rows with Wisteria inverse + line delta
        for ry in range(nrows):
            y = y0 + ry
            prevcl = [0] * 4
            row = bytearray(w * 4)
            for x in range(w):
                idx = ry * w + x
                v1 = chans[1][idx]
                v = [0, v1, chans[2][idx] + v1, chans[3][idx]]
                v[0] = chans[0][idx] + v1
                for c in range(4):
                    cl = (v[c] + prevcl[c]) & 0xFF
                    prevcl[c] = cl
                    if y > 0:
                        cl = (cl + prev[x * 4 + c]) & 0xFF
                    row[x * 4 + c] = cl
            rows.append(bytes(row))
            prev = row
    img = Image.frombytes("RGBA", (w, h), b"".join(rows))
    return img


if __name__ == "__main__":
    src = Path(sys.argv[1])
    img = decode_tlg5(src.read_bytes())
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".png")
    img.save(out)
    print(f"{src.name} -> {out.name}: {img.size}")
