#!/usr/bin/env python3
"""Build the flowchart asset (chart.idx, "VNCH") from the official chart data
in patch.xp3/scnchartdata.tjs.

Layout: the story spine runs downwards; branch alternatives are placed in
columns to the right of their parent, mirroring the in-game chart.

Record layout (little endian):
    "VNCH" u16 ver=1 u16 n_nodes u16 n_edges u16 n_routes
    nodes:   n_nodes * { i16 x, i16 y, u8 type, u8 route, u16 chapter,
                         u16 off, u16 len }        (12 bytes, off/len into blob)
    edges:   n_edges * { u16 from, u16 to }
    routes:  n_routes * { u16 off, u16 len }
    blob:    utf-8 titles then route names
"""
import re
import struct
import sys
from pathlib import Path

CHART = Path(r"K:\千恋＊万花\outPath\patch.xp3\scnchartdata.tjs")

NODE_W = 100
NODE_H = 18
COL_DX = 108
ROW_DY = 26


def parse():
    s = CHART.read_text(encoding="utf-16", errors="replace")

    def block(name, nxt):
        i, j = s.find(f'"{name}"'), s.find(f'"{nxt}"')
        return s[i:j]

    # captions: id -> [str, ...]
    caps = {}
    for m in re.finditer(r'"([^"]+)" => \(const\) \[\n(.*?)\n(\t+)\]',
                         block("captions", "chain"), re.S):
        caps[m.group(1)] = re.findall(r'"([^"]*)"', m.group(2))

    # chain: id -> str | [str,...]   (also "a:b" => ["select", n] keys)
    chain = {}
    chb = block("chain", "flagkeys")
    for m in re.finditer(r'"([^"]+)" => ("[^"]*"|\(const\) \[(.*?)\])',
                         chb, re.S):
        key = m.group(1)
        if m.group(2).startswith('"') and not m.group(3):
            chain[key] = [m.group(2).strip('"')]
        else:
            chain[key] = re.findall(r'"([^"]*)"', m.group(3) or "")

    # items: order matters
    items = []
    itb = block("items", "routes")
    for seg in re.split(r"\(const\) %\[", itb)[1:]:
        d = {}
        for k in ("id", "type", "tag", "comment", "name", "target"):
            m = re.search(rf'"{k}" => "([^"]*)"', seg)
            if m:
                d[k] = m.group(1)
        if '"selects" => (const) [' in seg:
            sub = seg[seg.find('"selects"'):seg.find('"selevals"')]
            d["selects"] = re.findall(r'^\s+"([^"]+)",?\s*$', sub, re.M)
        if "id" in d:
            items.append(d)

    routes = re.findall(r'^\t\t"([^"]+)"', block("routes", "selects"), re.M)
    return caps, chain, items, routes


def build():
    caps, chain, items, routes = parse()
    ids = [it["id"] for it in items]
    order = {k: i for i, k in enumerate(ids)}

    # node titles: chapter items carry "name"; others use the caption text
    def title_of(it):
        cap = caps.get(it["id"])
        if it.get("type") == "chapter" and it.get("name"):
            txt = it["name"]
            extra = [c for c in (cap or []) if c != txt]
            return (txt + " " + " ".join(extra)).strip()
        if cap:
            return cap[0]
        return it.get("comment") or it.get("id", "")

    # map scenario tag number (s001 ...) to OUR chapter index so a tap on a
    # node can jump straight into that chapter
    ch_idx = {}
    ts = Path("NanoApps/build/sb_full/chapters.tsv")
    if not ts.exists():
        ts = Path("NanoApps/build/chapters.tsv")
    if ts.exists():
        for n, ln in enumerate(ts.read_text(encoding="utf-8").splitlines()):
            m = re.match(r"(\d{3})", ln)
            if m:
                ch_idx.setdefault(m.group(1), n)

    def chapter_of(it):
        m = re.match(r"s(\d{3})", it.get("tag", "") or it["id"])
        return ch_idx.get(m.group(1), 0) if m else 0

    # ---- layout: depth-first along the chain, branches to the right -------
    pos = {}
    col_used = {}          # depth -> next free column
    root = ids[0] if ids else None
    seen = set()

    def walk(nid, col, depth):
        if nid in seen or nid not in order:
            return
        seen.add(nid)
        pos[nid] = (col, depth)
        kids = [k for k in chain.get(nid, []) if k in order]
        if not kids and nid in order:
            # fall back to "next item in file order" so nothing is orphaned
            nxt = ids[order[nid] + 1] if order[nid] + 1 < len(ids) else None
            kids = [nxt] if nxt else []
        if len(kids) == 1:
            walk(kids[0], col, depth + 1)
        else:
            for k, kid in enumerate(kids):
                walk(kid, col + k, depth + 1)

    if root:
        walk(root, 0, 0)
    # any node the chain never reached: append to the column at its file order
    for nid in ids:
        if nid not in pos:
            d = max((p[1] for p in pos.values()), default=0) + 1
            pos[nid] = (0, d)
            seen.add(nid)

    nodes = []
    idx_of = {}
    for it in items:
        nid = it["id"]
        if nid not in pos:
            continue
        col, depth = pos[nid]
        idx_of[nid] = len(nodes)
        nodes.append({
            "id": nid,
            "x": 4 + col * COL_DX,
            "y": 6 + depth * ROW_DY,
            "type": {"chapter": 0, "section": 1, "select": 2,
                     "branch": 3, "warp": 4}.get(it.get("type"), 1),
            "chapter": chapter_of(it),
            "title": title_of(it),
        })

    edges = []
    for nid, kids in chain.items():
        if nid not in idx_of:
            continue
        for k in kids:
            if k in idx_of:
                edges.append((idx_of[nid], idx_of[k]))

    # ---- serialise -------------------------------------------------------
    blob = bytearray()
    recs = bytearray()
    for n in nodes:
        if n["type"] == 0:                      # chapter header row
            n["title"] = n["title"][:40]
        t = n["title"].encode("utf-8")[:60]
        off = len(blob)
        blob += t
        recs += struct.pack("<hhBBHHH", n["x"], n["y"], n["type"], 0,
                            n["chapter"], off, len(t))
    rrec = bytearray()
    for r in routes:
        b = r.encode("utf-8")[:24]
        off = len(blob)
        blob += b
        rrec += struct.pack("<HH", off, len(b))
    erec = bytearray()
    for a, b in edges:
        erec += struct.pack("<HH", a, b)

    out = bytearray(b"VNCH")
    out += struct.pack("<HHHH", 1, len(nodes), len(edges), len(routes))
    out += recs + erec + rrec + blob
    return bytes(out), nodes, edges, routes


if __name__ == "__main__":
    dst = Path(sys.argv[1] if len(sys.argv) > 1
               else "NanoApps/build/sb_full/chart.idx")
    data, nodes, edges, routes = build()
    dst.write_bytes(data)
    print(f"chart.idx {len(data)} B: {len(nodes)} nodes, {len(edges)} edges, "
          f"{len(routes)} routes")
    print("  first nodes:", [(n["id"], n["x"], n["y"], n["title"][:12])
                             for n in nodes[:5]])
    print("  depth range:", max(n["y"] for n in nodes),
          "width range:", max(n["x"] for n in nodes))
