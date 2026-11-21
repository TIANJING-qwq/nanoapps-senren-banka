/* Host driver for apps/vn/vn.c — runs the REAL engine code on the PC and
 * writes the framebuffer to PPM files. Used to verify rendering (font,
 * layout, orientation) without a device.
 *   ./vn_host            -> title.ppm
 *   ./vn_host tap        -> also taps START and dumps scene.ppm
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "hb_raw_surface.h"
#include "hb_sdk.h"

static void dump_ppm(const char *path)
{
    const uint32_t *fb = hb_raw_fb();
    int w = hb_raw_w(), h = hb_raw_h(), x, y;
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return; }
    fprintf(f, "P6\n%d %d\n255\n", w, h);
    for (y = 0; y < h; y++)
        for (x = 0; x < w; x++) {
            uint32_t c = fb[y * w + x];
            uint8_t rgb[3] = { (uint8_t)((c >> 16) & 0xFF),
                               (uint8_t)((c >> 8) & 0xFF),
                               (uint8_t)(c & 0xFF) };
            fwrite(rgb, 1, 3, f);
        }
    fclose(f);
    fprintf(stderr, "wrote %s (%dx%d)\n", path, w, h);
}

int main(int argc, char **argv)
{
    hb_spoint_t t;
    int i;
    int do_tap = (argc > 1 && strcmp(argv[1], "tap") == 0);

    hb_raw_init(240, 432);
    for (i = 0; i < 3; i++) hb_raw_frame(NULL);
    dump_ppm("title.ppm");

    if (do_tap) {
        /* tap START: logical (20,50). touch->x = ly, touch->y = SCR_W-1-lx
         * = 432-1-20 = 411 */
        memset(&t, 0, sizeof t);
        t.x = 50; t.y = 411; t.down = 1;
        hb_raw_frame(&t);
        t.down = 0;
        hb_raw_frame(&t);
        for (i = 0; i < 40; i++) hb_raw_frame(NULL);
        dump_ppm("scene.ppm");
        /* click through a few lines */
        for (i = 0; i < 6; i++) {
            t.down = 1; hb_raw_frame(&t);
            t.down = 0; hb_raw_frame(&t);
            for (int k = 0; k < 40; k++) hb_raw_frame(NULL);
        }
        dump_ppm("scene2.ppm");
    }
    return 0;
}
