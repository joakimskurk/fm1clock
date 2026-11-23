/* SPDX-License-Identifier: GPL-3.0-only */
/* Hamster Piano for the M-VAVE FM-1: eight hamsters that sing C D E F G A B C, a 16-step sequencer with four patterns
 * and a song of them, the Tromster (a drummer hamster with an 8-step drum machine) and THALLHAMSTERGRINDCORE (the same
 * hamsters, an octave down, through a wall of gain, at twice the tempo). A port of the web page of that name
 * (v4.17): its sound in ham_engine.h, its look in ham_draw.h, its hamsters in firmware/gen/ham_art.h.
 *
 * The page is played with a finger on a screen. Here:
 *   white keys   the hamsters: C4..C5 are the eight; F3..B3 the same hamsters an octave down, D5..G5 an octave up
 *   black keys   C#4 D#4 F#4 G#4: kick, snare, hat, clap, by hand
 *   PLAY         play / stop (the pattern, or the song with SONG on)
 *   REC          step recording: a hamster is written to the step and the step moves on; SEL writes a rest
 *   EDIT         the editor: a key changes the step's note and stays; SELECT walks the steps;
 *                KNOB 1 glide, KNOB 2 arpeggio (+7, +12), KNOB 3 accent, KNOB 4 ratchet (x1..x4); OCT- OCT+ its octave;
 *                ARP the arpeggio too; SEL deletes the step; SAVE copies it to the next; LFO a random pattern
 *   ENV          undo (12 deep)
 *   SELECT       the step       PRESETS  the pattern A B C D (while it plays: from the next bar)
 *   ALGORITHM    the tempo, 50..220 BPM
 *   KNOB 1..4    (not editing) swing, the hamsters' level, the Tromster's level, the MIDI channel
 *   OCT- OCT+    (not editing) the keys an octave down / up again
 *   SEQ          the Tromster's page (and the drums on); held: the drums on / off
 *                there: F3 G3 A3 B3 choose kick snare hat clap, C4..C5 set its eight steps, KNOB 1..4 their voices
 *   FX           THALLHAMSTERGRINDCORE on / off
 *   GLO          SONG on / off; held: the song's page (C4 D4 E4 F4 write A B C D, SEL takes one away)
 *   HOME         home; at home: the sign says something else; held: what the buttons do
 *   SEL          held: the pattern cleared
 *   SAVE         (not editing) everything to flash now (it also saves itself, when nothing sounds)
 *   MIDI         notes in play the hamsters (and are recorded with REC); clock, start, stop in: it follows;
 *                notes out: what the hamsters sing (the channel), the drums on channel 10
 *   USB audio    what the FM-1 plays, to record it (the page's WAV export)
 */
#define APP_NAME "HAMSTER PIANO"
#define STORE_MAGIC 0x524D4148u                 /* "HAMR": this firmware's own settings (store.h) */
#include "platform.c"
#include "ham_engine.h"
#include "ham_draw.h"

#ifndef DINGHY_HOST
static volatile uint32_t au_load, au_worst;     /* the last render and the longest, in crystal ticks (139320 a block) */
#endif
static void app_audio(int32_t *out, uint32_t n)
{
#ifndef DINGHY_HOST
    uint32_t t0 = fm1_ticks(), dt;
    heng_render(out, n);
    dt = fm1_ticks() - t0;
    au_load = dt;
    if (dt > au_worst)
        au_worst = dt;
#else
    heng_render(out, n);
#endif
}

/* ---- what is kept in flash */
#define SV_VER 3u
typedef struct {
    uint8_t ver, bpm, active, song_mode, drums_on, thall, cur_step, swing, lvl_ham, lvl_drum, midi_ch, song_len;
    int8_t kb_oct;
    uint8_t pad[3];
    uint16_t pat[4][16];
    uint8_t drum[4][4], dvoice[4][4], song[64];
} save_t;
static save_t sv;

enum { PG_HOME, PG_TROM, PG_SONG, PG_HELP };
static uint32_t page, rec_on, edit_on, cur_step = 7, active, playing, song_playing, ext_sync, play_step, play_pat, song_pos;
static uint32_t sel_key, trom_row, song_cur, help_page, song_mode, drums_on, thall, bpm = 120, swing, lvl_ham = 16, lvl_drum = 16;
static uint32_t midi_ch, dirty, t_change, save_now;
static int32_t kb_oct;
static uint32_t t_ham[8], t_logo, logo_dance, t_sign, sign_on, lore_i = 99, t_status;
static char status[64], sign1[40], sign2[40];
/* what has to be drawn again */
static uint32_t rd_all = 1, rd_logo, rd_hams, rd_steps, rd_bot, rd_page;
static uint32_t ham_shown[8];
/* the drummer */
static uint32_t dr_frame, dr_step_t, dr_hit, dr_alt, dr_prev_t, dr_prev_kind;

static uint32_t rnd_s = 0x1234567u;
static uint32_t rnd(uint32_t n) { rnd_s = rnd_s * 1664525u + 1013904223u; return (rnd_s >> 8) % n; }

/* ---- small strings without a C library */
static char *sb;
static void sb_s(const char *s) { while (*s) *sb++ = *s++; *sb = 0; }
static void sb_u(uint32_t v)
{
    char d[10];
    uint32_t n = 0;
    do { d[n++] = (char)('0' + v % 10u); v /= 10u; } while (v);
    while (n) *sb++ = d[--n];
    *sb = 0;
}
static void sb_c(char c) { *sb++ = c; *sb = 0; }
static void sb_step(uint32_t i) { sb_c((char)('A' + active)); sb_u(i + 1u); }   /* "A8" */
static void sb_note(uint32_t s, int words)      /* "C↓2~↕7!×3", or in words */
{
    int32_t o = ST_OCT(s);
    sb_s(NOTE_NAME[ST_KEY(s)]);
    if (o) { sb_s(o < 0 ? "↓" : "↑"); if (o < -1 || o > 1) sb_u((uint32_t)(o < 0 ? -o : o)); }
    if (words) sb_c(' ');
    if (ST_GLIDE(s)) sb_c('~');
    if (ST_ARP(s)) { sb_s("↕"); sb_u(ST_ARP(s) == 1u ? 7u : 12u); }
    if (ST_ACCENT(s)) sb_c('!');
    if (ST_RATCHET(s) > 1u) { sb_s("×"); sb_u(ST_RATCHET(s)); }
}
static void say(const char *s)                  /* the status line */
{
    uint32_t i;
    for (i = 0; s[i] && i < sizeof status - 1u; i++) status[i] = s[i];
    status[i] = 0;
    t_status = fm1_ms;
    rd_bot = 1;
}
#define SAY_BEGIN() do { static char b_[64]; sb = b_; b_[0] = 0;
#define SAY_END() say(b_); } while (0)

static void touch(void) { dirty = 1; t_change = fm1_ms; }

/* ---- the sign: the hamster's wisdom, two lines */
static const char *const LORE[][2] = {
    {"HAMSTEREN VET.", ""}, {"IKKE SI", "«BARE EN HAMSTER»."}, {"FRØ TILHØRER", "HAMSTEREN."},
    {"IKKE DRA I", "HAMSTEREN MIN!"}, {"LODDRETTUS", "ERECTUS."}, {"1 CM ≈ 1 STOR", "SOLSIKKEFRØENHET"},
    {"GYLFENS", "GYLNE SNITT"}, {"SKUFFET BLIKK.", ""}, {"HAMSTER ER OFTE", "ET DYR."}, {"PRODUKSJONSMASKIN", ""},
    {"I HAMSTERDAM", ""}, {"NEPPE BEDRE ENN", "HAMSTERMELK"}, {"HAMSTEREN", "HAR TALT."}, {"STOL PÅ", "HAMSTEREN."},
};
#define NLORE (sizeof LORE / sizeof LORE[0])
static void sign(const char *a, const char *b, uint32_t ms)
{
    uint32_t i;
    for (i = 0; a[i] && i < sizeof sign1 - 1u; i++) sign1[i] = a[i];
    sign1[i] = 0;
    for (i = 0; b[i] && i < sizeof sign2 - 1u; i++) sign2[i] = b[i];
    sign2[i] = 0;
    sign_on = 1;
    t_sign = fm1_ms + ms;
    rd_bot = 1;
}
static void lore(void)
{
    uint32_t i;
    do { i = rnd(NLORE); } while (i == lore_i);
    lore_i = i;
    sign(LORE[i][0], LORE[i][1], 4000);
}

/* ---- the engine's copy of what the main loop owns */
static void push_all(void)
{
    hq.bpm = bpm;
    hq.thall = thall;
    hq.drums_on = drums_on;
    hq.swing = swing;
    hq.want_pat = active;
    hq.lvl_ham = lvl_ham * 16u;
    hq.lvl_drum = lvl_drum * 16u;
}

static void defaults(void)
{
    static const uint8_t A[16][2] = {{0, 2}, {2, 3}, {4, 3}, {2, 3}, {2, 2}, {4, 3}, {2, 3}, {1, 3},
                                     {3, 2}, {4, 3}, {5, 3}, {7, 3}, {4, 2}, {6, 3}, {4, 3}, {1, 3}};
    static const char SONG[] = "AABACCDC";
    uint32_t p, i;
    for (p = 0; p < 4u; p++) {
        for (i = 0; i < 16u; i++)
            hq.pat[p][i] = p ? 0u : (uint16_t)(ST_ON | A[i][0] | (uint32_t)A[i][1] << 3);
        hq.drum[p][DR_KICK] = 0x11;
        hq.drum[p][DR_SNARE] = 0x44;
        hq.drum[p][DR_HAT] = 0xFF;
        hq.drum[p][DR_CLAP] = 0x00;
        for (i = 0; i < 4u; i++)
            hq.dvoice[p][i] = 0;
    }
    for (i = 0; i < 8u; i++)
        hq.song[i] = (uint8_t)(SONG[i] - 'A');
    hq.song_len = 8;
    bpm = 120; active = 0; song_mode = 0; drums_on = 0; thall = 0; cur_step = 7; swing = 0;
    lvl_ham = lvl_drum = 16; midi_ch = 0; kb_oct = 0;
}

static void store_load(void)
{
    uint32_t p, i, ok;
    defaults();
    ok = !settings_load(&sv, sizeof sv) && sv.ver == SV_VER && sv.bpm >= 50u && sv.bpm <= 220u && sv.active < 4u &&
         sv.cur_step < 16u && sv.swing <= 60u && sv.lvl_ham <= 32u && sv.lvl_drum <= 32u && sv.midi_ch <= 16u &&
         sv.song_len >= 1u && sv.song_len <= 64u && sv.kb_oct >= -2 && sv.kb_oct <= 0;
    if (!ok)
        return;
    for (p = 0; p < 4u; p++) {
        for (i = 0; i < 16u; i++) {
            uint32_t s = sv.pat[p][i];
            hq.pat[p][i] = (uint16_t)((s & ST_ON) && ((s >> 3) & 7u) <= 4u ? s & 0x8FFFu : 0u);
        }
        for (i = 0; i < 4u; i++) {
            hq.drum[p][i] = sv.drum[p][i];
            hq.dvoice[p][i] = sv.dvoice[p][i] % 3u;
        }
    }
    for (i = 0; i < 64u; i++)
        hq.song[i] = sv.song[i] & 3u;
    hq.song_len = sv.song_len;
    bpm = sv.bpm; active = sv.active; song_mode = sv.song_mode & 1u; drums_on = sv.drums_on & 1u; thall = sv.thall & 1u;
    cur_step = sv.cur_step; swing = sv.swing; lvl_ham = sv.lvl_ham; lvl_drum = sv.lvl_drum; midi_ch = sv.midi_ch;
    kb_oct = sv.kb_oct;
}

static void store_save(void)
{
    uint32_t p, i;
    sv.ver = SV_VER; sv.bpm = (uint8_t)bpm; sv.active = (uint8_t)active; sv.song_mode = (uint8_t)song_mode;
    sv.drums_on = (uint8_t)drums_on; sv.thall = (uint8_t)thall; sv.cur_step = (uint8_t)cur_step; sv.swing = (uint8_t)swing;
    sv.lvl_ham = (uint8_t)lvl_ham; sv.lvl_drum = (uint8_t)lvl_drum; sv.midi_ch = (uint8_t)midi_ch;
    sv.song_len = (uint8_t)hq.song_len; sv.kb_oct = (int8_t)kb_oct;
    sv.pad[0] = sv.pad[1] = sv.pad[2] = 0;
    for (p = 0; p < 4u; p++) {
        for (i = 0; i < 16u; i++) sv.pat[p][i] = hq.pat[p][i];
        for (i = 0; i < 4u; i++) { sv.drum[p][i] = hq.drum[p][i]; sv.dvoice[p][i] = hq.dvoice[p][i]; }
    }
    for (i = 0; i < 64u; i++) sv.song[i] = hq.song[i];
    settings_save(&sv, sizeof sv);
    dirty = 0;
}

/* ---- undo: the pattern as it was, twelve deep */
static struct { uint8_t pat, cur; uint16_t s[16]; } undo[12];
static uint32_t undo_n;
static void undo_push(void)
{
    uint32_t i;
    if (undo_n == 12u) {
        for (i = 1; i < 12u; i++) undo[i - 1u] = undo[i];
        undo_n = 11;
    }
    undo[undo_n].pat = (uint8_t)active;
    undo[undo_n].cur = (uint8_t)cur_step;
    for (i = 0; i < 16u; i++) undo[undo_n].s[i] = hq.pat[active][i];
    undo_n++;
}
static void set_active(uint32_t p)
{
    active = p & 3u;
    hq.want_pat = active;
    rd_steps = 0xFFFF; rd_bot = 1; rd_page = 1;
    touch();
}
static void undo_pop(void)
{
    uint32_t i;
    if (!undo_n) { say("INGENTING Å ANGRE"); return; }
    undo_n--;
    set_active(undo[undo_n].pat);
    for (i = 0; i < 16u; i++) hq.pat[active][i] = undo[undo_n].s[i];
    cur_step = undo[undo_n].cur;
    SAY_BEGIN(); sb_s("ANGRET · SEKVENS "); sb_c((char)('A' + active)); SAY_END();
}

/* ---- transport */
static void stop(int tell)
{
    heng_cmd(HCMD(HC_STOP, 0));
    playing = song_playing = ext_sync = 0;
    play_step = 0; song_pos = 0; play_pat = active;
    logo_dance = 0;
    rd_logo = rd_bot = rd_page = 1; rd_steps = 0xFFFF;
    if (tell) say("STOPPET");
}
static void play(void)
{
    playing = 1;
    song_playing = song_mode;
    ext_sync = 0;
    play_step = 0; song_pos = 0;
    play_pat = song_mode ? hq.song[0] : active;
    hq.want_pat = active;
    heng_cmd(HCMD(HC_PLAY, song_mode));
    if (song_mode) say("SPILLER SONG");
    else { SAY_BEGIN(); sb_s("SPILLER SEKVENS "); sb_c((char)('A' + active)); SAY_END(); }
    rd_bot = rd_page = 1; rd_steps = 0xFFFF;
}

/* ---- a white key: which hamster, which octave. k: 0 (F3) .. 26 (G5) */
static const int8_t KEY_HAM[27] = {3, -1, 4, -1, 5, -1, 6, 0, -1, 1, -1, 2, 3, -1, 4, -1, 5, -1, 6, 7, -1, 1, -1, 2, 3, -1, 4};
static const int8_t KEY_OCT[27] = {-1, 0, -1, 0, -1, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 1};
static const uint8_t HAM_KEYLED[8] = {7, 9, 11, 12, 14, 16, 18, 19};   /* the eight's own keys: C4..C5 */
static const char *const DRUM_NAME[4] = {"KICK", "SNARE", "HAT", "CLAP"};

static void sing(uint32_t key, int32_t oct, uint32_t vel)   /* a hamster by hand (vel 0: the page's own) */
{
    uint32_t midi = (uint32_t)((int32_t)HAM_MIDI[key] + 12 * oct);
    heng_cmd(HCMD(HC_NOTE, midi | key << 7 | vel << 10));
}
static void preview(uint32_t step)
{
    if (hq.pat[active][step] & ST_ON)
        heng_cmd(HCMD(HC_PREVIEW, step | active << 4));
}
static void step_say(uint32_t step)
{
    uint32_t s = hq.pat[active][step];
    SAY_BEGIN();
    sb_step(step);
    if (s & ST_ON) { sb_s(" · "); sb_note(s, 0); } else sb_s(" · TOMT");
    SAY_END();
}

/* a hamster pressed: key 0..7, its octave -3..+1; vel: MIDI velocity, 0 from the keys */
static void press(uint32_t key, int32_t oct, uint32_t vel)
{
    oct = oct < -3 ? -3 : oct > 1 ? 1 : oct;
    sel_key = key;
    if (page == PG_HOME && edit_on) {           /* the editor: the step's note changes, its effects stay */
        uint32_t s = hq.pat[active][cur_step];
        undo_push();
        hq.pat[active][cur_step] = (uint16_t)((s & ST_ON) ? (s & ~0x3Fu) | key | (uint32_t)(oct + 3) << 3 : ST_MAKE(key, oct));
        preview(cur_step);
        SAY_BEGIN(); sb_step(cur_step); sb_s(" · TONE → "); sb_s(NOTE_NAME[key]); SAY_END();
        rd_steps |= 1u << cur_step;
        touch();
        return;
    }
    sing(key, oct, vel);
    if (page == PG_HOME && rec_on) {            /* step recording: written, and on to the next */
        uint32_t step = cur_step;
        undo_push();
        hq.pat[active][step] = ST_MAKE(key, oct);
        cur_step = (cur_step + 1u) & 15u;
        SAY_BEGIN(); sb_step(step); sb_s(" · "); sb_s(NOTE_NAME[key]); sb_s(" LAGRET"); SAY_END();
        rd_steps |= 1u << step | 1u << cur_step;
        touch();
    } else if (page == PG_HOME) {
        SAY_BEGIN(); sb_s("HAMSTER "); sb_u(key + 1u); sb_s(" · "); sb_s(NOTE_NAME[key]); SAY_END();
    }
}

static void randomize(void)                     /* the page's: a tune in C that comes home */
{
    static const int8_t MOVE[9] = {-2, -1, -1, -1, 0, 1, 1, 1, 2};
    static const uint8_t C024[3] = {0, 2, 4}, C0245[4] = {0, 2, 4, 5}, C542[3] = {5, 4, 2}, C421[3] = {4, 2, 1};
    static const int8_t M1001[4] = {-1, 0, 0, 1};
    int32_t k = C024[rnd(3)];
    uint32_t i;
    if (playing) stop(0);
    undo_push();
    for (i = 0; i < 16u; i++) {
        if ((i & 3u) == 3u && i != 15u && rnd(100) < 16u) {
            hq.pat[active][i] = 0;
            continue;
        }
        if (i == 0u) k = C024[rnd(3)];
        else if (i == 4u || i == 8u) k = C0245[rnd(4)] + M1001[rnd(4)];
        else if (i == 12u) k = C542[rnd(3)];
        else if (i == 13u) k = C421[rnd(3)];
        else if (i == 14u) k = rnd(2) ? 2 : 1;
        else if (i == 15u) k = 0;
        else k += MOVE[rnd(9)];
        k = k < 0 ? 0 : k > 7 ? 7 : k;
        hq.pat[active][i] = ST_MAKE((uint32_t)k, 0);
    }
    cur_step = 0;
    rec_on = 0;
    edit_on = 1;
    say("NY RANDOMISERT SEKV.");
    rd_steps = 0xFFFF; rd_bot = 1;
    touch();
}

static void set_thall(uint32_t on)
{
    if (thall && !on)
        heng_cmd(HCMD(HC_CHOKE, 0));
    thall = on;
    hq.thall = thall;
    if (thall) {
        static char l2[24];
        sb = l2; l2[0] = 0;
        sb_s("GRINDCORE · "); sb_u(bpm * 2u); sb_s(" BPM");
        sign("THALLHAMSTER-", l2, 2600);
        say("-1 OKT · VRENG · ×2");
    } else {
        SAY_BEGIN(); sb_s("HAMSTER MODE · "); sb_u(bpm); SAY_END();
    }
    rd_logo = rd_bot = 1;
    touch();
}

/* ---- drawing */
static uint32_t disp_pat(void) { return song_playing ? play_pat : active; }

static void draw_bottom(void)
{
    uint32_t i;
    char t[12];
    if (sign_on) {                              /* the sign, over both rows */
        fb_rect(0, Y_BOT, 240, 32, C_INK);
        fb_rect(1, Y_BOT + 1, 238, 30, C_SIGN);
        if (sign2[0]) {
            fb_text_mid(0, 240, Y_BOT + 2, sign1, C_INK, 2);
            fb_text_mid(0, 240, Y_BOT + 17, sign2, C_INK, 2);
        } else {
            fb_text_mid(0, 240, Y_BOT + 9, sign1, C_INK, 2);
        }
        return;
    }
    fb_rect(0, Y_BOT, 240, 16, C_INK);
    fb_rect(0, Y_BOT + 1, 240, 15, C_CREAM);
    for (i = 0; i < 4u; i++) {                  /* the patterns */
        uint32_t now = playing && play_pat == i, act = i == active && !song_playing;
        char s[2] = {(char)('A' + i), 0};
        fb_rect(1 + (int32_t)i * 19, Y_BOT + 1, 18, 15, act ? C_YELLOW : now ? C_PINK : C_INK2);
        fb_text(5 + (int32_t)i * 19, Y_BOT + 2, s, act || now ? C_INK : C_CREAM2, 2);
    }
    sb = t; t[0] = 0;
    sb_u(bpm * (thall ? 2u : 1u));
    fb_rect(80, Y_BOT + 1, 42, 15, C_INK2);
    fb_text_mid(80, 42, Y_BOT + 2, t, C_CREAM2, 2);
    {                                           /* what it is doing */
        static char st[16];
        uint16_t bg = C_CREAM, fg = C_INK;
        sb = st; st[0] = 0;
        if (ext_sync) { sb_s("EXT SYNC"); bg = C_BLUE; fg = C_CREAM2; }
        else if (rec_on) { sb_s("● REC"); bg = C_PINK2; fg = C_WHITE2; }
        else if (song_playing) { sb_s("SONG "); sb_u(song_pos + 1u); sb_c('/'); sb_u(hq.song_len); bg = C_PINK; }
        else if (playing) { sb_s("SPILLER"); bg = C_PINK; }
        else if (edit_on) { sb_s("REDIGER"); bg = C_YELLOW; }
        else if (song_mode) sb_s("SONG PÅ");
        else sb_s("KLAR");
        fb_rect(124, Y_BOT + 1, 116, 15, bg);
        fb_text_mid(124, 116, Y_BOT + 2, st, fg, 2);
    }
    fb_rect(0, Y_BOT + 16, 240, 16, C_INK);
    fb_rect(0, Y_BOT + 17, 240, 15, C_PAPER);
    fb_text(text_px(status, 2) > 232 ? 1 : 4, Y_BOT + 17, status, C_INK, 2);
}

static void draw_home(void)                     /* the hamsters that changed, the steps that changed */
{
    uint32_t i, p = disp_pat();
    for (i = 0; i < 8u; i++) {
        uint32_t age = t_ham[i] ? fm1_ms - t_ham[i] : 9999u, st, sq = 0;
        if (thall) {                            /* the page's hard press: flat, then nearly, then up */
            if (age < 45u) sq = 46;
            else if (age < 90u) sq = 49;
            else if (age < 135u) sq = 0;
            st = age < 135u ? 2u : i == sel_key ? 1u : 0u;
        } else {
            if (age < 60u) sq = 62;
            st = age < 120u ? 2u : i == sel_key ? 1u : 0u;
        }
        if (age >= 135u) t_ham[i] = 0;
        if ((rd_hams >> i & 1u) || ham_shown[i] != (st | sq << 4)) {
            ham_shown[i] = st | sq << 4;
            draw_ham(i, st, sq);
        }
    }
    rd_hams = 0;
    for (i = 0; i < 16u; i++)
        if (rd_steps >> i & 1u)
            draw_step(i, hq.pat[p][i], !song_playing && i == cur_step, playing && play_pat == p && i == play_step);
    rd_steps = 0;
}

static const uint16_t DRUM_COL[4] = {C_PINK, C_CREAM2, C_YELLOW, C_SKY};
static void draw_trom(void)
{
    uint32_t r, i, p = disp_pat();
    char t[12];
    fb_rect(0, Y_HAM, 240, Y_BOT - Y_HAM, C_INK2);
    draw_drummer(dr_frame);
    fb_text(126, 30, "TROMSTER", C_YELLOW, 2);
    fb_rect(126, 50, 17, 17, C_YELLOW);
    t[0] = (char)('A' + p); t[1] = 0;
    fb_text(129, 52, t, C_INK, 2);
    fb_text(150, 52, drums_on ? "PÅ" : "AV", drums_on ? C_CREAM2 : C_PINK, 2);
    fb_text(126, 76, "8 STEG · SYNC", C_MUTED, 1);
    fb_text(126, 90, "F3-B3 VELG TROMME", C_MUTED, 1);
    fb_text(126, 102, "C4-C5 STEG 1-8", C_MUTED, 1);
    fb_text(126, 114, "KNOTT 1-4 LYD", C_MUTED, 1);
    for (r = 0; r < 4u; r++) {
        int32_t y = 131 + (int32_t)r * 19;
        fb_rect(1, y, 70, 18, r == trom_row ? C_YELLOW : C_BLUE3);
        fb_text(4, y + 2, DRUM_NAME[r], r == trom_row ? C_INK : C_CREAM2, 2);
        t[0] = (char)('1' + hq.dvoice[p][r]); t[1] = 0;
        fb_text(64, y + 9, t, r == trom_row ? C_INK : C_MUTED, 1);
        for (i = 0; i < 8u; i++) {
            uint32_t on = hq.drum[p][r] >> i & 1u, now = playing && (play_step & 7u) == i;
            int32_t x = 72 + (int32_t)i * 21, m = now ? 2 : 1;
            fb_rect(x, y, 20, 18, now ? C_WHITE2 : C_EDGE);
            fb_rect(x + m, y + m, 20 - 2 * m, 18 - 2 * m, on ? DRUM_COL[r] : C_BLUE3);
        }
    }
}

static void draw_song(void)
{
    uint32_t i;
    char t[24];
    fb_rect(0, Y_HAM, 240, Y_BOT - Y_HAM, C_INK2);
    fb_text(8, 32, "SONG", C_YELLOW, 2);
    fb_text(64, 32, song_mode ? "PÅ" : "AV", song_mode ? C_CREAM2 : C_PINK, 2);
    sb = t; t[0] = 0;
    sb_u(hq.song_len); sb_s("/64");
    fb_text(232 - text_px(t, 2), 32, t, C_MUTED, 2);
    for (i = 0; i < 64u; i++) {
        int32_t x = 8 + (int32_t)(i & 15u) * 14, y = 56 + (int32_t)(i >> 4) * 20;
        uint32_t now = song_playing && i == song_pos;
        if (i < hq.song_len) {
            char s[2] = {(char)('A' + hq.song[i]), 0};
            fb_rect(x, y, 13, 17, now ? C_PINK : C_BLUE3);
            fb_text(x + 2, y + 2, s, now ? C_INK : C_CREAM2, 2);
        } else {
            fb_rect(x, y, 13, 17, C_CELL0);
        }
        if (i == song_cur)
            fb_frame(x - 1, y - 1, 15, 19, 2, C_YELLOW);
    }
    fb_text(8, 146, "C D E F  SKRIV A B C D", C_MUTED, 1);
    fb_text(8, 158, "SELECT  FLYTT · PRESETS  BYTT", C_MUTED, 1);
    fb_text(8, 170, "SEL  SLETT · GLO  PÅ/AV · HOME  UT", C_MUTED, 1);
    fb_text(8, 188, "PLAY SPILLER REKKEN", C_CREAM2, 1);
}

static const char *const HELP[3][13] = {
    {"SLIK FUNKER DET 1/3", "HVITE   HAMSTERE", "SVARTE  TROMMER", "PLAY    SPILL/STOPP", "REC     STEG-OPPTAK",
     "SEL     PAUSE I REC", "EDIT    REDIGER", "SELECT  VELG STEG", "PRESETS SEKVENS A-D", "ALGORITHM TEMPO",
     "OCT-/+  OKTAV", "ENV     ANGRE", "HOLD SEL: SLETT ALT"},
    {"REDIGER          2/3", "TANGENT BYTT TONE", "KNOTT 1 GLIDE", "KNOTT 2 ARP +7/+12", "KNOTT 3 ACCENT",
     "KNOTT 4 RATCHET ×1-4", "OCT-/+  STEGETS OKT.", "ARP     ARP +7/+12", "SEL     SLETT STEG", "SAVE    KOPIER →",
     "LFO     RANDOMISER", "ENV     ANGRE", ""},
    {"MER              3/3", "SEQ     TROMSTER", "HOLD SEQ TROMMER AV", "FX      THALLHAMSTER", "        GRINDCORE",
     "GLO     SONG AV/PÅ", "HOLD GLO SONG-REKKE", "HOME    HJEM/SKILT", "KNOTT 1-4 UTENFOR", " REDIGER: SWING,",
     " HAMSTER, TROMSTER,", " MIDI-KANAL", "USB: LYD OG MIDI"},
};
static void draw_help(void)
{
    uint32_t i;
    fb_rect(0, Y_HAM, 240, 240 - Y_HAM, C_INK2);
    for (i = 0; i < 13u; i++)
        fb_text(1, 28 + (int32_t)i * 16, HELP[help_page][i], i ? C_CREAM2 : C_YELLOW, 2);
}

static void draw(void)
{
    static uint32_t page_shown = 99;
    if (rd_all || page != page_shown) {
        page_shown = page;
        rd_all = 0;
        rd_logo = rd_bot = rd_page = 1;
        rd_hams = 0xFF; rd_steps = 0xFFFF;
    }
    if (rd_logo) {
        rd_logo = 0;
        draw_logo(thall, logo_dance);
    }
    if (page == PG_HOME) {
        draw_home();
    } else if (rd_page) {
        if (page == PG_TROM) draw_trom();
        else if (page == PG_SONG) draw_song();
        else draw_help();
    }
    rd_page = 0;
    if (rd_bot && page != PG_HELP) {
        rd_bot = 0;
        draw_bottom();
    }
    fb_flush();
}

/* ---- the keys' and the buttons' lights */
static void leds(void)
{
    static uint32_t lit_shown = ~0u, glow_shown = ~0u, btn_shown = ~0u;
    uint32_t lit = 0, glow = 0, btn = 0, k, p = disp_pat();
    if (page == PG_TROM) {                      /* the row's steps on C4..C5; the four drums on F3..B3 */
        static const uint8_t ROWKEY[4] = {0, 2, 4, 6};
        for (k = 0; k < 8u; k++) {
            uint32_t on = hq.drum[p][trom_row] >> k & 1u, now = playing && (play_step & 7u) == k;
            if (on != now) lit |= 1u << HAM_KEYLED[k];
            else if (!on) glow |= 1u << HAM_KEYLED[k];
        }
        for (k = 0; k < 4u; k++) {
            if (k == trom_row) lit |= 1u << ROWKEY[k];
            else glow |= 1u << ROWKEY[k];
        }
    } else if (page == PG_SONG) {
        for (k = 0; k < 4u; k++)
            glow |= 1u << HAM_KEYLED[k];
    } else {                                    /* the eight glow; the one that sings is lit */
        for (k = 0; k < 8u; k++) {
            if (t_ham[k] && fm1_ms - t_ham[k] < 120u) lit |= 1u << HAM_KEYLED[k];
            else glow |= 1u << HAM_KEYLED[k];
        }
    }
    glow |= 1u << 8 | 1u << 10 | 1u << 13 | 1u << 15;   /* the drums' black keys */
    if (playing && ((play_step & 3u) || fm1_ms - t_logo >= 60u))
        btn |= 1u << BTN_PLAY;                  /* (it winks on the beat) */
    if (rec_on) btn |= 1u << BTN_REC;
    if (edit_on) btn |= 1u << BTN_EDIT;
    if (drums_on) btn |= 1u << BTN_SEQ;
    if (thall) btn |= 1u << BTN_FX;
    if (song_mode) btn |= 1u << BTN_GLO;
    if (lit != lit_shown || glow != glow_shown) {
        for (k = 0; k < 27u; k++) {
            if ((lit ^ lit_shown) >> k & 1u) fm1_led_key(KEY_LED(k), (int)(lit >> k & 1u));
            if ((glow ^ glow_shown) >> k & 1u) fm1_led_key_glow(KEY_LED(k), (int)(glow >> k & 1u));
        }
        lit_shown = lit;
        glow_shown = glow;
    }
    if (btn != btn_shown) {
        static const uint8_t B[6] = {BTN_PLAY, BTN_REC, BTN_EDIT, BTN_SEQ, BTN_FX, BTN_GLO};
        for (k = 0; k < 6u; k++)
            fm1_led_key(B[k], (int)(btn >> B[k] & 1u));
        btn_shown = btn;
    }
}

/* ---- MIDI */
static struct { uint8_t on, st, note; uint32_t at; } m_off[12];
static void midi_note_out(uint32_t st, uint32_t note, uint32_t vel)
{
    uint32_t i, best = 0;
    for (i = 0; i < 12u; i++) {
        if (!m_off[i].on) { best = i; break; }
        if ((int32_t)(m_off[i].at - m_off[best].at) < 0) best = i;
    }
    if (m_off[best].on)
        midi_send(m_off[best].st & 0xEFu, m_off[best].note, 0);
    midi_send(st, note, vel ? vel : 1u);
    m_off[best].on = 1;
    m_off[best].st = (uint8_t)st;
    m_off[best].note = (uint8_t)note;
    m_off[best].at = fm1_ms + 90u;
}
static void midi_offs(void)
{
    uint32_t i;
    for (i = 0; i < 12u; i++)
        if (m_off[i].on && (int32_t)(fm1_ms - m_off[i].at) >= 0) {
            midi_send(m_off[i].st & 0xEFu, m_off[i].note, 0);
            m_off[i].on = 0;
        }
}

static void midi_in(void)
{
    static const int8_t PC_KEY[12] = {0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6};
    static const uint8_t PC_WHITE[12] = {1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1};
    uint8_t st, d1, d2;
    while (midi_get(&st, &d1, &d2)) {
        if (st == 0xFAu || st == 0xFBu) {       /* start, continue: it follows the clock from here */
            if (playing && !ext_sync)
                heng_cmd(HCMD(HC_STOP, 0));
            playing = 1; ext_sync = 1; song_playing = song_mode;
            if (st == 0xFAu) { play_step = 0; song_pos = 0; }
            hq.want_pat = active;
            heng_cmd(HCMD(HC_EXT_START, (st == 0xFBu ? 1u : 0u) | (song_mode ? 2u : 0u)));
            say("FØLGER MIDI-KLOKKE");
            rd_bot = rd_page = 1; rd_steps = 0xFFFF;
            continue;
        }
        if (st == 0xFCu) {
            if (ext_sync) stop(1);
            continue;
        }
        if (st == 0xF8u) {
            if (ext_sync) heng_cmd(HCMD(HC_EXT_CLOCK, 0));
            continue;
        }
        if (midi_ch && (st & 15u) != midi_ch - 1u)
            continue;
        if ((st & 0xF0u) == 0x90u && d2) {
            uint32_t pc = d1 % 12u, key = (uint32_t)PC_KEY[pc];
            int32_t oct = (int32_t)d1 / 12 - 5;
            if (d1 < 24u || d1 > 96u)
                continue;
            if (PC_WHITE[pc] && (rec_on || edit_on) && page == PG_HOME && oct >= -3 && oct <= 1) {
                press(key, oct, d2);            /* a white note: as the keys, recorded too */
            } else {
                heng_cmd(HCMD(HC_NOTE, d1 | key << 7 | (uint32_t)d2 << 10));
                sel_key = key;
            }
        }
    }
}

/* ---- the panel */
static void tempo(int32_t e)
{
    int32_t v = (int32_t)bpm + e;
    bpm = (uint32_t)(v < 50 ? 50 : v > 220 ? 220 : v);
    hq.bpm = bpm;
    SAY_BEGIN(); sb_s("TEMPO "); sb_u(bpm * (thall ? 2u : 1u)); sb_s(" BPM"); if (thall) sb_s(" · ×2"); SAY_END();
    touch();
}

static void step_fx(uint32_t which, int32_t e)   /* the editor's knobs: 0 glide, 1 arpeggio, 2 accent, 3 ratchet */
{
    uint32_t s = hq.pat[active][cur_step], v;
    if (!(s & ST_ON)) { say("TOMT STEG · VELG TONE"); return; }
    undo_push();
    if (which == 0u) {
        s = e > 0 ? s | 1u << 6 : s & ~(1u << 6);
    } else if (which == 1u) {
        int32_t a = (int32_t)ST_ARP(s) + (e > 0 ? 1 : -1);
        a = a < 0 ? 0 : a > 2 ? 2 : a;
        s = (s & ~(3u << 8)) | (uint32_t)a << 8;
    } else if (which == 2u) {
        s = e > 0 ? s | 1u << 7 : s & ~(1u << 7);
    } else {
        int32_t r = (int32_t)ST_RATCHET(s) + (e > 0 ? 1 : -1);
        r = r < 1 ? 1 : r > 4 ? 4 : r;
        s = (s & ~(3u << 10)) | (uint32_t)(r - 1) << 10;
    }
    hq.pat[active][cur_step] = (uint16_t)s;
    v = which == 0u ? ST_GLIDE(s) : which == 1u ? ST_ARP(s) : which == 2u ? ST_ACCENT(s) : ST_RATCHET(s);
    SAY_BEGIN();
    sb_step(cur_step); sb_s(" · ");
    if (which == 0u) sb_s(v ? "GLIDE PÅ" : "GLIDE AV");
    else if (which == 1u) sb_s(v == 0u ? "ARP AV" : v == 1u ? "ARP +7" : "ARP +12");
    else if (which == 2u) sb_s(v ? "ACCENT PÅ" : "ACCENT AV");
    else { sb_s("RATCHET ×"); sb_u(v); }
    SAY_END();
    preview(cur_step);
    rd_steps |= 1u << cur_step;
    touch();
}

static void go_page(uint32_t p)
{
    page = p;
    rd_all = 1;
}

static void drum_try(uint32_t d, uint32_t voice_changed)
{
    heng_cmd(HCMD(HC_DRUM, d | (uint32_t)hq.dvoice[active][d] << 2 | (voice_changed ? 16u : 0u)));
}

static void buttons(void)
{
    static uint32_t t_down[32], armed, fired;
    static const uint8_t HOLD[4] = {BTN_HOME, BTN_GLO, BTN_SEQ, BTN_SEL};
    uint32_t rel, b = fm1_input_edges(&rel), tap = 0, hold = 0, k;
    for (k = 0; k < 4u; k++) {                  /* these four: a tap when let go, or held 600 ms */
        uint32_t m = 1u << HOLD[k];
        if (b & m) { armed |= m; fired &= ~m; t_down[HOLD[k]] = fm1_ms; }
        if ((armed & m) && !(fired & m) && (fm1_in.buttons & m) && fm1_ms - t_down[HOLD[k]] >= 600u) {
            fired |= m;
            hold |= m;
        }
        if (rel & m) {
            if ((armed & m) && !(fired & m)) tap |= m;
            armed &= ~m;
        }
        b &= ~m;
    }
    if (page == PG_HELP) {                      /* any button: the next page, then out */
        if (b || tap) {
            if ((tap & (1u << BTN_HOME)) || ++help_page >= 3u) go_page(PG_HOME);
            else rd_page = 1;
        }
        return;
    }
    if (hold & (1u << BTN_HOME)) { help_page = 0; go_page(PG_HELP); return; }
    if (tap & (1u << BTN_HOME)) {
        if (page != PG_HOME) go_page(PG_HOME);
        else if (edit_on || rec_on) { edit_on = rec_on = 0; say("REC AV · SPILL FRITT"); rd_steps = 0xFFFF; }
        else lore();
    }
    if (b & (1u << BTN_PLAY)) {
        if (playing) stop(1);
        else play();
    }
    if (b & (1u << BTN_REC)) {
        rec_on = !rec_on;
        if (rec_on) edit_on = 0;
        if (page != PG_HOME) go_page(PG_HOME);
        if (song_playing) stop(0);
        if (rec_on) { SAY_BEGIN(); sb_s("REC · NESTE STEG "); sb_step(cur_step); SAY_END(); }
        else say("REC AV · SPILL FRITT");
        rd_steps = 0xFFFF;
    }
    if (b & (1u << BTN_EDIT)) {
        edit_on = !edit_on;
        if (edit_on) rec_on = 0;
        if (page != PG_HOME) go_page(PG_HOME);
        if (song_playing) stop(0);
        if (edit_on) { SAY_BEGIN(); sb_s("REDIGER "); sb_step(cur_step); SAY_END(); }
        else say("REDIGER AV");
        rd_steps = 0xFFFF;
    }
    if (b & (1u << BTN_FX))
        set_thall(!thall);
    if (b & (1u << BTN_ENV)) {
        undo_pop();
        rd_steps = 0xFFFF;
        touch();
    }
    if (b & (1u << BTN_LFO)) {
        if (page != PG_HOME) go_page(PG_HOME);
        randomize();
    }
    if (tap & (1u << BTN_SEQ)) {
        if (page == PG_TROM) go_page(PG_HOME);
        else {
            go_page(PG_TROM);
            if (!drums_on) { drums_on = 1; hq.drums_on = 1; touch(); }
            say("TROMSTER · SYNC");
        }
    }
    if (hold & (1u << BTN_SEQ)) {
        drums_on = !drums_on;
        hq.drums_on = drums_on;
        say(drums_on ? "TROMSTER PÅ" : "TROMSTER AV");
        rd_page = 1;
        touch();
    }
    if (tap & (1u << BTN_GLO)) {                /* SONG on / off: as the page, it stops what plays */
        if (playing) stop(0);
        song_mode = !song_mode;
        if (song_mode) say("SONG PÅ · PLAY = SONG");
        else { SAY_BEGIN(); sb_s("SONG AV · SEKVENS "); sb_c((char)('A' + active)); SAY_END(); }
        rd_page = 1;
        touch();
    }
    if (hold & (1u << BTN_GLO)) {
        if (page == PG_SONG) go_page(PG_HOME);
        else { song_cur = hq.song_len < 64u ? hq.song_len : 63u; go_page(PG_SONG); say("SONG-REKKEFØLGE"); }
    }
    if (b & (1u << BTN_SAVE)) {
        if (page == PG_HOME && edit_on) {       /* the step copied to the next */
            uint32_t s = hq.pat[active][cur_step];
            if (s & ST_ON) {
                undo_push();
                cur_step = (cur_step + 1u) & 15u;
                hq.pat[active][cur_step] = (uint16_t)s;
                SAY_BEGIN(); sb_s("KOPIERT TIL STEG "); sb_u(cur_step + 1u); SAY_END();
                preview(cur_step);
                rd_steps = 0xFFFF;
                touch();
            }
        } else {
            save_now = 1;
        }
    }
    if (b & (1u << BTN_ARP)) {
        if (page == PG_HOME && edit_on) {       /* off, +7, +12, off */
            uint32_t s = hq.pat[active][cur_step];
            if (s & ST_ON) {
                undo_push();
                hq.pat[active][cur_step] = (uint16_t)((s & ~(3u << 8)) | ((ST_ARP(s) + 1u) % 3u) << 8);
                s = hq.pat[active][cur_step];
                SAY_BEGIN(); sb_step(cur_step); sb_s(ST_ARP(s) == 0u ? " · ARP AV" : ST_ARP(s) == 1u ? " · ARP +7" : " · ARP +12"); SAY_END();
                preview(cur_step);
                rd_steps |= 1u << cur_step;
                touch();
            }
        } else {
            say("ARP: I REDIGER (EDIT)");
        }
    }
    if (b & (1u << BTN_OCT_DOWN | 1u << BTN_OCT_UP)) {
        int32_t d = b & (1u << BTN_OCT_UP) ? 1 : -1;
        if (page == PG_HOME && edit_on) {       /* the step's octave, -3..+1 */
            uint32_t s = hq.pat[active][cur_step];
            int32_t o = ST_OCT(s) + d;
            if ((s & ST_ON) && o >= -3 && o <= 1) {
                undo_push();
                hq.pat[active][cur_step] = (uint16_t)((s & ~(7u << 3)) | (uint32_t)(o + 3) << 3);
                step_say(cur_step);
                preview(cur_step);
                rd_steps |= 1u << cur_step;
                touch();
            }
        } else {                                /* the keys: down to two octaves lower, and up again */
            kb_oct += d;
            kb_oct = kb_oct < -2 ? -2 : kb_oct > 0 ? 0 : kb_oct;
            SAY_BEGIN(); sb_s("TANGENTER "); if (kb_oct) { sb_c('-'); sb_u((uint32_t)-kb_oct); } else sb_c('0'); sb_s(" OKT"); SAY_END();
            touch();
        }
    }
    if (tap & (1u << BTN_SEL)) {
        if (page == PG_SONG) {                  /* the letter before the cursor goes */
            if (hq.song_len > 1u && song_cur > 0u) {
                if (playing) stop(0);
                for (k = song_cur - 1u; k + 1u < hq.song_len; k++) hq.song[k] = hq.song[k + 1u];
                hq.song_len = hq.song_len - 1u;
                song_cur--;
                rd_page = 1;
                touch();
            }
        } else if (page == PG_HOME && rec_on) {  /* a rest, and on */
            uint32_t step = cur_step;
            undo_push();
            hq.pat[active][step] = 0;
            cur_step = (cur_step + 1u) & 15u;
            SAY_BEGIN(); sb_step(step); sb_s(" · REST"); SAY_END();
            rd_steps |= 1u << step | 1u << cur_step;
            touch();
        } else if (page == PG_HOME && edit_on) {
            if (hq.pat[active][cur_step] & ST_ON) {
                undo_push();
                hq.pat[active][cur_step] = 0;
                SAY_BEGIN(); sb_s("STEG "); sb_u(cur_step + 1u); sb_s(" SLETTET"); SAY_END();
                rd_steps |= 1u << cur_step;
                touch();
            }
        } else if (page == PG_HOME) {
            say("SEL: PAUSE I REC");
        }
    }
    if (hold & (1u << BTN_SEL)) {
        if (page == PG_TROM) {                  /* the drum's row cleared */
            hq.drum[active][trom_row] = 0;
            SAY_BEGIN(); sb_s(DRUM_NAME[trom_row]); sb_s(" SLETTET"); SAY_END();
            rd_page = 1;
        } else if (page == PG_HOME) {           /* the pattern cleared (ENV brings it back) */
            if (playing) stop(0);
            undo_push();
            for (k = 0; k < 16u; k++) hq.pat[active][k] = 0;
            cur_step = 0;
            SAY_BEGIN(); sb_s("SEKVENS "); sb_c((char)('A' + active)); sb_s(" SLETTET"); SAY_END();
            rd_steps = 0xFFFF;
        }
        touch();
    }
}

static void encoders(void)
{
    static const uint32_t KN[4] = {ENC_KNOB1, ENC_KNOB2, ENC_KNOB3, ENC_KNOB4};
    int32_t e;
    uint32_t k;
    if ((e = fm1_enc_take(ENC_ALGORITHM)) != 0 && page != PG_HELP)
        tempo(e);
    if ((e = fm1_enc_take(ENC_PRESETS)) != 0 && page != PG_HELP) {
        if (page == PG_SONG) {                  /* the letter under the cursor */
            if (song_cur < hq.song_len) {
                if (playing) stop(0);
                hq.song[song_cur] = (uint8_t)((hq.song[song_cur] + (e > 0 ? 1u : 3u)) & 3u);
                rd_page = 1;
                touch();
            }
        } else if (song_playing) {
            say("SONG SPILLER · STOPP");
        } else {
            set_active((active + (uint32_t)(e > 0 ? 1 : 3)) & 3u);
            SAY_BEGIN(); sb_s("SEKVENS "); sb_c((char)('A' + active)); sb_s(playing && play_pat != active ? " · NESTE" : " VALGT"); SAY_END();
        }
    }
    if ((e = fm1_enc_take(ENC_SELECT)) != 0) {
        if (page == PG_HELP) {
            help_page = (help_page + (e > 0 ? 1u : 2u)) % 3u;
            rd_page = 1;
        } else if (page == PG_TROM) {
            trom_row = (trom_row + (e > 0 ? 1u : 3u)) & 3u;
            if (!playing) drum_try(trom_row, 0);
            rd_page = 1;
        } else if (page == PG_SONG) {
            int32_t c = (int32_t)song_cur + e, mx = (int32_t)(hq.song_len < 64u ? hq.song_len : 63u);
            song_cur = (uint32_t)(c < 0 ? 0 : c > mx ? mx : c);
            rd_page = 1;
        } else {                                /* the step: where REC writes, what the editor holds */
            uint32_t old = cur_step;
            if (song_playing) stop(0);
            cur_step = (uint32_t)((int32_t)cur_step + e) & 15u;
            if (!playing) preview(cur_step);
            step_say(cur_step);
            rd_steps |= 1u << old | 1u << cur_step;
            touch();
        }
    }
    for (k = 0; k < 4u; k++) {
        if ((e = fm1_enc_take(KN[k])) == 0 || page == PG_HELP)
            continue;
        if (page == PG_TROM) {                  /* each drum's voice, 1..3 */
            int32_t v = (int32_t)hq.dvoice[active][k] + (e > 0 ? 1 : -1);
            hq.dvoice[active][k] = (uint8_t)(v < 0 ? 0 : v > 2 ? 2 : v);
            drum_try(k, 1);
            SAY_BEGIN(); sb_s(DRUM_NAME[k]); sb_c(' '); sb_u(hq.dvoice[active][k] + 1u); SAY_END();
            rd_page = 1;
            touch();
        } else if (page == PG_HOME && edit_on) {
            step_fx(k, e);
        } else if (k == 0u) {
            int32_t v = (int32_t)swing + e * 2;
            swing = (uint32_t)(v < 0 ? 0 : v > 60 ? 60 : v);
            hq.swing = swing;
            SAY_BEGIN(); sb_s("SWING "); sb_u(swing); sb_c('%'); SAY_END();
            touch();
        } else if (k == 1u || k == 2u) {
            uint32_t *l = k == 1u ? &lvl_ham : &lvl_drum;
            int32_t v = (int32_t)*l + e;
            *l = (uint32_t)(v < 0 ? 0 : v > 32 ? 32 : v);
            hq.lvl_ham = lvl_ham * 16u;
            hq.lvl_drum = lvl_drum * 16u;
            SAY_BEGIN(); sb_s(k == 1u ? "HAMSTER " : "TROMSTER "); sb_u(*l * 100u / 16u); sb_c('%'); SAY_END();
            touch();
        } else {
            int32_t v = (int32_t)midi_ch + (e > 0 ? 1 : -1);
            midi_ch = (uint32_t)(v < 0 ? 0 : v > 16 ? 16 : v);
            SAY_BEGIN(); sb_s("MIDI-KANAL "); if (midi_ch) sb_u(midi_ch); else sb_s("ALLE"); SAY_END();
            touch();
        }
    }
}

static void keys(void)
{
    static uint32_t prev;
    uint32_t now = fm1_in.notes, down = fm1_input_note_edges(), k;
#ifdef DINGHY_HOST
    down |= now & ~prev;                        /* (the host's keys have no edges of their own) */
#endif
    prev = now;
    if (!down || page == PG_HELP)
        return;
    for (k = 0; k < 27u; k++) {
        if (!(down >> k & 1u))
            continue;
        if (k == 8u || k == 10u || k == 13u || k == 15u) {   /* the drums by hand */
            uint32_t d = k == 8u ? DR_KICK : k == 10u ? DR_SNARE : k == 13u ? DR_HAT : DR_CLAP;
            drum_try(d, 1);
            continue;
        }
        if (KEY_HAM[k] < 0)
            continue;
        if (page == PG_TROM) {
            if (k < 7u) {                       /* F3 G3 A3 B3: the drum */
                trom_row = k / 2u;
                drum_try(trom_row, 0);
            } else if (k <= 19u) {              /* C4..C5: its steps */
                uint32_t i = (uint32_t)KEY_HAM[k];
                hq.drum[active][trom_row] = (uint8_t)(hq.drum[active][trom_row] ^ (1u << i));
                if (hq.drum[active][trom_row] >> i & 1u)
                    drum_try(trom_row, 0);
                touch();
            }
            rd_page = 1;
        } else if (page == PG_SONG) {
            if (k >= 7u && k <= 12u && hq.song_len < 64u && KEY_HAM[k] < 4) {   /* C4 D4 E4 F4: A B C D, at the cursor */
                uint32_t i;
                if (playing) stop(0);
                for (i = hq.song_len; i > song_cur; i--) hq.song[i] = hq.song[i - 1u];
                hq.song[song_cur] = (uint8_t)KEY_HAM[k];
                hq.song_len = hq.song_len + 1u;
                if (song_cur < 63u) song_cur++;
                rd_page = 1;
                touch();
            }
        } else {
            press((uint32_t)KEY_HAM[k], KEY_OCT[k] + kb_oct, 0);
        }
    }
}

/* what the engine says: the step that plays, the hamster that sings, the drums */
static void events(void)
{
    static const uint8_t DRUM_NOTE[4] = {36, 38, 42, 39};
    uint32_t e, k;
    while ((e = heng_ev()) != 0) {
        uint32_t a = e & 0x0FFFFFFFu;
        switch (e >> 28) {
        case HE_STEP: {
            uint32_t old = play_step;
            if (!playing) break;                /* (it was stopped meanwhile) */
            play_step = a & 15u;
            play_pat = a >> 4 & 3u;
            song_pos = a >> 8 & 63u;
            rd_steps |= 1u << old | 1u << play_step;
            if (song_playing && play_step == 0u) { rd_steps = 0xFFFF; rd_bot = 1; }
            logo_dance = play_step & 1u ? 2u : 1u;
            t_logo = fm1_ms;
            rd_logo = 1;
            dr_step_t = fm1_ms;
            dr_hit = 0;
            if (drums_on)
                for (k = 0; k < 4u; k++)
                    dr_hit |= hq.drum[play_pat][k] >> (play_step & 7u) & 1u;
            if (dr_hit) dr_alt ^= 1u;
            if (page == PG_TROM || (page == PG_SONG && play_step == 0u)) rd_page = 1;
            break;
        }
        case HE_NOTE: {
            uint32_t key = a & 7u, midi = a >> 4 & 127u, vel = a >> 12 & 127u;
            t_ham[key] = fm1_ms ? fm1_ms : 1u;
            ham_shown[key] = ~0u;
            sel_key = key;
            midi_note_out(0x90u | (midi_ch ? midi_ch - 1u : 0u), midi, vel);
            break;
        }
        case HE_DRUM:
            for (k = 0; k < 4u; k++)
                if (a >> k & 1u)
                    midi_note_out(0x99u, DRUM_NOTE[k], 100);
            if (!playing) {                     /* by hand: the drummer plays it */
                dr_prev_t = fm1_ms ? fm1_ms : 1u;
                dr_prev_kind = a & 8u ? 3u : a & 2u ? 1u : a & 4u ? 2u : 0u;
            }
            break;
        case HE_BAR:
            play_pat = a & 3u;
            rd_bot = 1;
            break;
        }
    }
}

static void drummer(void)                       /* the Tromster's hamster: the page's frames */
{
    static const uint8_t CYC[2][3] = {{2, 3, 1}, {1, 3, 2}};
    static const uint8_t PREV[4][5] = {{1, 2, 3, 0, 0}, {1, 3, 2, 0, 0}, {2, 3, 1, 0, 0}, {3, 1, 2, 3, 0}};
    uint32_t f = 0;
    if (playing) {
        if (dr_hit) {
            uint32_t sm = 30000u / (bpm * (thall ? 2u : 1u)), d = sm * 45u / 100u;
            d = d < 85u ? 85u : d > 155u ? 155u : d;
            f = CYC[dr_alt][(fm1_ms - dr_step_t) / d % 3u];
        }
    } else if (dr_prev_t) {
        uint32_t i = (fm1_ms - dr_prev_t) / 88u;
        if (i >= 5u || !PREV[dr_prev_kind][i]) dr_prev_t = 0;
        else f = PREV[dr_prev_kind][i];
    }
    if (f != dr_frame) {
        dr_frame = f;
        if (page == PG_TROM) rd_page = 1;
    }
}

#ifdef DINGHY_WEB
#define APP_STATE static
#else
#define APP_STATE
#endif
static void app_main(void)
{
    APP_STATE uint32_t t_draw = 0;
#ifdef DINGHY_WEB
    static int started;
    if (!started) {
        started = 1;
#endif
    heng_init();
    store_load();
    push_all();
    play_pat = active;
#ifndef DINGHY_HOST
    rnd_s ^= fm1_ticks();                       /* (the sign: not the same words at every power-on) */
#endif
    say("KLAR · SPILL FRITT");
    lore();
#ifdef DINGHY_WEB
    }
    do {
#else
    for (;;) {
#endif
#ifndef DINGHY_HOST
        if (usb.ota_req)
            hq.off = 1;                         /* the updater gets the whole chip */
#endif
        platform_poll();
        events();
        midi_in();
        midi_offs();
        buttons();
        encoders();
        keys();
        drummer();
        rnd_s += fm1_in.notes + 1u;             /* (the keys' timing stirs the dice) */

        if (logo_dance && fm1_ms - t_logo > 110u) {   /* the notes come to rest */
            logo_dance = 0;
            rd_logo = 1;
        }
        if (sign_on && (int32_t)(fm1_ms - t_sign) >= 0) {
            sign_on = 0;
            rd_bot = 1;
        }
        if (page == PG_HOME && edit_on && t_status && fm1_ms - t_status > 1800u) {   /* the editor: the step it holds */
            step_say(cur_step);
            t_status = 0;
        }
        if (fm1_ms - t_draw >= 16u) {
            t_draw = fm1_ms;
            draw();
        }
        leds();

        /* to flash: 2 s after the last change, when nothing sounds (an erase stops the sound); or SAVE, now */
        if (save_now || (dirty && fm1_ms - t_change > 2000u && !heng_busy)) {
            store_save();
            if (save_now) say("LAGRET");
            save_now = 0;
        }
#ifdef DINGHY_WEB
    } while (0);
#else
    }
#endif
}

#ifdef DINGHY_WEB
/* the page: playing, rec, edit, drums, THALL, song mode, the page shown: bits 0, 1, 2, 3, 4, 5, 6-7 */
WEB_EXPORT(web_state) uint32_t web_state(void)
{
    return playing | rec_on << 1 | edit_on << 2 | drums_on << 3 | thall << 4 | song_mode << 5 | page << 6;
}
#endif
