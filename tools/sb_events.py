#!/usr/bin/env python3
"""Extract the FULL presentation event stream from .psb.tjs dumps
(background / character / dialogue), each event attributed to the scene
label it belongs to, ordered by source position.

Output NanoApps/build/sb_events.tsv:
  base \t label \t B \t <bg image name>
  base \t label \t C \t <char> \t <stand file>
  base \t label \t S \t <speaker> \t <text> \t <voice>

The dumps are huge (some .psb.tjs are ~38 MB), so this uses plain str.find
cursor scanning (C speed) instead of regex finditer.
"""
import bisect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from voice83 import short_of          # long voice name -> 8.3 short name
except Exception:
    def short_of(v):
        return ""

SCN = Path("K:/千恋＊万花/outPath/data.xp3/scn")
OUT = Path("NanoApps/build/sb_events.tsv")

VOID = "void,"
SCENE_HDR = re.compile(
    r'\n    \(const\) %\[\n(?:      "firstLine" => -?\d+,\n)?'
    r'      "label" => "([^"]+)",')


def scan(s, key):
    """yield (pos, value) for `"<key>" => "<value>"`."""
    pat = '"' + key + '" => "'
    n = len(pat)
    p = 0
    while True:
        i = s.find(pat, p)
        if i < 0:
            return
        j = s.find('"', i + n)
        if j < 0:
            return
        yield i, s[i + n:j]
        p = j + 1


def extract(path: Path):
    base = path.name.split("ver")[0]
    s = path.read_text(encoding="utf-8", errors="replace")

    labels = [(m.start(), m.group(1)) for m in SCENE_HDR.finditer(s)]
    starts = [p for p, _ in labels]

    def label_of(pos):
        i = bisect.bisect_right(starts, pos) - 1
        return labels[i][1] if i >= 0 else ""

    raw = []                                # (pos, payload tuple)

    # ---- background / character events (from "class" + "name" + "file") ----
    c_iter = scan(s, "class")
    n_iter = scan(s, "name")
    c = next(c_iter, None)
    nm = next(n_iter, None)
    last_class = (-1, "")
    last_name = (-1, "")
    for pos, fname in scan(s, "file"):
        while c is not None and c[0] < pos:
            last_class = c
            c = next(c_iter, None)
        while nm is not None and nm[0] < pos:
            last_name = nm
            nm = next(n_iter, None)
        cls = last_class[1] if 0 <= pos - last_class[0] < 8000 else ""
        if cls == "stage":
            raw.append((pos, ("B", fname)))
        elif cls == "character":
            ch = fname.split(".")[0] if "." in fname else fname
            raw.append((pos, ("C", ch, fname)))

    # ---- dialogue blocks: line `"<sp>",` + line `void,` + line `"<tx>",` ---
    p = 0
    while True:
        i = s.find(VOID, p)
        if i < 0:
            break
        ls = s.rfind("\n", 0, i) + 1
        if s[ls:i].strip():
            p = i + 5
            continue
        pe = ls - 1
        ps = s.rfind("\n", 0, pe) + 1
        sp_line = s[ps:pe].strip()
        if not (sp_line.startswith('"') and sp_line.endswith('",')
                and "=>" not in sp_line):
            p = i + 5
            continue
        sp = sp_line[1:-2]
        ne = s.find("\n", i)
        if ne < 0:
            break
        ns2 = ne + 1
        ne2 = s.find("\n", ns2)
        tx_line = s[ns2:ne2 if ne2 >= 0 else len(s)].strip()
        if not (tx_line.startswith('"') and tx_line.endswith('",')):
            p = i + 5
            continue
        tx = tx_line[1:-2]
        voice = ""
        v = s.find('"voice" => "', i, i + 2500)
        if v >= 0:
            w = s.find('"', v + 12)
            if w > v:
                voice = s[v + 12:w]
        if voice:
            s8 = short_of(voice)
            if s8:
                voice = s8[:-4]
        if tx.strip():
            raw.append((i, ("S", sp, tx, voice)))
        p = i + 5

    raw.sort(key=lambda t: t[0])
    return base, [(label_of(pos), payload) for pos, payload in raw]


rows = []
for f in sorted(SCN.glob("*.psb.tjs")):
    base, evs = extract(f)
    for label, payload in evs:
        rows.append((base, label) + payload)

with OUT.open("w", encoding="utf-8") as fh:
    for r in rows:
        fh.write("\t".join(r) + "\n")
nb = sum(1 for r in rows if r[2] == "B")
nc = sum(1 for r in rows if r[2] == "C")
ns = sum(1 for r in rows if r[2] == "S")
nv = sum(1 for r in rows if r[2] == "S" and r[5])
print(f"{len(rows)} events: {nb} bg, {nc} sprite, {ns} say ({nv} voiced)")
