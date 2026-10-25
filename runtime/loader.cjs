/* Additive official-client loader, inspired by xhwxt/zusage's Electron injection path. */
"use strict";
const { app, webContents } = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { fileURLToPath } = require('node:url');
const ROOT = __dirname;
let stopped = false, busy = false, timer;
const bound = new WeakSet();
const booted = new WeakSet();
const diag = { version: '0.4.2', loadedAt: new Date().toISOString(), windows: 0, updates: 0 };

function eligible(wc) {
  try {
    if (wc.isDestroyed() || wc.getType() !== 'window') return false;
    const url = new URL(wc.getURL());
    return url.protocol === 'file:' && fileURLToPath(url).replaceAll('\\', '/').endsWith('/app.asar/out/renderer/index.html');
  } catch { return false; } // A window may be between navigations.
}
function bounded(promise, ms = 2500) {
  let timeout;
  return Promise.race([promise, new Promise((_, reject) => {
    timeout = setTimeout(() => reject(new Error('renderer-timeout')), ms);
  })]).finally(() => clearTimeout(timeout));
}
async function inject(wc) {
  if (!eligible(wc)) return;
  const source = await fs.readFile(path.join(ROOT, 'overlay.js'), 'utf8');
  await bounded(wc.executeJavaScript(source));
  booted.add(wc);
}
function bind(wc) {
  if (bound.has(wc)) return;
  bound.add(wc);
  wc.on('did-finish-load', () => { booted.delete(wc); });
}
async function query(ids) {
  const cfg = JSON.parse(await fs.readFile(path.join(ROOT, 'config.json'), 'utf8'));
  return new Promise((resolve) => {
    const child = execFile(cfg.python, [path.join(ROOT, 'collector.py'), cfg.database],
      { timeout: 4000, maxBuffer: 128 * 1024, windowsHide: true }, (error, stdout) => {
        try { resolve(JSON.parse(stdout)); }
        catch { resolve({ sessions: {}, error: 'data-unavailable' }); }
      });
    child.stdin.on('error', () => {}); // Exit before stdin is consumed is handled by the callback.
    child.stdin.end(JSON.stringify(ids));
  });
}
async function tick() {
  if (busy || stopped) return;
  busy = true;
  try {
    const targets = [];
    for (const wc of webContents.getAllWebContents()) {
      bind(wc);
      if (!eligible(wc)) continue;
      try {
        if (!booted.has(wc)) await inject(wc);
        const ids = await bounded(wc.executeJavaScript('window.__dshStats?.wanted() || []'));
        if (Array.isArray(ids)) targets.push({ wc, ids: ids.filter(s => typeof s === 'string' && s.length <= 160).slice(0, 8) });
      } catch { booted.delete(wc); } // Retry windows that reload or did not finish mounting.
    }
    diag.windows = targets.length;
    const ids = [...new Set(targets.flatMap(t => t.ids))];
    if (ids.length) {
      const data = { sessions: {} };
      for (let offset = 0; offset < ids.length; offset += 8) {
        const batch = await query(ids.slice(offset, offset + 8));
        Object.assign(data.sessions, batch.sessions);
        if (batch.error) data.error = batch.error;
      }
      for (const { wc, ids: ownIds } of targets) {
        // Each window receives only data for its explicitly mounted sessions.
        const payload = { sessions: Object.fromEntries(ownIds.map(s => [s, data.sessions?.[s] || { error: 'session-unavailable' }])), error: data.error, at: Date.now() };
        if (eligible(wc)) await bounded(wc.executeJavaScript(`window.__dshStats?.receive(${JSON.stringify(payload)})`)).catch(() => {});
      }
      diag.updates += 1;
      diag.dataAvailable = !data.error;
    }
    diag.checkedAt = new Date().toISOString();
    await fs.writeFile(path.join(ROOT, 'health.json'), JSON.stringify(diag, null, 2), { mode: 0o600 });
  } catch (error) {
    console.error('[zcode-dsh-stats]', error.code || error.message);
  } finally {
    busy = false;
    if (!stopped) timer = setTimeout(tick, 1500);
  }
}
app.on('will-quit', () => { stopped = true; clearTimeout(timer); });
app.whenReady().then(tick).catch(e => console.error('[zcode-dsh-stats]', e.message));
