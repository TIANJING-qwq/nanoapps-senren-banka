#!/usr/bin/env python3
"""Walk a VNPK script and report opcode counts + any CG/choice payloads."""
import struct
import sys
from collections import Counter
from pathlib import Path

NAMES = {0: "END", 1: "LABEL", 2: "BG", 3: "SPR", 4: "SPRCLR", 5: "BGM",
         6: "SAY", 7: "CHOICE", 8: "JUMP", 9: "WAIT", 10: "NEXT",
         11: "VOICE", 12: "CG"}


def rd_str(b, pc):
    ln = struct.unpack_from("<H", b, pc)[0]
    return b[pc + 2:pc + 2 + ln].decode("utf-8", "replace"), pc + 2 + ln


def walk(b, start, label):
    pc = start
    ops = Counter()
    cgs, bgs, sprs = [], [], []
    while pc < len(b):
        op = b[pc]
        pc += 1
        ops[NAMES.get(op, hex(op))] += 1
        if op == 0:
            break
        elif op == 1:
            pc += 4
        elif op in (2, 5, 11, 12):
            txt, pc = rd_str(b, pc)
            if op == 2:
                bgs.append(txt)
            elif op == 12:
                cgs.append(txt)
        elif op == 3:
            pc += 2
            txt, pc = rd_str(b, pc)
            sprs.append(txt)
        elif op == 4:
            pc += 1
        elif op == 6:
            nm, pc = rd_str(b, pc)
            tx, pc = rd_str(b, pc)
        elif op == 7:
            n = b[pc]
            pc += 1
            for _ in range(n):
                pc += 4
                _, pc = rd_str(b, pc)
        elif op in (8,):
            pc += 4
        elif op in (9, 10):
            pc += 2
        else:
            print("bad op", op, "at", pc - 1)
            break
    print(f"{label}: {sum(ops.values())} ops")
    for k, v in ops.most_common():
        print(f"   {k:8s} {v}")
    print("   bgs:", bgs[:6])
    print("   cgs:", cgs[:6])
    print("   sprs:", sprs[:6])


if __name__ == "__main__":
    f = Path(sys.argv[1])
    b = f.read_bytes()
    nl = struct.unpack_from("<I", b, 8)[0]
    starts = [struct.unpack_from("<I", b, 12 + 4 * i)[0] for i in range(nl)]
    print(f"{f.name}: {nl} labels at {starts}")
    for i, st in enumerate(starts):
        walk(b, st, f"label {i}")
