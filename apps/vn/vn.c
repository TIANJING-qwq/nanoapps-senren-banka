/*
 * vn 鈥?landscape visual-novel player for NanoApps: the on-device half of
 * the galgame port pipeline (see tools/build_galpack.py for the host half).
 *
 * LANDSCAPE by design: the logical screen is 432x240 and the user holds
 * the nano rotated 90掳 clockwise (home button on the LEFT, volume buttons
 * toward the top). The engine maps logical (lx, ly) to the physical
 * 240x432 framebuffer as:
 *     phys_x = ly,  phys_y = lx      (fb[lx*240 + ly])
 * and the touch coordinates are transformed with the same mapping.
 * (If your grip is the other way round and the image is upside down,
 * flip lx/ly with SCR_W-1-x / SCR_H-1-y in lpx() and hb_raw_frame.)
 *
 * GalPack on /Data/vn/ (all formats documented in apps/vn/README.md):
 *   script.bin   compiled scenario (opcodes + UTF-8 strings)
 *   font.bin     subset 1-bpp CJK bitmap font
 *   bg/*.bin     backgrounds, 432x240 RGB565
 *   spr/*.bin    sprites, RGB565 + A8 planes (bottom-anchored)
 *   ui/title.bin optional 432x240 title image (fallback is drawn)
 *   cg.idx       CG gallery manifest (references bg assets)
 *   cg/*.bin     gallery CGs, 432x240; cgt/*.bin 84x48 thumbnails
 *   flow.idx     flowchart manifest (scene labels + titles)
 *   bgm/*.wav    mono 16-bit WAV, one-shot, volume from settings
 *   seen.bin     engine-written unlock bitmaps (CG + flow nodes)
 *   settings.bin engine-written settings
 *   save.bin     engine-written auto-save (every dialogue line)
 *   save0..7.bin manual save slots; quick.bin = quick-save slot
 *                (all VNSV v2: + 64-byte preview text)
 *
 * Screens: title (Yuzusoft-style LEFT menu over the real title art),
 * scenario (dialogue box, name plate, typewriter, paging), choices,
 * in-game menu (12 items: resume/auto/skip/rewind/save/load/quick save/
 * quick load/config/CG/flow/title), save/load slot picker, CG gallery
 * (grid + fullscreen viewer), flowchart (chapter list, tap to jump),
 * settings (tap to cycle values), END. VOL_UP hold = fast-forward,
 * VOL_DOWN tap in-scene = rewind one line; in list screens it backs out.
 */

#include "hb_raw_surface.h"
#include "hb_sdk.h"

/* ---------------------------------------------------------------- layout --- */

#define SCR_W     432                  /* logical landscape size             */
#define SCR_H     240
#define PHW       240                  /* physical framebuffer width         */

#define BOX_X     16
#define BOX_W     (SCR_W - 2 * (BOX_X))
#define BOX_Y     130
#define BOX_H     104
#define TXT_X     ((BOX_X) + 14)
#define TXT_Y     ((BOX_Y) + 34)
#define TXT_W     ((BOX_W) - 28)
#define LINE_GAP  4

#define DIR_BASE  "/Data/vn"

/* ------------------------------------------------------------- pack caps --- */

#define SCRIPT_MAX      (160u * 1024u)
#define FONT_GLYPH_MAX  3400
#define FONT_W_MAX      20
#define FONT_H_MAX      20
#define FONT_FILE_MAX   (10u + (FONT_GLYPH_MAX) * \
                         (4u + (FONT_H_MAX) * (((FONT_W_MAX) + 7u) / 8u)))
/* asset scratch: largest asset is a 432x240 RGB565 bg/cg (9-byte header +
 * 2 bytes/pixel). MUST be separate from s_font_file: images loaded every
 * frame used to overwrite the glyph bitmaps (the "all CJK garbled" bug). */
#define ASSET_MAX       (9u + 432u * 240u * 2u)  /* largest staged asset = a full-screen bg/cg */
#define BG_W            SCR_W
#define BG_H            SCR_H
#define SPR_SLOTS       1
#define SPR_W_MAX       160
#define SPR_H_MAX       220
#define SPR_PX          ((SPR_W_MAX) * (SPR_H_MAX))
#define NAME_MAX        96
#define TEXT_MAX        768
#define SAVENAME_MAX    64
#define CHOICE_MAX      5
#define CG_MAX          512
#define FLOW_MAX        256
#define THUMB_W         84
#define THUMB_H         48
#define THUMB_PX        ((THUMB_W) * (THUMB_H))

/* --------------------------------------------------------------- opcodes --- */

#define OP_END     0x00
#define OP_NEXT_CH 0x0A
#define OP_LABEL   0x01   /* u32 label_id                               */
#define OP_BG      0x02   /* u16 nlen, name[]                           */
#define OP_SPR     0x03   /* u8 slot, u8 pos, u16 nlen, name[]          */
#define OP_SPRCLR  0x04   /* u8 mask                                    */
#define OP_BGM     0x05   /* u16 nlen, name[]                           */
#define OP_JUMPX   0x0D   /* u16 chapter, u32 label: cross-chapter jump */
#define OP_VOICE   0x0B   /* u16 nlen, name[] 鈥?line voice clip          */
#define OP_CG      0x0C   /* u16 nlen, name[] — event CG */
#define OP_SAY     0x06   /* u16 nlen, name[], u16 tlen, text[]         */
#define OP_CHOICE  0x07   /* u8 n, n * (u32 label, u16 tlen, text[])    */
#define OP_JUMP    0x08   /* u32 label_id                               */
#define OP_WAIT    0x09   /* u16 frames                                 */

#define SPR_LIFT    12      /* raise the stand so the head clears the text box */
#define SPR_SHIFT   30      /* nudge every stand to the right */
#define POS_LEFT    0
#define POS_CENTER  1
#define POS_RIGHT   2

/* ---------------------------------------------------------------- modes ---- */

enum {
    MODE_MISSING = 0,
    MODE_TITLE,
    MODE_SCENE,
    MODE_CHOICE,
    MODE_IGMENU,          /* in-game menu overlay                        */
    MODE_SAVELOAD,        /* save/load slot picker (s_slot_pick = which) */
    MODE_GALLERY,         /* CG grid                                     */
    MODE_CGVIEW,          /* CG fullscreen                               */
    MODE_FLOW,            /* flowchart / chapter jump                    */
    MODE_CHSEL,           /* chapter select by route (鍏遍€?涓汉/鍚庢棩璋?  */
    MODE_SETTINGS,
    MODE_END,
    MODE_ERROR,
};

/* pseudo modes for s_slot_pick (never a real s_mode value) */
#define MODE_SAVE 0xFEu
#define MODE_LOAD 0xFFu

/* ---------------------------------------------------------------- state ---- */

/* font.bin: "VNFN" u8 w u8 h u8 bpp u8 rsvd u16 n, sorted entries */
static uint8_t  s_font_file[FONT_FILE_MAX];   /* font.bin ONLY              */
static uint8_t  s_asset_buf[ASSET_MAX];       /* image load scratch         */
static uint8_t  s_font_w, s_font_h;
static uint16_t s_font_n;
static uint32_t s_font_cp[FONT_GLYPH_MAX];
static uint32_t s_font_off[FONT_GLYPH_MAX];
static uint32_t s_font_got;                    /* bytes read (self-test)  */
static uint32_t s_font_xor;                    /* sample checksum         */
static uint16_t s_voice_play, s_voice_miss;    /* audio self-test counters */
static uint16_t s_bgm_play, s_bgm_miss;

/* script.bin: "VNPK" u32 ver u32 nlabels, u32 table[], opcode stream */
static uint8_t  s_script[SCRIPT_MAX];
static uint32_t s_script_len;
static uint32_t s_labels_n;
static uint16_t s_chapter;
static uint32_t s_pc;

/* scene caches */
static uint16_t s_bg[BG_W * BG_H];
static uint8_t  s_bg_ok;
static char     s_cur_bg[SAVENAME_MAX];
static uint8_t  s_cur_cg_is_cg;

static struct {
    uint8_t  used, pos;
    uint16_t w, h;
    char     name[SAVENAME_MAX];
    uint16_t color[SPR_PX];
    uint8_t  alpha[SPR_PX];
} s_spr[SPR_SLOTS];

/* current line */
static char     s_say_name[NAME_MAX];
static char     s_say_text[TEXT_MAX];
static uint16_t s_say_len;
static uint16_t s_page_start;
static uint16_t s_reveal;
static uint8_t  s_have_name;

/* choices */
static uint8_t  s_choice_n;
static char     s_choice_text[CHOICE_MAX][NAME_MAX];
static uint32_t s_choice_label[CHOICE_MAX];

/* CG gallery */
static uint16_t s_cg_n;
static char     s_cg_name[CG_MAX][SAVENAME_MAX];
static uint8_t  s_cg_seen[(CG_MAX + 7) / 8];
static uint16_t s_cg_page;
static uint16_t s_cg_view;               /* index being viewed             */
static uint16_t s_thumb[THUMB_PX];

/* flowchart */
static uint16_t s_flow_n;
static uint16_t s_flow_ver;
static uint32_t s_flow_label[FLOW_MAX];
static char     s_flow_title[FLOW_MAX][NAME_MAX];
static uint8_t  s_flow_seen[(FLOW_MAX + 7) / 8];
static uint16_t s_flow_top;              /* scroll line                    */
static uint8_t  s_seen_dirty;

/* chapter select (VNCS): grouped route list 鍏遍€?涓汉绾?鍚庢棩璋?*/
#define CHSEL_MAX  96
#define CHSEL_GROUP_N 7
static uint16_t s_chsel_n;
static uint8_t  s_chsel_group[CHSEL_MAX];
static uint16_t s_chsel_ch[CHSEL_MAX];
static char     s_chsel_title[CHSEL_MAX][NAME_MAX];
static uint16_t s_chsel_top;

/* settings */
static uint8_t  s_set_speed;             /* 0鐬?1蹇?2鏅?3鎱?                */
static uint8_t  s_set_auto;              /* 0 off 1蹇?2鏅?3鎱?              */
static uint8_t  s_set_volume;            /* 0..8                           */
static uint8_t  s_set_unlock;            /* debug: show all CG / flowchart */
static uint8_t  s_set_voice = 1;         /* voice playback on/off          */
static uint8_t  s_need_full;             /* repaint bg+sprites this frame  */
static uint8_t  s_prev_mode = 0xFFu;     /* detect mode switches           */

/* Audio: the SDK spawns a pthread for loadFile+play and that pthread only
 * gets CPU when the caller yields. A tight 60 fps redraw loop STARVES it
 * (SDK: "...or block on a long sleep. A tight UI loop ... will STARVE the
 * pthread and no sound plays."). So sounds are queued here and started at
 * the very end of the frame, followed by a vsync wait which both paces the
 * loop and hands the CPU to the audio worker. */
static char     s_pending_snd[96];
static uint16_t s_pending_vol;
static uint8_t  s_pending_kind;          /* 0 none, 1 bgm, 2 voice        */
static char     s_dbg_snd[40];           /* last attempted sound (tail)   */
static uint8_t  s_dbg_ret;               /* its play() return value       */
static uint16_t s_dbg_calls;             /* how many play calls happened  */
/* The iPod audio API owns ONE static descriptor and is single-shot: calling
 * it again before the previous clip finished overlaps/crashes (device
 * reboot). Everything goes through this mutex. */
static uint32_t s_audio_until;
static int audio_busy(void);
static char     s_last_voice[32];        /* dedupe repeated OP_VOICE      */
static uint16_t s_pending_ticks;         /* length of the queued clip     */

static uint8_t  s_dbg_fs;                /* file existed when attempted   */

static void queue_sound(const char *path, uint16_t vol, uint8_t kind,
                        uint16_t ticks)
{
    s_pending_ticks = ticks;
    uint32_t i = 0;
    while (path[i] && i < sizeof s_pending_snd - 1u) {
        s_pending_snd[i] = path[i];
        i++;
    }
    s_pending_snd[i] = 0;
    s_pending_vol = vol;
    s_pending_kind = kind;
}
static uint16_t s_auto_ticks;

/* run state */
static uint8_t  s_mode;
static uint8_t  s_ret_mode;              /* where IG-menu/settings return  */
static uint32_t s_ticks;

static int audio_busy(void)
{
    return (int32_t)(s_audio_until - s_ticks) > 0;
}
static uint16_t s_wait;
static uint8_t  s_prev_down;
static uint8_t  s_prev_ffwd;
static uint8_t  s_prev_back;
static int16_t  s_dbg_lx = -1, s_dbg_ly = -1;      /* touch debug readout */
static uint8_t  s_skip;                  /* skip-to-choice fast-forward   */
static uint8_t  s_skip_bg;               /* skip to the next background   */
static uint8_t  s_saw_bg;                /* step() just executed OP_BG    */
static char     s_last_bgm[SAVENAME_MAX];
static uint32_t s_bgm_ticks;             /* length of current bgm, frames */
static uint32_t s_bgm_t0;                /* frame it (re)started at       */
static uint16_t s_bgm_vol;               /* volume of the current bgm     */
static uint32_t s_voice_ticks;  /* voice window length in frames (~33ms) */
static uint32_t s_voice_t0;     /* frame counter when it started       */
#define VOICE_TICK_MS 33u       /* one s_ticks frame 鈮?33 ms            */
static uint32_t s_err;
static uint8_t  s_save_valid;
static uint32_t s_save_off;
static uint16_t s_save_ch;
static uint32_t s_say_off;                 /* offset of the SAY being shown */
static char     s_save_bg[SAVENAME_MAX];
static char     s_save_spr[SPR_SLOTS][SAVENAME_MAX];
static uint8_t  s_save_pos[SPR_SLOTS];

/* dialogue rewind ring: offsets of the last SAY ops (蹇€€) */
#define HIST_MAX 24
static uint32_t s_hist[HIST_MAX];
static uint8_t  s_hist_n;

/* toast */
static char     s_toast[96];
static uint16_t s_toast_ticks;
static void set_toast(const char *s)
{
    uint32_t i;
    for (i = 0; i + 1 < sizeof s_toast && s[i]; i++) s_toast[i] = s[i];
    s_toast[i] = 0;
    s_toast_ticks = 90;
}

/* save slots: 0..7 = save0..7.bin, 8 = quick.bin, 9 = save.bin (auto) */
#define SAVE_SLOTS 8
#define SLOT_QUICK 8u
#define SLOT_AUTO  9u
static uint8_t  s_slot_pick;              /* MODE_SAVE or MODE_LOAD        */
static uint8_t  s_slot_meta[10];          /* 1 = has data                  */
static char     s_slot_prev[10][SAVENAME_MAX];

#define SAVE_MAGIC   0x564E5356u   /* 'VNSV' */
#define SAVE_VERSION 3u
#define SAVE_SIZE    (16u + 3u * (SAVENAME_MAX) + 2u + (SAVENAME_MAX))

/* ------------------------------------------------------------ tiny utils --- */

static void start_new_game(void);
static void continue_game(void);
static void step(void);

static void xmemcpy(void *dst, const void *src, uint32_t n)
{
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    while (n--) *d++ = *s++;
}

static uint32_t xstrlen(const char *s)
{
    uint32_t n = 0;
    while (s[n]) n++;
    return n;
}

static uint8_t str_eq(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static uint32_t utf8_next(const char *s, const char **next)
{
    unsigned char c = (unsigned char)*s;
    *next = s + 1;
    if (c == 0) return 0;
    if (c < 0x80) return c;
    if ((c & 0xE0u) == 0xC0u && (s[1] & 0xC0u) == 0x80u) {
        *next = s + 2;
        return ((uint32_t)(c & 0x1Fu) << 6) | ((uint32_t)s[1] & 0x3Fu);
    }
    if ((c & 0xF0u) == 0xE0u && (s[1] & 0xC0u) == 0x80u && (s[2] & 0xC0u) == 0x80u) {
        *next = s + 3;
        return ((uint32_t)(c & 0x0Fu) << 12) | ((uint32_t)(s[1] & 0x3Fu) << 6) |
               (uint32_t)(s[2] & 0x3Fu);
    }
    if ((c & 0xF8u) == 0xF0u && (s[1] & 0xC0u) == 0x80u && (s[2] & 0xC0u) == 0x80u &&
        (s[3] & 0xC0u) == 0x80u) {
        *next = s + 4;
        return ((uint32_t)(c & 0x07u) << 18) | ((uint32_t)(s[1] & 0x3Fu) << 12) |
               ((uint32_t)(s[2] & 0x3Fu) << 6) | (uint32_t)(s[3] & 0x3Fu);
    }
    return 0xFFFDu;
}

static void rd_err(uint32_t code) { s_err = code; s_mode = MODE_ERROR; }

static uint8_t rd_u8(void)
{
    if (s_pc + 1u > s_script_len) { rd_err(0xE0u); return 0; }
    return s_script[s_pc++];
}

static uint16_t rd_u16(void)
{
    uint16_t v;
    if (s_pc + 2u > s_script_len) { rd_err(0xE1u); return 0; }
    v = (uint16_t)((uint16_t)s_script[s_pc] | ((uint16_t)s_script[s_pc + 1u] << 8));
    s_pc += 2u;
    return v;
}

static uint32_t rd_u32(void)
{
    uint32_t v;
    if (s_pc + 4u > s_script_len) { rd_err(0xE2u); return 0; }
    v = (uint32_t)s_script[s_pc] | ((uint32_t)s_script[s_pc + 1u] << 8) |
        ((uint32_t)s_script[s_pc + 2u] << 16) | ((uint32_t)s_script[s_pc + 3u] << 24);
    s_pc += 4u;
    return v;
}

static void rd_str(char *dst, uint16_t dst_size)
{
    uint16_t n = rd_u16(), i;
    for (i = 0; i < n; i++) {
        uint8_t c = rd_u8();
        if (i + 1u < dst_size) dst[i] = (char)c;
    }
    if (n < dst_size - 1u) dst[n] = 0;
    else dst[dst_size - 1u] = 0;
}

/* ----------------------------------------------------- landscape drawing --- */
/* Device held rotated 90掳 CW (Home button LEFT): physical top edge faces
 * the user's right, so logical X grows toward DECREASING physical y:
 *   fb[(SCR_W-1-lx)*240 + ly]
 * (the previous lx*240+ly form was the CCW grip 鈥?a mirror image.) */

static uint32_t *lpx(int lx, int ly)
{
    return hb_raw_fb() + (long)(SCR_W - 1 - lx) * PHW + ly;
}

static uint32_t rgb565_x(uint16_t p)
{
    uint32_t r = ((uint32_t)p >> 11) & 0x1Fu, g = ((uint32_t)p >> 5) & 0x3Fu,
             b = (uint32_t)p & 0x1Fu;
    return ((r << 3 | r >> 2) << 16) | ((g << 2 | g >> 4) << 8) | (b << 3 | b >> 2);
}

static void lfill_rect(int x, int y, int w, int h, uint32_t col)
{
    int xx, yy, y0 = y, y1 = y + h;
    if (x < 0) { w += x; x = 0; }
    if (x + w > SCR_W) w = SCR_W - x;
    if (y0 < 0) y0 = 0;
    if (y1 > SCR_H) y1 = SCR_H;
    if (w <= 0 || y1 <= y0) return;
    col |= 0xFF000000u;
    for (xx = x; xx < x + w; xx++) {
        /* one multiply per column, then linear writes (phys y is contiguous) */
        uint32_t *p = lpx(xx, y0);
        for (yy = y0; yy < y1; yy++) *p++ = col;
    }
}

static void ldim_rect(int x, int y, int w, int h, uint8_t keep)
{
    int xx, yy, y0 = y, y1 = y + h;
    if (x < 0) { w += x; x = 0; }
    if (x + w > SCR_W) w = SCR_W - x;
    if (y0 < 0) y0 = 0;
    if (y1 > SCR_H) y1 = SCR_H;
    if (w <= 0 || y1 <= y0) return;
    for (xx = x; xx < x + w; xx++) {
        uint32_t *p = lpx(xx, y0);
        for (yy = y0; yy < y1; yy++, p++) {
            uint32_t c = p[0];
            p[0] = 0xFF000000u |
                (((((c >> 16) & 0xFFu) * keep) >> 8) << 16) |
                (((((c >> 8) & 0xFFu) * keep) >> 8) << 8) |
                ((((c & 0xFFu) * keep) >> 8));
        }
    }
}

static void lrect_outline(int x, int y, int w, int h, int t, uint32_t col)
{
    lfill_rect(x, y, w, t, col);
    lfill_rect(x, y + h - t, w, t, col);
    lfill_rect(x, y, t, h, col);
    lfill_rect(x + w - t, y, t, h, col);
}



static void draw_glyph(int x, int y, uint32_t cp, uint32_t col)
{
    int lo = 0, hi = (int)s_font_n - 1, mid = -1;
    int bpr = (s_font_w + 7) >> 3, row, bit;
    const uint8_t *bm;

    if (!s_font_w) return;
    while (lo <= hi) {
        mid = (lo + hi) >> 1;
        if (s_font_cp[mid] == cp) break;
        if (s_font_cp[mid] < cp) lo = mid + 1; else hi = mid - 1;
    }
    if (lo > hi || mid < 0 || s_font_cp[mid] != cp) return;
    bm = s_font_file + s_font_off[mid];
    col |= 0xFF000000u;
    for (row = 0; row < s_font_h; row++) {
        int yy = y + row;
        if (yy < 0 || yy >= SCR_H) continue;
        for (bit = 0; bit < s_font_w; bit++) {
            int xx = x + bit;
            if (xx < 0 || xx >= SCR_W) continue;
            if (bm[(long)row * bpr + (bit >> 3)] & (0x80u >> (bit & 7)))
                lpx(xx, yy)[0] = col;
        }
    }
}

static void draw_str(const char *p, int x, int y, uint32_t col)
{
    while (*p) {
        const char *np;
        uint32_t cp = utf8_next(p, &np);
        draw_glyph(x, y, cp, col);
        x += s_font_w;
        p = np;
    }
}

static uint32_t str_chars(const char *p)
{
    uint32_t n = 0;
    while (*p) { const char *np; utf8_next(p, &np); p = np; n++; }
    return n;
}

static void draw_str_center(const char *p, int cx, int y, uint32_t col)
{
    draw_str(p, cx - (int)(str_chars(p) * s_font_w) / 2, y, col);
}

/* 8x8 ASCII via the SDK font (menus/help when no CJK font is present) */
static void draw_ascii8(int x, int y, const char *s, int scale, uint32_t col)
{
    col |= 0xFF000000u;
    for (; *s; s++, x += 8 * scale) {
        const uint8_t *g = hb_font8x8_glyph(*s);
        int row, bit, dx, dy;
        if (!g) continue;
        for (row = 0; row < 8; row++) {
            for (bit = 0; bit < 8; bit++) {
                if (!(g[row] & (0x80u >> bit))) continue;
                for (dy = 0; dy < scale; dy++) {
                    if (y + row * scale + dy < 0 || y + row * scale + dy >= SCR_H)
                        continue;
                    for (dx = 0; dx < scale; dx++) {
                        int xx = x + bit * scale + dx;
                        if (xx < 0 || xx >= SCR_W) continue;
                        lpx(xx, y + row * scale + dy)[0] = col;
                    }
                }
            }
        }
    }
}

static int ascii8_w(const char *s, int scale) { return (int)xstrlen(s) * 8 * scale; }

/* ------------------------------------------------------------- loading ---- */

static uint8_t load_asset(const char *dir, const char *name, uint16_t want_w,
                          uint16_t want_h, uint8_t want_alpha,
                          uint16_t *color_out, uint8_t *alpha_out,
                          uint16_t *out_w, uint16_t *out_h)
{
    char path[96];
    uint8_t hdr[9];
    uint32_t got, need, px, i;
    uint16_t w, h;
    uint8_t fmt;
    uint32_t dl = xstrlen(dir), nl = xstrlen(name);

    if (9u + dl + 1u + nl + 5u > sizeof path) { rd_err(0xE3u); return 0; }
    xmemcpy(path, DIR_BASE "/", 9);
    xmemcpy(path + 9, dir, dl);
    path[9 + dl] = '/';
    xmemcpy(path + 10 + dl, name, nl + 1);
    xmemcpy(path + 10 + dl + nl, ".bin", 5);

    got = hb_fs_read(path, hdr, 9);
    if (got != 9 || hdr[0] != 'V' || hdr[1] != 'N' || hdr[2] != 'B' || hdr[3] != 'I')
        return 0;
    w = (uint16_t)((uint16_t)hdr[4] | ((uint16_t)hdr[5] << 8));
    h = (uint16_t)((uint16_t)hdr[6] | ((uint16_t)hdr[7] << 8));
    fmt = hdr[8];
    if (w == 0 || h == 0) return 0;
    if ((fmt == 1u) != (want_alpha ? 1u : 0u)) return 0;
    if (want_w && (w > want_w || h > want_h)) { rd_err(0xE4u); return 0; }

    px = (uint32_t)w * h;
    need = 9u + px * 2u + (fmt == 1u ? px : 0u);
    if (need > ASSET_MAX) { rd_err(0xE5u); return 0; }

    got = hb_fs_read_chunked(path, s_asset_buf, need);
    if (got != need) return 0;
    if (color_out)
        for (i = 0; i < px; i++)
            color_out[i] = (uint16_t)((uint16_t)s_asset_buf[9u + i * 2u] |
                                      ((uint16_t)s_asset_buf[9u + i * 2u + 1u] << 8));
    if (alpha_out && fmt == 1u)
        xmemcpy(alpha_out, s_asset_buf + 9u + px * 2u, px);
    if (out_w) *out_w = w;
    if (out_h) *out_h = h;
    return 1;
}

static void cg_unlock(const char *name);

static void set_bg(const char *name)
{
    uint16_t w = 0, h = 0;
    /* same background already loaded: do NOT re-read the 207 KB file */
    if (name[0] && s_bg_ok && str_eq(name, s_cur_bg)) return;
    s_bg_ok = 0;
    s_cur_bg[0] = 0;
    s_need_full = 1;
    if (!name[0]) return;
    if (load_asset("bg", name, BG_W, BG_H, 0, s_bg, 0, &w, &h) &&
        w == BG_W && h == BG_H) {
        s_bg_ok = 1;
        xmemcpy(s_cur_bg, name, xstrlen(name) + 1);
        cg_unlock(name);
    }
}

static void set_cg(const char *name)
{
    uint16_t w = 0, h = 0;
    if (name[0] && s_bg_ok && s_cur_cg_is_cg && str_eq(name, s_cur_bg))
        return;                       /* already showing this CG */
    s_bg_ok = 0;
    s_cur_bg[0] = 0;
    s_cur_cg_is_cg = 1;
    s_need_full = 1;
    if (!name[0]) return;
    if (load_asset("cg", name, BG_W, BG_H, 0, s_bg, 0, &w, &h) &&
        w == BG_W && h == BG_H) {
        s_bg_ok = 1;
        xmemcpy(s_cur_bg, name, xstrlen(name) + 1);
    }
}

static void set_spr(int slot, uint8_t pos, const char *name)
{
    if (slot < SPR_SLOTS && s_spr[slot].used && str_eq(name, s_spr[slot].name))
        return;                       /* already showing this sprite */
    s_need_full = 1;
    if (slot >= SPR_SLOTS) return;
    s_spr[slot].used = 0;
    s_spr[slot].name[0] = 0;
    if (!name[0]) return;
    if (load_asset("spr", name, SPR_W_MAX, SPR_H_MAX, 1,
                   s_spr[slot].color, s_spr[slot].alpha,
                   &s_spr[slot].w, &s_spr[slot].h)) {
        s_spr[slot].used = 1;
        s_spr[slot].pos = pos;
        xmemcpy(s_spr[slot].name, name, xstrlen(name) + 1);
    }
}

static void load_font(void)
{
    uint32_t got, off, i, bpr;
    s_font_w = 0;
    got = hb_fs_read_chunked(DIR_BASE "/font.bin", s_font_file, FONT_FILE_MAX);
    if (got < 12 || s_font_file[0] != 'V' || s_font_file[1] != 'N' ||
        s_font_file[2] != 'F' || s_font_file[3] != 'N')
        return;
    if (s_font_file[6] != 1u) return;
    s_font_w = s_font_file[4];
    s_font_h = s_font_file[5];
    if (s_font_w == 0 || s_font_w > FONT_W_MAX || s_font_h == 0 ||
        s_font_h > FONT_H_MAX) { s_font_w = 0; return; }
    s_font_n = (uint16_t)((uint16_t)s_font_file[8] | ((uint16_t)s_font_file[9] << 8));
    if (s_font_n > FONT_GLYPH_MAX) { s_font_w = 0; return; }

    bpr = ((uint32_t)s_font_w + 7u) >> 3;
    off = 10;
    s_font_got = got;
    s_font_xor = 0;
    {   /* sample checksum: every 97th byte (coprime stride) */
        uint32_t k;
        for (k = 0; k + 4u <= got; k += 97u)
            s_font_xor ^= (uint32_t)s_font_file[k] |
                          ((uint32_t)s_font_file[k + 1u] << 8) |
                          ((uint32_t)s_font_file[k + 2u] << 16) |
                          ((uint32_t)s_font_file[k + 3u] << 24);
    }
    for (i = 0; i < s_font_n; i++) {
        if (off + 4u + (uint32_t)s_font_h * bpr > got) { s_font_w = 0; return; }
        s_font_cp[i] = (uint32_t)s_font_file[off] |
                       ((uint32_t)s_font_file[off + 1u] << 8) |
                       ((uint32_t)s_font_file[off + 2u] << 16) |
                       ((uint32_t)s_font_file[off + 3u] << 24);
        off += 4;
        s_font_off[i] = off;
        off += (uint32_t)s_font_h * bpr;
    }
}

static uint8_t load_script_chapter(uint16_t chapter)
{
    uint32_t got, ver;
    char path[32];
    s_script_len = 0;
    if (chapter == 0u) {
        xmemcpy(path, DIR_BASE "/script.bin", 20);
    } else {
        char num[5];
        num[0] = (char)('0' + ((chapter / 1000u) % 10u));
        num[1] = (char)('0' + ((chapter / 100u) % 10u));
        num[2] = (char)('0' + ((chapter / 10u) % 10u));
        num[3] = (char)('0' + (chapter % 10u));
        num[4] = 0;
        xmemcpy(path, DIR_BASE "/ch/", 12);
        path[12] = num[0]; path[13] = num[1];
        path[14] = num[2]; path[15] = num[3];
        path[16] = '.'; path[17] = 'b'; path[18] = 'i'; path[19] = 'n';
        path[20] = 0;
    }
    if (hb_fs_size(path) > SCRIPT_MAX) { rd_err(0xE9u); return 0; }
    got = hb_fs_read_chunked(path, s_script, SCRIPT_MAX);
    if (got < 16 || s_script[0] != 'V' || s_script[1] != 'N' ||
        s_script[2] != 'P' || s_script[3] != 'K')
        return 0;
    ver = (uint32_t)s_script[4] | ((uint32_t)s_script[5] << 8) |
          ((uint32_t)s_script[6] << 16) | ((uint32_t)s_script[7] << 24);
    if (ver != 1u) { rd_err(0xEAu); return 0; }
    s_labels_n = (uint32_t)s_script[8] | ((uint32_t)s_script[9] << 8) |
                 ((uint32_t)s_script[10] << 16) | ((uint32_t)s_script[11] << 24);
    if (12u + s_labels_n * 4u > got) { rd_err(0xEBu); return 0; }
    s_script_len = got;
    s_chapter = chapter;
    s_pc = 12u + s_labels_n * 4u;
    s_hist_n = 0;
    return 1;
}

static uint8_t load_script(void)
{
    return load_script_chapter(0u);
}

/* ---------------------------------------------------- manifests + unlocks -- */

static uint8_t s_cgidx_buf[8 + CG_MAX * (3 + SAVENAME_MAX)];
static uint8_t s_cg_grp[CG_MAX];
static uint8_t s_cg_tab;
static uint8_t s_flowidx_buf[8 + FLOW_MAX * (4 + 2 + NAME_MAX)];

static void load_cgidx(void)
{
    uint32_t got, off, i;
    uint16_t n;
    s_cg_n = 0;
    got = hb_fs_read_chunked(DIR_BASE "/cg.idx", s_cgidx_buf, sizeof s_cgidx_buf);
    if (got < 8 || s_cgidx_buf[0] != 'V' || s_cgidx_buf[1] != 'N' ||
        s_cgidx_buf[2] != 'C' || s_cgidx_buf[3] != 'G')
        return;
    n = (uint16_t)((uint16_t)s_cgidx_buf[6] | ((uint16_t)s_cgidx_buf[7] << 8));
    if (n > CG_MAX) n = CG_MAX;
    off = 8;
    for (i = 0; i < n && off + 2u <= got; i++) {
        uint16_t l = (uint16_t)((uint16_t)s_cgidx_buf[off] | ((uint16_t)s_cgidx_buf[off + 1u] << 8));
        uint16_t j;
        off += 2;
        s_cg_grp[i] = s_cgidx_buf[off];   /* route group */
        off += 1;
        if (l > SAVENAME_MAX - 1u) l = SAVENAME_MAX - 1u;
        if (off + l > got) break;
        for (j = 0; j < l; j++) s_cg_name[i][j] = (char)s_cgidx_buf[off + j];
        s_cg_name[i][l] = 0;
        off += l;
    }
    s_cg_n = (uint16_t)i;
}

static void load_flowidx(void)
{
    uint32_t got, off, i;
    uint16_t n;
    s_flow_n = 0;
    got = hb_fs_read_chunked(DIR_BASE "/flow.idx", s_flowidx_buf, sizeof s_flowidx_buf);
    if (got < 8 || s_flowidx_buf[0] != 'V' || s_flowidx_buf[1] != 'N' ||
        s_flowidx_buf[2] != 'F' || s_flowidx_buf[3] != 'L')
        return;
    n = (uint16_t)((uint16_t)s_flowidx_buf[6] | ((uint16_t)s_flowidx_buf[7] << 8));
    s_flow_ver = (uint16_t)((uint16_t)s_flowidx_buf[4] |
                            ((uint16_t)s_flowidx_buf[5] << 8));
    if (n > FLOW_MAX) n = FLOW_MAX;
    off = 8;
    for (i = 0; i < n && off + 6u <= got; i++) {
        uint16_t l;
        uint16_t j;
        s_flow_label[i] = (uint32_t)s_flowidx_buf[off] |
                          ((uint32_t)s_flowidx_buf[off + 1u] << 8) |
                          ((uint32_t)s_flowidx_buf[off + 2u] << 16) |
                          ((uint32_t)s_flowidx_buf[off + 3u] << 24);
        off += 4;
        l = (uint16_t)((uint16_t)s_flowidx_buf[off] | ((uint16_t)s_flowidx_buf[off + 1u] << 8));
        off += 2;
        if (l > NAME_MAX - 1u) l = NAME_MAX - 1u;
        if (off + l > got) break;
        for (j = 0; j < l; j++) s_flow_title[i][j] = (char)s_flowidx_buf[off + j];
        s_flow_title[i][l] = 0;
        off += l;
    }
    s_flow_n = (uint16_t)i;
}

static void seen_load(void)
{
    uint8_t buf[8 + sizeof s_cg_seen + sizeof s_flow_seen];
    uint32_t got, cb = (uint32_t)((s_cg_n + 7) / 8), fb = (uint32_t)((s_flow_n + 7) / 8);
    s_seen_dirty = 0;
    if (hb_fs_read(DIR_BASE "/seen.bin", buf, sizeof buf) < 8 ||
        buf[0] != 'V' || buf[1] != 'N' || buf[2] != 'S' || buf[3] != 'E')
        return;
    got = 8;
    if (got + cb <= sizeof buf) xmemcpy(s_cg_seen, buf + got, cb);
    got += cb;
    if (got + fb <= sizeof buf) xmemcpy(s_flow_seen, buf + got, fb);
}

static void seen_flush(void)
{
    uint8_t buf[8 + sizeof s_cg_seen + sizeof s_flow_seen];
    uint32_t cb = (uint32_t)((s_cg_n + 7) / 8), fb = (uint32_t)((s_flow_n + 7) / 8), i = 0;
    if (!s_seen_dirty) return;
    buf[i++] = 'V'; buf[i++] = 'N'; buf[i++] = 'S'; buf[i++] = 'E';
    buf[i++] = 1;
    buf[i++] = 0; buf[i++] = (uint8_t)(s_cg_n & 0xFF); buf[i++] = 0;
    xmemcpy(buf + i, s_cg_seen, cb);
    i += cb;
    xmemcpy(buf + i, s_flow_seen, fb);
    i += fb;
    hb_fs_write(DIR_BASE "/seen.bin", buf, i);
    s_seen_dirty = 0;
}

static void cg_unlock(const char *name)
{
    uint16_t i;
    for (i = 0; i < s_cg_n; i++) {
        if (str_eq(s_cg_name[i], name)) {
            if (!(s_cg_seen[i >> 3] & (1u << (i & 7)))) {
                s_cg_seen[i >> 3] |= (uint8_t)(1u << (i & 7));
                s_seen_dirty = 1;
            }
            return;
        }
    }
}

static void flow_visit(uint32_t label_id)
{
    uint16_t i;
    for (i = 0; i < s_flow_n; i++) {
        if (s_flow_label[i] == label_id) {
            if (!(s_flow_seen[i >> 3] & (1u << (i & 7)))) {
                s_flow_seen[i >> 3] |= (uint8_t)(1u << (i & 7));
                s_seen_dirty = 1;
            }
            return;
        }
    }
}

static uint8_t cg_is_seen(uint16_t i)
{
    if (s_set_unlock) return 1;
    return (uint8_t)((s_cg_seen[i >> 3] >> (i & 7)) & 1u);
}

static uint8_t flow_is_seen(uint16_t i)
{
    if (s_set_unlock) return 1;
    return (uint8_t)((s_flow_seen[i >> 3] >> (i & 7)) & 1u);
}

/* -------------------------------------------------------------- settings -- */

static void settings_load(void)
{
    uint8_t buf[10];
    s_set_speed = 2;
    s_set_auto = 0;
    s_set_volume = 6;
    s_set_unlock = 0;
    if (hb_fs_read(DIR_BASE "/settings.bin", buf, 10) >= 8 &&
        buf[0] == 'V' && buf[1] == 'N' && buf[2] == 'S' && buf[3] == 'T') {
        if (buf[5] <= 3) s_set_speed = buf[5];
        if (buf[6] <= 3) s_set_auto = buf[6];
        if (buf[7] <= 8) s_set_volume = buf[7];
        if (buf[9] & 1u) s_set_unlock = 1;
        if (buf[9] & 2u) s_set_voice = 1; else s_set_voice = 0;
    }
}

static void settings_save(void)
{
    uint8_t buf[10];
    buf[0] = 'V'; buf[1] = 'N'; buf[2] = 'S'; buf[3] = 'T';
    buf[4] = 2; buf[5] = s_set_speed; buf[6] = s_set_auto; buf[7] = s_set_volume;
    buf[8] = 0;
    buf[9] = (uint8_t)((s_set_unlock ? 1u : 0u) |
                     (s_set_voice ? 2u : 0u));
    hb_fs_write(DIR_BASE "/settings.bin", buf, 10);
}

static uint16_t text_delay_ticks(void)
{
    static const uint16_t speed[] = {0, 6, 2, 0};
    if (s_set_speed == 3) return 5;
    if (s_set_speed == 0) return 0;
    return speed[s_set_speed];
}

static uint16_t auto_delay_ticks(void)
{
    switch (s_set_auto) {
    case 1: return 40;
    case 2: return 80;
    case 3: return 150;
    default: return 0;
    }
}

/* ----------------------------------------------------------------- save ---- */

static void slot_path(uint8_t slot, char *out)
{
    static const char *const names[10] = {
        "/save0.bin", "/save1.bin", "/save2.bin", "/save3.bin",
        "/save4.bin", "/save5.bin", "/save6.bin", "/save7.bin",
        "/quick.bin", "/save.bin",
    };
    xmemcpy(out, DIR_BASE, 8);                       /* "/Data/vn" is 8   */
    xmemcpy(out + 8, names[slot], xstrlen(names[slot]) + 1);
}

static void fill_save_buf(uint8_t *buf, uint32_t code_off)
{
    uint32_t i = 0, v, k, j;

    v = SAVE_MAGIC;
    buf[i++] = (uint8_t)v; buf[i++] = (uint8_t)(v >> 8);
    buf[i++] = (uint8_t)(v >> 16); buf[i++] = (uint8_t)(v >> 24);
    v = SAVE_VERSION;
    buf[i++] = (uint8_t)v; buf[i++] = (uint8_t)(v >> 8);
    buf[i++] = (uint8_t)(v >> 16); buf[i++] = (uint8_t)(v >> 24);
    buf[i++] = (uint8_t)code_off; buf[i++] = (uint8_t)(code_off >> 8);
    buf[i++] = (uint8_t)(code_off >> 16); buf[i++] = (uint8_t)(code_off >> 24);
    buf[i++] = (uint8_t)s_chapter; buf[i++] = (uint8_t)(s_chapter >> 8);
    buf[i++] = 0; buf[i++] = 0;                      /* pad to 16          */

    for (k = 0; k < 3u; k++) {
        const char *src = "";
        if (k == 0u) src = s_cur_bg;
        else if (s_spr[k - 1u].used) src = s_spr[k - 1u].name;
        for (j = 0; j < SAVENAME_MAX && src[j]; j++) buf[i++] = (uint8_t)src[j];
        for (; j < SAVENAME_MAX; j++) buf[i++] = 0;
    }
    buf[i++] = s_spr[0].used ? s_spr[0].pos : POS_CENTER;
    buf[i++] = s_spr[1].used ? s_spr[1].pos : POS_CENTER;

    /* preview: current line, clipped to SAVENAME_MAX-1 bytes */
    for (j = 0; j + 1 < SAVENAME_MAX && j < s_say_len; j++)
        buf[i++] = (uint8_t)s_say_text[j];
    for (; j < SAVENAME_MAX; j++) buf[i++] = 0;
}

static void write_slot(uint8_t slot)
{
    uint8_t buf[SAVE_SIZE];
    char path[32];
    uint32_t j;
    fill_save_buf(buf, s_say_off);
    slot_path(slot, path);
    hb_fs_write(path, buf, SAVE_SIZE);
    /* refresh meta cache */
    s_slot_meta[slot] = 1;
    for (j = 0; j < SAVENAME_MAX; j++)
        s_slot_prev[slot][j] = (char)buf[16u + 3u * SAVENAME_MAX + 2u + j];
    s_slot_prev[slot][SAVENAME_MAX - 1] = 0;
}

/* read one slot into the s_save_* staging fields; 0 on failure */
static uint8_t read_slot_into(uint8_t slot)
{
    uint8_t buf[SAVE_SIZE];
    char path[32];
    uint32_t got, off, magic, ver;
    int k;

    slot_path(slot, path);
    got = hb_fs_read(path, buf, SAVE_SIZE);
    if (got < SAVE_SIZE) return 0;
    magic = (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) | ((uint32_t)buf[2] << 16) |
            ((uint32_t)buf[3] << 24);
    ver = (uint32_t)buf[4] | ((uint32_t)buf[5] << 8) | ((uint32_t)buf[6] << 16) |
          ((uint32_t)buf[7] << 24);
    if (magic != SAVE_MAGIC || ver != SAVE_VERSION) return 0;
    s_save_off = (uint32_t)buf[8] | ((uint32_t)buf[9] << 8) |
                 ((uint32_t)buf[10] << 16) | ((uint32_t)buf[11] << 24);
    s_save_ch = (uint16_t)buf[12] | ((uint16_t)buf[13] << 8);
    off = 16;
    for (k = 0; k < SAVENAME_MAX; k++) s_save_bg[k] = (char)buf[off + k];
    off += SAVENAME_MAX;
    for (k = 0; k < SPR_SLOTS; k++) {
        int j;
        for (j = 0; j < SAVENAME_MAX; j++) s_save_spr[k][j] = (char)buf[off + j];
        off += SAVENAME_MAX;
    }
    s_save_pos[0] = buf[off];
    s_save_pos[1] = buf[off + 1];
    s_save_bg[SAVENAME_MAX - 1] = 0;
    s_save_spr[0][SAVENAME_MAX - 1] = 0;
    s_save_spr[1][SAVENAME_MAX - 1] = 0;
    for (k = 0; k < SAVENAME_MAX; k++)
        s_slot_prev[slot][k] = (char)buf[16u + 3u * SAVENAME_MAX + 2u + k];
    s_slot_prev[slot][SAVENAME_MAX - 1] = 0;
    return 1;
}

static void load_slots_meta(void)
{
    uint8_t s;
    for (s = 0; s < 10u; s++) {
        uint32_t save_off_keep = s_save_off;
        s_slot_meta[s] = read_slot_into(s);
        s_save_off = save_off_keep;                    /* auto slot wins at boot */
    }
}

static void autosave(uint32_t code_off)
{
    uint8_t buf[SAVE_SIZE];
    char path[32];
    s_say_off = code_off;
    fill_save_buf(buf, code_off);
    slot_path(SLOT_AUTO, path);
    hb_fs_write(path, buf, SAVE_SIZE);
    s_slot_meta[SLOT_AUTO] = 1;
    {
        uint32_t j;
        for (j = 0; j < SAVENAME_MAX; j++)
            s_slot_prev[SLOT_AUTO][j] =
                (char)buf[16u + 3u * SAVENAME_MAX + 2u + j];
        s_slot_prev[SLOT_AUTO][SAVENAME_MAX - 1] = 0;
    }
    seen_flush();
}

static void save_load(void)
{
    s_save_valid = read_slot_into(SLOT_AUTO);
}

static void quick_save(void)
{
    write_slot(SLOT_QUICK);
    set_toast("\xE5\xB7\xB2\xE5\xBF\xAB\xE9\x80\x9F\xE5\xAD\x98\xE6\xA1\xA3");  /* 宸插揩閫熷瓨妗?*/
}

static uint8_t quick_load(void)
{
    if (!read_slot_into(SLOT_QUICK)) return 0;
    continue_game();
    set_toast("\xE5\xB7\xB2\xE5\xBF\xAB\xE9\x80\x9F\xE8\xAF\xBB\xE6\xA1\xA3");  /* 宸插揩閫熻妗?*/
    return 1;
}

/* ------------------------------------------------------------- layout ------ */

static int txt_cols(void)    { int c = s_font_w ? TXT_W / s_font_w : 25; return c < 1 ? 1 : c; }
static int txt_line_h(void)  { return s_font_h ? s_font_h + LINE_GAP : 12; }
static int txt_rows(void)
{
    int r = (BOX_Y + BOX_H - 6 - TXT_Y) / txt_line_h();
    return r < 1 ? 1 : r;
}

static uint16_t text_chars(void)
{
    const char *p = s_say_text;
    uint32_t n = 0;
    while (p < s_say_text + s_say_len) {
        const char *np;
        utf8_next(p, &np);
        p = np;
        n++;
    }
    return (uint16_t)n;
}

static uint16_t page_chars(void)
{
    const char *p = s_say_text;
    uint32_t skip = s_page_start, n = 0;
    int cols = txt_cols(), rows = txt_rows();
    int col = 0, row = 0;

    while (p < s_say_text + s_say_len && skip) {
        const char *np;
        utf8_next(p, &np);
        p = np;
        skip--;
    }
    while (p < s_say_text + s_say_len && row < rows) {
        if (*p == '\n') { p++; col = 0; row++; n++; }
        else {
            const char *np;
            utf8_next(p, &np);
            p = np;
            n++;
            if (++col >= cols) { col = 0; row++; }
        }
    }
    return (uint16_t)n;
}

/* ---------------------------------------------------------------- VM ------- */

static uint32_t label_offset(uint32_t id)
{
    if (id >= s_labels_n) return 0xFFFFFFFFu;
    return (uint32_t)s_script[12u + id * 4u] |
           ((uint32_t)s_script[13u + id * 4u] << 8) |
           ((uint32_t)s_script[14u + id * 4u] << 16) |
           ((uint32_t)s_script[15u + id * 4u] << 24);
}

/* dialogue rewind ring (蹇€€): offsets of recent SAY ops */
static void hist_push(uint32_t off)
{
    if (s_hist_n && s_hist[s_hist_n - 1u] == off) return;   /* replay dup */
    if (s_hist_n < HIST_MAX) s_hist[s_hist_n++] = off;
    else {
        uint8_t i;
        for (i = 1; i < HIST_MAX; i++) s_hist[i - 1u] = s_hist[i];
        s_hist[HIST_MAX - 1u] = off;
    }
}

static void rewind_line(void)
{
    if (s_hist_n < 2u) {
        set_toast("\xE5\xB7\xB2\xE5\x88\xB0\xE5\xBC\x80\xE5\xA4\xB4");  /* 宸插埌寮€澶?*/
        return;
    }
    s_hist_n--;
    s_pc = s_hist[s_hist_n - 1u];
    s_wait = 0;
    step();
}

static void step(void)
{
    if (s_mode == MODE_ERROR) return;
    for (;;) {
        uint32_t op_pc = s_pc;
        uint8_t op = rd_u8();
        if (s_mode == MODE_ERROR) return;
        switch (op) {
        case OP_END:
            s_skip = 0;
            s_mode = MODE_END;
            return;
        case OP_NEXT_CH: {
            /* advance to the next chapter volume, then keep executing */
            uint16_t next = rd_u16();
            if (!load_script_chapter(next)) { s_mode = MODE_ERROR; }
            return;
        }
        case OP_LABEL:
            flow_visit(rd_u32());
            break;
        case OP_BG: {
            char name[SAVENAME_MAX];
            rd_str(name, (uint16_t)sizeof name);
            set_bg(name);
            s_saw_bg = 1;
            break;
        }
        case OP_SPR: {
            uint8_t slot = rd_u8(), pos = rd_u8();
            char name[SAVENAME_MAX];
            rd_str(name, (uint16_t)sizeof name);
            set_spr(slot, pos, name);
            break;
        }
        case OP_SPRCLR: {
            uint8_t mask = rd_u8(), k;
            s_need_full = 1;
            for (k = 0; k < SPR_SLOTS; k++)
                if (mask & (1u << k)) s_spr[k].used = 0;
            break;
        }
        case OP_BGM: {
            /* Background music playback is DISABLED per request: the iPod
             * audio stack has a single static descriptor and bgm + voice
             * compete for it (overlap => device reboot). We still record the
             * track name so saves/scene state stay faithful, but nothing is
             * played for bgm. */
            char name[SAVENAME_MAX];
            rd_str(name, (uint16_t)sizeof name);
            if (name[0]) {
                uint32_t dl = xstrlen(name) + 1u;
                if (dl > sizeof s_last_bgm) dl = sizeof s_last_bgm;
                xmemcpy(s_last_bgm, name, dl - 1u);
                s_last_bgm[dl - 1u] = 0;
            }
            break;
        }
        case OP_VOICE: {
            /* u16 nlen, name[] 鈥?play /Data/vn/voice/<name>.wav for this
               line. VOICE runs right before its SAY, so s_voice_ms/t0
               still describe the PREVIOUS line here: if that clip is
               inside its window we stay silent (device API is
               single-shot); switching lines never chains audio. */
            char name[SAVENAME_MAX], path[96];
            uint32_t dl;
            rd_str(name, (uint16_t)sizeof name);
            s_voice_ticks = 0;
            if (!name[0]) break;
            if (audio_busy()) break;      /* never stack clips: reboots */
            if (s_ticks - s_voice_t0 < s_voice_ticks)
                break;                       /* previous clip still active */
            dl = xstrlen(name);
            if (14u + dl + 5u < sizeof path) {
                uint8_t wh[44];
                uint32_t got, rate, dsize;
                /* "/Data/vn/voice/" is 15 chars 鈥?the old 14 dropped the
                   trailing slash and glued the file name onto "voice". */
                xmemcpy(path, DIR_BASE "/voice/", 15);
                xmemcpy(path + 15, name, dl + 1);
                xmemcpy(path + 15 + dl, ".WAV", 5);   /* FS is case-sensitive */
                got = hb_fs_read(path, wh, 44);
                if (got != 44) {          /* case-insensitive fallback */
                    xmemcpy(path + 15 + dl, ".wav", 5);
                    got = hb_fs_read(path, wh, 44);
                    xmemcpy(path + 15 + dl, ".WAV", 5);
                }
                rate = got == 44 ? (uint32_t)wh[24] | ((uint32_t)wh[25] << 8)
                    | ((uint32_t)wh[26] << 16) | ((uint32_t)wh[27] << 24) : 0;
                dsize = got == 44 ? (uint32_t)wh[40] | ((uint32_t)wh[41] << 8)
                    | ((uint32_t)wh[42] << 16) | ((uint32_t)wh[43] << 24) : 0;
                if (got == 44) s_voice_play++;
                else if (s_voice_miss < 9999) s_voice_miss++;
                if (rate) {
                    /* 16-bit mono PCM: ms = bytes / (rate*2/1000) */
                    uint32_t ms = dsize / (rate / 500u ? rate / 500u : 1u);
                    if (ms > 60000u) ms = 60000u;
                    s_voice_ticks = ms / VOICE_TICK_MS + 1u;
                }
                s_voice_t0 = s_ticks;
                /* never play the same clip twice in a row: a re-entered step,
                   a rewind or a duplicated op would otherwise sound like the
                   same line doubling up */
                if (str_eq(name, s_last_voice)) break;
                if (s_set_voice && s_voice_ticks && !audio_busy()) {
                    /* queue it: plays at the next frame start, OUTSIDE the
                       touch-event context. Skipped while another clip is
                       still playing (the API is single-shot). */
                    queue_sound(path, 0x7FFFu, 2, (uint16_t)s_voice_ticks);
                    xmemcpy(s_last_voice, name, xstrlen(name) + 1);
                }
            }
            break;
        }
        case OP_CG: {
            char name[SAVENAME_MAX];
            rd_str(name, (uint16_t)sizeof name);
            set_cg(name);
            break;
        }
        case OP_SAY: {
            uint32_t off = op_pc, i;
            uint16_t n;
            rd_str(s_say_name, (uint16_t)sizeof s_say_name);
            n = rd_u16();
            if (n > TEXT_MAX - 1u) n = TEXT_MAX - 1u;
            for (i = 0; i < n; i++) s_say_text[i] = (char)rd_u8();
            s_say_text[n] = 0;
            s_say_len = n;
            s_have_name = s_say_name[0] != 0;
            s_page_start = 0;
            s_reveal = 0;
            s_auto_ticks = 0;
            s_say_off = off;
            hist_push(off);
            s_mode = MODE_SCENE;
            autosave(off);
            return;
        }
        case OP_CHOICE: {
            uint8_t n = rd_u8(), k;
            if (n > CHOICE_MAX) n = CHOICE_MAX;
            s_choice_n = n;
            for (k = 0; k < n; k++) {
                s_choice_label[k] = rd_u32();
                rd_str(s_choice_text[k], (uint16_t)sizeof s_choice_text[k]);
            }
            s_skip = 0;                      /* a choice always stops skip */
            s_mode = MODE_CHOICE;
            return;
        }
        case OP_JUMPX: {
            uint16_t ch = rd_u16();
            uint32_t lab = rd_u32();
            if (!load_script_chapter(ch)) { rd_err(0xE7u); return; }
            s_pc = label_offset(lab);
            if (s_pc >= s_script_len) { rd_err(0xE8u); return; }
            break;
        }
        case OP_JUMP: {
            uint32_t off = label_offset(rd_u32());
            if (off == 0xFFFFFFFFu || off >= s_script_len) { rd_err(0xE6u); return; }
            s_pc = off;
            break;
        }
        case OP_WAIT:
            s_wait = rd_u16();
            s_mode = MODE_SCENE;
            return;
        default:
            rd_err(0xE8u);
            return;
        }
    }
}

/* -------------------------------------------------------------- compose --- */

static void compose_bg_from(const uint16_t *src)
{
    int x, y;
    for (x = 0; x < SCR_W; x++) {
        uint32_t *p = lpx(x, 0);
        const uint16_t *s = src + x;
        for (y = 0; y < SCR_H; y++, p++, s += BG_W)
            *p = 0xFF000000u | rgb565_x(*s);
    }
}

/* repaint just the textbox region of the background (used every frame so the
   translucent box always blends over fresh pixels instead of darkening) */
static void compose_bg_region(const uint16_t *src, int rx, int ry, int rw, int rh)
{
    int x, y, y1 = ry + rh;
    if (ry < 0) ry = 0;
    if (y1 > SCR_H) y1 = SCR_H;
    if (rx < 0) { rw += rx; rx = 0; }
    if (rx + rw > SCR_W) rw = SCR_W - rx;
    if (rw <= 0 || y1 <= ry) return;
    for (x = rx; x < rx + rw; x++) {
        uint32_t *p = lpx(x, ry);
        const uint16_t *s = src + (long)ry * BG_W + x;
        for (y = ry; y < y1; y++, p++, s += BG_W)
            *p = 0xFF000000u | rgb565_x(*s);
    }
}

static void compose_bg(void)
{
    if (s_bg_ok) compose_bg_from(s_bg);
    else lfill_rect(0, 0, SCR_W, SCR_H, 0x101018u);
}

static void compose_sprites_clip(int ry0, int ry1)
{
    int s;
    if (ry1 < 0) ry1 = SCR_H;
    for (s = SPR_SLOTS - 1; s >= 0; s--) {
        int x, y, x0, y0, sy0, sy1;
        if (!s_spr[s].used) continue;
        y0 = SCR_H - s_spr[s].h - SPR_LIFT;   /* sit a little higher */
        if (s_spr[s].pos == POS_LEFT)      x0 = 64 + SPR_SHIFT;
        else if (s_spr[s].pos == POS_RIGHT) x0 = SCR_W - s_spr[s].w - 6 + SPR_SHIFT;
        else                                x0 = ((SCR_W - s_spr[s].w) >> 1) + SPR_SHIFT;
        sy0 = y0 < 0 ? -y0 : 0;
        sy1 = s_spr[s].h;
        if (y0 + sy1 > SCR_H) sy1 = SCR_H - y0;
        /* clip to the requested logical y band */
        if (y0 + sy0 < ry0) sy0 = ry0 - y0;
        if (y0 + sy1 > ry1) sy1 = ry1 - y0;
        if (sy1 <= sy0) continue;
        for (x = 0; x < s_spr[s].w; x++) {
            int xx = x0 + x;
            const uint8_t *ap;
            const uint16_t *cp;
            uint32_t *p;
            if (xx < 0 || xx >= SCR_W) continue;
            ap = s_spr[s].alpha + (long)sy0 * s_spr[s].w + x;
            cp = s_spr[s].color + (long)sy0 * s_spr[s].w + x;
            p = lpx(xx, y0 + sy0);
            for (y = sy0; y < sy1; y++, p++, ap += s_spr[s].w,
                 cp += s_spr[s].w) {
                uint8_t a = *ap;
                uint32_t col;
                if (a == 0) continue;
                col = rgb565_x(*cp);
                if (a == 255) { p[0] = 0xFF000000u | col; continue; }
                {
                    uint32_t d = p[0], na = 255u - a;
                    p[0] = 0xFF000000u |
                        (((((col >> 16) & 0xFFu) * a +
                           (((d >> 16) & 0xFFu) * na)) >> 8) << 16) |
                        (((((col >> 8) & 0xFFu) * a +
                           (((d >> 8) & 0xFFu) * na)) >> 8) << 8) |
                        ((((col & 0xFFu) * a + ((d & 0xFFu) * na)) >> 8));
                }
            }
        }
    }
}

static void compose_sprites(void)
{
    compose_sprites_clip(0, SCR_H);
}

static void compose_text(void)
{
    int cols = txt_cols(), rows = txt_rows(), line_h = txt_line_h();
    uint32_t skip = s_page_start, drawn = 0;
    int col = 0, row = 0;
    const char *p = s_say_text;

    while (p < s_say_text + s_say_len && skip) {
        const char *np;
        utf8_next(p, &np);
        p = np;
        skip--;
    }
    while (p < s_say_text + s_say_len && row < rows) {
        if (*p == '\n') {
            p++;
            col = 0; row++; drawn++;
        } else {
            const char *np;
            uint32_t cp = utf8_next(p, &np);
            p = np;
            if (drawn < s_reveal && cp != ' ')
                draw_glyph(TXT_X + col * s_font_w, TXT_Y + row * line_h, cp, 0xF5F6FAu);
            drawn++;
            if (++col >= cols) { col = 0; row++; }
        }
    }
}

static void draw_arrow(void)               /* next-page marker, bottom right */
{
    int cx = BOX_X + BOX_W - 18, cy = BOX_Y + BOX_H - 12, y;
    for (y = 0; y < 6; y++)
        lfill_rect(cx - y, cy + y, 1 + 2 * y, 1, 0xFFD166u);
}

static void draw_nameplate(const char *name)
{
    int w = (int)(str_chars(name) * s_font_w) + 16;
    lfill_rect(BOX_X + 8, BOX_Y - s_font_h - 6, w, s_font_h + 8, 0x2B2D42u);
    lrect_outline(BOX_X + 8, BOX_Y - s_font_h - 6, w, s_font_h + 8, 1, 0xE07A5Fu);
    draw_str(name, BOX_X + 16, BOX_Y - s_font_h, 0xFFD166u);
}

static void compose_textbox(void)
{
    /* scene shortcut buttons: jump to the next background / next choice */
    if (s_mode == MODE_SCENE) {
        lfill_rect(4, 2, 58, 16, 0x1D3557u);
        lfill_rect(64, 2, 58, 16, 0x1D3557u);
        if (s_font_w) {
            draw_str("åºæ¯", 12, 0, 0xF1FAEEu);
            draw_str("éé¡¹", 72, 0, 0xF1FAEEu);
        }
    }
    /* gradient: strong at the bottom, fading toward the top (鍘熺増椋?.
       First rebuild the box region's base pixels (bg + sprites) so the
       translucent gradient never compounds frame over frame. */
    int y;
    if (s_bg_ok)
        compose_bg_region(s_bg, BOX_X, BOX_Y, BOX_W, BOX_H);
    else
        lfill_rect(BOX_X, BOX_Y, BOX_W, BOX_H, 0x101018u);
    compose_sprites_clip(BOX_Y, BOX_Y + BOX_H);
    for (y = 0; y < BOX_H; y++) {
        int a = 40 + (140 * (BOX_H - 1 - y)) / (BOX_H - 1);  /* 40..180 */
        ldim_rect(BOX_X, BOX_Y + y, BOX_W, 1, (uint8_t)a);
    }
    lrect_outline(BOX_X, BOX_Y, BOX_W, BOX_H, 1, 0x3A86FFu);
    if (s_have_name && s_font_w)
        draw_nameplate(s_say_name);
    /* voice progress bar: small strip along the textbox bottom (鍘熺増椋? */
    if (s_voice_ticks) {
        uint32_t el = s_ticks - s_voice_t0;
        uint32_t frac = el >= s_voice_ticks ? 8 :
            el * 8u / s_voice_ticks;
        int bw = (BOX_W - 24) / 8 * (int)frac;
        lfill_rect(BOX_X + 12, BOX_Y + BOX_H - 5, BOX_W - 24, 2, 0x2A2D3Au);
        if (bw > 0)
            lfill_rect(BOX_X + 12, BOX_Y + BOX_H - 5, bw, 2, 0xE8998Du);
    }
}

static void draw_button(int x, int y, int w, int h, const char *cjk,
                        const char *ascii, uint32_t border)
{
    lfill_rect(x, y, w, h, 0x1D3557u);
    lrect_outline(x, y, w, h, 2, border);
    if (s_font_w)
        draw_str_center(cjk, x + w / 2, y + (h - s_font_h) / 2, 0xF1FAEEu);
    else {
        int tw = ascii8_w(ascii, 2);
        draw_ascii8(x + (w - tw) / 2, y + (h - 16) / 2, ascii, 2, 0xF1FAEEu);
    }
}

/* ---------------------------------------------------------------- title ---- */

/* Yuzusoft-style menu item: translucent dark band, accent bar on the
 * left edge, white label; warm accent when "active". */
static void draw_menu_item(int x, int y, int w, int h, const char *cjk,
                           const char *ascii, uint8_t active)
{
    /* original layout: small icon block, CJK label, tiny English caption */
    uint32_t accent = active ? 0xE8998Du : 0xB0526Du;
    uint32_t text = active ? 0xFFE9E4u : 0xF5F2F0u;
    ldim_rect(x, y, w, h, 150);
    lfill_rect(x, y, 2, h, accent);
    /* icon: a small square glyph to the left of the label */
    lfill_rect(x + 8, y + h / 2 - 5, 9, 9, accent);
    lrect_outline(x + 8, y + h / 2 - 5, 9, 9, 1, 0xF5F2F0u);
    if (s_font_w) {
        draw_str(cjk, x + 22, y + 2, text);
        draw_ascii8(x + 22, y + h - 9, ascii, 1, 0xC9BEB8u);
    } else {
        int tw = ascii8_w(ascii, 1);
        draw_ascii8(x + (w - tw) / 2, y + (h - 8) / 2, ascii, 1, text);
    }
}

static void draw_title_bg(void)
{
    uint16_t w = 0, h = 0;
    if (load_asset("ui", "title", BG_W, BG_H, 0, s_bg, 0, &w, &h) &&
        w == BG_W && h == BG_H) {
        compose_bg_from(s_bg);
        return;
    }
    /* fallback: Yuzusoft-ish night gradient + petals dots */
    int x, y;
    for (y = 0; y < SCR_H; y++) {
        uint32_t r = 0x10 + (0x2A * y / SCR_H);
        uint32_t g = 0x14 + (0x1E * y / SCR_H);
        uint32_t b = 0x28 + (0x46 * y / SCR_H);
        for (x = 0; x < SCR_W; x++)
            lpx(x, y)[0] = 0xFF000000u | (r << 16) | (g << 8) | b;
    }
    for (x = 0; x < 40; x++) {
        int px = (x * 97) % SCR_W, py = (x * 53) % SCR_H;
        lfill_rect(px, py, 2, 2, 0xE8C6C6u);
    }
}

/* title menu occupies the LEFT column, like the original game */
#define TITLE_X   14
#define TITLE_W   118
#define TITLE_Y0  38
#define TITLE_DY  27
#define TITLE_N   7

static void compose_title(void)
{
    static const char *const cjk[TITLE_N] = {
        "\xE5\xBC\x80\xE5\xA7\x8B\xE6\xB8\xB8\xE6\x88\x8F",        /* 寮€濮嬫父鎴?*/
        "\xE7\xBB\xA7\xE7\xBB\xAD\xE6\xB8\xB8\xE6\x88\x8F",        /* 缁х画娓告垙 */
        "\xE7\xAB\xA0\xE8\x8A\x82\xE9\x80\x89\xE6\x8B\xA9",        /* 绔犺妭閫夋嫨 */
        "\xE8\xAF\xBB\xE6\xA1\xA3",                                /* 璇绘。     */
        "CG\xE9\x89\xB4\xE8\xB5\x8F",                              /* CG閴磋祻   */
        "\xE6\xB5\x81\xE7\xA8\x8B\xE5\x9B\xBE",                    /* 娴佺▼鍥?  */
        "\xE8\xAE\xBE\xE7\xBD\xAE",                                /* 璁剧疆     */
    };
    static const char *const asc[TITLE_N] = {
        "START", "CONTINUE", "CHAPTERS", "LOAD", "CG MODE", "FLOW", "CONFIG",
    };
    int i;
    draw_title_bg();
    for (i = 0; i < TITLE_N; i++) {
        if (i == 1 && !s_save_valid) {                     /* no auto save */
            draw_menu_item(TITLE_X, TITLE_Y0 + i * TITLE_DY, TITLE_W, 26,
                           "\xE7\xBB\xA7\xE7\xBB\xAD\xE6\xB8\xB8\xE6\x88\x8F",
                           "CONTINUE", 0);
            continue;
        }
        draw_menu_item(TITLE_X, TITLE_Y0 + i * TITLE_DY, TITLE_W, 26,
                       cjk[i], asc[i], (uint8_t)(i == 0));
    }
    if (!s_font_w) {
        int w = ascii8_w("SENREN*BANKA", 2);
        draw_ascii8((SCR_W - w) / 2, 196, "SENREN*BANKA", 2, 0xF1FAEEu);
    }
}

static void title_hit(int lx, int ly)
{
    int i;
    if (lx < TITLE_X || lx >= TITLE_X + TITLE_W) return;
    for (i = 0; i < TITLE_N; i++) {
        int y0 = TITLE_Y0 + i * TITLE_DY;
        if (ly < y0 || ly >= y0 + 26) continue;
        switch (i) {
        case 0: start_new_game(); return;
        case 1: if (s_save_valid) {
                    save_load();                     /* re-read latest auto */
                    if (s_save_valid) continue_game();
                } return;
        case 2: if (s_chsel_n) { s_mode = MODE_CHSEL; s_chsel_top = 0; }
                return;
        case 3: s_slot_pick = MODE_LOAD; s_ret_mode = MODE_TITLE;
                s_mode = MODE_SAVELOAD; return;
        case 4: s_mode = MODE_GALLERY; s_cg_page = 0; return;
        case 5: s_mode = MODE_FLOW; s_flow_top = 0; return;
        case 6: s_ret_mode = MODE_TITLE; s_mode = MODE_SETTINGS; return;
        }
    }
}

/* --------------------------------------------------------------- choices --- */

static void compose_choice(void)
{
    int i, n = s_choice_n, bh = 32, gap = 8;
    int y0 = (SCR_H - n * (bh + gap)) / 2 + 10;
    ldim_rect(0, 0, SCR_W, SCR_H, 90);
    for (i = 0; i < n; i++)
        draw_button(66, y0 + i * (bh + gap), 300, bh, s_choice_text[i], "", 0xE07A5Fu);
}

static void choice_hit(int lx, int ly)
{
    int i, n = s_choice_n, bh = 32, gap = 8;
    int y0 = (SCR_H - n * (bh + gap)) / 2 + 10;
    for (i = 0; i < n; i++) {
        if (lx >= 66 && lx < 366 && ly >= y0 + i * (bh + gap) &&
            ly < y0 + i * (bh + gap) + bh) {
            uint32_t off = label_offset(s_choice_label[i]);
            if (off != 0xFFFFFFFFu && off < s_script_len) {
                s_pc = off;
                step();
            }
            return;
        }
    }
}

/* --------------------------------------------------------- in-game menu ---- */

/* 12 items, two columns of six (system | save & modes) */
static const char *const IG_ITEMS_CJK[12] = {
    "\xE8\xBF\x94\xE5\x9B\x9E\xE6\xB8\xB8\xE6\x88\x8F",            /* 杩斿洖娓告垙 */
    "\xE8\x87\xAA\xE5\x8A\xA8\xE6\x92\xAD\xE6\x94\xBE",            /* 鑷姩鎾斁 */
    "\xE5\xBF\xAB\xE8\xBF\x9B\xE6\xA8\xA1\xE5\xBC\x8F",            /* 蹇繘妯″紡 */
    "\xE4\xB8\x8A\xE4\xB8\x80\xE5\x8F\xA5",                        /* 涓婁竴鍙?  */
    "\xE8\xAE\xBE\xE7\xBD\xAE",                                    /* 璁剧疆     */
    "\xE8\xBF\x94\xE5\x9B\x9E\xE6\xA0\x87\xE9\xA2\x98",            /* 杩斿洖鏍囬 */
    "\xE5\xAD\x98\xE6\xA1\xA3",                                    /* 瀛樻。     */
    "\xE8\xAF\xBB\xE6\xA1\xA3",                                    /* 璇绘。     */
    "\xE5\xBF\xAB\xE9\x80\x9F\xE5\xAD\x98\xE6\xA1\xA3",            /* 蹇€熷瓨妗?*/
    "\xE5\xBF\xAB\xE9\x80\x9F\xE8\xAF\xBB\xE6\xA1\xA3",            /* 蹇€熻妗?*/
    "CG\xE9\x89\xB4\xE8\xB5\x8F",                                  /* CG閴磋祻   */
    "\xE6\xB5\x81\xE7\xA8\x8B\xE5\x9B\xBE",                        /* 娴佺▼鍥?  */
};
static const char *const IG_ITEMS_ASC[12] = {
    "RESUME", "AUTO", "SKIP", "PREV", "CONFIG", "TITLE",
    "SAVE", "LOAD", "QSAVE", "QLOAD", "CG MODE", "FLOW",
};
#define IG_IX(i)   ((i) < 6 ? 24 : 222)
#define IG_IY(i)   (22 + ((i) % 6) * 35)
#define IG_IW      186

static void compose_igmenu(void)
{
    int i;
    compose_bg();
    compose_sprites();
    ldim_rect(0, 0, SCR_W, SCR_H, 80);
    for (i = 0; i < 12; i++) {
        uint8_t active = 0;
        if (i == 1 && s_set_auto) active = 1;              /* auto on   */
        if (i == 2 && s_skip) active = 1;                  /* skip on   */
        draw_menu_item(IG_IX(i), IG_IY(i), IG_IW, 28,
                       IG_ITEMS_CJK[i], IG_ITEMS_ASC[i], active);
    }
}

static void igmenu_hit(int lx, int ly)
{
    int i = -1, k;
    for (k = 0; k < 12; k++) {
        if (lx >= IG_IX(k) && lx < IG_IX(k) + IG_IW &&
            ly >= IG_IY(k) && ly < IG_IY(k) + 28) { i = k; break; }
    }
    if (i < 0) return;                                     /* tap gap: ignore */
    switch (i) {
    case 0: s_mode = MODE_SCENE; break;
    case 1: s_set_auto = (uint8_t)((s_set_auto + 1) & 3); settings_save(); break;
    case 2: s_skip ^= 1u;
            s_set_auto = 0;
            if (s_skip) set_toast("\xE5\xBF\xAB\xE8\xBF\x9B\xE4\xB8\xAD");  /* 蹇繘涓?*/
            s_mode = MODE_SCENE;
            break;
    case 3: s_mode = MODE_SCENE; rewind_line(); break;
    case 4: s_ret_mode = MODE_SCENE; s_mode = MODE_SETTINGS; break;
    case 5: seen_flush(); s_mode = MODE_TITLE; break;
    case 6: s_slot_pick = MODE_SAVE; s_ret_mode = MODE_SCENE;
            s_mode = MODE_SAVELOAD; break;
    case 7: s_slot_pick = MODE_LOAD; s_ret_mode = MODE_SCENE;
            s_mode = MODE_SAVELOAD; break;
    case 8: quick_save(); s_mode = MODE_SCENE; break;
    case 9: if (!quick_load()) set_toast("\xE6\x97\xA0\xE5\xBF\xAB\xE9\x80\x9F\xE5\xAD\x98\xE6\xA1\xA3");  /* 鏃犲揩閫熷瓨妗?*/
            break;
    case 10: s_mode = MODE_GALLERY; s_cg_page = 0; break;
    case 11: s_mode = MODE_FLOW; s_flow_top = 0; break;
    default: break;
    }
}

/* ------------------------------------------------------- save/load picker -- */

static void compose_saveload(void)
{
    static const char *save_t = "\xE5\xAD\x98\xE6\xA1\xA3";       /* 瀛樻。 */
    static const char *load_t = "\xE8\xAF\xBB\xE6\xA1\xA3";       /* 璇绘。 */
    static const char *empty  = "--- \xE7\xA9\xBA ---";           /* 绌?  */
    int i;
    lfill_rect(0, 0, SCR_W, SCR_H, 0x141021u);
    if (s_font_w)
        draw_str(s_slot_pick == MODE_SAVE ? save_t : load_t, 14, 6, 0xF1FAEEu);
    else
        draw_ascii8(14, 8, s_slot_pick == MODE_SAVE ? "SAVE" : "LOAD", 2,
                    0xF1FAEEu);
    for (i = 0; i < SAVE_SLOTS; i++) {
        int y = 26 + i * 20;
        char no[4];
        no[0] = (char)('1' + i); no[1] = 0;
        lfill_rect(10, y, 412, 18, s_slot_meta[i] ? 0x2A2438u : 0x1B1826u);
        lfill_rect(10, y, 3, 18, s_slot_meta[i] ? 0xB0526Du : 0x3A3348u);
        draw_ascii8(18, y + 5, no, 1, 0xF1FAEEu);
        if (s_font_w) {
            const char *prev = s_slot_prev[i];
            if (!s_slot_meta[i]) prev = empty;
            draw_str(prev, 34, y + (18 - s_font_h) / 2, 0xD8D2DCu);
        } else if (s_slot_meta[i]) {
            draw_ascii8(34, y + 5, "SAVED", 1, 0xD8D2DCu);
        }
    }
    /* quick + auto rows */
    {
        static const char *qc = "\xE5\xBF\xAB\xE9\x80\x9F";       /* 蹇€?*/
        static const char *ac = "\xE8\x87\xAA\xE5\x8A\xA8";       /* 鑷姩 */
        int yq = 26 + SAVE_SLOTS * 20, ya = yq + 20, k;
        const char *rows[2];
        uint8_t have[2];
        rows[0] = s_slot_prev[SLOT_QUICK]; have[0] = s_slot_meta[SLOT_QUICK];
        rows[1] = s_slot_prev[SLOT_AUTO];  have[1] = s_slot_meta[SLOT_AUTO];
        for (k = 0; k < 2; k++) {
            int y = k ? ya : yq;
            lfill_rect(10, y, 412, 18, have[k] ? 0x2A2438u : 0x1B1826u);
            lfill_rect(10, y, 3, 18, have[k] ? 0xE8998Du : 0x3A3348u);
            if (s_font_w) {
                draw_str(k ? ac : qc, 18, y + (18 - s_font_h) / 2, 0xF1FAEEu);
                if (have[k]) draw_str(rows[k], 52, y + (18 - s_font_h) / 2,
                                      0xD8D2DCu);
            } else {
                draw_ascii8(18, y + 5, k ? "AUTO" : "QUICK", 1, 0xF1FAEEu);
                if (have[k]) draw_ascii8(64, y + 5, "SAVED", 1, 0xD8D2DCu);
            }
        }
    }
}

static void saveload_hit(int lx, int ly)
{
    int i;
    if (ly >= 26 && ly < 26 + SAVE_SLOTS * 20) {
        i = (ly - 26) / 20;
        if (lx < 10 || lx >= 422) return;
        if (s_slot_pick == MODE_SAVE) {
            write_slot((uint8_t)i);
            set_toast("\xE5\xB7\xB2\xE4\xBF\x9D\xE5\xAD\x98");   /* 宸蹭繚瀛?*/
            s_mode = s_ret_mode;
        } else if (s_slot_meta[i]) {
            if (read_slot_into((uint8_t)i)) {
                continue_game();
                set_toast("\xE5\xB7\xB2\xE8\xAF\xBB\xE6\xA1\xA3");  /* 宸茶妗?*/
            }
        } else {
            set_toast("\xE7\xA9\xBA\xE6\xA7\xBD\xE4\xBD\x8D");    /* 绌烘Ы浣?*/
        }
        return;
    }
    {
        int yq = 26 + SAVE_SLOTS * 20;
        if (lx < 10 || lx >= 422) return;
        if (ly >= yq && ly < yq + 20) {                    /* quick row  */
            if (s_slot_pick == MODE_SAVE) { quick_save(); s_mode = s_ret_mode; }
            else if (!quick_load())
                set_toast("\xE6\x97\xA0\xE5\xBF\xAB\xE9\x80\x9F\xE5\xAD\x98\xE6\xA1\xA3");
        } else if (ly >= yq + 20 && ly < yq + 40) {         /* auto row   */
            if (s_slot_pick == MODE_LOAD && s_slot_meta[SLOT_AUTO]) {
                save_load();                                /* latest auto */
                if (s_save_valid) {
                    continue_game();
                    set_toast("\xE5\xB7\xB2\xE8\xAF\xBB\xE6\xA1\xA3");
                }
            }
        }
    }
}

/* --------------------------------------------------------------- gallery --- */

#define CG_COLS 4
#define CG_ROWS 2
#define CG_PAGE (CG_COLS * CG_ROWS)

static uint16_t s_thumb_cache[CG_PAGE][THUMB_PX];  /* decoded page thumbs   */
static uint8_t  s_thumb_key[CG_PAGE];              /* valid flag per cell   */
static int16_t  s_thumb_page = -1;                 /* which page is cached  */
static int16_t  s_cg_cache = -1;                   /* cgview: loaded index  */

static void gallery_cache_page(void)
{
    int i;
    if (s_thumb_page == (int16_t)s_cg_page) return;
    s_thumb_page = (int16_t)s_cg_page;
    for (i = 0; i < CG_PAGE; i++)
        s_thumb_key[i] = 0;
    for (i = 0; i < CG_PAGE; i++) {
        uint16_t idx = (uint16_t)(s_cg_page * CG_PAGE + i);
        uint16_t w = 0, h = 0;
        if (idx >= s_cg_n) break;
        if (!cg_is_seen(idx)) continue;
        if (load_asset("cgt", s_cg_name[idx], THUMB_W, THUMB_H, 0,
                       s_thumb, 0, &w, &h) && w == THUMB_W && h == THUMB_H) {
            xmemcpy(s_thumb_cache[i], s_thumb, (uint32_t)THUMB_PX * 2u);
            s_thumb_key[i] = 1;
        }
    }
}

static void compose_gallery(void)
{
    int i;
    uint16_t pages = (uint16_t)((s_cg_n + CG_PAGE - 1) / CG_PAGE);
    lfill_rect(0, 0, SCR_W, SCR_H, 0x0B132Bu);
    if (s_font_w)
        draw_str("CG\xE9\x89\xB4\xE8\xB5\x8F", 12, 6, 0xF1FAEEu);
    else
        draw_ascii8(12, 8, "CG MODE", 2, 0xF1FAEEu);
    gallery_cache_page();                     /* disk reads only on page flip */
    for (i = 0; i < CG_PAGE; i++) {
        uint16_t idx = (uint16_t)(s_cg_page * CG_PAGE + i);
        int gx = 14 + (i % CG_COLS) * (THUMB_W + 16);
        int gy = 40 + (i / CG_COLS) * (THUMB_H + 18);
        if (idx >= s_cg_n) break;
        lfill_rect(gx, gy, THUMB_W, THUMB_H, 0x1D3557u);
        if (cg_is_seen(idx)) {
            if (s_thumb_key[i]) {
                int x, y;
                for (y = 0; y < THUMB_H; y++)
                    for (x = 0; x < THUMB_W; x++)
                        lpx(gx + x, gy + y)[0] =
                            0xFF000000u |
                            rgb565_x(s_thumb_cache[i][(long)y * THUMB_W + x]);
            }
            lrect_outline(gx, gy, THUMB_W, THUMB_H, 1, 0x457B9Du);
        } else {
            lrect_outline(gx, gy, THUMB_W, THUMB_H, 1, 0x30343Bu);
            if (s_font_w)
                draw_str_center("?", gx + THUMB_W / 2, gy + (THUMB_H - s_font_h) / 2,
                                0x50555Eu);
        }
    }
    /* pager */
    lfill_rect(12, SCR_H - 22, 200, 18, 0x0B132Bu);
    if (s_font_w) {
        char buf[NAME_MAX];
        uint32_t k = 0;
        const char *p1 = "\xE9\xA1\xB5 ";                      /* 椤?*/
        while (*p1 && k < NAME_MAX - 12) buf[k++] = *p1++;
        buf[k++] = '1' + (char)(s_cg_page % 10);
        if (pages > 1) { buf[k++] = '/'; buf[k++] = '1' + (char)((pages - 1) % 10); }
        buf[k] = 0;
        draw_str(buf, 12, SCR_H - 20, 0x8D99Aeu);
    }
    draw_ascii8(SCR_W - 130, SCR_H - 20, "tap=page  vol=back", 1, 0x8D99Aeu);
}

static void gallery_hit(int lx, int ly)
{
    uint16_t pages = (uint16_t)((s_cg_n + CG_PAGE - 1) / CG_PAGE);
    int i;
    if (ly < 18) {                       /* route tabs */
        int t = (lx - 2) / 61;
        uint16_t k;
        if (t < 0 || t > 6) return;
        for (k = 0; k < s_cg_n; k++) {
            if (s_cg_grp[k] == (uint8_t)t) {
                s_cg_tab = (uint8_t)t;
                s_cg_page = (uint16_t)(k / CG_PAGE);
                return;
            }
        }
        return;
    }
    for (i = 0; i < CG_PAGE; i++) {
        uint16_t idx = (uint16_t)(s_cg_page * CG_PAGE + i);
        int gx = 14 + (i % CG_COLS) * (THUMB_W + 16);
        int gy = 40 + (i / CG_COLS) * (THUMB_H + 18);
        if (idx >= s_cg_n) break;
        if (lx >= gx && lx < gx + THUMB_W && ly >= gy && ly < gy + THUMB_H) {
            if (cg_is_seen(idx)) {
                s_cg_view = idx;
                s_mode = MODE_CGVIEW;
            }
            return;
        }
    }
    s_cg_page = (uint16_t)((s_cg_page + 1) % (pages ? pages : 1));
}

static void compose_cgview(void)
{
    uint16_t w = 0, h = 0;
    if (s_cg_cache != (int16_t)s_cg_view) {   /* load only when the CG changes */
        s_cg_cache = -1;
        if (load_asset("cg", s_cg_name[s_cg_view], BG_W, BG_H, 0, s_bg, 0,
                       &w, &h) && w == BG_W && h == BG_H)
            s_cg_cache = (int16_t)s_cg_view;  /* s_bg now holds this CG */
    }
    if (s_cg_cache == (int16_t)s_cg_view)
        compose_bg_from(s_bg);
    else
        lfill_rect(0, 0, SCR_W, SCR_H, 0x101018u);
    draw_ascii8(8, 6, "vol=back", 1, 0xAFB2B6u);
}

static void cgview_hit(int lx, int ly)
{
    uint16_t i;
    /* tap right/left cycles through UNLOCKED CGs */
    for (i = 1; i < s_cg_n; i++) {
        uint16_t n = (uint16_t)((s_cg_view + (lx >= SCR_W / 2 ? i : s_cg_n - i)) % s_cg_n);
        if (cg_is_seen(n)) { s_cg_view = n; return; }
    }
}

/* ------------------------------------------------------------ flowchart ---- */

/* chart.idx ("VNCH" v2): one layout per route tab.
     4  "VNCH"
     2  u16 ver
     2  u16 n_routes
    12*n  route recs { u16 name_off, u16 name_len, u16 node_base,
                       u16 node_count, u16 edge_base, u16 edge_count }
    12*N  node recs  { i16 x, i16 y, u8 type, u8 route, u16 chapter,
                       u16 off, u16 len }
     4*E  edges      { u16 from, u16 to }   (global node indices)
          blob       utf-8 titles then route names                    */
#define CHART_MAX    24576u
#define CHART_HDR    8u
#define CHART_RREC   12u
#define CHART_NREC   12u
#define CHART_TABS   7
#define CHART_TABH   18
#define CHART_TOP    26
#define CHART_BOT    206
#define CHART_W      200          /* node box width, keep in sync with tool */
#define CHART_W_CH   420

static uint8_t  s_chart_buf[CHART_MAX];
static uint8_t  s_chart_ok;
static uint8_t  s_chart_route;
static uint16_t s_chart_nodes;
static uint16_t s_chart_edges;
static uint16_t s_chart_nroute;
static int16_t  s_chart_scroll[CHART_TABS];
static uint8_t  s_chart_started;
static int16_t  s_chart_dx;
static int16_t  s_dbg_lx, s_dbg_ly, s_dbg_moved;
static uint8_t  s_dbg_down, s_dbg_tab;
static int16_t  s_chart_drag;
static int16_t  s_chart_moved;
static int16_t  s_chart_tapx;
static int16_t  s_chart_tapy;
static uint32_t s_chart_node_off;
static uint32_t s_chart_edge_off;
static uint32_t s_chart_blob_off;

static uint16_t chart_u16(const uint8_t *q)
{
    return (uint16_t)((uint16_t)q[0] | ((uint16_t)q[1] << 8));
}

static uint8_t chart_load(void)
{
    uint32_t got;
    if (s_chart_ok) return 1;
    got = hb_fs_read_chunked(DIR_BASE "/chart.idx", s_chart_buf,
                             sizeof s_chart_buf);
    if (got < CHART_HDR || s_chart_buf[0] != 'V' || s_chart_buf[1] != 'N' ||
        s_chart_buf[2] != 'C' || s_chart_buf[3] != 'H')
        return 0;
    s_chart_nroute = chart_u16(s_chart_buf + 6);
    if (s_chart_nroute == 0 || s_chart_nroute > CHART_TABS) return 0;
    s_chart_nodes = 0;
    s_chart_edges = 0;
    {
        uint16_t r;
        for (r = 0; r < s_chart_nroute; r++) {
            const uint8_t *rec = s_chart_buf + CHART_HDR + (uint32_t)r * CHART_RREC;
            uint16_t nb = chart_u16(rec + 4);
            uint16_t nc = chart_u16(rec + 6);
            uint16_t eb = chart_u16(rec + 8);
            uint16_t ec = chart_u16(rec + 10);
            if (nb + nc > s_chart_nodes) s_chart_nodes = (uint16_t)(nb + nc);
            if (eb + ec > s_chart_edges) s_chart_edges = (uint16_t)(eb + ec);
        }
    }
    s_chart_node_off = CHART_HDR + (uint32_t)s_chart_nroute * CHART_RREC;
    s_chart_edge_off = s_chart_node_off + (uint32_t)s_chart_nodes * CHART_NREC;
    if (s_chart_edge_off + (uint32_t)s_chart_edges * 4u > got) return 0;
    s_chart_blob_off = s_chart_edge_off + (uint32_t)s_chart_edges * 4u;
    s_chart_ok = 1;
    s_chart_route = 0;
    {
        int i;
        for (i = 0; i < CHART_TABS; i++) s_chart_scroll[i] = 0;
    }
    return 1;
}

static const uint8_t *chart_rec(uint16_t i)
{
    return s_chart_buf + s_chart_node_off + (uint32_t)i * CHART_NREC;
}

static void chart_range(uint16_t *base, uint16_t *count)
{
    const uint8_t *rec = s_chart_buf + CHART_HDR +
                         (uint32_t)s_chart_route * CHART_RREC;
    if (base) *base = chart_u16(rec + 4);
    if (count) *count = chart_u16(rec + 6);
}

static void chart_erange(uint16_t *base, uint16_t *count)
{
    const uint8_t *rec = s_chart_buf + CHART_HDR +
                         (uint32_t)s_chart_route * CHART_RREC;
    if (base) *base = chart_u16(rec + 8);
    if (count) *count = chart_u16(rec + 10);
}

static void chart_route_name(uint8_t r, char *out, int maxcp)
{
    const uint8_t *rec = s_chart_buf + CHART_HDR + (uint32_t)r * CHART_RREC;
    uint16_t off = chart_u16(rec);
    uint16_t len = chart_u16(rec + 2);
    const char *b = (const char *)s_chart_buf + s_chart_blob_off + off;
    int i = 0, n = 0, cp = 0;
    while (i < (int)len && cp < maxcp) {
        unsigned char c = (unsigned char)b[i];
        int adv = (c >= 0xF0) ? 4 : (c >= 0xE0) ? 3 : (c >= 0xC0) ? 2 : 1;
        int k;
        if (i + adv > (int)len) break;
        for (k = 0; k < adv; k++) out[n++] = b[i + k];
        i += adv;
        cp++;
    }
    out[n] = 0;
}

static void chart_text(const uint8_t *rec, char *out, int maxcp)
{
    uint16_t off = chart_u16(rec + 8);
    uint16_t len = chart_u16(rec + 10);
    const char *b = (const char *)s_chart_buf + s_chart_blob_off + off;
    int i = 0, n = 0, cp = 0;
    while (i < (int)len && cp < maxcp) {
        unsigned char c = (unsigned char)b[i];
        int adv = (c >= 0xF0) ? 4 : (c >= 0xE0) ? 3 : (c >= 0xC0) ? 2 : 1;
        int k;
        if (i + adv > (int)len) break;
        for (k = 0; k < adv; k++) out[n++] = b[i + k];
        i += adv;
        cp++;
    }
    out[n] = 0;
}

static int16_t chart_max_scroll(void)
{
    uint16_t base, n, i;
    int maxy = 0;
    chart_range(&base, &n);
    for (i = 0; i < n; i++) {
        int y = (int)chart_u16(chart_rec((uint16_t)(base + i)) + 2) + 20;
        if (y > maxy) maxy = y;
    }
    return (int16_t)(maxy > (CHART_BOT - CHART_TOP) ? maxy - (CHART_BOT - CHART_TOP)
                                                   : 0);
}

static uint32_t chart_color(uint8_t type)
{
    switch (type) {
    case 0:  return 0xE8998Du;        /* chapter header */
    case 2:  return 0xFFD166u;        /* choice point   */
    case 3:  return 0x6FCF97u;        /* branch         */
    default: return 0x457B9Du;        /* scene          */
    }
}

static void compose_flow(void)
{
    uint16_t base, n, eb, ec, i;
    int16_t scroll;
    char buf[64];
    int t;

    lfill_rect(0, 0, SCR_W, SCR_H, 0x0B132Bu);
    if (!chart_load()) {
        draw_ascii8(12, 12, "no chart.idx", 2, 0xFF9A9Au);
        return;
    }
    scroll = s_chart_scroll[s_chart_route];
    if (scroll > chart_max_scroll()) {
        scroll = chart_max_scroll();
        s_chart_scroll[s_chart_route] = scroll;
    }

    /* route tabs */
    for (t = 0; t < (int)s_chart_nroute && t < CHART_TABS; t++) {
        int tx = 4 + t * 61, on = (t == (int)s_chart_route);
        chart_route_name((uint8_t)t, buf, 2);
        lfill_rect(tx, 2, 58, CHART_TABH, on ? 0xE8998Du : 0x1D3557u);
        lrect_outline(tx, 2, 58, CHART_TABH, 1, on ? 0xFFE9E4u : 0x457B9Du);
        if (s_font_w)
            draw_str(buf, tx + 6, 3, on ? 0x1B2433u : 0xF1FAEEu);
        else
            draw_ascii8(tx + 6, 5, buf, 1, on ? 0x1B2433u : 0xF1FAEEu);
    }

    chart_range(&base, &n);
    chart_erange(&eb, &ec);

    /* connectors */
    for (i = 0; i < ec; i++) {
        const uint8_t *e = s_chart_buf + s_chart_edge_off + (uint32_t)(eb + i) * 4u;
        uint16_t ai = chart_u16(e), bi = chart_u16(e + 2);
        const uint8_t *A, *B;
        int ax, ay, bx, by, k;
        if (ai >= s_chart_nodes || bi >= s_chart_nodes) continue;
        A = chart_rec(ai);
        B = chart_rec(bi);
        ax = (int)chart_u16(A) + 9;
        ay = (int)chart_u16(A + 2) + 18 + CHART_TOP - scroll;
        bx = (int)chart_u16(B) + 9;
        by = (int)chart_u16(B + 2) + CHART_TOP - scroll;
        if ((ay < CHART_TOP && by < CHART_TOP) ||
            (ay > CHART_BOT && by > CHART_BOT))
            continue;
        for (k = ay; k < by; k += 2) {
            if (k >= CHART_TOP && k < CHART_BOT && ax >= 0 && ax < SCR_W)
                lpx(ax, k)[0] = 0xFF3A4A66u;
        }
        {
            int x0 = ax < bx ? ax : bx, x1 = ax < bx ? bx : ax;
            for (k = x0; k <= x1; k += 2) {
                if (by >= CHART_TOP && by < CHART_BOT && k >= 0 && k < SCR_W)
                    lpx(k, by)[0] = 0xFF3A4A66u;
            }
        }
    }

    /* centre this route's graph: a narrow route should not hug the left edge */
    {
        int16_t right = 0;
        uint16_t k;
        for (k = 0; k < n; k++) {
            const uint8_t *rr = chart_rec((uint16_t)(base + k));
            int w2 = (rr[4] == 0) ? CHART_W_CH : CHART_W;
            int r2 = (int)chart_u16(rr) + w2;
            if (r2 > right) right = (int16_t)r2;
        }
        s_chart_dx = (right > 0 && right < SCR_W - 8)
                     ? (int16_t)((SCR_W - right) / 2) : 0;
    }

    /* node boxes */
    for (i = 0; i < n; i++) {
        const uint8_t *r = chart_rec((uint16_t)(base + i));
        int x = (int)chart_u16(r) + s_chart_dx;
        int y = (int)chart_u16(r + 2) + CHART_TOP - scroll;
        uint8_t type = r[4];
        int w = (type == 0) ? CHART_W_CH : CHART_W;
        uint32_t col = chart_color(type);
        if (y + 18 < CHART_TOP || y > CHART_BOT) continue;
        if (x < -w || x > SCR_W) continue;
        lfill_rect(x, y, w, 18, type == 0 ? 0x2A3A5Au : 0x1D3557u);
        lrect_outline(x, y, w, 18, 1, col);
        lfill_rect(x, y, 2, 18, col);
        chart_text(r, buf, (w - 12) / (s_font_w ? s_font_w : 8));
        if (s_font_w)
            draw_str(buf, x + 6, y + 1, 0xF1FAEEu);
        else
            draw_ascii8(x + 6, y + 2, buf, 1, 0xF1FAEEu);
    }
    /* paging buttons (drag scrolling is unusable on this touchscreen) */
    {
        int16_t mx = chart_max_scroll();
        int page = (CHART_BOT - CHART_TOP) - 26;
        int cur = s_chart_scroll[s_chart_route];
        int hw = SCR_W / 2;
        lfill_rect(2, CHART_BOT + 2, hw - 4, 12, cur > 0 ? 0x2A4A6Au : 0x1A2432u);
        lfill_rect(hw + 2, CHART_BOT + 2, hw - 4, 12,
                   cur < mx ? 0x2A4A6Au : 0x1A2432u);
        if (s_font_w) {
            draw_str("上页", 8, CHART_BOT + 2, cur > 0 ? 0xF1FAEEu : 0x55607Au);
            draw_str("下页", hw + 12, CHART_BOT + 2,
                     cur < mx ? 0xF1FAEEu : 0x55607Au);
        }
        /* position indicator: which screen of this route */
        (void)page;
    }
    (void)chart_max_scroll;
}

static void flow_hit(int lx, int ly)
{
    uint16_t base, n, i;
    int t;

    if (!s_chart_ok) return;
    /* paging strip at the bottom */
    if (ly >= CHART_BOT) {
        int mx = (int)chart_max_scroll();
        int page = (CHART_BOT - CHART_TOP) - 26;
        int v = (int)s_chart_scroll[s_chart_route];
        if (lx < SCR_W / 2) v -= page; else v += page;
        if (v < 0) v = 0;
        if (v > mx) v = mx;
        s_chart_scroll[s_chart_route] = (int16_t)v;
        return;
    }
    /* route tab? */
    if (ly < CHART_TABH + 2) {
        t = (lx - 4) / 61;
        if (t >= 0 && t < (int)s_chart_nroute && t != (int)s_chart_route) {
            s_chart_route = (uint8_t)t;
            s_need_full = 1;
        }
        return;
    }
    chart_range(&base, &n);
    for (i = 0; i < n; i++) {
        const uint8_t *r = chart_rec((uint16_t)(base + (n - 1 - i)));
        int x = (int)chart_u16(r) + s_chart_dx;
        int y = (int)chart_u16(r + 2) + CHART_TOP - s_chart_scroll[s_chart_route];
        int w = (r[4] == 0) ? CHART_W_CH : CHART_W;
        if (lx >= x && lx < x + w && ly >= y && ly < y + 18) {
            uint16_t ch = chart_u16(r + 6);
            if (load_script_chapter(ch)) {
                s_mode = MODE_SCENE;
                step();
            }
            return;
        }
    }
}

/* ------------------------------------------------------- chapter select --- */

/* chsel.idx: "VNCS" u16 ver(1) u16 n, then n x (u8 group, u16 chapter,
   u16 nlen, name[]). group: 0 鍏遍€?1 鑺充箖 2 鑼夊瓙 3 涓涢洦 4 钑惧 5 灏忔槬
   6 鑺﹁姳 鈥?matches the original game's route structure (scenelist) */
static const char *const CHSEL_GROUP_CJK[CHSEL_GROUP_N] = {
    "\xE5\x85\xB1\xE9\x80\x9A\xE7\xBA\xBF",                    /* 鍏遍€氱嚎 */
    "\xE8\x8A\xB3\xE4\xB9\x83\xE7\xBA\xBF",                    /* 鑺充箖绾?*/
    "\xE8\x8C\x89\xE5\xAD\x90\xE7\xBA\xBF",                    /* 鑼夊瓙绾?*/
    "\xE4\xB8\x9B\xE9\x9B\xA8\xE7\xBA\xBF",                    /* 涓涢洦绾?*/
    "\xE8\x95\xBE\xE5\xA8\x9C\xE7\xBA\xBF",                    /* 钑惧绾?*/
    "\xE5\xB0\x8F\xE6\x98\xA5\xE7\xBA\xBF",                    /* 灏忔槬绾?*/
    "\xE8\x8A\xA6\xE8\x8A\xB1\xE7\xBA\xBF",                    /* 鑺﹁姳绾?*/
};

static void load_chsel(void)
{
    static uint8_t buf[8 + CHSEL_MAX * (3 + NAME_MAX)];
    uint32_t got, off;
    uint16_t n, i;
    s_chsel_n = 0;
    got = hb_fs_read_chunked(DIR_BASE "/chsel.idx", buf, sizeof buf);
    if (got < 8 || buf[0] != 'V' || buf[1] != 'N' || buf[2] != 'C' ||
        buf[3] != 'S')
        return;
    n = (uint16_t)((uint16_t)buf[6] | ((uint16_t)buf[7] << 8));
    if (n > CHSEL_MAX) n = CHSEL_MAX;
    off = 8;
    for (i = 0; i < n && off + 5u <= got; i++) {
        uint16_t l, j;
        s_chsel_group[i] = buf[off] & 7u;
        s_chsel_ch[i] = (uint16_t)((uint16_t)buf[off + 1] |
                                   ((uint16_t)buf[off + 2] << 8));
        l = (uint16_t)((uint16_t)buf[off + 3] | ((uint16_t)buf[off + 4] << 8));
        off += 5;
        if (l > NAME_MAX - 1u) l = NAME_MAX - 1u;
        if (off + l > got) break;
        for (j = 0; j < l; j++)
            s_chsel_title[i][j] = (char)buf[off + j];
        s_chsel_title[i][l] = 0;
        off += l;
    }
    s_chsel_n = (uint16_t)i;
}

static void compose_chsel(void)
{
    int i, y = 30;
    uint8_t last_g = 0xFF;
    lfill_rect(0, 0, SCR_W, SCR_H, 0x0B132Bu);
    if (s_font_w)
        draw_str("\xE7\xAB\xA0\xE8\x8A\x82\xE9\x80\x89\xE6\x8B\xA9", 12, 6,
                 0xF1FAEEu);                                   /* 绔犺妭閫夋嫨 */
    else
        draw_ascii8(12, 8, "CHAPTERS", 2, 0xF1FAEEu);
    for (i = s_chsel_top; i < s_chsel_n && y < SCR_H - 24; i++) {
        if (s_chsel_group[i] != last_g && s_font_w) {
            if (s_chsel_group[i] < CHSEL_GROUP_N)
                draw_str(CHSEL_GROUP_CJK[s_chsel_group[i]], 20, y,
                         0xE8998Du);
            y += 18;
            last_g = s_chsel_group[i];
            if (y >= SCR_H - 24) break;
        }
        draw_button(20, y, 320, 20, s_chsel_title[i], "", 0x457B9Du);
        y += 22;
    }
    draw_ascii8(12, SCR_H - 18, "tap=go  tap-low=scrol  vol=back", 1,
                0x8D99Aeu);
}

static void chsel_hit(int lx, int ly)
{
    int i, y = 30;
    uint8_t last_g = 0xFF;
    if (ly >= SCR_H - 24) {                    /* bottom strip = scroll */
        s_chsel_top = (uint16_t)((s_chsel_top + 8) %
                                 (s_chsel_n ? s_chsel_n : 1));
        return;
    }
    for (i = s_chsel_top; i < s_chsel_n && y < SCR_H - 24; i++) {
        if (s_chsel_group[i] != last_g) {
            y += 18;
            last_g = s_chsel_group[i];
            if (y >= SCR_H - 24) break;
        }
        if (lx >= 20 && lx < 340 && ly >= y && ly < y + 20) {
            if (load_script_chapter(s_chsel_ch[i])) {
                s_mode = MODE_SCENE;
                step();
            }
            return;
        }
        y += 22;
    }
}

/* -------------------------------------------------------------- settings --- */

static const char *const SPEED_CJK[] = {"\xE7\x9E\xAC\xE9\x97\xB4", "\xE5\xBF\xAB", "\xE6\x99\xAE\xE9\x80\x9A", "\xE6\x85\xA2"};
static const char *const AUTO_CJK[] = {"\xE5\x85\xB3", "\xE5\xBF\xAB", "\xE6\x99\xAE\xE9\x80\x9A", "\xE6\x85\xA2"};

static void compose_settings(void)
{
    lfill_rect(0, 0, SCR_W, SCR_H, 0x0B132Bu);
    if (s_font_w)
        draw_str("\xE8\xAE\xBE\xE7\xBD\xAE", 12, 6, 0xF1FAEEu);
    else
        draw_ascii8(12, 8, "CONFIG", 2, 0xF1FAEEu);
    /* label left, value right 鈥?the old layout drew the value inside the
       same box as the label, which is why the screen looked garbled */
    draw_button(20, 34, 392, 28, "\xE6\x96\x87\xE5\xAD\x97\xE9\x80\x9F\xE5\xBA\xA6", "TEXT SPEED", 0x457B9Du);
    draw_str(SPEED_CJK[s_set_speed], 356, 40, 0xFFD166u);
    if (!s_font_w) draw_ascii8(376, 42, "SPD", 1, 0xFFD166u);
    draw_button(20, 68, 392, 28, "\xE8\x87\xAA\xE5\x8A\xA8\xE6\x92\xAD\xE6\x94\xBE", "AUTO MODE", 0x457B9Du);
    draw_str(AUTO_CJK[s_set_auto], 356, 74, 0xFFD166u);
    if (!s_font_w) draw_ascii8(376, 76, "AUT", 1, 0xFFD166u);
    draw_button(20, 102, 392, 28, "\xE9\x9F\xB3\xE9\x87\x8F", "VOLUME", 0x457B9Du);
    {
        int i;
        for (i = 0; i < 8; i++) {
            uint32_t c = i < (int)s_set_volume ? 0x6FCF97u : 0x30343Bu;
            lfill_rect(340 + i * 9, 108, 6, 16, c);
        }
    }
    draw_button(20, 136, 392, 28, "\xE5\x85\xA8\xE9\x83\xA8\xE8\xA7\xA3\xE9\x94\x81", "UNLOCK ALL", 0x457B9Du);
    draw_str(s_set_unlock ? "\xE5\xBC\x80" : "\xE5\x85\xB3",
             356, 142, s_set_unlock ? 0x6FCF97u : 0x8D99Aeu);
    if (!s_font_w) draw_ascii8(376, 144, s_set_unlock ? "ON" : "OFF", 1,
                               0xFFD166u);
    draw_button(20, 170, 392, 28, "\xE8\xAF\xAD\xE9\x9F\xB3", "VOICE", 0x457B9Du);
    draw_str(s_set_voice ? "\xE5\xBC\x80" : "\xE5\x85\xB3",
             356, 176, s_set_voice ? 0x6FCF97u : 0x8D99Aeu);
    if (!s_font_w) draw_ascii8(376, 178, s_set_voice ? "ON" : "OFF", 1,
                               0xFFD166u);
    draw_ascii8(20, 208, "tap row = change   vol = back", 1, 0x8D99Aeu);
}

static void settings_hit(int lx, int ly)
{
    (void)lx;
    if (ly >= 34 && ly < 66) s_set_speed = (uint8_t)((s_set_speed + 1) & 3);
    else if (ly >= 68 && ly < 100) s_set_auto = (uint8_t)((s_set_auto + 1) & 3);
    else if (ly >= 102 && ly < 134) s_set_volume = (uint8_t)((s_set_volume + 1) % 9);
    else if (ly >= 136 && ly < 168) s_set_unlock = (uint8_t)!s_set_unlock;
    else if (ly >= 170 && ly < 202) s_set_voice = (uint8_t)!s_set_voice;
    else return;
    settings_save();
}

/* ------------------------------------------------------------ misc screens - */

static void compose_missing(void)
{
    static const char *const lines[] = {
        "No game pack found.",
        "",
        "Run tools/build_galpack.py,",
        "then copy script.bin, font.bin,",
        "bg/, spr/, cg.idx, flow.idx",
        "into /Data/vn/ on the iPod disk.",
        "",
        "See apps/vn/README.md",
    };
    int cx = SCR_W / 2, y = 60;
    unsigned i;
    lfill_rect(0, 0, SCR_W, SCR_H, 0x0B132Bu);
    for (i = 0; i < sizeof lines / sizeof lines[0]; i++) {
        int w = ascii8_w(lines[i], 2);
        draw_ascii8(cx - w / 2, y, lines[i], 2, 0xBC6C25u);
        y += 26;
    }
}

static void compose_error(void)
{
    char buf[12];
    uint32_t i = 0, v = s_err;
    lfill_rect(0, 0, SCR_W, SCR_H, 0x6A040Fu);
    draw_ascii8(20, 40, "pack error", 2, 0xF1FAEEu);
    if (v == 0) buf[i++] = '?';
    else {
        char t[12];
        uint32_t n = 0;
        while (v && n < 11) { t[n++] = (char)('0' + v % 10u); v /= 10u; }
        while (n) buf[i++] = t[--n];
    }
    buf[i] = 0;
    draw_ascii8(20, 80, "code", 2, 0xF1FAEEu);
    draw_ascii8(20 + ascii8_w("code", 2) + 10, 80, buf, 2, 0xFFD166u);
    draw_ascii8(20, 120, "script.bin is corrupt or was", 1, 0xE0E1DDu);
    draw_ascii8(20, 134, "built by a newer build_galpack.py.", 1, 0xE0E1DDu);
}

/* --------------------------------------------------------------- flow ------ */

static void start_new_game(void)
{
    if (s_chapter != 0u) {
        if (!load_script_chapter(0u)) {
            s_mode = s_err ? MODE_ERROR : MODE_MISSING;
            return;
        }
    }
    s_pc = 12u + s_labels_n * 4u;
    s_bg_ok = 0;
    s_cur_bg[0] = 0;
    s_spr[0].used = s_spr[1].used = 0;
    s_last_bgm[0] = 0;
    s_hist_n = 0;
    s_skip = 0;
    step();
}

static void continue_game(void)
{
    if (s_chapter != s_save_ch || !s_script_len) {
        if (!load_script_chapter(s_save_ch)) {
            s_mode = s_err ? MODE_ERROR : MODE_MISSING;
            return;
        }
    }
    if (s_save_off < 12u + s_labels_n * 4u || s_save_off >= s_script_len) {
        s_save_valid = 0;
        return;
    }
    set_bg(s_save_bg);
    set_spr(0, s_save_pos[0], s_save_spr[0]);
    set_spr(1, s_save_pos[1], s_save_spr[1]);
    s_pc = s_save_off;
    s_hist_n = 0;
    s_skip = 0;
    step();
}

/* ---------------------------------------------------------------- entry ---- */

void hb_raw_init(int w, int h)
{
    (void)w; (void)h;
    settings_load();
    if (!load_script()) {
        s_mode = s_err ? MODE_ERROR : MODE_MISSING;
        return;
    }
    load_font();
    load_cgidx();
    load_flowidx();
    load_chsel();
    seen_load();
    save_load();
    load_slots_meta();
    save_load();
    s_mode = MODE_TITLE;
}

/* toast overlay: bottom translucent band */
static void compose_toast(void)
{
    if (!s_toast_ticks) return;
    if (s_toast_ticks != 0xFFFFu) s_toast_ticks--;
    ldim_rect(64, SCR_H - 30, 304, 24, 120);
    if (s_font_w)
        draw_str_center(s_toast, 216, SCR_H - 30 + (24 - s_font_h) / 2,
                        0xF1FAEEu);
    else {
        int tw = ascii8_w(s_toast, 1);
        draw_ascii8(216 - tw / 2, SCR_H - 23, s_toast, 1, 0xF1FAEEu);
    }
}

/* touch debug readout: bottom-right, always visible */
static void compose_touchdbg(void)
{
    char b[24];
    int i = 0, v;
    const char *hex = "0123456789ABCDEF";
    if (s_dbg_lx < 0) return;
    b[i++] = 'T'; b[i++] = ':';
    v = s_dbg_lx; if (v < 0) { b[i++] = '-'; v = -v; }
    { int h = v / 100, t = (v / 10) % 10, o = v % 10;
      b[i++] = h ? hex[h] : ' '; b[i++] = hex[t]; b[i++] = hex[o]; }
    b[i++] = ',';
    v = s_dbg_ly; if (v < 0) { b[i++] = '-'; v = -v; }
    { int h = v / 100, t = (v / 10) % 10, o = v % 10;
      b[i++] = h ? hex[h] : ' '; b[i++] = hex[t]; b[i++] = hex[o]; }
    b[i] = 0;
    draw_ascii8(SCR_W - 66, 2, b, 1, 0x6FCF97u);
}

void hb_raw_frame(const hb_spoint_t *touch)
{
    uint8_t click, ffwd, back;
    int lx = 0, ly = 0;

    /* Frame start: start the sound queued last frame, then yield once so the
     * audio pthread gets CPU. Must be BEFORE the redraw work, and reached on
     * every path (previous version only yielded on the dialogue path). */
    if (s_pending_kind) {
        uint32_t i = 0, n = xstrlen(s_pending_snd);
        if (audio_busy()) {                 /* still playing: drop it */
            s_pending_kind = 0;
            s_pending_snd[0] = 0;
        }
        s_dbg_fs = (uint8_t)(hb_fs_size(s_pending_snd) != 0);
        s_dbg_ret = s_pending_kind ?
            (uint8_t)hb_audio_play_wav_main(s_pending_snd, s_pending_vol) : 0;
        if (s_pending_kind) {
            uint32_t hold = (uint32_t)(s_pending_ticks ? s_pending_ticks : 30u);
            /* Ultra conservative: clip length + 50% + 2 s, and never less
               than 3 s between two playbacks. Frequent pthread_create on a
               single static descriptor is what reboots the device. */
            /* clip length + 2 s (covers the pthread's loadFile latency),
               floor 4 s. Longer waits only make speech sparse. */
            hold = hold + 90u;
            if (hold < 180u) hold = 180u;    /* clip + 3 s, floor 6 s */
            s_audio_until = s_ticks + hold;
        }
        if (s_dbg_calls < 9999) s_dbg_calls++;
        /* keep the tail of the path (file name is what matters) */
        if (n > 20u) i = n - 20u;
        {
            uint32_t k = 0;
            while (s_pending_snd[i] && k < sizeof s_dbg_snd - 1u)
                s_dbg_snd[k++] = s_pending_snd[i++];
            s_dbg_snd[k] = 0;
        }
        s_pending_kind = 0;
        s_pending_snd[0] = 0;
        hb_display_wait_vsync();
    }

    if (s_prev_mode != s_mode) {          /* mode switch: full repaint */
        s_prev_mode = s_mode;
        s_need_full = 1;
    }

    s_ticks++;
    if (touch) {                                   /* physical -> logical */
        lx = SCR_W - 1 - touch->y;                 /* CW grip: phys y grows left */
        ly = touch->x;                             /* logical y = phys x  */
        if (touch->down) {
            s_dbg_lx = (int16_t)lx;
            s_dbg_ly = (int16_t)ly;
        }
    }
    click = (uint8_t)(touch && touch->down && !s_prev_down);
    s_prev_down = touch ? (uint8_t)touch->down : 0;
    ffwd = (uint8_t)hb_button_pressed(HB_BTN_VOL_UP);
    back = (uint8_t)hb_button_pressed(HB_BTN_VOL_DOWN);

    /* VOL_UP edge: leave list screens back to title */
    if (ffwd && !s_prev_ffwd) {
        switch (s_mode) {
        case MODE_GALLERY: case MODE_CGVIEW: case MODE_FLOW: case MODE_CHSEL:
            seen_flush();
            s_mode = MODE_TITLE;
            break;
        case MODE_SETTINGS:
            s_mode = s_ret_mode;
            if (s_mode == MODE_SCENE) s_mode = MODE_IGMENU;
            break;
        case MODE_SAVELOAD:
            s_mode = s_ret_mode;
            if (s_mode == MODE_SCENE) s_mode = MODE_IGMENU;
            break;
        default:
            break;
        }
    }
    s_prev_ffwd = ffwd;

    /* VOL_DOWN edge: scene = rewind one line (蹇€€); lists = back out */
    if (back && !s_prev_back) {
        switch (s_mode) {
        case MODE_SCENE:
            rewind_line();
            break;
        case MODE_GALLERY: case MODE_CGVIEW: case MODE_FLOW: case MODE_CHSEL:
            seen_flush();
            s_mode = MODE_TITLE;
            break;
        case MODE_SETTINGS:
            s_mode = s_ret_mode;
            if (s_mode == MODE_SCENE) s_mode = MODE_IGMENU;
            break;
        case MODE_SAVELOAD:
            s_mode = s_ret_mode;
            if (s_mode == MODE_SCENE) s_mode = MODE_IGMENU;
            break;
        default:
            break;
        }
    }
    s_prev_back = back;

    switch (s_mode) {
    case MODE_FLOW:
        if (click) { flow_hit(lx, ly); s_need_full = 1; }
        break;
    case MODE_TITLE:
        if (click) title_hit(lx, ly);
        break;
    case MODE_CHOICE:
        if (click) choice_hit(lx, ly);
        break;
    case MODE_IGMENU:
        if (click) igmenu_hit(lx, ly);
        break;
    case MODE_SAVELOAD:
        if (click) saveload_hit(lx, ly);
        break;
    case MODE_GALLERY:
        if (click) gallery_hit(lx, ly);
        break;
    case MODE_CGVIEW:
        if (click) cgview_hit(lx, ly);
        break;
    case MODE_CHSEL:
        if (click) chsel_hit(lx, ly);
        break;
    case MODE_SETTINGS:
        if (click) settings_hit(lx, ly);
        break;
    case MODE_END:
        if (click) s_mode = MODE_TITLE;
        break;
    case MODE_SCENE:
        if (click && ly < 20) {                       /* scene shortcut bar */
            if (lx >= 4 && lx < 62) { s_skip_bg = 1; s_skip = 0; break; }
            if (lx >= 64 && lx < 122) { s_skip = 1; s_skip_bg = 0; break; }
        }
        if (lx >= SCR_W - 40 && ly < 32 && click) {   /* corner menu zone */
            s_mode = MODE_IGMENU;
            break;
        }
        if (s_skip_bg) {                               /* skip-to-next-bg */
            if (click) { s_skip_bg = 0; break; }       /* tap cancels     */
            s_saw_bg = 0;
            step();
            if (s_saw_bg || s_mode != MODE_SCENE) s_skip_bg = 0;
            break;
        }
        if (s_skip) {                                  /* skip-to-choice */
            if (click) { s_skip = 0; break; }          /* tap cancels   */
            if ((s_ticks & 1u) == 0) step();
            break;
        }
        if (s_wait) {
            if (click || --s_wait == 0) { s_wait = 0; step(); }
            break;
        }
        if (s_reveal < page_chars()) {
            uint16_t d = text_delay_ticks();
            if (ffwd || click || d == 0) s_reveal = page_chars();
            else if (d && (s_ticks % d) == 0) s_reveal++;
        } else if (click) {
            if (s_page_start + page_chars() < text_chars()) {
                s_page_start = (uint16_t)(s_page_start + page_chars());
                s_reveal = 0;
                s_auto_ticks = 0;
            } else {
                step();
            }
        } else if (auto_delay_ticks()) {
            if (++s_auto_ticks >= auto_delay_ticks()) {
                s_auto_ticks = 0;
                if (s_page_start + page_chars() < text_chars()) {
                    s_page_start = (uint16_t)(s_page_start + page_chars());
                    s_reveal = 0;
                } else {
                    step();
                }
            }
        }
        break;
    default:
        break;
    }

    switch (s_mode) {
    case MODE_MISSING: compose_missing(); compose_toast(); compose_touchdbg(); return;
    case MODE_ERROR:   compose_error();   compose_toast(); compose_touchdbg(); return;
    case MODE_TITLE:   compose_title();   compose_toast(); compose_touchdbg(); return;
    case MODE_GALLERY: compose_gallery(); compose_toast(); compose_touchdbg(); return;
    case MODE_CGVIEW:  compose_cgview();  compose_toast(); compose_touchdbg(); return;
    case MODE_FLOW:    compose_flow();    compose_toast(); compose_touchdbg(); return;
    case MODE_CHSEL:   compose_chsel();   compose_toast(); compose_touchdbg(); return;
    case MODE_SETTINGS: compose_settings(); compose_toast(); compose_touchdbg(); return;
    case MODE_SAVELOAD: compose_saveload(); compose_toast(); compose_touchdbg(); return;
    default:           break;
    }

    if (s_mode == MODE_IGMENU) { compose_igmenu(); compose_toast(); compose_touchdbg(); return; }

    /* Background and sprites only change on OP_BG / OP_SPR / mode switches;
       repainting them every frame is what made the UI feel frozen on the
       ARM9. The textbox rebuilds its own region each frame (see
       compose_textbox), so a stale overlay never lingers. */
    if (s_need_full) {
        compose_bg();
        compose_sprites();
        s_need_full = 0;
    }
    if (s_mode == MODE_CHOICE) { compose_choice(); compose_toast(); compose_touchdbg(); return; }
    if (s_mode == MODE_END) {
        int w = ascii8_w("- THE END -", 2);
        draw_ascii8((SCR_W - w) / 2, 110, "- THE END -", 2, 0xF1FAEEu);
        draw_arrow();
        compose_touchdbg();
        return;
    }
    compose_textbox();
    compose_text();
    /* chapter marker, top-left (original: "CHAPTER 2-1") */
    {
        char cb[24];
        int k = 0;
        const char *p1 = "CHAPTER ";
        unsigned n = (unsigned)s_chapter + 1u;
        while (*p1) cb[k++] = *p1++;
        if (n >= 100u) cb[k++] = (char)('0' + (n / 100u) % 10u);
        if (n >= 10u) cb[k++] = (char)('0' + (n / 10u) % 10u);
        cb[k++] = (char)('0' + n % 10u);
        cb[k] = 0;
        ldim_rect(4, 4, 108, 14, 120);
        draw_ascii8(8, 7, cb, 1, 0xF5F2F0u);
    }
    /* audio debug (temporary): ret / file-existed / last file */
    {
        char d[52];
        int k = 0, j = 0;
        const char *p1 = "SD:";
        while (*p1) d[k++] = *p1++;
        d[k++] = (char)('0' + (s_dbg_ret ? 1 : 0));
        d[k++] = (char)('0' + (s_dbg_fs ? 1 : 0));
        d[k++] = ' ';
        d[k++] = (char)('0' + (s_dbg_calls / 100) % 10);
        d[k++] = (char)('0' + (s_dbg_calls / 10) % 10);
        d[k++] = (char)('0' + s_dbg_calls % 10);
        d[k++] = ' ';
        while (s_dbg_snd[j] && k < 48) d[k++] = s_dbg_snd[j++];
        d[k] = 0;
        draw_ascii8(6, 112, d, 1, 0xFFD166u);
    }
    /* in-game menu affordance */
    lfill_rect(SCR_W - 34, 6, 28, 20, 0x1D3557u);
    draw_ascii8(SCR_W - 30, 10, "MENU", 1, 0xF1FAEEu);
    if (s_wait == 0 && s_reveal >= page_chars()) draw_arrow();
    /* ---- frame tail: start any queued sound, then hand the CPU over ----
     * The audio pthread needs this app to yield; hb_display_wait_vsync()
     * blocks until the next vblank (~16 ms) which both paces the loop and
     * lets the audio worker actually run. Without it every clip dies
     * silently (SDK: a tight UI loop STARVES the audio pthread). */
    if (s_pending_kind) {
        hb_audio_play_wav_main(s_pending_snd, s_pending_vol);
        s_pending_kind = 0;
        s_pending_snd[0] = 0;
        hb_display_wait_vsync();      /* give the worker its slice */
    }
}
