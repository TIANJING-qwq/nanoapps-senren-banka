#!/usr/bin/env python3
"""TLG5 block bitstream: search plausible LZSS variants.
Constraint: decode exactly 4*w*3 bytes; consume ~all input bits; output
should be smooth (image prior: small adjacent deltas)."""
import struct
import sys
from pathlib import Path

d = Path(sys.argv[1]).read_bytes()
w, h = struct.unpack_from("<II", d, 12)
nblk = (h + 3) // 4
base = 24 + 4 * nblk
ln0 = struct.unpack_from("<I", d, 24)[0]
blk = d[base:base + ln0]
# first sub-block
sl = struct.unpack_from("<I", blk, 1)[0]
data0 = blk[5:5 + sl]
out_need = 4 * w          # one channel plane, 4 rows
print(f"w={w} h={h} blocks={nblk}; sub0: {sl}B -> {out_need}B")


class Bits:
    def __init__(self, data):
        self.d = data
        self.pos = 0

    def bit(self):
        byte = self.d[self.pos >> 3]
        v = (byte >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return v

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v


def decode(data, out_n, lit_bit, off_bits, len_base, len_bits, len_bit_first):
    """variant: bit==lit_bit -> literal; else copy(offset,len)."""
    b = Bits(data)
    out = bytearray()
    try:
        while len(out) < out_n:
            if b.bit() == lit_bit:
                out.append(b.bits(8))
                continue
            if len_bit_first:
                ln = len_base + b.bits(len_bits)
                off = 1 + b.bits(off_bits)
            else:
                off = 1 + b.bits(off_bits)
                ln = len_base + b.bits(len_bits)
            if off > len(out) or ln == 0:
                return None
            for _ in range(ln):
                out.append(out[-off])
    except IndexError:
        return None
    return bytes(out) if len(out) == out_n else None


def smoothness(buf):
    if not buf:
        return 1e9
    return sum(abs(buf[i] - buf[i - 1]) for i in range(1, len(buf))) / len(buf)


results = []
for lit in (1, 0):
    for ob in (8, 10, 12, 4, 6):
        for lb in (2, 3, 4):
            for lbits in (2, 3, 4, 5):
                if lb + lbits > 13:
                    continue
                for lbf in (True, False):
                    out = decode(data0, out_need, lit, ob, lb, lbits, lbf)
                    if out is not None:
                        sm = smoothness(out[:600])
                        results.append((sm, lit, ob, lb, lbits, lbf))
results.sort()
print(f"{len(results)} variants decoded exactly; top 6 by smoothness:")
for sm, lit, ob, lb, lbits, lbf in results[:6]:
    print(f"  smooth={sm:6.1f} lit={lit} off={ob}b len={lb}+{lbits}b "
          f"{'len-first' if lbf else 'off-first'}")
