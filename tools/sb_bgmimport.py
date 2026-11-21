#!/usr/bin/env python3
"""Convert dumped BGM opus files to engine WAVs, downmixed to mono and
resampled to 22.05 kHz (≈4.6 MB/min). Only tracks actually referenced
by the story (sb_bgms.tsv) are converted. Engine plays
/Data/vn/bgm/<name>.wav where name is the tjs form (bgm34).

Usage: python tools/sb_bgmimport.py <dump_bgm_dir> <pack_dir>"""
import ctypes
import struct
import sys
import wave
from pathlib import Path

from pyogg import OpusFile

src = Path(sys.argv[1])
out = Path(sys.argv[2]) / "bgm"
out.mkdir(parents=True, exist_ok=True)

RATE = 22050
refs = set()
bp = Path("NanoApps/build/sb_bgms.tsv")
if bp.exists():
    for ln in bp.read_text(encoding="utf-8").splitlines():
        if "\t" in ln:
            refs.add(ln.split("\t", 1)[1])
if not refs:
    refs = {p.stem.lower() for p in src.glob("BGM*.opus")}

# map tjs name -> dump file (bgm34 -> BGM34.opus)
def dump_for(name):
    cands = [src / f"{name.upper()}.opus", src / f"{name.upper()}.OGG",
             src / f"BGM{int(''.join(c for c in name if c.isdigit())):02d}.opus"]
    for c in cands:
        if c.exists():
            return c
    return None


total = done = 0
for name in sorted(refs):
    dst = out / f"{name}.wav"
    if dst.exists() and dst.stat().st_size > 100:
        total += dst.stat().st_size
        done += 1
        continue
    p = dump_for(name)
    if p is None:
        continue
    try:
        af = OpusFile(str(p))
        nch, fr = af.channels, af.frequency
        pcm = ctypes.string_at(af.buffer, af.buffer_length)
    except Exception as e:
        print(f"skip {name}: {e}")
        continue
    ns = len(pcm) // 2
    sm = struct.unpack(f"<{ns}h", pcm)
    # mono mixdown
    if nch == 2:
        mono = [(sm[i] + sm[i + 1]) // 2 for i in range(0, ns - 1, 2)]
    else:
        mono = list(sm)
    # linear-interp resample to RATE
    n_out = int(len(mono) * RATE / fr)
    rs = []
    for i in range(n_out):
        x = i * fr / RATE
        i0 = int(x)
        if i0 + 1 >= len(mono):
            rs.append(mono[-1] if mono else 0)
            continue
        rs.append(int(mono[i0] + (mono[i0 + 1] - mono[i0]) * (x - i0)))
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{len(rs)}h", *rs))
    total += dst.stat().st_size
    done += 1
    print(f"  {name}: {len(rs)/RATE:.1f}s")
print(f"{done}/{len(refs)} bgm -> {out} ({total/1e6:.1f} MB)")
