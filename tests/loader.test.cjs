'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../runtime/loader.cjs'), 'utf8');
const WINDOWS_URL = 'file:///C:/Program%20Files/ZCode/resources/app.asar/out/renderer/index.html?restoreSession=true';
const MAIN_URL = process.platform === 'win32' ? WINDOWS_URL : 'file:///Applications/ZCode.app/Contents/Resources/app.asar/out/renderer/index.html?restoreSession=true';
const OVERLAY = 'window.__dshStats = window.__testStats;';

function windowFixture(ids, options = {}) {
  const wc = new EventEmitter();
  Object.assign(wc, { ids, url: MAIN_URL, type: 'window', destroyed: false, scripts: [], received: [], ...options });
  const sandbox = {
    __testStats: {
      wanted: () => wc.ids,
      receive: data => wc.received.push(JSON.parse(JSON.stringify(data))),
    },
  };
  sandbox.window = sandbox;
  wc.context = vm.createContext(sandbox);
  wc.getURL = () => wc.url;
  wc.getType = () => wc.type;
  wc.isDestroyed = () => wc.destroyed;
  wc.executeJavaScript = async code => {
    wc.scripts.push(code);
    return vm.runInContext(code, wc.context);
  };
  return wc;
}

async function launch(windows) {
  const app = new EventEmitter();
  app.whenReady = () => Promise.resolve();
  const timers = new Map();
  const queries = [];
  const health = [];
  const errors = [];
  let timerId = 0;
  const config = { python: '/test/python3', database: '/test/zcode/db.sqlite' };
  const fakeFs = {
    readFile: async name => {
      if (path.basename(name) === 'overlay.js') return OVERLAY;
      if (path.basename(name) === 'config.json') return JSON.stringify(config);
      throw new Error(`Unexpected read: ${name}`);
    },
    writeFile: async (name, contents) => {
      assert.equal(path.basename(name), 'health.json');
      health.push(JSON.parse(contents));
    },
  };
  const modules = {
    electron: { app, webContents: { getAllWebContents: () => windows } },
    'node:fs/promises': fakeFs,
    'node:path': path,
    'node:url': require('node:url'),
    'node:child_process': {
      execFile: (executable, args, options, callback) => {
        assert.equal(executable, config.python);
        assert.equal(args[1], config.database);
        const stdin = new EventEmitter();
        stdin.end = input => {
          const ids = JSON.parse(input);
          queries.push(ids);
          // Give every session a different recognizable value to detect cross-window leakage.
          const sessions = Object.fromEntries(ids.map(id => [id, { sampleOwner: id }]));
          queueMicrotask(() => callback(null, JSON.stringify({ sessions })));
        };
        return { stdin };
      },
    },
  };
  vm.runInNewContext(source, {
    __dirname: '/test/runtime',
    require: name => {
      assert.ok(Object.hasOwn(modules, name), `Unexpected module: ${name}`);
      return modules[name];
    },
    URL,
    console: { error: (...args) => errors.push(args) },
    setTimeout: (callback, delay) => {
      const id = ++timerId;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimeout: id => timers.delete(id),
  }, { filename: 'loader.cjs' });

  // Drain asynchronous bootstrap work without advancing any fake timeout.
  for (let i = 0; i < 20 && !health.length; i++) await new Promise(resolve => setImmediate(resolve));
  assert.equal(health.length, 1, `Loader did not finish bootstrap: ${JSON.stringify(errors)}`);

  const nextPoll = async () => {
    // Once the current tick settled, bounded renderer timers have all been cleared.
    assert.equal(timers.size, 1, 'Expected exactly one pending poll after a completed tick');
    const [id, timer] = [...timers][0];
    timers.delete(id);
    await timer.callback();
    assert.deepEqual(errors, []);
  };
  return { app, timers, queries, health, errors, nextPoll };
}

test('injects only live packaged ZCode renderer windows', async () => {
  const valid = windowFixture(['official-session']);
  const denied = [
    windowFixture(['web-session'], { url: 'https://example.test/app.asar/out/renderer/index.html' }),
    windowFixture(['browser-session'], { type: 'webview' }),
    windowFixture(['closed-session'], { destroyed: true }),
    windowFixture(['other-file'], { url: 'file:///tmp/preview.html' }),
    windowFixture(['navigation'], { url: 'about:blank' }),
  ];
  const harness = await launch([valid, ...denied]);
  assert.deepEqual(harness.queries, [['official-session']]);
  assert.equal(valid.received.length, 1);
  for (const wc of denied) assert.equal(wc.scripts.length, 0);
  harness.app.emit('will-quit');
});

test('Windows packaged file URLs with spaces receive the correct session', async () => {
  const wc = windowFixture(['windows-session'], { url: WINDOWS_URL });
  const harness = await launch([wc]);
  assert.deepEqual(harness.queries, [['windows-session']]);
  assert.equal(wc.received[0].sessions['windows-session'].sampleOwner, 'windows-session');
  harness.app.emit('will-quit');
});

test('each window receives only its requested sessions and switches without stale-session delivery', async () => {
  const left = windowFixture(['left-a', 'left-b']);
  const right = windowFixture(['right']);
  const harness = await launch([left, right]);
  assert.deepEqual(Object.keys(left.received[0].sessions), ['left-a', 'left-b']);
  assert.deepEqual(Object.keys(right.received[0].sessions), ['right']);
  assert.equal(right.received[0].sessions.right.sampleOwner, 'right');

  left.ids = ['left-new'];
  await harness.nextPoll();
  assert.deepEqual(Object.keys(left.received.at(-1).sessions), ['left-new']);
  assert.deepEqual(Object.keys(right.received.at(-1).sessions), ['right']);
  assert.equal(left.received.at(-1).sessions['left-new'].sampleOwner, 'left-new');
  harness.app.emit('will-quit');
});

test('a cancelled before-quit leaves telemetry polling alive; will-quit stops it', async () => {
  const wc = windowFixture(['session']);
  const harness = await launch([wc]);
  let cancelled = false;
  harness.app.on('before-quit', event => event.preventDefault());
  harness.app.emit('before-quit', { preventDefault: () => { cancelled = true; } });
  assert.equal(cancelled, true);
  await harness.nextPoll();
  assert.equal(wc.received.length, 2);
  assert.equal(harness.health.length, 2);
  harness.app.emit('will-quit');
  assert.equal(harness.timers.size, 0);
});

test('more than eight requested sessions across windows are queried in bounded batches without loss', async () => {
  const windows = Array.from({ length: 3 }, (_, w) =>
    windowFixture(Array.from({ length: 5 }, (_, s) => `window-${w}-session-${s}`)));
  const harness = await launch(windows);
  assert.ok(harness.queries.length > 1);
  assert.ok(harness.queries.every(ids => ids.length <= 8));
  const wanted = windows.flatMap(wc => wc.ids);
  assert.deepEqual([...new Set(harness.queries.flat())].sort(), [...wanted].sort());
  for (const wc of windows) {
    assert.deepEqual(Object.keys(wc.received[0].sessions), wc.ids);
    for (const id of wc.ids) assert.deepEqual(wc.received[0].sessions[id], { sampleOwner: id });
  }
  harness.app.emit('will-quit');
});

test('a renderer reload remounts the overlay before requesting the new document session', async () => {
  const wc = windowFixture(['old']);
  const harness = await launch([wc]);
  vm.runInContext('delete window.__dshStats', wc.context);
  wc.ids = ['reloaded'];
  wc.emit('did-finish-load');
  await harness.nextPoll();
  assert.equal(wc.scripts.filter(code => code === OVERLAY).length, 2);
  assert.deepEqual(Object.keys(wc.received.at(-1).sessions), ['reloaded']);
  harness.app.emit('will-quit');
});
