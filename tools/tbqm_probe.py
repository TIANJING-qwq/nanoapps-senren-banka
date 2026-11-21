#!/usr/bin/env python3
"""With paired (real-name plain OGG from dump) vs (hash tBQM from our
data.xp3 extract), test MD5 naming forms AND derive the tBQM layer."""
import hashlib
import sys
from pathlib import Path

DUMP = Path("K:/千恋＊万花/outPath/data.xp3")
SYS = Path("NanoApps/build/sb_sys")

# index our extracted files by size (SE oggs are small & unique-ish)
by_size = {}
for p in SYS.iterdir():
    by_size.setdefault(p.stat().st_size, []).append(p)

plain = next((DUMP / "sound").glob("*.ogg"))
print(f"plain: {plain.name} size={plain.size if hasattr(plain,'size') else ''}")
sz = plain.stat().st_size
cands = by_size.get(sz, [])
print(f"cipher candidates by size {sz}: {len(cands)}")
pb = plain.read_bytes()
print("plain magic:", pb[:4].hex(), pb[:4])
for c in cands[:4]:
    cb = c.read_bytes()
    print(f"{c.name[:16]} magic: {cb[:8].hex()}")
    # XOR diff over first 64 bytes
    x = bytes(a ^ b for a, b in zip(pb[:64], cb[:64]))
    print("  xor[:24]:", x[:24].hex())

# MD5 naming forms
for form in (plain.name, "und/" + plain.name, "und\\" + plain.name,
             plain.stem, "voice/" + plain.name):
    for enc in ("utf-8", "utf-16-le", "shift_jis"):
        h = hashlib.md5(form.encode(enc)).hexdigest()
        if (SYS / h).exists():
            print(f"MD5 HIT: {form!r} {enc} -> {h}")
