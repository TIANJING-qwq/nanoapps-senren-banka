#!/usr/bin/env python3
"""Align the flowchart's chapter numbers with the Mi Band script files.

Both pipelines reference the same CG numbers (ev101, ev701, ...), so each
chapter that shows a CG gives a hard anchor: old chapter i -> new file j when
the first CG matches. Chapters without a CG are interpolated between anchors.

Rewrites chart.idx in place, replacing every node's `chapter` field with the
script-file index the flowchart should jump to.
"""
import json
import re
import struct
import zipfile
from pathlib import Path

ZIP = Path(r"C:\Users\TIANJING\.dsh\attachments\v1\files\57\5726a9dcf9cbe9aaf66848e430eb94e2f08c0bc7a827ac6200b41e9806fe3bd4\千恋万花.zip")
CHART = Path("NanoApps/build/sb_full/chart.idx")
CHDIR = Path("NanoApps/build/sb_full/ch")


def cg_key(name):
    m = re.match(r"(?:ev|sd)(\d{3})", name or "")
    return m.group(1) if m else ""


def old_chapters():
    """chapter index -> first CG key (script.bin is chapter 0)"""
    out = {}
    sb = Path("NanoApps/build/sb_full/script.bin")
    if sb.exists():
        m = re.search(rb"(?:ev|sd)\d{3}", sb.read_bytes())
        out[0] = cg_key(m.group(0).decode()) if m else ""
    for f in sorted(CHDIR.glob("*.bin")):
        idx = int(f.stem)
        m = re.search(rb"(?:ev|sd)\d{3}", f.read_bytes())
        out[idx] = cg_key(m.group(0).decode()) if m else ""
    return out


def new_files():
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
        cg = next((cg_key(d[k].get("cg")) for k in ks if d[k].get("cg")), "")
        out.append(cg)
    return out


def main():
    oc = old_chapters()
    nf = new_files()
    print(f"old chapters={len(oc)} new files={len(nf)}")

    # anchors: unique CG key present once on each side
    from collections import Counter, defaultdict
    ocnt = Counter(v for v in oc.values() if v)
    ncnt = Counter(v for v in nf if v)
    cand = []
    for k, v in ocnt.items():
        if v == 1 and ncnt.get(k) == 1:
            i = next(a for a, b in oc.items() if b == k)
            j = nf.index(k)
            cand.append((i, j))
    # keep only a monotonically increasing subset (orders must agree)
    anchors = {}
    last = -1
    for i, j in sorted(cand):
        if j > last:
            anchors[i] = j
            last = j
    print(f"unique CG anchors: {len(anchors)}")

    # fill between anchors by linear interpolation
    amap = {}
    pts = sorted(anchors.items())
    for a, j in pts:
        amap[a] = j
    if pts:
        first_i, first_j = pts[0]
        for i in range(0, first_i):
            amap[i] = max(0, first_j - (first_i - i))
        last_i, last_j = pts[-1]
        n_old = max(oc) + 1
        for i in range(last_i + 1, n_old):
            span = max(1, n_old - 1 - last_i)
            amap[i] = min(len(nf) - 1,
                          last_j + round((i - last_i) * (len(nf) - 1 - last_j) / span))
    for i in range(len(oc)):
        amap.setdefault(i, 0)
    print("mapped chapters:", len(amap))

    b = bytearray(CHART.read_bytes())
    nr = struct.unpack_from("<HH", b, 4)[1]
    recs = [struct.unpack_from("<HHHHHH", b, 8 + i * 12) for i in range(nr)]
    total = max(r[2] + r[3] for r in recs)
    noff = 8 + nr * 12
    changed = 0
    for i in range(total):
        off = noff + i * 12
        old = struct.unpack_from("<H", b, off + 6)[0]
        new = amap.get(old, old)
        if new != old:
            struct.pack_into("<H", b, off + 6, new)
            changed += 1
    CHART.write_bytes(bytes(b))
    print(f"chart.idx rewritten: {changed}/{total} nodes remapped")
    print("sample map:", list(amap.items())[:8])


if __name__ == "__main__":
    main()
