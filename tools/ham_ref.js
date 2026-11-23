// SPDX-License-Identifier: GPL-3.0-only
// Hamster Synth's reference sound: the original web page (Hamster Piano) renders each case of tests/ham/cases.json itself (its own
// WAV export, an OfflineAudioContext), in Chromium (Playwright). What is kept of the WAVs is their band energies
// (tests/ham/parity.py ref DIR -> tests/ref/ham_features.json); the page itself is not in this repository.
//
//   node tools/ham_ref.js PAGE.html OUTDIR
//
// Two things are set for it: the sample rate (44.1 kHz, the FM-1's) and a noise that is the same every run. And one
// is put right: played live, the page starts every note on one of Web Audio's render quanta (128 frames: it starts
// them "now"). Its export starts them where the steps fall, mostly inside a quantum, and Chromium's oscillators then
// run their first frames at the pitch their parameters had before the note (440 Hz). That moves the three
// oscillators of a THALL note against each other, by a different amount every step, and its distortion with them.
// The reference is the instrument as it is played: each note on a quantum.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const [page_html, out] = process.argv.slice(2);
if (!page_html || !out) { console.error('usage: node tools/ham_ref.js PAGE.html OUTDIR'); process.exit(2); }
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'tests', 'ham', 'cases.json'), 'utf8'));
const Q = 'when=Math.round(when*ctx.sampleRate/128)*128/ctx.sampleRate;';
let html = fs.readFileSync(page_html, 'utf8');
for (const head of ['function scheduleHamsterVoice(ctx,dest,noiseBuffer,key,velocity=1,octave=0,when=0,fx=null){',
                    'function scheduleDrumVoice(ctx,dest,noiseBuffer,id,when,velocity=1,voice=0){']) {
  if (!html.includes(head)) { console.error('the page has no ' + head); process.exit(1); }
  html = html.replace(head, head + Q);
}
html = html.replace('function scheduleThallGateChoke(gate,when){', 'function scheduleThallGateChoke(gate,when){when=Math.round(when*44100/128)*128/44100;');
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch();
  for (const [name, c] of Object.entries(cases)) {
    const ctx = await b.newContext({ acceptDownloads: true });
    await ctx.addInitScript(([state]) => {
      const AC = window.AudioContext;
      window.AudioContext = function () { return new AC({ sampleRate: 44100 }); };
      let s = 12345;
      Math.random = () => (s = (s * 1103515245 + 12345) >>> 0, s / 4294967296);
      localStorage.setItem('hamsterPiano.v4_17', JSON.stringify(state));
    }, [{ patterns: c.patterns, activePattern: 'A', songString: 'A', songMode: false, tromsterDiscovered: !!c.drums,
          drumPatterns: c.dp, drumVoices: c.dv, thallMode: !!c.thall, currentStep: 0, bpm: c.bpm, volume: 1 }]);
    const p = await ctx.newPage();
    await p.route('**/page.html', r => r.fulfill({ contentType: 'text/html; charset=utf-8', body: html }));
    await p.goto('http://hamster.invalid/page.html');
    if (c.drums) await p.click('#tromsterLauncher');
    await p.click('#exportBtn');
    const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 60000 }), p.click('#exportRenderBtn')]);
    await dl.saveAs(path.join(out, name + '.wav'));
    console.log(name, fs.statSync(path.join(out, name + '.wav')).size);
    await ctx.close();
  }
  await b.close();
})();
