#!/usr/bin/env python3
"""Build each chapter's EXECUTION GRAPH from the game's own data:
  - scenelist.psb.tjs : ordered (storage,target) entries + per-choice options
  - sb_events.tsv     : dialogue/bg/sprite events attributed to scene labels

Output NanoApps/build/sb_flow.json:
  { base: [ {label, kind, events, choices, choice_idx, next} ] }
kind: "scene" | "choice" | "empty"
"""
import json
import re
from pathlib import Path

SCN = Path("K:/千恋＊万花/outPath/data.xp3/scn")
SCENELIST = SCN / "scenelist.psb.tjs"
EVENTS = Path("NanoApps/build/sb_events.tsv")
OUT = Path("NanoApps/build/sb_flow.json")


def parse_scenelist():
    """Indent-aware parser: entry fields live at 6 spaces, choice fields at
    8+ spaces, so a `"target" =>` at 6 spaces belongs to the entry while one
    nested deeper belongs to a choice option."""
    s = SCENELIST.read_text(encoding="utf-8", errors="replace")
    s = s[s.index('"list"'):]
    entries = []
    cur = None
    for line in s.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped == "(const) %[" and indent == 4:
            if cur:
                entries.append(cur)
            cur = {"storage": "", "target": "", "title": "", "choices": []}
            continue
        if cur is None:
            continue
        if stripped == "]," and indent <= 4:
            entries.append(cur)
            cur = None
            continue
        m = re.match(r'"(storage|target|title)" => "(.*?)"', stripped)
        if m:
            k, v = m.group(1), m.group(2)
            if indent <= 6:
                cur[k] = v
            else:                      # nested: choice option
                if k == "target":
                    cur["_last_target"] = v
            continue
        m = re.match(r'"text" => "(.*?)"', stripped)
        if m and indent >= 8:
            # option order is ... "target" then "text"
            if cur.get("_last_target"):
                cur["choices"].append([m.group(1), cur["_last_target"]])
                cur["_last_target"] = None
            continue
        if stripped == "(const) %[" and indent >= 6:
            cur["_last_text"] = None
    if cur:
        entries.append(cur)
    for e in entries:
        e.pop("_last_text", None); e.pop("_last_target", None)
    return entries


def main():
    entries = parse_scenelist()
    print(f"scenelist entries: {len(entries)}")

    ev = {}
    for ln in EVENTS.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) < 3 or not p[1]:
            continue
        ev.setdefault((p[0], p[1]), []).append(p[2:])
    print(f"event groups: {len(ev)}")

    flow = {}
    for e in entries:
        # chapter base exactly matches sb_events.tsv (name without the ver tail)
        base = re.sub(r"\.ks(\.psb)?(\.tjs)?$", "", e["storage"])
        base = re.sub(r"ver[\d.]*$", "", base)
        label = e["target"]
        if not label:
            continue
        blocks = ev.get((base, label), [])
        kind = "choice" if e["choices"] else ("scene" if blocks else "empty")
        flow.setdefault(base, []).append({
            "label": label,
            "kind": kind,
            "events": blocks,
            "choices": e["choices"],
        })

    total_ev = 0
    for base, segs in flow.items():
        by_label = {s["label"]: i for i, s in enumerate(segs)}
        branch = set()
        for s in segs:
            for _, t in s["choices"]:
                branch.add(t)

        def has_dialogue(seg):
            return any(e and e[0] == "S" for e in seg["events"])

        def meaningful(seg):
            return seg["kind"] == "choice" or has_dialogue(seg)

        for i, s in enumerate(segs):
            if s["kind"] == "choice":
                s["choice_idx"] = [[txt, by_label.get(t, -1)]
                                   for txt, t in s["choices"]]
            # next meaningful segment after this one
            j = i + 1
            while j < len(segs) and not meaningful(segs[j]):
                j += 1
            s["next"] = j if j < len(segs) else -1
            if s["label"] in branch:
                # branch ends: resume at the first segment after the branch
                # run that is not another branch (the merge point)
                k = i + 1
                while k < len(segs) and (segs[k]["label"] in branch
                                         or not meaningful(segs[k])):
                    k += 1
                s["next"] = k if k < len(segs) else -1
            total_ev += len(s["events"])

    OUT.write_text(json.dumps(flow, ensure_ascii=False), encoding="utf-8")
    nseg = sum(len(v) for v in flow.values())
    nch = sum(1 for v in flow.values() for s in v if s["kind"] == "choice")
    nsc = sum(1 for v in flow.values() for s in v if s["kind"] == "scene")
    print(f"{len(flow)} chapters, {nseg} segments ({nsc} with dialogue), "
          f"{nch} choice points, {total_ev} events -> {OUT}")


if __name__ == "__main__":
    main()
