// SPDX-License-Identifier: GPL-3.0-only
// The site's "Try it here" in Chromium (Playwright): the page served over HTTP (a worklet needs it), Start, and the
// clock runs: its screen drawn, a key lit under the pendulum, at the computer's time (the digits); the cuckoo clock and
// PLAY (the strike button lit while it calls); no error on the page.
//
//   node tests/web/app_page.js build/site          (or a URL: the site as it is published)
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const dir = path.resolve(/^https?:/.test(process.argv[2] || '') ? '.' : process.argv[2] || 'build/site');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.wasm': 'application/wasm', '.png': 'image/png',
                '.gif': 'image/gif', '.fwsc': 'application/octet-stream' };
const server = http.createServer((req, res) => {
  const f = path.join(dir, decodeURIComponent(req.url.split('?')[0].split('#')[0]).replace(/\/$/, '/index.html'));
  if (!f.startsWith(dir) || !fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});

(async () => {
  const live = /^https?:/.test(process.argv[2] || '');
  if (!live) await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const url = live ? process.argv[2] : `http://127.0.0.1:${server.address().port}/`;
  const b = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  let fail = 0;
  const check = (ok, what) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`); if (!ok) fail = 1; };
  try {
    const p = await b.newPage({ viewport: { width: 1000, height: 1000 } });
    const errs = [];
    p.on('pageerror', (e) => errs.push(String(e)));
    p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
    await p.goto(url, { waitUntil: 'networkidle' });
    await p.click('#start');
    await p.waitForFunction(() => document.getElementById('app').classList.contains('on'), null, { timeout: 15000 });
    await p.waitForTimeout(2000);
    const drawn = await p.$eval('#lcd', (c) => {
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i] || d[i + 1] || d[i + 2]) n++;
      return n / (d.length / 4);
    });
    check(drawn > 0.9, `Start: the clock on the screen (${(100 * drawn).toFixed(0)} % of it drawn)`);
    check((await p.$$('.kbd span.on')).length === 1, "a key's light, under the pendulum");
    check(/Running/.test(await p.textContent('#appstatus')), 'the status: running');
    await p.click('[data-clock="1"]');
    await p.waitForTimeout(1500);
    check((await p.getAttribute('[data-clock="1"]', 'aria-pressed')) === 'true', 'ALGORITHM: the cuckoo clock');
    check(!(await p.$eval('#b-wind', (e) => e.disabled)), 'its ENV (Wind it) there');
    await p.click('#b-play');
    await p.waitForTimeout(1500);
    check(await p.$eval('#b-play', (e) => e.classList.contains('lit')), 'PLAY: lit while it calls');
    check(errs.length === 0, `no errors on the page${errs.length ? ': ' + errs.join(' | ') : ''}`);
  } finally {
    await b.close();
    if (!live) server.close();
  }
  console.log(fail ? 'app_page: FAILED' : 'app_page: all passed');
  process.exit(fail);
})();
