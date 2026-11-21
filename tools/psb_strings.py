#!/usr/bin/env python3
"""Dump PSB v3 string table: [0x14]=strdata, table=[0x10]=u8 offsets."""
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
import struct
u = struct.unpack_from("<8I", data, 8)
stroffs, strdata = u[2], u[3]
# u16 LE offset table; first 4 bytes belong to the tree region tail
tbl = data[stroffs + 4:strdata]
offs = [tbl[i] | (tbl[i + 1] << 8) for i in range(0, len(tbl) - 1, 2)]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 80
lo = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
for i in range(lo, min(lo + n, len(offs))):
    o = offs[i]
    if strdata + o >= len(data):
        continue
    e = data.index(b"\x00", strdata + o)
    try:
        s = data[strdata + o:e].decode("cp932")
    except Exception:
        s = data[strdata + o:e].decode("utf-8", "replace")
    print(f"[{i:4}] {s[:70]}")
