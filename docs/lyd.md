# Lyden: målt, tilpasset, regnet ut

Alt i FM1 Clock er syntetisert. Ingen sampler fra opptaket ligger i firmwaren. Denne siden forklarer hvordan
gongen og tikkene er laget, og hvordan de er målt mot opptaket.

## Opptaket

*Clock Strike Chime Sound 31x Day BEACON Pendulum Wall Item 1125* (Adelaide Clocks): 48 kHz, mono, 43 s, lavpass ved
ca. 15,5 kHz.

| Tid | Hva |
|---|---|
| 0–15,5 s | Tikking. Tikk og takk veksler med 0,578 og 0,511 s mellom (klokka går litt skjevt; FM1 Clock tikker jevnt hvert 0,5 s) |
| 15,65 s | Ett slag alene: kilden for gongens modell |
| 25,6–37,5 s | Elleve slag, 1,192 s mellom (slagtoget) |

`tools/analyze_ref.py OPPTAK.wav` måler det og skriver `tools/ref_model.json` og `tests/ref/features.json`.

## Gongen

**Modene.** Signalet etter slaget (0,06–5,2 s) heterodynes ned til 0 Hz i bånd på 70 Hz fra 150 Hz til 15 kHz,
desimeres til 400 Hz og analyseres med *matrix pencil*. Det gir dempede sinuser med frekvens, utklingning,
amplitude og fase. 742 moder blir med. Mange partialer består av to poler på nesten samme frekvens med ulik
utklingning, for eksempel 551,4 Hz med τ = 0,39 s og 2,1 s. Det er en tostegs utklingning, og begge beholdes. Til
slutt strekkes utklingningen per tredjedels-oktav litt (0,89–1,34) slik at båndenergien fra 0,1 til 5 s stemmer.

**FM.** Hver mode er en bærer i motoren. De 32 med mest energi (a²τ) har en modulator:
`a e^(−t/τ) (1 + B e^(−t/τI)) sin(2π f t + φ + I e^(−t/τI) sin(2π r f t))`. For hver av dem er forholdet r (0,1–π),
indeksen I (0–3), indeksfallet τI (4–60 ms) og løftet B søkt fram (koordinatsøk, tre runder), slik at de tre
første vinduene (0–20, 20–50, 50–100 ms) får opptakets båndenergi. Avviket der gikk fra 2,4 til 0,9 dB RMS.

**Slagtoget.** Hammeren slår 1,192 s fra treff til treff (± 0,6 %), med et utløserklikk 40 ms før. Styrken måles som
energien like etter et treff minus energien like før: 1,0, 0,85, og så 0,53 i snitt. Et nytt treff på en gong som
ringer, legges til med ukjent fase: |a + b| ≈ max + 3/8 min. Står gongen nesten stille, starter hver mode med fasen
fra opptaket, så selve slaget blir som i opptaket.

## Tikkene

Tikk og takk måles hver for seg, 14 av hver, høypass ved 400 Hz (det er brum i rommet under). Hver lyd blir
64 sinusoperatorer: de 28 sterkeste toppene i spekteret og 36 spredt fra 330 Hz til 14,5 kHz. Kassa banker også.
I hvert tredjedels-oktavbånd har operatorene annenhver kort og lang utklingning (et raskt fall og så en hale).
Utklingningene velges per bånd fra et rutenett (NNLS). Så tilpasses alle nivåene samtidig med hver operators egen
mal, siden et vindu på 6 ms lar energi lekke over i nabobåndene (multiplikativ NMF-oppdatering). Anslaget stiger
som 1 − e^(−t/τa), og τa = 4,0 ms for tikket og 5,5 ms for takket gir best treff. Takket har et etterklikk 115 ms
senere, ca. 9 dB svakere.

## Motoren

`firmware/src/clk_engine.h`, bare heltall:

- Sinustabell med 16384 punkter (Q15) i RAM, fasen er 32 bit (`>> 18`).
- Gongens bærere: fase, steg, nivå (Q31), utklingning per 16 frames (Q32). Modulatorene: fase, steg,
  indekskonvolutt. Indeksen virker som fase: `SINT[(p + SINT[mp >> 18] * I) >> 18]`.
- Tikkbankene: 2 × 64 operatorer, nivået trappes ned hver 4. frame, stigningen per frame per bank.
- Alt regnes i hver frame. Guvernøren måler tiden og velger antall bærere (de sterkeste først) for 78 % av
  blokka. Bærere som ikke regnes, klinger ut og går videre i fasen per blokk.

## Målt mot opptaket

`tests/clk/clk_render.c` kjører motoren alene på verten, og `tests/clk/parity.py` måler resultatet på samme måte som
opptaket (tredjedels-oktaver over tid, tikkene i opptaket maskert bort, bare bånd over støyen). Tallene står i
[README.md](../README.md#lyden). `tests/run_clock.sh` feiler hvis noe vindu glir over 2 dB (slaget) eller 1,6 dB
(tikkene).
