#!/usr/bin/env python3
"""Hunt for real voice names inside the OGG files: vorbis comments,
or positional alignment via XP3 table order (= directory creation
order on NTFS)."""
import struct
import sys
from pathlib import Path

V = Path("NanoApps/build/sb_voice")
files = [p for p in V.iterdir() if p.name[0] != "$"][:0]

# creation-order listing (Windows: order of directory entries ~ insert
# order = unpack order = XP3 table order)
ordered = sorted(V.iterdir(), key=lambda p: p.stat().st_ctime)
print(f"files: {len(ordered)}")

# 1) check vorbis comments for names
import re
for p in ordered[:5]:
    b = p.read_bytes()
    m = re.search(rb"[a-zA-Z]{3}\d{3}_\d{3}", b[:8192])
    print(p.name[:12], "comment-name:", m.group(0) if m else None)
