/* SPDX-License-Identifier: GPL-3.0-only */
/* Hamster Piano's engine alone (firmware/src/ham_engine.h, unchanged) on the host: a case of tests/ham/cases.json
 * played by its own sequencer into a WAV, to hold against what the original page renders (tests/ham/parity.py).
 *
 *   ham_render CASE.txt OUT.wav     CASE.txt: a line a setting (tests/ham/parity.py writes it from cases.json)
 *     bpm N | thall 0/1 | drums 0/1 | swing N | rounds N | song ABCD... | voice 0/1 (1: the hamster voice)
 *     step P I KEY OCT GLIDE ARP ACCENT RATCHET     pattern P (0..3), step I: ARP 0, 7 or 12
 *     drum P D BITS | dvoice P D V                  drum D (0 kick .. 3 clap): its 8 steps, its voice
 *   ham_render bench                the heaviest minute for the instruction count (DINGHY_PERF) */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ham_engine.h"

int main(int argc, char **argv)
{
    char line[256], what[16], song[80] = "";
    uint32_t rounds = 1, frames, f, i, nsong = 0, bench = argc > 1 && !strcmp(argv[1], "bench");
    int16_t *wav;
    FILE *fp;
    if (argc < 3 && !bench) { fprintf(stderr, "usage: ham_render CASE.txt OUT.wav | bench\n"); return 2; }
    heng_init();
    if (bench) {                                /* every step a note with four ratchets, the drums, THALL or not */
        uint32_t p;
        for (p = 0; p < 16u; p++) hq.pat[0][p] = (uint16_t)(ST_MAKE(p & 7u, 0) | 3u << 10 | (p & 1u) << 8);
        for (p = 0; p < 4u; p++) hq.drum[0][p] = 0xFF;
        hq.drums_on = 1; hq.bpm = 220; hq.thall = argc > 2;
        rounds = 8;
    } else {
        if (!(fp = fopen(argv[1], "r"))) { perror(argv[1]); return 1; }
        while (fgets(line, sizeof line, fp)) {
            unsigned a[8] = {0};
            int oct = 0;
            if (sscanf(line, "%15s", what) != 1) continue;
            if (!strcmp(what, "bpm")) { sscanf(line, "%*s %u", &a[0]); hq.bpm = a[0]; }
            else if (!strcmp(what, "thall")) { sscanf(line, "%*s %u", &a[0]); hq.thall = a[0]; }
            else if (!strcmp(what, "drums")) { sscanf(line, "%*s %u", &a[0]); hq.drums_on = a[0]; }
            else if (!strcmp(what, "swing")) { sscanf(line, "%*s %u", &a[0]); hq.swing = a[0]; }
            else if (!strcmp(what, "voice")) { sscanf(line, "%*s %u", &a[0]); hq.hvoice = a[0]; }
            else if (!strcmp(what, "rounds")) { sscanf(line, "%*s %u", &rounds); }
            else if (!strcmp(what, "song")) { sscanf(line, "%*s %79s", song); }
            else if (!strcmp(what, "step")) {
                sscanf(line, "%*s %u %u %u %d %u %u %u %u", &a[0], &a[1], &a[2], &oct, &a[3], &a[4], &a[5], &a[6]);
                hq.pat[a[0] & 3u][a[1] & 15u] = (uint16_t)(ST_MAKE(a[2] & 7u, oct) | (a[3] & 1u) << 6 | (a[5] & 1u) << 7 |
                                                          (a[4] == 7u ? 1u : a[4] == 12u ? 2u : 0u) << 8 | ((a[6] ? a[6] : 1u) - 1u) << 10);
            }
            else if (!strcmp(what, "drum")) { sscanf(line, "%*s %u %u %i", &a[0], &a[1], (int *)&a[2]); hq.drum[a[0] & 3u][a[1] & 3u] = (uint8_t)a[2]; }
            else if (!strcmp(what, "dvoice")) { sscanf(line, "%*s %u %u %u", &a[0], &a[1], &a[2]); hq.dvoice[a[0] & 3u][a[1] & 3u] = (uint8_t)a[2]; }
        }
        fclose(fp);
    }
    for (i = 0; song[i] && nsong < 64u; i++)
        if (song[i] >= 'A' && song[i] <= 'D') hq.song[nsong++] = (uint8_t)(song[i] - 'A');
    hq.song_len = nsong ? nsong : 1u;
    hq.want_pat = 0;
    /* as the page's export: the steps, then 0.7 s */
    frames = (uint32_t)((uint64_t)rounds * (nsong ? nsong : 1u) * 16u * STEP_T / (hq.bpm * (hq.thall ? 2u : 1u))) + 30870u;
    frames = (frames + 255u) / 256u * 256u;
    wav = calloc(frames, 4);
    heng_cmd(HCMD(HC_PLAY, nsong ? 1u : 0u));
    for (f = 0; f < frames; f += 256u) {
        int32_t buf[512];
        if (!bench && f + 30870u + 2048u >= frames) {   /* the rounds are over: nothing more (the page's export ends) */
            memset((void *)hq.pat, 0, sizeof hq.pat);
            hq.drums_on = 0;
        }
        memset(buf, 0, sizeof buf);
        heng_render(buf, 256u);
        while (heng_ev()) {}
        for (i = 0; i < 512u; i++)
            wav[2u * f + i] = (int16_t)(buf[i] > 32767 ? 32767 : buf[i] < -32767 ? -32767 : buf[i]);
    }
    if (bench) { printf("bench: %u frames\n", frames); return 0; }
    if (!(fp = fopen(argv[2], "wb"))) { perror(argv[2]); return 1; }
    {
        uint32_t bytes = frames * 4u, v[] = {16, 0x00020001u, 44100u, 44100u * 4u, 0x00100004u};
        fwrite("RIFF", 1, 4, fp); bytes += 36; fwrite(&bytes, 4, 1, fp); bytes -= 36;
        fwrite("WAVEfmt ", 1, 8, fp); fwrite(v, 4, 5, fp);
        fwrite("data", 1, 4, fp); fwrite(&bytes, 4, 1, fp);
        fwrite(wav, 4, frames, fp);
    }
    fclose(fp);
    return 0;
}
