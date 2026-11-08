/* SPDX-License-Identifier: GPL-3.0-only */
/* FM-1 Clock: the most useless firmware for the M-VAVE FM-1. Two clocks that keep the time, swing their pendulums and
 * tick at both ends of the swing. The wall clock (a 31-day pendulum clock) ticks every half second and strikes the
 * hours (and one at the half hour) on an FM gong fitted to a recording of a real one. The cuckoo clock (a Black
 * Forest 1-day clock) beats faster, and at the hour opens its door: the bird calls the hours on two FM pipes (one
 * call at the half hour) while a wire gong is struck, and its weights go down on their chains through the day. The
 * whole chip goes into the ticking, the gongs and the pipes.
 *
 *   ALGORITHM    the clock: the wall clock or the cuckoo clock
 *   SELECT       the minute hand (turned forward past the hour or the half hour, the clock strikes it, as a real one)
 *   PRESETS      the hour hand
 *   SEL          to the nearest minute (press it at :00 of a clock you trust)
 *   PLAY         strike the last hour again (a repeater)
 *   FX           the strike on / off (FX lit: silent)
 *   GLO          the keys' lights: under the pendulum, on the hour (they flash with each blow, and in silence on the
 *                hour, its count), off
 *   HOME         the time as digits beside the clock, on / off
 *   ENV          (the cuckoo clock) wind it: pull its chains, the weights go up (it winds itself when one is down)
 *   SEQ          how many of the FM operators the chip runs, and how much of it they take, on / off
 *   KNOB 1, 2    the ticks' and the strike's level (kept in flash, with the clock and the keys' lights)
 *   MIDI         CC 20 hours, CC 21 minutes, CC 22 seconds (any channel): the time is set when the seconds come
 *                (tools/settime.py sends the computer's)
 *
 * Time: TIMER4 counts the 24 MHz crystal; the audio interrupt turns it into half seconds (the time of day) and beats
 * (the cuckoo's pendulum) and puts each tick on its frame in the block it renders. The time is lost when the FM-1 is
 * switched off, as a clock that stops: set it. Integers only, no float, no 64-bit division (docs/RULES.md). The
 * sound: clk_engine.h; the pictures: clk_draw.h. */
#define APP_NAME "FM1 CLOCK"
#define STORE_MAGIC 0x4B4C4346u                 /* "FCLK": this firmware's own settings (store.h) */
#include "platform.c"
#ifdef DINGHY_HOST
static uint32_t frames;
#define ENG_ON_HIT(e) printf("%6u ms  HIT at %.4f s, strength %u\n", fm1_ms, (frames + (e)->frame) / 44100.0, (e)->arg)
#define ENG_ON_PIPE(e) printf("%6u ms  PIPE %s at %.4f s\n", fm1_ms, (e)->arg ? "low" : "high", (frames + (e)->frame) / 44100.0)
#define ENG_ON_FLASH(e) printf("%6u ms  FLASH at %.4f s\n", fm1_ms, (frames + (e)->frame) / 44100.0)
#endif
#include "clk_engine.h"
#include "clk_draw.h"

#define HALF_TICKS 12000000u                    /* half a second of the crystal */
#define DAY 172800u                             /* half seconds in a day */
#define HOUR 7200u
#define SWING_A 95443718u                       /* the wall clock's pendulum, each way: 8 degrees (2^32 = a turn) */
#define SWING_B 83513253u                       /* the cuckoo's: 7 degrees */
#define BOOT_TOD (10u * HOUR + 10u * 120u)      /* 10:10 at power-on */
#define CK_RUN (26u * HOUR)                     /* the cuckoo's going weight runs down in 26 hours */
#define CK_CALLS 195u                           /* and its cuckoo weight in as many calls (26 hours of them) */
#define WIND_FRAMES 3700u                       /* winding: the click wheel, a tooth every 84 ms */

/* ---- time: written by the audio interrupt (ck_*), read by the main loop through ck_seq */
static volatile uint32_t ck_half;               /* half seconds since power-on */
static volatile uint32_t ck_sub;                /* crystal ticks into this half second */
static volatile uint32_t ck_beat;               /* the cuckoo's beats since it was chosen */
static volatile uint32_t ck_bsub;               /* crystal ticks into this beat */
static volatile uint32_t ck_t4;                 /* the crystal when ck_sub was this */
static volatile uint32_t ck_seq;                /* odd while they change */
static volatile uint32_t ck_off = BOOT_TOD;     /* (main) the time of day = ck_half + ck_off, modulo DAY */
static volatile uint32_t ck_silent;             /* (main) no strike on the hour */
static volatile uint32_t ck_clock;              /* (main) the clock */
static volatile uint32_t ck_wind;               /* (main) its chains are being pulled */
static volatile uint32_t st_req_n, st_req_seq;  /* (main) strike n now */
static volatile uint32_t eng_off;               /* (main) the updater runs: no sound, the time goes on */
static volatile uint32_t tr_left;               /* (ISR) events still to come in this train */

#ifdef DINGHY_HOST
static uint32_t clk_now(void) { return fm1_ms * 24000u; }   /* the host's millisecond, as the crystal */
#else
static uint32_t clk_now(void) { return fm1_ticks(); }
#endif

static uint32_t hour12(uint32_t tod) { uint32_t h = tod / HOUR % 12u; return h ? h : 12u; }

/* ---- the audio interrupt: the time, the events of this block, the sound */
#ifndef DINGHY_HOST
static uint32_t frames;                         /* frames since power-on (the ISR's) */
#endif
static uint32_t ck_done, ck_bdone, ck_started, tr_seen, isr_clock, wind_t;
static ev_t tr_ev[48];                          /* the train: its events, at their frames (since power-on) */
static uint32_t tr_n, tr_i;

static void ev_add(ev_t *ev, uint32_t *nev, uint32_t frame, uint32_t type, uint32_t arg)
{
    uint32_t i = *nev;
    if (i >= 12u) return;
    while (i && ev[i - 1u].frame > frame) {     /* in frame order */
        ev[i] = ev[i - 1u];
        i--;
    }
    ev[i].frame = frame;
    ev[i].type = type;
    ev[i].arg = arg;
    (*nev)++;
}

static void tr_put(uint32_t at, uint32_t type, uint32_t arg)
{
    if (tr_n < 48u) {
        tr_ev[tr_n].frame = at;
        tr_ev[tr_n].type = type;
        tr_ev[tr_n].arg = arg;
        tr_n++;
    }
}
static uint32_t jit(uint32_t v, uint32_t sh)    /* v, a little more or less: up to v / 2^sh either way */
{
    uint32_t r = v >> sh;
    return v - r + (uint32_t)(((uint64_t)(eng_rnd() & 65535u) * (2u * r)) >> 16);
}
#define CLICK_ARG(snd, g15) ((snd) | (g15) << 8)

/* n strikes (the wall clock) or calls (the cuckoo) from frame at; mute: the blows only, for the keys */
static void train_start(uint32_t n, uint32_t at, uint32_t mute)
{
    uint32_t k, t = at;
    tr_n = tr_i = 0;
    if (!isr_clock) {                           /* the release click, 40 ms on the hit; the next 1.19 s on */
        for (k = 0; k < n; k++) {
            uint32_t g = HAMMER[k < 2u ? k : 2u];   /* the first blow the hardest, the next a little less */
            if (!mute) tr_put(t, EV_CLICK, CLICK_ARG(SND_A_TICK, 15000u));
            t += CLICK_FRAMES + (eng_rnd() & 255u) - 128u;
            tr_put(t, mute ? EV_FLASH : EV_HIT, (g * (30800u + (eng_rnd() & 4095u))) >> 15);
            t += TRAIN_FRAMES - CLICK_FRAMES + (eng_rnd() & 1023u) - 512u;
        }
    } else {                                    /* the warning, the door, the calls: the gong and the two pipes */
        uint32_t h = at + CK_RUN0_FRAMES, lo = h;
        if (!mute) {                            /* the warning: the train runs, clicks twice, catches on its pin */
            tr_put(at, EV_RUN, 1);
            tr_put(h - CK_PRE_FRAMES, EV_CLICK, CLICK_ARG(SND_B_WARN, 32767u));
            tr_put(h - CK_PRE1_FRAMES, EV_CLICK, CLICK_ARG(SND_B_WARN, 32767u));
            tr_put(h - CK_STOP_FRAMES, EV_RUN, 0);
            tr_put(h - CK_PRE2_FRAMES, EV_CLICK, CLICK_ARG(SND_B_DOOR, 32767u));   /* the release: the door opens */
            tr_put(h - CK_PRE2_FRAMES, EV_DOOR, 1);
            tr_put(h - CK_PRE2_FRAMES, EV_RUN, 1);                              /* the train runs on */
        }
        for (k = 0; k < n; k++) {
            uint32_t hi = h + jit(k ? CK_HIT_TO_HIGH : CK_FIRST_HIT_TO_HIGH, 7);
            lo = hi + jit(CK_HIGH_TO_LOW, 7);
            tr_put(h, mute ? EV_FLASH : EV_HIT, (HAMMER[2] * (30800u + (eng_rnd() & 4095u))) >> 15);
            if (!mute) {
                tr_put(hi, EV_PIPE, 0);
                tr_put(lo, EV_PIPE, 1);
            }
            h += jit(CK_CALL_FRAMES, 7);
        }
        if (!mute) {
            tr_put(lo + CK_POST0_FRAMES, EV_CLICK, CLICK_ARG(SND_B_SHUT, 32767u));   /* (as loud as the door shutting) */
            tr_put(lo + CK_POST0_FRAMES, EV_DOOR, 0);   /* the bird goes in; the door shuts on the next click */
            tr_put(lo + CK_POST1_FRAMES, EV_CLICK, CLICK_ARG(SND_B_SHUT, 32767u));
            tr_put(lo + CK_POST1_FRAMES, EV_RUN, 0);   /* and stops */
        }
    }
    tr_left = tr_n;
}

static void half_second(uint32_t h, uint32_t f, ev_t *ev, uint32_t *nev)   /* the time: the strike; the wall clock's tick */
{
    uint32_t tod = (h + ck_off) % DAY;
    if (!isr_clock)                             /* its pendulum at an end: one click at each, the left, the right */
        ev_add(ev, nev, f, h & 1u ? EV_TICK : EV_TOCK, h & 1u ? SND_A_TICK : SND_A_TOCK);
    if (tod % 3600u == 0) {
        if (!ck_silent)
            train_start(tod % HOUR ? 1u : hour12(tod), frames + f, 0);
        else if (tod % HOUR == 0)               /* silent: the hour's count for the keys only */
            train_start(hour12(tod), frames + f, 1);
    }
}

static void app_audio(int32_t *out, uint32_t n)
{
    ev_t ev[12];
    uint32_t nev = 0, now = clk_now(), d, due, f;
    if (!ck_started) {                          /* (the audio starts before app_main: the time from here) */
        ck_started = 1;
        ck_t4 = now;
    }
    d = now - ck_t4;
    ck_seq++;
    ck_sub += d;
    ck_bsub += d;
    ck_t4 = now;
    while (ck_sub >= HALF_TICKS) {
        ck_sub -= HALF_TICKS;
        ck_half++;
    }
    while (ck_bsub >= CK_BEAT_TICKS) {
        ck_bsub -= CK_BEAT_TICKS;
        ck_beat++;
    }
    if ((ck_clock != 0u) != isr_clock) {        /* another clock: its pendulum from its end, its sound, no train (the
                                                   two cuckoos sound alike: from one to the other nothing stops) */
        isr_clock = ck_clock != 0u;
        eng_want = isr_clock;
        ck_beat = ck_bdone = 0;
        ck_bsub = 0;
        tr_n = tr_i = tr_left = 0;
        eng_door = 0;
    }
    ck_seq++;
    if (ck_done != ck_half) {                   /* a half second went past between two blocks: it now */
        half_second(ck_half, 0, ev, &nev);
        ck_done = ck_half;
    }
    due = HALF_TICKS - ck_sub;                  /* the next one, if it falls in this block: on its frame */
    f = due * 147u / 80000u;                    /* (44100 / 24 M = 147 / 80000) */
    if (f < n) {
        half_second(ck_half + 1u, f, ev, &nev);
        ck_done = ck_half + 1u;
    }
    if (isr_clock) {                            /* the cuckoo's beat: its own pendulum */
        if (ck_bdone != ck_beat) {
            ev_add(ev, &nev, 0, ck_beat & 1u ? EV_TICK : EV_TOCK, SND_B_TICK);
            ck_bdone = ck_beat;
        }
        due = CK_BEAT_TICKS - ck_bsub;
        f = due * 147u / 80000u;
        if (f < n) {
            ev_add(ev, &nev, f, ck_beat & 1u ? EV_TOCK : EV_TICK, SND_B_TICK);
            ck_bdone = ck_beat + 1u;
        }
        if (ck_wind && (int32_t)(wind_t - frames) < (int32_t)n) {   /* the chains pulled: the click wheel */
            uint32_t off = (int32_t)(wind_t - frames) < 0 ? 0 : wind_t - frames;
            ev_add(ev, &nev, off, EV_CLICK, CLICK_ARG(SND_B_WARN, 5000u + (eng_rnd() & 2047u)));
            wind_t = frames + off + WIND_FRAMES + (eng_rnd() & 511u);
        } else if (!ck_wind) {
            wind_t = frames;
        }
    }
    if (st_req_seq != tr_seen) {                /* the main loop asks: the repeat, the hands turned past */
        tr_seen = st_req_seq;
        train_start(st_req_n, frames, 0);
    }
    while (tr_i < tr_n && (int32_t)(tr_ev[tr_i].frame - frames) < (int32_t)n) {
        uint32_t off = (int32_t)(tr_ev[tr_i].frame - frames) < 0 ? 0 : tr_ev[tr_i].frame - frames;
        ev_add(ev, &nev, off, tr_ev[tr_i].type, tr_ev[tr_i].arg);
        tr_i++;
    }
    tr_left = tr_n - tr_i;
    if (!eng_off)
        eng_render(out, n, ev, nev);
    frames += n;
}

/* the time now, as the main loop sees it: half seconds since power-on, crystal ticks into the half; the cuckoo's
   beats, and ticks into the beat */
static void clk_read2(uint32_t *half, uint32_t *sub, uint32_t *beat, uint32_t *bsub)
{
    uint32_t s, h, b, t, bt, bb, d;
    do {
        s = ck_seq;
        h = ck_half;
        b = ck_sub;
        bt = ck_beat;
        bb = ck_bsub;
        t = ck_t4;
    } while ((s & 1u) || s != ck_seq);
    d = clk_now() - t;
    b += d;
    bb += d;
    while (b >= HALF_TICKS) {
        b -= HALF_TICKS;
        h++;
    }
    while (bb >= CK_BEAT_TICKS) {
        bb -= CK_BEAT_TICKS;
        bt++;
    }
    *half = h;
    *sub = b;
    *beat = bt;
    *bsub = bb;
}
static void clk_read(uint32_t *half, uint32_t *sub)
{
    uint32_t bt, bb;
    clk_read2(half, sub, &bt, &bb);
}

/* ---- the panel */
enum { KEYS_SWING, KEYS_HOUR, KEYS_OFF };
static struct { uint8_t tick, gong, silent, digits, info, clock, keys, pad; } set = {16, 16, 0, 0, 0, 0, KEYS_SWING, 0};
static uint32_t dirty, t_change, t_set, t_level, level_which, strike_due, strike_n, t_turn, t_clock, t_keys;

static void apply_set(void)
{
    eng_tick_lvl = set.tick * 16u;
    eng_gong_lvl = set.gong * 16u;
    ck_silent = set.silent;
    ck_clock = set.clock;
}

static void set_time(int32_t delta)             /* the hands moved by delta half seconds */
{
    uint32_t h, sub, old;
    clk_read(&h, &sub);
    old = (h + ck_off) % DAY;
    ck_off = (ck_off + (uint32_t)((int32_t)DAY * 4 + delta)) % DAY;
    if (delta > 0 && !set.silent) {             /* forward past :00 or :30: strike it, when the turning stops */
        uint32_t last = (old + (uint32_t)delta) / 3600u * 3600u;
        if (last > old) {
            strike_due = 1;
            strike_n = last % HOUR ? 1u : hour12(last % DAY);
        }
    }
    t_turn = t_set = fm1_ms;
}

static void strike_now(uint32_t n)
{
    st_req_n = n;
    st_req_seq++;
}

static void midi_in(void)
{
    static uint32_t hh, mm, have;
    uint8_t st, d1, d2;
    while (midi_get(&st, &d1, &d2)) {
        if ((st & 0xF0u) != 0xB0u) continue;
        if (d1 == 20u && d2 < 24u) { hh = d2; have |= 1u; }
        if (d1 == 21u && d2 < 60u) { mm = d2; have |= 2u; }
        if (d1 == 22u && d2 < 60u && have == 3u) {   /* the seconds set it, now: the half second starts here */
            uint32_t h, sub, want = hh * HOUR + mm * 120u + d2 * 2u;
            clk_read(&h, &sub);
            ck_off = (want + DAY - h % DAY) % DAY;
            t_set = fm1_ms;
            have = 0;
        }
    }
}

#define M_L 56                                  /* the margins beside the clocks */
#define M_R 183
#define M_W (240 - M_R)

/* words in the margins, over what is there (bg_px: the panel wall, the clock's own picture), their edges blended
 * into it, dark, as if burnt into the wood */
#define TXT_HI RGB(56, 32, 16)
#define TXT_LO RGB(92, 60, 36)
static void bg_text_box(uint32_t x, uint32_t y, uint32_t w, const felucca_font_t *f, const char *s, uint16_t c)
{
    int32_t tx = ((int32_t)w - text_w(f, s)) / 2;
    uint32_t i, j;
    cv_begin(w, f->h, C_BLACK);
    for (j = 0; j < cv_h; j++)
        for (i = 0; i < cv_w; i++)
            cv_px[j * cv_w + i] = bg_px(x + i, y + j);
    for (; *s; s++) {
        uint32_t gi = glyph(f, (uint8_t)*s), gx, gy, gw = f->bw[gi], bpr = (gw + 1u) / 2u;
        const uint8_t *gd = f->data + f->off[gi];
        for (gy = 0; gy < f->h && gy < cv_h; gy++)
            for (gx = 0; gx < gw; gx++) {
                uint32_t v = gd[gy * bpr + gx / 2u];
                int32_t px = tx - f->pad + (int32_t)gx;
                v = (gx & 1u) ? (v & 15u) : (v >> 4);
                if (v && px >= 0 && (uint32_t)px < cv_w) {
                    uint16_t *d = &cv_px[gy * cv_w + (uint32_t)px];
                    *d = (uint16_t)unsw(mix565(unsw(*d), c, v * 256u / 15u));
                }
            }
        tx += f->adv[gi];
    }
    cv_blit(x, y);
    lcd_sync();
}

static void num(char *s, uint32_t v, const char *unit)   /* "368 OP" */
{
    char d[8];
    uint32_t n = 0;
    do { d[n++] = (char)('0' + v % 10u); v /= 10u; } while (v && n < 7u);
    while (n) *s++ = d[--n];
    *s++ = ' ';
    while (*unit) *s++ = *unit++;
    *s = 0;
}
static void draw_info(int force)                /* SEQ: the FM operators on the chip (the gong's carriers and
                                                   modulators, the ticks', the pipes', the drone's, the rattle's),
                                                   and the share of the audio's time the engine takes */
{
    static uint32_t shown = ~0u, t_last;
    uint32_t ops = eng_st.ng + K_FM + 2u * NT + 4u + PIPE_NBODY[0] + PIPE_NBODY[1] + DRONE_N + RATTLE_G;
    uint32_t pct = eng_st.load / (BLOCK_TICKS / 100u), v;
    char s[16];
    if (!force && fm1_ms - t_last < 1000u)
        return;
    t_last = fm1_ms;
    v = set.info ? ops << 8 | pct : 0u;
    if (v == shown && !force)
        return;
    shown = v;
    if (set.info) {
        num(s, ops, "OP");
        bg_text_box(M_R, 4, M_W, &FONT_S, s, TXT_LO);
        num(s, pct, "%");
        bg_text_box(M_R, 22, M_W, &FONT_S, s, TXT_LO);
    } else {
        bg_fill(M_R, 4, M_W, 36);
    }
}

static const char *const KEYS_NAME[3] = {"SWING", "HOURS", "OFF"};

static void draw_margins(uint32_t tod, int force)   /* the digits (left), the levels, the keys and SILENT (right) */
{
    static uint32_t shown_t = ~0u, shown_r = ~0u;
    uint32_t show_t = set.digits || fm1_ms - t_set < 3000u, t = show_t ? tod / 120u : 9999u, r;
    char s[12];
    if (t != shown_t || force) {
        shown_t = t;
        if (show_t) {
            s[0] = (char)('0' + t / 600u); s[1] = (char)('0' + t / 60u % 10u); s[2] = ':';
            s[3] = (char)('0' + t % 60u / 10u); s[4] = (char)('0' + t % 10u); s[5] = 0;
            bg_text_box(0, 104, M_L, &FONT_S, s, TXT_HI);
        } else {
            bg_fill(0, 104, M_L, 16);
        }
    }
    r = t_level && fm1_ms - t_level < 2000u ? 1u + level_which : 0u;
    if (t_keys && fm1_ms - t_keys < 2000u && (!r || t_keys > t_level))
        r = 3u;
    r = r | (r == 1u || r == 2u ? (level_which ? set.gong : set.tick) << 2 : r == 3u ? (uint32_t)set.keys << 2 : 0u)
        | set.silent << 9;
    if (r != shown_r || force) {
        shown_r = r;
        if ((r & 3u) == 3u) {
            bg_text_box(M_R, 96, M_W, &FONT_S, "KEYS", TXT_HI);
            bg_text_box(M_R, 114, M_W, &FONT_S, KEYS_NAME[r >> 2 & 3u], TXT_HI);
        } else if (r & 3u) {
            uint32_t v = (r >> 2 & 127u) * 100u / 16u;
            bg_text_box(M_R, 96, M_W, &FONT_S, (r & 3u) == 1u ? "TICK" : set.clock ? "CALL" : "GONG", TXT_HI);
            s[0] = (char)(v >= 100u ? '0' + v / 100u : ' '); s[1] = (char)(v >= 10u ? '0' + v / 10u % 10u : ' ');
            s[2] = (char)('0' + v % 10u); s[3] = '%'; s[4] = 0;
            bg_text_box(M_R, 114, M_W, &FONT_S, s, TXT_HI);
        } else {
            bg_fill(M_R, 96, M_W, 36);
        }
        if (set.silent)
            bg_text_box(M_R, 214, M_W, &FONT_S, "SILENT", TXT_LO);
        else
            bg_fill(M_R, 214, M_W, 16);
    }
    draw_info(force);
}

static int is_black(uint32_t k) { return (0x54Au >> ((53u + k) % 12u)) & 1u; }

/* the keys' lights: lit = the white key (0..15) under the bob, 16 all of them, 17 none */
static void keys_show(uint32_t lit, const uint32_t *white)
{
    static uint32_t shown = 99;
    uint32_t k;
    if (lit == shown)
        return;
#if BOARD_SMK37
    for (k = 0; k < 16u; k++) {                 /* (no key lights: the pads, in brass) */
        uint32_t on = lit == 16u || (lit < 16u && (k & 7u) == lit / 2u);
        padled_set(k, on ? 200 : lit == 17u ? 0 : 6, on ? 120 : lit == 17u ? 0 : 3, on ? 30 : 0);
    }
    padled_flush();
    (void)white;
#else
    if (shown < 16u)
        fm1_led_key(KEY_LED(white[shown]), 0);
    else if (shown == 16u || shown == 99u)
        for (k = 0; k < 27u; k++)
            fm1_led_key(KEY_LED(k), 0);
    if (lit < 16u)
        fm1_led_key(KEY_LED(white[lit]), 1);
    else if (lit == 16u)
        for (k = 0; k < 27u; k++)
            fm1_led_key(KEY_LED(k), 1);
#endif
    shown = lit;
}

static void app_main(void)
{
    uint32_t last_dial = ~0u, t_win = 0, white[16], nw = 0, k, shown_clock = ~0u, bow_seen = 0, t_pipe = 0, t_high = 0;
    uint32_t hits_seen = 0, t_flash = 0, wind_h = 0, calls = 0, calls_seen = 0, shown_go = ~0u, shown_ck = ~0u;
    uint32_t show_go = 0, show_ck = 0, winding = 0, d_open = 0, d_out = 0, d_bow = 0, d_shown = ~0u;
    eng_init();
    if (settings_load(&set, sizeof set) || set.tick > 32u || set.gong > 32u || set.silent > 1u || set.digits > 1u ||
        set.info > 1u || set.clock > 2u || set.keys > KEYS_OFF) {
        set.tick = 16; set.gong = 16; set.silent = 0; set.digits = 0; set.info = 0; set.clock = 0; set.keys = KEYS_SWING;
    }
    if (set.clock > 1u)                         /* (a build before had two cuckoo clocks: either is this one) */
        set.clock = 1u;
    apply_set();
#ifdef DINGHY_HOST
    {
        const char *e = getenv("CLK_NG");       /* the host renders a fixed number of carriers (all, by default) */
        eng_fixed_ng = e ? (uint32_t)atoi(e) : NG_MAX;
    }
#endif
    for (k = 0; k < 27u; k++)
        if (!is_black(k)) white[nw++] = k;
    for (;;) {
        uint32_t h, sub, beat, bsub, tod, rel, b, ph, th, lit;
        int32_t e, cosq;
#ifndef DINGHY_HOST
        if (usb.ota_req)
            eng_off = 1;                        /* the updater gets the whole chip */
#endif
        platform_poll();
        midi_in();

        if ((e = fm1_enc_take(ENC_ALGORITHM)) != 0) {   /* the other clock, either way: once a turn, however many
                                                   detents (a turn ends when the knob has rested 400 ms: a turn of
                                                   two detents switched there and back again) */
            if (!t_clock || fm1_ms - t_clock > 400u) {
                set.clock ^= 1u;
                dirty = 1; t_change = fm1_ms;
            }
            t_clock = fm1_ms;
        }
        if ((e = fm1_enc_take(ENC_SELECT)) != 0)          /* a minute a detent */
            set_time((e < -60 ? -60 : e > 60 ? 60 : e) * 120);
        if ((e = fm1_enc_take(ENC_PRESETS)) != 0)         /* an hour */
            set_time((e < -24 ? -24 : e > 24 ? 24 : e) * (int32_t)HOUR);
        if ((e = fm1_enc_take(ENC_KNOB1)) != 0) {
            int32_t v = (int32_t)set.tick + e;
            set.tick = (uint8_t)(v < 0 ? 0 : v > 32 ? 32 : v);
            level_which = 0; t_level = fm1_ms; dirty = 1; t_change = fm1_ms;
        }
        if ((e = fm1_enc_take(ENC_KNOB2)) != 0) {
            int32_t v = (int32_t)set.gong + e;
            set.gong = (uint8_t)(v < 0 ? 0 : v > 32 ? 32 : v);
            level_which = 1; t_level = fm1_ms; dirty = 1; t_change = fm1_ms;
        }
        b = fm1_input_edges(&rel);
        if (b & (1u << BTN_SEL)) {              /* to the nearest minute */
            clk_read(&h, &sub);
            tod = (h + ck_off) % DAY;
            k = tod % 120u;
            set_time(k >= 60u ? (int32_t)(120u - k) : -(int32_t)k);
            strike_due = 0;
        }
        if (b & (1u << BTN_PLAY)) {
            clk_read(&h, &sub);
            strike_now(hour12((h + ck_off) % DAY));
        }
        if (b & (1u << BTN_FX)) { set.silent ^= 1u; dirty = 1; t_change = fm1_ms; }
        if (b & (1u << BTN_HOME)) { set.digits ^= 1u; dirty = 1; t_change = fm1_ms; }
        if (b & (1u << BTN_SEQ)) { set.info ^= 1u; dirty = 1; t_change = fm1_ms; draw_info(1); }
        if (b & (1u << BTN_GLO)) { set.keys = (uint8_t)((set.keys + 1u) % 3u); t_keys = fm1_ms; dirty = 1; t_change = fm1_ms; }
        if ((b & (1u << BTN_ENV)) && set.clock)   /* wind it when you like; it winds itself when a weight is down */
            winding = 1;
        apply_set();
        if (strike_due && fm1_ms - t_turn > 500u) {   /* the hands have stopped: what they passed */
            strike_due = 0;
            strike_now(strike_n);
        }

        clk_read2(&h, &sub, &beat, &bsub);
        tod = (h + ck_off) % DAY;
        if (set.clock != shown_clock) {         /* another clock: all of the screen */
            shown_clock = set.clock;
            draw_clock = set.clock;
            draw_all();
            last_dial = ~0u;
            shown_go = shown_ck = ~0u;
            d_open = d_out = d_bow = 0;
            d_shown = ~0u;
            bow_seen = eng_bow;
            calls_seen = eng_calls;
            draw_margins(tod, 1);
        }
        /* the hands: once a second (and when set) */
        if (tod / 2u != last_dial) {
            uint32_t m = tod % HOUR, fr = (uint32_t)(((uint64_t)sub * 13032u) >> 18);
            last_dial = tod / 2u;
            draw_dial((tod % 86400u) * 49710u, m * 596523u + fr);
        }
        /* the pendulum: cos of the beat, at both ends on the ticks; ~50 frames a second */
        if (!set.clock)
            ph = (h << 31) + (uint32_t)(((uint64_t)sub * 187649984u) >> 20);
        else
            ph = (beat << 31) + (uint32_t)(((uint64_t)bsub * CK_BEAT_K) >> 20);
        cosq = SINT[(ph + 1073741824u) >> 18];
        th = (uint32_t)(int32_t)(((int64_t)(int32_t)(set.clock ? SWING_B : SWING_A) * cosq) >> 15);

        if (set.clock && fm1_ms - t_win >= 20u) {   /* the cuckoo, ~50 times a second: its weights, its door, its bird */
            uint32_t go = h - wind_h, tgo, tck, beak, v;
            if (eng_calls != calls_seen) {      /* a call: the cuckoo weight a step down */
                calls += eng_calls - calls_seen;
                calls_seen = eng_calls;
            }
            if (eng_bow != bow_seen) {          /* a pipe: the bird's beak opens, it bows from the high one */
                bow_seen = eng_bow;
                t_pipe = fm1_ms;
                if (!eng_pipe)
                    t_high = fm1_ms;
            }
            if (go >= CK_RUN || calls >= CK_CALLS)   /* run down: someone winds it (as one does a 1-day clock) */
                winding = 1;
            if (winding) {                      /* the rings pulled down, the weights up: 40 px a second, one, the other */
                uint32_t step = 40u * 256u / 50u;
                show_go = show_go > step ? show_go - step : 0;
                if (!show_go)
                    show_ck = show_ck > step ? show_ck - step : 0;
                wind_h = h;
                calls = 0;
                if (!show_go && !show_ck)
                    winding = 0;
            } else {
                tgo = go * (CK_TRAVEL * 256u / 64u) / (CK_RUN / 64u);
                tck = calls * (CK_TRAVEL * 256u) / CK_CALLS;
                show_go = tgo;
                show_ck = show_ck + (tck > show_ck ? (tck - show_ck + 15u) >> 4 : 0u);   /* the chain runs */
            }
            ck_wind = winding;
            if (show_go >> 8 != shown_go || show_ck >> 8 != shown_ck) {
                shown_go = show_go >> 8;
                shown_ck = show_ck >> 8;
                draw_chains(show_go, show_ck);
            }
            /* the door opens (120 ms), then the bird comes out (200 ms); it goes in (100 ms), then the door shuts
               (80 ms). It bows from its high note to the end of its low one, and opens its beak on each */
            if (eng_door) {
                d_open = d_open + 43u > 256u ? 256u : d_open + 43u;
                if (d_open > 200u)
                    d_out = d_out + 26u > 256u ? 256u : d_out + 26u;
            } else {
                d_out = d_out > 52u ? d_out - 52u : 0;
                if (!d_out)
                    d_open = d_open > 64u ? d_open - 64u : 0;
            }
            v = d_out && t_high && fm1_ms - t_high < CK_HIGH_TO_LOW * 10u / 441u + 90u ? 256u : 0u;
            d_bow = v > d_bow ? (d_bow + 86u > 256u ? 256u : d_bow + 86u) : (d_bow > 64u ? d_bow - 64u : 0u);
            beak = d_out && t_pipe && fm1_ms - t_pipe < 110u;
            v = d_open | d_out << 9 | d_bow << 18 | beak << 27;
            if (v != d_shown) {
                d_shown = v;
                draw_door(d_open, d_out, d_bow, beak);
            }
        } else if (!set.clock) {
            ck_wind = winding = 0;
        }
        if (fm1_ms - t_win >= 20u) {
            t_win = fm1_ms;
            if (set.clock)
                draw_lower(th);
            else
                draw_window(th);
        }
        /* the keys' lights */
        if (eng_hits != hits_seen) {            /* a blow, sounded or not */
            hits_seen = eng_hits;
            t_flash = fm1_ms;
        }
        if (set.keys == KEYS_SWING) {           /* the white key under the bob */
            lit = (uint32_t)((cosq + 32768) * 16) >> 16;
            if (lit > 15u) lit = 15u;
        } else if (set.keys == KEYS_HOUR) {
            lit = t_flash && fm1_ms - t_flash < 180u ? 16u : 17u;
        } else {
            lit = 17u;
        }
        keys_show(lit, white);
        fm1_led_key(BTN_FX, set.silent);
        fm1_led_key(BTN_PLAY, tr_left != 0);
        draw_margins(tod, 0);

        /* settings: 2 s after a change, when the gong is still and between two ticks (an erase stops the sound) */
        if (dirty && fm1_ms - t_change > 2000u && !eng_st.peak && !tr_left &&
            (set.clock ? bsub > 2000000u && bsub < 6000000u : sub > 2400000u && sub < 7200000u)) {
            settings_save(&set, sizeof set);
            dirty = 0;
        }
    }
}
