// SPDX-License-Identifier: GPL-3.0-only
// FM-1 Clock on its own page: the firmware runs in the audio thread (worklet.js, fm1clock.wasm); here its screen, its
// keys' lights and the FM-1's controls, as buttons. Nothing is loaded before Start (a browser plays sound after a click).
const $ = (id) => document.getElementById(id);
const app = $('app');
if (app) {
  const lcd = $('lcd'), g = lcd.getContext('2d');
  const small = document.createElement('canvas');
  small.width = small.height = 240;
  const gs = small.getContext('2d');
  const img = gs.createImageData(240, 240);
  const px32 = new Uint32Array(img.data.buffer);
  const status = $('appstatus');
  let ac = null, node = null, gain = null, state = 0, booting = false;

  // the keys' lights: the FM-1's 27 keys (F3..G5), LED id 14 + key; black where platform.c's pattern says
  const isBlack = (k) => (0x54A >> ((53 + k) % 12)) & 1;
  const keysEl = $('keys');
  const keyEls = [];
  const nWhite = [...Array(27).keys()].filter((k) => !isBlack(k)).length;
  let wi = 0;
  for (let k = 0; k < 27; k++) {
    const el = document.createElement('span');
    if (isBlack(k)) {
      el.className = 'kb';
      el.style.left = `calc(${(100 * wi) / nWhite}% - ${(100 * 0.32) / nWhite}%)`;
      el.style.width = `${(100 * 0.64) / nWhite}%`;
    } else {
      el.className = 'kw';
      el.style.left = `${(100 * wi) / nWhite}%`;
      el.style.width = `${100 / nWhite}%`;
      wi++;
    }
    keysEl.appendChild(el);
    keyEls.push(el);
  }

  const now = () => { const d = new Date(); return { h: d.getHours(), m: d.getMinutes(), s: d.getSeconds() }; };
  const send = (m) => node && node.port.postMessage(m);
  const say = (t) => { status.textContent = t; };

  function draw(p) {                             // RGB565 -> the canvas, twice its size, sharp
    for (let i = 0; i < 57600; i++) {
      const c = p[i];
      const r = ((c >> 11) * 527 + 23) >> 6, gg = (((c >> 5) & 63) * 259 + 33) >> 6, b = ((c & 31) * 527 + 23) >> 6;
      px32[i] = 0xFF000000 | (b << 16) | (gg << 8) | r;
    }
    gs.putImageData(img, 0, 0);
    g.imageSmoothingEnabled = false;
    g.drawImage(small, 0, 0, lcd.width, lcd.height);
  }

  function show(st, leds) {                      // the controls as the firmware has them now
    state = st;
    const clock = st & 1;
    for (const b of app.querySelectorAll('[data-clock]')) b.setAttribute('aria-pressed', String(+b.dataset.clock === clock));
    $('b-silent').setAttribute('aria-pressed', String(!!(st & 2)));
    $('b-digits').setAttribute('aria-pressed', String(!!(st & 4)));
    $('b-info').setAttribute('aria-pressed', String(!!(st & 32)));
    $('b-wind').disabled = !clock;
    $('b-play').classList.toggle('lit', !!(leds[0] & (1 << 12)));
    for (let k = 0; k < 27; k++) {
      const id = 14 + k;
      const on = id < 32 ? leds[0] & (1 << id) : leds[1] & (1 << (id - 32));
      keyEls[k].classList.toggle('on', !!on);
    }
  }

  async function start() {
    if (booting) return;
    if (ac) {                                    // a pause, a go on: the clock's time is its sound's, so it set again
      if (ac.state === 'running') { await ac.suspend(); $('start').hidden = false; $('start').textContent = '▶ Go on'; say('Paused.'); }
      else { await ac.resume(); send({ type: 'time', time: now() }); $('start').hidden = true; say('Running, at your time.'); }
      return;
    }
    booting = true;
    say('Loading the firmware…');
    try {
      ac = new AudioContext({ sampleRate: 44100, latencyHint: 'playback' });
      const [wasm] = await Promise.all([
        fetch('app/fm1clock.wasm').then((r) => { if (!r.ok) throw new Error(`fm1clock.wasm: ${r.status}`); return r.arrayBuffer(); }),
        ac.audioWorklet.addModule('app/worklet.js'),
      ]);
      node = new AudioWorkletNode(ac, 'fm1-clock', { numberOfInputs: 0, outputChannelCount: [2] });
      gain = ac.createGain();
      gain.gain.value = vol();
      node.connect(gain).connect(ac.destination);
      node.port.onmessage = (e) => {
        const m = e.data;
        if (m.type === 'frame') { if (m.lcd) draw(m.lcd); show(m.state, m.leds); }
        else if (m.type === 'ready') { $('start').hidden = true; app.classList.add('on'); say('Running, at your time.'); }
        else if (m.type === 'error') say(`It did not start: ${m.message}`);
      };
      node.port.postMessage({ type: 'boot', wasm, ng: 206, time: now() }, [wasm]);
      await ac.resume();
    } catch (err) {
      say(`It did not start here: ${err.message || err}. It needs a browser with Web Audio worklets (any recent one).`);
      ac = null;
    }
    booting = false;
  }

  const vol = () => { const v = $('vol').value / 100; return v * v; };
  $('vol').addEventListener('input', () => { if (gain) gain.gain.value = vol(); });
  $('start').addEventListener('click', start);
  $('b-pause').addEventListener('click', () => { if (ac) start(); });
  $('b-time').addEventListener('click', () => send({ type: 'time', time: now() }));
  for (const b of app.querySelectorAll('[data-clock]'))
    b.addEventListener('click', () => { if (+b.dataset.clock !== (state & 1)) send({ type: 'enc', id: 1, n: 1 }); });   // ALGORITHM
  for (const b of app.querySelectorAll('[data-btn]'))
    b.addEventListener('click', () => send({ type: 'btn', id: +b.dataset.btn }));
  for (const b of app.querySelectorAll('[data-enc]'))
    b.addEventListener('click', () => send({ type: 'enc', id: +b.dataset.enc, n: +b.dataset.n }));
  document.addEventListener('visibilitychange', () => {   // (back to the page after a while: the time again)
    if (!document.hidden && ac && ac.state === 'running') send({ type: 'time', time: now() });
  });
}
