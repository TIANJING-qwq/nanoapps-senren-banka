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
OP_CG = 0x0C          # str name: full-screen event CG (cg/<name>.bin)

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
chapters = {}          # base -> [(text, speaker, voice)]   (fallback path)
events = {}            # base -> [("B",name) | ("C",char,file) | ("S",sp,tx,voice)]
order = []
bgm_of = {}
bgm_path = Path("NanoApps/build/sb_bgms.tsv")
if bgm_path.exists():
    for ln in bgm_path.read_text(encoding="utf-8").splitlines():
        if "\t" in ln:
            b, g = ln.split("\t", 1)
            bgm_of[b] = g

# real background name -> bbNN (from tools/sb_bgimport2.py)
bg_names = {}
bgn_path = Path("NanoApps/build/sb_full/bg_names.tsv")
if not bgn_path.exists():
    bgn_path = Path("NanoApps/build/bg_names.tsv")
if bgn_path.exists():
    for ln in bgn_path.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) == 2:
            bg_names[p[0]] = p[1]
    print(f"bg_names: {len(bg_names)} real background names")

# character name -> sprite asset (from tools/sb_sprimport2.py)
spr_of = {}
sprn_path = Path("NanoApps/build/sb_full/spr_names.tsv")
if not sprn_path.exists():
    sprn_path = Path("NanoApps/build/spr_names.tsv")
if sprn_path.exists():
    for ln in sprn_path.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) == 2:
            spr_of[p[0]] = p[1]
    print(f"spr_names: {len(spr_of)} characters")

# event CG assets: sd001aa -> cg07 (imported PNGs) and ev701aa -> ev701a
# (composed layered CGs), matched by their three-digit number.
cg_sd_of = {}
cg_ev_by_num = {}
for _n in ("cg_names.tsv", "cg_ev_names.tsv"):
    _p = Path("NanoApps/build/sb_full") / _n
    if not _p.exists():
        _p = Path("NanoApps/build") / _n
    if not _p.exists():
        continue
    for ln in _p.read_text(encoding="utf-8").splitlines():
        q = ln.split("\t")
        if len(q) != 2:
            continue
        if _n == "cg_names.tsv":
            cg_sd_of[q[0]] = q[1]
        else:
            m = re.match(r"ev(\d{3})", q[0])
            if m:
                cg_ev_by_num.setdefault(m.group(1), q[0])
print(f"cg assets: {len(cg_sd_of)} sd, {len(cg_ev_by_num)} ev chapters")


def cg_asset(name):
    """Map a scenario CG reference to the asset we ship.

    The scenario says e.g. "ev301aa" while the dump stores "ev301a"; a lookup
    that simply returned None for anything unmapped threw away most CGs, so
    fall back to the reference itself - the packer ships alias files under the
    exact referenced names."""
    cand = None
    if name.startswith("sd"):
        cand = cg_sd_of.get(name)
    elif name.startswith("ev"):
        m = re.match(r"ev(\d{3})", name)
        if m:
            cand = cg_ev_by_num.get(m.group(1))
    if cand:
        return cand
    # no mapping: use the name verbatim (alias files exist for these)
    if re.fullmatch(r"(?:ev|sd)\d{3}[a-z]*", name):
        return name
    return None

# Execution graph (scenelist order + choices + per-label events)
FLOW = {}
flow_path = Path("NanoApps/build/sb_flow.json")
if flow_path.exists():
    import json as _json
    FLOW = _json.load(open(flow_path, encoding="utf-8"))
    print(f"flow: {len(FLOW)} chapters, "
          f"{sum(len(v) for v in FLOW.values())} segments")

# PRIMARY source: the full event stream (bg + sprite + dialogue, true order)
ev_path = Path("NanoApps/build/sb_events.tsv")
EVENTS = ev_path.exists()
if EVENTS:
    for ln in ev_path.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) < 3:
            continue
        base = re.sub(r"\.ks(\.psb)?(\.tjs)?$", "", p[0])
        if base not in events:
            events[base] = []
            order.append(base)
        if p[2] == "B":
            events[base].append(("B", p[3]))
        elif p[2] == "C":
            events[base].append(("C", p[3], p[4] if len(p) > 4 else ""))
        elif p[2] == "E":
            events[base].append(("E", p[3]))
        elif p[2] == "S":
            events[base].append(("S", p[3], p[4] if len(p) > 4 else "",
                                 p[5] if len(p) > 5 else ""))
    print(f"source: sb_events.tsv ({len(events)} chapters, "
          f"{sum(len(v) for v in events.values())} events)")

tjs_path = Path("NanoApps/build/sb_tjs83.tsv")   # 8.3 short voice names
if not tjs_path.exists():
    tjs_path = Path("NanoApps/build/sb_tjs.tsv")
if not EVENTS:
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
    """0 共通 / 1 芳乃 / 2 茉子 / 3 丛雨 / 4 蕾娜 / 5 小春 / 6 芦花.
    Authoritative file->group from sb_scenemap.tsv (built from the game's
    own scenelist.psb.tjs); falls back to numeric prefix if absent."""
    g = SCENEMAP.get(stem_key(base), (None, None))[1]
    if g:
        return {"common": 0, "yoshino": 1, "mako": 2, "murasame": 3,
                "rena": 4, "koharu": 5, "roka": 6}[g]
    m = re.match(r"^(\d+)", base)
    no = int(m.group(1)) if m else ci
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


def stem_key(base):
    """Normalize a chapter base name to the scenemap key (e.g.
    '414レナ・イザナウver1.00' -> '414レナ', '508b・...' -> '508b')."""
    m = re.match(r"(\d+[ab]?)(レナ)?", base)
    if not m:
        return base.split("・")[0]
    return m.group(1) + (m.group(2) or "")


# scenemap: key -> (order, group, display title) from the game's own list
SCENEMAP = {}
sm_path = Path("NanoApps/build/sb_scenemap.tsv")
if sm_path.exists():
    for ln in sm_path.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) == 4:
            SCENEMAP[p[0]] = (int(p[1]), p[2], p[3])


def build_from_flow(ci, base, segs, next_no):
    """Compile a chapter's execution graph into a multi-label VNPK script.

    Each meaningful segment becomes one label. A choice segment emits
    OP_CHOICE with (label_id, option text) pairs; every other segment ends
    with OP_JUMP to its merge/next segment (or OP_NEXT / OP_END at the end).
    """
    # label ids: index into the meaningful-segment list
    seg_label = {}
    order = [i for i, sg in enumerate(segs)
             if sg["kind"] == "choice"
             # a segment matters if it says something OR shows an event CG:
             # CG-only segments have no dialogue and used to be dropped whole,
             # which is why almost every in-story CG went missing
             or any(e and e[0] in ("S", "E") for e in sg["events"])]
    for lid, i in enumerate(order):
        seg_label[i] = lid

    def next_label_of(i):
        j = segs[i]["next"]
        return seg_label.get(j, -1) if j >= 0 else -1

    bodies = []          # per label: op bytes
    for lid, i in enumerate(order):
        sg = segs[i]
        b = bytearray()
        cur_bg = ""
        pending = ""
        cur_spr = ""
        cur_cg = ""
        if sg["kind"] == "choice":
            opts = [(txt, seg_label.get(ti, -1))
                    for txt, ti in sg.get("choice_idx", [])
                    if seg_label.get(ti, -1) >= 0]
            if not opts:
                bodies.append(bytes([OP_END]))
                continue
            b += bytes([OP_CHOICE, len(opts)])
            for txt, tl in opts:
                tb = txt.encode("utf-8")[:200]
                b += struct.pack("<I", tl) + s_str(tb)
            bodies.append(bytes(b))
            continue
        hold_bg = False       # a CG must survive following bg events
        for e in sg["events"]:
            if e[0] == "B":
                if hold_bg:
                    continue
                bb = bg_names.get(e[1])
                if bb:
                    pending = bb
                continue
            if e[0] == "E":
                # event CG: full-screen art replaces the scene. Hide sprites
                # and drop bg/sprite tracking so the next B/C re-emits.
                asset = cg_asset(e[1])
                if asset and asset != cur_cg:
                    if pending and pending != cur_bg:
                        b += bytes([OP_BG]) + s_str(pending.encode())
                    b += bytes([OP_SPRCLR, 0xFF])
                    b += bytes([OP_CG]) + s_str(asset.encode())
                    cur_cg = asset
                    cur_spr = ""
                    cur_bg = ""
                    pending = ""
                    hold_bg = True
                continue
            if e[0] == "C":
                sp = spr_of.get(e[1]) or spr_of.get(e[1] + "a")
                if sp and sp != cur_spr:
                    if pending and pending != cur_bg:
                        b += bytes([OP_BG]) + s_str(pending.encode())
                        cur_bg = pending
                    b += bytes([OP_SPR, 0, 0]) + s_str(sp.encode())
                    cur_spr = sp
                continue
            if pending and pending != cur_bg:
                b += bytes([OP_BG]) + s_str(pending.encode())
                cur_bg = pending
            spname, tx, voice = e[1], e[2], e[3] if len(e) > 3 else ""
            t = tx.strip("「」")
            if voice:
                b += bytes([OP_VOICE]) + s_str(voice.encode("ascii"))
            enc = t.encode("utf-8")[:60000]
            b += bytes([OP_SAY]) + s_str(spname.encode("utf-8")) + s_str(enc)
        nl = next_label_of(i)
        if lid == len(order) - 1 and next_no is not None:
            b += bytes([OP_NEXT]) + struct.pack("<H", next_no)
        elif nl >= 0:
            b += bytes([OP_JUMP]) + struct.pack("<I", nl)
        b += bytes([OP_END])
        bodies.append(bytes(b))

    # assemble: header + label offset table + bodies
    n = len(bodies)
    hdr = 12 + 4 * n
    offs = []
    cur = hdr
    for b in bodies:
        offs.append(cur)
        cur += len(b)
    out = bytearray(b"VNPK" + struct.pack("<II", 1, n))
    for o in offs:
        out += struct.pack("<I", o)
    for b in bodies:
        out += b
    return bytes(out)


def build(ci, ks, lines, next_no):
    ops2 = bytearray()
    labels2 = []
    hdr_len = 12 + 4  # 1 label
    labels2.append(hdr_len)
    ops2 += bytes([OP_LABEL]) + struct.pack("<I", 0)
    if EVENTS:
        # full event stream: background changes + dialogue in true order.
        # BG events fire many times per line (effect layers redraw the same
        # stage); only the LAST bg set before a dialogue line matters, so
        # keep a pending bg and emit it lazily at the next SAY.
        bgm = bgm_of.get(ks.split("ver")[0])
        if bgm:
            ops2 += bytes([OP_BGM]) + s_str(bgm.encode())
        cur_bg = ""
        pending = ""
        cur_spr = ""
        for e in lines:
            if e[0] == "B":
                bb = bg_names.get(e[1])
                if bb:
                    if pending and pending != bb:
                        cur_spr = ""      # new scene: drop the old sprite
                    pending = bb
                continue
            if e[0] == "C":
                # character sprite change: speakername -> spr asset
                sp = spr_of.get(e[1]) or spr_of.get(e[1] + "a")
                if sp and sp != cur_spr:
                    if pending and pending != cur_bg:
                        ops2 += bytes([OP_BG]) + s_str(pending.encode())
                        cur_bg = pending
                    ops2 += bytes([OP_SPR, 0, 0]) + s_str(sp.encode())
                    cur_spr = sp
                continue
            if pending and pending != cur_bg:
                ops2 += bytes([OP_BG]) + s_str(pending.encode())
                cur_bg = pending
            sp, tx, voice = e[1], e[2], e[3]
            t = tx.strip("「」")
            if voice:
                ops2 += bytes([OP_VOICE]) + s_str(voice.encode("ascii"))
            enc = t.encode("utf-8")
            if len(enc) > 60000:
                enc = enc[:60000]
            ops2 += bytes([OP_SAY]) + s_str(sp.encode("utf-8")) + s_str(enc)
    else:
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
# order chapters by the game's own scenelist sequence (first appearance),
# falling back to name sort for anything the scenelist doesn't cover
order.sort(key=lambda b: (SCENEMAP.get(stem_key(b), (9999,))[0], b))
for ci, ks in enumerate(order):
    g_cur = route_group(ks, ci)
    g_next = route_group(order[ci + 1], ci + 1) if ci + 1 < len(order) else -1
    next_no = ci + 1 if ci + 1 < len(order) and g_cur == g_next else None
    src = events[ks] if EVENTS else chapters[ks]
    if FLOW and ks in FLOW:
        blob = build_from_flow(ci, ks, FLOW[ks], next_no)
    else:
        blob = build(ci, ks, src, next_no)
    safe = f"{ci:04d}"
    nsay = sum(1 for e in src if e[0] == "S") if EVENTS else len(src)
    if ci == 0:
        (outdir / "script.bin").write_bytes(blob)
    else:
        (outdir / "ch").mkdir(exist_ok=True)
        (outdir / f"ch/{ci:04d}.bin").write_bytes(blob)
    # title: original chapter number + name from the scenelist
    sm = SCENEMAP.get(stem_key(ks))
    if sm and sm[2]:
        title = sm[2]
    else:
        title = ks.rsplit("ver", 1)[0].rstrip("・").lstrip("0123456789")
    flows.append(f"{ci}\t{title}")
    chsels.append((g_cur, ci, title))
    idx_lines.append(f"{ks}\t{safe}\t{nsay}\t{len(blob)}")

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
