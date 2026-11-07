/* SPDX-License-Identifier: GPL-3.0-only */
/* FM1 Clock's sound, in the audio interrupt: a gong of NG FM carriers (the first K_FM with a modulator each) and two
 * banks of NT sine operators for the ticks, every one of them computed in every frame, sounding or not. That is the
 * point: the chip is full, all of the time. A governor keeps it full and no fuller: it measures each render against
 * the crystal and renders as many of the gong's carriers (strongest first) as fit in LOAD_PCT of the time a block
 * has. The tables (firmware/gen/clk_tables.h) are fitted to a recording of a real 31-day pendulum clock striking
 * on a coil gong (tools/analyze_ref.py, tools/fit_model.py).
 *
 *   eng_init()                        the sine table, the operators (main, before the audio runs)
 *   eng_render(out, n, ev, nev)       n frames (CLK_BLOCK), the events of this block at their frames (the ISR)
 *
 * Integers only: phases of 2^32 a cycle, levels Q31 of the output's full scale, the mix in Q30. */
#include "clk_tables.h"

#ifndef LOAD_PCT
#define LOAD_PCT 78u                            /* the gong renders until the block has used this much of its time */
#endif
#define BLOCK_TICKS 139320u                     /* 256 frames at 44.1 kHz, in 24 MHz crystal ticks */
#define LOAD_TARGET (BLOCK_TICKS / 100u * LOAD_PCT)
#define NG_START 96u                            /* the governor starts low and climbs */

static int16_t SINT[16384] __attribute__((section(".pool")));   /* one cycle, Q15; index = phase >> 18 */

typedef struct { uint32_t ph, inc, amp, dec; } op_t;          /* a sine operator: phase, its step, level, decay */
typedef struct { uint32_t ph, inc, env, i0, dec, b; } mod_t;  /* a modulator: phase, step, index envelope (Q31), ... */
typedef struct { op_t o[NT]; int32_t gl, gr, att, atk; } bank_t;   /* a tick: NT operators, its pan (Q8 left, right),
                                                                     its rise (Q15) and how fast */

static op_t gop[NG] __attribute__((section(".pool")));
static uint32_t gdec_blk[NG] __attribute__((section(".pool")));
static mod_t gmod[K_FM] __attribute__((section(".pool")));
static bank_t tbank[2] __attribute__((section(".pool")));
static uint32_t tbank_next;

/* shared with the main loop: one writer each */
static volatile struct {                        /* (the ISR's; one struct, so fm1-emu reads it in one --dump) */
    uint32_t ng;                                /* carriers rendered (the governor; the host: fixed) */
    uint32_t load;                              /* the last render, crystal ticks */
    uint32_t peak;                              /* the loudest carrier of the last block (Q15): 0 = the gong is still */
    uint32_t worst;                             /* the longest render after the first second */
    uint32_t blocks;                            /* blocks rendered */
} eng_st = {NG_START, 0, 0, 0, 0};
static volatile uint32_t eng_tick_lvl = 256u;   /* the ticks' level, Q8 (main) */
static volatile uint32_t eng_gong_lvl = 256u;   /* the gong's level, Q8 (main) */
static volatile uint32_t eng_fixed_ng;          /* nonzero: render this many, no governor (host tests) */

enum { EV_TICK, EV_TOCK, EV_CLICK, EV_HIT };
typedef struct { uint32_t frame, type, arg; } ev_t;

static uint32_t eng_rng = 0x2545F491u;
static uint32_t eng_rnd(void)
{
    eng_rng ^= eng_rng << 13;
    eng_rng ^= eng_rng >> 17;
    eng_rng ^= eng_rng << 5;
    return eng_rng;
}
static inline uint32_t mulhi(uint32_t a, uint32_t b) { return (uint32_t)(((uint64_t)a * b) >> 32); }

static void eng_init(void)
{
    uint32_t i, k;
    for (i = 0; i < 4096u; i++) {
        SINT[i] = SINQ[i];
        SINT[4096u + i] = SINQ[4096u - i];
        SINT[8192u + i] = (int16_t)-SINQ[i];
        SINT[12288u + i] = (int16_t)-SINQ[4096u - i];
    }
    for (k = 0; k < NG; k++) {
        gop[k].ph = G_PH[k];
        gop[k].inc = G_INC[k];
        gop[k].amp = 0;
        gop[k].dec = G_DEC[k];
        gdec_blk[k] = G_DEC_BLOCK[k];
    }
    for (k = 0; k < K_FM; k++) {
        gmod[k].ph = 0;
        gmod[k].inc = F_INC[k];
        gmod[k].env = 0;
        gmod[k].i0 = F_I0[k];
        gmod[k].dec = F_DEC[k];
        gmod[k].b = F_B[k];
    }
}

/* ---- events */
static void eng_tick(uint32_t snd, uint32_t g15, int32_t gl, int32_t gr)   /* a tick (0) or a tock (1) at g15 (Q15) */
{
    bank_t *b = &tbank[tbank_next];
    const uint32_t *I = snd ? T1_INC : T0_INC, *A = snd ? T1_AMP : T0_AMP, *D = snd ? T1_DEC : T0_DEC;
    uint32_t k, g = (g15 * (30147u + (eng_rnd() & 4095u))) >> 15;   /* this tick: 0.92 .. 1.04 of it */
    tbank_next ^= 1u;
    for (k = 0; k < NT; k++) {                  /* each operator: a phase of its own, a little off in pitch and level */
        op_t *o = &b->o[k];
        int32_t dp = (int32_t)(eng_rnd() & 255u) - 128;
        o->ph = eng_rnd();
        o->inc = I[k] + (uint32_t)(((int32_t)(I[k] >> 10) * dp) >> 7);    /* +-0.1 % */
        o->amp = (uint32_t)(((uint64_t)A[k] * ((g * (28672u + (eng_rnd() & 8191u))) >> 15)) >> 15);   /* 0.88 .. 1.12 */
        o->dec = D[k];
    }
    b->gl = gl;
    b->gr = gr;
    b->att = 0;
    b->atk = (int32_t)T_ATK[snd];
}

static void eng_strike(uint32_t g15)            /* the hammer hits the gong, at g15 (Q15) of its strength */
{
    uint32_t k;
    for (k = 0; k < NG; k++) {
        op_t *o = &gop[k];
        uint32_t nw = (uint32_t)(((uint64_t)G_AMP[k] * g15) >> 15), old = o->amp;
        if (old < (nw >> 1)) {                  /* (nearly) still: the hit as recorded, its own phase */
            o->amp = nw + (old >> 2) + (old >> 3);
            o->ph = G_PH[k];
        } else {                                /* ringing: the two add with unknown phases, |a + b| ~ max + 3/8 min */
            uint32_t hi = old > nw ? old : nw, lo = old > nw ? nw : old;
            o->amp = hi + (lo >> 2) + (lo >> 3);
        }
    }
    for (k = 0; k < K_FM; k++) {                /* the hit's brightness: the modulators' index, from the top */
        gmod[k].env = g15 << 16;
        gmod[k].ph = 0;
    }
}

/* ---- the render, CLK_SUB frames at a time: the gong into acc (Q30), each tick bank into its own */
static uint32_t gong_fm(int32_t *acc)
{
    uint32_t k, i, pk = 0;
    for (k = 0; k < K_FM; k++) {
        op_t *o = &gop[k];
        mod_t *m = &gmod[k];
        uint32_t p = o->ph, d = o->inc, mp = m->ph, md = m->inc, e15 = m->env >> 16;
        int32_t I = (int32_t)((m->i0 * e15) >> 15);                      /* the index now, phase / 2^15 */
        int32_t a = (int32_t)(o->amp >> 16);
        a += (int32_t)(((int64_t)a * (int32_t)((m->b * e15) >> 15)) >> 12);   /* the hit's boost */
        if ((uint32_t)a > pk) pk = (uint32_t)a;
        for (i = 0; i < CLK_SUB; i++) {
            mp += md;
            p += d;
            acc[i] += SINT[(p + (uint32_t)(SINT[mp >> 18] * I)) >> 18] * a;
        }
        o->ph = p;
        o->amp = mulhi(o->amp, o->dec);
        m->ph = mp;
        m->env = mulhi(m->env, m->dec);
    }
    return pk;
}

static uint32_t gong_plain(int32_t *acc, uint32_t from, uint32_t to)
{
    op_t *o = &gop[from], *e = &gop[to];
    uint32_t pk = 0;
    for (; o < e; o++) {
        uint32_t p = o->ph, d = o->inc, i;
        int32_t a = (int32_t)(o->amp >> 16), *q = acc;
        if ((uint32_t)a > pk) pk = (uint32_t)a;
        for (i = 0; i < CLK_SUB; i += 4u) {
            p += d; q[0] += SINT[p >> 18] * a;
            p += d; q[1] += SINT[p >> 18] * a;
            p += d; q[2] += SINT[p >> 18] * a;
            p += d; q[3] += SINT[p >> 18] * a;
            q += 4;
        }
        o->ph = p;
        o->amp = mulhi(o->amp, o->dec);
    }
    return pk;
}

static void tick_render(bank_t *b, int32_t *acc)
{
    uint32_t k, j;
    for (k = 0; k < NT; k++) {
        op_t *o = &b->o[k];
        uint32_t p = o->ph, d = o->inc, am = o->amp, dc = o->dec;
        int32_t *q = acc;
        for (j = 0; j < CLK_SUB; j += CLK_TSTEP) {   /* the level steps every 4 frames: ticks fall fast */
            int32_t a = (int32_t)(am >> 16);
            p += d; q[0] += SINT[p >> 18] * a;
            p += d; q[1] += SINT[p >> 18] * a;
            p += d; q[2] += SINT[p >> 18] * a;
            p += d; q[3] += SINT[p >> 18] * a;
            q += 4;
            am = mulhi(am, dc);
        }
        o->ph = p;
        o->amp = am;
    }
}

static uint32_t clk_now(void);

static void eng_event(const ev_t *e)
{
    switch (e->type) {
    case EV_TICK: eng_tick(0, 32767u, 256, 150); break;       /* left: the pendulum's left end */
    case EV_TOCK: eng_tick(1, 32767u, 150, 256); break;       /* right */
    case EV_CLICK: eng_tick(0, 15000u, 220, 220); break;      /* the strike train lets the hammer go */
    case EV_HIT:
        eng_strike(e->arg);
#ifdef ENG_ON_HIT
        ENG_ON_HIT(e);                          /* (the host's log: the tests count the blows) */
#endif
        break;
    }
}

static void eng_render(int32_t *out, uint32_t n, const ev_t *ev, uint32_t nev)
{
    int32_t acc[CLK_SUB], ta[CLK_SUB], tb[CLK_SUB];
    uint32_t s, i, k, ng = eng_fixed_ng ? eng_fixed_ng : eng_st.ng, pk = 0, t0 = clk_now(), dt;
    int32_t gl = (int32_t)eng_gong_lvl, tl = (int32_t)eng_tick_lvl;
    if (ng < K_FM) ng = K_FM;
    if (ng > NG) ng = NG;
    for (s = 0; s < n; s += CLK_SUB) {
        uint32_t p;
        while (nev && ev->frame < s + CLK_SUB / 2u) {      /* an event: at the nearest step of CLK_SUB frames */
            eng_event(ev);
            ev++;
            nev--;
        }
        for (i = 0; i < CLK_SUB; i++)
            acc[i] = ta[i] = tb[i] = 0;
        p = gong_fm(acc);
        if (p > pk) pk = p;
        p = gong_plain(acc, K_FM, ng);
        if (p > pk) pk = p;
        tick_render(&tbank[0], ta);
        tick_render(&tbank[1], tb);
        for (i = 0; i < CLK_SUB; i++) {
            int32_t g = ((acc[i] >> 15) * gl) >> 8, a, b;
            tbank[0].att += ((32767 - tbank[0].att) * tbank[0].atk) >> 15;    /* the ticks rise over a few ms */
            tbank[1].att += ((32767 - tbank[1].att) * tbank[1].atk) >> 15;
            a = ((((ta[i] >> 15) * tl) >> 8) * tbank[0].att) >> 15;
            b = ((((tb[i] >> 15) * tl) >> 8) * tbank[1].att) >> 15;
            out[2u * (s + i)] += g + ((a * tbank[0].gl + b * tbank[1].gl) >> 8);
            out[2u * (s + i) + 1u] += g + ((a * tbank[0].gr + b * tbank[1].gr) >> 8);
        }
    }
    while (nev) {                               /* (an event past the last step: now) */
        eng_event(ev++);
        nev--;
    }
    for (k = ng; k < NG; k++) {                 /* the carriers not rendered ring down and turn on all the same: when
                                                   the governor takes one back it goes on where it would be */
        gop[k].amp = mulhi(gop[k].amp, gdec_blk[k]);
        gop[k].ph += gop[k].inc * n;
    }
    eng_st.peak = pk;
    dt = clk_now() - t0;
    eng_st.load = dt;
    if (++eng_st.blocks > 172u && dt > eng_st.worst)
        eng_st.worst = dt;
    if (eng_fixed_ng)
        eng_st.ng = ng;
    else {                                      /* the governor: towards LOAD_TARGET, faster down than up */
        uint32_t cur = eng_st.ng;
        if (dt > LOAD_TARGET + LOAD_TARGET / 50u) {
            uint32_t cut = dt > LOAD_TARGET * 5u / 4u ? cur / 4u : 1u + (cur * ((dt - LOAD_TARGET) >> 4)) / (dt >> 4);
            cur = cur > K_FM + cut ? cur - cut : K_FM;
        } else if (dt + LOAD_TARGET / 50u < LOAD_TARGET && cur < NG) {
            uint32_t add = 1u + (cur * ((LOAD_TARGET - dt) >> 4)) / (LOAD_TARGET >> 4) / 4u;
            cur += add > 8u ? 8u : add;
            if (cur > NG) cur = NG;
        }
        eng_st.ng = cur;
    }
}
