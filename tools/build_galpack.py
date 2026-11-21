#!/usr/bin/env python3
"""build_galpack.py — host-side GalPack builder for the NanoApps vn player.

The on-device half is apps/vn/vn.c (RAW_SURFACE app). This tool converts a
Windows galgame into the compact formats it plays from /Data/vn/ on the
iPod disk. Nothing here touches the device: build a pack, copy it over.

Two modes:

  demo — synthesize a tiny test pack (no game files needed), so the whole
         pipeline (font/image/script/audio formats + the engine) can be
         verified on hardware in minutes:

    python tools/build_galpack.py demo build/galpack-demo

  kirikiri — convert a game directory that was ALREADY unpacked from its
         XP3 archive with GARbro / arc_conv (accept the "extract all"
         output: .ks scripts plus .png/.jpg/.bmp images, .ogg/.mp3 audio):

    python tools/build_galpack.py kirikiri "C:/Games/SomeGal_extracted" \
        build/galpack --entry first.ks --config my_map.json

         Tag handling is driven by a JSON mapping config because every
         KiriKiri game names its scene macros differently (see
         tools/galpack.example.json and the README).

Options:
  --font PATH    CJK-capable TTF/TTC for the bitmap font (default: search
                 common system font locations)
  --size N       glyph pixel size for the font (default 16; 20/24 for a
                 chunkier look — the engine reads the size from font.bin)
  --entry FILE   first scenario file to execute (default: first.ks, else
                 the alphabetically first .ks)
  --config PATH  JSON tag-mapping overrides
  --ffmpeg PATH  ffmpeg binary for audio conversion (default: search PATH;
                 without it BGM is skipped with a warning)

Outputs (copy the CONTENTS of the out dir into /Data/vn/ on the iPod):
  script.bin, font.bin, bg/*.bin, spr/*.bin, bgm/*.wav, ui/title.bin,
  cg.idx + cg/*.bin + cgt/*.bin (CG gallery), flow.idx (flowchart),
  pack-info.txt

Limits enforced to match the engine (see apps/vn/vn.c caps):
  script <= 384 KiB, font <= 3400 glyphs <= 24 px, bg 432x240 landscape,
  sprites <= 160x220, CG thumbnails 84x48, names <= 63 bytes,
  one line <= ~740 bytes.
Long lines are auto-split into consecutive SAY ops at char boundaries.

The iPod is held LANDSCAPE (rotated 90° CCW, home button right): all
coordinates below assume the 432x240 logical screen.

Copyright-minded: the engine and this tool are the deliverables; convert
only games you own, and do not distribute the converted packs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:
    print("Pillow is required:  python -m pip install Pillow", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]

SCR_W, SCR_H = 432, 240          # landscape: device held rotated 90° CCW
SPR_W, SPR_H = 160, 220
THUMB_W, THUMB_H = 84, 48
CG_MAX, FLOW_MAX = 512, 256
SCRIPT_MAX = 384 * 1024
GLYPH_MAX = 3400
GLYPH_SIZE_MAX = 24
NAME_MAX = 63
TEXT_MAX = 740            # bytes of UTF-8 per SAY (auto-split above this)

FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]

OP_END, OP_LABEL, OP_BG, OP_SPR, OP_SPRCLR = 0x00, 0x01, 0x02, 0x03, 0x04
OP_BGM, OP_SAY, OP_CHOICE, OP_JUMP, OP_WAIT = 0x05, 0x06, 0x07, 0x08, 0x09
POS = {"left": 0, "center": 1, "right": 2}


def die(msg: str) -> None:
    print(f"build_galpack: error: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"build_galpack: warning: {msg}", file=sys.stderr)


# --------------------------------------------------------------- font -------

def find_font(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        die(f"--font not found: {explicit}")
    for c in FONT_CANDIDATES:
        if Path(c).is_file():
            return Path(c)
    die("no CJK font found — pass --font /path/to/font.ttf "
        "(e.g. C:\\Windows\\Fonts\\msyh.ttc)")


def build_font(chars: set[str], size: int, font_path: Path) -> bytes:
    if not (8 <= size <= GLYPH_SIZE_MAX):
        die(f"--size must be 8..{GLYPH_SIZE_MAX}")
    chars = {c for c in chars if ord(c) >= 0x20} - {"\n"}
    cps = sorted(ord(c) for c in chars)
    if len(cps) > GLYPH_MAX:
        die(f"script uses {len(cps)} unique glyphs > engine cap {GLYPH_MAX}; "
            "split the game into chapter packs")
    font = ImageFont.truetype(str(font_path), size)
    bpr = (size + 7) // 8
    out = bytearray()
    out += b"VNFN"
    out += bytes([size, size, 1, 0])
    out += struct.pack("<H", len(cps))
    for cp in cps:
        ch = chr(cp)
        img = Image.new("L", (size, size), 0)
        ImageDraw.Draw(img).text((0, 0), ch, font=font, fill=255)
        bb = img.getbbox()
        if bb:  # re-center the ink in the cell
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            img = Image.new("L", (size, size), 0)
            ImageDraw.Draw(img).text(
                ((size - w) // 2 - bb[0], (size - h) // 2 - bb[1]), ch,
                font=font, fill=255)
        out += struct.pack("<I", cp)
        bits = bytearray(size * bpr)
        px = img.load()
        for y in range(size):
            for x in range(size):
                if px[x, y] >= 64:
                    bits[y * bpr + (x >> 3)] |= 0x80 >> (x & 7)
        out += bits
    return bytes(out)


# -------------------------------------------------------------- images ------

def rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def pack_bg(img: Image.Image) -> bytes:
    img = img.convert("RGB")
    s = max(SCR_W / img.width, SCR_H / img.height)
    img = img.resize((max(1, round(img.width * s)),
                      max(1, round(img.height * s))), Image.LANCZOS)
    x = (img.width - SCR_W) // 2
    y = (img.height - SCR_H) // 2
    img = img.crop((x, y, x + SCR_W, y + SCR_H))
    px = img.load()
    out = bytearray(b"VNBI" + struct.pack("<HHB", SCR_W, SCR_H, 0))
    for j in range(SCR_H):
        for i in range(SCR_W):
            r, g, b = px[i, j]
            out += struct.pack("<H", rgb565(r, g, b))
    return bytes(out)


def pack_spr(img: Image.Image) -> bytes:
    img = img.convert("RGBA")
    s = min(SPR_W / img.width, SPR_H / img.height, 1.0)
    if s < 1.0:
        img = img.resize((max(1, round(img.width * s)),
                          max(1, round(img.height * s))), Image.LANCZOS)
    w, h = img.size
    px = img.load()
    color = bytearray()
    alpha = bytearray()
    for j in range(h):
        for i in range(w):
            r, g, b, a = px[i, j]
            color += struct.pack("<H", rgb565(r, g, b))
            alpha.append(a)
    return b"VNBI" + struct.pack("<HHB", w, h, 1) + bytes(color) + bytes(alpha)


def pack_thumb(img: Image.Image) -> bytes:
    """84x48 RGB565 gallery thumbnail (VNBI fmt 0), same cover-crop as bg."""
    img = img.convert("RGB")
    s = max(THUMB_W / img.width, THUMB_H / img.height)
    img = img.resize((max(1, round(img.width * s)),
                      max(1, round(img.height * s))), Image.LANCZOS)
    x = (img.width - THUMB_W) // 2
    y = (img.height - THUMB_H) // 2
    img = img.crop((x, y, x + THUMB_W, y + THUMB_H))
    px = img.load()
    out = bytearray(b"VNBI" + struct.pack("<HHB", THUMB_W, THUMB_H, 0))
    for j in range(THUMB_H):
        for i in range(THUMB_W):
            r, g, b = px[i, j]
            out += struct.pack("<H", rgb565(r, g, b))
    return bytes(out)


# ---------------------------------------------------- manifests (cg / flow) --

def write_cgidx(out: Path, names: list[str]) -> bytes:
    """cg.idx: 'VNCG' u16 ver u16 n, then per entry u16 nlen + utf-8 name."""
    blob = bytearray(b"VNCG" + struct.pack("<HH", 1, len(names)))
    for n in names:
        b = n.encode("utf-8")
        blob += struct.pack("<H", len(b)) + b
    (out / "cg.idx").write_bytes(bytes(blob))
    return bytes(blob)


def write_flowidx(out: Path, entries: list[tuple[int, str]]) -> bytes:
    """flow.idx: 'VNFL' u16 ver u16 n, then u32 label_id + u16 tlen + title."""
    blob = bytearray(b"VNFL" + struct.pack("<HH", 1, len(entries)))
    for label_id, title in entries:
        b = title.encode("utf-8")
        blob += struct.pack("<IH", label_id, len(b)) + b
    (out / "flow.idx").write_bytes(bytes(blob))
    return bytes(blob)


def label_ids(c: Compiler) -> dict[str, int]:
    """Dense label ids exactly as Compiler.emit assigns them."""
    return {k: i for i, k in enumerate(
        sorted(c.labels, key=lambda k: c.labels[k]))}


# --------------------------------------------------------------- audio ------

def convert_wav(src: Path, dst: Path, ffmpeg: str | None) -> bool:
    if not ffmpeg:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0


def synth_demo_wav(dst: Path, seconds: float = 3.0, freq: float = 523.25) -> None:
    """A soft sine loop so demo packs exercise the audio path."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    rate = 16000
    n = int(rate * seconds)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            env = 0.5 * (1 - math.cos(2 * math.pi * i / n))     # loop click-free
            v = int(9000 * env * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


# ------------------------------------------------------------- compiler -----

TAG_RE = re.compile(r"\[(/?)([A-Za-z_][\w]*)([^\]]*)\]")
ATTR_RE = re.compile(r'([\w]+)\s*=\s*"([^"]*)"')

DEFAULT_CONFIG = {
    "bg_tags": ["bg", "background", "back", "bcross", "wcross"],
    "fg_tags": ["fg", "fgimage", "chara", "character", "stand", "sp"],
    "bgm_tags": ["playbgm", "bgm", "music"],
    "end_tags": ["s"],
    "choice_tag": "gal_choice",
    "name_patterns": ["^【(.+?)】"],
    "default_sprite_pos": "center",
    "image_layer0_is_bg": True,
}


def read_text_ks(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp932", errors="replace")


def parse_attrs(body: str) -> dict[str, str]:
    return dict(ATTR_RE.findall(body))


class Compiler:
    """Two-pass .ks -> script.bin compiler (opcodes match apps/vn/vn.c)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.labels: dict[str, int] = {}          # "file:label" -> dense id
        self.ops: list[tuple] = []                # intermediate op records
        self.choice_buf: list[tuple[str, str]] = []
        self.ignored: dict[str, int] = {}
        self.referenced: dict[str, tuple[str, str]] = {}  # stem -> (kind, orig)
        self.bgm_refs: dict[str, str] = {}        # stem -> original stem
        self.names: dict[str, int] = {}
        self.cur_speaker = ""

    def label_key(self, fname: str, label: str) -> str:
        return f"{fname}:{label}"

    # ---- pass 1: tokenize one .ks file into self.ops -----------------------

    def feed(self, fname: str, text: str) -> None:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("*"):
                label = line[1:].split("|")[0].strip()
                if label:
                    self.flush_choices()
                    key = self.label_key(fname, label)
                    self.labels.setdefault(key, len(self.labels))
                    self.ops.append(("LABEL", key))
                continue
            if line.startswith("@"):
                body = line[1:]
                m = re.match(r"([\w]+)(.*)", body)
                if m:
                    self.flush_choices()
                    self.tag(m.group(1), parse_attrs(m.group(2)), fname)
                continue
            # mixed line: walk [tags] and text segments in order
            pos = 0
            for m in TAG_RE.finditer(line):
                if m.start() > pos:
                    self.say(line[pos:m.start()])
                closing, name, body = m.group(1), m.group(2), m.group(3)
                if not closing:
                    self.flush_choices()
                    self.tag(name, parse_attrs(body), fname)
                pos = m.end()
            if pos < len(line):
                self.say(line[pos:])

    def say(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        name = ""
        for pat in self.cfg["name_patterns"]:
            m = re.match(pat, text)
            if m:
                name = m.group(1).strip()
                text = text[m.end():].strip()
                break
        if not name:
            name = self.cur_speaker
        self.ops.append(("SAY", name, text))
        self.names[name] = self.names.get(name, 0) + 1

    def flush_choices(self) -> None:
        if self.choice_buf:
            self.ops.append(("CHOICE", list(self.choice_buf)))
            self.choice_buf = []

    def tag(self, name: str, attrs: dict[str, str], fname: str) -> None:
        cfg = self.cfg
        storage = attrs.get("storage") or attrs.get("file") or attrs.get("bgm")

        if name == cfg["choice_tag"]:
            target = attrs.get("target", "")
            key = self.label_key(
                attrs.get("storage", fname).replace(".ks", ""), target.lstrip("*"))
            self.choice_buf.append((key, attrs.get("text", "...")))
            return
        if name in cfg["bgm_tags"]:
            if storage:
                stem = sanitize(Path(storage).stem)
                self.bgm_refs[stem] = Path(storage).stem
                self.ops.append(("BGM", stem))
            return
        if name in cfg["end_tags"]:
            self.ops.append(("END",))
            return
        if name == "jump" or name == "rjump" or name == "call":
            target = attrs.get("target", "").lstrip("*")
            dest = attrs.get("storage", fname)
            if target:
                key = self.label_key(dest.replace(".ks", ""), target)
                self.ops.append(("JUMP", key))
            return
        if name == "wait":
            try:
                ms = int(attrs.get("time", "0"))
            except ValueError:
                ms = 0
            if ms > 0:
                self.ops.append(("WAIT", min(3600, max(1, round(ms / 16.7)))))
            return
        if name == "image" and storage:
            layer = attrs.get("layer", "0")
            is_bg = (layer == "0") if cfg["image_layer0_is_bg"] else False
            if is_bg:
                self.bg(storage)
            else:
                self.spr(storage, attrs.get("pos", cfg["default_sprite_pos"]))
            return
        if storage and (name in cfg["bg_tags"] or name in cfg["fg_tags"]):
            if name in cfg["bg_tags"]:
                self.bg(storage)
            else:
                self.spr(storage, attrs.get("pos", cfg["default_sprite_pos"]))
            return
        if name in ("cl", "clear", "freeimage", "fgclear", "characlear"):
            self.ops.append(("SPRCLR", 3))
            return
        if name in ("name", "charname") and attrs.get("text"):
            self.cur_speaker = attrs["text"]
            return
        if name == "er" or name == "cm":
            self.cur_speaker = ""
            return
        self.ignored[name] = self.ignored.get(name, 0) + 1

    def bg(self, storage: str) -> None:
        stem = sanitize(Path(storage).stem)
        self.referenced[stem] = ("bg", Path(storage).stem)
        self.ops.append(("BG", stem))

    def spr(self, storage: str, pos: str) -> None:
        stem = sanitize(Path(storage).stem)
        self.referenced[stem] = ("spr", Path(storage).stem)
        self.ops.append(("SPR", stem, POS.get(pos, 1)))

    # ---- pass 2: emit --------------------------------------------------------

    def emit(self) -> bytes:
        # dense ids in insertion order; resolve every reference or die
        ids = {k: i for i, k in enumerate(
            sorted(self.labels, key=lambda k: self.labels[k]))}
        unresolved = []
        for op in self.ops:
            if op[0] == "JUMP" and op[1] not in ids:
                unresolved.append(op[1])
            elif op[0] == "CHOICE":
                unresolved += [key for key, _ in op[1] if key not in ids]
        if unresolved:
            die("unresolved jump/choice targets (labels not found): " +
                ", ".join(sorted(set(unresolved))[:10]))
        out = bytearray()
        recs = []

        def s_bytes(s: str) -> bytes:
            return s.encode("utf-8")

        for op in self.ops:
            recs.append((len(out), op))
            kind = op[0]
            if kind == "LABEL":
                out.append(OP_LABEL)
                out += struct.pack("<I", ids[op[1]])
            elif kind == "END":
                out.append(OP_END)
            elif kind == "BG":
                out.append(OP_BG)
                b = s_bytes(op[1])
                out += struct.pack("<H", len(b)) + b
            elif kind == "SPR":
                # rotate the free slot: 0 then 1
                slot = self._next_slot()
                out.append(OP_SPR)
                out.append(slot)
                out.append(op[2])
                b = s_bytes(op[1])
                out += struct.pack("<H", len(b)) + b
            elif kind == "SPRCLR":
                out.append(OP_SPRCLR)
                out.append(op[1])
                self._slot_ctr = 0
            elif kind == "BGM":
                out.append(OP_BGM)
                b = s_bytes(op[1])
                out += struct.pack("<H", len(b)) + b
            elif kind == "SAY":
                name, text = op[1], op[2]
                for part in split_say(text):
                    nb, tb = s_bytes(name), s_bytes(part)
                    out.append(OP_SAY)
                    out += struct.pack("<H", len(nb)) + nb
                    out += struct.pack("<H", len(tb)) + tb
            elif kind == "CHOICE":
                opts = op[1]
                out.append(OP_CHOICE)
                out.append(len(opts))
                for key, text in opts:
                    tb = s_bytes(text)
                    out += struct.pack("<I", ids[key])
                    out += struct.pack("<H", len(tb)) + tb
            elif kind == "JUMP":
                out.append(OP_JUMP)
                out += struct.pack("<I", ids[op[1]])
            elif kind == "WAIT":
                out.append(OP_WAIT)
                out += struct.pack("<H", op[1])
        out.append(OP_END)

        # label offset table: absolute file offset of each LABEL opcode
        # (header = magic 4 + ver 4 + count 4 + table 4*n)
        head_len = 12 + 4 * len(ids)
        offsets = [head_len] * len(ids)
        for pos_, op in recs:
            if op[0] == "LABEL":
                offsets[ids[op[1]]] = head_len + pos_
        head = bytearray(b"VNPK" + struct.pack("<II", 1, len(ids)))
        for o in offsets:
            head += struct.pack("<I", o)
        blob = bytes(head) + bytes(out)
        if len(blob) > SCRIPT_MAX:
            die(f"script.bin is {len(blob)} bytes > engine cap {SCRIPT_MAX}; "
                "split the game into chapter packs (see README)")
        return blob

    _slot_ctr = 0

    def _next_slot(self) -> int:
        s = self._slot_ctr % 2
        self._slot_ctr += 1
        return s


def sanitize(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    return (out[:59] or "x")


def split_say(text: str) -> list[str]:
    """Split a long line into SAY-sized parts at UTF-8 char boundaries."""
    parts, cur, cur_bytes = [], "", 0
    for ch in text:
        n = len(ch.encode("utf-8"))
        if cur_bytes + n > TEXT_MAX:
            parts.append(cur)
            cur, cur_bytes = "", 0
        cur += ch
        cur_bytes += n
    if cur:
        parts.append(cur)
    return parts


# ------------------------------------------------------------- pipeline -----

def find_asset(root: Path, orig_stem: str, exts: list[str]) -> Path | None:
    import glob as _glob
    pat = _glob.escape(str(root / "**" / orig_stem)) + ".*"
    for base in sorted(_glob.glob(pat, recursive=True)):
        p = Path(base)
        if p.is_file() and p.suffix.lower() in exts:
            return p
    return None


def write_pack(out: Path, script: bytes, font: bytes) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "script.bin").write_bytes(script)
    (out / "font.bin").write_bytes(font)
    return {"script.bin": len(script), "font.bin": len(font)}


def cmd_demo(args) -> None:
    out = Path(args.out)
    font_path = find_font(args.font)
    size = args.size
    print(f"font: {font_path} @ {size}px")

    lines = [
        ("BG", "bg_school"),
        ("BGM", "demo_loop"),
        ("SAY", "\u7cfb\u7edf", "\u65e9\u4e0a\u4e03\u70b9\uff0c\u9633\u5149"
         "\u4ece\u7a97\u5e18\u7f1d\u91cc\u6d17\u8fdb\u6559\u5ba4\u3002"),
        ("SPR", "spr_demo", 1),
        ("SAY", "\u5c0f\u96e8", "\u201c\u65e9\u5440\uff01\u4eca\u5929\u5929"
         "\u6c14\u771f\u597d\uff0c\u8981\u4e00\u8d77\u53bb\u5929\u53f0\u5417"
         "\uff1f\u201d"),
        ("SAY", "", "\uff08\u5979\u7684\u7b11\u5bb9\u4e00\u5982\u65e2\u5f80"
         "\u3002\uff09"),
        ("SAY", "\u5c0f\u96e8", "\u201c\u5bf9\u4e86\uff0c\u542c\u8bf4\u795e"
         "\u793e\u7684\u6a31\u82b1\u5f00\u4e86\uff0c\u5468\u672b\u4e00\u8d77"
         "\u53bb\u770b\u770b\u5427\uff1f\u8fd8\u53ef\u4ee5\u987a\u8def\u53bb"
         "\u53c2\u89c2\u90a3\u628a\u4f20\u8bf4\u4e2d\u7684\u5200\u3002\u201d"),
        ("CHOICE_PLACE", None),
        ("LABEL", "go_roof"),
        ("BG", "bg_room"),
        ("SPRCLR", None),
        ("SPR", "spr_demo", 1),
        ("SAY", "\u5c0f\u96e8", "\u201c\u98ce\u5f88\u5927\u5462\u2026\u2026"
         "\u4f46\u5f88\u8212\u670d\u3002\u201d"),
        ("SAY", "", "\u2014\u2014 \u5b8c \u2014\u2014"),
        ("END", None),
        ("LABEL", "stay"),
        ("SAY", "\u5c0f\u96e8", "\u201c\u4e5f\u597d\uff0c\u90a3\u6211\u4eec"
         "\u4e0b\u5348\u518d\u53bb\u5427\u3002\u201d"),
        ("SAY", "", "\u2014\u2014 \u5b8c \u2014\u2014"),
        ("END", None),
    ]
    choices = [
        ("\u4e00\u8d77\u53bb\u5929\u53f0", "go_roof"),
        ("\u7559\u5728\u6559\u5ba4", "stay"),
    ]

    c = Compiler(DEFAULT_CONFIG)
    # synthesize ops directly (no .ks parsing for the demo)
    c.ignored.clear()
    for op in lines:
        kind = op[0]
        if kind == "BG":
            c.bg(op[1])
        elif kind == "SPR":
            stem = sanitize(op[1])
            c.referenced[stem] = ("spr", stem)
            c.ops.append(("SPR", stem, op[2]))
        elif kind == "SPRCLR":
            c.ops.append(("SPRCLR", 3))
        elif kind == "BGM":
            c.bgm_refs[op[1]] = op[1]
            c.ops.append(("BGM", op[1]))
        elif kind == "SAY":
            c.ops.append(("SAY", op[1], op[2]))
        elif kind == "LABEL":
            c.labels.setdefault("demo:" + op[1], len(c.labels))
            c.ops.append(("LABEL", "demo:" + op[1]))
        elif kind == "CHOICE_PLACE":
            c.ops.append(("CHOICE",
                          [("demo:" + t, txt) for txt, t in choices]))
        elif kind == "END":
            c.ops.append(("END",))

    script = c.emit()
    chars = collect_chars(c)
    font = build_font(chars, size, font_path)
    sizes = write_pack(out, script, font)

    # assets: gradients + one soft-edged sprite
    (out / "bg").mkdir(exist_ok=True)
    (out / "spr").mkdir(exist_ok=True)
    bg_school = gradient(0x1d4e89, 0x9fc5ff, vertical=False)
    bg_room = gradient(0x7f4f24, 0xf3c57b, vertical=True)
    (out / "bg" / "bg_school.bin").write_bytes(pack_bg(bg_school))
    (out / "bg" / "bg_room.bin").write_bytes(pack_bg(bg_room))
    (out / "spr" / "spr_demo.bin").write_bytes(spr_silhouette())
    synth_demo_wav(out / "bgm" / "demo_loop.wav")

    # gallery: the two demo BGs double as CGs (unlock when first shown)
    (out / "cg").mkdir(exist_ok=True)
    (out / "cgt").mkdir(exist_ok=True)
    for stem, img in (("bg_school", bg_school), ("bg_room", bg_room)):
        (out / "cg" / f"{stem}.bin").write_bytes(
            (out / "bg" / f"{stem}.bin").read_bytes())
        (out / "cgt" / f"{stem}.bin").write_bytes(pack_thumb(img))

    # flowchart: one node per branch label
    ids = label_ids(c)
    write_flowidx(out, [(ids["demo:go_roof"], "一起去天台"),
                        (ids["demo:stay"], "留在教室")])

    # title screen image
    (out / "ui").mkdir(exist_ok=True)
    (out / "ui" / "title.bin").write_bytes(
        pack_bg(title_image(font_path)))

    report(out, sizes, c, args)


def title_image(font_path: Path) -> Image.Image:
    img = gradient(0x1b1035, 0x55286f, vertical=True)
    d = ImageDraw.Draw(img)
    big = ImageFont.truetype(str(font_path), 44)
    small = ImageFont.truetype(str(font_path), 16)
    d.text((30, 66), "NanoGal", font=big, fill=(245, 246, 250))
    d.text((34, 122), "横屏演示 · landscape demo pack", font=small,
           fill=(224, 122, 95))
    for i in range(18):
        d.ellipse([(i * 37 + 13) % 400, (i * 61 + 20) % 210,
                   (i * 37 + 17) % 400, (i * 61 + 24) % 210],
                  fill=(232, 198, 198))
    return img


def gradient(c1, c2, vertical=True) -> Image.Image:
    img = Image.new("RGB", (SCR_W, SCR_H))
    px = img.load()
    r1, g1, b1 = (c1 >> 16) & 255, (c1 >> 8) & 255, c1 & 255
    r2, g2, b2 = (c2 >> 16) & 255, (c2 >> 8) & 255, c2 & 255
    for y in range(SCR_H):
        for x in range(SCR_W):
            t = (y if vertical else x) / (SCR_H if vertical else SCR_W)
            px[x, y] = (round(r1 + (r2 - r1) * t),
                        round(g1 + (g2 - g1) * t),
                        round(b1 + (b2 - b1) * t))
    return img


def spr_silhouette() -> bytes:
    img = Image.new("RGBA", (110, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([30, 8, 80, 76], radius=24, fill=(255, 214, 165, 255))
    d.rounded_rectangle([18, 80, 92, 196], radius=26, fill=(120, 180, 255, 255))
    # soft radial fade at the bottom so the alpha path is exercised
    mask = Image.new("L", (110, 200), 0)
    dm = ImageDraw.Draw(mask)
    dm.rectangle([0, 130, 110, 200], fill=255)
    for y in range(130, 200):
        fade = int(255 * (1 - (y - 130) / 70))
        dm.line([(0, y), (110, y)], fill=fade)
    a = img.getchannel("A")
    img.putalpha(ImageChops.multiply(a, mask))
    return pack_spr(img)


def collect_chars(c: Compiler) -> set[str]:
    chars: set[str] = set()
    for op in c.ops:
        if op[0] == "SAY":
            chars |= set(op[1]) | set(op[2])
        elif op[0] == "CHOICE":
            for _, text in op[1]:
                chars |= set(text)
    chars |= set("\u3010\u3011\u201c\u201d\uff08\uff09\uff0c\u3002\uff01\uff1f\u2026\u2014")
    # the engine's own UI renders through this font too
    chars |= set("开始游戏继续CG鉴赏流程图设置返回标题自动播放"
                 "瞬间快速普通慢关文字速度音量页"
                 "读上一句进模式速档空已保存到头槽位无中")
    return chars


def cmd_kirikiri(args) -> None:
    game = Path(args.game)
    if not game.is_dir():
        die(f"game dir not found: {game}")
    out = Path(args.out)
    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        cfg.update(json.loads(Path(args.config).read_text(encoding="utf-8")))

    ks_files = sorted(game.rglob("*.ks"))
    if not ks_files:
        die(f"no .ks scenario files under {game} — extract the XP3 with "
            "GARbro first (script + images + audio)")
    entry = None
    for p in ks_files:
        if p.name.lower() == args.entry.lower():
            entry = p
            break
    if entry is None:
        entry = ks_files[0]
        if args.entry != "first.ks":
            warn(f"entry {args.entry} not found; using {entry.name}")
    ks_files = [entry] + [p for p in ks_files if p != entry]

    font_path = find_font(args.font)
    c = Compiler(cfg)
    for p in ks_files:
        c.feed(p.stem, read_text_ks(p))
    c.flush_choices()
    script = c.emit()
    font = build_font(collect_chars(c), args.size, font_path)
    sizes = write_pack(out, script, font)

    # assets
    img_exts = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]
    (out / "bg").mkdir(exist_ok=True)
    (out / "spr").mkdir(exist_ok=True)
    converted = skipped = 0
    for stem, (kind, orig) in sorted(c.referenced.items()):
        src = find_asset(game, orig, img_exts)
        if src is None:
            warn(f"asset not found: {orig} (referenced by script)")
            skipped += 1
            continue
        img = Image.open(src)
        has_alpha = (img.mode in ("RGBA", "LA") or
                     (img.mode == "P" and "transparency" in img.info))
        if kind == "spr" or has_alpha:
            (out / "spr" / (stem + ".bin")).write_bytes(pack_spr(img))
        else:
            (out / "bg" / (stem + ".bin")).write_bytes(pack_bg(img))
        converted += 1

    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if c.bgm_refs and not ffmpeg:
        warn("ffmpeg not found — BGM files skipped (install ffmpeg or pass "
             "--ffmpeg)")
    (out / "bgm").mkdir(exist_ok=True)
    aud = 0
    if ffmpeg:
        for stem, orig in sorted(c.bgm_refs.items()):
            src = find_asset(game, orig, [".ogg", ".mp3", ".wav", ".m4a", ".aac"])
            if src is None:
                warn(f"bgm not found: {orig}")
                continue
            if convert_wav(src, out / "bgm" / (stem + ".wav"), ffmpeg):
                aud += 1
            else:
                warn(f"ffmpeg failed on {src.name}")

    # ---- CG gallery manifest: every referenced background is a gallery entry
    bg_stems = [stem for stem, (kind, _) in c.referenced.items()
                if kind == "bg"][:CG_MAX]
    if bg_stems:
        (out / "cg").mkdir(exist_ok=True)
        (out / "cgt").mkdir(exist_ok=True)
        for stem in bg_stems:
            src_bin = out / "bg" / (stem + ".bin")
            if src_bin.is_file():
                (out / "cg" / (stem + ".bin")).write_bytes(src_bin.read_bytes())
                imgsrc = find_asset(game, c.referenced[stem][1], img_exts)
                if imgsrc:
                    (out / "cgt" / (stem + ".bin")).write_bytes(
                        pack_thumb(Image.open(imgsrc)))
        write_cgidx(out, bg_stems)

    # ---- flowchart manifest: script labels become jump nodes
    ids = label_ids(c)
    write_flowidx(out, [(ids[k], k.split(":", 1)[1][:NAME_MAX])
                        for k in list(ids)[:FLOW_MAX]])

    # ---- title screen: reuse the game's own title/logo art when present
    (out / "ui").mkdir(exist_ok=True)
    t = find_title_image(game)
    if t:
        (out / "ui" / "title.bin").write_bytes(pack_bg(Image.open(t)))
        print(f"title image: {t.name}")

    print(f"converted {converted} images ({skipped} missing), {aud} bgm tracks, "
          f"{len(bg_stems)} CG entries, {min(len(ids), FLOW_MAX)} flow nodes")
    report(out, sizes, c, args)


def find_title_image(game: Path) -> Path | None:
    cands = [p for p in game.rglob("*")
             if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp")
             and re.search(r"title|logo|op", p.name, re.I)]
    return sorted(cands, key=lambda p: (len(p.name), str(p)))[0] if cands else None


def report(out: Path, sizes: dict, c: Compiler, args) -> None:
    lines = [
        "GalPack — copy the CONTENTS of this folder into /Data/vn/ on the",
        "iPod disk (create the folder if needed), eject, then open NanoGal.",
        "",
        f"files: " + ", ".join(f"{k}={v}B" for k, v in sizes.items()),
        f"labels: {len(c.labels)}, ops: {len(c.ops)}, "
        f"unique ignored tags: {len(c.ignored)}",
    ]
    top = sorted(c.ignored.items(), key=lambda kv: -kv[1])[:15]
    if top:
        lines.append("most-skipped tags (map them via --config if needed):")
        lines += [f"  [{n}] x{cnt}" for n, cnt in top]
    (out / "pack-info.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[2:]))
    print(f"\npack written to {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)

    d = sub.add_parser("demo", help="synthesize a test pack")
    d.add_argument("out")
    d.add_argument("--font")
    d.add_argument("--size", type=int, default=16)
    d.set_defaults(fn=cmd_demo)

    k = sub.add_parser("kirikiri", help="convert an extracted KiriKiri game")
    k.add_argument("game")
    k.add_argument("out")
    k.add_argument("--entry", default="first.ks")
    k.add_argument("--config")
    k.add_argument("--font")
    k.add_argument("--size", type=int, default=16)
    k.add_argument("--ffmpeg")
    k.set_defaults(fn=cmd_kirikiri)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
