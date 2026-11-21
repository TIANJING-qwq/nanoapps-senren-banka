#!/usr/bin/env python3
"""Build the authoritative file -> (order, group, title) mapping from
scenelist.psb.tjs. Output: NanoApps/build/sb_scenemap.tsv
  file <tab> order <tab> group <tab> title
Title = original chapter number + the file's own Japanese name,
e.g. 001 -> '1-1 アーサー王'.
Route groups (original structure):
  0 common  001-015 (+113 end/114 epi/115 after)
  1 yoshino 200-211            2 mako 301-317
  3 murasame 414-429 (non-レナ) 4 rena 415レナ-429レナ
  5 koharu 501-513(508a)        6 roka 509,521-523(508b)
"""
import re
from pathlib import Path

SRC = Path(r"K:\千恋＊万花\outPath\data.xp3\scn\scenelist.psb.tjs")
OUT = Path("NanoApps/build/sb_scenemap.tsv")

body = SRC.read_text(encoding="utf-8")[SRC.read_text(encoding="utf-8").index('"list"'):]
raw = re.split(r"\n    \(const\) %\[", body)
flow = []
for chunk in raw[1:]:
    st = re.search(r'"storage" => "(.*?)"', chunk)
    ti = re.search(r'"title" => "(.*?)"', chunk)
    if st:                      # keep untitled entries too (e.g. 108)
        flow.append((st.group(1), ti.group(1) if ti else ""))

GROUPS = [
    (lambda f, n: n <= 115 or n <= 15, "common"),
]


def group_of(fname: str) -> str:
    stem = fname.split("・")[0]
    m = re.match(r"(\d+)([ab]?)(レナ)?", stem)
    if not m:
        return "?"
    n, ab, rena_sfx = int(m.group(1)), m.group(2), m.group(3) is not None
    if rena_sfx:                       # 414レナ..429レナ — the rena route
        return "rena"
    if n <= 15:
        return "common"
    if 100 <= n < 200:
        return "yoshino"
    if 200 <= n < 300:
        return "mako"
    if 300 <= n < 400:
        return "murasame"
    if n == 508:
        return "roka" if ab == "b" else "koharu"
    if 500 <= n < 520:
        return "koharu"
    return "roka"

# first-appearance order of each storage file
seen, order = {}, 0
rows = []
for storage, title in flow:
    stem = storage.split("・")[0]
    # key: numeric stem; the rena-route files are "414レナ・..." so the
    # suffix is glued to the number — but "006・レナ登場" is NOT a rena
    # route (chapter named after the character). split("・")[0] keeps
    # "414レナ" vs "006" correctly.
    key = stem
    if key not in seen:
        seen[key] = order
        order += 1
    rows.append((key, storage, title))

best = {}
for key, storage, title in rows:
    if key not in best or (not best[key][1] and title):
        best[key] = (storage, title)

out = []
for key, (storage, title) in sorted(best.items(), key=lambda kv: seen[kv[0]]):
    stem = storage.split("・")[0]
    jp = storage.split("・", 1)[1] if "・" in storage else ""
    jp = re.sub(r"ver[\d.]+.*$", "", jp).strip()   # strip ver1.07(.ks...) tail
    chno = title.replace("chapter\u3000", "")
    disp = f"{chno} {jp}" if chno else jp
    out.append((seen[key], key, group_of(storage), disp))

OUT.write_text("\n".join(f"{k}\t{o}\t{g}\t{t}" for o, k, g, t in out),
               encoding="utf-8")
print(f"{len(out)} files mapped -> {OUT}")
for o, k, g, t in out[:8]:
    print(f"  {o:3d} {k:8s} {g:10s} {t}")
print("  ...")
for o, k, g, t in out[-6:]:
    print(f"  {o:3d} {k:8s} {g:10s} {t}")
from collections import Counter
print(Counter(g for _, _, g, _ in out))
