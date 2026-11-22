#!/usr/bin/env python3
"""Static layout audit for apps/vn/vn.c: finds draw calls whose rectangle
falls outside the 432x240 logical screen, and reports the title menu +
settings rows so spacing problems are visible without a device."""
import re
import sys
from pathlib import Path

SRC = Path("NanoApps/apps/vn/vn.c")
W, H = 432, 240
s = SRC.read_text(encoding="utf-8")

problems = []


def num(tok, consts):
    tok = tok.strip()
    if tok in consts:
        return consts[tok]
    try:
        return int(tok, 0)
    except ValueError:
        return None


# constants
consts = {}
for m in re.finditer(r"#define\s+(\w+)\s+\(?([-\w\s+*/()]+)\)?", s):
    name, expr = m.group(1), m.group(2)
    try:
        consts[name] = int(eval(expr, {}, dict(consts)))
    except Exception:
        pass

# check lfill_rect / draw_button / draw_ascii8 with literal args
for m in re.finditer(r"(lfill_rect|draw_button|ldim_rect|lrect_outline)\(\s*"
                     r"([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)", s):
    fn = m.group(1)
    vals = []
    for g in m.groups()[1:5]:
        v = num(g, consts)
        if v is None:
            vals = None
            break
        vals.append(v)
    if not vals:
        continue
    x, y, w, h = vals
    if x < 0 or y < 0 or x + w > W or y + h > H:
        line = s[:m.start()].count("\n") + 1
        problems.append(f"line {line}: {fn}({x},{y},{w},{h}) -> "
                        f"right={x+w} bottom={y+h} (screen {W}x{H})")

print(f"=== {len(problems)} out-of-screen draw calls ===")
for p in problems:
    print(" ", p)

# title menu rows
y0 = consts.get("TITLE_Y0", 0)
dy = consts.get("TITLE_DY", 0)
n = consts.get("TITLE_N", 0)
print(f"\n=== title menu: Y0={y0} DY={dy} N={n} item_h=26 ===")
for i in range(n):
    y = y0 + i * dy
    flag = "OUT" if y + 26 > H else "ok"
    print(f"  item {i}: y={y}..{y+26} {flag}")
