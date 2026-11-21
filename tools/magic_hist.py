#!/usr/bin/env python3
"""Magic-byte histogram of extracted files."""
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
c = Counter()
samples = {}
for p in root.rglob("*"):
    if not p.is_file():
        continue
    b = p.read_bytes()[:16]
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        m = "PNG"
    elif b[:5] == b"TLG5." or b[:5] == b"TLG6.":
        m = b[:4].decode()
    elif b[:4] == b"TJS2" or b[:7] == b"TJS2100":
        m = "TJS2"
    elif b[:3] == b"PSB":
        m = "PSB"
    elif b[:4] == b"OggS":
        m = "OGG"
    elif b[:4] == b"RIFF":
        m = "WAV"
    elif b[:3] == b"ID3" or b[:2] == b"\xff\xfb":
        m = "MP3"
    elif b[:2] == b"BM":
        m = "BMP"
    elif b[:4] == b"DDS ":
        m = "DDS"
    elif b[:2] == b"\x1f\x8b":
        m = "GZ"
    elif b[:4] == b"PK\x03\x04":
        m = "ZIP"
    else:
        m = "?" + b[:6].hex()
    c[m] += 1
    samples.setdefault(m, p.name)
for m, n in c.most_common(30):
    print(f"{m:14} {n:5}  e.g. {samples[m][:44]}")
