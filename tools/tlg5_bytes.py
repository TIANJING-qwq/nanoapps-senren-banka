#!/usr/bin/env python3
"""Byte-level TLG5 plane codec search.
Hypothesis family: bytes 0xF0-0xFF (or 0x80+) are escapes; following byte
gives run length; run copies from distance d (literal/RLE/dist2/...)."""
import struct
import sys
from pathlib import Path

d = Path(sys.argv[1]).read_bytes()
w, h = struct.unpack_from("<II", d, 12)
nblk = (h + 3) // 4
base = 24 + 4 * nblk
ln0 = struct.unpack_from("<I", d, 24)[0]
blk = d[base:base + ln0]
sl = struct.unpack_from("<I", blk, 1)[0]
data = blk[5:5 + sl]
out_need = 4 * w
print(f"sub0 {sl}B -> {out_need}B: {data[:24].hex(' ')}")


def try_decode(esc_lo, len_mode, dist_mode):
    """esc_lo: first escape value (0xF0 / 0xF8 / 0x80).
    len_mode: 'next' (len=next), 'next+2', 'nib|next'.
    dist_mode: 'rle' (repeat prev), 'nib' (distance = low nibble),
               'nib+1', 'nib+3'."""
    out = bytearray()
    i = 0
    try:
        while len(out) < out_need and i < len(data):
            b = data[i]
            if b < esc_lo:
                out.append(b)
                i += 1
                continue
            nib = b - esc_lo
            i += 1
            if i >= len(data):
                return None
            n = data[i]
            i += 1
            if len_mode == "next":
                ln = n
            elif len_mode == "next+2":
                ln = n + 2
            else:
                ln = (nib << 8) | n
            if dist_mode == "rle":
                if not out:
                    return None
                seg = bytes([out[-1]]) * ln
            else:
                if dist_mode == "nib":
                    dd = nib if nib > 0 else 1
                elif dist_mode == "nib+1":
                    dd = nib + 1
                else:
                    dd = nib + 3
                if dd > len(out) or dd <= 0:
                    return None
                seg = bytes(out[-dd:]) * (ln // dd + 1)
                seg = seg[:ln]
            out += seg
    except IndexError:
        return None
    if len(out) != out_need:
        return None
    return bytes(out)


def smooth(buf):
    return sum(abs(buf[i] - buf[i - 1]) for i in range(1, len(buf))) / len(buf)


hits = []
for esc in (0xF0, 0xF8, 0x80):
    for lm in ("next", "next+2", "nib|next"):
        for dm in ("rle", "nib", "nib+1", "nib+3"):
            r = try_decode(esc, lm, dm)
            if r:
                hits.append((smooth(r), esc, lm, dm, r))
hits.sort()
print(f"{len(hits)} hits")
for sm, esc, lm, dm, r in hits[:6]:
    print(f"smooth={sm:6.1f} esc={esc:#x} len={lm} dist={dm} "
          f"first16={r[:16].hex(' ')}")
