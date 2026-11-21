#!/usr/bin/env python3
import sys
from pathlib import Path
from pyogg import OpusFile

p = Path(sys.argv[1])
af = OpusFile(str(p))
print("attrs:", [a for a in dir(af) if not a.startswith("_")])
print("channels", af.channels, "freq", af.frequency)
for name in ("buffer", "as_buffer", "pcm", "bytes"):
    try:
        v = getattr(af, name)
        v = v() if callable(v) else v
        print(name, type(v), len(v) if hasattr(v, "__len__") else v)
    except Exception as e:
        print(name, "ERR", e)
