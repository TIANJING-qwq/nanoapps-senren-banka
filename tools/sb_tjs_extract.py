#!/usr/bin/env python3
"""Extract the authoritative (speaker, text, voice) stream from the
KrkrExtract .psb.tjs dumps: instruction blocks look like
  [ "name", void, "「text」", [ %["voice"=>... ] ], lineno, ... ]
Output: sb_tjs.tsv  chapterbase \t speaker \t text \t voice"""
import re
import sys
from pathlib import Path

SCN = Path("K:/千恋＊万花/outPath/data.xp3/scn")
OUT = Path("NanoApps/build/sb_tjs.tsv")

blk = re.compile(
    r'\[\s*\n?\s*"(?P<sp>[^"]*)",\s*\n?\s*void,\s*\n?\s*"(?P<tx>[^"]*)",\s*\n?'
    r'(?P<rest>\(const\) \[\s*\n\s*\(const\) %\[)?', re.M)
vc = re.compile(r'"voice" => "([^"]+)"')
bgmre = re.compile(r'"filename" => "(bgm\d+)"')

rows = []
bgms = {}
for f in sorted(SCN.glob("*.psb.tjs")):
    base = f.name.split("ver")[0]
    s = f.read_text(encoding="utf-8", errors="replace")
    bm = bgmre.search(s)
    if bm:
        bgms[base] = bm.group(1)
    pos = 0
    for m in blk.finditer(s):
        rest = s[m.end():m.end() + 700]
        vm = vc.search(rest)
        voice = vm.group(1) if vm else ""
        sp = m.group("sp")
        tx = m.group("tx")
        if not tx.strip():
            continue
        rows.append((base, sp, tx, voice))

with OUT.open("w", encoding="utf-8") as fh:
    for base, sp, tx, v in rows:
        fh.write(f"{base}\t{sp}\t{tx}\t{v}\n")
Path("NanoApps/build/sb_bgms.tsv").write_text(
    "\n".join(f"{b}\t{g}" for b, g in sorted(bgms.items())),
    encoding="utf-8")
nv = sum(1 for r in rows if r[3])
print(f"{len(rows)} lines, {nv} with voice, {len(bgms)} chapter bgms "
      f"-> {OUT}")
