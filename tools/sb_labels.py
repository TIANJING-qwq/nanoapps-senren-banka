#!/usr/bin/env python3
"""Parse the per-file `scenes` array from a .psb.tjs dump: ordered labels
with their dialogue blocks (speaker/text/voice). Prints the segment list
so it can be compared against scenelist's actual execution order.

Usage: sb_labels.py <file.psb.tjs> [--json out.json]
"""
import json
import re
import sys
from pathlib import Path

# scene header: "firstLine" => N, "label" => "*name", "lines" => [...]
SCENE = re.compile(r'\n    \(const\) %\[\n(?:      "firstLine" => -?\d+,\n)?'
                   r'      "label" => "([^"]+)",\n      "lines" => \(const\) \[', )
BLOCK = re.compile(r'\[\s*\n?\s*"(?P<sp>[^"]*)",\s*\n?\s*void,\s*\n?\s*'
                   r'"(?P<tx>[^"]*)"')
VOICE = re.compile(r'"voice" => "([^"]+)"')


def parse(path: Path):
    s = path.read_text(encoding="utf-8", errors="replace")
    scenes = []
    starts = [(m.start(), m.group(1)) for m in SCENE.finditer(s)]
    for i, (pos, label) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(s)
        seg = s[pos:end]
        blocks = []
        for b in BLOCK.finditer(seg):
            tx = b.group("tx")
            if not tx.strip():
                continue
            rest = seg[b.end():b.end() + 700]
            vm = VOICE.search(rest)
            blocks.append((b.group("sp"), tx, vm.group(1) if vm else ""))
        scenes.append({"label": label, "blocks": blocks})
    return scenes


if __name__ == "__main__":
    scenes = parse(Path(sys.argv[1]))
    total = sum(len(sc["blocks"]) for sc in scenes)
    print(f"{len(scenes)} scenes, {total} blocks")
    for sc in scenes:
        first = sc["blocks"][0][1][:28] if sc["blocks"] else "(empty)"
        print(f'  {sc["label"]:28s} n={len(sc["blocks"]):4d}  {first}')
    if len(sys.argv) > 3 and sys.argv[2] == "--json":
        Path(sys.argv[3]).write_text(
            json.dumps(scenes, ensure_ascii=False, indent=1), encoding="utf-8")
