/* SPDX-License-Identifier: GPL-3.0-only */
/* HamsterSynth's engine (firmware/src/ham_engine.h) on the host: what must hold when one plays over what plays.
 *   - THALL: a note by hand does not cut the sequence's note off, nor the sequence's the hand's (two lines)
 *   - all voices busy: two notes begun together both sound (a voice that has just begun is never taken)
 *   - a step asked to be skipped (it was played by hand just before it) plays no note, and only that one */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static unsigned young;
#define HENG_ON_STEAL(h) do { if ((h)->amp.i <= 1u || !(h)->amp.left) young++; } while (0)
#include "ham_engine.h"

static int fails;
static void check(const char *what, int ok) { printf("%s: %s\n", what, ok ? "ok" : "FAIL"); fails += !ok; }
static void run(uint32_t frames)
{
    int32_t buf[512];
    uint32_t f;
    for (f = 0; f < frames; f += 256u) {
        memset(buf, 0, sizeof buf);
        heng_render(buf, 256u);
    }
}
static uint32_t notes;
static void drain(void)
{
    uint32_t e;
    while ((e = heng_ev()) != 0)
        if (e >> 28 == HE_NOTE) notes++;
}

int main(void)
{
    uint32_t i, line0 = 0, line1 = 0;
    heng_init();
    hq.bpm = 120; hq.thall = 1;
    for (i = 0; i < 16u; i++) hq.pat[0][i] = ST_MAKE(0, -1);
    heng_cmd(HCMD(HC_PLAY, 0));
    run(256u * 20u);                            /* a step has begun: the sequence's note */
    heng_cmd(HCMD(HC_NOTE, 64u | 2u << 7));     /* E by hand */
    run(256u * 8u);
    for (i = 0; i < NTV; i++)
        if (tv[i].on && !tv[i].choked) {
            if (tv[i].line) line1++; else line0++;
        }
    check("THALL: the hand's note and the sequence's both sound", line0 == 1u && line1 == 1u);
    heng_cmd(HCMD(HC_STOP, 0));
    run(256u * 40u);

    heng_init();
    hq.thall = 0; hq.hvoice = 1;
    for (i = 0; i < NHV; i++)                   /* all voices busy */
        heng_cmd(HCMD(HC_NOTE, (60u + i % 12u) | (i % 8u) << 7));
    run(256u * 4u);
    young = 0;
    heng_cmd(HCMD(HC_NOTE, 72u | 7u << 7));     /* two at once */
    heng_cmd(HCMD(HC_NOTE, 48u | 0u << 7));
    run(256u * 2u);
    check("all voices busy: two notes begun together both sound (no voice taken in its attack)", young == 0u);

    heng_init();
    hq.thall = 0; hq.bpm = 120;
    for (i = 0; i < 16u; i++) hq.pat[0][i] = ST_MAKE(i & 7u, 0);
    hq.skip = heng_fired + 3u;                  /* the third step to fire: no note */
    drain();
    notes = 0;
    heng_cmd(HCMD(HC_PLAY, 0));
    for (i = 0; i < 16u * 11025u / 256u - 4u; i += 1u) { run(256u); drain(); }   /* (16 steps of 11025 frames, not the 17th) */
    check("a step asked to be skipped plays no note, the other fifteen do", notes == 15u);
    return fails ? 1 : 0;
}
