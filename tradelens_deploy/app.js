/* app.js — TradeLens PWA frontend logic.
   Works ONLINE (talks to server.py) and OFFLINE (Greeks, paper-trading,
   watchlist, alerts all run client-side via localStorage). */

const API = location.origin;          // same host that served the page
const LS = {                          // localStorage keys
  watch: 'tl_watch', paper: 'tl_paper', cash: 'tl_cash', alerts: 'tl_alerts',
};
let ONLINE = false;
let DEFERRED_INSTALL = null;

/* ---------------- helpers ---------------- */
const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? '—'
  : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });

function toast(msg, ms = 2200) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('show'), ms);
}

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.status); }
  return r.json();
}

function badgeClass(action) {
  const a = (action || '').toUpperCase();
  if (a.includes('BUY')) return 'sig-buy';
  if (a.includes('SELL') || a.includes('SHORT')) return 'sig-sell';
  return 'sig-hold';
}

function drawSpark(svgId, vals) {
  const svg = $(svgId); if (!svg || !vals || !vals.length) return;
  const w = 300, h = 46, min = Math.min(...vals), max = Math.max(...vals);
  const rng = (max - min) || 1;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((v - min) / rng) * (h - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const up = vals[vals.length - 1] >= vals[0];
  svg.innerHTML = `<polyline points="${pts}" fill="none" stroke="${up ? '#22c55e' : '#ef4444'}" stroke-width="2"/>`;
}

/* ---------------- navigation ---------------- */
document.querySelectorAll('.nav a').forEach(a => {
  a.addEventListener('click', (e) => {
    e.preventDefault();
    document.querySelectorAll('.nav a').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.screen').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    $(a.dataset.screen).classList.add('active');
  });
});

/* ---------------- boot ---------------- */
const FALLBACK_SYMBOLS = ['Nifty 50', 'Sensex', 'Bank Nifty', 'Gold (USD)', 'Bitcoin (USD)'];
const FALLBACK_DAILY = ['EMA Crossover (20/50)', 'RSI Mean-Reversion', 'MACD Trend',
  'Donchian Breakout (20)', 'Combined (Trend+Momentum+RSI)'];
const FALLBACK_INTRA = ['VWAP Momentum', 'Opening Range Breakout', 'Supertrend (10,3)', 'RSI Scalper (7)'];

function fillSelect(el, items, sel) {
  el.innerHTML = items.map(x => `<option ${x === sel ? 'selected' : ''}>${x}</option>`).join('');
}

async function boot() {
  let symbols = FALLBACK_SYMBOLS, daily = FALLBACK_DAILY, intra = FALLBACK_INTRA;
  try {
    const s = await api('/api/symbols'); symbols = s.symbols;
    const st = await api('/api/strategies'); daily = st.daily; intra = st.intraday;
    ONLINE = true; $('netpill').textContent = 'online ✓';
  } catch (e) {
    ONLINE = false; $('netpill').textContent = 'offline mode';
  }
  ['sigSymbol', 'inSymbol', 'paSymbol', 'alSymbol'].forEach(id => fillSelect($(id), symbols, symbols[0]));
  fillSelect($('sigStrategy'), daily, daily[daily.length - 1]);
  fillSelect($('inStrategy'), intra, intra[0]);
  renderPaper(); renderWatch(); renderAlerts();
}

/* ---------------- signals ---------------- */
async function loadSignal() {
  if (!ONLINE) return toast('Signals need the server running. Start server.py.');
  $('sigLoader').innerHTML = '<div class="loader"></div>'; $('sigResult').style.display = 'none';
  try {
    const symbol = $('sigSymbol').value, strategy = $('sigStrategy').value, period = $('sigPeriod').value;
    const d = await api(`/api/signal?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&period=${period}`);
    const chg = ((d.last_close / d.prev_close - 1) * 100);
    $('sigName').textContent = `${d.symbol} · ${d.strategy}`;
    $('sigPrice').textContent = '₹' + fmt(d.last_close);
    $('sigChg').innerHTML = `<span class="${chg >= 0 ? 'chg-up' : 'chg-dn'}">${chg >= 0 ? '▲' : '▼'} ${fmt(Math.abs(chg))}%</span>`;
    const b = $('sigBadge'); b.textContent = d.action; b.className = 'signal-badge ' + badgeClass(d.action);
    $('sigRsi').textContent = d.rsi != null ? `RSI ${d.rsi}` : '';
    drawSpark('sigSpark', d.spark);
    $('sigResult').dataset.symbol = d.symbol;
    $('sigResult').dataset.price = d.last_close;
    $('sigResult').style.display = 'block';
  } catch (e) { toast('Error: ' + e.message); }
  $('sigLoader').innerHTML = '';
}

async function loadBacktest() {
  if (!ONLINE) return toast('Backtest needs the server running.');
  $('btResult').innerHTML = '<div class="loader"></div>';
  try {
    const symbol = $('sigSymbol').value, strategy = $('sigStrategy').value, period = $('sigPeriod').value;
    const short = $('btShort').checked;
    const d = await api(`/api/backtest?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&period=${period}&short=${short}`);
    const m = d.metrics;
    const stat = (k, v) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`;
    $('btResult').innerHTML = `
      <div class="grid3" style="margin-top:12px">
        ${stat('Net %', m['Net Return %'])}
        ${stat('Buy&Hold %', m['Buy & Hold %'])}
        ${stat('CAGR %', m['CAGR %'])}
        ${stat('Sharpe', m['Sharpe (ann.)'])}
        ${stat('MaxDD %', m['Max Drawdown %'])}
        ${stat('Win %', m['Win Rate %'])}
        ${stat('Trades', m['Total Trades'])}
        ${stat('Profit F.', m['Profit Factor'])}
        ${stat('Final ₹', fmt(m['Final Equity'], 0))}
      </div>
      ${equityChart(d)}
      <div class="mut" style="margin-top:10px">Last ${d.trades.length} trades:</div>
      ${tradeTable(d.trades)}`;
  } catch (e) { $('btResult').innerHTML = `<div class="empty">Error: ${e.message}</div>`; }
}

function equityChart(d) {
  const eq = d.equity, bh = d.buyhold; if (!eq || !eq.length) return '';
  const all = eq.concat(bh), min = Math.min(...all), max = Math.max(...all), rng = (max - min) || 1;
  const w = 300, h = 90;
  const line = (arr, col) => {
    const pts = arr.map((v, i) => `${(i / (arr.length - 1) * w).toFixed(1)},${(h - (v - min) / rng * (h - 6) - 3).toFixed(1)}`).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2"/>`;
  };
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:90px;margin-top:12px">
    ${line(bh, '#8aa0c6')}${line(eq, '#22c55e')}</svg>
    <div class="mut" style="font-size:11px"><span style="color:#22c55e">■</span> Strategy &nbsp; <span style="color:#8aa0c6">■</span> Buy&Hold</div>`;
}

function tradeTable(trades) {
  if (!trades || !trades.length) return '<div class="empty">No trades.</div>';
  const rows = trades.slice(-12).reverse().map(t => `<tr>
    <td>${t.entry_date}</td><td><span class="tag ${t.direction === 'LONG' ? 'long' : 'short'}">${t.direction}</span></td>
    <td>${fmt(t.entry)}</td><td>${fmt(t.exit)}</td>
    <td class="${t.pnl_pct >= 0 ? 'chg-up' : 'chg-dn'}">${(t.pnl_pct * 100).toFixed(2)}%</td></tr>`).join('');
  return `<table><tr><th>Entry</th><th>Side</th><th>In</th><th>Out</th><th>P&L</th></tr>${rows}</table>`;
}

/* ---------------- intraday ---------------- */
document.querySelectorAll('#inTf button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#inTf button').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
}));

async function loadIntraday() {
  if (!ONLINE) return toast('Intraday needs the server running.');
  $('inLoader').innerHTML = '<div class="loader"></div>'; $('inResult').innerHTML = '';
  try {
    const symbol = $('inSymbol').value, strategy = $('inStrategy').value;
    const tf = document.querySelector('#inTf button.on').dataset.tf;
    const d = await api(`/api/intraday?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&tf=${tf}&short=true`);
    const m = d.metrics;
    const stat = (k, v) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`;
    $('inResult').innerHTML = `<div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div class="mut">${symbol} · ${tf}</div>
        <div class="signal-badge ${badgeClass(d.action)}">${d.action}</div>
      </div>
      <div class="grid3" style="margin-top:12px">
        ${stat('Net %', m['Net Return %'])}${stat('Trades', m['Total Trades'])}${stat('Win %', m['Win Rate %'])}
        ${stat('Sharpe', m['Sharpe (ann.)'])}${stat('MaxDD %', m['Max Drawdown %'])}${stat('PF', m['Profit Factor'])}
      </div>
      ${tradeTable(d.trades)}
      <div class="disclaimer" style="margin-top:10px">Intraday edges decay fast & costs bite harder. Short free-data windows make these noisy — validate on live data + paper trading.</div>
    </div>`;
  } catch (e) { $('inResult').innerHTML = `<div class="empty">Error: ${e.message}</div>`; }
  $('inLoader').innerHTML = '';
}

/* ---------------- greeks (works OFFLINE too via local BS) ---------------- */
function normCdf(x) { // Abramowitz-Stegun
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp(-x * x / 2);
  let p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}
function normPdf(x) { return 0.3989422804 * Math.exp(-x * x / 2); }

function localGreeks(S, K, T, r, sig, type) {
  if (T <= 0 || sig <= 0) {
    const px = type === 'call' ? Math.max(0, S - K) : Math.max(0, K - S);
    return { price: px, delta: 0, gamma: 0, theta_per_day: 0, vega_per_1pct: 0, rho_per_1pct: 0 };
  }
  const d1 = (Math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * Math.sqrt(T));
  const d2 = d1 - sig * Math.sqrt(T);
  let price, delta, theta, rho;
  if (type === 'call') {
    price = S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2);
    delta = normCdf(d1);
    theta = -(S * normPdf(d1) * sig) / (2 * Math.sqrt(T)) - r * K * Math.exp(-r * T) * normCdf(d2);
    rho = K * T * Math.exp(-r * T) * normCdf(d2);
  } else {
    price = K * Math.exp(-r * T) * normCdf(-d2) - S * normCdf(-d1);
    delta = normCdf(d1) - 1;
    theta = -(S * normPdf(d1) * sig) / (2 * Math.sqrt(T)) + r * K * Math.exp(-r * T) * normCdf(-d2);
    rho = -K * T * Math.exp(-r * T) * normCdf(-d2);
  }
  const gamma = normPdf(d1) / (S * sig * Math.sqrt(T));
  const vega = S * normPdf(d1) * Math.sqrt(T);
  return { price, delta, gamma, theta_per_day: theta / 365, vega_per_1pct: vega / 100, rho_per_1pct: rho / 100 };
}

function calcGreeks() {
  const S = +$('gS').value, K = +$('gK').value, dte = +$('gDte').value;
  const iv = +$('gIv').value / 100, r = 6.5 / 100, type = $('gType').value, lot = +$('gLot').value;
  const g = localGreeks(S, K, dte / 365, r, iv, type);
  $('gPrice').textContent = fmt(g.price);
  $('gDelta').textContent = g.delta.toFixed(3);
  $('gGamma').textContent = g.gamma.toFixed(5);
  $('gTheta').textContent = fmt(g.theta_per_day);
  $('gVega').textContent = fmt(g.vega_per_1pct);
  $('gRho').textContent = fmt(g.rho_per_1pct);
  $('gLotInfo').innerHTML = `1 lot (${lot}) premium ≈ <b>₹${fmt(g.price * lot, 0)}</b> · Theta decay ≈ <b>₹${fmt(g.theta_per_day * lot, 0)}/day</b> · Delta exposure ≈ <b>${(g.delta * lot).toFixed(1)}</b>`;
  $('gResult').style.display = 'block';
}

function calcIV() {
  const price = +$('ivPrice').value, S = +$('gS').value, K = +$('gK').value, dte = +$('gDte').value;
  const r = 6.5 / 100, type = $('gType').value, T = dte / 365;
  if (T <= 0 || price <= 0) { $('ivOut').textContent = 'n/a'; return; }
  let lo = 0.0001, hi = 5;
  const f = (v) => localGreeks(S, K, T, r, v, type).price - price;
  if (f(lo) * f(hi) > 0) { $('ivOut').textContent = 'n/a'; return; }
  for (let i = 0; i < 80; i++) { const m = (lo + hi) / 2; (f(lo) * f(m) < 0) ? hi = m : lo = m; }
  $('ivOut').textContent = (((lo + hi) / 2) * 100).toFixed(2) + '% IV';
}

/* ---------------- paper trading (localStorage) ---------------- */
function getJSON(k, def) { try { return JSON.parse(localStorage.getItem(k)) ?? def; } catch { return def; } }
function setJSON(k, v) { localStorage.setItem(k, JSON.stringify(v)); }

function getCash() { const c = localStorage.getItem(LS.cash); return c === null ? 100000 : +c; }
function setCash(v) { localStorage.setItem(LS.cash, String(v)); }

async function livePrice(symbol) {
  if (!ONLINE) return null;
  try { const d = await api(`/api/signal?symbol=${encodeURIComponent(symbol)}&strategy=EMA%20Crossover%20(20%2F50)&period=1y`); return d.last_close; }
  catch { return null; }
}

async function addPaperTrade() {
  const symbol = $('paSymbol').value, side = $('paSide').value, qty = +$('paQty').value;
  let price = +$('paPrice').value;
  if (!price) { price = await livePrice(symbol); if (!price) return toast('No live price — enter a price manually.'); }
  const cost = price * qty;
  let cash = getCash();
  if (side === 'BUY' && cost > cash) return toast('Not enough virtual cash.');
  cash += side === 'BUY' ? -cost : cost;
  setCash(cash);
  const trades = getJSON(LS.paper, []);
  trades.push({ id: Date.now(), symbol, side, qty, entry: price, ts: new Date().toLocaleString('en-IN') });
  setJSON(LS.paper, trades);
  toast(`Paper ${side} ${qty} ${symbol} @ ₹${fmt(price)}`);
  renderPaper();
}

async function renderPaper() {
  const trades = getJSON(LS.paper, []);
  let openPnl = 0, invested = 0;
  const rows = [];
  for (const t of trades) {
    const lp = await livePrice(t.symbol);
    const cur = lp || t.entry;
    const pnl = (t.side === 'BUY' ? 1 : -1) * (cur - t.entry) * t.qty;
    openPnl += pnl; invested += t.entry * t.qty;
    rows.push(`<div class="list-item">
      <div><b>${t.symbol}</b> <span class="tag ${t.side === 'BUY' ? 'long' : 'short'}">${t.side} ${t.qty}</span>
        <div class="mut" style="font-size:11px">@₹${fmt(t.entry)} → ₹${fmt(cur)}</div></div>
      <div style="text-align:right">
        <div class="${pnl >= 0 ? 'chg-up' : 'chg-dn'}">${pnl >= 0 ? '+' : ''}₹${fmt(pnl, 0)}</div>
        <button class="ghost" style="width:auto;padding:5px 10px;font-size:12px;margin-top:4px" onclick="closePaper(${t.id})">Close</button>
      </div></div>`);
  }
  $('paList').innerHTML = rows.length ? rows.join('') : '<div class="empty">No paper trades yet.</div>';
  const cash = getCash();
  $('pCash').textContent = '₹' + fmt(cash, 0);
  $('pPnl').innerHTML = `<span class="${openPnl >= 0 ? 'chg-up' : 'chg-dn'}">${openPnl >= 0 ? '+' : ''}₹${fmt(openPnl, 0)}</span>`;
  $('pEquity').textContent = '₹' + fmt(cash + invested + openPnl, 0);
}

async function closePaper(id) {
  const trades = getJSON(LS.paper, []);
  const t = trades.find(x => x.id === id); if (!t) return;
  const lp = await livePrice(t.symbol) || t.entry;
  let cash = getCash();
  cash += t.side === 'BUY' ? lp * t.qty : -lp * t.qty;   // close out
  setCash(cash);
  setJSON(LS.paper, trades.filter(x => x.id !== id));
  toast('Position closed.'); renderPaper();
}

/* ---------------- watchlist ---------------- */
function addToWatch() {
  const r = $('sigResult'); const sym = r.dataset.symbol; if (!sym) return;
  const w = getJSON(LS.watch, []);
  if (w.includes(sym)) return toast('Already in watchlist.');
  w.push(sym); setJSON(LS.watch, w); toast('Added to watchlist.'); renderWatch();
}
async function renderWatch() {
  const w = getJSON(LS.watch, []);
  if (!w.length) { $('watchList').innerHTML = '<div class="empty">Empty. Add from Signals tab.</div>'; return; }
  $('watchList').innerHTML = w.map(s => `<div class="list-item" id="w-${s.replace(/\W/g, '')}">
    <div><b>${s}</b><div class="mut" style="font-size:11px" id="wp-${s.replace(/\W/g, '')}">tap refresh…</div></div>
    <button class="ghost" style="width:auto;padding:5px 10px;font-size:12px" onclick="rmWatch('${s}')">✕</button></div>`).join('');
}
function rmWatch(s) { setJSON(LS.watch, getJSON(LS.watch, []).filter(x => x !== s)); renderWatch(); }
async function refreshWatch() {
  if (!ONLINE) return toast('Need server for live signals.');
  const w = getJSON(LS.watch, []);
  for (const s of w) {
    try {
      const d = await api(`/api/signal?symbol=${encodeURIComponent(s)}&strategy=Combined%20(Trend%2BMomentum%2BRSI)&period=1y`);
      const chg = ((d.last_close / d.prev_close - 1) * 100).toFixed(2);
      const el = $('wp-' + s.replace(/\W/g, ''));
      if (el) el.innerHTML = `₹${fmt(d.last_close)} <span class="${chg >= 0 ? 'chg-up' : 'chg-dn'}">${chg}%</span> · <b>${d.action}</b>`;
    } catch { }
  }
  toast('Watchlist refreshed.');
}

/* ---------------- alerts ---------------- */
function addAlert() {
  const symbol = $('alSymbol').value, cond = $('alCond').value, level = +$('alLevel').value;
  if (!level) return toast('Enter a level.');
  const a = getJSON(LS.alerts, []);
  a.push({ id: Date.now(), symbol, cond, level }); setJSON(LS.alerts, a);
  if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
  toast('Alert added.'); renderAlerts();
}
function renderAlerts() {
  const a = getJSON(LS.alerts, []);
  $('alList').innerHTML = a.length ? a.map(x => `<div class="list-item">
    <div><b>${x.symbol}</b> ${x.cond === 'above' ? '≥' : '≤'} ₹${fmt(x.level)}</div>
    <button class="ghost" style="width:auto;padding:5px 10px;font-size:12px" onclick="rmAlert(${x.id})">✕</button></div>`).join('')
    : '<div class="empty">No alerts set.</div>';
}
function rmAlert(id) { setJSON(LS.alerts, getJSON(LS.alerts, []).filter(x => x.id !== id)); renderAlerts(); }

async function checkAlerts() {
  if (!ONLINE) return;
  const a = getJSON(LS.alerts, []); if (!a.length) return;
  for (const x of a) {
    const p = await livePrice(x.symbol); if (!p) continue;
    const hit = x.cond === 'above' ? p >= x.level : p <= x.level;
    if (hit) {
      const msg = `${x.symbol} ₹${fmt(p)} ${x.cond} ₹${fmt(x.level)}`;
      if ('Notification' in window && Notification.permission === 'granted')
        new Notification('🔔 TradeLens Alert', { body: msg });
      else toast('🔔 ' + msg, 4000);
      rmAlert(x.id);
    }
  }
}
setInterval(checkAlerts, 60000); // check every minute while open

/* ---------------- angel login ---------------- */
async function angelLogin() {
  if (!ONLINE) return toast('Server must be running for Angel One.');
  try {
    const body = JSON.stringify({
      api_key: $('anApi').value, client_code: $('anClient').value,
      pin: $('anPin').value, totp_secret: $('anTotp').value,
    });
    const d = await api('/api/angel/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
    $('anStatus').innerHTML = d.ok ? '✅ ' + d.message : '❌ ' + d.message;
    toast(d.ok ? 'Connected to Angel One' : 'Login failed');
  } catch (e) { $('anStatus').textContent = '❌ ' + e.message; }
}

/* ---------------- install prompt ---------------- */
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault(); DEFERRED_INSTALL = e; $('installBtn').style.display = 'block';
});
function doInstall() {
  if (!DEFERRED_INSTALL) return toast('Use browser menu → Add to Home Screen.');
  DEFERRED_INSTALL.prompt();
}

/* ---------------- service worker + boot ---------------- */
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => { });
}
boot();
