#!/usr/bin/env python3
"""Summarize the scenelist: unique chapter titles in order, with the
storage files each covers — the real route structure."""
import re
from pathlib import Path

SRC = Path(r"K:\千恋＊万花\outPath\data.xp3\scn\scenelist.psb.tjs")
body = SRC.read_text(encoding="utf-8")
body = body[body.index('"list"'):]
raw = re.split(r"\n    \(const\) %\[", body)
flow = []
for chunk in raw[1:]:
    st = re.search(r'"storage" => "(.*?)"', chunk)
    tg = re.search(r'"target" => "(.*?)"', chunk)
    ti = re.search(r'"title" => "(.*?)"', chunk)
    nsels = chunk.count('"text" =>')
    flow.append({"storage": st.group(1) if st else "", "target": tg.group(1) if tg else "",
                 "title": ti.group(1) if ti else "", "sels": nsels})

# group consecutive same-title entries
runs = []
for f in flow:
    if not f["title"]:
        continue
    if runs and runs[-1][0] == f["title"]:
        runs[-1][1].add(f["storage"].split("・")[0])
        runs[-1][2] += f["sels"]
    else:
        runs.append([f["title"], {f["storage"].split("・")[0]}, f["sels"]])
print(f"chapter runs in order: {len(runs)}")
for t, files, sels in runs:
    print(f"  {t:20s} files={','.join(sorted(files)):30s} sels={sels}")
