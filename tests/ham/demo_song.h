/* SPDX-License-Identifier: GPL-3.0-only */
/* Hamster Piano's sound demo (tools/ham_demo.sh): a song of four patterns to start from, instead of the page's A and
 * three empty ones. Only in the demo's host build (-DHAM_DEMO); the firmware starts as the page does.
 *   A  the page's own: C, C, F, G, the bass under the tune
 *   B  A minor, F, C, G: glides, an arpeggio, ratchets
 *   C  the tune on top: an accent, glides, a fifth's arpeggio, a ratchet of three
 *   D  the way home: F, G, C, ratchets and arpeggios, down to the low C */
#define DS(k, o, fx) ((uint16_t)(ST_MAKE((k), (o)) | (fx)))
#define GL (1u << 6)                            /* glide */
#define AC (1u << 7)                            /* accent */
#define A7 (1u << 8)                            /* arpeggio +7 */
#define A12 (2u << 8)                           /* arpeggio +12 */
#define R2 (1u << 10)                           /* ratchet x2, x3, x4 */
#define R3 (2u << 10)
#define R4 (3u << 10)
static void ham_demo(void)
{
    static const uint16_t P[3][16] = {
        {DS(5, -1, AC), DS(7, 0, 0), DS(2, 0, A7), DS(7, 0, GL), DS(3, -1, 0), DS(5, 0, 0), DS(7, 0, R2), DS(5, 0, 0),
         DS(0, -1, AC), DS(2, 0, 0), DS(4, 0, AC), DS(2, 0, GL), DS(4, -1, 0), DS(6, 0, 0), DS(1, 1, A12), DS(6, 0, R3)},
        {DS(0, -1, AC), DS(2, 0, 0), DS(4, 0, 0), DS(5, 0, 0), DS(4, 0, GL), DS(2, 0, 0), DS(1, 0, 0), DS(0, 0, 0),
         DS(5, -1, AC), DS(7, 0, 0), DS(6, 0, 0), DS(5, 0, A7), DS(4, 0, GL), DS(2, 0, 0), DS(1, 0, R3), DS(0, 0, 0)},
        {DS(3, -1, AC), DS(5, 0, 0), DS(7, 0, A12), DS(5, 0, 0), DS(4, -1, AC), DS(6, 0, 0), DS(1, 1, 0), DS(6, 0, GL),
         DS(0, -1, AC | R2), DS(4, 0, 0), DS(7, 0, A12), DS(2, 0, 0), DS(4, 0, R4), 0, DS(7, 0, AC), DS(0, -2, AC)},
    };
    static const uint8_t DR[4][4] = {               /* kick, snare, hat, clap: 8 steps each, a bit a step */
        {0x11, 0x44, 0xFF, 0x00}, {0x11, 0x44, 0x55, 0x00}, {0x91, 0x44, 0xFF, 0x40}, {0x11, 0x44, 0xFF, 0x44}};
    /* the voices: C sniffs and squeaks, D pops its cheeks and crunches a seed (4: the hamster kit) */
    static const uint8_t DV[4][4] = {{0, 0, 0, 0}, {0, 1, 0, 0}, {1, 0, 3, 3}, {3, 3, 2, 1}};
    uint32_t p, i;
    for (p = 0; p < 3u; p++)
        for (i = 0; i < 16u; i++)
            hq.pat[p + 1u][i] = P[p][i];
    for (p = 0; p < 4u; p++)
        for (i = 0; i < 4u; i++) {
            hq.drum[p][i] = DR[p][i];
            hq.dvoice[p][i] = DV[p][i];
        }
    for (i = 0; i < 4u; i++)
        hq.song[i] = (uint8_t)i;
    hq.song_len = 4;
#ifdef HAM_DEMO_PAGE_VOICE
    hvoice = 0;                                 /* (the same demo in the page's voice, to hold against it) */
#endif
}
