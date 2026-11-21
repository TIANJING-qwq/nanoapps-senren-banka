#!/usr/bin/env python3
"""MD5 rainbow for voice names: try naming forms against sb_voice
hashed filenames. Names come from the tjs dump (yos002_001 etc)."""
import hashlib
from pathlib import Path

V = {p.name for p in Path("NanoApps/build/sb_voice").iterdir()}

names = ["yos002_001", "uts001_001", "mak002_001", "yos001_001"]
forms = [
    lambda n: n,
    lambda n: n + ".ogg",
    lambda n: "voice/" + n,
    lambda n: "voice/" + n + ".ogg",
    lambda n: "voice\\" + n + ".ogg",
    lambda n: n + ".wav",
    lambda n: n.upper(),
    lambda n: n.lower(),
    lambda n: "Voice/" + n + ".ogg",
]
hit = False
for n in names:
    for i, f in enumerate(forms):
        v = f(n)
        for enc in ("utf-8", "utf-16-le", "shift_jis", "ascii"):
            h = hashlib.md5(v.encode(enc, "ignore")).hexdigest()
            if h in V:
                print(f"HIT: {n} form{i} {enc} {v!r} -> {h}")
                hit = True
    if not hit:
        pass
if not hit:
    print("no direct hits; also trying with adler32-in-name variants...")
    import zlib
    import struct
    # maybe filename embeds the adler (as unpack used adler to name?)
    # check: is the name maybe the XP3 adler of the file content?
    p = next(iter(sorted(V)))
    b = Path("NanoApps/build/sb_voice", p).read_bytes()
    print("sample adler:", f"{zlib.adler32(b):08x}", "file:", p)
    print("sample crc32:", f"{zlib.crc32(b):08x}")
