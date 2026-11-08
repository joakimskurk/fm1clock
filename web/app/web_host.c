/* SPDX-License-Identifier: GPL-3.0-only */
/* FM-1 Clock in a browser: an FM-1 for the page (web/app/), as tests/host.c is one for a computer. platform.c
 * includes this file instead of tests/host.c when DINGHY_WEB is set (with DINGHY_HOST: the app's host branches). The
 * firmware's own code runs unchanged on it, compiled to WebAssembly (web/app/build.sh), no C library:
 *
 *   web_init(ng)            the app's start (ng: the gong's carriers to render; 206 as on the chip)
 *   web_run(n)              n stereo frames of its sound into web_out (L R L R, +-32767): the app's main loop runs a
 *                           pass for each millisecond those frames are worth, the sound in its blocks of 256 frames,
 *                           as the audio interrupt renders it; so the page's sound is the clock's time base
 *   web_lcd(), web_lcd_rev()  the screen, 240 x 240 RGB565 (CPU order), and a count that moves when it changes
 *   web_leds_lo / hi()      the LEDs: bit id (0..13 the buttons, 14..40 the keys), the dim layer not
 *   web_btn(id)             a button pressed and let go (BTN_*)
 *   web_enc(id, n)          an encoder turned n detents (ENC_*, + = clockwise)
 *   web_midi(st, d1, d2)    a MIDI message in, over "USB" (CC 20, 21, 22: the time)
 */
#include <stdint.h>
#include <stddef.h>

#define WEB_EXPORT(name) __attribute__((export_name(#name)))

void *memcpy(void *d, const void *s, size_t n)
{
    volatile uint8_t *a = d;
    const uint8_t *b = s;
    while (n--) *a++ = *b++;
    return d;
}
void *memmove(void *d, const void *s, size_t n)
{
    volatile uint8_t *a = d;
    const uint8_t *b = s;
    if (a < b) while (n--) *a++ = *b++;
    else while (n--) a[n] = b[n];
    return d;
}
void *memset(void *d, int c, size_t n)
{
    volatile uint8_t *a = d;
    while (n--) *a++ = (uint8_t)c;
    return d;
}
int memcmp(const void *x, const void *y, size_t n)
{
    const uint8_t *a = x, *b = y;
    for (; n; n--, a++, b++)
        if (*a != *b) return *a - *b;
    return 0;
}

#ifndef APP_NAME
#define APP_NAME "DINGHY"
#endif
#ifndef APP_VER
#define APP_VER "0.0"
#endif
#define FS 44100u
#define HALF_FRAMES 256u

static volatile uint32_t fm1_ms;
#define HOST_NENC 7
static struct { uint32_t notes, buttons; } fm1_in;
static uint32_t host_edges, host_rel, host_rel_next;
static uint32_t fm1_input_edges(uint32_t *released)
{
    uint32_t b = host_edges;
    host_edges = 0;
    *released = host_rel;
    host_rel = host_rel_next;
    host_rel_next = 0;
    return b;
}
static uint32_t fm1_input_note_edges(void) { return 0; }
static int32_t host_enc[HOST_NENC];
static int32_t fm1_enc_take(uint32_t e) { int32_t v = host_enc[e % HOST_NENC]; host_enc[e % HOST_NENC] = 0; return v; }
static uint64_t host_leds;
static void fm1_irq_off(void) {}                 /* (the sound is rendered between the main loop's passes) */
static void fm1_irq_on(void) {}
static void fm1_led_key(uint32_t id, int on) { if (on) host_leds |= (uint64_t)1 << id; else host_leds &= ~((uint64_t)1 << id); }
static void fm1_led_key_glow(uint32_t id, int on) { (void)id; (void)on; }

/* the screen: 240 x 240 RGB565, in the CPU's order (gfx.c sends the bytes swapped, as the ST7789 wants them) */
static uint16_t fb[240 * 240];
static uint32_t fb_rev;
static void lcd_sync(void) {}
static void lcd_fill(uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint16_t c)
{
    uint32_t i, j;
    for (j = y; j < y + h && j < 240u; j++)
        for (i = x; i < x + w && i < 240u; i++)
            fb[j * 240u + i] = c;
    fb_rev++;
}
static void lcd_blit(uint32_t x, uint32_t y, uint32_t w, uint32_t h, const uint16_t *px)
{
    uint32_t i, j;
    for (j = 0; j < h; j++)
        for (i = 0; i < w; i++)
            if (x + i < 240u && y + j < 240u) {
                uint16_t c = px[j * w + i];
                fb[(y + j) * 240u + x + i] = (uint16_t)(c >> 8 | c << 8);
            }
    fb_rev++;
}
#ifndef CV_MAX
#define CV_MAX (240u * 64u)
#endif
#include "gfx.c"

/* storage in RAM, for as long as the page is open (store.h's sizes) */
#include "store.h"
static uint8_t host_set[SECTOR_MAX + 4];
static int host_load(uint8_t *a, uint32_t max, void *p, uint32_t n)
{
    if (!a[0] || n > max || (uint32_t)(a[1] | a[2] << 8 | a[3] << 16) != n) return -1;
    memcpy(p, a + 4, n);
    return 0;
}
static int host_save(uint8_t *a, uint32_t max, const void *p, uint32_t n)
{
    if (n > max) return -1;
    a[0] = 1; a[1] = (uint8_t)n; a[2] = (uint8_t)(n >> 8); a[3] = (uint8_t)(n >> 16);
    memcpy(a + 4, p, n);
    return 0;
}
static int settings_load(void *p, uint32_t n) { return host_load(host_set, SECTOR_MAX, p, n); }
static int settings_save(const void *p, uint32_t n) { return host_save(host_set, SECTOR_MAX, p, n); }
static int blob_load(uint32_t i, void *p, uint32_t n) { (void)i; (void)p; (void)n; return -1; }
static int blob_save(uint32_t i, const void *p, uint32_t n) { (void)i; (void)p; (void)n; return -1; }
static int slot_load(uint32_t i, void *p, uint32_t n) { (void)i; (void)p; (void)n; return -1; }
static int slot_save(uint32_t i, const void *p, uint32_t n) { (void)i; (void)p; (void)n; return -1; }

static uint8_t mq[64][3];
static uint32_t mq_w, mq_r;
static int midi_get(uint8_t *st, uint8_t *d1, uint8_t *d2)
{
    if (mq_r == mq_w) return 0;
    *st = mq[mq_r % 64u][0]; *d1 = mq[mq_r % 64u][1]; *d2 = mq[mq_r % 64u][2];
    mq_r++;
    return 1;
}
static void midi_send(uint32_t st, uint32_t d1, uint32_t d2) { (void)st; (void)d1; (void)d2; }

static void app_audio(int32_t *out, uint32_t n);
static void app_main(void);

/* the sound: a ring the passes fill, a block at a time; web_run hands it out */
#define RING 8192u                              /* frames */
static int32_t ring[2u * RING];
static uint32_t ring_w, ring_r;                 /* frames written, read */
static int32_t web_out[2u * 1024u];

static void platform_poll(void)                 /* one call = one millisecond, as on the host */
{
    static uint32_t owed;
    static int32_t blk[2u * HALF_FRAMES];
    fm1_ms++;
    owed += FS;
    while (owed >= 1000u * HALF_FRAMES) {
        uint32_t i;
        owed -= 1000u * HALF_FRAMES;
        for (i = 0; i < 2u * HALF_FRAMES; i++) blk[i] = 0;
        app_audio(blk, HALF_FRAMES);
        for (i = 0; i < HALF_FRAMES; i++) {
            uint32_t k = (ring_w + i) % RING;
            ring[2u * k] = blk[2u * i];
            ring[2u * k + 1u] = blk[2u * i + 1u];
        }
        ring_w += HALF_FRAMES;
    }
}

static uint32_t web_ng = 206;
WEB_EXPORT(web_init) void web_init(uint32_t ng)
{
    static int started;
    if (started) return;
    started = 1;
    web_ng = ng;
    app_main();                                 /* its start and a first pass (app_main: one pass a call here) */
}
WEB_EXPORT(web_run) uint32_t web_run(uint32_t n)
{
    uint32_t i, guard = 0;
    if (n > 1024u) n = 1024u;
    while (ring_w - ring_r < n && guard++ < 1000u)
        app_main();
    for (i = 0; i < n; i++) {
        uint32_t k = (ring_r + i) % RING;
        web_out[2u * i] = ring[2u * k];
        web_out[2u * i + 1u] = ring[2u * k + 1u];
    }
    ring_r += n;
    return n;
}
WEB_EXPORT(web_out_ptr) int32_t *web_out_ptr(void) { return web_out; }
WEB_EXPORT(web_lcd) uint16_t *web_lcd(void) { return fb; }
WEB_EXPORT(web_lcd_rev) uint32_t web_lcd_rev(void) { return fb_rev; }
WEB_EXPORT(web_ms) uint32_t web_ms(void) { return fm1_ms; }
WEB_EXPORT(web_leds_lo) uint32_t web_leds_lo(void) { return (uint32_t)host_leds; }
WEB_EXPORT(web_leds_hi) uint32_t web_leds_hi(void) { return (uint32_t)(host_leds >> 32); }
WEB_EXPORT(web_btn) void web_btn(uint32_t id)
{
    if (id < 32u) { host_edges |= 1u << id; host_rel_next |= 1u << id; }
}
WEB_EXPORT(web_enc) void web_enc(uint32_t id, int32_t n) { host_enc[id % HOST_NENC] += n; }
WEB_EXPORT(web_midi) void web_midi(uint32_t st, uint32_t d1, uint32_t d2)
{
    mq[mq_w % 64u][0] = (uint8_t)st; mq[mq_w % 64u][1] = (uint8_t)d1; mq[mq_w % 64u][2] = (uint8_t)d2;
    mq_w++;
}
