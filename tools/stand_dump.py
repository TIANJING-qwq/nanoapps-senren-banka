#!/usr/bin/env python3
"""Dump every field of the E-mote .stand files under both plausible
encodings, so the table structure (per-part rows) can be identified.

Two decodings are tried per file:
  A) UTF-16BE units, each unit XOR 0x00FF  (how the header text reads)
  B) UTF-16LE plain (how fragments like "2400" read)
Fields are split on U+0006. We print a compact per-field summary."""
import sys
from pathlib import Path

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")


def fields_xorbe(b: bytes):
    out, cur = [], []
    for i in range(0, len(b) - 1, 2):
        v = (b[i] << 8 | b[i + 1]) ^ 0x00FF
        if v == 0x0006:
            out.append(bytes(cur))
            cur = []
        else:
            cur += bytes((v & 0xFF,))
    out.append(bytes(cur))
    return out


def fields_le(b: bytes):
    out, cur = [], []
    for i in range(0, len(b) - 1, 2):
        v = b[i] | (b[i + 1] << 8)
        if v == 0x0006:
            out.append(bytes(cur))
            cur = []
        else:
            cur += bytes((v & 0xFF,))
    out.append(bytes(cur))
    return out


def summarize(fs):
    """map each distinct field shape to first indexes, to expose repetition"""
    import collections
    shapes = collections.OrderedDict()
    for i, f in enumerate(fs):
        s = f.decode("latin-1")
        kind = "digits" if s.isdigit() and s else \
               "colon" if s and all(c.isdigit() or c == ":" for c in s) else \
               "ascii" if s and all(32 <= ord(c) < 127 for c in s) else "bin"
        shapes.setdefault((kind, s[:24]), []).append(i)
    return shapes


if __name__ == "__main__":
    names = sys.argv[1:] or ["芳乃a.txt", "芳乃a_0.txt"]
    for name in names:
        b = (SRC / name).read_bytes()
        for label, fn in (("xor-be", fields_xorbe), ("le-plain", fields_le)):
            fs = fn(b)
            printable = sum(1 for f in fs
                            if f and all(32 <= c < 127 for c in f))
            print(f"{name} [{label}] {len(fs)} fields, {printable} ascii")
            sh = summarize(fs)
            for (kind, sample), idxs in list(sh.items())[:40]:
                print(f"   {kind:6s} n={len(idxs):3d} "
                      f"first@{idxs[0]:4d} {sample!r}")
            print()
