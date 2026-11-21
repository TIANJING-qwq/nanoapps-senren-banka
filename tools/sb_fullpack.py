#!/usr/bin/env python3
"""Assemble the full Senren Banka pack: font over ALL dialogue chars +
88-chapter scripts + flow.idx + converted bg/cg/title assets."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_galpack import build_font, find_font  # noqa: E402

src = Path(sys.argv[1])          # sb_pack (scripts+flow)
out = Path(sys.argv[2])          # target pack dir
out.mkdir(parents=True, exist_ok=True)

# 1) font over every char in every script + names + titles
chars = set()
def rd_str(b, pc):
    ln = struct.unpack_from("<H", b, pc)[0]
    s = b[pc + 2:pc + 2 + ln].decode("utf-8", "replace")
    return s, pc + 2 + ln


for f in [src / "script.bin"] + sorted((src / "ch").glob("*.bin")):
    b = f.read_bytes()
    nl = struct.unpack_from("<I", b, 8)[0]
    pc = 12 + 4 * nl
    while pc < len(b):
        op = b[pc]; pc += 1
        if op in (0, 4):
            if op == 0:
                break
            pc += 1
        elif op == 1:
            pc += 4
        elif op in (2, 5):
            _, pc = rd_str(b, pc)
        elif op == 3:
            pc += 2
            _, pc = rd_str(b, pc)
        elif op == 6:
            for _ in range(2):
                s, pc = rd_str(b, pc)
                chars |= set(s)
        elif op == 8:
            pc += 4
        elif op == 9:
            pc += 2
        elif op == 10:
            pc += 2
        else:
            print(f"op {op} at {pc - 1} in {f.name}"); sys.exit(1)
chars |= set((src / "chapters.tsv").read_text(encoding="utf-8"))
chars = {c for c in chars if ord(c) >= 0x20} - {"\n", "\t"}
print(f"{len(chars)} unique glyphs needed")

fp = find_font(None)
blob = build_font(chars, 16, fp)
(out / "font.bin").write_bytes(blob)
print(f"font.bin {len(blob):,} B")

# 2) scripts + flow
(out / "script.bin").write_bytes((src / "script.bin").read_bytes())
(out / "flow.idx").write_bytes((src / "flow.idx").read_bytes())
(out / "ch").mkdir(exist_ok=True)
for f in (src / "ch").glob("*.bin"):
    (out / "ch" / f.name).write_bytes(f.read_bytes())
print(f"scripts: 1 + {len(list((src / 'ch').glob('*.bin')))} chapters")

# 3) assets from the verified demo pack (bg/cg/cgt/spr/ui/bgm)
demo = Path("NanoApps/build/galpack-demo")
for sub in ("bg", "cg", "cgt", "spr", "ui", "bgm"):
    d = demo / sub
    if d.exists():
        (out / sub).mkdir(exist_ok=True)
        for f in d.iterdir():
            (out / sub / f.name).write_bytes(f.read_bytes())
print("assets copied from demo pack")
