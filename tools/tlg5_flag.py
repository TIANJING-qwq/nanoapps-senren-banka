#!/usr/bin/env python3
"""Flag-byte LZSS hypothesis: token stream with per-8 flag byte."""
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
print(f"sub0 {sl}B -> {out_need}B")


def run(lsb_flags, lsb_pair, pair_mode):
    out = bytearray()
    i = 0
    try:
        while len(out) < out_need and i < len(data):
            flags = data[i]; i += 1
            for k in range(8):
                if len(out) >= out_need:
                    break
                bit = (flags >> k) & 1 if lsb_flags else (flags >> (7 - k)) & 1
                if bit:
                    out.append(data[i]); i += 1
                else:
                    a, b = data[i], data[i + 1]; i += 2
                    if pair_mode == "off_len":
                        off, ln = a, b
                    elif pair_mode == "len_off":
                        off, ln = b, a
                    else:  # nibble-split
                        off, ln = (a >> 4) + 1, ((a & 15) << 8 | b)
                    if off == 0 or off > len(out) or ln == 0:
                        return None
                    for _ in range(ln):
                        out.append(out[-off])
    except IndexError:
        return None
    return bytes(out) if len(out) == out_need else None


def smooth(buf):
    return sum(abs(buf[i] - buf[i - 1]) for i in range(1, len(buf))) / len(buf)


hits = []
for lf in (True, False):
    for lp in (True, False):
        for pm in ("off_len", "len_off", "nib"):
            r = run(lf, lp, pm)
            if r:
                hits.append((smooth(r), lf, lp, pm, r))
hits.sort()
print(f"{len(hits)} hits")
for sm, lf, lp, pm, r in hits[:6]:
    print(f"smooth={sm:6.2f} flags={'LSB' if lf else 'MSB'} "
          f"pair={'LSB' if lp else 'MSB'} mode={pm} head={r[:16].hex(' ')}")
