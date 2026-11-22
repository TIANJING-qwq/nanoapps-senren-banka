#!/usr/bin/env python3
"""Compile the Mi Band script JSON into VNPK with REAL choice branching.

Label layout per chapter file:
    label 0            = line 0
    label 1..k         = every choice target line that falls inside this file
Bodies are emitted in label order; each body ends with OP_JUMP to the next
label so linear reading continues, and OP_CHOICE points at the label of the
chosen target (when the target lives in this file, otherwise the next label).
"""
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

ZIP = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"C:\Users\TIANJING\.dsh\attachments\v1\files\57\5726a9dcf9cbe9aaf66848e430eb94e2f08c0bc7a827ac6200b41e9806fe3bd4\千恋万花.zip")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "NanoApps/build/sb_mb2")
CHUNK = 500

END, LABEL, BG, SPR, SPRCLR, BGM, SAY, CHOICE, JUMP, WAIT, NEXT, VOICE, CG = range(13)


def s_str(b):
    return struct.pack("<H", len(b)) + b


def pack_chapter(bodies):
    n = len(bodies)
    hdr = 12 + 4 * n
    offs, cur = [], hdr
    for b in bodies:
        offs.append(cur)
        cur += len(b)
    out = bytearray(b"VNPK" + struct.pack("<II", 1, n))
    for o in offs:
        out += struct.pack("<I", o)
    for b in bodies:
        out += b
    return bytes(out)


def load_maps():
    bg = {}
    p = Path("NanoApps/build/bg_ascii.tsv")
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if "\t" in ln:
                k, v = ln.split("\t")
                bg[k] = v
    voice = {}
    q = Path("NanoApps/build/voice_map.tsv")
    if q.exists():
        for ln in q.read_text(encoding="utf-8").splitlines():
            z = ln.split("\t")
            if len(z) == 3:
                voice[(z[0], z[1])] = z[2]
    return bg, voice


def build(d, fidx):
    """d: {line_key: entry}; fidx: 0-based file index"""
    bg_map, voice_map = MAPS
    keys = sorted(d, key=lambda s: int(s))
    first_id = fidx * CHUNK + 1
    # line key -> index inside the file
    pos = {k: i for i, k in enumerate(keys)}

    # collect label anchor positions (file-relative line indices)
    anchors = {0}
    for k in keys:
        v = d[k]
        if not v.get("co"):
            continue
        for c in ("c1t", "c2t", "c3t", "c4t"):
            t = v.get(c)
            if isinstance(t, int):
                ln = t - first_id
                if 0 <= ln < len(keys):
                    anchors.add(ln)
    anchors = sorted(anchors)
    label_of_line = {ln: i for i, ln in enumerate(anchors)}

    def label_at_or_before(ln):
        best = 0
        for a in anchors:
            if a <= ln:
                best = label_of_line[a]
            else:
                break
        return best

    bodies = []
    for li, start in enumerate(anchors):
        nxt = anchors[li + 1] if li + 1 < len(anchors) else len(keys)
        body = bytearray()
        cur_bg = cur_spr = cur_cg = ""
        for i in range(start, nxt):
            k = keys[i]
            v = d[k]
            b = v.get("b") or ""
            if b and b != cur_bg:
                body += bytes([BG]) + s_str(bg_map.get(b, b).encode())
                cur_bg = b
            if v.get("cg"):
                nm = v["cg"].rsplit(".", 1)[0]
                if nm != cur_cg:
                    body += bytes([SPRCLR, 0xFF])
                    body += bytes([CG]) + s_str(nm.encode())
                    cur_cg, cur_spr = nm, ""
            if v.get("c"):
                nm = v["c"].strip()
                if nm != cur_spr:
                    z = int(v.get("z") or 0) & 1
                    body += bytes([SPR, 0, z]) + s_str(nm.encode())
                    cur_spr, cur_cg = nm, ""
            t = v.get("t")
            if t:
                sp = v.get("s") or ""
                vo = voice_map.get((str(fidx), k))
                if vo:
                    body += bytes([VOICE]) + s_str(vo.encode("ascii"))
                body += bytes([SAY]) + s_str(sp.encode()) + s_str(t.encode())
            elif v.get("co"):
                opts = []
                for n in range(1, 5):
                    txt = v.get("c%d" % n)
                    tgt = v.get("c%dt" % n)
                    if txt:
                        if isinstance(tgt, int):
                            ln = tgt - first_id
                            lab = label_at_or_before(ln) if 0 <= ln < len(keys) \
                                else (li + 1 if li + 1 < len(anchors) else 0)
                        else:
                            lab = li + 1 if li + 1 < len(anchors) else 0
                        opts.append((txt, lab))
                if opts:
                    body += bytes([CHOICE, len(opts)])
                    for txt, lab in opts:
                        body += struct.pack("<I", lab) + s_str(txt.encode())
        # continue to the following label, or stop at the end
        if li + 1 < len(anchors):
            body += bytes([JUMP]) + struct.pack("<I", li + 1)
        else:
            body += bytes([END])
        bodies.append(bytes(body))
    return pack_chapter(bodies)


def main():
    global MAPS
    MAPS = load_maps()
    z = zipfile.ZipFile(ZIP)

    def num(i):
        m = re.search(r"(\d+)\.txt$", i.filename)
        return int(m.group(1)) if m else 0

    files = sorted((i for i in z.infolist()
                    if "/script/" in i.filename and i.file_size), key=num)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ch").mkdir(exist_ok=True)
    tot_choice = 0
    for idx, i in enumerate(files):
        d = json.loads(z.read(i.filename).decode("utf-8", "replace"))
        tot_choice += sum(1 for v in d.values() if isinstance(v, dict) and v.get("co"))
        blob = build(d, idx)
        (OUT / "ch" / ("%04d.bin" % idx)).write_bytes(blob)
        if idx == 0:
            (OUT / "script.bin").write_bytes(blob)
    print("files=%d choices=%d -> %s" % (len(files), tot_choice, OUT))


if __name__ == "__main__":
    main()
