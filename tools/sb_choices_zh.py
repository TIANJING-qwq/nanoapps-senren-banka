#!/usr/bin/env python3
"""Replace the Japanese choice labels in sb_flow.json with the official
Chinese ones from patch.xp3/scnchartdata.tjs.

Pairing rule: choices are matched per chapter (the `sNNN` tag) and in order.
When a chapter's choice-point count differs between the scenario list and the
chart data we leave it alone rather than risk showing the wrong option.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

FLOW = Path("NanoApps/build/sb_flow.json")
CHART = Path(r"K:\千恋＊万花\outPath\patch.xp3\scnchartdata.tjs")


def load_chart():
    s = CHART.read_text(encoding="utf-16", errors="replace")
    i, j = s.find('"items"'), s.find('"routes"')
    per = defaultdict(list)
    for it in re.split(r"\(const\) %\[", s[i:j])[1:]:
        if '"selects" => (const) [' not in it:
            continue
        m = re.search(r'"id" => "s(\d{3})\*', it)
        if not m:
            continue
        block = it[it.find('"selects"'):it.find('"selevals"')]
        picks = re.findall(r'^\s+"([^"]+)",?\s*$', block, re.M)
        if picks:
            per["s" + m.group(1)].append(picks)
    return per


def main():
    chart = load_chart()
    flow = json.loads(FLOW.read_text(encoding="utf-8"))
    replaced = skipped = 0
    for base, segs in flow.items():
        m = re.match(r"(\d{3})", base)
        if not m:
            continue
        tag = "s" + m.group(1)
        ours = [s for s in segs if s.get("kind") == "choice"]
        theirs = chart.get(tag, [])
        if not ours or len(ours) != len(theirs):
            if ours:
                skipped += len(ours)
            continue
        for seg, cn in zip(ours, theirs):
            cur = seg.get("choices") or []
            n = min(len(cur), len(cn))
            for k in range(n):
                old = cur[k][0]
                cur[k] = [cn[k], cur[k][1]]
                idx = seg.get("choice_idx") or []
                if k < len(idx):
                    idx[k] = [cn[k], idx[k][1]]
            replaced += n
    FLOW.write_text(json.dumps(flow, ensure_ascii=False), encoding="utf-8")
    print(f"choice labels -> Chinese: {replaced} replaced, "
          f"{skipped} left as-is (count mismatch), {len(chart)} chapters mapped")


if __name__ == "__main__":
    main()
