#!/usr/bin/env python3
"""Extract the FULL presentation event stream from .psb.tjs dumps
(background / character / dialogue, ordered by source position).

The dumps are huge (some .psb.tjs are ~38 MB), so this uses plain str.find
cursor scanning (C speed) instead of regex finditer.

Output NanoApps/build/sb_events.tsv:
  base \t B \t <bg image name>
  base \t C \t <char> \t <stand file>
  base \t S \t <speaker> \t <text> \t <voice>
"""
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


rows = []
for f in sorted(SCN.glob("*.psb.tjs")):
    base = f.name.split("ver")[0]
    s = f.read_text(encoding="utf-8", errors="replace")
    ev = []                                    # (pos, payload)

    # class / name / file with rolling context
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
            ev.append((pos, ("B", fname)))
        elif cls == "character":
            # the "name" here is the LAYER (ch_effect / ch_effect0..), not the
            # character — the character is the stand file's stem (芳乃.stand)
            ch = fname.split(".")[0] if "." in fname else fname
            ev.append((pos, ("C", ch, fname)))

    # dialogue blocks: a line that is just `"<sp>",` followed by a line
    # `void,` followed by `"<tx>",`  (object fields use `"k" => void,`)
    p = 0
    while True:
        i = s.find(VOID, p)
        if i < 0:
            break
        ls = s.rfind("\n", 0, i) + 1              # start of the void, line
        if s[ls:i].strip():                       # `void,` must be alone
            p = i + 5
            continue
        # previous non-empty line = sp
        pe = ls - 1
        ps = s.rfind("\n", 0, pe) + 1
        sp_line = s[ps:pe].strip()
        if not (sp_line.startswith('"') and sp_line.endswith('",')
                and "=>" not in sp_line):
            p = i + 5
            continue
        sp = sp_line[1:-2]
        # next line = tx
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
        if tx.strip():
            if voice:
                s8 = short_of(voice)          # FAT32 8.3 short name
                if s8:
                    voice = s8[:-4]           # engine appends ".wav"
            ev.append((i, ("S", sp, tx, voice)))
        p = i + 5

    ev.sort(key=lambda t: t[0])
    for _, payload in ev:
        rows.append((base,) + payload)

with OUT.open("w", encoding="utf-8") as fh:
    for r in rows:
        fh.write("\t".join(r) + "\n")
nb = sum(1 for r in rows if r[1] == "B")
nc = sum(1 for r in rows if r[1] == "C")
ns = sum(1 for r in rows if r[1] == "S")
nv = sum(1 for r in rows if r[1] == "S" and r[4])
print(f"{len(rows)} events: {nb} bg, {nc} sprite, {ns} say ({nv} voiced)")
