#!/usr/bin/env python3
"""cxdec — Yuzusoft XP3 content decryption, ported 1:1 from the community
xp3filter.tjs (KiriKiri Z Storages.setXP3ArchiveExtractionFilter hook).

The filter decrypts a file stream given its 32-bit hash (the XP3 'adlr'
chunk value = adler32 of the original filename) — the filename itself is
not needed. Usage as a module:

    from cxdec import cxdec_decode
    cxdec_decode(hash, buf)          # buf: mutable bytearray, whole file

Or CLI:  python cxdec.py XP3FILE OUTDIR   (decrypt every entry in place of
unpack_xp3.py output; experimental)
"""
from __future__ import annotations

import re
import sys

M32 = 0xFFFFFFFF


def _load_ecb(tjs_path: str) -> list[int]:
    src = open(tjs_path, encoding="utf-8", errors="replace").read()
    m = re.search(r"var tempBlock = \[(.*?)\];", src, re.S)
    if not m:
        raise RuntimeError("tempBlock not found in xp3filter.tjs")
    vals = [int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", m.group(1))]
    if len(vals) != 4096:
        raise RuntimeError(f"tempBlock has {len(vals)} bytes, want 4096")
    return [vals[i] | (vals[i + 1] << 8) | (vals[i + 2] << 16) |
            (vals[i + 3] << 24) for i in range(0, 4096, 4)]


class Cxdec:
    def __init__(self, tjs_path: str):
        self.ECB = _load_ecb(tjs_path)
        self.xcode_seed = 0
        self.cache: dict[int, list] = {}

    # ---- PRNG -------------------------------------------------------------
    def _rand(self) -> int:
        seed = self.xcode_seed
        self.xcode_seed = (1103515245 * seed + 12345) & M32
        return (self.xcode_seed ^ ((seed << 16) & M32) ^ (seed >> 16)) & M32

    # ---- xcode program building -------------------------------------------
    def _push(self, xcode: list, n: int, inst) -> bool:
        xcode[0] += n
        if xcode[0] > 128:
            return False
        xcode.append(inst)
        return True

    def _first_stage(self, xcode: list) -> bool:
        r = self._rand() % 3
        if r == 2:
            xcode[0] += 7
            if xcode[0] > 128:
                return False
            return self._push(xcode, 4, [0, self.ECB[self._rand() & 0x3FF]])
        if r == 1:
            xcode[0] += 1
            if xcode[0] > 128:
                return False
            return self._push(xcode, 4, [0, self._rand()])
        return self._push(xcode, 2, [16])

    def _stage0(self, xcode: list, stage: int) -> bool:
        stage -= 1
        if stage == 1 - 1:                      # stage-- == 1 in TJS
            return self._first_stage(xcode)
        if self._rand() & 1:
            if not self._stage1(xcode, stage):
                return False
        else:
            if not self._stage0(xcode, stage):
                return False
        r = self._rand() & 7
        if r == 5:
            return self._push(xcode, 2, [2])
        if r == 4:
            return self._push(xcode, 2, [3])
        if r == 2:
            return self._push(xcode, 1, [4])
        if r == 6:
            return self._push(xcode, 1, [5])
        if r == 7:
            return self._push(xcode, 21, [79])
        if r == 3:
            xcode[0] += 1
            if xcode[0] > 128:
                return False
            return self._push(xcode, 4, [8, self._rand()])
        if r == 0:
            sel = self._rand() & 1                     # selector FIRST
            xcode[0] += 1
            if xcode[0] > 128:
                return False
            return self._push(xcode, 4, [6 if sel else 7, self._rand()])
        # r == 1: table_ECB
        return self._push(xcode, 13, [80])

    def _stage1(self, xcode: list, stage: int) -> bool:
        stage -= 1
        if stage == 0:
            return self._first_stage(xcode)
        if not self._push(xcode, 1, [11]):
            return False
        if self._rand() & 1:
            if not self._stage1(xcode, stage):
                return False
        else:
            if not self._stage0(xcode, stage):
                return False
        if not self._push(xcode, 2, [1]):
            return False
        if self._rand() & 1:
            if not self._stage1(xcode, stage):
                return False
        else:
            if not self._stage0(xcode, stage):
                return False
        r = self._rand() % 6
        if r == 2:
            ok = self._push(xcode, 2, [9])
        elif r == 5:
            ok = self._push(xcode, 2, [10])
        elif r == 0:
            ok = self._push(xcode, 2, [3]) and self._push(xcode, 2, [9])
        elif r == 3:
            ok = self._push(xcode, 3, [15])
        elif r == 1:
            ok = self._push(xcode, 9, [14])
        else:
            ok = self._push(xcode, 9, [13])
        if not ok:
            return False
        return self._push(xcode, 1, [12])

    def _build(self, seed: int) -> list:
        self.xcode_seed = seed
        xcode = []
        for stage in range(5, 0, -1):
            xcode = [5 + 4]
            if self._stage1(xcode, stage) and xcode[0] + 5 + 1 <= 128:
                break
        return xcode

    # ---- VM ----------------------------------------------------------------
    def _execute(self, xcode: list, arg: int) -> int:
        reg = 0
        reg2 = 0
        stack = []
        for inst in xcode[1:]:
            op = inst[0]
            if op == 0:
                reg = inst[1] & M32
            elif op == 16:
                reg = arg & M32
            elif op == 1:
                reg2 = reg
            elif op == 2:
                reg ^= M32
            elif op == 3:
                reg = (-reg) & M32
            elif op == 4:
                reg = (reg + 1) & M32
            elif op == 5:
                reg = (reg - 1) & M32
            elif op == 6:
                reg = (reg + inst[1]) & M32
            elif op == 7:
                reg = (reg - inst[1]) & M32
            elif op == 8:
                reg ^= inst[1] & M32
            elif op == 9:
                reg = (reg + reg2) & M32
            elif op == 10:
                reg = (reg - reg2) & M32
            elif op == 11:
                stack.append(reg2)
            elif op == 12:
                reg2 = stack.pop() if stack else 0
            elif op == 13:
                reg >>= reg2 & 0xF
            elif op == 14:
                reg = (reg << (reg2 & 0xF)) & M32
            elif op == 15:
                reg = (reg * reg2) & M32
            elif op == 80:
                reg = self.ECB[reg & 0x3FF]
            elif op == 79:
                reg = (((reg & 0xAAAAAAAA) >> 1) | ((reg & 0x55555555) << 1)) & M32
        return reg & M32

    def _execute_xcode(self, h: int):
        index = h & 0x7F
        h >>= 7
        if index not in self.cache:
            self.cache[index] = self._build(index)
        prog = self.cache[index]
        return self._execute(prog, h), self._execute(prog, (h ^ M32) & M32)

    # ---- byte-level decrypt -------------------------------------------------
    def _decode_block(self, h: int, offset: int, buf: bytearray, base: int, ln: int):
        r0, r1 = self._execute_xcode(h)
        key8 = (r0 >> 8) & 0xFF
        key9 = (r0 >> 16) & 0xFF
        key10 = r0 & 0xFF
        key1 = r1 >> 16
        key2 = r1 & 0xFFFF
        if key1 == key2:
            key2 += 1
        if key10 == 0:
            key10 = 1
        if offset <= key2 < offset + ln:
            buf[base + key2 - offset] ^= key9
        if offset <= key1 < offset + ln:
            buf[base + key1 - offset] ^= key8
        for i in range(base, base + ln):
            buf[i] ^= key10

    def decode(self, h: int, offset: int, buf: bytearray, ln: int) -> None:
        boundary = (h & 0x134) + 0x736
        base = 0
        if offset < boundary:
            dec = min(boundary - offset, ln)
            self._decode_block(h, offset, buf, base, dec)
            offset += dec
            base += dec
            ln -= dec
        if ln:
            self._decode_block(((h >> 16) ^ h) & M32, offset, buf, base, ln)


def cxdec_factory(tjs_path: str):
    cx = Cxdec(tjs_path)

    def cxdec_decode(h: int, data: bytes) -> bytearray:
        buf = bytearray(data)
        cx.decode(h & M32, 0, buf, len(buf))
        return buf

    return cxdec_decode


if __name__ == "__main__":
    # self-test: decrypt a raw entry blob given hash, write out
    #   python cxdec.py HASH BLOBFILE OUTFILE
    h = int(sys.argv[1], 0)
    blob = open(sys.argv[2], "rb").read()
    dec = cxdec_factory(r"K:\千恋＊万花\补丁\解密补丁\xp3filter.tjs")
    out = dec(h, blob)
    open(sys.argv[3], "wb").write(out)
    print(f"decrypted {len(out)}B, head: {out[:16].hex(' ')}")
