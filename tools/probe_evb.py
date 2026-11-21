#!/usr/bin/env python3
"""Analyze KrkrExtract EVB pck structure: hexdump + name scan + zlib map."""
import re
import sys
import zlib

path = sys.argv[1]
data = open(path, "rb").read()
print(f"{path}: {len(data):,} B = {len(data):#x}")

arg = sys.argv[2] if len(sys.argv) > 2 else "head"
if arg == "head":
    n = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x200
    for off in range(0, min(n, len(data)), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        print(f"{off:08x}  {hexs:<47}  {asc}")
elif arg == "names":
    # scan UTF-16LE printable runs with offsets
    i = 0
    out = []
    while i < len(data) - 4:
        if data[i] != 0 and 0x20 <= data[i] < 0x7f and data[i + 1] == 0:
            j = i
            s = []
            while j < len(data) - 1:
                ch = data[j] | (data[j + 1] << 8)
                if ch == 0:
                    break
                if not (0x20 <= ch < 0x7f or 0x3000 <= ch <= 0x9fff or
                        ch in (0x30fb, 0xff0a, 0x2017)):
                    break
                s.append(chr(ch))
                j += 2
            txt = "".join(s)
            if len(txt) >= 3 and (any(0x3000 <= ord(c) <= 0x9fff for c in txt)
                                  or txt.endswith((".png", ".ks", ".tjs", ".psb",
                                                  ".ogg", ".wav", ".bmp", ".jpg"))
                                  or "/" in txt):
                out.append((i, txt[:70]))
                i = j
                continue
        i += 2
    for off, txt in out[:400]:
        print(f"{off:08x}  {txt}")
    print(f"({len(out)} runs)")
elif arg == "zlibs":
    # every zlib stream start + first bytes of decompressed data
    found = []
    for m in re.finditer(b"\x78[\x01\x5e\x9c\xda]", data):
        o = m.start()
        try:
            d = zlib.decompressobj()
            out = d.decompress(data[o:o + (1 << 16)])
            if len(out) > 64:
                found.append((o, len(out), out[:16]))
        except Exception:
            pass
    for o, n, head in found[:60]:
        print(f"{o:08x} -> {n:>9,} B  {head.hex(' ')}")
    print(f"({len(found)} streams)")
elif arg == "seek":
    # dump around an offset
    o = int(sys.argv[3], 0)
    for off in range(max(0, o - 32), min(len(data), o + 96), 16):
        chunk = data[off:off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        print(f"{off:08x}  {hexs:<47}  {asc}")
