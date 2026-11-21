#!/usr/bin/env python3
"""Probe M2 PSB structure from a decrypted Senren Banka scenario blob."""
import struct
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
nm = sys.argv[1].replace("\\", "/").split("/")[-1]
print(f"{nm}: {len(data):,} B")
assert data[:4] == b"PSB\x00", data[:8].hex()
for off in range(0, 0x80, 16):
    chunk = data[off:off + 16]
    hexs = " ".join(f"{b:02x}" for b in chunk)
    asc = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
    print(f"{off:04x}  {hexs:<47}  {asc}")
ver, enc = struct.unpack_from("<HH", data, 4)
print(f"ver={ver} enc={enc}")
u = struct.unpack_from("<10I", data, 8)
print("u32@8..:", [hex(x) for x in u])
if len(sys.argv) > 2:
    for lo in sys.argv[2:]:
        o = int(lo, 0)
        if o >= len(data):
            print(f"@{o:#x}: BEYOND EOF ({len(data):#x})")
            continue
        n = min(96, len(data) - o)
        chunk = data[o:o + n]
        asc = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        hexs = " ".join(f"{b:02x}" for b in chunk[:32])
        print(f"@{o:#x}: {hexs}")
        print(f"        {asc}")
