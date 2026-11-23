/* SPDX-License-Identifier: GPL-3.0-only */
/* Hamster Synth's sound and its sequencer, in the audio interrupt.
 *
 * The original is a web page: every note a graph of Web Audio oscillators, biquad filters and gains with exponential
 * ramps. Here, in integers:
 *   a hamster     a wavetable of its eight harmonics as its three formant filters and the low-pass leave them at that
 *                 note (tools/gen_ham_tables.py works the filters out, a table a note), its body's sine beside it
 *                 (the page detunes the two against each other), its breath a filtered noise, a room's echo
 *   the hamster voice (hq.hvoice; this firmware's own, the page's is the one above): each hamster its own size,
 *                 vowel and vibrato. A note squeaks as it opens (a chirp from above, the vowel "i"), sings its vowel,
 *                 and closes ("u", a little lower); three tables a note, faded one into the next. Its length follows
 *                 the tempo, the eight sit left to right as on the screen, in a small room of a few reflections
 *   THALL         (THALLHAMSTERGRINDCORE) one voice at a time, an octave down: a sawtooth, a triangle and a square,
 *                 through the page's high gain (its curve, four times oversampled) and its cabinet's filters
 *   Tromster      the drums: kick, snare, hat, clap, three voices of each, a sine or a triangle and filtered noise;
 *                 a fourth of each, the hamster kit: a cheek's pop, a seed's crunch, a sniff, a squeak
 *   envelopes     lines in the base-2 logarithm, a step every control block (HCB frames): that is Web Audio's
 *                 exponentialRampToValueAtTime; pitches the same way (a glide, a bend at the start, the arpeggio)
 *   the sequencer counts frames: a step is 30 / BPM seconds to the frame, its ratchets on their subdivisions
 *
 *   heng_init()                     (main, before the audio runs)
 *   heng_render(out, n)             n frames, added to out (L R, Q15); the audio interrupt
 *   heng_cmd(c)                     main -> the interrupt: a key, a drum, play, stop (HC_*)
 *   heng_ev()                       the interrupt -> main: a step, a note, drums (HE_*); 0: none
 * The patterns, the drums, the song and the tempo are the main loop's (hq): the interrupt only reads them.
 * No float, no 64-bit division (docs/RULES.md). */
#include "ham_tables.h"

#define HCB 16u                                 /* frames a control block */
#define NHV 14u                                 /* hamsters singing at once */
#define NTV 2u                                  /* THALL: the note and the one it cuts off (10 ms) */
#define NDV 8u                                  /* drums sounding at once */
#define NSEG 14u
#define STEP_T 1323000u                         /* a step in frames times BPM: 44100 * 30 */
#define TDLY 192u                               /* THALL: what the page's oversampled distortion takes (4.4 ms), so the
                                                   note's first milliseconds pass under its envelope as they do there */
#define ROOM_N 1676u                            /* the room: one echo after 38 ms, at 0.038 */
#define LG_DRUM_TRY (-7884)                     /* 0.92: a drum's step set */
#define LG_DRUM_VOICE (-4850)                   /* 0.95: another voice of a drum tried */
#define HAM_MAKEUP_SH 7                         /* the mix (Q23) to the output (Q15), twice the page's level */

/* a step of a pattern, 16 bits: one store, so the interrupt never reads half of an edit */
#define ST_ON 0x8000u
#define ST_KEY(s) ((s) & 7u)
#define ST_OCT(s) ((int32_t)(((s) >> 3) & 7u) - 3)          /* -3..+1 */
#define ST_GLIDE(s) (((s) >> 6) & 1u)
#define ST_ACCENT(s) (((s) >> 7) & 1u)
#define ST_ARP(s) (((s) >> 8) & 3u)                          /* 0 off, 1 a fifth up, 2 an octave up */
#define ST_RATCHET(s) ((((s) >> 10) & 3u) + 1u)
#define ST_MAKE(key, oct) ((uint16_t)(ST_ON | (key) | (uint32_t)((oct) + 3) << 3))

enum { DR_KICK, DR_SNARE, DR_HAT, DR_CLAP };
/* main -> interrupt, 32 bits: the command in the top 4 bits */
enum { HC_NOTE = 1, HC_PREVIEW, HC_DRUM, HC_PLAY, HC_STOP, HC_CHOKE, HC_EXT_START, HC_EXT_CLOCK };
#define HCMD(c, a) ((uint32_t)(c) << 28 | (a))
/* HC_NOTE: MIDI note (7 bits) | table key << 7 (3 bits) | velocity << 10 (7 bits; 0: the page's 1.0)
   HC_PREVIEW: step | pattern << 4      HC_DRUM: drum | voice << 2 | 16: a voice tried (0.95; else a step set, 0.92)
   HC_PLAY: 0 a pattern, 1 the song     HC_EXT_START: 0 from the start, 1 on from where it was */
/* interrupt -> main */
enum { HE_STEP = 1, HE_NOTE, HE_DRUM, HE_BAR };
/* HE_STEP: step | pattern << 4 | song position << 8     HE_NOTE: key | MIDI note << 4 | velocity (0..127) << 12
   HE_DRUM: a bit a drum     HE_BAR: the pattern that now plays | song position << 8 */

static const uint8_t HAM_MIDI[8] = {60, 62, 64, 65, 67, 69, 71, 72};

/* what the main loop owns and the interrupt reads */
static struct {
    volatile uint16_t pat[4][16];
    volatile uint8_t drum[4][4];                /* [pattern][drum]: 8 steps, a bit each */
    volatile uint8_t dvoice[4][4];              /* 0..2 */
    volatile uint8_t song[64];
    volatile uint32_t song_len, bpm, thall, drums_on, swing, want_pat, lvl_ham, lvl_drum, off, hvoice;
} hq = {.song_len = 1, .bpm = 120, .lvl_ham = 256, .lvl_drum = 256};

/* ---- the two rings */
static volatile uint32_t hc_q[32], hc_w, hc_r, he_q[64], he_w, he_r;
static void heng_cmd(uint32_t c)                /* (main) */
{
    if (hc_w - hc_r < 32u) {
        hc_q[hc_w & 31u] = c;
        hc_w = hc_w + 1u;
    }
}
static uint32_t heng_ev(void)                   /* (main) */
{
    uint32_t e;
    if (he_r == he_w)
        return 0;
    e = he_q[he_r & 63u];
    he_r = he_r + 1u;
    return e;
}
static void he_put(uint32_t type, uint32_t a)   /* (the interrupt) */
{
    if (he_w - he_r < 64u) {
        he_q[he_w & 63u] = type << 28 | a;
        he_w = he_w + 1u;
    }
}

/* ---- envelopes: lines in the logarithm (or in whatever the caller counts), a step a control block */
enum { SEG_RAMP, SEG_SET, SEG_HOLD };
typedef struct { int32_t tgt; uint16_t len; uint16_t type; } seg_t;
typedef struct {
    int32_t lg, dlg, end;
    uint32_t left;
    uint8_t i, n, done;
    seg_t s[NSEG];
} env_t;

static void env_start(env_t *e, int32_t lg0)
{
    e->lg = lg0;
    e->dlg = 0;
    e->left = 0;
    e->i = e->n = e->done = 0;
}
static void env_seg(env_t *e, uint32_t type, int32_t tgt, uint32_t len)   /* len: control blocks */
{
    if (e->n < NSEG) {
        e->s[e->n].tgt = tgt;
        e->s[e->n].len = (uint16_t)(len > 65535u ? 65535u : len);
        e->s[e->n].type = (uint16_t)type;
        e->n++;
    }
}
static int32_t env_step(env_t *e)
{
    while (!e->left) {
        const seg_t *s;
        if (e->i >= e->n) {
            e->done = 1;
            return e->lg;
        }
        s = &e->s[e->i++];
        if (s->type == SEG_SET || (s->type == SEG_RAMP && !s->len)) {
            e->lg = s->tgt;
            continue;
        }
        if (!s->len)
            continue;
        e->left = s->len;
        e->end = s->type == SEG_HOLD ? e->lg : s->tgt;
        e->dlg = s->type == SEG_HOLD ? 0 : (s->tgt - e->lg) / (int32_t)s->len;
    }
    e->lg += e->dlg;
    if (!--e->left)
        e->lg = e->end;
    return e->lg;
}

static inline uint32_t ex2_m(int32_t lg)        /* the mantissa of 2^(lg / 65536): Q30, 1..2 */
{
    uint32_t f = (uint32_t)lg & 0xFFFFu, i = f >> 8;
    return HAM_EXP2[i] + (((HAM_EXP2[i + 1u] - HAM_EXP2[i]) * (f & 255u)) >> 8);
}
static inline uint32_t ex2_q24(int32_t lg)      /* a level: 2^(lg / 65536), Q24 */
{
    int32_t sh = 6 - (lg >> 16);
    uint32_t m = ex2_m(lg);
    return sh >= 32 ? 0u : sh >= 0 ? m >> sh : sh > -2 ? m << -sh : 0xFFFFFFFFu;
}
static inline uint32_t ex2_inc(int32_t lg)      /* a phase step: 2^(lg / 65536) */
{
    int32_t sh = 30 - (lg >> 16);
    uint32_t m = ex2_m(lg);
    return sh >= 32 ? 0u : sh >= 0 ? m >> sh : m << 1;
}

typedef struct { int32_t x1, x2, y1, y2; } bq_t;
static inline int32_t bq_run(bq_t *q, const int32_t *c, int32_t x)   /* c: b0 b1 b2 a1 a2, Q28 */
{
    int64_t acc = (int64_t)c[0] * x + (int64_t)c[1] * q->x1 + (int64_t)c[2] * q->x2 - (int64_t)c[3] * q->y1 -
                  (int64_t)c[4] * q->y2;
    int32_t y = (int32_t)(acc >> 28);
    q->x2 = q->x1;
    q->x1 = x;
    q->y2 = q->y1;
    q->y1 = y;
    return y;
}

/* ---- the voices */
typedef struct {                                /* a hamster */
    uint8_t on, key, gliding, hv;               /* hv: the hamster voice */
    uint32_t ph, bph, vph, vinc, inc, binc, age;
    int32_t lgp, al, ar, dal, dar, bg0, bg1, xf;   /* xf: how much of t1 (the arpeggio's other note), Q12 */
    const int16_t *t0, *t1, *tq, *tc;           /* (the hamster voice: its squeak's table, its closing's) */
    env_t vow;                                  /* (the hamster voice: -4096 squeak .. 0 its vowel .. 4096 closed) */
    int16_t gre[8], gim[8];                     /* gliding: each harmonic through the formants where it is now */
    int16_t gl, gr;
    env_t amp, br, pv, pb, arp, vib;
} hv_t;
typedef struct {                                /* THALL */
    uint8_t on, soft5, choked, pad;
    uint32_t ph, bph, eph, vph, vinc, inc, binc, einc, age;
    int32_t lgp, a, xprev;
    uint32_t dly_i;
    env_t amp, br, pv, pb, pe, arp, vib, gate;
    bq_t f_str, f_br, f_soft, f_pre, f_chp, f_mid, f_clp;
    int32_t dly[TDLY];
} tv_t;
typedef struct {                                /* a drum: an oscillator, a filtered noise, or both */
    uint8_t on, wave, has_osc, has_nz;
    uint32_t ph, inc, age;
    int32_t ao, an, dao, dan;
    const int32_t *c;
    env_t pitch, oamp, namp;
    bq_t f;
} dv_t;
enum { W_SINE, W_TRI, W_SQUARE };

static hv_t hv[NHV];
static tv_t tv[NTV];
static dv_t dv[NDV];
static int32_t room[2u * ROOM_N] __attribute__((section(".pool")));
static uint32_t room_i, eng_age, nz_seed = 0x2545F491u;
static int32_t nz_prev, nz_gain;
static bq_t nz_bp, nz_lp;
static volatile uint32_t heng_busy;             /* something sounds (main: no save to flash meanwhile) */
static volatile int32_t heng_peak;              /* the last block's highest sample (Q15) */

static inline int32_t nz_white(void)            /* Q15 */
{
    nz_seed = nz_seed * 1664525u + 1013904223u;
    return (int32_t)(nz_seed >> 16) - 32768;
}

#define MS(ms) ((uint32_t)((ms) * 441u / 10u))  /* milliseconds as frames (a constant) */
static inline uint32_t blk(uint32_t frames)     /* frames as control blocks, at least one */
{
    uint32_t b = (frames + HCB / 2u) / HCB;
    return b ? b : 1u;
}
static inline uint32_t umin(uint32_t a, uint32_t b) { return a < b ? a : b; }
static inline uint32_t umax(uint32_t a, uint32_t b) { return a > b ? a : b; }

typedef struct {                                /* a note, as the page's playTone gets it */
    uint32_t key;                               /* the hamster (its formants, its vibrato, its place) */
    int32_t toct;                               /* the octave of its table */
    int32_t lgp;                                /* its pitch: the logarithm of its phase step */
    int32_t vel;                                /* its velocity, a logarithm */
    uint32_t ss;                                /* the step it has, in frames (a ratchet: its part of it) */
    int32_t from;                               /* a glide from this pitch; 0: none */
    uint32_t arp;                               /* 0, 7, 12 */
    uint32_t maxdur;                            /* THALL: its gate in frames; 0: a key (0.62 s) */
} note_t;

/* the arpeggio: up at start, down at 2q, up at 3q, down at the end; those inside the note, in the order of time */
static void arp_env(env_t *e, uint32_t ss, uint32_t dur, uint32_t start, int32_t up)
{
    uint32_t q = ss / 4u, t[4], k, at = 0, last = umin(ss * 98u / 100u, dur * 96u / 100u);
    int32_t v[4] = {up, 0, up, 0};
    t[0] = start; t[1] = 2u * q; t[2] = 3u * q; t[3] = last;
    for (k = 1; k < 4u; k++) {                  /* (a glide can put the start after 2q) */
        uint32_t j = k, tt = t[k];
        int32_t vv = v[k];
        while (j && t[j - 1u] > tt) { t[j] = t[j - 1u]; v[j] = v[j - 1u]; j--; }
        t[j] = tt; v[j] = vv;
    }
    env_start(e, 0);
    for (k = 0; k < 4u; k++) {
        uint32_t b = (t[k] + HCB / 2u) / HCB;
        if (!t[k] || t[k] >= dur)
            continue;
        if (b > at)
            env_seg(e, SEG_HOLD, 0, b - at);
        env_seg(e, SEG_SET, v[k], 0);
        at = umax(at, b);
    }
}

static void ham_on(const note_t *n)
{
    uint32_t i, best = 0, ss = umax(n->ss, MS(80)), dur, t1, t2, gt, ti;
    int32_t v = n->vel < LG_VMIN ? LG_VMIN : n->vel > LG_VMAX ? LG_VMAX : n->vel, low = 0x7FFFFFFF;
    int32_t oc = n->toct < HAM_OCT_LO ? HAM_OCT_LO : n->toct > HAM_OCT_LO + (int32_t)HAM_NOCT - 2 ? HAM_OCT_LO + (int32_t)HAM_NOCT - 2 : n->toct;
    hv_t *h;
    for (i = 0; i < NHV; i++) {                 /* a free voice, or the quietest */
        if (!hv[i].on) { best = i; break; }
        if (hv[i].amp.lg < low) { low = hv[i].amp.lg; best = i; }
    }
    h = &hv[best];
    dur = n->arp ? umin(umax(ss * 108u / 100u, MS(180)), MS(480)) : MS(530);
    h->hv = 0;
    h->key = (uint8_t)n->key;
    h->lgp = n->lgp;
    h->ph = 0;
    ti = n->key * HAM_NOCT + (uint32_t)(oc - HAM_OCT_LO);
    h->t0 = HAM_WT[ti];
    h->bg0 = HAM_BODY_G[ti];
    h->bph = HAM_BODY_PH[ti];
    ti += n->arp == 7u ? 8u * HAM_NOCT : n->arp == 12u ? 1u : 0u;
    h->t1 = HAM_WT[ti];                         /* the arpeggio's other note */
    h->bg1 = HAM_BODY_G[ti];
    h->xf = 0;
    h->gliding = n->from != 0;
    h->vph = 0;
    h->vinc = HAM_VIB_INC[n->key];
    h->gl = HAM_PAN_L[n->key];
    h->gr = HAM_PAN_R[n->key];
    h->al = h->ar = 0;
    h->age = eng_age++;

    env_start(&h->amp, LG_FLOOR);
    t1 = umin(MS(290), dur * 72u / 100u);
    env_seg(&h->amp, SEG_RAMP, LG_H_A1 + v, blk(MS(26)));
    env_seg(&h->amp, SEG_RAMP, LG_H_A2 + v, blk(MS(95) - MS(26)));
    env_seg(&h->amp, SEG_RAMP, LG_H_A3 + v, blk(t1 - MS(95)));
    env_seg(&h->amp, SEG_RAMP, LG_FLOOR, blk(dur - t1));

    env_start(&h->br, LG_FLOOR);
    t2 = umin(MS(320), dur * 80u / 100u);
    env_seg(&h->br, SEG_RAMP, LG_H_BR1 + v, blk(MS(30)));
    env_seg(&h->br, SEG_RAMP, LG_H_BR2, blk(MS(140) - MS(30)));
    env_seg(&h->br, SEG_RAMP, LG_FLOOR, blk(t2 - MS(140)));

    gt = umin(umax(ss * 42u / 100u, MS(35)), MS(160));
    if (n->from) {                              /* the glide: both from the note before (ham_block: while it lasts
                                                   the voice is its eight harmonics, each through the formants) */
        env_start(&h->pv, n->from - n->lgp);
        env_seg(&h->pv, SEG_RAMP, 0, blk(gt));
        env_start(&h->pb, n->from - n->lgp);
        env_seg(&h->pb, SEG_RAMP, 0, blk(gt));
    } else {                                    /* a little sharp at first, the voice more than its body */
        uint32_t tv0 = umin(MS(55), ss * 22u / 100u);
        env_start(&h->pv, LG_H_V0);
        env_seg(&h->pv, SEG_RAMP, 0, blk(tv0));
        if (!n->arp) {                          /* then it drifts: a little up, a little under */
            uint32_t d1 = umin(MS(220), dur * 55u / 100u), d2 = umin(MS(460), dur * 94u / 100u);
            env_seg(&h->pv, SEG_RAMP, LG_DRIFT1, blk(d1 > tv0 ? d1 - tv0 : 1u));
            env_seg(&h->pv, SEG_RAMP, LG_DRIFT2, blk(d2 - d1));
        }
        env_start(&h->pb, LG_H_B0);
        env_seg(&h->pb, SEG_RAMP, 0, blk(umin(MS(50), ss * 20u / 100u)));
    }
    if (n->arp)
        arp_env(&h->arp, ss, dur, n->from ? umax(ss / 4u, gt) : ss / 4u, n->arp == 7u ? LG_FIFTH : LG_OCT);
    else
        env_start(&h->arp, 0);
    env_start(&h->vib, 0);                      /* the vibrato's depth: cents, Q8 */
    t2 = umin(MS(350), dur * 80u / 100u);
    env_seg(&h->vib, SEG_RAMP, n->arp ? 384 : 922, blk(MS(80)));
    env_seg(&h->vib, SEG_RAMP, n->arp ? 256 : 563, blk(t2 > MS(80) ? t2 - MS(80) : 1u));
    h->on = 1;
}

/* the hamster voice: its squeak, its vowel, its closing; its length after the tempo */
static void ham_on_hv(const note_t *n)
{
    uint32_t i, best = 0, ss = umax(n->ss, MS(80)), dur, t1, ti, gt, close;
    int32_t v = n->vel < LG_VMIN ? LG_VMIN : n->vel > LG_VMAX ? LG_VMAX : n->vel, low = 0x7FFFFFFF, sq;
    int32_t oc = n->toct < HAM_OCT_LO ? HAM_OCT_LO : n->toct > HAM_OCT_LO + (int32_t)HAM_NOCT - 2 ? HAM_OCT_LO + (int32_t)HAM_NOCT - 2 : n->toct;
    hv_t *h;
    for (i = 0; i < NHV; i++) {
        if (!hv[i].on) { best = i; break; }
        if (hv[i].amp.lg < low) { low = hv[i].amp.lg; best = i; }
    }
    h = &hv[best];
    dur = n->arp ? umin(umax(ss * 108u / 100u, MS(180)), MS(480)) : umin(umax(2u * ss + MS(60), MS(200)), MS(560));
    h->hv = 1;
    h->key = (uint8_t)n->key;
    h->lgp = n->lgp;
    h->ph = h->bph = 0;
    ti = n->key * HAM_NOCT + (uint32_t)(oc - HAM_OCT_LO);
    h->tq = HAM_HV[3u * ti];
    h->t0 = HAM_HV[3u * ti + 1u];
    h->tc = HAM_HV[3u * ti + 2u];
    h->t1 = n->arp == 7u ? HAM_HV5[ti] : n->arp == 12u ? HAM_HV[3u * (ti + 1u) + 1u] : h->t0;
    h->bg0 = h->bg1 = HAM_HV_BODY[ti];
    h->xf = 0;
    h->gliding = 0;
    h->vph = 0;
    h->vinc = HAM_HV_VIB[n->key];
    h->gl = HAM_SEAT_L[n->key];
    h->gr = HAM_SEAT_R[n->key];
    h->al = h->ar = 0;
    h->age = eng_age++;
    env_start(&h->amp, LG_FLOOR);               /* quick to speak, then as the page's */
    t1 = umin(MS(290), dur * 65u / 100u);
    v += LG_OCT / 2;                            /* (3 dB more: its notes are shorter, it sings as loud) */
    env_seg(&h->amp, SEG_RAMP, LG_H_A1 + v, blk(MS(8)));
    env_seg(&h->amp, SEG_RAMP, LG_H_A2 + v, blk(MS(70) - MS(8)));
    env_seg(&h->amp, SEG_RAMP, LG_H_A3 + v, blk(t1 > MS(70) ? t1 - MS(70) : 1u));
    env_seg(&h->amp, SEG_RAMP, LG_FLOOR, blk(dur - t1));
    env_start(&h->br, LG_FLOOR);                /* the squeak's "tsk": a short high noise */
    env_seg(&h->br, SEG_RAMP, LG_H_BR1 + LG_OCT + v, blk(66));
    env_seg(&h->br, SEG_RAMP, LG_FLOOR, blk(MS(25)));
    sq = HAM_HV_SQUEAK[n->key] + (n->vel > 9000 ? HAM_HV_SQUEAK[n->key] / 2 : 0);   /* (an accent: a bigger squeak) */
    gt = umin(umax(ss * 42u / 100u, MS(35)), MS(160));
    close = dur * 70u / 100u;
    if (n->from) {                              /* a glide: from the note before, no squeak */
        env_start(&h->pv, n->from - n->lgp);
        env_seg(&h->pv, SEG_RAMP, 0, blk(gt));
        env_start(&h->pb, n->from - n->lgp);
        env_seg(&h->pb, SEG_RAMP, 0, blk(gt));
        env_start(&h->vow, 0);
    } else {                                    /* the squeak: a chirp from above, the vowel "i" */
        env_start(&h->pv, sq);
        env_seg(&h->pv, SEG_RAMP, 0, blk(MS(35)));
        env_start(&h->pb, sq / 2);
        env_seg(&h->pb, SEG_RAMP, 0, blk(MS(30)));
        env_start(&h->vow, -4096);
        env_seg(&h->vow, SEG_RAMP, 0, blk(MS(60)));
        gt = MS(60);
    }
    if (n->arp) {
        arp_env(&h->arp, ss, dur, umax(ss / 4u, n->from ? gt : MS(40)), n->arp == 7u ? LG_FIFTH : LG_OCT);
    } else {                                    /* it closes: "u", a little lower */
        env_start(&h->arp, 0);
        env_seg(&h->pv, SEG_HOLD, 0, blk(close > gt ? close - gt : 1u));
        env_seg(&h->pv, SEG_RAMP, LG_HV_FALL, blk(dur - close));
        env_seg(&h->vow, SEG_HOLD, 0, blk(close > gt ? close - gt : 1u));
        env_seg(&h->vow, SEG_RAMP, 4096, blk(dur - close));
    }
    env_start(&h->vib, 0);                      /* its trill: quick, a little wider than the page's (cents, Q8) */
    env_seg(&h->vib, SEG_RAMP, 2560, blk(MS(90)));
    env_seg(&h->vib, SEG_RAMP, 4608, blk(dur * 80u / 100u > MS(90) ? dur * 80u / 100u - MS(90) : 1u));
    h->on = 1;
}

static void thall_on(const note_t *n)
{
    uint32_t i, best = 0, ss = umax(n->ss, MS(80)), dur, gt, t1, t2;
    int32_t v = n->vel < LG_VMIN ? LG_VMIN : n->vel > LG_VMAX ? LG_VMAX : n->vel;
    tv_t *t;
    for (i = 0; i < NTV; i++)                   /* one at a time: the one that sounds goes, in 10 ms */
        if (tv[i].on && !tv[i].choked) {
            tv[i].choked = 1;
            env_start(&tv[i].gate, 0);
            env_seg(&tv[i].gate, SEG_RAMP, LG_FLOOR, blk(MS(10)));
        }
    for (i = 0; i < NTV; i++) {
        if (!tv[i].on) { best = i; break; }
        if (tv[i].age < tv[best].age) best = i;
    }
    t = &tv[best];
    dur = n->maxdur ? umin(umax(n->maxdur, MS(340)), MS(720)) : MS(620);
    t->lgp = n->lgp;
    t->ph = t->bph = t->eph = t->vph = 0;
    t->vinc = HAM_VIB_INC[n->key];
    t->soft5 = n->arp != 0u;
    t->choked = 0;
    t->a = 0;
    t->xprev = 0;
    t->dly_i = 0;
    for (i = 0; i < TDLY; i++)
        t->dly[i] = 0;
    t->age = eng_age++;
    for (i = 0; i < sizeof(bq_t) / 4u; i++) {
        ((int32_t *)&t->f_str)[i] = 0; ((int32_t *)&t->f_br)[i] = 0; ((int32_t *)&t->f_soft)[i] = 0;
        ((int32_t *)&t->f_pre)[i] = 0; ((int32_t *)&t->f_chp)[i] = 0; ((int32_t *)&t->f_mid)[i] = 0;
        ((int32_t *)&t->f_clp)[i] = 0;
    }
    env_start(&t->gate, 0);
    env_start(&t->amp, LG_FLOOR);
    t1 = umin(MS(180), dur * 42u / 100u);
    t2 = umin(MS(480), dur * 82u / 100u);
    env_seg(&t->amp, SEG_RAMP, LG_T_A1 + v, blk(79));
    env_seg(&t->amp, SEG_RAMP, LG_T_A2 + v, blk(MS(22) - 79u));
    env_seg(&t->amp, SEG_RAMP, LG_T_A3 + v, blk(t1 - MS(22)));
    env_seg(&t->amp, SEG_RAMP, LG_T_A4 + v, blk(t2 - t1));
    env_seg(&t->amp, SEG_RAMP, LG_FLOOR, blk(dur - t2));
    env_start(&t->br, LG_FLOOR);
    t1 = umin(MS(28), dur * 48u / 100u);
    env_seg(&t->br, SEG_RAMP, LG_T_BR1 + v, blk(66));
    env_seg(&t->br, SEG_RAMP, LG_T_BR2 + v, blk(MS(10) - 66u));
    env_seg(&t->br, SEG_RAMP, LG_FLOOR, blk(t1 - MS(10)));
    gt = umin(umax(ss * 42u / 100u, MS(35)), MS(160));
    if (n->from) {
        env_start(&t->pv, n->from - n->lgp); env_seg(&t->pv, SEG_RAMP, 0, blk(gt));
        env_start(&t->pb, n->from - n->lgp); env_seg(&t->pb, SEG_RAMP, 0, blk(gt));
        env_start(&t->pe, n->from - n->lgp); env_seg(&t->pe, SEG_RAMP, 0, blk(gt));
    } else {                                    /* the pick: sharp for a few milliseconds */
        env_start(&t->pv, LG_T_V0); env_seg(&t->pv, SEG_RAMP, 0, blk(MS(9)));
        if (!n->arp) {
            uint32_t d1 = umin(MS(220), dur * 55u / 100u), d2 = umin(MS(460), dur * 94u / 100u);
            env_seg(&t->pv, SEG_RAMP, LG_DRIFT1, blk(d1 - MS(9)));
            env_seg(&t->pv, SEG_RAMP, LG_DRIFT2, blk(d2 - d1));
        }
        env_start(&t->pb, LG_T_B0); env_seg(&t->pb, SEG_RAMP, 0, blk(MS(8)));
        env_start(&t->pe, LG_T_E0); env_seg(&t->pe, SEG_RAMP, 0, blk(MS(7)));
    }
    if (n->arp)
        arp_env(&t->arp, ss, dur, n->from ? umax(ss / 4u, gt) : ss / 4u, n->arp == 7u ? LG_FIFTH : LG_OCT);
    else
        env_start(&t->arp, 0);
    env_start(&t->vib, 0);
    t1 = umin(MS(22), dur * 22u / 100u);
    t2 = umin(MS(70), dur * 72u / 100u);
    env_seg(&t->vib, SEG_RAMP, n->arp ? 154 : 90, blk(t1));
    env_seg(&t->vib, SEG_RAMP, n->arp ? 90 : 31, blk(t2 - t1));
    t->on = 1;
}

static void thall_choke(void)                   /* THALL: the note stops, in 10 ms */
{
    uint32_t i;
    for (i = 0; i < NTV; i++)
        if (tv[i].on && !tv[i].choked) {
            tv[i].choked = 1;
            env_start(&tv[i].gate, 0);
            env_seg(&tv[i].gate, SEG_RAMP, LG_FLOOR, blk(MS(10)));
        }
}

static dv_t *drum_slot(void)
{
    uint32_t i, best = 0;
    dv_t *d;
    for (i = 0; i < NDV; i++) {
        if (!dv[i].on) { best = i; break; }
        if (dv[i].age < dv[best].age) best = i;
    }
    d = &dv[best];
    d->has_osc = d->has_nz = 0;
    d->ph = 0;
    d->ao = d->an = 0;
    d->f.x1 = d->f.x2 = d->f.y1 = d->f.y2 = 0;
    d->age = eng_age++;
    env_start(&d->oamp, LG_FLOOR);
    env_start(&d->namp, LG_FLOOR);
    env_start(&d->pitch, 0);
    d->oamp.done = d->namp.done = 1;
    return d;
}

/* a drum: id, its voice (0..2), its velocity as a logarithm (before the Tromster's own level) */
static void drum_on(uint32_t id, uint32_t vc, int32_t vel)
{
    static const uint16_t KICK_SWEEP[4] = {MS(120), MS(170), MS(90), MS(70)}, KICK_END[4] = {MS(240), MS(300), MS(170), MS(200)};
    static const uint16_t SN_END[3] = {MS(170), MS(240), MS(105)}, SN_TONE[4] = {MS(110), MS(160), MS(75), MS(40)};
    static const uint16_t HAT_END[3] = {MS(55), MS(120), MS(35)};
    static const uint16_t CLAP_END[3] = {MS(180), MS(270), MS(130)}, CLAP_LOW[3] = {MS(12), MS(18), MS(9)};
    static const uint16_t CLAP_GAP[3] = {MS(18), MS(26), MS(12)};
    static const uint8_t CLAP_N[3] = {3, 4, 3};
    static const uint16_t CRUNCH[5] = {0, MS(6), MS(11), MS(19), MS(26)};   /* the seed's crunch: its cracks */
    int32_t v = vel + LG_DRUM;
    dv_t *d = drum_slot();
    v = v < LG_DVMIN ? LG_DVMIN : v > LG_DVMAX ? LG_DVMAX : v;
    if (vc > 3u) vc = 0;
    if (id == DR_KICK) {
        d->has_osc = 1;
        d->wave = vc == 1u ? W_TRI : W_SINE;
        env_start(&d->pitch, LGP_KICK0[vc]);
        env_seg(&d->pitch, SEG_RAMP, LGP_KICK1[vc], blk(KICK_SWEEP[vc]));
        env_start(&d->oamp, LG_FLOOR);
        env_seg(&d->oamp, SEG_RAMP, LG_KICK_PK[vc] + v, blk(MS(4)));
        env_seg(&d->oamp, SEG_RAMP, LG_FLOOR, blk(KICK_END[vc] - MS(4)));
        d->on = 1;
        if (vc == 2u) {                         /* its beater's click: a square, 820 Hz down to 190 */
            d = drum_slot();
            d->has_osc = 1;
            d->wave = W_SQUARE;
            env_start(&d->pitch, LGP_CLICK[0]);
            env_seg(&d->pitch, SEG_RAMP, LGP_CLICK[1], blk(MS(25)));
            env_start(&d->oamp, LG_CLICK + v);
            env_seg(&d->oamp, SEG_RAMP, LG_FLOOR, blk(MS(28)));
            d->on = 1;
        }
        return;
    }
    d->has_nz = 1;
    d->c = BQ_DRUM[id - 1u][vc];
    env_start(&d->namp, LG_FLOOR);
    if (vc == 3u) {                             /* the hamster kit */
        uint32_t k, at = 0;
        if (id == DR_SNARE) {                   /* a seed's crunch: five cracks, then a little ring */
            for (k = 0; k < 5u; k++) {
                if (k) env_seg(&d->namp, SEG_HOLD, 0, blk(CRUNCH[k] - at));
                env_seg(&d->namp, SEG_SET, LG_SNARE_PK[3] + v - (int32_t)k * 9000, 0);
                env_seg(&d->namp, SEG_RAMP, LG_SNARE_PK[3] + v - 160000, blk(MS(4)));
                at = CRUNCH[k] + MS(4);
            }
            env_seg(&d->namp, SEG_RAMP, LG_FLOOR, blk(MS(60)));
            d->has_osc = 1;
            d->wave = W_TRI;
            env_start(&d->pitch, LGP_SNARE[3]);
            env_start(&d->oamp, LG_SNARE_TONE[3] + v);
            env_seg(&d->oamp, SEG_RAMP, LG_FLOOR, blk(SN_TONE[3]));
        } else if (id == DR_HAT) {              /* a sniff, twice */
            env_seg(&d->namp, SEG_RAMP, LG_HAT_PK[3] + v, blk(MS(4)));
            env_seg(&d->namp, SEG_RAMP, LG_FLOOR, blk(MS(28)));
            env_seg(&d->namp, SEG_HOLD, 0, blk(MS(23)));
            env_seg(&d->namp, SEG_RAMP, LG_HAT_PK[3] + v - 20000, blk(MS(4)));
            env_seg(&d->namp, SEG_RAMP, LG_FLOOR, blk(MS(40)));
        } else {                                /* a paw's pat, and a squeak over it */
            env_seg(&d->namp, SEG_RAMP, LG_CLAP_PK[3] + v, blk(MS(2)));
            env_seg(&d->namp, SEG_RAMP, LG_FLOOR, blk(MS(40)));
            d->has_osc = 1;
            d->wave = W_SINE;
            env_start(&d->pitch, LGP_PIP[0]);
            env_seg(&d->pitch, SEG_RAMP, LGP_PIP[1], blk(MS(45)));
            env_start(&d->oamp, LG_FLOOR);
            env_seg(&d->oamp, SEG_RAMP, LG_PIP + v, blk(MS(3)));
            env_seg(&d->oamp, SEG_RAMP, LG_FLOOR, blk(MS(80)));
        }
        d->on = 1;
        return;
    }
    if (id == DR_SNARE) {
        env_seg(&d->namp, SEG_RAMP, LG_SNARE_PK[vc] + v, blk(MS(3)));
        env_seg(&d->namp, SEG_RAMP, LG_FLOOR, blk(SN_END[vc] - MS(3)));
        d->has_osc = 1;
        d->wave = vc == 1u ? W_SINE : W_TRI;
        env_start(&d->pitch, LGP_SNARE[vc]);
        env_start(&d->oamp, LG_SNARE_TONE[vc] + v);
        env_seg(&d->oamp, SEG_RAMP, LG_FLOOR, blk(SN_TONE[vc]));
    } else if (id == DR_HAT) {
        env_seg(&d->namp, SEG_RAMP, LG_HAT_PK[vc] + v, blk(MS(2)));
        env_seg(&d->namp, SEG_RAMP, LG_FLOOR, blk(HAT_END[vc] - MS(2)));
    } else {                                    /* the clap: three or four bursts, then its tail */
        uint32_t k, at = 0;
        for (k = 0; k < CLAP_N[vc]; k++) {
            if (k) {
                env_seg(&d->namp, SEG_HOLD, 0, blk(CLAP_GAP[vc] - CLAP_LOW[vc]));
                env_seg(&d->namp, SEG_SET, LG_FLOOR, 0);
            }
            env_seg(&d->namp, SEG_RAMP, LG_CLAP_PK[vc] + v, blk(MS(3)));
            env_seg(&d->namp, SEG_RAMP, LG_CLAP_LOW + v, blk(CLAP_LOW[vc] - MS(3)));
            at = k * CLAP_GAP[vc] + CLAP_LOW[vc];
        }
        env_seg(&d->namp, SEG_RAMP, LG_FLOOR, blk(CLAP_END[vc] - at));
    }
    d->on = 1;
}

/* ---- the sequencer (all of it in the interrupt) */
typedef struct { uint32_t at, kind; note_t n; uint32_t vc; } pend_t;   /* a ratchet's next hit: frames from now */
static struct {
    uint32_t playing, song, ext, pat, step, pos, acc, thr, first;
    int32_t last_lgp;                           /* the note before, for a glide; 0: none */
    pend_t pend[8];
    uint32_t npend, ext_n, ext_last, ext_len, now;
} sq;

static uint32_t sq_step_frames(void)            /* a step now, in frames */
{
    uint32_t b = hq.bpm * (hq.thall ? 2u : 1u);
    if (sq.ext && sq.ext_len)
        return sq.ext_len;
    return STEP_T / (b ? b : 120u);
}

static int32_t note_lgp(uint32_t midi)          /* a MIDI note's pitch; THALL plays everything an octave down */
{
    int32_t m = (int32_t)midi - (hq.thall ? 12 : 0);
    return HAM_LGP[m < 0 ? 0 : m > 127 ? 127 : m];
}

static void note_on(const note_t *n, uint32_t midi)
{
    int32_t v = n->vel < LG_VMIN ? LG_VMIN : n->vel > LG_VMAX ? LG_VMAX : n->vel;
    if (hq.thall)
        thall_on(n);
    else if (hq.hvoice)
        ham_on_hv(n);
    else
        ham_on(n);
    he_put(HE_NOTE, n->key | midi << 4 | (uint32_t)((v - LG_VMIN) * 127 / (LG_VMAX - LG_VMIN)) << 12);
}

/* a step's note: now, and its ratchets after it. from: the pitch a glide comes from */
static void step_note(uint32_t s, uint32_t step, int32_t from)
{
    uint32_t count = ST_RATCHET(s), k, sf = sq_step_frames(), sub = sf / count, midi;
    note_t n;
    n.key = ST_KEY(s);
    n.toct = ST_OCT(s);
    midi = (uint32_t)((int32_t)HAM_MIDI[n.key] + 12 * n.toct);
    n.lgp = note_lgp(midi);
    n.vel = HAM_VEL_LG[step & 15u] + (ST_ACCENT(s) ? LG_ACCENT : 0);
    n.ss = umax(MS(55), sub);
    n.from = ST_GLIDE(s) ? from : 0;
    n.arp = ST_ARP(s) == 1u ? 7u : ST_ARP(s) == 2u ? 12u : 0u;
    n.maxdur = umax(MS(35), sub * 88u / 100u);
    note_on(&n, midi);
    n.from = 0;
    for (k = 1; k < count && sq.npend < 8u; k++) {
        sq.pend[sq.npend].at = sub * k;
        sq.pend[sq.npend].kind = 0;
        sq.pend[sq.npend].n = n;
        sq.pend[sq.npend].vc = midi;
        sq.npend++;
    }
}

static void sq_fire(void)                       /* the step sq.step of the pattern sq.pat, now */
{
    uint32_t step = sq.step, p = sq.pat & 3u, s = hq.pat[p][step], d, mask = 0;
    sq.npend = 0;                               /* (a new step: the last one's ratchets are over) */
    he_put(HE_STEP, step | p << 4 | sq.pos << 8);
    if (hq.drums_on) {
        for (d = 0; d < 4u; d++)
            if (hq.drum[p][d] >> (step & 7u) & 1u) {
                drum_on(d, hq.dvoice[p][d], HAM_VEL_LG[step]);
                mask |= 1u << d;
            }
        /* THALL: a kick under a ratchet takes the ratchet too */
        if (hq.thall && (mask & 1u) && (s & ST_ON) && ST_RATCHET(s) > 1u) {
            uint32_t count = ST_RATCHET(s), k, sub = sq_step_frames() / count;
            for (k = 1; k < count && sq.npend < 8u; k++) {
                sq.pend[sq.npend].at = sub * k;
                sq.pend[sq.npend].kind = 1;
                sq.pend[sq.npend].n.vel = HAM_VEL_LG[step];
                sq.pend[sq.npend].vc = hq.dvoice[p][DR_KICK];
                sq.npend++;
            }
        }
        if (mask)
            he_put(HE_DRUM, mask);
    }
    if (s & ST_ON) {
        step_note(s, step, sq.last_lgp);
        sq.last_lgp = note_lgp((uint32_t)((int32_t)HAM_MIDI[ST_KEY(s)] + 12 * ST_OCT(s)));
    }
    if (++sq.step >= 16u) {                     /* the bar is over: the song goes on, or the pattern asked for */
        sq.step = 0;
        if (sq.song) {
            sq.pos = sq.pos + 1u >= hq.song_len ? 0u : sq.pos + 1u;
            sq.pat = hq.song[sq.pos & 63u] & 3u;
        } else {
            sq.pat = hq.want_pat & 3u;
        }
        he_put(HE_BAR, sq.pat | sq.pos << 8);
    }
}

static void sq_stop(void)
{
    sq.playing = sq.song = sq.ext = 0;
    sq.npend = 0;
    sq.step = sq.pos = 0;
    sq.last_lgp = 0;
    if (hq.thall)
        thall_choke();
}

static void sq_start(uint32_t song, uint32_t ext)
{
    sq.playing = 1;
    sq.song = song;
    sq.ext = ext;
    sq.step = sq.pos = 0;
    sq.npend = 0;
    sq.last_lgp = 0;
    sq.pat = song ? hq.song[0] & 3u : hq.want_pat & 3u;
    sq.acc = 0;
    sq.thr = 0;                                 /* the first step at once (ext: on the first clock) */
    sq.first = 1;
    sq.ext_n = 0;
    sq.ext_len = 0;
}

static void sq_command(uint32_t c)
{
    uint32_t a = c & 0x0FFFFFFFu;
    switch (c >> 28) {
    case HC_NOTE: {
        note_t n;
        uint32_t midi = a & 127u, vq = a >> 10 & 127u;
        n.key = a >> 7 & 7u;
        n.toct = (int32_t)midi / 12 - 5 - (n.key == 7u ? 1 : 0);
        n.lgp = note_lgp(midi);
        n.vel = vq ? HAM_MIDI_VEL_LG[vq] : 0;
        n.ss = sq_step_frames();
        n.from = 0;
        n.arp = 0;
        n.maxdur = 0;
        note_on(&n, midi);
        break;
    }
    case HC_PREVIEW: {                          /* a step alone, as the page's editor plays it */
        uint32_t step = a & 15u, p = a >> 4 & 3u, s = hq.pat[p][step], k;
        int32_t from = 0;
        if (!(s & ST_ON))
            break;
        for (k = 1; k <= 16u && ST_GLIDE(s); k++) {   /* a glide: from the note before it in the pattern */
            uint32_t o = hq.pat[p][(step + 16u - k) & 15u];
            if (o & ST_ON) {
                from = note_lgp((uint32_t)((int32_t)HAM_MIDI[ST_KEY(o)] + 12 * ST_OCT(o)));
                break;
            }
        }
        sq.npend = 0;
        step_note(s, step, from);
        break;
    }
    case HC_DRUM:
        drum_on(a & 3u, a >> 2 & 3u, a & 16u ? LG_DRUM_VOICE : LG_DRUM_TRY);
        he_put(HE_DRUM, 1u << (a & 3u));
        break;
    case HC_PLAY:
        sq_start(a & 1u, 0);
        break;
    case HC_STOP:
        sq_stop();
        break;
    case HC_CHOKE:
        thall_choke();
        break;
    case HC_EXT_START:
        if (a & 1u) {                           /* continue: on from where it stopped */
            sq.playing = 1;
            sq.ext = 1;
            sq.ext_n = 0;
        } else {
            sq_start(hq.song_len > 0u && (a & 2u), 1);
        }
        break;
    case HC_EXT_CLOCK:                          /* a MIDI clock: six a step */
        if (sq.playing && sq.ext) {
            if (sq.ext_n % 6u == 0u) {
                if (!sq.first)
                    sq.ext_len = sq.now - sq.ext_last;
                sq.ext_last = sq.now;
                sq.first = 0;
                sq_fire();
            }
            sq.ext_n++;
        }
        break;
    }
}

/* the sequencer's time: HCB frames on. Steps and ratchets that fall in them sound at their start */
static void sq_tick(void)
{
    uint32_t k;
    sq.now += HCB;
    while (hc_r != hc_w) {
        sq_command(hc_q[hc_r & 31u]);
        hc_r = hc_r + 1u;
    }
    for (k = 0; k < sq.npend;) {                /* the ratchets due */
        pend_t *p = &sq.pend[k];
        if (p->at > HCB) {
            p->at -= HCB;
            k++;
            continue;
        }
        if (p->kind)
            drum_on(DR_KICK, p->vc, p->n.vel);
        else
            note_on(&p->n, p->vc);
        *p = sq.pend[--sq.npend];
    }
    if (sq.playing && !sq.ext) {
        uint32_t b = hq.bpm * (hq.thall ? 2u : 1u);
        uint32_t sw = hq.swing > 60u ? 60u : hq.swing;   /* swing: the off steps late, by percent of a step */
        uint32_t len = sq.step & 1u ? STEP_T - STEP_T / 100u * sw : STEP_T + STEP_T / 100u * sw;
        if (sq.first) {
            sq.first = 0;
            sq.thr = len;
            sq.acc = 0;
            sq_fire();
        } else {
            sq.acc += HCB * b;
            if (sq.acc >= sq.thr) {
                sq.acc -= sq.thr;
                sq.thr = len;
                sq_fire();
            }
        }
    }
}

static void heng_init(void)
{
    uint32_t i;
    for (i = 0; i < NHV; i++) hv[i].on = 0;
    for (i = 0; i < NTV; i++) tv[i].on = 0;
    for (i = 0; i < NDV; i++) dv[i].on = 0;
    for (i = 0; i < 2u * ROOM_N; i++) room[i] = 0;
}

static inline int32_t blep_q15(uint32_t ph, uint32_t inc)   /* the rounding of a step at ph == 0 (PolyBLEP) */
{
    uint32_t d = inc >> 12;
    int32_t t;
    if (!d)
        return 0;
    if (ph < inc) {
        t = (int32_t)(((ph >> 12) << 12) / d);
        if (t > 4096) t = 4096;
        return (t << 4) - ((t * t) >> 9) - 32768;
    }
    if (ph > 0u - inc) {
        t = 4096 - (int32_t)((((0u - ph) >> 12) << 12) / d);
        if (t < 0) t = 0;
        return (t * t) >> 9;
    }
    return 0;
}
static inline int32_t tri_q15(uint32_t ph)      /* a triangle from 0 upwards */
{
    uint32_t q = ph >> 30, f = (ph >> 15) & 0x7FFFu;
    return q == 0u ? (int32_t)f : q == 3u ? (int32_t)f - 32768 : q == 1u ? 32767 - (int32_t)f : -(int32_t)f;
}

/* one control block of THALL voice t: HCB frames added to mix (Q23, mono) */
static void thall_block(tv_t *t, int32_t *mix)
{
    int32_t alg = env_step(&t->amp), glg = t->choked ? env_step(&t->gate) : 0, arp = env_step(&t->arp);
    int32_t vd = env_step(&t->vib), vib, a1, br, x, da;
    const int32_t *soft = t->soft5 ? BQ_T_SOFT5 : BQ_SOFT;
    uint32_t i;
    t->vph += t->vinc;
    vib = (((vd * HAM_SIN[t->vph >> 20]) >> 15) * HAM_CENT_Q16) >> 16;
    t->inc = ex2_inc(t->lgp + env_step(&t->pv) + arp + vib);
    t->binc = ex2_inc(t->lgp + env_step(&t->pb) + arp + vib);
    t->einc = ex2_inc(t->lgp + LG_OCT + env_step(&t->pe) + arp);
    a1 = (int32_t)(ex2_q24(alg + glg + LG_T_TRIM) >> 9);     /* Q15 */
    br = (int32_t)(ex2_q24(env_step(&t->br)) >> 9);
    da = (a1 - t->a) / (int32_t)HCB;
    for (i = 0; i < HCB; i++) {
        int32_t saw, sq2, w, nz, u, y, k, acc = 0, d;
        uint32_t q;
        t->ph += t->inc;
        t->bph += t->binc;
        t->eph += t->einc;
        q = t->ph + 0x80000000u;                /* Web Audio's sawtooth: through 0 upwards at the start */
        saw = (int32_t)(q >> 16) - 32768 - blep_q15(q, t->inc);
        sq2 = (t->eph < 0x80000000u ? 32767 : -32767) + blep_q15(t->eph, t->einc) - blep_q15(t->eph + 0x80000000u, t->einc);
        x = bq_run(&t->f_str, BQ_T_STRING, (saw * 18907) >> 10);            /* 0.68 of it, Q20 */
        x += (tri_q15(t->bph) * 7864) >> 10;                                /* the body, 0.24 */
        x += (sq2 * 2363) >> 10;                                            /* the string's edge, 0.085 */
        w = nz_white();
        nz_prev = (nz_prev * 23593 + w * 9175) >> 15;
        nz = bq_run(&t->f_br, BQ_T_BREATH, ((nz_prev * 28836 + w * 3932) >> 15) << 5);
        x += (int32_t)(((int64_t)nz * br) >> 15);
        x = bq_run(&t->f_soft, soft, x);
        x = bq_run(&t->f_pre, BQ_T_PREHP, x);
        u = (int32_t)(((int64_t)x * 15155) >> 12);                          /* the gain: 3.7 */
        d = (u - t->xprev) / 4;
        for (k = 1; k <= 4; k++) {              /* the curve, four points a frame */
            int32_t p = t->xprev + d * k;
            uint32_t pp;
            p = p > 1048575 ? 1048575 : p < -1048576 ? -1048576 : p;
            pp = (uint32_t)(p + 1048576) * 2047u;
            acc += HAM_SHAPE[pp >> 21] + (((HAM_SHAPE[(pp >> 21) + 1u] - HAM_SHAPE[pp >> 21]) * (int32_t)((pp >> 5) & 0xFFFFu)) >> 16);
        }
        t->xprev = u;
        y = acc << 3;                           /* the mean of the four, Q20 */
        y = bq_run(&t->f_chp, BQ_T_CABHP, y);
        y = bq_run(&t->f_mid, BQ_T_CABMID, y);
        y = bq_run(&t->f_clp, BQ_T_CABLP, y);
        k = t->dly[t->dly_i];
        t->dly[t->dly_i] = y;
        if (++t->dly_i >= TDLY)
            t->dly_i = 0;
        y = k;
        t->a += da;
        mix[i] += (int32_t)(((int64_t)y * t->a) >> 12);                     /* Q20 * Q15 -> Q23 */
    }
    t->a = a1;
    if (t->amp.done || (t->choked && t->gate.done))
        t->on = 0;
}

static void ham_block(hv_t *h, int32_t *l, int32_t *r)
{
    int32_t alg = env_step(&h->amp), arp = env_step(&h->arp), vd = env_step(&h->vib), vib, a, al1, ar1;
    int32_t bg, vm = h->hv ? env_step(&h->vow) : 0;
    const int16_t *tv = vm < 0 ? h->tq : h->tc;
    uint32_t i;
    if (vm < 0) vm = -vm;
    h->vph += h->vinc;
    vib = (((vd * HAM_SIN[h->vph >> 20]) >> 15) * HAM_CENT_Q16) >> 16;
    h->inc = ex2_inc(h->lgp + env_step(&h->pv) + arp + vib);
    h->binc = ex2_inc(h->lgp + env_step(&h->pb) + arp + vib);
    if (arp)
        h->xf = h->xf + 1024 > 4096 ? 4096 : h->xf + 1024;
    else
        h->xf = h->xf > 1024 ? h->xf - 1024 : 0;
    bg = h->bg0 + (((h->bg1 - h->bg0) * h->xf) >> 12);
    if (h->gliding) {                           /* where each harmonic is among the formants now */
        int32_t lgf = h->lgp + h->pv.lg - LG_RESP0;
        uint32_t k;
        for (k = 0; k < 8u; k++) {
            int32_t pos = lgf + HAM_LGK[k], fr = pos & 4095, re = 0, im = 0;   /* 16 points an octave: Q16 octaves are Q12 points */
            uint32_t j = pos < 0 ? 0u : (uint32_t)pos >> 12;
            if (pos >= 0 && j + 1u < HAM_RESP_N) {
                re = HAM_RESP_RE[h->key][j] + (((HAM_RESP_RE[h->key][j + 1u] - HAM_RESP_RE[h->key][j]) * fr) >> 12);
                im = HAM_RESP_IM[h->key][j] + (((HAM_RESP_IM[h->key][j + 1u] - HAM_RESP_IM[h->key][j]) * fr) >> 12);
            }
            h->gre[k] = (int16_t)((re * HAM_HARM[k]) >> 15);
            h->gim[k] = (int16_t)((im * HAM_HARM[k]) >> 15);
        }
        if (h->pv.done || (h->pv.i >= 1u && !h->pv.left))   /* there: its table from here */
            h->gliding = 0;
    }
    a = (int32_t)(ex2_q24(alg) >> 9);           /* Q15 */
    al1 = (a * h->gl) >> 15;
    ar1 = (a * h->gr) >> 15;
    h->dal = (al1 - h->al) / (int32_t)HCB;
    h->dar = (ar1 - h->ar) / (int32_t)HCB;
    nz_gain += (int32_t)(ex2_q24(env_step(&h->br) + alg + LG_PAN0) >> 9);
    for (i = 0; i < HCB; i++) {
        uint32_t k, f;
        int32_t s;
        h->ph += h->inc;
        h->bph += h->binc;
        k = h->ph >> 24;
        f = (h->ph >> 8) & 0xFFFFu;
        if (h->gliding) {
            s = 0;
            for (k = 0; k < 8u; k++) {
                uint32_t p = h->ph * (k + 1u);
                s += HAM_SIN[p >> 20] * h->gre[k] + HAM_SIN[(p + 0x40000000u) >> 20] * h->gim[k];
            }
            s >>= 15;                           /* Q15 * Q14 -> Q14 */
        } else {
            s = h->t0[k] + (((h->t0[k + 1u] - h->t0[k]) * (int32_t)f) >> 16);
        }
        if (h->xf && !h->gliding) {
            int32_t s1 = h->t1[k] + (((h->t1[k + 1u] - h->t1[k]) * (int32_t)f) >> 16);
            s += ((s1 - s) * h->xf) >> 12;
        }
        if (vm) {                               /* the hamster voice: toward its squeak, or its closing */
            int32_t s1 = tv[k] + (((tv[k + 1u] - tv[k]) * (int32_t)f) >> 16);
            s += ((s1 - s) * vm) >> 12;
        }
        s += (HAM_SIN[h->bph >> 20] * bg) >> 16;                            /* Q14 */
        h->al += h->dal;
        h->ar += h->dar;
        l[i] += (s * h->al) >> 6;               /* Q14 * Q15 -> Q23 */
        r[i] += (s * h->ar) >> 6;
    }
    h->al = al1;
    h->ar = ar1;
    if (h->amp.done)
        h->on = 0;
}

static void drum_block(dv_t *d, int32_t *mix, const int32_t *white)
{
    uint32_t i;
    if (d->has_osc) {
        int32_t a1 = (int32_t)(ex2_q24(env_step(&d->oamp)) >> 9), da = (a1 - d->ao) / (int32_t)HCB;
        d->inc = ex2_inc(env_step(&d->pitch));
        for (i = 0; i < HCB; i++) {
            int32_t s;
            d->ph += d->inc;
            if (d->wave == W_SINE)
                s = HAM_SIN[d->ph >> 20];
            else if (d->wave == W_TRI)
                s = tri_q15(d->ph);
            else
                s = (((d->ph < 0x80000000u ? 32767 : -32767) + blep_q15(d->ph, d->inc) -
                      blep_q15(d->ph + 0x80000000u, d->inc)) * HAM_SQR_NORM) >> 15;
            d->ao += da;
            mix[i] += (s * d->ao) >> 7;         /* Q15 * Q15 -> Q23 */
        }
        d->ao = a1;
    }
    if (d->has_nz) {
        int32_t a1 = (int32_t)(ex2_q24(env_step(&d->namp)) >> 9), da = (a1 - d->an) / (int32_t)HCB;
        for (i = 0; i < HCB; i++) {
            int32_t y = bq_run(&d->f, d->c, white[i] << 5);                 /* Q20 */
            d->an += da;
            mix[i] += (int32_t)(((int64_t)y * d->an) >> 12);
        }
        d->an = a1;
    }
    if ((!d->has_osc || d->oamp.done) && (!d->has_nz || d->namp.done))
        d->on = 0;
}

/* n frames (a multiple of HCB), added to out */
static void heng_render(int32_t *out, uint32_t n)
{
    uint32_t f, i, k, busy = 0;
    int32_t pk = 0;
    for (f = 0; f < n; f += HCB) {
        int32_t hl[HCB], hr[HCB], tm[HCB], dm[HCB], white[HCB];
        uint32_t any_h = 0, any_d = 0;
        sq_tick();
        for (i = 0; i < HCB; i++)
            hl[i] = hr[i] = tm[i] = dm[i] = 0;
        nz_gain = 0;
        for (k = 0; k < NHV; k++)
            if (hv[k].on) {
                ham_block(&hv[k], hl, hr);
                any_h = 1;
            }
        if (any_h && nz_gain) {                 /* the hamsters' breath: one noise for all of them */
            for (i = 0; i < HCB; i++) {
                int32_t w = nz_white(), y;
                nz_prev = (nz_prev * 23593 + w * 9175) >> 15;
                y = bq_run(&nz_bp, hq.hvoice ? BQ_SQUEAK : BQ_BREATH, ((nz_prev * 28836 + w * 3932) >> 15) << 5);
                y = bq_run(&nz_lp, hq.hvoice ? BQ_SOFT8 : BQ_SOFT, y);
                y = (int32_t)(((int64_t)y * nz_gain) >> 12);
                hl[i] += y;
                hr[i] += y;
            }
        }
        for (k = 0; k < NTV; k++)
            if (tv[k].on) {
                thall_block(&tv[k], tm);
                busy = 1;
            }
        for (k = 0; k < NDV; k++)
            any_d |= dv[k].on;
        if (any_d) {
            for (i = 0; i < HCB; i++)
                white[i] = nz_white();
            for (k = 0; k < NDV; k++)
                if (dv[k].on)
                    drum_block(&dv[k], dm, white);
        }
        busy |= any_h | any_d;
        for (i = 0; i < HCB; i++) {             /* the room, the levels, the output */
            int32_t el = room[2u * room_i], er = room[2u * room_i + 1u], l, r, d;
            room[2u * room_i] = hl[i];
            room[2u * room_i + 1u] = hr[i];
            if (++room_i >= ROOM_N)
                room_i = 0;
            busy |= (uint32_t)(el | er) != 0u;
            if (hq.hvoice) {                    /* the hamster voice: a small room, a few reflections, crossed */
#define ROOM(d, c) (room[2u * (room_i >= (d) ? room_i - (d) : room_i + ROOM_N - (d)) + (c)] >> 6)
                l = hl[i] + ((ROOM(750u, 0u) * 15729 + ROOM(1014u, 1u) * 13107 + ROOM(1367u, 0u) * 9175) >> 12) + tm[i];
                r = hr[i] + ((ROOM(838u, 1u) * 15729 + ROOM(1191u, 0u) * 13107 + ROOM(1632u, 1u) * 9175) >> 12) + tm[i];
#undef ROOM
            } else {
                l = hl[i] + (((el >> 6) * 9961) >> 12) + tm[i];
                r = hr[i] + (((er >> 6) * 9961) >> 12) + tm[i];
            }
            d = (int32_t)(((int64_t)dm[i] * (int32_t)hq.lvl_drum) >> 8);
            l = ((int32_t)(((int64_t)l * (int32_t)hq.lvl_ham) >> 8) + d) >> HAM_MAKEUP_SH;
            r = ((int32_t)(((int64_t)r * (int32_t)hq.lvl_ham) >> 8) + d) >> HAM_MAKEUP_SH;
            if (!hq.off) {
                out[2u * (f + i)] += l;
                out[2u * (f + i) + 1u] += r;
            }
            if (l > pk) pk = l;
            if (-l > pk) pk = -l;
            if (r > pk) pk = r;
            if (-r > pk) pk = -r;
        }
    }
    heng_busy = busy | sq.playing;
    heng_peak = pk;
}
