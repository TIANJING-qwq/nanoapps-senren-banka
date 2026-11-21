# 千恋万花 — landscape VN player for iPod nano 7 (NanoApps)

A visual-novel engine that plays converted Windows galgames on the nano,
held **landscape** (432×240 logical screen). This is the on-device half of
the port pipeline; the host half is `tools/build_galpack.py`.

Status: engine + demo pack complete and verified host-side. Senren Banka
asset extraction has landed — **the cxdec content decryption is fully
solved** (`tools/cxdec.py`, ported from the community `xp3filter.tjs`),
which unlocked bgimage/data archives: 97 background/CG PNGs and the
system UI/scripts. See "Extraction status" below.

## Screens

| Screen | What it does |
| --- | --- |
| Title | pack title image (real Senren Banka title art in the demo pack), **left-side** vertical menu in the original game's style: 开始游戏 / 继续游戏 / 读档 / CG鉴赏 / 流程图 / 设置 |
| Scenario | BG + up to 2 sprites, name plate, typewriter text box (3 rows), paging arrow, auto-mode |
| Choices | dimmed overlay, centered buttons |
| In-game menu | 12 items in two columns: 返回游戏 / 自动播放 / 快进模式 / 上一句 / 设置 / 返回标题 · 存档 / 读档 / 快速存档 / 快速读档 / CG鉴赏 / 流程图 |
| Save/Load | 8 manual slots + 快速 + 自动 rows, each showing a text preview of the saved line; save-mode tap writes the slot, load-mode tap restores it |
| CG gallery | 4×2 grid of 84×48 thumbnails, tap cycles pages, locked slots show `?`, tap opens fullscreen viewer (tap left/right cycles unlocked CGs) |
| Flowchart | chapter list with visited marks; tap a visited node jumps the script there; unvisited shows `???` |
| Settings | text speed (瞬间/快/普通/慢), auto-advance (关/快/普通/慢), volume 0–8 — persisted |
| END / errors | `- THE END -`; red error screen with pack error code |

Controls:

- tap = advance/page/select; tap during 快进 cancels it.
- **VOL_UP hold** = fast-forward text reveal; VOL_UP press in
  gallery/flow/settings/save-load = back out.
- **VOL_DOWN press in scene = 快退** (rewind one dialogue line, up to 24
  lines back); in list screens = same back-out as VOL_UP.

## Orientation

Hold the nano rotated 90° **clockwise**: home button on the LEFT, volume
buttons toward the top. Logical (lx, ly) → physical framebuffer
`fb[lx*240 + ly]`. If your grip is mirrored and everything is upside
down, flip `lx`/`ly` in `lpx()` and `hb_raw_frame()` (one-line change,
marked in the source).

## GalPack format (on /Data/vn/ on the iPod disk)

| File | Format |
| --- | --- |
| `script.bin` | `VNPK` u32 ver u32 nlabels, u32 table[nlabels] (absolute offsets of LABEL ops), then opcodes |
| `font.bin` | `VNFN` u8 w u8 h u8 bpp(1) u8 rsvd u16 n, then n × (u32 codepoint sorted, h × bpr rows, MSB-left) |
| `bg/*.bin`, `cg/*.bin`, `ui/title.bin` | `VNBI` u16 w u16 h u8 fmt(0); RGB565 plane, 432×240 |
| `spr/*.bin` | `VNBI` fmt 1; RGB565 plane + A8 plane, ≤160×220 |
| `cgt/*.bin` | `VNBI` fmt 0, 84×48 thumbnails |
| `cg.idx` | `VNCG` u16 ver u16 n, then n × (u16 len, utf-8 name) — gallery order |
| `flow.idx` | `VNFL` u16 ver u16 n, then n × (u32 label_id, u16 len, utf-8 title) |
| `bgm/*.wav` | mono 16-bit PCM WAV, one-shot, volume from settings |

Opcodes: `0 END, 1 LABEL u32, 2 BG str, 3 SPR u8 slot u8 pos str,
4 SPRCLR u8 mask, 5 BGM str, 6 SAY str name + str text, 7 CHOICE u8 n ×
(u32 label + str), 8 JUMP u32, 9 WAIT u16, 10 NEXT u16 chapter`.
END is terminal; code after the first END is branch data reachable only
via jumps. **NEXT** loads `ch/NNNN.bin` (chapter number) and continues —
the full-game pack chains 88 chapters this way.

Engine-written files (all `VNSV` **v3**: magic + ver + SAY offset +
**u16 chapter** + pad + bg/spr names + positions + 64-byte preview;
total 274 B):

- `save.bin` — auto slot, rewritten at every SAY
- `save0..7.bin` — 8 manual slots (存档 screen)
- `quick.bin` — 快速存档 slot (QSAVE/QLOAD menu items)

`seen.bin` (CG + flow unlock bitmaps, flushed with the autosave),
`settings.bin`. `flow.idx` ver 2 = chapter mode (node id = chapter
number; tapping a visited node loads that chapter); ver 1 = legacy
in-file label mode.

## Full-game pipeline (Senren Banka, 37,201 lines)

```
python tools/unpack_xp3.py extract <xp3> out --decrypt <xp3filter.tjs>
python tools/scn_carve.py  <scenario.pck> build/sb_scn      # 92 PSB vols
python tools/sb_extract.py build/sb_scn build/sb_dialogue.tsv
python tools/sb_topack.py  build/sb_dialogue.tsv build/sb_pack
python tools/sb_bgimport.py build/sb_full                  # bg/bbNN.bin
python tools/sb_fullpack.py build/sb_pack build/sb_full    # font+assets
python tools/sb_checkall.py build/sb_full                  # walk check
```

## Build & run

```
./start build vn && ./start install vn        # Mac/Linux with the SDK
python tools/build_galpack.py demo build/galpack-demo
python tools/verify_galpack.py build/galpack-demo
python tools/render_galpack_preview.py build/galpack-demo build/preview.png
```

Copy the **contents** of the pack dir into `/Data/vn/` on the iPod disk
(while on the Home Screen, not in "Connected" mode), then open 千恋万花.

Caps (engine ↔ converter locked): script ≤ 384 KiB, font ≤ 3000 glyphs
≤ 24 px, names ≤ 63 B, one line ≤ ~740 B, 2 sprite slots, CG ≤ 512,
flow ≤ 256. Runtime RAM ≈ 1.3 MiB.

Error codes: E0 bad opcode, E1/E2 truncated stream, E3 path too long,
E4 asset too large, E5 asset > scratch cap, E6 bad jump, E8 unknown op,
E9 script too big, EA version, EB label table.

## Extraction status (Senren Banka, KiriKiri Z)

**SOLVED this round — cxdec content decryption** (`tools/cxdec.py`): a
1:1 Python port of the community `xp3filter.tjs` filter. The XP3 `adlr`
chunk (a content checksum stored per file in the archive index) is the
only key needed, so **every encrypted archive decrypts without knowing
the hashed filenames**:

```
python tools/unpack_xp3.py extract "K:\千恋＊万花\bgimage720.xp3" out \
    --decrypt "K:\千恋＊万花\补丁\解密补丁\xp3filter.tjs"
```

Unlocked so far: `bgimage720.xp3` (97 PNGs: 75 event CGs 1480×853,
21 backgrounds 1280×720, 1 title 1920×1080 — the demo pack's title art
is the real game title screen), `data.xp3` (172 TJS scripts, 95 PSB
scenario volumes, 48 UI PNGs, 367 OGG sound effects, plain-text tjs).

Remaining blockers for a full-game pack:

1. **Hashed filenames** — the `adlr` value is a content checksum, not a
   name hash, so script→asset matching needs names recovered from the
   decrypted TJS/PSB string tables (next step), or a KrkrExtract
   real-name dump.
2. **Compiled scenario** — PSB (M2 compiled) volumes; needs a PSB
   reader + Yuzusoft command schema mapping into GalPack ops.
3. **BGM/voice are OGG** — convert host-side with ffmpeg (not required
   for the demo).

## Legal

Engine and tools only. Convert games you own, for personal use; do not
distribute converted packs.
