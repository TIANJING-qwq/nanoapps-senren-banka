#!/usr/bin/env python3
"""Build chart.idx ("VNCH" v2): the flowchart split into route tabs, laid out
separately per route so each tab is a compact, scrollable tree.

Routes come from chsel.idx (group per chapter), matching the in-game tabs:
    0 共通  1 芳乃  2 茉子  3 丛雨  4 蕾娜  5 小春  6 芦花

File layout (little endian):
    "VNCH" u16 ver=2 u16 n_routes
    routes: n_routes * { u16 name_off, u16 name_len, u16 node_base,
                         u16 node_count, u16 edge_base, u16 edge_count }
    nodes:  all_node_count * { i16 x, i16 y, u8 type, u8 route, u16 chapter,
                               u16 off, u16 len }
    edges:  all_edge_count * { u16 from, u16 to }      (global node indices)
    blob:   utf-8 titles, then route names
"""
import re
import struct
import sys
from pathlib import Path

CHART = Path(r"K:\千恋＊万花\outPath\patch.xp3\scnchartdata.tjs")

NODE_W = 140          # keep in sync with vn.c
NODE_W_CH = 260
COL_DX = 148
ROW_DY = 24

ROUTE_NAMES = ["共通", "芳乃", "茉子", "丛雨", "蕾娜", "小春", "芦花"]


def block(s, name, nxt):
    i, j = s.find(f'"{name}"'), s.find(f'"{nxt}"')
    return s[i:j]


def parse_chart():
    s = CHART.read_text(encoding="utf-16", errors="replace")
    caps = {}
    for m in re.finditer(r'"([^"]+)" => \(const\) \[\n(.*?)\n(\t|\s+)\]',
                         block(s, "captions", "chain"), re.S):
        caps[m.group(1)] = re.findall(r'"([^"]*)"', m.group(2))

    chain = {}
    for m in re.finditer(r'"([^"]+)" => ("[^"]*"|\(const\) \[(.*?)\])',
                         block(s, "chain", "flagkeys"), re.S):
        key = m.group(1)
        if m.group(3) is None:
            chain[key] = [m.group(2).strip('"')]
        else:
            chain[key] = re.findall(r'"([^"]*)"', m.group(3))

    items = []
    for seg in re.split(r"\(const\) %\[", block(s, "items", "routes"))[1:]:
        d = {}
        for k in ("id", "type", "tag", "comment", "name"):
            m = re.search(rf'"{k}" => "([^"]*)"', seg)
            if m:
                d[k] = m.group(1)
        if '"selects" => (const) [' in seg:
            sub = seg[seg.find('"selects"'):seg.find('"selevals"')]
            d["selects"] = re.findall(r'^\s+"([^"]+)",?\s*$', sub, re.M)
        if "id" in d:
            items.append(d)
    return caps, chain, items


def chapter_table():
    """chapter index -> (scenario tag digits, route group)"""
    tags, groups = {}, {}
    ts = Path("NanoApps/build/sb_full/chapters.tsv")
    if not ts.exists():
        ts = Path("NanoApps/build/chapters.tsv")
    if ts.exists():
        for n, ln in enumerate(ts.read_text(encoding="utf-8").splitlines()):
            m = re.match(r"(\d{3})", ln)
            if m:
                tags.setdefault(m.group(1), n)
    cs = Path("NanoApps/build/sb_full/chsel.idx")
    if not cs.exists():
        cs = Path("NanoApps/build/chsel.idx")
    if cs.exists():
        b = cs.read_bytes()
        if b[:4] == b"VNCS":
            n = b[6] | (b[7] << 8)
            off = 8
            for _ in range(n):
                g = b[off]
                ch = b[off + 1] | (b[off + 2] << 8)
                ln = b[off + 3] | (b[off + 4] << 8)
                groups[ch] = g
                off += 5 + ln
    return tags, groups


def build():
    caps, chain, items = parse_chart()
    tags, groups = chapter_table()

    def chapter_of(it):
        m = re.match(r"s(\d{3})", it.get("tag", "") or it["id"])
        return tags.get(m.group(1), 0) if m else 0

    def title_of(it):
        t = it.get("type")
        if t == "chapter":
            txt = it.get("name") or (caps.get(it["id"]) or [""])[0]
            extra = [c for c in (caps.get(it["id"]) or []) if c != txt]
            return (txt + " " + " ".join(extra)).strip()
        if t == "select" and it.get("comment"):
            return it["comment"]
        cap = caps.get(it["id"])
        if cap:
            c = cap[0]
            if len(c) > 22:
                c = c[:20] + "…"
            return c
        return it.get("comment") or it["id"]

    ids = [it["id"] for it in items]
    order = {k: i for i, k in enumerate(ids)}

    per_route = {g: [] for g in range(len(ROUTE_NAMES))}
    for it in items:
        ch = chapter_of(it)
        g = groups.get(ch, 0)
        if g >= len(ROUTE_NAMES):
            g = 0
        per_route[g].append(it)

    nodes, edges, routes = [], [], []
    for g in sorted(per_route):
        its = per_route[g]
        if not its:
            continue
        local = {it["id"] for it in its}
        pos, seen = {}, set()

        def walk(nid, col, depth):
            if nid in seen or nid not in local:
                return
            seen.add(nid)
            pos[nid] = (col, depth)
            kids = [k for k in chain.get(nid, []) if k in local and k not in seen]
            if not kids:
                i = order.get(nid)
                nxt = ids[i + 1] if i is not None and i + 1 < len(ids) else None
                kids = [nxt] if nxt in local and nxt not in seen else []
            if len(kids) <= 1:
                if kids:
                    walk(kids[0], col, depth + 1)
            else:
                for k, kid in enumerate(kids[:3]):
                    walk(kid, col + k, depth + 1)

        walk(its[0]["id"], 0, 0)
        for it in its:
            if it["id"] not in pos:
                d = max((p[1] for p in pos.values()), default=-1) + 1
                pos[it["id"]] = (0, d)

        node_base = len(nodes)
        base_idx = {}
        for it in its:
            col, depth = pos[it["id"]]
            t = {"chapter": 0, "section": 1, "select": 2, "branch": 3,
                 "warp": 4}.get(it.get("type"), 1)
            base_idx[it["id"]] = len(nodes)
            nodes.append({
                "x": 4 + col * COL_DX, "y": 4 + depth * ROW_DY,
                "type": t, "route": g, "chapter": chapter_of(it),
                "title": title_of(it),
            })
        edge_base = len(edges)
        for it in its:
            for k in chain.get(it["id"], []):
                if k in base_idx:
                    edges.append((base_idx[it["id"]], base_idx[k]))
        routes.append({"name": ROUTE_NAMES[g], "node_base": node_base,
                       "node_count": len(nodes) - node_base,
                       "edge_base": edge_base,
                       "edge_count": len(edges) - edge_base})

    blob = bytearray()
    recs = bytearray()
    for n in nodes:
        t = n["title"].encode("utf-8")
        off = len(blob)
        blob += t
        recs += struct.pack("<hhBBHHH", n["x"], n["y"], n["type"], n["route"],
                            n["chapter"], off, len(t))
    erec = b"".join(struct.pack("<HH", a, b) for a, b in edges)
    rrec = bytearray()
    for r in routes:
        nb = r["name"].encode("utf-8")
        off = len(blob)
        blob += nb
        rrec += struct.pack("<HHHHHH", off, len(nb), r["node_base"],
                            r["node_count"], r["edge_base"], r["edge_count"])
    out = bytearray(b"VNCH")
    out += struct.pack("<HH", 2, len(routes))
    out += rrec + recs + erec + blob
    return bytes(out), routes, nodes


if __name__ == "__main__":
    dst = Path(sys.argv[1] if len(sys.argv) > 1
               else "NanoApps/build/sb_full/chart.idx")
    data, routes, nodes = build()
    dst.write_bytes(data)
    print(f"chart.idx {len(data)} B, {len(nodes)} nodes")
    for r in routes:
        print(f"  {r['name']:4s} nodes={r['node_count']:3d} "
              f"edges={r['edge_count']:3d}")
