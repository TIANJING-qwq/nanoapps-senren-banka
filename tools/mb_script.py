#!/usr/bin/env python3
"""Convert the Mi Band port's per-line script JSON into our VNPK format.

Each scriptData*.txt is {"<line>": {...}} with
    b  background name        c  sprite+expression (lh01_2)
    z  sprite position        cg event CG name
    s  speaker                t  dialogue text
    co/c1/c1t/c2/c2t  choice

We emit a linear VNPK body per file: BG / SPR / SPRCLR / CG / SAY, and keep
the header/label layout identical to sb_topack.py so the engine loads it.
Choices are emitted with both option texts and fall through to the next line
for now (v1); proper branch targets come later.
"""
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

ZIP = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"C:\Users\TIANJING\.dsh\attachments\v1\files\57\5726a9dcf9cbe9aaf66848e430eb94e2f08c0bc7a827ac6200b41e9806fe3bd4\千恋万花.zip")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "NanoApps/build/sb_mb")

# The iPod filesystem cannot open Japanese filenames, so backgrounds are
# shipped under ASCII aliases (g0001, g0002, ...) and translated here.
BG_MAP = {}
_bm = Path("NanoApps/build/bg_ascii.tsv")
if _bm.exists():
    for _ln in _bm.read_text(encoding="utf-8").splitlines():
        if "	" in _ln:
            _k, _v = _ln.split("	")
            BG_MAP[_k] = _v

END, LABEL, BG, SPR, SPRCLR, BGM, SAY, CHOICE, JUMP, WAIT, NEXT, VOICE, CG = \
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12


VOICE_MAP = {}
_vm = Path("NanoApps/build/voice_map.tsv")
if _vm.exists():
    for _ln in _vm.read_text(encoding="utf-8").splitlines():
        _q = _ln.split("	")
        if len(_q) == 3:
            VOICE_MAP[(_q[0], _q[1])] = _q[2]


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


def sprite_name(c):
    """'lh01_2' -> 'lh01_2' (our spr/ files are stored under the same name)"""
    return c.strip()


def build(lines, fidx=0):
    body = bytearray()
    # NOTE: no OP_LABEL here. A single-label chapter starts straight at its
    # first op (the engine treats OP_LABEL's u32 as a jump target, so emitting
    # one at offset 0 makes the script jump to END immediately).
    cur_bg = cur_spr = cur_cg = ""
    split_at = None
    for k in sorted(lines, key=lambda s: int(s)):
        v = lines[k]
        b = v.get("b") or ""
        if b and b != cur_bg:
            body += bytes([BG]) + s_str(BG_MAP.get(b, b).encode())
            cur_bg = b
        if v.get("cg"):
            nm = v["cg"].rsplit(".", 1)[0]
            if nm != cur_cg:
                body += bytes([SPRCLR, 0xFF])
                body += bytes([CG]) + s_str(nm.encode())
                cur_cg, cur_spr = nm, ""
        if v.get("c"):
            nm = sprite_name(v["c"])
            if nm != cur_spr:
                pos = int(v.get("z") or 1)
                body += bytes([SPR, 0, pos & 1]) + s_str(nm.encode())
                cur_spr = nm
                cur_cg = ""
        elif v.get("c") is None and v.get("t") and cur_spr:
            pass
        t = v.get("t")
        if t:
            sp = v.get("s") or ""
            vo = VOICE_MAP.get((str(fidx), k))
            if vo:
                body += bytes([VOICE]) + s_str(vo.encode("ascii"))
            body += bytes([SAY]) + s_str(sp.encode()) + s_str(t.encode())
        elif v.get("co"):
            opts = [v.get("c1") or "", v.get("c2") or ""]
            body += bytes([CHOICE, 2])
            for o in opts:
                body += struct.pack("<I", 1) + s_str(o.encode())
            if split_at is None:
                split_at = len(body)   # label 1 starts right after the choice
    body += bytes([END])
    return bytes(body), split_at


def main():
    z = zipfile.ZipFile(ZIP)
    def _num(i):
        m = re.search(r"(\d+)\.txt$", i.filename)
        return int(m.group(1)) if m else 0
    files = sorted((i for i in z.infolist()
                    if "/script/" in i.filename and i.file_size), key=_num)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ch").mkdir(exist_ok=True)
    total_say = total_bg = total_cg = total_spr = 0
    for idx, i in enumerate(files):
        try:
            d = json.loads(z.read(i.filename).decode("utf-8", "replace"))
        except Exception:
            continue
        body, split_at = build(d, idx)
        if split_at is not None:
            blob = pack_chapter([body[:split_at], body[split_at:]])
        else:
            blob = pack_chapter([body])
        for k, v in d.items():
            if v.get("t"):
                total_say += 1
            if v.get("b"):
                total_bg += 1
            if v.get("cg"):
                total_cg += 1
            if v.get("c"):
                total_spr += 1
        (OUT / "ch" / f"{idx:04d}.bin").write_bytes(blob)
        if idx == 0:
            (OUT / "script.bin").write_bytes(blob)
            print(f"chapter-1 script.bin {len(blob)} B")
    print(f"{len(files)} files -> {OUT}")
    print(f"lines: say={total_say} bg={total_bg} cg={total_cg} spr={total_spr}")


if __name__ == "__main__":
    main()
