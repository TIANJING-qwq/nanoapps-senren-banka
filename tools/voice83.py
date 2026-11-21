#!/usr/bin/env python3
"""8.3 short-name scheme for voice files (FAT32 directory-entry limit:
25,878 LFN files exhausted the single-directory entry chain).

Mapping is DETERMINISTIC from the sorted prefix+suffix table extracted
from sb_tjs.tsv, so tools/sb_topack.py and the renamer always agree:

    <prefix><NNN>_<NNN>[_ref]  ->  <CODE><NNN><NNN>.WAV
    e.g.  yos010_008            ->  <code-of 'yos'>010 008 .WAV (8+3)

Subcommands:
  map tsv         rewrite a tjs-format tsv's voice column to short names
  rename srcdir   rename existing long-name .wav files in place
"""
import re
import sys
from pathlib import Path

TJS = Path("NanoApps/build/sb_tjs.tsv")

PAT = re.compile(r"^([a-z]+)(\d{3})_(\d{3})(_ref)?$")


def build_table():
    keys = set()
    for ln in TJS.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) >= 4 and p[3]:
            m = PAT.match(p[3])
            if m:
                keys.add((m.group(1), m.group(4) or ""))
    table = {}
    for i, k in enumerate(sorted(keys)):
        code = chr(65 + i // 26) + chr(65 + i % 26)
        table[k] = code
    return table


TABLE = build_table()


def short_of(voice: str) -> str:
    m = PAT.match(voice)
    if not m:
        return ""
    key = (m.group(1), m.group(4) or "")
    code = TABLE.get(key)
    if not code:
        return ""
    return f"{code}{m.group(2)}{m.group(3)}.WAV"


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "map":
        src, dst = Path(sys.argv[2]), Path(sys.argv[3])
        out, miss = [], 0
        for ln in src.read_text(encoding="utf-8").splitlines():
            p = ln.split("\t")
            if len(p) >= 4 and p[3]:
                s = short_of(p[3])
                if s:
                    p[3] = s[:-4]          # engine appends ".wav" itself
                else:
                    p[3] = ""
                    miss += 1
            out.append("\t".join(p))
        dst.write_text("\n".join(out), encoding="utf-8")
        print(f"mapped -> {dst} ({miss} unmapped dropped)")
    elif cmd == "rename":
        d = Path(sys.argv[2])
        n = err = 0
        for f in sorted(d.glob("*.wav")):
            m = PAT.match(f.stem)
            if not m:
                continue
            s = short_of(f.stem)
            if not s:
                err += 1
                continue
            tgt = f.with_name(s)
            if tgt.exists():
                continue
            f.rename(tgt)
            n += 1
        print(f"renamed {n} ({err} unmapped) in {d}")
