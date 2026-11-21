#!/usr/bin/env python3
"""Exhaustive-ish TLG5 channel-plane bitstream search (round 2).
Families: bit order(MSB/LSB), lit polarity, offset(4/8/12b fixed or
2-stage 4/8b), length(fixed 2-5b or gamma), len/off order."""
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


class Bits:
    def __init__(self, data, msb):
        self.d = data
        self.pos = 0
        self.msb = msb

    def bit(self):
        byte = self.d[self.pos >> 3]
        v = (byte >> (7 - (self.pos & 7))) & 1 if self.msb else \
            (byte >> (self.pos & 7)) & 1
        self.pos += 1
        return v

    def bits(self, n):
        v = 0
        if self.msb:
            for _ in range(n):
                v = (v << 1) | self.bit()
        else:
            for i in range(n):
                v |= self.bit() << i
        return v

    def gamma(self):
        n = 0
        while self.bit():
            n += 1
            if n > 16:
                raise ValueError
        return (1 << n) + self.bits(n) if n else 1


def decode(msb, lit, off_mode, len_mode, order):
    b = Bits(data, msb)
    out = bytearray()
    try:
        while len(out) < out_need:
            if b.bit() == lit:
                out.append(b.bits(8))
                continue
            if off_mode == "2stage":
                off = 1 + (b.bits(4) if b.bit() == 0 else 16 + b.bits(8))
            else:
                off = 1 + b.bits(off_mode)
            ln = b.gamma() if len_mode == "gamma" else 1 + b.bits(len_mode)
            if order == "len_first":
                pass
            if off > len(out) or ln <= 0 or ln > 4096:
                return None
            for _ in range(ln):
                out.append(out[-off])
    except (IndexError, ValueError):
        return None
    if len(out) != out_need:
        return None
    return bytes(out), b.pos


def smooth(buf):
    return sum(abs(buf[i] - buf[i - 1]) for i in range(1, len(buf))) / len(buf)


results = []
for msb in (True, False):
    for lit in (1, 0):
        for om in ("2stage", 4, 8, 12, 10):
            for lm in ("gamma", 2, 3, 4, 5):
                for order in ("off_first", "len_first"):
                    r = decode(msb, lit, om, lm, order)
                    if r:
                        out, bits_used = r
                        results.append((smooth(out[:800]), msb, lit, om, lm,
                                        order, bits_used))
results.sort()
print(f"{len(results)} hits")
for sm, msb, lit, om, lm, order, bu in results[:8]:
    print(f"smooth={sm:6.1f} {'MSB' if msb else 'LSB'} lit={lit} "
          f"off={om} len={lm} {order} bits={bu}/{sl * 8}")
