#!/usr/bin/env python3
"""unpack_xp3.py — KiriKiri Z (krkrZ) XP3 unpacker for Yuzusoft archives.

Handles the 12-byte krkrZ signature variant ("XP3\r\n \x0a\x1a\x8bg\x01\x17")
with the zlib-compressed index at a pointer stored at offset 0x20, and the
1-flag + u64 sizes table prologue. File data segments are stored or
zlib-compressed. This matches the Senren Banka archives (data/bgm/voice/
bgimage/fgimage/patch, 720p and 1080p variants).

Usage:
  python tools/unpack_xp3.py list ARCHIVE [filter-substr]
  python tools/unpack_xp3.py extract ARCHIVE OUTDIR [--filter SUBSTR]
      [--limit N] [--flat]
"""
from __future__ import annotations

import argparse
import io
import os
import struct
import sys
import zlib
from pathlib import Path

KRKRZ_SIG = bytes.fromhex("5850330D0A200A1A8B67")   # minor-version suffix varies
IDX_PTR_OFF = 0x20


def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def u32(b, o): return struct.unpack_from("<I", b, o)[0]
def u64(b, o): return struct.unpack_from("<Q", b, o)[0]


def die(msg):
    print(f"unpack_xp3: error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_index(f) -> bytes:
    head = f.read(0x28)
    if head[:8] == bytes.fromhex("5850330D0A1A0A"):          # krkr2 variant
        f.seek(0x10)
        idx = u64(f.read(8), 0)
    elif head[:10] == KRKRZ_SIG:                              # krkrZ variant
        idx = u64(head, IDX_PTR_OFF)
    else:
        die(f"not an XP3 archive (sig={head[:12].hex()})")
    f.seek(idx)
    pro = f.read(17)
    flag, csize, usize = pro[0], u64(pro, 1), u64(pro, 9)
    if flag == 1:
        raw = f.read(csize)
        return zlib.decompress(raw)
    return f.read(usize)


def parse_table(t: bytes):
    """Yield entries: {name, size, adler, segments}."""
    pos = 0
    entries = []
    while pos + 12 <= len(t):
        tag = t[pos:pos + 4]
        size = u64(t, pos + 4)
        body = t[pos + 12:pos + 12 + size]
        pos += 12 + size
        if tag != b"File":
            continue                                     # 'utfs'/'time'/etc.
        p = 0
        name, fsize, segs, adler = None, 0, [], 0
        while p + 12 <= len(body):
            ctag = body[p:p + 4]
            csize = u64(body, p + 4)
            cdata = body[p + 12:p + 12 + csize]
            p += 12 + csize
            if ctag == b"adlr":
                adler = u32(cdata, 0)
            elif ctag == b"info":
                fsize = u64(cdata, 4)                 # protect u32, then size
                nl = u16(cdata, 20)                   # u16 name length @20
                name = cdata[22:22 + nl * 2].decode("utf-16-le", "replace")
            elif ctag in (b"sect", b"segm"):            # krkr2/krkrZ spellings
                if ctag == b"sect":
                    n, q = u32(cdata, 0), 4    # krkr2: u32 count prefix
                else:
                    n, q = len(cdata) // 28, 0  # krkrZ: bare 28-byte array
                for _ in range(n):
                    comp = u32(cdata, q)
                    off = u64(cdata, q + 4)
                    cs = u64(cdata, q + 12)
                    rs = u64(cdata, q + 20)
                    segs.append((off, cs, rs, comp))
                    q += 28
        if name is not None:
            entries.append((name, fsize, segs, adler))
    return entries


def extract_entry(f, segs) -> bytes:
    out = bytearray()
    for off, cs, rs, comp in segs:
        f.seek(off)
        data = f.read(cs)
        if comp == 1:
            data = zlib.decompress(data)
        out += data
    return bytes(out)


def safe_rel(name: str) -> Path:
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    parts = [p[:80] for p in parts] or ["_unnamed"]
    return Path(*parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["list", "extract"])
    ap.add_argument("archive")
    ap.add_argument("outdir", nargs="?")
    ap.add_argument("--filter", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--flat", action="store_true",
                    help="strip paths (name collision = last wins)")
    ap.add_argument("--decrypt", metavar="TJS",
                    help="apply the Yuzusoft cxdec filter (path to the "
                         "community xp3filter.tjs with the key table)")
    args = ap.parse_args()

    dec = None
    if args.decrypt:
        from cxdec import cxdec_factory
        dec = cxdec_factory(args.decrypt)

    arc = Path(args.archive)
    if not arc.is_file():
        die(f"archive not found: {arc}")
    f = open(arc, "rb")
    table = read_index(f)
    entries = parse_table(table)
    flt = args.filter.lower()
    shown = 0
    byext = {}
    for name, fsize, segs, adler in entries:
        ext = Path(name).suffix.lower() or "(none)"
        byext[ext] = byext.get(ext, [0, 0])
        byext[ext][0] += 1
        byext[ext][1] += fsize
        if args.mode == "list" and (not flt or flt in name.lower()):
            print(f"{fsize:>12,}  {adler:08x}  {name}")
            shown += 1
            if args.limit and shown >= args.limit:
                break
    if args.mode == "list":
        print(f"\n{len(entries)} files; by extension:")
        for ext, (n, sz) in sorted(byext.items(), key=lambda kv: -kv[1][1]):
            print(f"  {ext:<8} {n:>6} files  {sz/1048576:>9.1f} MiB")
        return

    out = Path(args.outdir or ".")
    out.mkdir(parents=True, exist_ok=True)
    n_ok = n_skip = 0
    for name, fsize, segs, adler in entries:
        if flt and flt not in name.lower():
            continue
        rel = safe_rel(name)
        dst = out / (rel.name if args.flat else rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = extract_entry(f, segs)
            if dec:
                data = dec(adler, data)
        except Exception as e:                            # noqa: BLE001
            print(f"  FAIL {name}: {e}", file=sys.stderr)
            n_skip += 1
            continue
        dst.write_bytes(data)
        n_ok += 1
        if n_ok % 200 == 0:
            print(f"  {n_ok} files...")
        if args.limit and n_ok >= args.limit:
            break
    print(f"extracted {n_ok} files ({n_skip} failed) -> {out}")


if __name__ == "__main__":
    main()
