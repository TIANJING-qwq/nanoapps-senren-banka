#!/usr/bin/env python3
"""Parse the KrkrExtract .ks.ks.txt scripts (speaker line + line-after
pattern) into a speaker table, aligned to sb_dialogue.tsv by
(file, text). Output: sb_speakers.tsv  file \t toffset \t speaker"""
import sys
from pathlib import Path

SCN = Path("K:/千恋＊万花/outPath/data.xp3/scn")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else
           "NanoApps/build/sb_speakers.tsv")

rows = []
n_txt = 0
for f in sorted(SCN.glob("*.ks.ks.txt")):
    base = f.name.split("ver")[0]           # 002・祟り神
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    speaker = ""
    for i, ln in enumerate(lines):
        t = ln.strip()
        if not t:
            continue
        if t.startswith("「"):
            n_txt += 1
            rows.append((base, t, speaker))
            speaker = ""                      # consume: next bare line re-speaks
        elif t.startswith("『"):
            n_txt += 1
            rows.append((base, t, speaker))
        else:
            # bare line: it is the speaker of the NEXT quoted line, but it
            # is ALSO a valid narration line if no quote follows.
            nxt = ""
            for j in range(i + 1, min(i + 3, len(lines))):
                u = lines[j].strip()
                if u:
                    nxt = u
                    break
            if nxt.startswith(("「", "『")):
                speaker = t
            else:
                n_txt += 1
                rows.append((base, t, ""))

with OUT.open("w", encoding="utf-8") as fh:
    for base, t, sp in rows:
        fh.write(f"{base}\t{sp}\t{t}\n")
print(f"{len(rows)} lines ({n_txt} quoted); wrote {OUT}")
