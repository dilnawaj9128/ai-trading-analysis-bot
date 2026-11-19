"use strict";

const $ = (id) => document.getElementById(id);

const labels = {
  DATA_PROVENANCE_UNVERIFIED: "Market-data origin is unverified",
  FEED_MODE_UNKNOWN: "Market feed mode is unknown",
  BROKER_PRICE_PARITY_UNVERIFIED: "Broker price parity is unverified",
  INDEPENDENT_FORWARD_VALIDATION_PENDING:
    "Independent forward validation is pending",
};

function put(id, value) {
  $(id).textContent = String(value);
}

function pill(id, text, className) {
  const element = $(id);
  element.textContent = text;
  element.className = `pill ${className}`;
}

function resetMetrics() {
  for (const id of [
    "win-rate", "net-pnl", "trades", "drawdown",
    "wins", "losses", "pushes", "resolved",
    "observed", "break-even", "signal-checks",
    "signal-failures", "selection-failures",
  ]) put(id, "—");

  for (const id of ["win-bar", "loss-bar", "push-bar"]) {
    $(id).style.width = "0%";
  }
  put("assessment", "Historical research evidence unavailable.");
}

function percentage(value) {
  return `${Number(value).toFixed(2)}%`;
}

function showStatus(status, signal) {
  put("feed-mode", status.feed_mode || "UNKNOWN");

  // Never turn API availability into market readiness.
  pill("connection", "API ONLINE · FEED OFFLINE", "neutral");

  const safeSignal =
    signal.signal === "NO TRADE" && signal.execution_enabled === false;

  put("signal", safeSignal ? "NO TRADE" : "UNAVAILABLE");
  put("expiry",
      "15 minutes");
  pill("signal-state", "BLOCKED", "warning");

  const reasons = $("reasons");
  reasons.replaceChildren();

  const codes = Array.isArray(signal.reason_codes)
    ? signal.reason_codes : [];

  for (const code of codes) {
    const item = document.createElement("li");
    item.textContent = labels[code] || "An additional safety restriction applies";
    reasons.appendChild(item);
  }

  if (!codes.length) {
    const item = document.createElement("li");
    item.textContent = "No directional signal is authorized";
    reasons.appendChild(item);
  }

  const reports = status.reports || {};
  const s46 = reports.stage46 || {};
  const s47 = reports.stage47 || {};

  pill(
    "stage46",
    s46.valid ? "RECONCILED" : "UNAVAILABLE",
    s46.valid ? "good" : "warning"
  );
  pill(
    "stage47",
    s47.valid ? "CHECKPOINTS PASSED" : "UNAVAILABLE",
    s47.valid ? "good" : "warning"
  );
}

function showResearch(research) {
  const metrics = research.historical_metrics;
  const checks = research.lookahead_checks;

  if (
    research.research_status !== "OFFLINE_AUDITS_AVAILABLE" ||
    !metrics || !checks
  ) {
    resetMetrics();
    pill("research-state", "EVIDENCE INCOMPLETE", "warning");
    return;
  }

  pill("research-state", "OFFLINE AUDITS AVAILABLE", "good");
  put("win-rate", percentage(metrics.win_rate_percent));
  put("observed", percentage(metrics.win_rate_percent));
  put("break-even", percentage(metrics.break_even_win_rate_percent));
  put("net-pnl", Number(metrics.net_units).toFixed(2));
  put("trades", metrics.total_trades);
  put("drawdown", Number(metrics.max_drawdown_units).toFixed(2));
  put("resolved", `${metrics.resolved} resolved trades`);
  put("wins", metrics.wins);
  put("losses", metrics.losses);
  put("pushes", metrics.pushes);
  put("signal-checks", checks.signal_checks);
  put("signal-failures", checks.signal_failures);
  put("selection-failures", checks.selection_failures);

  const total = Number(metrics.total_trades);
  if (total > 0) {
    $("win-bar").style.width = `${100 * metrics.wins / total}%`;
    $("loss-bar").style.width = `${100 * metrics.losses / total}%`;
    $("push-bar").style.width = `${100 * metrics.pushes / total}%`;
  }

  const observed = Number(metrics.win_rate_percent);
  const threshold = Number(metrics.break_even_win_rate_percent);

  put("assessment", observed < threshold
    ? "Historical win rate is below the assumed break-even level. " +
      "No profitable trading edge has been established."
    : "Historical result is not independent evidence of future " +
      "profitability. More validation is required.");
}

async function getJSON(path) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { "Accept": "application/json" },
  });

  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
}

async function refresh() {
  const button = $("refresh");
  button.disabled = true;
  $("error").hidden = true;

  try {
    const [health, status, research, signal] = await Promise.all([
      getJSON("/api/health"),
      getJSON("/api/status"),
      getJSON("/api/research"),
      getJSON("/api/signal"),
    ]);

    if (
      health.status !== "ONLINE" ||
      status.signal_authorized !== false ||
      status.trading_execution_enabled !== false ||
      signal.signal !== "NO TRADE" ||
      signal.execution_enabled !== false ||
      signal.expiry_minutes !== 15
    ) {
      throw new Error("Unexpected backend safety state");
    }

    showStatus(status, signal);
    showResearch(research);
  } catch (error) {
    pill("connection", "API UNAVAILABLE", "bad");
    pill("research-state", "EVIDENCE UNAVAILABLE", "warning");
    pill("stage46", "UNAVAILABLE", "warning");
    pill("stage47", "UNAVAILABLE", "warning");
    put("signal", "NO TRADE");
    put("feed-mode", "UNKNOWN");
    resetMetrics();

    $("reasons").replaceChildren();
    const item = document.createElement("li");
    item.textContent = "Backend unavailable or safety validation failed";
    $("reasons").appendChild(item);

    $("error").hidden = false;
    $("error").textContent =
      "Unable to load trusted research data. " +
      "No signal or performance result will be displayed.";
    console.error("Dashboard request failed:", error);
  } finally {
    button.disabled = false;
  }
}

$("refresh").addEventListener("click", refresh);
refresh();
