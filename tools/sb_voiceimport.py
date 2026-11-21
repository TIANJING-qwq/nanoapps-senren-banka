#!/usr/bin/env python3
"""Convert dumped voice OGGs (KrkrExtract real names) to mono 22.05 kHz
WAVs for the engine, with chapter filtering and a size budget report.

Usage:
  python tools/sb_voiceimport.py <dump_voice_dir> <pack_dir> [filters...]
    filters: chapter number prefixes, e.g. 001 002 or 1 (=all 1xx)
Output: <pack_dir>/voice/<name>.wav + prints total size.
"""
import sys
import wave
from pathlib import Path

from pyogg import VorbisFile

src = Path(sys.argv[1])
out = Path(sys.argv[2]) / "voice"
filters = sys.argv[3:]
out.mkdir(parents=True, exist_ok=True)


def wanted(name: str) -> bool:
    if not filters:
        return True
    digits = "".join(ch for ch in name if ch.isdigit())
    for f in filters:
        d = "".join(ch for ch in f if ch.isdigit())
        if digits.startswith(d):
            return True
    return False


files = sorted(p for p in src.glob("*.ogg") if wanted(p.name))
total = done = 0
for i, p in enumerate(files):
    dst = out / (p.stem + ".wav")
    if dst.exists():
        total += dst.stat().st_size
        done += 1
        continue
    try:
        vf = VorbisFile(str(p))
        pcm = bytes(vf.buffer)
        nch, rate = vf.channels, vf.frequency
    except Exception as e:
        print(f"skip {p.name}: {e}")
        continue
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    total += dst.stat().st_size
    done += 1
    if (i + 1) % 500 == 0:
        print(f"  {i + 1}/{len(files)} ... {total/1e6:.1f} MB")
print(f"{done}/{len(files)} voices -> {out} ({total/1e6:.1f} MB)")
if total > 300e6:
    print("NOTE: over the 300 MB suggested budget — rerun with chapter "
          "filters, e.g. `python tools/sb_voiceimport.py <src> <pack> 001`")
