/* SPDX-License-Identifier: GPL-3.0-only */
/* FM1 Clock: the most useless firmware for the M-VAVE FM-1. A pendulum wall clock that keeps the time, swings its
 * pendulum and ticks at both ends of the swing, every half second, and strikes the hours (and one at the half hour)
 * on an FM gong fitted to a recording of a real one. The whole chip goes into the ticking and the gong.
 *
 *   SELECT       the minute hand (turned forward past the hour or the half hour, the clock strikes it, as a real one)
 *   ALGORITHM    the hour hand
 *   SEL          to the nearest minute (press it at :00 of a clock you trust)
 *   PLAY         strike the last hour again (a repeater)
 *   FX           the strike on / off (FX lit: silent)
 *   HOME         the time as digits beside the clock, on / off
 *   SEQ          how many of the gong's FM operators the chip runs, and how much of it they take, on / off
 *   KNOB 1, 2    the ticks' and the gong's level (kept in flash)
 *   MIDI         CC 20 hours, CC 21 minutes, CC 22 seconds (any channel): the time is set when the seconds come
 *                (tools/settime.py sends the computer's)
 *   the keys     their lights follow the pendulum
 *
 * Time: TIMER4 counts the 24 MHz crystal; the audio interrupt turns it into half seconds and puts each tick on its
 * frame in the block it renders. The time is lost when the FM-1 is switched off, as a clock that stops: set it.
 * Integers only, no float, no 64-bit division (docs/RULES.md). The sound: clk_engine.h; the pictures: clk_draw.h. */
#define APP_NAME "FM1 CLOCK"
#define STORE_MAGIC 0x4B4C4346u                 /* "FCLK": this firmware's own settings (store.h) */
#include "platform.c"
#ifdef DINGHY_HOST
static uint32_t frames;
#define ENG_ON_HIT(e) printf("%6u ms  HIT at %.4f s, strength %u\n", fm1_ms, (frames + (e)->frame) / 44100.0, (e)->arg)
#endif
#include "clk_engine.h"
#include "clk_draw.h"

#define HALF_TICKS 12000000u                    /* half a second of the crystal */
#define DAY 172800u                             /* half seconds in a day */
#define HOUR 7200u
#define SWING 95443718u                         /* the pendulum's swing, each way: 8 degrees (2^32 = a turn) */
#define BOOT_TOD (10u * HOUR + 10u * 120u)      /* 10:10 at power-on */

/* ---- time: written by the audio interrupt (ck_*), read by the main loop through ck_seq */
static volatile uint32_t ck_half;               /* half seconds since power-on */
static volatile uint32_t ck_sub;                /* crystal ticks into this half second */
static volatile uint32_t ck_t4;                 /* the crystal when ck_sub was this */
static volatile uint32_t ck_seq;                /* odd while the three change */
static volatile uint32_t ck_off = BOOT_TOD;     /* (main) the time of day = ck_half + ck_off, modulo DAY */
static volatile uint32_t ck_silent;             /* (main) no strike on the hour */
static volatile uint32_t st_req_n, st_req_seq;  /* (main) strike n now */
static volatile uint32_t eng_off;               /* (main) the updater runs: no sound, the time goes on */
static volatile uint32_t tr_left;               /* (ISR) strikes still to come in this train */

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
static uint32_t ck_done, ck_started, tr_k, tr_t, tr_click, tr_seen;

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

static void train_start(uint32_t n, uint32_t at)  /* n strikes from frame at: the release click, 40 ms on the hit */
{
    tr_left = n;
    tr_k = 0;
    tr_t = at;
    tr_click = 1;
}

static void half_second(uint32_t h, uint32_t f, ev_t *ev, uint32_t *nev)   /* the pendulum at an end: a tick */
{
    uint32_t tod = (h + ck_off) % DAY;
    ev_add(ev, nev, f, h & 1u ? EV_TICK : EV_TOCK, 0);   /* one click at each end: the left, the right */
    if (!ck_silent && tod % 3600u == 0)
        train_start(tod % HOUR ? 1u : hour12(tod), frames + f);
}

static void app_audio(int32_t *out, uint32_t n)
{
    ev_t ev[12];
    uint32_t nev = 0, now = clk_now(), due, f;
    if (!ck_started) {                          /* (the audio starts before app_main: the time from here) */
        ck_started = 1;
        ck_t4 = now;
    }
    ck_seq++;
    ck_sub += now - ck_t4;
    ck_t4 = now;
    while (ck_sub >= HALF_TICKS) {
        ck_sub -= HALF_TICKS;
        ck_half++;
    }
    ck_seq++;
    if (ck_done != ck_half) {                   /* a half second went past between two blocks: its tick now */
        half_second(ck_half, 0, ev, &nev);
        ck_done = ck_half;
    }
    due = HALF_TICKS - ck_sub;                  /* the next one, if it falls in this block: on its frame */
    f = due * 147u / 80000u;                    /* (44100 / 24 M = 147 / 80000) */
    if (f < n) {
        half_second(ck_half + 1u, f, ev, &nev);
        ck_done = ck_half + 1u;
    }
    if (st_req_seq != tr_seen) {                /* the main loop asks: the repeat, the hands turned past */
        tr_seen = st_req_seq;
        train_start(st_req_n, frames);
    }
    while (tr_left && (int32_t)(tr_t - frames) < (int32_t)n) {
        uint32_t off = (int32_t)(tr_t - frames) < 0 ? 0 : tr_t - frames;
        if (tr_click) {
            ev_add(ev, &nev, off, EV_CLICK, 0);
            tr_t += CLICK_FRAMES + (eng_rnd() & 255u) - 128u;
            tr_click = 0;
        } else {                                /* the hammer: the first blow the hardest, the next a little less */
            uint32_t g = HAMMER[tr_k < 2u ? tr_k : 2u];
            ev_add(ev, &nev, off, EV_HIT, (g * (30800u + (eng_rnd() & 4095u))) >> 15);
            tr_k++;
            tr_left--;
            tr_t += TRAIN_FRAMES - CLICK_FRAMES + (eng_rnd() & 1023u) - 512u;
            tr_click = 1;
        }
    }
    if (!eng_off)
        eng_render(out, n, ev, nev);
    frames += n;
}

/* the time now, as the main loop sees it: half seconds since power-on, crystal ticks into the half */
static void clk_read(uint32_t *half, uint32_t *sub)
{
    uint32_t s, h, b, t;
    do {
        s = ck_seq;
        h = ck_half;
        b = ck_sub;
        t = ck_t4;
    } while ((s & 1u) || s != ck_seq);
    b += clk_now() - t;
    while (b >= HALF_TICKS) {
        b -= HALF_TICKS;
        h++;
    }
    *half = h;
    *sub = b;
}

/* ---- the panel */
static struct { uint8_t tick, gong, silent, digits, info, pad[3]; } set = {16, 16, 0, 0, 0, {0}};   /* levels: 16ths */
static uint32_t dirty, t_change, t_set, t_level, level_which, strike_due, strike_n, t_turn;

static void apply_set(void)
{
    eng_tick_lvl = set.tick * 16u;
    eng_gong_lvl = set.gong * 16u;
    ck_silent = set.silent;
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
static void draw_info(int force)                /* SEQ: the gong's operators on the chip (carriers + modulators + the
                                                   ticks'), and the share of the audio's time the engine takes */
{
    static uint32_t shown = ~0u, t_last;
    uint32_t ops = eng_st.ng + K_FM + 2u * NT, pct = eng_st.load / (BLOCK_TICKS / 100u), v;
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
        draw_text_box(BG_X + BG_W, 4, 240 - BG_X - BG_W, &FONT_S, s, RGB(150, 120, 90), 1);
        num(s, pct, "%");
        draw_text_box(BG_X + BG_W, 22, 240 - BG_X - BG_W, &FONT_S, s, RGB(150, 120, 90), 1);
    } else {
        lcd_fill(BG_X + BG_W, 4, 240 - BG_X - BG_W, 36, C_BLACK);
    }
}

static void draw_margins(uint32_t tod, int force)   /* the digits (left), the levels and SILENT (right) */
{
    static uint32_t shown_t = ~0u, shown_r = ~0u;
    uint32_t show_t = set.digits || fm1_ms - t_set < 3000u, t = show_t ? tod / 120u : 9999u, r;
    char s[12];
    if (t != shown_t || force) {
        shown_t = t;
        if (show_t) {
            s[0] = (char)('0' + t / 600u); s[1] = (char)('0' + t / 60u % 10u); s[2] = ':';
            s[3] = (char)('0' + t % 60u / 10u); s[4] = (char)('0' + t % 10u); s[5] = 0;
            draw_text_box(0, 104, BG_X, &FONT_S, s, RGB(224, 200, 150), 1);
        } else {
            lcd_fill(0, 104, BG_X, 16, C_BLACK);
        }
    }
    r = t_level && fm1_ms - t_level < 2000u ? 1u + level_which : 0u;
    r = r | (r ? (level_which ? set.gong : set.tick) << 2 : 0u) | set.silent << 9;
    if (r != shown_r || force) {
        shown_r = r;
        if (r & 3u) {
            uint32_t v = (r >> 2 & 127u) * 100u / 16u;
            draw_text_box(BG_X + BG_W, 96, 240 - BG_X - BG_W, &FONT_S, (r & 3u) == 1u ? "TICK" : "GONG", RGB(224, 200, 150), 1);
            s[0] = (char)(v >= 100u ? '0' + v / 100u : ' '); s[1] = (char)(v >= 10u ? '0' + v / 10u % 10u : ' ');
            s[2] = (char)('0' + v % 10u); s[3] = '%'; s[4] = 0;
            draw_text_box(BG_X + BG_W, 114, 240 - BG_X - BG_W, &FONT_S, s, RGB(224, 200, 150), 1);
        } else {
            lcd_fill(BG_X + BG_W, 96, 240 - BG_X - BG_W, 36, C_BLACK);
        }
        if (set.silent)
            draw_text_box(BG_X + BG_W, 214, 240 - BG_X - BG_W, &FONT_S, "SILENT", RGB(150, 120, 90), 1);
        else
            lcd_fill(BG_X + BG_W, 214, 240 - BG_X - BG_W, 16, C_BLACK);
    }
    draw_info(force);
}

static int is_black(uint32_t k) { return (0x54Au >> ((53u + k) % 12u)) & 1u; }

static void app_main(void)
{
    uint32_t last_dial = ~0u, t_win = 0, white[16], nw = 0, k, led_prev = 99;
    eng_init();
    if (settings_load(&set, sizeof set) || set.tick > 32u || set.gong > 32u || set.silent > 1u || set.digits > 1u || set.info > 1u) {
        set.tick = 16; set.gong = 16; set.silent = 0; set.digits = 0; set.info = 0;
    }
    apply_set();
#ifdef DINGHY_HOST
    {
        const char *e = getenv("CLK_NG");       /* the host renders a fixed number of carriers (all, by default) */
        eng_fixed_ng = e ? (uint32_t)atoi(e) : NG;
    }
#endif
    for (k = 0; k < 27u; k++)
        if (!is_black(k)) white[nw++] = k;
    draw_all();
    for (;;) {
        uint32_t h, sub, tod, rel, b, ph, th;
        int32_t e, cosq, bobx;
#ifndef DINGHY_HOST
        if (usb.ota_req)
            eng_off = 1;                        /* the updater gets the whole chip */
#endif
        platform_poll();
        midi_in();

        if ((e = fm1_enc_take(ENC_SELECT)) != 0)          /* a minute a detent */
            set_time((e < -60 ? -60 : e > 60 ? 60 : e) * 120);
        if ((e = fm1_enc_take(ENC_ALGORITHM)) != 0)       /* an hour */
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
        apply_set();
        if (strike_due && fm1_ms - t_turn > 500u) {   /* the hands have stopped: what they passed */
            strike_due = 0;
            strike_now(strike_n);
        }

        clk_read(&h, &sub);
        tod = (h + ck_off) % DAY;
        /* the hands: once a second (and when set) */
        if (tod / 2u != last_dial) {
            uint32_t m = tod % HOUR, fr = (uint32_t)(((uint64_t)sub * 13032u) >> 18);
            last_dial = tod / 2u;
            draw_dial((tod % 86400u) * 49710u, m * 596523u + fr);
        }
        /* the pendulum: cos of the half seconds, at both ends on the ticks; ~50 frames a second */
        ph = (h << 31) + (uint32_t)(((uint64_t)sub * 187649984u) >> 20);
        cosq = SINT[(ph + 1073741824u) >> 18];
        th = (uint32_t)(int32_t)(((int64_t)(int32_t)SWING * cosq) >> 15);
        if (fm1_ms - t_win >= 20u) {
            t_win = fm1_ms;
            draw_window(th);
        }
        /* the keys' lights: the white key under the bob */
        bobx = SINT[th >> 18];                  /* -sin(8 deg) .. sin(8 deg), Q15 */
        bobx = bobx < -4560 ? -4560 : bobx > 4560 ? 4560 : bobx;
        k = (uint32_t)((bobx + 4560) * 15 + 4560) / 9120u;
        if (k > 15u) k = 15u;
        if (k != led_prev) {
#if BOARD_SMK37
            uint32_t pd;                        /* (no key lights: the pads, in brass, under the bob) */
            for (pd = 0; pd < 16u; pd++) {
                uint32_t col = pd & 7u, on = col == k / 2u;
                padled_set(pd, on ? 200 : 6, on ? 120 : 3, on ? 30 : 0);
            }
            padled_flush();
#else
            if (led_prev < 16u) fm1_led_key(KEY_LED(white[led_prev]), 0);
            fm1_led_key(KEY_LED(white[k]), 1);
#endif
            led_prev = k;
        }
        fm1_led_key(BTN_FX, set.silent);
        fm1_led_key(BTN_PLAY, tr_left != 0);
        draw_margins(tod, 0);

        /* settings: 2 s after a change, when the gong is still and between two ticks (an erase stops the sound) */
        if (dirty && fm1_ms - t_change > 2000u && !eng_st.peak && !tr_left && sub > 2400000u && sub < 7200000u) {
            settings_save(&set, sizeof set);
            dirty = 0;
        }
    }
}
