// SPDX-License-Identifier: GPL-3.0-only
// FM-1 Clock in a browser: the firmware (fm1clock.wasm, web/app/build.sh) in the audio thread. Its sound is the
// clock's time base, as the audio interrupt is on the FM-1: each quantum asks it for its frames, and it runs its main
// loop for the milliseconds they are worth. The screen and the lights go to the page about 30 times a second.
const FS = 44100;                                // the firmware's rate; another context rate is resampled (linear)

class FM1Clock extends AudioWorkletProcessor {
  constructor() {
    super();
    this.x = null;
    this.rev = -1;
    this.since = 0;
    this.step = FS / sampleRate;                 // firmware frames per output frame
    this.pos = 0;                                // (resampling) where we are in buf, in its frames
    this.buf = new Float32Array(2 * 4096);       // its frames not yet behind us, L R L R
    this.have = 0;
    this.port.onmessage = (e) => this.message(e.data);
  }

  async message(m) {
    if (m.type === 'boot') {
      try {
        const { instance } = await WebAssembly.instantiate(m.wasm, {});
        const x = instance.exports;
        x.web_init(m.ng || 206);
        this.setTime(x, m.time);
        this.x = x;
        this.port.postMessage({ type: 'ready' });
      } catch (err) {
        this.port.postMessage({ type: 'error', message: String(err) });
      }
      return;
    }
    const x = this.x;
    if (!x) return;
    if (m.type === 'btn') x.web_btn(m.id);
    else if (m.type === 'enc') x.web_enc(m.id, m.n);
    else if (m.type === 'time') this.setTime(x, m.time);
  }

  setTime(x, t) {                                // CC 20, 21, 22: the hours, minutes, seconds (the seconds set it)
    if (!t) return;
    x.web_midi(0xB0, 20, t.h);
    x.web_midi(0xB0, 21, t.m);
    x.web_midi(0xB0, 22, t.s);
  }

  process(_inputs, outputs) {
    const x = this.x;
    const out = outputs[0];
    if (!x) return true;
    const L = out[0], R = out[1] || out[0], n = L.length;
    if (this.step === 1) {                       // the usual case: the context runs at 44.1 kHz
      x.web_run(n);
      const o = new Int32Array(x.memory.buffer, x.web_out_ptr(), 2 * n);
      for (let i = 0; i < n; i++) {
        L[i] = o[2 * i] / 32768;
        R[i] = o[2 * i + 1] / 32768;
      }
    } else {                                     // another rate: a line between each two of its frames
      const st = this.step, b = this.buf;
      const top = Math.floor(this.pos + (n - 1) * st) + 2;   // the frames this quantum reads, from buf's start
      while (this.have < top) {
        x.web_run(128);
        const o = new Int32Array(x.memory.buffer, x.web_out_ptr(), 256);
        for (let i = 0; i < 256; i++) b[2 * this.have + i] = o[i] / 32768;
        this.have += 128;
      }
      for (let i = 0; i < n; i++) {
        const p = this.pos + i * st, j = p | 0, f = p - j;
        L[i] = b[2 * j] + (b[2 * j + 2] - b[2 * j]) * f;
        R[i] = b[2 * j + 1] + (b[2 * j + 3] - b[2 * j + 1]) * f;
      }
      this.pos += n * st;
      const done = this.pos | 0;                 // the frames behind us
      b.copyWithin(0, 2 * done, 2 * this.have);
      this.have -= done;
      this.pos -= done;
    }
    this.since += n;
    if (this.since >= sampleRate / 30) {         // the screen (when it changed), the lights, the state
      this.since = 0;
      const rev = x.web_lcd_rev();
      const msg = { type: 'frame', leds: [x.web_leds_lo(), x.web_leds_hi()], state: x.web_state(), ms: x.web_ms() };
      const transfer = [];
      if (rev !== this.rev) {
        this.rev = rev;
        msg.lcd = new Uint16Array(x.memory.buffer, x.web_lcd(), 240 * 240).slice();
        transfer.push(msg.lcd.buffer);
      }
      this.port.postMessage(msg, transfer);
    }
    return true;
  }
}

registerProcessor('fm1-clock', FM1Clock);
