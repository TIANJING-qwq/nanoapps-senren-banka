#!/usr/bin/env python3
"""Parse scenelist.psb.tjs — the game's authoritative ordered scenario
flow (storage+label sequence, per-choice branches, chapter titles)."""
import re
from pathlib import Path

SRC = Path(r"K:\千恋＊万花\outPath\data.xp3\scn\scenelist.psb.tjs")
txt = SRC.read_text(encoding="utf-8")

# entries: top-level %[ ... ] blocks inside "list" => (const) [ ... ]
body = txt[txt.index('"list"'):]
entries = re.findall(r"\(const\) %\[.*?\n    \]", body, re.S)
print(f"top-level entries: {len(entries)}")

items, cur = [], None
for ln in body.splitlines():
    s = ln.strip()
    m = re.match(r'^"title" => "(.*?)"', s)
    if s.startswith("(const) %["):
        cur = {"storage": "", "target": "", "title": "", "sel": 0}
    elif cur is not None:
        m = re.match(r'^"storage" => "(.*?)"', s)
        if m: cur["storage"] = m.group(1)
        m = re.match(r'^"target" => "(.*?)"', s)
        if m: cur["target"] = m.group(1)
        m = re.match(r'^"title" => "(.*?)"', s)
        if m: cur["title"] = m.group(1)
        if s == "(const) [" and "selects" in body[:body.index(ln)].splitlines()[-3]:
            pass
    # entry boundary: a line with exactly '],' at 6-space indent closes an entry
    if s == "]," and cur is not None:
        pass

# simpler: split on the entry-header line
raw = re.split(r"\n    \(const\) %\[", body)
print(f"raw chunks: {len(raw)}")
flow = []
for chunk in raw[1:]:
    st = re.search(r'"storage" => "(.*?)"', chunk)
    tg = re.search(r'"target" => "(.*?)"', chunk)
    ti = re.search(r'"title" => "(.*?)"', chunk)
    nsels = chunk.count('"text" =>')
    flow.append({
        "storage": st.group(1) if st else "",
        "target": tg.group(1) if tg else "",
        "title": ti.group(1) if ti else "",
        "sels": nsels,
    })
print(f"parsed flow entries: {len(flow)}")
titled = [f for f in flow if f["title"]]
print(f"titled (real scenes): {len(titled)}")
selpoints = [f for f in flow if f["sels"]]
print(f"choice points: {len(selpoints)}")
print("--- first 12 titled ---")
for f in titled[:12]:
    print(f'  {f["title"]:16s} {f["storage"][:28]:30s} {f["target"]}')
print("--- titles histogram ---")
seen = []
for f in titled:
    if f["title"] not in seen:
        seen.append(f["title"])
print(f"unique titles in order: {len(seen)}")
print(seen[:40])
