// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Joakim (joakimskurk)
// The clock for the browser (web/app/: the firmware compiled to WebAssembly, web/app/build.sh) in Node, as the page's
// worklet runs it: no imports; a tick every half second, on its frame; the screen drawn; ALGORITHM to the cuckoo
// clock and back; PLAY: it calls; the time over MIDI (CC 20, 21, 22) to 3:59:57: the wall clock strikes on the hour.
//
//   node tests/web/app_test.mjs build/web/fm1clock.wasm
import { readFileSync } from 'fs';

const mod = await WebAssembly.compile(readFileSync(process.argv[2] || 'build/web/fm1clock.wasm'));
let fail = 0;
const check = (ok, what) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`); if (!ok) fail = 1; };

const imports = WebAssembly.Module.imports(mod);
check(imports.length === 0, `no imports (${imports.map((i) => i.name).join(', ') || 'none'})`);
const { exports: x } = await WebAssembly.instantiate(mod, {});
x.web_init(206);

const env = [];                                  // the loudest sample of each 128 frames
let t = 0;
function run(sec) {
  const peaks = [];
  for (let i = 0; i < Math.round((sec * 44100) / 128); i++) {
    x.web_run(128);
    const o = new Int32Array(x.memory.buffer, x.web_out_ptr(), 256);
    let p = 0;
    for (let k = 0; k < 256; k++) p = Math.max(p, Math.abs(o[k]));
    env.push(p); peaks.push(p);
    t += 128 / 44100;
  }
  return peaks;
}
const lcd = () => new Uint16Array(x.memory.buffer, x.web_lcd(), 240 * 240).slice();
const differ = (a, b) => a.reduce((n, v, i) => n + (v !== b[i]), 0);

const t0 = performance.now();
const p0 = run(3);
const speed = 3000 / (performance.now() - t0);
check(speed > 2, `3 s of the clock (206 carriers) in ${(3000 / speed).toFixed(0)} ms: ${speed.toFixed(1)} x real time`);
const tick = Math.max(...p0), thr = tick * 0.3, loud = 2 * tick, ticks = [];
let last = -1;
p0.forEach((p, i) => { const s = (i * 128) / 44100; if (p > thr && s - last > 0.2) { ticks.push(s); last = s; } });
const apart = ticks.slice(1).map((s, i) => s - ticks[i]);
check(ticks.length >= 5 && apart.every((d) => Math.abs(d - 0.5) < 0.006),
  `a tick every half second: ${ticks.length} ticks, apart ${apart.map((d) => d.toFixed(3)).join(' ')}`);
check(x.web_ms() >= 2995 && x.web_ms() <= 3005, `the main loop ran a pass a millisecond: ${x.web_ms()} ms`);
const wall = lcd();
check(wall.filter((c) => c !== 0).length > 50000, 'the screen: the wall clock on its wall');
check(((x.web_leds_lo() >>> 14) | (x.web_leds_hi() << 18)) !== 0, "the keys' lights: one lit, under the pendulum");

x.web_enc(1, 1);                                 // ALGORITHM
run(1.5);
const cuckoo = lcd();
check((x.web_state() & 1) === 1 && differ(wall, cuckoo) > 20000, `ALGORITHM: the cuckoo clock (${differ(wall, cuckoo)} pixels changed)`);
x.web_btn(12);                                   // PLAY: it calls the last hour
const pc = run(3);
check(Math.max(...pc) > loud, `PLAY: the cuckoo calls (its loudest ${Math.max(...pc)}, the ticks' ${tick})`);
run(9);
x.web_enc(1, -1);                                // and back
run(1);
check((x.web_state() & 1) === 0 && differ(wall, lcd()) < 20000, 'ALGORITHM again: the wall clock');
x.web_midi(0xB0, 20, 3); x.web_midi(0xB0, 21, 59); x.web_midi(0xB0, 22, 57);
const ph = run(4.5);
const first = ph.findIndex((p) => p > loud);
check(first >= 0 && (first * 128) / 44100 > 2.5 && (first * 128) / 44100 < 4.0,
  `the time over MIDI, 3:59:57: the hour strikes ${first >= 0 ? ((first * 128) / 44100).toFixed(2) + ' s on' : 'never'}`);
console.log(fail ? 'app_test: FAILED' : 'app_test: all passed');
process.exit(fail);
