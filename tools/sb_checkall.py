#!/usr/bin/env python3
"""Walk every chapter script in a pack; report op counts and any overrun."""
import struct
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = [root / "script.bin"] + sorted((root / "ch").glob("*.bin"))
tot_say = tot = tot_voice = bad = 0
for f in files:
    b = f.read_bytes()
    assert b[:4] == b"VNPK", f.name
    nl = struct.unpack_from("<I", b, 8)[0]
    pc = 12 + 4 * nl
    nsay = nops = nvoice = 0
    nxt = None
    while pc < len(b):
        op = b[pc]; pc += 1; nops += 1
        if op == 0:
            break
        elif op == 1:
            pc += 4
        elif op in (2, 5, 12):
            pc += 2 + struct.unpack_from("<H", b, pc)[0]
        elif op == 3:
            pc += 2
            pc += 2 + struct.unpack_from("<H", b, pc)[0]
        elif op == 4:
            pc += 1
        elif op == 6:
            for _ in range(2):
                pc += 2 + struct.unpack_from("<H", b, pc)[0]
            nsay += 1
        elif op == 7:
            cnt = b[pc]; pc += 1
            for _ in range(cnt):
                pc += 4 + struct.unpack_from("<H", b, pc)[0]
        elif op == 8:
            pc += 4
        elif op == 9:
            pc += 2
        elif op == 10:
            nxt = struct.unpack_from("<H", b, pc)[0]; pc += 2
        elif op == 11:
            pc += 2 + struct.unpack_from("<H", b, pc)[0]
            nvoice += 1
        else:
            print(f"BAD op {op} @{pc-1} in {f.name}"); bad += 1; break
        if pc > len(b):
            print(f"OVERRUN in {f.name}"); bad += 1; break
    tot_say += nsay
    tot += nops
    tot_voice += nvoice
print(f"{len(files)} scripts walked: {tot} ops, {tot_say} SAY, "
      f"{tot_voice} VOICE, {bad} bad")
