"use strict";

const $ = id => document.getElementById(id);
const markets = { NIFTY50: "NIFTY 50", EURUSD: "EUR/USD" };
const horizons = [1, 5, 15];
const signals = ["UP", "DOWN", "NO TRADE"];
const outcomes = ["WIN", "LOSS", "PUSH", "PENDING"];
const timestamp = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
});
const clock = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
});
const label = value => value == null || value === "" ? "—" : String(value);
const escape = value => label(value).replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));
const finite = value => typeof value === "number" && Number.isFinite(value);
const iso = value => new Date(value).toISOString();
const fmt = value => value ? timestamp.format(new Date(value)) + " IST" : "—";
const num = (value, digits = 2) => finite(value) ? value.toLocaleString("en-IN", {
  minimumFractionDigits: digits, maximumFractionDigits: digits
}) : "—";
const price = value => num(value, state.market === "EURUSD" ? 5 : 2);
const baseTime = Date.parse("2026-11-25T05:30:00Z");

function makeDemoMarket(symbol) {
  const isIndex = symbol === "NIFTY50";
  const base = isIndex ? 26080 : 1.154;
  const unit = isIndex ? 1 : .000015;
  let last = base - 21 * unit;
  let ema20 = last;
  let ema50 = last;
  const candles = Array.from({ length: 60 }, (_, i) => {
    const open = last;
    const close = base + unit * (i * 1.04 - 20 + 13 * Math.sin(i * .23) + 5.2 * Math.sin(i * 1.51));
    const high = Math.max(open, close) + unit * (3 + i % 5);
    const low = Math.min(open, close) - unit * (2 + i % 4);
    ema20 += (close - ema20) * 2 / 21;
    ema50 += (close - ema50) * 2 / 51;
    last = close;
    return {
      time: iso(baseTime - (59 - i) * 60000), open, high, low, close, completed: true,
      indicators: {
        ema20, ema50, rsi: 55 + 11 * Math.sin(i * .23), macd: (2 + 4 * Math.sin(i * .23)) * unit,
        atr: unit * 11, support: base + unit * (i * 1.04 - 37), resistance: base + unit * (i * 1.04 + 5)
      },
      pattern: i % 9 === 0 ? "Doji" : i % 7 === 0 ? "Bullish Harami" : "None detected"
    };
  });
  const sampleSignals = candles.slice(47).flatMap((candle, i) => horizons.map(horizon => {
    const signal = i % (horizon === 1 ? 4 : 3) === 0 ? "NO TRADE" : i % 2 ? "UP" : "DOWN";
    const reason = signal === "NO TRADE"
      ? "Price is near resistance and momentum is mixed."
      : signal === "UP" ? "Fast EMA is above slow EMA and momentum is rising."
        : "Short-term momentum is weakening below the previous candle.";
    const future = candles[47 + i + horizon];
    let outcome = null;
    if (signal !== "NO TRADE") {
      const delta = future && future.close - candle.close;
      outcome = !future ? "PENDING" : delta === 0 ? "PUSH" : (delta > 0) === (signal === "UP") ? "WIN" : "LOSS";
    }
    return { time: candle.time, horizon, signal, reason, origin: i % 2 ? "recorded" : "recomputed", outcome };
  }));
  return {
    provider: isIndex ? "Upstox" : "Twelve Data", quality: "Sample feed", missing: 0, candles, signals: sampleSignals,
    paperTrades: [{ time: candles[48].time, direction: "UP", result: "WIN", profitLoss: 80 },
      { time: candles[50].time, direction: "DOWN", result: "LOSS", profitLoss: -100 },
      { time: candles[59].time, direction: "UP", result: "OPEN" }]
  };
}

const demo = {
  markets: { NIFTY50: makeDemoMarket("NIFTY50"), EURUSD: makeDemoMarket("EURUSD") },
  stage: "Sample stage 58", tests: "Sample report"
};
const state = { data: { markets: {} }, market: "NIFTY50", horizon: 15, mode: "latest", selected: "", page: "overview", filter: "" };
const marketData = () => state.data.markets[state.market];
const isDemo = () => state.data === demo;
const live = { active: false, status: "", connected: false, timer: null, request: null };
const liveURL = "/api/nifty";
const sourceLabel = () => live.active ? live.connected ? "Bot feed connected" : "Bot feed disconnected"
  : isDemo() ? "Demo data" : "Imported snapshot";
const rows = () => marketData()?.signals.filter(signal => signal.horizon === state.horizon) ?? [];
const set = (id, value) => { $(id).textContent = label(value); };

function syncControls() {
  set("source", "◉ " + sourceLabel());
  $("source").dataset.tone = live.connected ? "ok" : "";
  $("feedNotice").hidden = !live.active;
  $("feedNotice").dataset.tone = live.connected
    ? marketData()?.behindSession ? "warning" : "ok" : "";
  set("feedNotice", state.market === "EURUSD" && live.connected
    ? "The bot live feed supplies NIFTY 50. EUR/USD is available through snapshot import."
    : live.status);
  $("market").value = state.market;
  document.querySelectorAll("[data-mode]").forEach(button => {
    button.setAttribute("aria-pressed", button.dataset.mode === state.mode);
  });
  document.querySelectorAll("[data-min]").forEach(button => {
    button.setAttribute("aria-pressed", Number(button.dataset.min) === state.horizon);
  });
}

function render() {
  syncControls();
  if (state.page !== "overview") {
    renderDetail();
    return;
  }
  const data = marketData();
  const candles = data?.candles ?? [];
  const latest = candles.at(-1);
  const inspected = state.mode === "historical";
  const candle = (inspected && candles.find(row => row.time === state.selected)) || latest;
  const recorded = rows().find(row => row.time === candle?.time);
  const analysis = live.active && !inspected
    ? live.connected && candle && data?.current?.[state.horizon] : recorded;
  const signal = analysis?.signal;
  const outcomesAt = candle && iso(Date.parse(candle.time) + state.horizon * 60000);
  $("historical").hidden = !inspected;
  $("history").innerHTML = candles.slice().reverse().map(row =>
    '<option value="' + row.time + '">' + escape(fmt(row.time)) + '</option>').join("");
  $("history").disabled = !candles.length;
  $("history").value = candle?.time ?? "";
  $("signalCard").dataset.tone = !signal ? "neutral" : signal.toLowerCase();
  set("signal", signal ?? "Unavailable");
  set("signalSource", isDemo() ? "Demo analysis" : analysis?.origin === "recorded"
    ? "Recorded Signal" : analysis?.origin === "recomputed" ? "Recomputed Analysis" : live.active ? "Bot feed" : "Imported snapshot");
  set("reason", analysis?.reason || (live.active && state.market === "NIFTY50" && state.horizon === 1
    ? "The connected NIFTY 50 bot does not publish a 1-minute prediction."
    : candle ? "No signal for this candle and horizon." : live.active
      ? "Waiting for completed candles from the connected market."
      : "Load a snapshot for this market."));
  set("close", fmt(candle?.time));
  set("expiry", ["UP", "DOWN"].includes(signal) ? fmt(outcomesAt) : "—");
  set("completed", candle ? "Completed" : "—");
  set("provider", data?.provider ?? "Unavailable");
  set("count", candles.length);
  const ageMinutes = latest ? Math.floor((Date.now() - Date.parse(latest.time)) / 60000) : -1;
  set("age", isDemo() ? "Historical sample" : ageMinutes < 0 ? "—" : ageMinutes < 1
    ? "<1 min" : ageMinutes < 60 ? ageMinutes + " min" : Math.floor(ageMinutes / 60) + " hr");
  set("quality", isDemo() ? "Sample feed" : live.active && !live.connected ? "Disconnected"
    : data?.quality ?? "Quality unknown");
  set("missingLabel", live.active ? "Candle gaps" : "Missing candles");
  set("missing", data?.missing);
  set("chartSubtitle", markets[state.market] + (live.active && state.market === "NIFTY50"
    ? " · 1m candles · Chart times are candle opens (IST)" : " · Completed candles · IST"));
  $("ohlc").hidden = !candle;
  set("ohlc", candle ? ["open", "high", "low", "close"].map(key =>
    key[0].toUpperCase() + " " + price(candle[key])).join("  ·  ") : "");
  set("price", price(candle?.close));
  const indicator = candle?.indicators ?? {};
  $("indicatorList").innerHTML = [
    ["RSI (14)", num(indicator.rsi)], ["MACD", num(indicator.macd, state.market === "EURUSD" ? 6 : 2)],
    ["ATR (14)", price(indicator.atr)], ["EMA 20", price(indicator.ema20)], ["EMA 50", price(indicator.ema50)],
    ["Support", price(indicator.support)], ["Resistance", price(indicator.resistance)]
  ].map(([key, value]) => "<div><dt>" + key + "</dt><dd>" + value + "</dd></div>").join("");
  set("pattern", candle?.pattern);
  drawChart();
}

function drawChart() {
  const canvas = $("chart");
  const { width, height } = canvas.getBoundingClientRect();
  if (!width || !height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.font = "12px system-ui";
  const all = marketData()?.candles ?? [];
  const selected = state.mode === "historical" ? all.findIndex(row => row.time === state.selected) : -1;
  const end = selected < 0 ? all.length : Math.min(all.length, Math.max(60, selected + 8));
  const candles = all.slice(Math.max(0, end - 60), end);
  if (!candles.length) {
    ctx.fillStyle = "#a3b3c9";
    ctx.textAlign = "center";
    ctx.fillText("No completed candles available", width / 2, height / 2);
    return;
  }
  const xEnd = width - 68;
  const yEnd = height - 28;
  const step = (xEnd - 10) / candles.length;
  const x = i => 8 + step * (i + .5);
  const focus = all[selected] ?? all.at(-1);
  const levels = focus.indicators ?? {};
  const dataPoints = candles.flatMap(row => [row.low, row.high, row.indicators?.ema20, row.indicators?.ema50])
    .concat([levels.support, levels.resistance]).filter(finite);
  const low = Math.min(...dataPoints);
  const high = Math.max(...dataPoints);
  const pad = (high - low) * .09 || Math.abs(high) * .001 || 1;
  const y = value => 8 + (high + pad - value) / (high - low + 2 * pad) * (yEnd - 12);

  for (let tick = 0; tick <= 5; tick++) {
    const value = low + (high - low) * tick / 5;
    const yy = y(value);
    ctx.strokeStyle = "#27384c";
    ctx.beginPath(); ctx.moveTo(5, yy); ctx.lineTo(xEnd, yy); ctx.stroke();
    ctx.fillStyle = "#a3b3c9";
    ctx.fillText(price(value), xEnd + 6, yy + 4);
  }
  candles.forEach((row, index) => {
    const xx = x(index);
    const top = y(Math.max(row.open, row.close));
    const bottom = y(Math.min(row.open, row.close));
    const bar = Math.max(1, step * .58);
    const color = row.close >= row.open ? "#71daab" : "#eb7988";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.moveTo(xx, y(row.high)); ctx.lineTo(xx, y(row.low)); ctx.stroke();
    ctx.fillRect(xx - bar / 2, top, bar, Math.max(1, bottom - top));
  });
  for (const [key, color] of [["ema20", "#72e4e1"], ["ema50", "#a79df7"]]) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    let continuing = false;
    candles.forEach((row, index) => {
      const value = row.indicators?.[key];
      if (!finite(value)) {
        continuing = false;
        return;
      }
      if (continuing) ctx.lineTo(x(index), y(value));
      else ctx.moveTo(x(index), y(value));
      continuing = true;
    });
    ctx.stroke();
  }
  ctx.lineWidth = 1;
  ctx.setLineDash([5, 4]);
  ctx.strokeStyle = "#bb9054";
  for (const value of [levels.support, levels.resistance].filter(finite)) {
    ctx.beginPath(); ctx.moveTo(5, y(value)); ctx.lineTo(xEnd, y(value)); ctx.stroke();
  }
  const focusIndex = candles.findIndex(row => row.time === focus.time);
  if (focusIndex >= 0) {
    const xx = x(focusIndex);
    ctx.strokeStyle = "#b5d5e7";
    ctx.beginPath(); ctx.moveTo(xx, 7); ctx.lineTo(xx, yEnd); ctx.stroke();
    ctx.fillStyle = "#e5f6ff";
    ctx.beginPath(); ctx.arc(xx, y(focus.close), 4, 0, Math.PI * 2); ctx.fill();
  }
  ctx.setLineDash([]);
  ctx.fillStyle = "#a3b3c9";
  for (let index = 0; index < candles.length; index += Math.max(1, Math.ceil(candles.length / (width > 470 ? 5 : 3)))) {
    ctx.fillText(clock.format(new Date(candles[index].openTime ?? candles[index].time)), Math.max(5, x(index) - 14), height - 7);
  }
  canvas.onclick = event => {
    const index = Math.floor((event.clientX - canvas.getBoundingClientRect().left - 8) / step);
    if (!candles[index]) return;
    state.mode = "historical";
    state.selected = candles[index].time;
    render();
  };
}

const tone = signal => signal === "UP" ? "up" : signal === "DOWN" ? "down" : signal === "NO TRADE" ? "wait" : "";
const badge = signal => '<strong class="' + tone(signal) + '">' + escape(signal) + '</strong>';
const metric = (title, value) => '<div class="card metric"><span class="eyebrow">' + escape(title) +
  '</span><strong>' + escape(value) + '</strong></div>';
function table(headers, entries, empty) {
  if (!entries.length) return '<p class="empty">' + escape(empty) + '</p>';
  return '<div class="table-wrap"><table><thead><tr>' + headers.map(header =>
    '<th scope="col">' + escape(header) + '</th>').join("") + '</tr></thead><tbody>' + entries.map(entry =>
    '<tr>' + entry.map(cell => '<td>' + cell + '</td>').join("") + '</tr>').join("") + '</tbody></table></div>';
}

const pages = {
  overview: ["Overview", ""],
  journal: ["Signal Journal", "Review signals and the reasons the bot recorded for them."],
  forward: ["Forward Results", "Track pending and resolved directional signals."],
  paper: ["Paper Trading", "Review simulated trade results."],
  health: ["System Health", "Review data quality, test status and project progress."]
};

function renderDetail() {
  const [title, subtitle] = pages[state.page];
  const data = marketData();
  const heading = '<div class="heading"><div><h1>' + title + '</h1><p>' + subtitle + '</p></div></div>';
  const analysisRows = rows().slice().reverse();
  let content;
  if (state.page === "journal") {
    const options = ["", ...signals].map(signal => '<option value="' + signal + '"' +
      (state.filter === signal ? " selected" : "") + '>' + (signal || "All signals") + '</option>');
    content = '<div class="detail-controls"><label for="filter">Signal</label><select id="filter">' + options.join("") +
      '</select></div>' + table(["Candle close (IST)", "Signal", "Reason", "Origin"],
        analysisRows.filter(row => !state.filter || row.signal === state.filter).map(row =>
          [escape(fmt(row.time)), badge(row.signal), escape(row.reason), escape(row.origin)]),
        "No matching signals for this market and horizon.");
  } else if (state.page === "forward") {
    const directional = analysisRows.filter(row => row.signal !== "NO TRADE");
    const tally = outcome => directional.filter(row => row.outcome === outcome).length;
    content = '<div class="metrics">' + outcomes.map(outcome => metric(outcome, tally(outcome))).join("") + '</div>' +
      table(["Candle close (IST)", "Signal", "Outcome check (IST)", "Outcome"], directional.map(row =>
        [escape(fmt(row.time)), badge(row.signal), escape(fmt(iso(Date.parse(row.time) + state.horizon * 60000))),
          escape(row.outcome ?? "Unknown")]), "No directional observations for this market and horizon.");
  } else if (state.page === "paper") {
    const trades = data?.paperTrades ?? [];
    const wins = trades.filter(row => row.result === "WIN").length;
    const losses = trades.filter(row => row.result === "LOSS").length;
    const realized = trades.filter(row => outcomes.slice(0, 3).includes(row.result) && finite(row.profitLoss));
    const pnl = realized.reduce((sum, row) => sum + row.profitLoss, 0);
    content = '<div class="metrics">' + metric("SIMULATED TRADES", trades.length) +
      metric("WIN RATE", wins + losses ? num(100 * wins / (wins + losses), 1) + "%" : "—") +
      metric("REPORTED REALIZED P/L", realized.length ? num(pnl) : "—") + '</div>' +
      table(["Entry time (IST)", "Direction", "Result", "Reported P/L"], trades.map(row =>
        [escape(fmt(row.time)), badge(row.direction), escape(row.result), escape(num(row.profitLoss))]),
        "No paper trades in this snapshot.");
  } else {
    content = '<div class="metrics">' + metric("DATA QUALITY", data?.quality ?? "Unknown") +
      metric("TEST STATUS", state.data.tests ?? "Unavailable") + metric("PROJECT STAGE", state.data.stage ?? "Unavailable") +
      '</div><p class="empty">' + (isDemo() ? "Sample statuses for this demo." : "Statuses reported by the selected data source.") + '</p>';
  }
  const marketOptions = Object.entries(markets).map(([value, name]) => '<option value="' + value + '"' +
    (state.market === value ? ' selected' : '') + '>' + name + '</option>').join("");
  const horizonOptions = horizons.map(horizon => '<option value="' + horizon + '"' +
    (state.horizon === horizon ? ' selected' : '') + '>' + horizon + 'm</option>').join("");
  const controls = '<div class="detail-controls"><label for="detailMarket">Market</label><select id="detailMarket">' +
    marketOptions + '</select>' + (["journal", "forward"].includes(state.page)
      ? '<label for="detailHorizon">Horizon</label><select id="detailHorizon">' + horizonOptions + '</select>' : '') +
    '<span>' + sourceLabel() + '</span></div>';
  $("detail").innerHTML = heading + controls + '<article class="card">' + content + '</article>';
  $("detailMarket").onchange = event => changeMarket(event.target.value, "detailMarket");
  if ($("detailHorizon")) $("detailHorizon").onchange = event => {
    state.horizon = Number(event.target.value);
    render();
    $("detailHorizon").focus();
  };
  if ($("filter")) $("filter").onchange = event => {
    state.filter = event.target.value;
    render();
    $("filter").focus();
  };
}

const validDate = value => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) &&
  Number.isFinite(Date.parse(value));

function normalize(snapshot) {
  const output = { markets: {}, tests: snapshot?.tests, stage: snapshot?.stage };
  for (const symbol of Object.keys(markets)) {
    const data = snapshot?.markets?.[symbol];
    if (!data || !Array.isArray(data.candles)) continue;
    const byTime = new Map();
    for (const row of data.candles) {
      if (!row || row.completed !== true) continue;
      const { open, high, low, close } = row;
      if (!validDate(row.time) || Date.parse(row.time) > Date.now() || ![open, high, low, close].every(finite) ||
          high < Math.max(open, close) || low > Math.min(open, close)) {
        throw new Error("Invalid completed candle for " + markets[symbol] + ".");
      }
      const time = iso(row.time);
      if (byTime.has(time)) throw new Error("Duplicate completed candle for " + markets[symbol] + ".");
      byTime.set(time, { ...row, time });
    }
    const candles = [...byTime.values()].sort((a, b) => a.time.localeCompare(b.time));
    if (!candles.length) continue;
    const signalMap = new Map();
    for (const row of Array.isArray(data.signals) ? data.signals : []) {
      if (!row || !validDate(row.time) || !horizons.includes(row.horizon) || !signals.includes(row.signal)) continue;
      const time = iso(row.time);
      if (!byTime.has(time)) continue;
      const key = time + "/" + row.horizon;
      if (signalMap.has(key)) throw new Error("Duplicate signal for " + markets[symbol] + " and the same horizon.");
      signalMap.set(key, { ...row, time, outcome: outcomes.includes(row.outcome) ? row.outcome : null });
    }
    const paperTrades = (Array.isArray(data.paperTrades) ? data.paperTrades : [])
      .filter(row => row && validDate(row.time) && ["UP", "DOWN"].includes(row.direction));
    output.markets[symbol] = { ...data, candles, signals: [...signalMap.values()].sort((a, b) =>
      a.time.localeCompare(b.time)), paperTrades };
  }
  if (!Object.keys(output.markets).length) throw new Error("No valid completed candles found for NIFTY 50 or EUR/USD.");
  return output;
}

function adaptNiftyFeed(payload, now = Date.now()) {
  if (payload?.market !== "NIFTY 50" || payload?.analysis_only !== true ||
      payload?.execution_enabled !== false || !Array.isArray(payload.candles) || !validDate(payload.checked_at)) {
    throw new Error("The local API response does not match the NIFTY 50 bot feed.");
  }
  const quality = typeof payload.state === "string" ? payload.state : "Unknown";
  const market = { provider: payload.provider || "Upstox", quality, candles: [], signals: [], current: {} };
  market.candleSource = payload.candle_source;
  market.behindSession = payload.behind_session === true;
  const snapshot = { markets: { NIFTY50: market } };
  if (!payload.candles.length) return snapshot;
  market.candles = payload.candles.map(([openTime, open, high, low, close], index) => {
    if (!validDate(openTime)) throw new Error("The bot returned a candle without a timezone.");
    const analysis = payload.candle_analysis?.[index];
    const values = analysis?.indicators ?? {};
    return {
      time: iso(Date.parse(openTime) + 60000), openTime, open, high, low, close, completed: true,
      indicators: {
        rsi: values.RSI_14, ema20: values.EMA_20, ema50: values.EMA_50,
        macd: values.MACD, atr: values.ATR_14, support: values.Support, resistance: values.Resistance
      },
      pattern: analysis?.pattern
    };
  }).sort((a, b) => a.time.localeCompare(b.time));
  const latest = market.candles.at(-1);
  if (!validDate(payload.quality?.latest_completed_close_utc) ||
      iso(payload.quality.latest_completed_close_utc) !== latest.time) {
    throw new Error("The bot did not confirm the latest completed candle.");
  }
  const candleAge = now - Date.parse(latest.time);
  const packetAge = now - Date.parse(payload.checked_at);
  const fresh = quality === "LIVE DATA" && candleAge >= 0 && candleAge <= 120000 &&
    packetAge >= -5000 && packetAge <= 120000;
  market.quality = quality === "LIVE DATA" && !fresh ? "STALE DATA" : quality;
  market.missing = Number.isInteger(payload.quality?.gaps) && payload.quality.gaps >= 0 ? payload.quality.gaps : undefined;
  for (const horizon of [5, 15]) {
    const current = payload.signals?.[horizon];
    if (current && signals.includes(current.label)) {
      market.current[horizon] = {
        signal: fresh ? current.label : "NO TRADE",
        reason: fresh ? current.reason : market.quality
      };
    }
    for (const row of payload.predictions?.[horizon]?.records ?? []) {
      if (!row || !["UP", "DOWN"].includes(row.direction)) continue;
      market.signals.push({ time: row.time, horizon, signal: row.direction, outcome: row.result,
        origin: "recorded", reason: "Paper research observation" });
    }
  }
  const validated = normalize(snapshot);
  return validated;
}

function stopLive() {
  live.active = false;
  live.connected = false;
  clearTimeout(live.timer);
  live.request?.abort();
  live.request = null;
}

async function pollLive() {
  if (!live.active) return;
  const request = new AbortController();
  live.request = request;
  const timeout = setTimeout(() => request.abort(), 8000);
  try {
    const response = await fetch(liveURL, { cache: "no-store", credentials: "omit", signal: request.signal });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "The local API could not read the feed.");
    const snapshot = adaptNiftyFeed(payload);
    if (live.request !== request) return;
    state.data = snapshot;
    live.connected = true;
    const data = snapshot.markets.NIFTY50;
    const lastClose = data.candles.at(-1)?.time;
    const notes = [data.candleSource, data.quality];
    if (lastClose) notes.push("Last candle closed " + fmt(lastClose));
    if (data.behindSession && validDate(payload.expected_close)) {
      notes.push("Feed behind (expected through " + fmt(payload.expected_close) + ")");
    }
    if (payload.refresh_note) notes.push(payload.refresh_note);
    live.status = notes.filter(Boolean).join(" · ");
  } catch (error) {
    if (live.request !== request) return;
    live.connected = false;
    live.status = error instanceof TypeError || error.name === "AbortError"
      ? "Bot feed unreachable. Check that the localhost server is still running."
      : error.message;
  } finally {
    clearTimeout(timeout);
    if (live.request === request) {
      set("liveStatus", live.status);
      render();
      live.timer = setTimeout(pollLive, 30000);
    }
  }
}

function connectLive() {
  stopLive();
  live.active = true;
  live.status = "Connecting to the bot feed…";
  state.data = { markets: {} };
  state.market = "NIFTY50";
  state.horizon = 15;
  state.selected = "";
  state.mode = "latest";
  if ($("dataDialog").open) $("dataDialog").close();
  render();
  pollLive();
}

function changeMarket(value, focusId) {
  state.market = value;
  state.selected = "";
  render();
  if (focusId) $(focusId)?.focus();
}
$("market").onchange = event => changeMarket(event.target.value);
$("horizon").onclick = event => {
  if (!event.target.dataset.min) return;
  state.horizon = Number(event.target.dataset.min);
  render();
};
$("mode").onclick = event => {
  if (!event.target.dataset.mode) return;
  state.mode = event.target.dataset.mode;
  render();
};
$("history").onchange = event => { state.selected = event.target.value; render(); };
document.querySelector("nav").onclick = event => {
  const button = event.target.closest("[data-page]");
  if (!button) return;
  state.page = button.dataset.page;
  document.querySelectorAll("[data-page]").forEach(item => item.removeAttribute("aria-current"));
  button.setAttribute("aria-current", "page");
  $("overview").hidden = state.page !== "overview";
  $("detail").hidden = state.page === "overview";
  set("crumb", pages[state.page][0]);
  render();
};
$("source").onclick = () => $("dataDialog").showModal();
$("connectLive").onclick = connectLive;
$("snapshot").onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const snapshot = normalize(JSON.parse(await file.text()));
    stopLive();
    state.data = snapshot;
    state.selected = "";
    state.mode = "latest";
    if (!marketData()) state.market = Object.keys(snapshot.markets)[0];
    set("importStatus", "Snapshot loaded.");
    render();
    $("dataDialog").close();
  } catch (error) {
    set("importStatus", error.message);
  } finally {
    $("snapshot").value = "";
  }
};
$("reset").onclick = () => {
  stopLive();
  state.data = demo;
  state.selected = "";
  state.mode = "latest";
  set("importStatus", "");
  $("dataDialog").close();
  render();
};
$("sample").onclick = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(demo, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "market-lens-example.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
new ResizeObserver(drawChart).observe($("chart"));
connectLive();
