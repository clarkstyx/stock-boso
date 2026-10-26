// Runs the page's analyze() on tests/fixtures/bars.json and prints JSON.
// Used by test_parity_with_javascript in test_boso.py.
//   node tests/parity.js
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const js = src.slice(src.indexOf('<script>') + 8, src.lastIndexOf('</script>'));

// Minimal DOM stubs so the page script can run headlessly.
const els = {};
const mk = id => ({ id, textContent: '', className: '', innerHTML: '', value: '', checked: false, disabled: false, hidden: true,
  addEventListener() {}, classList: { toggle() {}, add() {}, includes: () => false }, dataset: {}, scrollIntoView() {},
  clientWidth: 600, clientHeight: 300, getContext: () => new Proxy({}, { get: () => () => ({}) }) });
global.document = { getElementById: id => els[id] || (els[id] = mk(id)), querySelectorAll: () => [], documentElement: {} };
global.localStorage = { getItem: () => null, setItem() {} };
global.navigator = {}; global.window = { addEventListener() {}, devicePixelRatio: 1 };
global.requestAnimationFrame = f => f(); global.getComputedStyle = () => ({ getPropertyValue: () => '#000' });
new Function(js)();

const api = global.window.StockBoso;
if (!api) { console.error('index.html does not export window.StockBoso'); process.exit(2); }

const fx = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'bars.json'), 'utf8'));
const benches = {}; for (const b of ['QQQ', 'SMH']) benches[b] = api.benchInfo(fx[b]);
const out = {};
for (const sym of ['ACME', 'UPUP']) {
  const r = api.analyze(sym, fx[sym], benches, null, null);   // now=null -> treat as completed session
  out[sym] = { setup: r.setup, flags: r.flags, score: r.score, sc: r.raw.sc, rsi: r.rsi, atr: r.atr, rsB: r.rsB };
}
process.stdout.write(JSON.stringify(out));
