/* SPDX-License-Identifier: GPL-3.0-only */
/* The clock's sound engine alone (firmware/src/clk_engine.h), on the host: one strike, one tick, one tock or a
 * train, as a WAV, to hold against the reference's measurements (tests/clk/parity.py). The engine is the firmware's
 * own, unchanged; only the crystal is a stub (no governor: a fixed number of carriers).
 *
 *   clk_render strike OUT.wav [NG]      one blow of the hammer at 50 ms, 5.3 s
 *   clk_render tick|tock OUT.wav [N]    N (1) ticks (left) or tocks (right), the first at 10 ms, 0.2 s apart
 *   clk_render train N OUT.wav [NG]     N strikes 1.192 s apart, as on the hour
 *   clk_render bench [NG]               the worst case for the instruction count (callgrind): ticks and a strike
 * the cuckoo clock's:
 *   clk_render ck_strike OUT.wav [NG]   one blow on its wire gong at 50 ms, 3 s
 *   clk_render ck_call N OUT.wav [NG]   N calls (the gong, the high pipe, the low), CK_CALL_FRAMES apart
 *   clk_render ck_tick|ck_warning|ck_door|ck_shut OUT.wav [N]   N of its ticks (left), or of its train's warning
 *                                     clicks, its door opening, its door shutting (the middle), 0.2 s apart
 *   clk_render ck_run OUT.wav            its train running, its drone, from 0.1 to 1.1 s */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t clk_now(void) { return 0; }
#include "clk_engine.h"

static int16_t *wav;
static uint32_t wav_n;

static void run(uint32_t frames, const uint32_t *at, const uint32_t *type, const uint32_t *arg, uint32_t nat)
{
    uint32_t f, i, k = 0;
    int32_t buf[2 * CLK_BLOCK];
    wav = realloc(wav, (size_t)(wav_n + frames + CLK_BLOCK) * 4u);
    for (f = 0; f < frames; f += CLK_BLOCK) {
        ev_t ev[12];
        uint32_t nev = 0;
        while (k < nat && at[k] < f + CLK_BLOCK) {
            ev[nev].frame = at[k] - f;
            ev[nev].type = type[k];
            ev[nev].arg = arg[k];
            nev++;
            k++;
        }
        memset(buf, 0, sizeof buf);
        eng_render(buf, CLK_BLOCK, ev, nev);
        for (i = 0; i < 2u * CLK_BLOCK; i++) {
            int32_t v = buf[i];
            wav[2u * wav_n + i] = (int16_t)(v > 32767 ? 32767 : v < -32767 ? -32767 : v);
        }
        wav_n += CLK_BLOCK;
    }
}

static void write_wav(const char *name)
{
    FILE *fp = fopen(name, "wb");
    uint32_t bytes = wav_n * 4u, v[] = {16, 0x00020001u, 44100u, 44100u * 4u, 0x00100004u};
    if (!fp) { perror(name); exit(1); }
    fwrite("RIFF", 1, 4, fp); bytes += 36; fwrite(&bytes, 4, 1, fp); bytes -= 36;
    fwrite("WAVEfmt ", 1, 8, fp); fwrite(v, 4, 5, fp);
    fwrite("data", 1, 4, fp); fwrite(&bytes, 4, 1, fp);
    fwrite(wav, 4, wav_n, fp);
    fclose(fp);
}

int main(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "";
    eng_init();
    eng_fixed_ng = NG;
    if (!strcmp(mode, "strike") && argc > 2) {
        uint32_t at[] = {2205}, ty[] = {EV_HIT}, ar[] = {HAMMER[0]};
        if (argc > 3) eng_fixed_ng = (uint32_t)atoi(argv[3]);
        run(44100u * 53u / 10u, at, ty, ar, 1);
        write_wav(argv[2]);
    } else if ((!strcmp(mode, "tick") || !strcmp(mode, "tock")) && argc > 2) {
        uint32_t n = argc > 3 ? (uint32_t)atoi(argv[3]) : 1u, at[64], ty[64], ar[64], i;
        for (i = 0; i < n && i < 64u; i++) {
            at[i] = 441u + i * 8820u;
            ty[i] = mode[1] == 'i' ? EV_TICK : EV_TOCK;
            ar[i] = mode[1] == 'i' ? SND_A_TICK : SND_A_TOCK;
        }
        run(441u + i * 8820u, at, ty, ar, i);
        write_wav(argv[2]);
    } else if (!strcmp(mode, "train") && argc > 3) {
        uint32_t n = (uint32_t)atoi(argv[2]), at[24], ty[24], ar[24], i;
        if (argc > 4) eng_fixed_ng = (uint32_t)atoi(argv[4]);
        for (i = 0; i < n && i < 24u; i++) {
            at[i] = 2205u + i * TRAIN_FRAMES;
            ty[i] = EV_HIT;
            ar[i] = HAMMER[i < 2u ? i : 2u];
        }
        run(2205u + n * TRAIN_FRAMES + 44100u * 4u, at, ty, ar, i);
        write_wav(argv[3]);
    } else if (!strcmp(mode, "ck_strike") && argc > 2) {
        uint32_t at[] = {2205}, ty[] = {EV_HIT}, ar[] = {HAMMER[0]};
        eng_want = 1;
        eng_load(1);
        eng_fixed_ng = argc > 3 ? (uint32_t)atoi(argv[3]) : NGB;
        run(44100u * 3u, at, ty, ar, 1);
        write_wav(argv[2]);
    } else if (!strcmp(mode, "ck_call") && argc > 3) {
        uint32_t n = (uint32_t)atoi(argv[2]), at[36], ty[36], ar[36], i, k = 0;
        eng_want = 1;
        eng_load(1);
        eng_fixed_ng = argc > 4 ? (uint32_t)atoi(argv[4]) : NGB;
        at[k] = 0; ty[k] = EV_RUN; ar[k] = 1; k++;    /* the train runs under the calls */
        for (i = 0; i < n && i < 11u; i++) {
            uint32_t h = 2205u + i * CK_CALL_FRAMES;
            at[k] = h; ty[k] = EV_HIT; ar[k] = HAMMER[2]; k++;
            at[k] = h + CK_HIT_TO_HIGH; ty[k] = EV_PIPE; ar[k] = 0; k++;
            at[k] = h + CK_HIT_TO_HIGH + CK_HIGH_TO_LOW; ty[k] = EV_PIPE; ar[k] = 1; k++;
        }
        run(2205u + n * CK_CALL_FRAMES + 44100u * 2u, at, ty, ar, k);
        write_wav(argv[3]);
    } else if (!strcmp(mode, "ck_run") && argc > 2) {
        uint32_t at[] = {4410, 48510}, ty[] = {EV_RUN, EV_RUN}, ar[] = {1, 0};
        eng_want = 1;
        eng_load(1);
        run(44100u * 3u / 2u, at, ty, ar, 2);
        write_wav(argv[2]);
    } else if ((!strcmp(mode, "ck_tick") || !strcmp(mode, "ck_warning") || !strcmp(mode, "ck_door") ||
                !strcmp(mode, "ck_shut")) && argc > 2) {
        uint32_t n = argc > 3 ? (uint32_t)atoi(argv[3]) : 1u, at[128], ty[128], ar[128], i, k = 0;
        uint32_t snd = mode[3] == 't' ? SND_B_TICK : mode[3] == 'w' ? SND_B_WARN : mode[3] == 'd' ? SND_B_DOOR : SND_B_SHUT;
        eng_want = 1;
        eng_load(1);
        for (i = 0; i < n && i < 60u; i++) {
            at[k] = 441u + i * 8820u;
            ty[k] = snd == SND_B_TICK ? EV_TICK : EV_CLICK;
            ar[k] = snd == SND_B_TICK ? snd : snd | 32767u << 8;
            k++;
        }
        run(441u + i * 8820u, at, ty, ar, k);
        write_wav(argv[2]);
    } else if (!strcmp(mode, "bench")) {
        uint32_t at[] = {100, 2205, 22050, 44100}, ty[] = {EV_TICK, EV_HIT, EV_TOCK, EV_TICK}, ar[] = {SND_A_TICK, HAMMER[0], SND_A_TOCK, SND_A_TICK};
        if (argc > 2) eng_fixed_ng = (uint32_t)atoi(argv[2]);
        run(44100u * 2u, at, ty, ar, 4);
        printf("bench: %u frames at %u carriers\n", wav_n, eng_fixed_ng);
    } else {
        fprintf(stderr, "usage: clk_render strike|tick|tock|ck_strike|ck_tick|ck_pre|ck_post OUT.wav [NG|N] | train|ck_call N OUT.wav [NG] | bench [NG]\n");
        return 2;
    }
    return 0;
}
