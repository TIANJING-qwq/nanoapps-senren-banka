#!/usr/bin/env python3
"""psb — M2 PSB (v3) parser for decrypted Yuzusoft scenario blobs.

Layout confirmed by hexdump of live samples (see tools/psb_probe.py):

    0x00 "PSB\\0"  u16 ver  u16 enc(0)
    0x08 u32 key_index_offset     (u16 per chunk key, in file order)
    0x0C u32 str_offsets_offset   (u8 table of NUL-string offsets)
    0x10 u32 chunk_offsets_offset (u32 table)
    0x14 u32 chunk_lengths_offset (u32 table)
    0x18 u32 entry_offset
    0x1C u32 tree_offset
    (regions may alias when empty)

Tree value encoding (M2 standard):
    0x0A nil | 0x0B/0x0C false/true | 0x0D/0x0E +/-infinity | 0x0F nan
    0x1n  n-byte little-endian int (n=0..4), 0x19 = 8-byte int? (n=9)
    0x2n  chunk (object): n = key count; then key indices (u8 or 0x1n-prefixed)
    0x3n  string: n bytes index into the string table
    0x4n  array: n = element count (or 0x4F then int) — layout: elements
    0x5n  binary chunk index | 0x6n float | 0x7n double? (both little-endian)

Usage:  python psb.py FILE dump        (pretty tree)
        python psb.py FILE strings     (string table)
        from psb import load_psb       (returns python tree)
"""
from __future__ import annotations

import struct


class PSB:
    def __init__(self, data: bytes):
        self.d = data
        if data[:4] != b"PSB\x00":
            raise ValueError("not a PSB")
        self.ver, self.enc = struct.unpack_from("<HH", data, 4)
        (self.k_off, self.s_off, self.co_off, self.cl_off, self.ent_off,
         self.tree_off) = struct.unpack_from("<6I", data, 8)
        # key index table: u16 values starting at k_off (0x2c); count unknown
        # until we hit the str-offset region; derive from region sizes below.
        # str offset table: u8 offsets, strings NUL-separated right after.
        self._read_strings()
        self._read_chunks()
        self._read_keys()

    # -- string table ------------------------------------------------------
    def _read_strings(self):
        p = self.s_off
        d = self.d
        offs = []
        while p < min(self.co_off, len(d)):
            offs.append(d[p])
            p += 1
            if d[p - 1] == 0xFF or p >= len(d):      # extended marker
                break
        base = p
        strs = []
        for o in offs:
            e = d.index(b"\x00", base + o)
            strs.append(d[base + o:e].decode("utf-8", "replace"))
        self.strings = strs
        self.str_base = base

    # -- chunk offsets/lengths ----------------------------------------------
    def _read_chunks(self):
        d = self.d
        self.chunks = []                      # (offset, length)
        p = self.co_off
        while p + 4 <= self.cl_off:
            self.chunks.append(struct.unpack_from("<I", d, p)[0])
            p += 4
        lens = []
        p = self.cl_off
        while p + 4 <= max(self.ent_off, self.cl_off + 4):
            if p + 4 > len(d):
                break
            lens.append(struct.unpack_from("<I", d, p)[0])
            p += 4
            if p >= self.ent_off:
                break
        # zip; lengths region may be empty -> chunk bodies hold their own
        self.chunk_lens = lens

    def _read_keys(self):
        # u16 key-name indices between k_off and s_off
        n = (self.s_off - self.k_off - 4) // 2
        if n > 0:
            self.keys = list(struct.unpack_from(f"<{n}H", self.d,
                                                self.k_off + 4))
        else:
            self.keys = []

    # -- tree ---------------------------------------------------------------
    def value(self, off):
        d = self.d
        t = d[off]
        hi, lo = t >> 4, t & 0x0F
        if t == 0x0A:
            return None
        if t == 0x0B:
            return False
        if t == 0x0C:
            return True
        if hi == 0x1:
            if lo == 0:
                return 0
            return int.from_bytes(d[off + 1:off + 1 + lo], "little")
        if hi == 0x2:                              # chunk (dict)
            n = lo
            p = off + 1
            keys = []
            for _ in range(n):
                if d[p] >> 4 == 0x1:               # int-indexed key
                    k = d[p] & 0x0F
                    if k:
                        keys.append(int.from_bytes(d[p + 1:p + 1 + k], "little"))
                        p += 1 + k
                    else:
                        keys.append(0)
                        p += 1
                else:
                    keys.append(d[p])
                    p += 1
            out = {}
            for k in keys:
                v, p = self._value_at(p)
                out[self.strings[k] if k < len(self.strings) else f"#{k}"] = v
            return out
        if hi == 0x3:                              # string ref
            n = lo
            if n == 0:
                return ""
            idx = int.from_bytes(d[off + 1:off + 1 + n], "little")
            return self.strings[idx] if idx < len(self.strings) else f"#{idx}"
        if hi == 0x4:                              # array
            p = off + 1
            if lo == 0x0F:
                n, p = self._int_at(p)
            else:
                n = lo
            out = []
            for _ in range(n):
                v, p = self._value_at(p)
                out.append(v)
            return out
        if hi == 0x5:                              # binary blob ref
            n = lo
            idx = int.from_bytes(d[off + 1:off + 1 + n], "little") if n else 0
            if idx < len(self.chunks):
                o = self.chunks[idx]
                ln = self.chunk_lens[idx] if idx < len(self.chunk_lens) else 0
                return d[o:o + ln]
            return b""
        if hi == 0x6:                              # float
            return struct.unpack_from("<f", d, off + 1)[0]
        if hi == 0x7:                              # double
            return struct.unpack_from("<d", d, off + 1)[0]
        raise ValueError(f"unknown type {t:#04x} @ {off:#x}")

    def _int_at(self, p):
        t = self.d[p]
        if t >> 4 == 0x1:
            n = t & 0x0F
            if n == 0:
                return 0, p + 1
            return int.from_bytes(self.d[p + 1:p + 1 + n], "little"), p + 1 + n
        return self.d[p], p + 1

    def _value_at(self, p):
        # peek length of value starting at p: chunks/arrays recurse via value()
        v = self.value(p)
        return v, None                             # caller re-scans if needed

    def entry(self):
        return self.value(self.ent_off)


def load_psb(data: bytes):
    return PSB(data)


def _pretty(v, indent=0):
    pad = "  " * indent
    if isinstance(v, dict):
        lines = [f"{pad}{{"] if indent else ["{"]
        for k, x in v.items():
            if isinstance(x, (dict, list)) and _small(x):
                lines.append(f"{pad}  {k}: {_pretty(x, 1).strip()}")
            elif isinstance(x, (dict, list)):
                lines.append(f"{pad}  {k}:")
                lines += _pretty(x, indent + 2)
            else:
                lines.append(f"{pad}  {k}: {_clip(x)}")
        lines.append(f"{pad}}}" if indent else "}")
        return "\n".join(lines)
    if isinstance(v, list):
        items = ", ".join(_clip(x) for x in v[:12])
        more = "" if len(v) <= 12 else f", …×{len(v) - 12}"
        return f"{pad}[{items}{more}]"
    return f"{pad}{_clip(v)}"


def _small(v):
    if isinstance(v, dict):
        return len(v) <= 4
    return len(v) <= 8


def _clip(v):
    s = repr(v)
    return s if len(s) <= 90 else s[:87] + "..."


if __name__ == "__main__":
    import sys
    from pathlib import Path

    data = Path(sys.argv[1]).read_bytes()
    mode = sys.argv[2] if len(sys.argv) > 2 else "dump"
    psb = PSB(data)
    if mode == "strings":
        for i, s in enumerate(psb.strings):
            print(f"[{i:4}] {s}")
    else:
        print(f"strings={len(psb.strings)} chunks={len(psb.chunks)} "
              f"keys={len(psb.keys)}")
        print(_pretty(psb.entry()))
