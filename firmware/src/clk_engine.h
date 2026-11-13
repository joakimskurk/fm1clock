/* SPDX-License-Identifier: GPL-3.0-only */
/* Copyright (C) 2026 Joakim (joakimskurk) */
/* FM-1 Clock's sound, in the audio interrupt, for two clocks: a gong of FM carriers (the first K_FM with a modulator
 * each), two banks of NT sine operators for the ticks and the mechanism's clicks, and for the cuckoo clock its two
 * pipes (an FM pair each, with their body partials), every one of them computed in every frame, sounding or not.
 * That is the point: the chip is full, all of the time. A governor keeps it full and no fuller: it measures each
 * render against the crystal and renders as many of the gong's carriers (strongest first) as fit in LOAD_PCT of the
 * time a block has. The tables (firmware/gen/clk_tables.h) are fitted to recordings of a real 31-day pendulum clock
 * striking on a coil gong (tools/analyze_ref.py, tools/fit_model.py) and of a Black Forest cuckoo clock
 * (tools/analyze_cuckoo.py, tools/fit_cuckoo.py).
 *
 *   eng_init()                        the sine table, the wall clock's operators (main, before the audio runs)
 *   eng_load(clock)                   another clock's operators, all silent (the ISR, when eng_want changes)
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
typedef struct {                                /* a click: NT operators, its pan (Q8 left, right), its rise (Q15)
                                                   and how fast; its sound and steps of CLK_SUB frames since it began
                                                   (its noise operators take another frequency every SND_HOP of them;
                                                   an operator sounds from SND_DLY of them on, at its level held) */
    op_t o[NT];
    int32_t gl, gr, att, atk;
    uint32_t snd, step;
    uint32_t held[NT];
} bank_t;
typedef struct {                                /* a pipe: an FM pair at its pitch (1:1), its body, its bellows */
    uint32_t ph, mph, inc, idx, pos, n, nb;
    const uint32_t *env;
    uint32_t bph[4], binc[4], brel[4];
} pipe_t;
typedef struct {                                /* a clock's gong: its carriers and its modulators */
    uint32_t ng;
    const uint32_t *inc, *amp, *dec, *decb, *ph, *finc, *fi0, *fdec, *fb;
} gong_tab_t;
static const gong_tab_t GONGS[2] = {
    {NG, G_INC, G_AMP, G_DEC, G_DEC_BLOCK, G_PH, F_INC, F_I0, F_DEC, F_B},          /* the wall clock's coil gong */
    {NGB, GB_INC, GB_AMP, GB_DEC, GB_DEC_BLOCK, GB_PH, FB_INC, FB_I0, FB_DEC, FB_B},   /* the cuckoo's wire gong */
};
enum { SND_A_TICK, SND_A_TOCK, SND_B_TICK, SND_B_WARN, SND_B_DOOR, SND_B_SHUT };
static const uint32_t *const SND_INC[NSND] = {T0_INC, T1_INC, T2_INC, T3_INC, T4_INC, T5_INC};
static const uint32_t *const SND_AMP[NSND] = {T0_AMP, T1_AMP, T2_AMP, T3_AMP, T4_AMP, T5_AMP};
static const uint32_t *const SND_DEC[NSND] = {T0_DEC, T1_DEC, T2_DEC, T3_DEC, T4_DEC, T5_DEC};
static const uint32_t *const SND_PH[NSND] = {T0_PH, T1_PH, T2_PH, T3_PH, T4_PH, T5_PH};
static const uint16_t *const SND_HOP[NSND] = {T0_HOP, T1_HOP, T2_HOP, T3_HOP, T4_HOP, T5_HOP};
static const uint32_t *const SND_SPR[NSND] = {T0_SPR, T1_SPR, T2_SPR, T3_SPR, T4_SPR, T5_SPR};
static const uint8_t *const SND_DLY[NSND] = {T0_DLY, T1_DLY, T2_DLY, T3_DLY, T4_DLY, T5_DLY};
#define NG_MAX (NG > NGB ? NG : NGB)

static op_t gop[NG_MAX] __attribute__((section(".pool")));
static uint32_t gdec_blk[NG_MAX] __attribute__((section(".pool")));
static pipe_t cpipe[2];
static uint32_t drone_ph[DRONE_N];              /* the cuckoo's train running: its drone's partials' phases */
static int32_t drone_lvl, drone_on;             /* its level (Q15), going up or down to 0 or full */
#define RATTLE_G 8u
static op_t rattle[RATTLE_G];                   /* and its rattle: clicks at random, eight ringing at most */
static uint32_t rattle_next;
static uint32_t eng_clock;                      /* (the ISR's) the clock sounding: 0 the wall clock, 1 the cuckoo */
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
    uint32_t clock;                             /* the clock sounding */
} eng_st = {NG_START, 0, 0, 0, 0, 0};
static volatile uint32_t eng_tick_lvl = 256u;   /* the ticks' level, Q8 (main) */
static volatile uint32_t eng_gong_lvl = 256u;   /* the gong's level, Q8 (main) */
static volatile uint32_t eng_fixed_ng;          /* nonzero: render this many, no governor (host tests) */
static volatile uint32_t eng_want;              /* (main) the clock to sound */
static volatile uint32_t eng_hits;              /* (ISR) blows so far, sounded or silent: the keys flash on them */
static volatile uint32_t eng_door;              /* (ISR) the cuckoo's door: 1 open, the bird out */
static volatile uint32_t eng_bow;               /* (ISR) the pipes blown so far: the bird calls to each */
static volatile uint32_t eng_pipe;              /* (ISR) the last of them: 0 the high, 1 the low */
static volatile uint32_t eng_calls;             /* (ISR) the calls so far (their high pipes): the weight goes down */

/* EV_TICK, EV_TOCK: arg the sound, from the left, the right; EV_CLICK: arg the sound | its level (Q15) << 8, from the
 * middle; EV_HIT: arg the hammer's strength (Q15); EV_PIPE: arg 0 the high pipe, 1 the low; EV_DOOR: arg 1 open, 0
 * shut; EV_FLASH: a blow that does not sound (the strike off): only the keys see it; EV_RUN: arg 1 the cuckoo's
 * train starts to run (its drone comes up), 0 it stops */
enum { EV_TICK, EV_TOCK, EV_CLICK, EV_HIT, EV_PIPE, EV_DOOR, EV_FLASH, EV_RUN };
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

static void eng_load(uint32_t c)                /* a clock's operators, all of them still */
{
    const gong_tab_t *t = &GONGS[c];
    uint32_t k, j;
    for (k = 0; k < NG_MAX; k++) {
        gop[k].ph = k < t->ng ? t->ph[k] : 0;
        gop[k].inc = k < t->ng ? t->inc[k] : 0;
        gop[k].amp = 0;
        gop[k].dec = k < t->ng ? t->dec[k] : 0;
        gdec_blk[k] = k < t->ng ? t->decb[k] : 0;
    }
    for (k = 0; k < K_FM; k++) {
        gmod[k].ph = 0;
        gmod[k].inc = t->finc[k];
        gmod[k].env = 0;
        gmod[k].i0 = t->fi0[k];
        gmod[k].dec = t->fdec[k];
        gmod[k].b = t->fb[k];
    }
    for (k = 0; k < 2u; k++)
        for (j = 0; j < NT; j++)
            tbank[k].o[j].amp = 0;
    for (k = 0; k < 2u; k++) {
        pipe_t *pp = &cpipe[k];
        pp->inc = PIPE_INC[k];
        pp->idx = PIPE_IDX[k];
        pp->env = k ? PIPE_ENV1 : PIPE_ENV0;
        pp->n = k ? PIPE_ENV1_N : PIPE_ENV0_N;
        pp->pos = pp->n;                        /* still */
        pp->nb = PIPE_NBODY[k];
        for (j = 0; j < 4u; j++) {
            pp->binc[j] = PIPE_BODY_INC[4u * k + j];
            pp->brel[j] = PIPE_BODY_REL[4u * k + j];
            pp->bph[j] = 0;
        }
    }
    drone_lvl = drone_on = 0;
    for (k = 0; k < RATTLE_G; k++)
        rattle[k].amp = 0;
    eng_clock = c;
    eng_st.clock = c;
    if (eng_st.ng > t->ng) eng_st.ng = t->ng;
}

static void eng_init(void)
{
    uint32_t i;
    for (i = 0; i < 4096u; i++) {
        SINT[i] = SINQ[i];
        SINT[4096u + i] = SINQ[4096u - i];
        SINT[8192u + i] = (int16_t)-SINQ[i];
        SINT[12288u + i] = (int16_t)-SINQ[4096u - i];
    }
    eng_load(0);
}

/* ---- events */
static inline uint32_t eng_stray(uint32_t inc, uint32_t spr)   /* a frequency within +- spr of inc, at random */
{
    return inc + (uint32_t)(int32_t)(((int64_t)((int32_t)(eng_rnd() & 65535u) - 32768) * (int32_t)spr) >> 15);
}

static void eng_tick(uint32_t snd, uint32_t g15, int32_t gl, int32_t gr)   /* a click sound (SND_...) at g15 (Q15) */
{
    bank_t *b = &tbank[tbank_next];
    const uint32_t *I = SND_INC[snd], *A = SND_AMP[snd], *D = SND_DEC[snd];
    const uint16_t *H = SND_HOP[snd];
    const uint8_t *L = SND_DLY[snd];
    uint32_t k, g = (g15 * (30147u + (eng_rnd() & 4095u))) >> 15;   /* this tick: 0.92 .. 1.04 of it */
    tbank_next ^= 1u;
    for (k = 0; k < T_NDET[snd]; k++) {         /* what comes back every time (the crack, the case's knock): its phase */
        op_t *o = &b->o[k];
        o->ph = SND_PH[snd][k];
        o->inc = I[k];
        o->amp = (uint32_t)(((uint64_t)A[k] * g) >> 15);
        o->dec = D[k];
    }
    for (; k < NT; k++) {                       /* the rest: a phase of its own, a little off in pitch and level; the
                                                   noise operators (SND_HOP) anywhere in their band */
        op_t *o = &b->o[k];
        int32_t dp = (int32_t)(eng_rnd() & 255u) - 128;
        o->ph = eng_rnd();
        o->inc = I[k] + (uint32_t)(int32_t)(((int64_t)(I[k] >> 1) * dp) >> (T_JSH[snd] + 6));   /* +- 2^-T_JSH */
        o->amp = (uint32_t)(((uint64_t)A[k] * ((g * (28672u + (eng_rnd() & 8191u))) >> 15)) >> 15);   /* 0.88 .. 1.12 */
        o->dec = D[k];
        if (H[k])
            o->inc = eng_stray(I[k], SND_SPR[snd][k]);
    }
    for (k = 0; k < NT; k++)                    /* (the ones that come later: still till then) */
        if (L[k]) {
            b->held[k] = b->o[k].amp;
            b->o[k].amp = 0;
        }
    b->gl = gl;
    b->gr = gr;
    b->att = 0;
    b->atk = (int32_t)T_ATK[snd];
    b->snd = snd;
    b->step = 0;
}

static void eng_strike(uint32_t g15)            /* the hammer hits the gong, at g15 (Q15) of its strength */
{
    const gong_tab_t *t = &GONGS[eng_clock];
    uint32_t k;
    for (k = 0; k < t->ng; k++) {
        op_t *o = &gop[k];
        uint32_t nw = (uint32_t)(((uint64_t)t->amp[k] * g15) >> 15), old = o->amp;
        if (old < (nw >> 1)) {                  /* (nearly) still: the hit as recorded, its own phase */
            o->amp = nw + (old >> 2) + (old >> 3);
            o->ph = t->ph[k];
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
    uint32_t k, j, t = b->step++;
    const uint32_t *I = SND_INC[b->snd], *W = SND_SPR[b->snd];
    const uint16_t *H = SND_HOP[b->snd];
    const uint8_t *L = SND_DLY[b->snd];
    for (k = 0; k < NT; k++) {
        op_t *o = &b->o[k];
        uint32_t p, d, am, dc;
        if (L[k] == t && t) {                   /* its turn: it starts, from nothing (a mode: its phase ran on
                                                   meanwhile to there; noise: up or down, at random) */
            o->amp = b->held[k];
            if (k >= T_NDET[b->snd])
                o->ph = (eng_rnd() & 0x80000000u) - o->inc;
        }
        if (H[k] && !((t + k) & (H[k] - 1u)) && o->amp)   /* a noise operator: another frequency in its band, now and
                                                             then, its phase unbroken (noise, not a line) */
            o->inc = eng_stray(I[k], W[k]);
        p = o->ph, d = o->inc, am = o->amp, dc = o->dec;
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

static void pipes_render(int32_t *acc)          /* the cuckoo's two pipes, CLK_SUB frames (still: level 0) */
{
    uint32_t k, i, j;
    for (k = 0; k < 2u; k++) {
        pipe_t *pp = &cpipe[k];
        uint32_t p = pp->ph, mp = pp->mph, d = pp->inc;
        int32_t a = pp->pos < pp->n ? (int32_t)(pp->env[pp->pos] >> 16) : 0, I = (int32_t)pp->idx;
        if (pp->pos < pp->n)
            pp->pos++;
        for (i = 0; i < CLK_SUB; i++) {         /* the FM pair: the pipe's tone */
            mp += d;
            p += d;
            acc[i] += SINT[(p + (uint32_t)(SINT[mp >> 18] * I)) >> 18] * a;
        }
        pp->ph = p;
        pp->mph = mp;
        for (j = 0; j < pp->nb; j++) {          /* its body: the bellows and the wood */
            uint32_t bp = pp->bph[j], bi = pp->binc[j];
            int32_t ab = (a * (int32_t)pp->brel[j]) >> 15;
            for (i = 0; i < CLK_SUB; i++) {
                bp += bi;
                acc[i] += SINT[bp >> 18] * ab;
            }
            pp->bph[j] = bp;
        }
    }
}

static void drone_render(int32_t *acc)          /* the train running, CLK_SUB frames: its drone, its rattle */
{
    uint32_t k, i;
    if (drone_on)
        drone_lvl = drone_lvl + (int32_t)DRONE_RISE > 32767 ? 32767 : drone_lvl + (int32_t)DRONE_RISE;
    else
        drone_lvl = drone_lvl > (int32_t)DRONE_FALL ? drone_lvl - (int32_t)DRONE_FALL : 0;
    for (k = 0; k < DRONE_N; k++) {
        uint32_t p = drone_ph[k], d = DRONE_INC[k];
        int32_t a = ((int32_t)(DRONE_AMP[k] >> 16) * drone_lvl) >> 15;
        for (i = 0; i < CLK_SUB; i++) {
            p += d;
            acc[i] += SINT[p >> 18] * a;
        }
        drone_ph[k] = p;
    }
    if (drone_lvl && (eng_rnd() & 65535u) < RATTLE_P16) {   /* a click of the wheels, the fly: at random */
        op_t *o = &rattle[rattle_next];
        uint32_t r = eng_rnd() & 65535u, j = 0;
        while (j + 1u < RATTLE_N && r >= RATTLE_CUM[j])
            j++;
        rattle_next = (rattle_next + 1u) % RATTLE_G;
        o->ph = eng_rnd();
        o->inc = RATTLE_INC[j];
        o->amp = (uint32_t)(((uint64_t)RATTLE_AMP * (13107u + (eng_rnd() % 19661u))) >> 15);   /* 0.4 .. 1 */
        o->dec = RATTLE_DEC;
    }
    for (k = 0; k < RATTLE_G; k++) {            /* (all eight, ringing or not) */
        op_t *o = &rattle[k];
        uint32_t p = o->ph, d = o->inc, am = o->amp;
        int32_t *q = acc;
        for (i = 0; i < CLK_SUB; i += CLK_TSTEP) {
            int32_t a = (((int32_t)(am >> 16)) * drone_lvl) >> 15;
            p += d; q[0] += SINT[p >> 18] * a;
            p += d; q[1] += SINT[p >> 18] * a;
            p += d; q[2] += SINT[p >> 18] * a;
            p += d; q[3] += SINT[p >> 18] * a;
            q += 4;
            am = mulhi(am, o->dec);
        }
        o->ph = p;
        o->amp = am;
    }
}

static uint32_t clk_now(void);

static void eng_event(const ev_t *e)
{
    switch (e->type) {
    case EV_TICK: eng_tick(e->arg, 32767u, 256, 150); break; /* left: the pendulum's left end */
    case EV_TOCK: eng_tick(e->arg, 32767u, 150, 256); break; /* right */
    case EV_CLICK: {                            /* the train, the door; from the middle (the cuckoo's as recorded) */
        int32_t g = (e->arg & 255u) >= SND_B_TICK ? 256 : 220;
        eng_tick(e->arg & 255u, e->arg >> 8, g, g);
        break;
    }
    case EV_HIT:
        eng_strike(e->arg);
        eng_hits++;
#ifdef ENG_ON_HIT
        ENG_ON_HIT(e);                          /* (the host's log: the tests count the blows) */
#endif
        break;
    case EV_PIPE:
        cpipe[e->arg & 1u].pos = 0;
        cpipe[e->arg & 1u].ph = cpipe[e->arg & 1u].mph = 0;
        eng_pipe = e->arg & 1u;
        if (!eng_pipe)
            eng_calls++;
        eng_bow++;
#ifdef ENG_ON_PIPE
        ENG_ON_PIPE(e);
#endif
        break;
    case EV_DOOR: eng_door = e->arg; break;
    case EV_RUN: drone_on = (int32_t)e->arg; break;
    case EV_FLASH:
        eng_hits++;
#ifdef ENG_ON_FLASH
        ENG_ON_FLASH(e);
#endif
        break;
    }
}

static void eng_render(int32_t *out, uint32_t n, const ev_t *ev, uint32_t nev)
{
    int32_t acc[CLK_SUB], ta[CLK_SUB], tb[CLK_SUB];
    uint32_t s, i, k, ng = eng_fixed_ng ? eng_fixed_ng : eng_st.ng, pk = 0, t0 = clk_now(), dt, ngc;
    int32_t gl = (int32_t)eng_gong_lvl, tl = (int32_t)eng_tick_lvl;
    if (eng_want != eng_clock)                  /* another clock: its operators, from silence */
        eng_load(eng_want & 1u);
    ngc = GONGS[eng_clock].ng;
    if (ng < K_FM) ng = K_FM;
    if (ng > ngc) ng = ngc;
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
        pipes_render(acc);
        drone_render(acc);
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
    for (k = ng; k < ngc; k++) {                /* the carriers not rendered ring down and turn on all the same: when
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
        } else if (dt + LOAD_TARGET / 50u < LOAD_TARGET && cur < ngc) {
            uint32_t add = 1u + (cur * ((LOAD_TARGET - dt) >> 4)) / (LOAD_TARGET >> 4) / 4u;
            cur += add > 8u ? 8u : add;
        }
        if (cur > ngc) cur = ngc;
        eng_st.ng = cur;
    }
}
