#!/usr/bin/env python3
"""Verify a GalPack's binary formats against the apps/vn/vn.c consumer."""
import struct
import sys
from pathlib import Path

OPS = {0: "END", 1: "LABEL", 2: "BG", 3: "SPR", 4: "SPRCLR", 5: "BGM",
       6: "SAY", 7: "CHOICE", 8: "JUMP", 9: "WAIT"}

def check_pack(root: Path) -> int:
    errors = 0

    # ---- font.bin ----
    f = (root / "font.bin").read_bytes()
    assert f[:4] == b"VNFN", "font magic"
    w, h, bpp, _ = f[4], f[5], f[6], f[7]
    n = struct.unpack_from("<H", f, 8)[0]
    bpr = (w + 7) // 8
    off = 10
    cps = []
    for _ in range(n):
        cp = struct.unpack_from("<I", f, off)[0]
        cps.append(cp)
        off += 4 + h * bpr
    assert off == len(f), f"font size mismatch: walked {off}, file {len(f)}"
    assert cps == sorted(cps), "font not sorted by codepoint"
    print(f"font.bin OK: {n} glyphs {w}x{h}bpp{bpp}, {len(f)}B")

    # ---- script.bin ----
    s = (root / "script.bin").read_bytes()
    assert s[:4] == b"VNPK", "script magic"
    ver, nl = struct.unpack_from("<II", s, 4)
    assert ver == 1
    table = [struct.unpack_from("<I", s, 12 + 4 * i)[0] for i in range(nl)]
    pc = 12 + 4 * nl
    ops = []
    def u8():
        nonlocal pc
        v = s[pc]; pc += 1; return v
    def u16():
        nonlocal pc
        v = struct.unpack_from("<H", s, pc)[0]; pc += 2; return v
    def u32():
        nonlocal pc
        v = struct.unpack_from("<I", s, pc)[0]; pc += 4; return v
    def txt():
        nonlocal pc
        ln = u16()
        v = s[pc:pc + ln].decode("utf-8")
        pc += ln
        return v
    label_pcs = []
    while pc < len(s):
        op_pos = pc
        op = u8()
        name = OPS.get(op, f"?{op:02x}")
        if op == 0: ops.append("END")
        elif op == 1: label_pcs.append((u32(), op_pos)); ops.append("LABEL")
        elif op in (2, 5): ops.append(f"{name}({txt()!r})")
        elif op == 3:
            slot, pos = u8(), u8(); ops.append(f"SPR{slot}/p{pos}({txt()!r})")
        elif op == 4: ops.append(f"SPRCLR({u8()})")
        elif op == 6:
            nm = txt(); t = txt(); ops.append(f"SAY({nm!r}, {t[:14]!r}...)")
        elif op == 7:
            cnt = u8()
            for _ in range(cnt):
                u32(); txt()
            ops.append(f"CHOICE(x{cnt})")
        elif op == 8: ops.append(f"JUMP({u32()})")
        elif op == 9: ops.append(f"WAIT({u16()})")
        elif op == 10: ops.append(f"NEXT({u16()})")
        else:
            print(f"UNKNOWN OPCODE {op:02x} at {pc-1}"); errors += 1; break
        if op == 0: break
    # OP_END is terminal on-device: bytes after the first END are other
    # branches, reachable only via jumps — that is fine.
    assert pc <= len(s), f"overrun: walked {pc}, file {len(s)}"
    print(f"  (walk stopped at first END; {len(s) - pc}B of branch code follows)")
    for lid, lpc in label_pcs:
        assert lid < nl and table[lid] == lpc, f"label {lid} table mismatch"
    print(f"script.bin OK: {len(ops)} ops, {nl} labels, {len(s)}B")
    print("  " + " | ".join(ops[:10]) + (" ..." if len(ops) > 10 else ""))

    # ---- assets ----
    for sub, fmt, maxdim in (("bg", 0, (432, 240)), ("cg", 0, (432, 240)),
                             ("ui", 0, (432, 240)), ("cgt", 0, (84, 48)),
                             ("spr", 1, (160, 220))):
        d = root / sub
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.bin")):
            b = p.read_bytes()
            assert b[:4] == b"VNBI", f"{p}: magic"
            w, h, fm = struct.unpack_from("<HHB", b, 4)
            need = 9 + w * h * (3 if fm else 2)
            assert fm == fmt, f"{p}: fmt {fm}"
            assert need == len(b), f"{p}: size {len(b)} != {need}"
            if fmt == 0:
                if sub in ("bg", "cg", "ui"):
                    assert (w, h) == maxdim, f"{p}: {sub} {w}x{h}"
                else:
                    assert w <= maxdim[0] and h <= maxdim[1], f"{p}: {w}x{h}"
            else:
                assert w <= maxdim[0] and h <= maxdim[1], f"{p}: spr {w}x{h}"
            print(f"{sub}/{p.name} OK: {w}x{h} fmt{fm} {len(b)}B")

    # ---- cg.idx ----
    cg_names = []
    p = root / "cg.idx"
    if p.is_file():
        b = p.read_bytes()
        assert b[:4] == b"VNCG", "cg.idx magic"
        ver, n = struct.unpack_from("<HH", b, 4)
        assert ver == 1
        off = 8
        for _ in range(n):
            ln = struct.unpack_from("<H", b, off)[0]
            off += 2
            cg_names.append(b[off:off + ln].decode("utf-8"))
            off += ln
        assert off == len(b), f"cg.idx size {len(b)} != {off}"
        assert n <= 512
        for nm in cg_names:
            assert (root / "cg" / f"{nm}.bin").is_file(), f"cg asset {nm}.bin"
            assert (root / "cgt" / f"{nm}.bin").is_file(), f"cgt asset {nm}.bin"
        print(f"cg.idx OK: {n} entries, all cg/cgt assets present")

    # ---- flow.idx ----
    p = root / "flow.idx"
    if p.is_file():
        b = p.read_bytes()
        assert b[:4] == b"VNFL", "flow.idx magic"
        ver, n = struct.unpack_from("<HH", b, 4)
        assert ver == 1
        off = 8
        ids = []
        for _ in range(n):
            lid = struct.unpack_from("<I", b, off)[0]
            ln = struct.unpack_from("<H", b, off + 4)[0]
            off += 6
            title = b[off:off + ln].decode("utf-8")
            off += ln
            assert lid < nl, f"flow label {lid} >= {nl}"
            ids.append(title)
        assert off == len(b), f"flow.idx size {len(b)} != {off}"
        assert n <= 256
        print(f"flow.idx OK: {n} nodes (labels verified)")

    return errors

if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "build/galpack-demo")
    sys.exit(1 if check_pack(root) else 0)
