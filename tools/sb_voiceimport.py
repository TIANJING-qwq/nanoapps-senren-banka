#!/usr/bin/env python3
"""Convert dumped voice OGGs (KrkrExtract real names) to mono 22.05 kHz
WAVs for the engine, with chapter filtering and a size budget report.

Usage:
  python tools/sb_voiceimport.py <dump_voice_dir> <pack_dir> [filters...]
    filters: chapter number prefixes, e.g. 001 002 or 1 (=all 1xx)
Output: <pack_dir>/voice/<name>.wav + prints total size.
"""
import os
import struct
import sys
import wave
from pathlib import Path

from pyogg import VorbisFile

RATE = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() \
    else 16000

src = Path(sys.argv[1])
out = (Path(sys.argv[2]).resolve() / "voice")
filters = [a for a in sys.argv[3:] if not a.isdigit()]
out.mkdir(parents=True, exist_ok=True)
print(f"target rate: {RATE} Hz mono")


def wanted(name: str) -> bool:
    if not filters:
        return True
    digits = "".join(ch for ch in name if ch.isdigit())
    for f in filters:
        d = "".join(ch for ch in f if ch.isdigit())
        if digits.startswith(d):
            return True
    return False


def resample_mono(pcm: bytes, nch: int, fr: int) -> list:
    ns = len(pcm) // 2
    sm = struct.unpack(f"<{ns}h", pcm)
    if nch == 2:
        mono = [(sm[i] + sm[i + 1]) // 2 for i in range(0, ns - 1, 2)]
    else:
        mono = list(sm)
    if fr == RATE:
        return mono
    n_out = int(len(mono) * RATE / fr)
    rs = []
    for i in range(n_out):
        x = i * fr / RATE
        i0 = int(x)
        if i0 + 1 >= len(mono):
            rs.append(mono[-1] if mono else 0)
            continue
        rs.append(int(mono[i0] + (mono[i0 + 1] - mono[i0]) * (x - i0)))
    return rs


files = sorted(p for p in src.glob("*.ogg") if wanted(p.name))
total = done = 0
# PyOgg's native vorbisfile uses ANSI fopen: it cannot open paths with
# non-ASCII characters (the game dir is 千恋＊万花). chdir into the source
# and address files by their pure-ASCII names.
os.chdir(src)
for i, p in enumerate(files):
    dst = out / (p.stem + ".wav")
    if dst.exists() and dst.stat().st_size > 100:
        total += dst.stat().st_size
        done += 1
        continue
    try:
        vf = VorbisFile(p.name)          # bare ASCII name, cwd = src
        pcm = bytes(vf.buffer)
        nch, fr = vf.channels, vf.frequency
    except Exception as e:
        print(f"skip {p.name}: {e}")
        continue
    rs = resample_mono(pcm, nch, fr)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{len(rs)}h", *rs))
    total += dst.stat().st_size
    done += 1
    if (i + 1) % 500 == 0:
        print(f"  {i + 1}/{len(files)} ... {total/1e6:.1f} MB",
              flush=True)
print(f"{done}/{len(files)} voices -> {out} ({total/1e6:.1f} MB)")
if total > 300e6:
    print("NOTE: over the 300 MB suggested budget — rerun with chapter "
          "filters, e.g. `python tools/sb_voiceimport.py <src> <pack> 001`")
