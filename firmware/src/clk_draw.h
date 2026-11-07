/* SPDX-License-Identifier: GPL-3.0-only */
/* FM1 Clock's pictures: the design as the background (firmware/gen/clk_art.h, tools/gen_art.py), and over it what
 * moves: the hands (polygons, 4 x 4 samples a pixel) and the pendulum (the rod, the bob with its own shading, both
 * behind the glass: its reflections and the gold go over them). Two regions are drawn again, each into a buffer of
 * its own and sent by DMA while the next is made: the dial's middle when the hands move, the window when the
 * pendulum does.
 *
 *   draw_all()                        the whole screen once
 *   draw_dial(hour, minute)           the hands at these angles (2^32 = a turn, from 12 clockwise)
 *   draw_window(theta)                the pendulum at this angle (2^32 = a turn, + = to the right) */
#include "clk_art.h"

#define FX 256                                  /* coordinates in 1/256 px */
#define DIAL_R 36                               /* the hands stay within this of the hub (px) */
#define DIAL_W (2 * DIAL_R)
#define PEND_L256 (BOB_Y256 - HUB_Y256)         /* the hub to the bob's centre: the pendulum hangs from behind it */

static uint16_t dial_px[DIAL_W * DIAL_W] __attribute__((section(".pool")));
static uint16_t win_px[WIN_W * WIN_H] __attribute__((section(".pool")));
static int32_t dial_x0, dial_y0;

static inline uint32_t unsw(uint32_t c) { return ((c >> 8) & 0xFFu) | ((c & 0xFFu) << 8); }
/* c over d, a = 0..256 (RGB565 in the CPU's order) */
static inline uint32_t mix565(uint32_t d, uint32_t c, uint32_t a)
{
    uint32_t r = (((d >> 11) * (256u - a) + (c >> 11) * a) >> 8);
    uint32_t g = ((((d >> 5) & 63u) * (256u - a) + ((c >> 5) & 63u) * a) >> 8);
    uint32_t b = (((d & 31u) * (256u - a) + (c & 31u) * a) >> 8);
    return r << 11 | g << 5 | b;
}
static inline void unpack(uint32_t c, int32_t *r, int32_t *g, int32_t *b)   /* 565 -> 0..255 */
{
    *r = (int32_t)(((c >> 11) * 527u + 23u) >> 6);
    *g = (int32_t)((((c >> 5) & 63u) * 259u + 33u) >> 6);
    *b = (int32_t)(((c & 31u) * 527u + 23u) >> 6);
}
static inline uint32_t pack(int32_t r, int32_t g, int32_t b)
{
    r = r < 0 ? 0 : r > 255 ? 255 : r;
    g = g < 0 ? 0 : g > 255 ? 255 : g;
    b = b < 0 ? 0 : b > 255 ? 255 : b;
    return (uint32_t)((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3));
}

static void draw_all(void)
{
    uint32_t y, i;
    lcd_fill(0, 0, 240, 240, C_BLACK);
    for (y = 0; y < BG_H; y += 32u) {           /* in strips through RAM: the screen's DMA reads RAM only (lcd.c) */
        uint32_t h = BG_H - y < 32u ? BG_H - y : 32u;
        lcd_sync();
        for (i = 0; i < h * BG_W; i++)
            dial_px[i] = BG_SW[y * BG_W + i];
        lcd_blit(BG_X, BG_Y + y, BG_W, h, dial_px);
    }
    lcd_sync();
}

/* ---- the hands: convex pieces, in the hand's own frame (px * 256: x across, y out from the hub) */
typedef struct { int16_t n, pt[4][2]; } piece_t;
static const piece_t MINUTE[2] = {
    {4, {{-230, -1300}, {230, -1300}, {170, 6200}, {-170, 6200}}},     /* the shaft, a little tail behind the hub */
    {4, {{0, 5000}, {540, 6300}, {0, 7900}, {-540, 6300}}},            /* the spear by its tip */
};
static const piece_t HOUR[2] = {
    {4, {{-360, -1100}, {360, -1100}, {280, 3700}, {-280, 3700}}},
    {4, {{0, 3000}, {830, 4250}, {0, 5800}, {-830, 4250}}},            /* the arrow */
};
#define C_HAND_DARK RGB(18, 16, 22)
#define C_HAND_LIT RGB(74, 70, 82)

/* the pieces turned to angle th about the hub, offset (ox, oy) px*256: edges as a x + b y + c >= 0 */
typedef struct { int32_t a[4], b[4], c[4], n; int32_t x0, y0, x1, y1; } edges_t;
static void hand_edges(const piece_t *pc, uint32_t th, int32_t ox, int32_t oy, edges_t *e)
{
    int32_t s = SINT[th >> 18], c = SINT[(th + 1073741824u) >> 18], i;
    int32_t px[4], py[4];
    e->n = pc->n;
    e->x0 = e->y0 = 1 << 30;
    e->x1 = e->y1 = -(1 << 30);
    for (i = 0; i < pc->n; i++) {               /* local (x across, y out) -> screen: out = (sin, -cos) */
        int32_t lx = pc->pt[i][0], ly = pc->pt[i][1];
        px[i] = HUB_X256 + ox + ((lx * c + ly * s) >> 15);
        py[i] = HUB_Y256 + oy + ((lx * s - ly * c) >> 15);
        if (px[i] < e->x0) e->x0 = px[i];
        if (px[i] > e->x1) e->x1 = px[i];
        if (py[i] < e->y0) e->y0 = py[i];
        if (py[i] > e->y1) e->y1 = py[i];
    }
    for (i = 0; i < pc->n; i++) {               /* the pieces are clockwise on the screen (y down) */
        int32_t j = (i + 1) % pc->n;
        e->a[i] = (py[j] - py[i]) >> 4;         /* (1/16 px steps keep the products in 32 bits) */
        e->b[i] = (px[i] - px[j]) >> 4;
        e->c[i] = -(e->a[i] * (px[i] >> 4) + e->b[i] * (py[i] >> 4));
    }
}
static inline int edges_in(const edges_t *e, int32_t x16, int32_t y16)
{
    int32_t i;
    for (i = 0; i < e->n; i++)
        if (e->a[i] * x16 + e->b[i] * y16 + e->c[i] < 0)
            return 0;
    return 1;
}
/* one hand (two pieces) into dial_px: shade = 0: its shadow (black, ~35 %); 1: the hand, lit on its right side */
static void draw_hand(const piece_t *pcs, uint32_t th, int shade)
{
    edges_t e[2];
    int32_t ox = shade ? 0 : 300, oy = shade ? 0 : 420, x, y, k, s = SINT[th >> 18], c = SINT[(th + 1073741824u) >> 18];
    int32_t x0, y0, x1, y1;
    hand_edges(&pcs[0], th, ox, oy, &e[0]);
    hand_edges(&pcs[1], th, ox, oy, &e[1]);
    x0 = (e[0].x0 < e[1].x0 ? e[0].x0 : e[1].x0) >> 8;
    y0 = (e[0].y0 < e[1].y0 ? e[0].y0 : e[1].y0) >> 8;
    x1 = ((e[0].x1 > e[1].x1 ? e[0].x1 : e[1].x1) >> 8) + 1;
    y1 = ((e[0].y1 > e[1].y1 ? e[0].y1 : e[1].y1) >> 8) + 1;
    if (x0 < dial_x0) x0 = dial_x0;
    if (y0 < dial_y0) y0 = dial_y0;
    if (x1 > dial_x0 + DIAL_W) x1 = dial_x0 + DIAL_W;
    if (y1 > dial_y0 + DIAL_W) y1 = dial_y0 + DIAL_W;
    for (y = y0; y < y1; y++)
        for (x = x0; x < x1; x++) {
            int32_t cov = 0, lit = 0, sy, sx;
            for (sy = 0; sy < 4; sy++)
                for (sx = 0; sx < 4; sx++) {
                    int32_t px = x * 16 + 2 + sx * 4, py = y * 16 + 2 + sy * 4;   /* 1/16 px */
                    if (edges_in(&e[0], px, py) || edges_in(&e[1], px, py)) {
                        cov++;
                        /* across the hand: (p - hub) . (cos, sin); its right side catches the light */
                        if (shade && ((px - (HUB_X256 >> 4)) * c + (py - (HUB_Y256 >> 4)) * s) > 1 * 16 * 32767 / 4)
                            lit++;
                    }
                }
            if (cov) {
                uint16_t *d = &dial_px[(y - dial_y0) * DIAL_W + (x - dial_x0)];
                uint32_t dc = unsw(*d), col;
                if (!shade) {
                    col = mix565(dc, 0, (uint32_t)cov * 90u / 16u);
                } else {
                    uint32_t hc = lit * 2 > cov ? C_HAND_LIT : C_HAND_DARK;
                    col = mix565(dc, hc, (uint32_t)cov * 16u);
                }
                *d = (uint16_t)unsw(col);
            }
            (void)k;
        }
}
static void draw_hub(void)                      /* the brass boss over the hands */
{
    int32_t x, y, sx, sy, cx = HUB_X256 >> 4, cy = HUB_Y256 >> 4;
    for (y = (HUB_Y256 >> 8) - 5; y <= (HUB_Y256 >> 8) + 5; y++)
        for (x = (HUB_X256 >> 8) - 5; x <= (HUB_X256 >> 8) + 5; x++) {
            int32_t cov = 0, rim = 0, lr = 0, lg = 0, lb = 0;
            for (sy = 0; sy < 4; sy++)
                for (sx = 0; sx < 4; sx++) {
                    int32_t dx = x * 16 + 2 + sx * 4 - cx, dy = y * 16 + 2 + sy * 4 - cy, r2 = dx * dx + dy * dy;
                    if (r2 < 61 * 61) {        /* 3.8 px */
                        cov++;
                        if (r2 > 51 * 51) rim++;
                        else {                  /* lit from the top left */
                            int32_t l = 150 - (dx + dy) * 2;
                            lr += 150 + l * 2 / 3; lg += 96 + l / 2; lb += 28 + l / 6;
                        }
                    }
                }
            if (cov) {
                uint16_t *d = &dial_px[(y - dial_y0) * DIAL_W + (x - dial_x0)];
                int32_t in = cov - rim;
                uint32_t col = in ? pack(lr / in, lg / in, lb / in) : RGB(46, 28, 10);
                col = in ? mix565(RGB(46, 28, 10), col, (uint32_t)in * 256u / (uint32_t)cov) : col;
                *d = (uint16_t)unsw(mix565(unsw(*d), col, (uint32_t)cov * 16u));
            }
        }
}

static void draw_dial(uint32_t hour, uint32_t minute)
{
    int32_t y;
    dial_x0 = (HUB_X256 >> 8) - DIAL_R;
    dial_y0 = (HUB_Y256 >> 8) - DIAL_R;
    lcd_sync();                                 /* (the last send of this buffer is done) */
    for (y = 0; y < DIAL_W; y++) {
        const uint16_t *src = BG_SW + (uint32_t)(dial_y0 + y - BG_Y) * BG_W + (uint32_t)(dial_x0 - BG_X);
        uint16_t *d = &dial_px[y * DIAL_W];
        int32_t x;
        for (x = 0; x < DIAL_W; x++)
            d[x] = src[x];
    }
    draw_hand(HOUR, hour, 0);
    draw_hand(MINUTE, minute, 0);
    draw_hand(HOUR, hour, 1);
    draw_hand(MINUTE, minute, 1);
    draw_hub();
    lcd_blit((uint32_t)dial_x0, (uint32_t)dial_y0, DIAL_W, DIAL_W, dial_px);
}

/* ---- the pendulum */
static void draw_window(uint32_t th)
{
    int32_t s = SINT[th >> 18], c = SINT[(th + 1073741824u) >> 18];
    int32_t bx = HUB_X256 + (int32_t)(((int64_t)PEND_L256 * s) >> 15);     /* the bob's centre, 1/256 px */
    int32_t by = HUB_Y256 + (int32_t)(((int64_t)PEND_L256 * c) >> 15);
    int32_t rx_top = HUB_X256 + ((WIN_Y * FX - HUB_Y256) * s) / (c > 16384 ? c : 16384);   /* the rod at the top */
    int32_t xa, xb, x, y;
    lcd_sync();
    for (y = 0; y < WIN_H; y++) {               /* the window as it is without the pendulum */
        const uint16_t *src = BG_SW + (uint32_t)(WIN_Y + y - BG_Y) * BG_W + (uint32_t)(WIN_X - BG_X);
        uint16_t *d = &win_px[y * WIN_W];
        for (x = 0; x < WIN_W; x++)
            d[x] = src[x];
    }
    /* the columns the rod and the bob can touch */
    xa = ((rx_top < bx ? rx_top : bx) - BOB_R256 - 4 * FX) >> 8;
    xb = ((rx_top > bx ? rx_top : bx) + BOB_R256 + 4 * FX) >> 8;
    if (xa < WIN_X) xa = WIN_X;
    if (xb > WIN_X + WIN_W) xb = WIN_X + WIN_W;
    for (y = 0; y < WIN_H; y++)
        for (x = xa; x < xb; x++) {
            int32_t i = y * WIN_W + (x - WIN_X), r, g, b, a;
            int32_t px = (x << 8) + 128, py = ((WIN_Y + y) << 8) + 128;
            int32_t u, t, sxp, syp;
            unpack(WIN_BACK[i], &r, &g, &b);
            /* the rod: across it u, along it t (from the hub down), 1/256 px */
            u = ((px - HUB_X256) * c - (py - HUB_Y256) * s) >> 15;   /* (each term < 2^30: 32 bits do) */
            t = ((px - HUB_X256) * s + (py - HUB_Y256) * c) >> 15;
            if (t < PEND_L256 && u > -(ROD_N * FX / 2) - FX && u < ROD_N * FX / 2 + FX) {
                int32_t pos = u + ROD_N * FX / 2 - FX / 2, k = pos >> 8, f = pos & 255, cov;
                int32_t k0 = k < 0 ? 0 : k > ROD_N - 1 ? ROD_N - 1 : k, k1 = k + 1 < 0 ? 0 : k + 1 > ROD_N - 1 ? ROD_N - 1 : k + 1;
                int32_t edge = ROD_N * FX / 2 - (u < 0 ? -u : u);   /* 1/256 px inside the rod's edge */
                cov = edge + FX / 2;
                cov = cov < 0 ? 0 : cov > FX ? FX : cov;
                if (cov) {
                    int32_t rr = (ROD_RGB[3 * k0] * (256 - f) + ROD_RGB[3 * k1] * f) >> 8;
                    int32_t rg = (ROD_RGB[3 * k0 + 1] * (256 - f) + ROD_RGB[3 * k1 + 1] * f) >> 8;
                    int32_t rb = (ROD_RGB[3 * k0 + 2] * (256 - f) + ROD_RGB[3 * k1 + 2] * f) >> 8;
                    r += ((rr - r) * cov) >> 8;
                    g += ((rg - g) * cov) >> 8;
                    b += ((rb - b) * cov) >> 8;
                }
            }
            /* the bob: its sprite (premultiplied), sampled between its pixels */
            sxp = px - bx + BOB_CX256 - 128;
            syp = py - by + BOB_CY256 - 128;
            if (sxp >= 0 && syp >= 0 && (sxp >> 8) < BOB_W - 1 && (syp >> 8) < BOB_H - 1) {
                int32_t ix = sxp >> 8, iy = syp >> 8, fx = sxp & 255, fy = syp & 255, ch, v[4];
                const uint8_t *p0 = &BOB_RGBA[4 * (iy * BOB_W + ix)], *p1 = p0 + 4 * BOB_W;
                for (ch = 0; ch < 4; ch++) {
                    int32_t top = p0[ch] * (256 - fx) + p0[ch + 4] * fx, bot = p1[ch] * (256 - fx) + p1[ch + 4] * fx;
                    v[ch] = (top * (256 - fy) + bot * fy) >> 16;
                }
                a = v[3];
                r = v[0] + ((r * (255 - a)) >> 8);
                g = v[1] + ((g * (255 - a)) >> 8);
                b = v[2] + ((b * (255 - a)) >> 8);
            }
            /* the glass and the gold in front */
            {
                const uint8_t *f = &WIN_FRONT[4 * i];
                a = f[3];
                r = f[0] + ((r * (255 - a)) >> 8);
                g = f[1] + ((g * (255 - a)) >> 8);
                b = f[2] + ((b * (255 - a)) >> 8);
            }
            win_px[i] = (uint16_t)unsw(pack(r, g, b));
        }
    lcd_blit(WIN_X, WIN_Y, WIN_W, WIN_H, win_px);
}
