#!/usr/bin/env python3
"""Verify PyOgg can decode our OGGs to PCM WAV."""
import sys
from pathlib import Path

import wave

from pyogg import VorbisFile

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
vf = VorbisFile(str(src))
pcm = vf.buffer
print(f"{src.name}: {vf.channels}ch {vf.frequency}Hz "
      f"{len(pcm)} bytes PCM")
with wave.open(str(dst), "wb") as w:
    w.setnchannels(vf.channels)
    w.setsampwidth(2)
    w.setframerate(vf.frequency)
    w.writeframes(bytes(pcm))
print(f"wrote {dst} ({dst.stat().st_size} B)")
