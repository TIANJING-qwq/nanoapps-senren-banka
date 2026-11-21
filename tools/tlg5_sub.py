#!/usr/bin/env python3
"""Parse TLG5 block into sub-blocks: [tag u8][u32 len][payload]."""
import struct
import sys
from pathlib import Path

d = Path(sys.argv[1]).read_bytes()
w, h = struct.unpack_from("<II", d, 12)
nblk = (h + 3) // 4
base = 24 + 4 * nblk
bi = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
off = base
for k in range(bi):
    off += struct.unpack_from("<I", d, 24 + 4 * k)[0]
ln = struct.unpack_from("<I", d, 24 + 4 * bi)[0]
blk = d[off:off + ln]
print(f"block {bi}: {ln} B")

p = 0
sub = 0
while p + 5 <= ln:
    tag = blk[p]
    sl = struct.unpack_from("<I", blk, p + 1)[0]
    if p + 5 + sl > ln:
        print(f"@{p}: tag={tag:#04x} len={sl} OVERFLOW (remaining {ln - p})")
        break
    print(f"@{p}: tag={tag:#04x} sublen={sl}")
    sub += 1
    p += 5 + sl
print(f"parsed {sub} sub-blocks; consumed {p}/{ln}")
