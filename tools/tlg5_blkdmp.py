#!/usr/bin/env python3
"""Hexdump TLG5 block 0/1/2 to reveal sub-structure (plane prefixes?)."""
import struct
import sys
from pathlib import Path

d = Path(sys.argv[1]).read_bytes()
w, h = struct.unpack_from("<II", d, 12)
nblk = (h + 3) // 4
base = 24 + 4 * nblk
off = base
for bi in range(3):
    ln = struct.unpack_from("<I", d, 24 + 4 * bi)[0]
    blk = d[off:off + ln]
    print(f"--- block {bi}: {ln} B (expect {4 * w * 3} out)")
    for r in range(0, min(ln, 48), 16):
        print("  " + " ".join(f"{b:02x}" for b in blk[r:r + 16]))
    off += ln
