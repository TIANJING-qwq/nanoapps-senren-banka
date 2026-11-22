#!/usr/bin/env python3
"""Backfill voice names into the Mi Band script, aligning PER CHARACTER.

The two translations word lines differently, but the Nth line spoken by a
character in the old script usually lines up with the Nth line that same
character speaks in the new one. A clip is only attached when the character
matches, so audio never lands on the wrong person.

Output: NanoApps/build/voice_map.tsv   <file_index> TAB <line_key> TAB <voice>
"""
import collections
import json
import re
import zipfile
from pathlib import Path

ZIP = Path(r"C:\Users\TIANJING\.dsh\attachments\v1\files\57\5726a9dcf9cbe9aaf66848e430eb94e2f08c0bc7a827ac6200b41e9806fe3bd4\千恋万花.zip")
EV = Path("NanoApps/build/sb_events.tsv")
OUT = Path("NanoApps/build/voice_map.tsv")


def norm(s):
    return re.sub("[\u3010\u3011\\[\\]\u300c\u300d\u300e\u300f\\s\u30fb]", "", s or "")


BLOCK = {"司机", "先生", "女性", "男性", "路人", "乘客", "店员", "学生", "巫女"}


def old_per_char():
    per = collections.defaultdict(list)
    for ln in EV.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) < 4 or p[2] != "S":
            continue
        sp = norm(p[3])
        if not sp or sp in BLOCK:
            continue
        per[sp].append(p[5] if len(p) > 5 else "")
    return per


def new_sequences():
    z = zipfile.ZipFile(ZIP)

    def num(i):
        m = re.search(r"(\d+)\.txt$", i.filename)
        return int(m.group(1)) if m else 0

    files = sorted((i for i in z.infolist()
                    if "/script/" in i.filename and i.file_size), key=num)
    out = []
    for idx, i in enumerate(files):
        d = json.loads(z.read(i.filename).decode("utf-8", "replace"))
        ks = sorted(d, key=lambda s: int(s))
        out.append([(k, norm(d[k].get("s")))
                    for k in ks
                    if d[k].get("t") and norm(d[k].get("s"))])
    return out


def main():
    per = old_per_char()
    new = new_sequences()
    total = sum(len(v) for v in new)
    print("characters=%d new speaker lines=%d" % (len(per), total))

    rows = []
    hits = 0
    for k, nseq in enumerate(new):
        seen = collections.Counter()
        for key, sp in nseq:
            i = seen[sp]
            seen[sp] += 1
            arr = per.get(sp)
            if arr and i < len(arr) and arr[i]:
                rows.append(str(k) + "\t" + key + "\t" + arr[i])
                hits += 1
    OUT.write_text("\n".join(rows), encoding="utf-8")
    print("voice hits: %d / %d (%.1f%%)" % (hits, total, 100.0 * hits / max(1, total)))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
