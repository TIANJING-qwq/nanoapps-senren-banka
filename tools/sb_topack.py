#!/usr/bin/env python3
"""Convert dialogue into per-chapter VNPK script.bin volumes.

Opcode set (engine-locked): 0 END, 1 LABEL u32, 2 BG str, 3 SPR u8 u8 str,
4 SPRCLR u8, 5 BGM str, 6 SAY str-name str-text, 7 CHOICE, 8 JUMP u32,
9 WAIT u16, 10 NEXT u16, 11 VOICE str.  Header: VNPK u32 ver u32 nlabels
u32 labels[nlabels].

Input priority: sb_tjs.tsv (base, speaker, text, voice — authoritative,
from the KrkrExtract .psb.tjs dump) over sb_dialogue.tsv (offsets only).

Also emits chsel.idx (VNCS): grouped route list 共通0/芳乃1/茉子2/丛雨3/
レナ4/小春・芦花5/后日谈6.
"""
import re
import struct
import sys
from pathlib import Path

tsv = Path(sys.argv[1])
outdir = Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)

OP_END, OP_LABEL, OP_BG, OP_SPR, OP_SPRCLR, OP_BGM, OP_SAY, OP_CHOICE, \
    OP_JUMP, OP_WAIT, OP_NEXT, OP_VOICE = range(12)

chapters = {}
order = []
bg_map = {}
bgmap_path = Path("NanoApps/build/bg_map.tsv")
if bgmap_path.exists():
    for ln in bgmap_path.read_text(encoding="utf-8").splitlines():
        if "\t" in ln:
            nm, bb = ln.split("\t", 1)
            bg_map[nm] = bb
spr_map = {}
sprmap_path = Path("NanoApps/build/spr_map.tsv")
if sprmap_path.exists():
    for ln in sprmap_path.read_text(encoding="utf-8").splitlines():
        if "\t" in ln:
            nm, sp = ln.split("\t", 1)
            spr_map[nm] = sp
print(f"bg_map: {len(bg_map)} entries; spr_map: {len(spr_map)} speakers")

def chapter_spr(ks):
    """chapter protagonist sprite: match speaker name inside chapter title"""
    for nm, sp in spr_map.items():
        if nm in ks:
            return sp
    return None


def bg_file_for(ci):
    """chapter bg: rotate through mapped names, skipping washed-out
    (mask/solid) images whose key maps to an all-dark/all-bright file"""
    if bg_map:
        keys = sorted(bg_map)
        for k in range(len(keys)):
            pick = bg_map[keys[(ci * 7 + k) % len(keys)]]
            stem = pick.replace("bb", "")
            n = int(stem) if stem.isdigit() else -1
            # skip known dark/bright masks (bb00 white, bb01/bb02 black)
            if n in (0, 1, 2):
                continue
            return pick
    return "bg_school"
chapters = {}          # base -> [(text, speaker, voice)]
order = []
bgm_of = {}
bgm_path = Path("NanoApps/build/sb_bgms.tsv")
if bgm_path.exists():
    for ln in bgm_path.read_text(encoding="utf-8").splitlines():
        if "\t" in ln:
            b, g = ln.split("\t", 1)
            bgm_of[b] = g
tjs_path = Path("NanoApps/build/sb_tjs.tsv")
if tjs_path.exists():
    for ln in tjs_path.read_text(encoding="utf-8").splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        base, sp, tx = parts[0], parts[1], parts[2]
        v = parts[3] if len(parts) > 3 and parts[3] else ""
        base = re.sub(r"\.ks(\.psb)?(\.tjs)?$", "", base)
        if base not in chapters:
            chapters[base] = []
            order.append(base)
        chapters[base].append((tx, sp, v))
    print(f"source: sb_tjs.tsv ({sum(len(v) for v in chapters.values())}"
          " lines with speakers+voice)")
else:
    for line in tsv.read_text(encoding="utf-8").splitlines():
        ks, off, text = line.split("\t", 2)
        ks = ks.rsplit("ver", 1)[0].rstrip("・").rstrip(".ks")
        if ks not in chapters:
            chapters[ks] = []
            order.append(ks)
        chapters[ks].append((text, "", ""))


NAMES = ("芳乃", "茉子", "蕾娜", "小春", "芦花", "将臣", "廉太郎", "ムラサメ",
         "丛雨", "朝武", "常陆", "神主", "心子", "レナ", "マキ", "雌蕊")


def speaker_of(text):
    for n in NAMES:
        if n + "「" in text or n + "：" in text:
            return n
    return ""


def s_str(b):
    return struct.pack("<H", len(b)) + b


def route_group(base, ci):
    """0 共通 / 1 芳乃 / 2 茉子 / 3 丛雨 / 4 レナ / 5 小春・芦花 / 6 后日谈.
    Chapter numbers: 0xx common, 1xx Yoshino, 2xx Makoto, 3xx Murasame,
    4xx Rena, 5xx Koharu&Roka; a title with 'after' marks an epilogue."""
    m = re.match(r"^(\d+)", base)
    no = int(m.group(1)) if m else ci
    if re.search(r"ａｆｔｅｒ|after", base, re.I):
        return 6
    if no < 100:
        return 0
    if no < 200:
        return 1
    if no < 300:
        return 2
    if no < 400:
        return 3
    if no < 500:
        return 4
    return 5


def build(ci, ks, lines, next_no):
    ops2 = bytearray()
    labels2 = []
    hdr_len = 12 + 4  # 1 label
    labels2.append(hdr_len)
    ops2 += bytes([OP_LABEL]) + struct.pack("<I", 0)
    ops2 += bytes([OP_BG]) + s_str(bg_file_for(ci).encode())
    bgm = bgm_of.get(ks.split("ver")[0])
    if bgm:
        ops2 += bytes([OP_BGM]) + s_str(bgm.encode())
    sp = chapter_spr(ks)
    if sp:
        ops2 += bytes([OP_SPR, 0, 1]) + s_str(sp.encode())
    prev_spk = None
    for text, nm, voice in lines:
        t = text.strip("「」")
        if not nm:
            nm = speaker_of(text)
        if nm and nm != prev_spk and nm in spr_map:
            ops2 += bytes([OP_SPR, 0, 1]) + s_str(spr_map[nm].encode())
            prev_spk = nm
        if voice:
            ops2 += bytes([OP_VOICE]) + s_str(voice.encode("ascii"))
        enc = t.encode("utf-8")
        if len(enc) > 60000:
            enc = enc[:60000]
        ops2 += bytes([OP_SAY]) + s_str(nm.encode("utf-8")) + s_str(enc)
    if next_no is not None:
        ops2 += bytes([OP_NEXT]) + struct.pack("<H", next_no)
    ops2 += bytes([OP_END])
    out = bytearray()
    out += b"VNPK" + struct.pack("<II", 1, 1)
    out += struct.pack("<I", labels2[0])
    out += ops2
    return bytes(out)


idx_lines = []
flows = []
chsels = []
for ci, ks in enumerate(order):
    next_no = ci + 1 if ci + 1 < len(order) else None
    blob = build(ci, ks, chapters[ks], next_no)
    safe = f"{ci:04d}"
    no = ci + 1
    if ci == 0:
        (outdir / "script.bin").write_bytes(blob)
    else:
        (outdir / "ch").mkdir(exist_ok=True)
        (outdir / f"ch/{ci:04d}.bin").write_bytes(blob)
    # chapter title: strip ver suffix and numeric prefix
    title = ks.rsplit("ver", 1)[0].rstrip("・").lstrip("0123456789")
    flows.append(f"{ci}\t{title}")
    chsels.append((route_group(ks, ci), ci, title))
    idx_lines.append(f"{ks}\t{safe}\t{len(chapters[ks])}\t{len(blob)}")

(outdir / "chapters.tsv").write_text("\n".join(idx_lines), encoding="utf-8")

# flow.idx: VNFL u16 ver(2=chapter mode) u16 n, then n x (u32 chapter, u16 len, utf-8 title)
fb = bytearray(b"VNFL") + struct.pack("<HH", 2, len(flows))
for row in flows:
    ci, title = row.split("\t")
    tb = title.encode("utf-8")
    fb += struct.pack("<IH", int(ci), len(tb)) + tb
(outdir / "flow.idx").write_bytes(fb)

# chsel.idx: VNCS u16 ver(1) u16 n, then n x (u8 group, u16 chapter,
# u16 nlen, name[]) — grouped chapter list for the 章节选择 screen
cb = bytearray(b"VNCS") + struct.pack("<HH", 1, len(chsels))
for grp, ci, title in chsels:
    tb = title.encode("utf-8")
    cb += struct.pack("<BHH", grp, ci, len(tb)) + tb
(outdir / "chsel.idx").write_bytes(cb)
groups = [g for g, _, _ in chsels]
print(f"{len(order)} chapters, flow.idx {len(fb)}B, chsel.idx {len(cb)}B "
      f"(groups: " + "/".join(str(groups.count(i)) for i in range(7)) + ")")
print("first 5:")
for l in idx_lines[:5]:
    print(" ", l)
