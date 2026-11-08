// SPDX-License-Identifier: GPL-3.0-only
// The site's installer (web/make_site.py, web/index.html) against a simulated FM-1 on Web MIDI: the update
// protocol's two steps (the running firmware reads some of the package and stages the loader; the loader reads all
// of it), then the FM-1 back as FM1 Clock. Every byte the page sends is checked against the package's image. Then
// an install cut off: the FM-1 already in update mode, the page finishes it.
//
//   node tests/web/install_sim.js SITE_DIR        (Playwright and its Chromium)
const { chromium } = require('playwright');
const SIM = ([startMode, startId]) => {
  const pack7 = (data) => { const o = []; let acc = 0, nb = 0; for (const b of data) { acc |= b << nb; nb += 8; while (nb >= 7) { o.push(acc & 0x7F); acc >>>= 7; nb -= 7; } } if (nb) o.push(acc & 0x7F); return o; };
  const unpack7 = (s) => { const o = []; let acc = 0, nb = 0; for (const b of s) { acc |= (b & 0x7F) << nb; nb += 7; while (nb >= 8) { o.push(acc & 0xFF); acc >>>= 8; nb -= 8; } } return o; };
  const S = window.__sim = { log: [], served: 0, bad: 0, modes: [] };
  const inputs = new Map(), outputs = new Map();
  let inp = null, out = null, mode = startMode, id = startId, image = null, queue = [], waiting = null;
  const toHost = (b) => setTimeout(() => { if (inp && inp.state === 'connected' && inp.onmidimessage) inp.onmidimessage({ data: new Uint8Array(b) }); }, 1);
  const plug = (name) => {
    inp = { name, state: 'connected', onmidimessage: null, open: async () => {} };
    out = { name, state: 'connected', open: async () => {}, send: (d) => onHost(Array.from(d)) };
    inputs.clear(); outputs.clear(); inputs.set('in', inp); outputs.set('out', out);
  };
  const unplug = () => { inp.state = out.state = 'disconnected'; out.send = () => { throw new Error('gone'); }; inputs.clear(); outputs.clear(); };
  const ident = (t) => { const d = [0, 0x59, 0x11, 0, 0, 0]; for (let i = 0; i < 27; i++) d.push(i < t.length ? t.charCodeAt(i) : 0); d.push(0); return [0xF0, ...pack7(d), 0xF7]; };
  const req = (a, n) => { const u = [0, 0x59, 0x30, 0, 0, 0, 0, a & 255, (a >>> 8) & 255, (a >>> 16) & 255, (a >>> 24) & 255, n & 255, (n >> 8) & 255, 0]; let s = 0; for (let i = 6; i < 14; i++) s += u[i]; u.push(~s & 255); return [0xF0, ...pack7(u), 0xF7]; };
  const logical = (f) => { const o = new Uint8Array(f.length - 20); for (let i = 0; i < 20; i++) o.set(f.subarray(i * 0x30, i * 0x30 + 0x2F), i * 0x2F); o.set(f.subarray(20 * 0x30), 20 * 0x2F); return o; };
  async function run(reqs, fin) {
    for (const [a, n] of [...reqs, [fin, 0]]) {
      const got = new Promise((r) => { waiting = r; });
      toHost(req(a, n));
      const body = await got;
      if (a === fin) break;
      const data = body.slice(14, 14 + n);
      for (let i = 0; i < n; i++) if (data[i] !== image[a + i]) S.bad++;
      S.served++;
    }
  }
  async function onHost(b) {
    if (b.length === 10 && b[1] === 0x00 && b[2] === 0x32) { toHost(ident(id)); return; }          // the handshake
    if (b.length === 6 && b[1] === 0x22 && b[2] === 0x24) {                                       // UPGRADE
      if (!image) image = logical(new Uint8Array(await (await fetch(document.getElementById('dl').href)).arrayBuffer()));
      S.modes.push(mode);
      if (mode === 'app') {                                                                       // step 1: some reads
        const r = []; for (let k = 0; k < 74; k++) r.push([(k * 7919 * 512) % (image.length - 512), 512]);
        await run(r, 0xE0000000);
        setTimeout(() => { unplug(); setTimeout(() => { mode = 'ota'; id = 'ota-FM-1_940'; plug('Felucca'); }, 1500); }, 300);
      } else {                                                                                    // step 2: all of it
        const r = []; for (let a = 0; a < image.length; a += 512) r.push([a, Math.min(512, image.length - a)]);
        await run(r, 0xF0000000);
        setTimeout(() => { unplug(); setTimeout(() => { mode = 'app'; id = 'FM-1_940'; plug('Felucca'); }, 1500); }, 300);
      }
      return;
    }
    if (b[0] === 0xF0 && waiting) { const w = waiting; waiting = null; w(unpack7(b.slice(1, -1))); }   // a response
  }
  plug('Felucca');
  navigator.requestMIDIAccess = async () => ({ inputs, outputs });
};
const http = require('http'), fs = require('fs'), path = require('path');
const dir = process.argv[2];
if (!dir) { console.error('usage: node tests/web/install_sim.js SITE_DIR'); process.exit(2); }
const types = { '.html': 'text/html', '.gif': 'image/gif', '.png': 'image/png', '.fwsc': 'application/octet-stream' };
const server = http.createServer((q, r) => {
  const f = path.join(dir, decodeURIComponent(q.url.split('?')[0]).replace(/\/$/, '/index.html'));
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); } else { r.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); r.end(d); } });
});
async function one(b, url, start, want) {
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(String(e)));
  await p.addInitScript(SIM, start);
  await p.goto(url, { waitUntil: 'networkidle' });
  await p.waitForFunction(() => !document.getElementById('go').disabled, null, { timeout: 15000 });
  await p.click('#go');
  await p.waitForFunction(() => /Done|Error|not|Stopped|lost/.test(document.getElementById('status').textContent), null, { timeout: 180000, polling: 500 });
  const status = await p.textContent('#status');
  const sim = await p.evaluate(() => window.__sim);
  const ok = /Done/.test(status) && sim.bad === 0 && sim.served > 1000 && JSON.stringify(sim.modes) === JSON.stringify(want) && !errs.length;
  console.log(`${start[1]}: ${status} (${sim.served} reads, ${sim.bad} bytes wrong, steps ${sim.modes.join(' -> ')})${errs.length ? ' errors: ' + errs : ''}: ${ok ? 'ok' : 'FAIL'}`);
  await p.close();
  return ok;
}
server.listen(0, async () => {
  const url = `http://127.0.0.1:${server.address().port}/`;
  const b = await chromium.launch();
  let ok = await one(b, url, ['app', 'FM-1_016'], ['app', 'ota']);        // from the official firmware
  ok = (await one(b, url, ['ota', 'ota-FM-1_940'], ['ota'])) && ok;      // an install cut off
  await b.close();
  server.close();
  process.exit(ok ? 0 : 1);
});
