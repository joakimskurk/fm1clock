/* SPDX-License-Identifier: GPL-3.0-only */
/* FM1 Clock's pictures, for three clocks, all on one panel wall. The wall clock: the design as the background
 * (firmware/gen/clk_art.h, tools/gen_art.py), and over it what moves: the hands (polygons, 4 x 4 samples a pixel) and the pendulum (the rod,
 * the bob with its own shading, both behind the glass: its reflections and the gold go over them). The cuckoo clocks:
 * this firmware's own chalet and classic (firmware/gen/clk_art_cuckoo.h, tools/gen_art_cuckoo.py) with their big
 * dials and the same hands; its door, turned on its hinge in perspective, and the bird, coming forward out of the dark and bowing
 * to its call; and below the house what hangs from it: the pendulum (a stick and its bob, swinging behind the rest,
 * close to the wall), the two chains over their sprockets, each with a pine-cone weight on one end and a ring on the
 * other, and the house's balcony and apron in front of it all. The regions are drawn again, each into a buffer of
 * its own and sent by DMA: the dial's middle when the hands move, the window (or the space under the house) when the
 * pendulum does, the door when it or the bird moves.
 *
 *   draw_clock                        the clock to draw: 0 the wall clock, 1 the chalet cuckoo, 2 the classic one
 *   draw_all()                        the whole screen once
 *   draw_dial(hour, minute)           the hands at these angles (2^32 = a turn, from 12 clockwise)
 *   draw_window(theta)                the wall clock's pendulum at this angle (2^32 = a turn, + = to the right)
 *   draw_door(open, out, bow, beak)   the cuckoo's door open by open, the bird out by out, bowing by bow (0..256),
 *                                     its beak open or shut
 *   draw_chains(d_go, d_ck)           the chains with their weights let down by d (1/256 px) from wound up
 *   draw_lower(theta)                 the cuckoo's pendulum at this angle */
#include "clk_art.h"
#include "clk_art_cuckoo.h"

#define FX 256                                  /* coordinates in 1/256 px */
#define DIAL_R 36                               /* the hands stay within this of the hub (px), at most */
#define DIAL_W (2 * DIAL_R)
#define PEND_L256 (BOB_Y256 - HUB_Y256)         /* the hub to the bob's centre: the pendulum hangs from behind it */

/* the two faces: the background they are on, the hub, how far the hands reach, their size (Q8) and colours */
typedef struct {
    const uint16_t *bg;
    int32_t bx, by, bw, bh, hx, hy, r, scale;
    uint32_t lit, dark;
} face_t;
static const face_t FACES[3] = {
    {BG_SW, BG_X, BG_Y, BG_W, BG_H, HUB_X256, HUB_Y256, 36, 256, RGB(74, 70, 82), RGB(18, 16, 22)},
    {CK0_HOUSE, CB_X, CB_Y, CB_W, CB_H, CK_HUB_X256, CK_HUB_Y256, 26, 194, RGB(92, 64, 42), RGB(34, 22, 14)},
    {CK1_HOUSE, CB_X, CB_Y, CB_W, CB_H, CK_HUB_X256, CK_HUB_Y256, 26, 194, RGB(92, 64, 42), RGB(34, 22, 14)},
};
/* the two cuckoo clocks: one layout (clk_art_cuckoo.h), their pictures their own; both on the panel wall */
typedef struct {
    const uint16_t *house, *lowall, *drbg;      /* the house on the wall, the wall below it, round the door open */
    const uint8_t *front, *leaf, *bob;          /* the house in front of what hangs, the door's leaf, the bob */
    uint8_t stick[6];                           /* the pendulum's stick: its lit side, its other (R G B) */
} ck_art_t;
static const ck_art_t CK_ART[2] = {
    {CK0_HOUSE, CK0_LOWALL, CK0_DRBG, CK0_FRONT, CK0_LEAF, CK0_BOB, {196, 132, 72, 138, 84, 40}},   /* the chalet */
    {CK1_HOUSE, CK1_LOWALL, CK1_DRBG, CK1_FRONT, CK1_LEAF, CK1_BOB, {150, 70, 44, 88, 34, 20}},    /* the classic */
};
static const ck_art_t *ck = &CK_ART[0];
static uint32_t draw_clock;
static const face_t *face = &FACES[0];

static uint16_t dial_px[DIAL_W * DIAL_W] __attribute__((section(".pool")));
static uint16_t win_px[WIN_W * WIN_H] __attribute__((section(".pool")));
static int32_t dial_x0, dial_y0, dial_w;

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

static uint32_t lo_dirty;                       /* the cuckoo's window: everything again */

/* what is behind everything drawn over the clock (the margins' words): the clock's picture where it is, round it
 * the panel wall all three clocks hang on */
static inline uint16_t bg_px(uint32_t x, uint32_t y)
{
    if (x - (uint32_t)face->bx < (uint32_t)face->bw && y - (uint32_t)face->by < (uint32_t)face->bh)
        return face->bg[(y - (uint32_t)face->by) * (uint32_t)face->bw + (x - (uint32_t)face->bx)];
    return CK_WALL_SW[y * CK_WALL_TW + x % CK_WALL_TW];
}
static void bg_fill(uint32_t x, uint32_t y, uint32_t w, uint32_t h)   /* (in strips through dial_px) */
{
    uint32_t r = DIAL_W * DIAL_W / w, y0, i, j;
    for (y0 = 0; y0 < h; y0 += r) {
        uint32_t n = h - y0 < r ? h - y0 : r;
        lcd_sync();
        for (j = 0; j < n; j++)
            for (i = 0; i < w; i++)
                dial_px[j * w + i] = bg_px(x + i, y + y0 + j);
        lcd_blit(x, y + y0, w, n, dial_px);
    }
    lcd_sync();
}

static void draw_all(void)
{
    uint32_t y, i, bw, bh;
    face = &FACES[draw_clock < 3u ? draw_clock : 0u];
    bw = (uint32_t)face->bw;
    bh = (uint32_t)face->bh;
    lcd_sync();
    ck = &CK_ART[draw_clock == 2u ? 1 : 0];
    bg_fill(0, 0, 240, 240);                    /* the panel wall the clock hangs on, all of the screen */
    for (y = 0; y < bh; y += 32u) {             /* in strips through RAM: the screen's DMA reads RAM only (lcd.c) */
        uint32_t h = bh - y < 32u ? bh - y : 32u;
        lcd_sync();
        for (i = 0; i < h * bw; i++)
            dial_px[i] = face->bg[y * bw + i];
        lcd_blit((uint32_t)face->bx, (uint32_t)face->by + y, bw, h, dial_px);
    }
    lcd_sync();
    lo_dirty = 1;
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
        int32_t lx = (pc->pt[i][0] * face->scale) >> 8, ly = (pc->pt[i][1] * face->scale) >> 8;
        px[i] = face->hx + ox + ((lx * c + ly * s) >> 15);
        py[i] = face->hy + oy + ((lx * s - ly * c) >> 15);
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
    if (x1 > dial_x0 + dial_w) x1 = dial_x0 + dial_w;
    if (y1 > dial_y0 + dial_w) y1 = dial_y0 + dial_w;
    for (y = y0; y < y1; y++)
        for (x = x0; x < x1; x++) {
            int32_t cov = 0, lit = 0, sy, sx;
            for (sy = 0; sy < 4; sy++)
                for (sx = 0; sx < 4; sx++) {
                    int32_t px = x * 16 + 2 + sx * 4, py = y * 16 + 2 + sy * 4;   /* 1/16 px */
                    if (edges_in(&e[0], px, py) || edges_in(&e[1], px, py)) {
                        cov++;
                        /* across the hand: (p - hub) . (cos, sin); its right side catches the light */
                        if (shade && ((px - (face->hx >> 4)) * c + (py - (face->hy >> 4)) * s) > 1 * 16 * 32767 / 4)
                            lit++;
                    }
                }
            if (cov) {
                uint16_t *d = &dial_px[(y - dial_y0) * dial_w + (x - dial_x0)];
                uint32_t dc = unsw(*d), col;
                if (!shade) {
                    col = mix565(dc, 0, (uint32_t)cov * 90u / 16u);
                } else {
                    uint32_t hc = lit * 2 > cov ? face->lit : face->dark;
                    col = mix565(dc, hc, (uint32_t)cov * 16u);
                }
                *d = (uint16_t)unsw(col);
            }
            (void)k;
        }
}
static void draw_hub(void)                      /* the brass boss over the hands */
{
    int32_t x, y, sx, sy, cx = face->hx >> 4, cy = face->hy >> 4;
    for (y = (face->hy >> 8) - 5; y <= (face->hy >> 8) + 5; y++)
        for (x = (face->hx >> 8) - 5; x <= (face->hx >> 8) + 5; x++) {
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
                uint16_t *d = &dial_px[(y - dial_y0) * dial_w + (x - dial_x0)];
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
    dial_w = 2 * face->r;
    dial_x0 = (face->hx >> 8) - face->r;
    dial_y0 = (face->hy >> 8) - face->r;
    lcd_sync();                                 /* (the last send of this buffer is done) */
    for (y = 0; y < dial_w; y++) {
        const uint16_t *src = face->bg + (uint32_t)(dial_y0 + y - face->by) * (uint32_t)face->bw + (uint32_t)(dial_x0 - face->bx);
        uint16_t *d = &dial_px[y * dial_w];
        int32_t x;
        for (x = 0; x < dial_w; x++)
            d[x] = src[x];
    }
    draw_hand(HOUR, hour, 0);
    draw_hand(MINUTE, minute, 0);
    draw_hand(HOUR, hour, 1);
    draw_hand(MINUTE, minute, 1);
    draw_hub();
    /* to the screen only the round the hands can reach (r + 1 px from the hub, their shadows too), row by row:
       the square's corners never change, and on the cuckoo clock they hold the windows' inner shutters, which
       flickered on the panel as they were sent again every two seconds. The rows the whole width wide at once */
    {
        int32_t rr = (face->r + 1) * (face->r + 1), full0 = -1;
        for (y = 0; y <= dial_w; y++) {
            int32_t dy = 2 * y + 1 - dial_w, half = face->r;   /* (twice the row's offset from the hub) */
            if (y < dial_w)
                while (half > 0 && 4 * half * half + dy * dy > 4 * rr)
                    half--;
            if (y < dial_w && half >= face->r) {   /* a whole row: with the others round it */
                if (full0 < 0)
                    full0 = y;
                continue;
            }
            if (full0 >= 0) {
                lcd_blit((uint32_t)dial_x0, (uint32_t)(dial_y0 + full0), (uint32_t)dial_w, (uint32_t)(y - full0),
                         &dial_px[full0 * dial_w]);
                full0 = -1;
            }
            if (y < dial_w && half > 0)
                lcd_blit((uint32_t)(dial_x0 + face->r - half), (uint32_t)(dial_y0 + y), (uint32_t)(2 * half), 1u,
                         &dial_px[y * dial_w + face->r - half]);
        }
    }
}

/* ---- the pendulum, and its shadow on the wood behind it (the light from the top left, as on the bob and the glass) */
#define SH_DX 768                               /* the shadow's offset: 3 px right, 2.5 px down */
#define SH_DY 640
#define SH_K 170                                /* how dark, /256 */

static int32_t bob_alpha(int32_t sxp, int32_t syp)   /* the bob's alpha (0..255) at sprite coordinates, 1/256 px */
{
    int32_t ix = sxp >> 8, iy = syp >> 8, fx = sxp & 255, fy = syp & 255, top, bot;
    const uint8_t *p0;
    if (sxp < 0 || syp < 0 || ix >= BOB_W - 1 || iy >= BOB_H - 1)
        return 0;
    p0 = &BOB_RGBA[4 * (iy * BOB_W + ix) + 3];
    top = p0[0] * (256 - fx) + p0[4] * fx;
    bot = p0[4 * BOB_W] * (256 - fx) + p0[4 * BOB_W + 4] * fx;
    return (top * (256 - fy) + bot * fy) >> 16;
}
static int32_t rod_cov(int32_t px, int32_t py, int32_t s, int32_t c, int32_t *u_out)   /* 0..256 of the rod */
{
    int32_t u = ((px - HUB_X256) * c - (py - HUB_Y256) * s) >> 15;   /* across it (each term < 2^30: 32 bits do) */
    int32_t t = ((px - HUB_X256) * s + (py - HUB_Y256) * c) >> 15;   /* along it, from the hub down */
    int32_t cov = ROD_N * FX / 2 - (u < 0 ? -u : u) + FX / 2;        /* 1/256 px inside its edge, half a pixel soft */
    *u_out = u;
    if (t >= PEND_L256)
        return 0;
    return cov < 0 ? 0 : cov > FX ? FX : cov;
}

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
    xb = ((rx_top > bx ? rx_top : bx) + BOB_R256 + 4 * FX + SH_DX) >> 8;
    if (xa < WIN_X) xa = WIN_X;
    if (xb > WIN_X + WIN_W) xb = WIN_X + WIN_W;
    for (y = 0; y < WIN_H; y++)
        for (x = xa; x < xb; x++) {
            int32_t i = y * WIN_W + (x - WIN_X), r, g, b, a;
            int32_t px = (x << 8) + 128, py = ((WIN_Y + y) << 8) + 128;
            int32_t u, sxp, syp, cov, k, sh = 0;
            unpack(WIN_BACK[i], &r, &g, &b);
            /* the shadow: the bob and the rod a little to the right and down, four samples soft */
            for (k = 0; k < 4; k++) {
                int32_t qx = px - SH_DX + (k & 1 ? 192 : -192), qy = py - SH_DY + (k & 2 ? 192 : -192), uu;
                int32_t ba = bob_alpha(qx - bx + BOB_CX256 - 128, qy - by + BOB_CY256 - 128);
                int32_t ra = rod_cov(qx, qy, s, c, &uu);
                sh += ba > ra ? ba : ra;
            }
            if (sh) {
                sh = (sh >> 2) * SH_K;                  /* 0 .. 255 * SH_K */
                r -= (r * sh) >> 16;
                g -= (g * sh) >> 16;
                b -= (b * sh) >> 16;
            }
            /* the rod */
            cov = rod_cov(px, py, s, c, &u);
            if (cov) {
                int32_t pos = u + ROD_N * FX / 2 - FX / 2, kk = pos >> 8, f = pos & 255;
                int32_t k0 = kk < 0 ? 0 : kk > ROD_N - 1 ? ROD_N - 1 : kk, k1 = kk + 1 < 0 ? 0 : kk + 1 > ROD_N - 1 ? ROD_N - 1 : kk + 1;
                int32_t rr = (ROD_RGB[3 * k0] * (256 - f) + ROD_RGB[3 * k1] * f) >> 8;
                int32_t rg = (ROD_RGB[3 * k0 + 1] * (256 - f) + ROD_RGB[3 * k1 + 1] * f) >> 8;
                int32_t rb = (ROD_RGB[3 * k0 + 2] * (256 - f) + ROD_RGB[3 * k1 + 2] * f) >> 8;
                r += ((rr - r) * cov) >> 8;
                g += ((rg - g) * cov) >> 8;
                b += ((rb - b) * cov) >> 8;
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

/* ---- the cuckoo clock: below the house. Back to front: the wall, the pendulum, the chains with their weights
 * and rings, the house's lowest leaves (its front). All but the pendulum change only when a chain runs: they are
 * made into lo_front then (premultiplied), and lo_bg is that over the wall (the panel wall, the house's shadow on
 * it: ck->lowall); each frame the pendulum goes between. */
#define LO_X CK_LO_X
#define LO_Y CK_FRONT_Y
#define LO_W CK_LO_W
#define LO_H (240 - CK_FRONT_Y)
#define CK_STICK_W 480                          /* the pendulum's stick, 1/256 px across */
#define CK_PEND_L256 (CK_BOB_Y256 - CK_PIVOT_Y256)

static uint8_t lo_front[LO_W * LO_H * 4] __attribute__((section(".pool")));
static uint16_t lo_bg[LO_W * LO_H] __attribute__((section(".pool")));
static uint16_t lo_px[LO_W * LO_H] __attribute__((section(".pool")));
static uint16_t door_px[CK_DR_W * CK_DR_H];
static int32_t lo_bx0 = LO_X, lo_bx1 = LO_X + LO_W, lo_by1 = 240;   /* what the pendulum covered last */

static inline void lo_over(int32_t x, int32_t y, int32_t r, int32_t g, int32_t b, int32_t a)   /* premultiplied */
{
    uint8_t *d;
    if (x < LO_X || x >= LO_X + LO_W || y < LO_Y || y >= 240)
        return;
    d = &lo_front[4 * ((y - LO_Y) * LO_W + (x - LO_X))];
    d[0] = (uint8_t)(r + ((d[0] * (255 - a)) >> 8));
    d[1] = (uint8_t)(g + ((d[1] * (255 - a)) >> 8));
    d[2] = (uint8_t)(b + ((d[2] * (255 - a)) >> 8));
    d[3] = (uint8_t)(a + ((d[3] * (255 - a)) >> 8));
}
static void lo_chain(int32_t cx, int32_t y_end, int32_t run)   /* a strand down to y_end; run: where its links are */
{
    int32_t y;
    for (y = LO_Y; y <= y_end && y < 240; y++) {
        uint32_t p = (uint32_t)(y - run) & 3u;  /* a link face on (an O, 3 wide), the next edge on (a line) */
        if (p == 1u) {
            lo_over(cx - 1, y, 168, 138, 72, 230);
            lo_over(cx + 1, y, 132, 106, 54, 200);
            lo_over(cx, y, 24, 18, 8, 120);
        } else if (p == 0u || p == 2u) {
            lo_over(cx, y, 210, 178, 104, 255);
            lo_over(cx - 1, y, 60, 48, 24, 90);
            lo_over(cx + 1, y, 46, 36, 18, 80);
        } else {
            lo_over(cx, y, 120, 96, 48, 255);
        }
    }
}
static void lo_weight(int32_t cx, int32_t y_hook)   /* the pine cone, its eye on the chain's last link */
{
    int32_t x, y, x0 = cx - CK_WT_W / 2, y0 = y_hook - 1;
    for (y = 0; y < CK_WT_H; y++)
        for (x = 0; x < CK_WT_W; x++) {
            const uint8_t *q = &CK_WT_RGBA[4 * (y * CK_WT_W + x)];
            if (q[3])
                lo_over(x0 + x, y0 + y, q[0], q[1], q[2], q[3]);
        }
}
static void lo_ring(int32_t cx, int32_t cy)   /* a brass ring, 7 px across, 4 x 4 samples */
{
    int32_t x, y, sx, sy;
    for (y = cy - 5; y <= cy + 5; y++)
        for (x = cx - 5; x <= cx + 5; x++) {
            int32_t cov = 0, lit = 0;
            for (sy = 0; sy < 4; sy++)
                for (sx = 0; sx < 4; sx++) {
                    int32_t dx = (x - cx) * 16 + 2 + sx * 4 - 8, dy = (y - cy) * 16 + 2 + sy * 4 - 8, r2 = dx * dx + dy * dy;
                    if (r2 >= 40 * 40 && r2 <= 60 * 60) {
                        cov++;
                        lit += dx + dy < 0;     /* the light from the top left */
                    }
                }
            if (cov) {
                int32_t a = cov * 255 / 16, l = lit * 2 >= cov;
                lo_over(x, y, (l ? 214 : 142) * a / 255, (l ? 180 : 112) * a / 255, (l ? 100 : 56) * a / 255, a);
            }
        }
}

static void draw_chains(uint32_t d_go, uint32_t d_ck)
{
    int32_t i, x, y, g = (int32_t)(d_go >> 8), k = (int32_t)(d_ck >> 8);
    int32_t c0 = (CK_STRAND0_X256 + 128) >> 8, c1 = (CK_STRAND1_X256 + 128) >> 8;
    int32_t c2 = (CK_STRAND2_X256 + 128) >> 8, c3 = (CK_STRAND3_X256 + 128) >> 8;
    if (g > CK_TRAVEL) g = CK_TRAVEL;
    if (k > CK_TRAVEL) k = CK_TRAVEL;
    for (i = 0; i < LO_W * LO_H * 4; i++)
        lo_front[i] = 0;
    /* the going train's chain (left): its weight on strand 0, its ring on 1; the cuckoo's (right): ring 2, weight 3.
       A chain is one: as the weight goes down, the links run down on its side and up on the ring's */
    lo_chain(c0, CK_W_TOP + g, g);
    lo_chain(c1, CK_RING_LOW - g - 4, -g);
    lo_chain(c2, CK_RING_LOW - k - 4, -k);
    lo_chain(c3, CK_W_TOP + k, k);
    lo_ring(c1, CK_RING_LOW - g);
    lo_ring(c2, CK_RING_LOW - k);
    lo_weight(c0, CK_W_TOP + g);
    lo_weight(c3, CK_W_TOP + k);
    for (y = LO_Y; y < CB_Y + CB_H; y++)        /* the house's lowest leaves in front */
        for (x = LO_X; x < LO_X + LO_W; x++) {
            const uint8_t *q = &ck->front[4 * ((y - CK_FRONT_Y) * CB_W + (x - CB_X))];
            if (q[3])
                lo_over(x, y, q[0], q[1], q[2], q[3]);
        }
    for (i = 0; i < LO_W * LO_H; i++) {         /* over the wall */
        int32_t r, g, b, a = lo_front[4 * i + 3];
        unpack(unsw(ck->lowall[i]), &r, &g, &b);
        lo_bg[i] = (uint16_t)unsw(pack(lo_front[4 * i] + ((r * (255 - a)) >> 8), lo_front[4 * i + 1] + ((g * (255 - a)) >> 8),
                                       lo_front[4 * i + 2] + ((b * (255 - a)) >> 8)));
    }
    lo_dirty = 1;
}

static void draw_lower(uint32_t th)
{
    int32_t s = SINT[th >> 18], c = SINT[(th + 1073741824u) >> 18];
    int32_t bx = CK_PIVOT_X256 + (int32_t)(((int64_t)CK_PEND_L256 * s) >> 15);   /* the bob's centre, 1/256 px */
    int32_t by = CK_PIVOT_Y256 + (int32_t)(((int64_t)CK_PEND_L256 * c) >> 15);
    int32_t rx = CK_PIVOT_X256 + (LO_Y * FX - CK_PIVOT_Y256) * s / c;   /* the stick at the top (32 bits do) */
    int32_t cx0, cx1, cy1, x0, x1, y1, bw, x, y;
    cx0 = ((rx < bx ? rx : bx) >> 8) - 20;      /* what it covers now */
    cx1 = ((rx > bx ? rx : bx) >> 8) + 21;
    cy1 = (by >> 8) + 21;
    if (cx0 < LO_X) cx0 = LO_X;
    if (cx1 > LO_X + LO_W) cx1 = LO_X + LO_W;
    if (cy1 > 240) cy1 = 240;
    if (lo_dirty) {                             /* the chains ran, or the screen is new: all of it */
        x0 = LO_X; x1 = LO_X + LO_W; y1 = 240;
        lo_dirty = 0;
    } else {                                    /* and where it was */
        x0 = cx0 < lo_bx0 ? cx0 : lo_bx0;
        x1 = cx1 > lo_bx1 ? cx1 : lo_bx1;
        y1 = cy1 > lo_by1 ? cy1 : lo_by1;
    }
    lo_bx0 = cx0; lo_bx1 = cx1; lo_by1 = cy1;
    bw = x1 - x0;
    lcd_sync();
    for (y = LO_Y; y < y1; y++)
        for (x = x0; x < x1; x++) {
            int32_t i = (y - LO_Y) * LO_W + (x - LO_X), px = (x << 8) + 128, py = (y << 8) + 128;
            int32_t u = ((px - CK_PIVOT_X256) * c - (py - CK_PIVOT_Y256) * s) >> 15;   /* across the stick */
            int32_t t = ((px - CK_PIVOT_X256) * s + (py - CK_PIVOT_Y256) * c) >> 15;   /* along it */
            int32_t r = 0, g = 0, b = 0, a = 0, cov;
            uint16_t *o = &lo_px[(y - LO_Y) * bw + (x - x0)];
            const uint8_t *f = &lo_front[4 * i];
            if (f[3] == 255) {                  /* (in front of it all: as it is) */
                *o = lo_bg[i];
                continue;
            }
            cov = CK_STICK_W / 2 - (u < 0 ? -u : u) + FX / 2;   /* the stick: wood, its left edge lit */
            if (t < CK_PEND_L256 && cov > 0) {
                cov = cov > FX ? 255 : cov;
                r = ck->stick[u < 0 ? 0 : 3] * cov >> 8;
                g = ck->stick[u < 0 ? 1 : 4] * cov >> 8;
                b = ck->stick[u < 0 ? 2 : 5] * cov >> 8;
                a = cov;
            }
            {                                   /* the leaf: its sprite turned with the stick, between its pixels */
                int32_t sxp = (((px - bx) * c - (py - by) * s) >> 15) + CK_BOB_W * 128 - 128;
                int32_t syp = (((px - bx) * s + (py - by) * c) >> 15) + CK_BOB_H * 128 - 128;
                if (sxp >= 0 && syp >= 0 && (sxp >> 8) < CK_BOB_W - 1 && (syp >> 8) < CK_BOB_H - 1) {
                    int32_t ix = sxp >> 8, iy = syp >> 8, fx = sxp & 255, fy = syp & 255, ch, v[4];
                    const uint8_t *p0 = &ck->bob[4 * (iy * CK_BOB_W + ix)], *p1 = p0 + 4 * CK_BOB_W;
                    for (ch = 0; ch < 4; ch++) {
                        int32_t top = p0[ch] * (256 - fx) + p0[ch + 4] * fx, bot = p1[ch] * (256 - fx) + p1[ch + 4] * fx;
                        v[ch] = (top * (256 - fy) + bot * fy) >> 16;
                    }
                    r = v[0] + ((r * (255 - v[3])) >> 8);
                    g = v[1] + ((g * (255 - v[3])) >> 8);
                    b = v[2] + ((b * (255 - v[3])) >> 8);
                    a = v[3] + ((a * (255 - v[3])) >> 8);
                }
            }
            if (!a) {
                *o = lo_bg[i];
                continue;
            }
            {                                   /* the wall behind it */
                int32_t wr, wg, wb;
                unpack(unsw(ck->lowall[i]), &wr, &wg, &wb);
                r += (wr * (255 - a)) >> 8;
                g += (wg * (255 - a)) >> 8;
                b += (wb * (255 - a)) >> 8;
            }
            r = f[0] + ((r * (255 - f[3])) >> 8);   /* the chains and the house over it */
            g = f[1] + ((g * (255 - f[3])) >> 8);
            b = f[2] + ((b * (255 - f[3])) >> 8);
            *o = (uint16_t)unsw(pack(r, g, b));
        }
    lcd_blit((uint32_t)x0, LO_Y, (uint32_t)bw, (uint32_t)(y1 - LO_Y), lo_px);
}

/* a sprite's premultiplied RGBA at (sx, sy) in 1/256 of its pixels, between them; 0 outside */
static void spr_at(const uint8_t *spr, int32_t w, int32_t h, int32_t sx, int32_t sy, int32_t *v)
{
    int32_t ix = sx >> 8, iy = sy >> 8, fx = sx & 255, fy = sy & 255, ch;
    const uint8_t *p0, *p1;
    if (sx < 0 || sy < 0 || ix >= w - 1 || iy >= h - 1) {
        v[0] = v[1] = v[2] = v[3] = 0;
        return;
    }
    p0 = &spr[4 * (iy * w + ix)];
    p1 = p0 + 4 * w;
    for (ch = 0; ch < 4; ch++) {
        int32_t top = p0[ch] * (256 - fx) + p0[ch + 4] * fx, bot = p1[ch] * (256 - fx) + p1[ch + 4] * fx;
        v[ch] = (top * (256 - fy) + bot * fy) >> 16;
    }
}
static int in_hole(int32_t px, int32_t py)      /* in the doorway (1/256 px) */
{
    int32_t dx = px - CK_HOLE_X256, dy = py - CK_HOLE_Y256;
    if (py > CK_HOLE_BOT256 || dx < -CK_HOLE_R256 || dx > CK_HOLE_R256)
        return 0;
    return dy >= 0 || (dx >> 4) * (dx >> 4) + (dy >> 4) * (dy >> 4) <= (CK_HOLE_R256 >> 4) * (CK_HOLE_R256 >> 4);
}

#define DOOR_OPEN_ANG 1789569707u               /* the door opens to 150 degrees */
#define BOW_ANG 202950000u                      /* the bird bows by 17 degrees */

static void draw_door(uint32_t open, uint32_t out, uint32_t bow, uint32_t beak)
{
    uint32_t phi = (DOOR_OPEN_ANG >> 8) * open, beta = (BOW_ANG >> 8) * bow;
    int32_t c = SINT[(phi + 1073741824u) >> 18], s = SINT[phi >> 18];
    int32_t cb = SINT[(beta + 1073741824u) >> 18], sb = SINT[beta >> 18];
    int32_t sc = 141 + ((115 * (int32_t)out) >> 8);   /* the bird: 0.55 of its size in the dark .. 1 out */
    int32_t inv_sc = (512 * 256) / sc;          /* screen 1/256 px -> its sprite's (twice the screen's) */
    int32_t lum = 110 + ((146 * (int32_t)out) >> 8);   /* and lit as it comes out */
    int32_t fx = CK_HOLE_X256 + 256, fy = CK_HOLE_BOT256 - 384 + ((448 * (int32_t)out) >> 8);   /* its feet */
    int32_t hinge = CK_LEAF_X * 256, inv_c = c > 1200 || c < -1200 ? (1 << 30) / c : 0;
    int32_t yc = (CK_LEAF_Y * 2 + CK_LEAF_H) * 128, persp = (31 * s) >> 15;   /* the free edge nearer: taller */
    const uint8_t *bird = beak ? CK_BIRD1_RGBA : CK_BIRD0_RGBA;
    int32_t x, y;
    lcd_sync();
    for (y = 0; y < CK_DR_H; y++)
        for (x = 0; x < CK_DR_W; x++) {
            int32_t X = CK_DR_X + x, Y = CK_DR_Y + y, px = (X << 8) + 128, py = (Y << 8) + 128, r, g, b, v[4];
            uint16_t *o = &door_px[y * CK_DR_W + x];
            if (!open && !out) {                /* shut: the house as it is */
                *o = ck->house[(Y - CB_Y) * CB_W + (X - CB_X)];
                continue;
            }
            unpack(unsw(ck->drbg[y * CK_DR_W + x]), &r, &g, &b);   /* the gable, the doorway open */
            if (out && (out > 170u || in_hole(px, py))) {   /* the bird: 2 x 2 samples of it turned and scaled */
                int32_t acc[4] = {0, 0, 0, 0}, k;
                for (k = 0; k < 4; k++) {
                    int32_t dx = px + (k & 1 ? 64 : -64) - fx, dy = py + (k & 2 ? 64 : -64) - fy;
                    int32_t qx = (dx * cb + dy * sb) >> 15, qy = (dy * cb - dx * sb) >> 15;   /* turned back */
                    int32_t w4[4], ch;
                    spr_at(bird, CK_BIRD_W, CK_BIRD_H, ((qx * inv_sc) >> 8) + CK_BIRD_FX2 * 256,
                           ((qy * inv_sc) >> 8) + CK_BIRD_FY2 * 256, w4);
                    for (ch = 0; ch < 4; ch++)
                        acc[ch] += w4[ch];
                }
                if (acc[3]) {
                    int32_t a = acc[3] >> 2;
                    r = (((acc[0] >> 2) * lum) >> 8) + ((r * (255 - a)) >> 8);
                    g = (((acc[1] >> 2) * lum) >> 8) + ((g * (255 - a)) >> 8);
                    b = (((acc[2] >> 2) * lum) >> 8) + ((b * (255 - a)) >> 8);
                }
            }
            {                                   /* the leaf, turned about its hinge (shut: over the doorway) */
                int32_t dxh = px - hinge;
                if (inv_c) {
                    int32_t u = (int32_t)(((int64_t)dxh * inv_c) >> 15);   /* across the leaf, from the hinge */
                    if (u >= 0 && u < CK_LEAF_W * 256) {
                        int32_t vy = py - ((((py - yc) * persp) >> 8) * u) / (CK_LEAF_W * 256);
                        spr_at(ck->leaf, CK_LEAF_W, CK_LEAF_H, u - 128, vy - CK_LEAF_Y * 256 - 128, v);
                        if (v[3]) {
                            int32_t l = c > 0 ? 190 + ((66 * c) >> 15) : 100 + ((-40 * c) >> 15);   /* its back darker */
                            r = ((v[0] * l) >> 8) + ((r * (255 - v[3])) >> 8);
                            g = ((v[1] * l) >> 8) + ((g * (255 - v[3])) >> 8);
                            b = ((v[2] * l) >> 8) + ((b * (255 - v[3])) >> 8);
                        }
                    }
                } else if (dxh >= -192 && dxh < 192 && py >= CK_LEAF_Y * 256 && py < (CK_LEAF_Y + CK_LEAF_H) * 256) {
                    r = 196; g = 140; b = 84;   /* edge on: its thickness */
                }
            }
            *o = (uint16_t)unsw(pack(r, g, b));
        }
    lcd_blit(CK_DR_X, CK_DR_Y, CK_DR_W, CK_DR_H, door_px);
}
