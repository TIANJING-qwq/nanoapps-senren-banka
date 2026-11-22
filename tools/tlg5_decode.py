#!/usr/bin/env python3
"""Faithful TLG5 decoder, ported 1:1 from libtlg-rs (load_tlg5 +
tlg5_decompress_slide + tlg5_compose_colors4).

    tlg5_decode.py <in.tlg> <out.png>
"""
import struct
import sys
from pathlib import Path

from PIL import Image

SLIDE_N = 4096
SLIDE_M = 18 + 255


def decompress_slide(out, inp, insize, text, r):
    flags = 0
    inpos = 0
    outpos = 0
    while inpos < insize:
        flags >>= 1
        if flags & 256 == 0:
            flags = inp[inpos] | 0xFF00
            inpos += 1
        if flags & 1:
            mpos = inp[inpos] | ((inp[inpos + 1] & 0xF) << 8)
            mlen = ((inp[inpos + 1] & 0xF0) >> 4) + 3
            inpos += 2
            if mlen == 18:
                mlen += inp[inpos]
                inpos += 1
            while mlen > 0:
                c = text[mpos]
                out[outpos] = c
                outpos += 1
                text[r] = c
                r += 1
                mpos = (mpos + 1) & 4095
                r &= 4095
                mlen -= 1
        else:
            c = inp[inpos]
            inpos += 1
            out[outpos] = c
            outpos += 1
            text[r] = c
            r = (r + 1) & 4095
    return r


def compose4(outp, upper, bufs, width):
    pb = pg = pr = pa = 0
    o = 0
    for x in range(width):
        b = bufs[0][x]
        g = bufs[1][x]
        r = bufs[2][x]
        a = bufs[3][x]
        b = (b + g) & 0xFF
        r = (r + g) & 0xFF
        pb = (pb + b) & 0xFF
        pg = (pg + g) & 0xFF
        pr = (pr + r) & 0xFF
        pa = (pa + a) & 0xFF
        outp[o] = (pb + upper[o]) & 0xFF
        outp[o + 1] = (pg + upper[o + 1]) & 0xFF
        outp[o + 2] = (pr + upper[o + 2]) & 0xFF
        outp[o + 3] = (pa + upper[o + 3]) & 0xFF
        o += 4


def compose3(outp, upper, bufs, width):
    pb = pg = pr = 0
    o = 0
    for x in range(width):
        b = bufs[0][x]
        g = bufs[1][x]
        r = bufs[2][x]
        b = (b + g) & 0xFF
        r = (r + g) & 0xFF
        pb = (pb + b) & 0xFF
        pg = (pg + g) & 0xFF
        pr = (pr + r) & 0xFF
        outp[o] = (pb + upper[o]) & 0xFF
        outp[o + 1] = (pg + upper[o + 1]) & 0xFF
        outp[o + 2] = (pr + upper[o + 2]) & 0xFF
        o += 3


def decode(src: Path):
    b = src.read_bytes()
    if b[:11] != b"TLG5.0\x00raw\x1a":
        raise SystemExit("not TLG5 raw: %r" % b[:11])
    pos = 11
    colors = b[pos]
    pos += 1
    width, height, blockheight = struct.unpack_from("<III", b, pos)
    pos += 12
    blockcount = (height - 1) // blockheight + 1
    pos += blockcount * 4
    print(f"colors={colors} w={width} h={height} blockheight={blockheight} "
          f"blocks={blockcount} data@{pos}")

    stride = width * colors
    out = bytearray(width * height * colors)
    r = 0
    text = bytearray(4096)
    # NB: the previous row persists ACROSS block rows (libtlg-rs keeps
    # `prevline` outside the y_blk loop). Resetting it per block punched a
    # band every `blockheight` rows because the differential restarted at 0.
    prev = None
    for y_blk in range(0, height, blockheight):
        bufs = []
        for c in range(colors):
            mark = b[pos]
            pos += 1
            size = struct.unpack_from("<I", b, pos)[0]
            pos += 4
            buf = bytearray(blockheight * width + 10)
            if mark == 0:
                r = decompress_slide(buf, b[pos:pos + size], size, text, r)
            else:
                buf[:size] = b[pos:pos + size]
            pos += size
            bufs.append(buf)
        y_lim = min(y_blk + blockheight, height)
        for y in range(y_blk, y_lim):
            cur = bytearray(stride)
            upper = bytearray(stride) if prev is None else prev
            if colors == 4:
                compose4(cur, upper, bufs, width)
            else:
                compose3(cur, upper, bufs, width)
            out[y * stride:(y + 1) * stride] = cur
            prev = cur
            for c in range(colors):
                bufs[c] = bufs[c][width:]
    return width, height, colors, bytes(out)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    w, h, colors, data = decode(src)
    img = Image.frombytes("RGBA" if colors == 4 else "RGB", (w, h), data,
                          "raw", "BGRA" if colors == 4 else "BGR")
    img.thumbnail((800, 600))
    img.save(dst)
    print("wrote", dst, img.size)
