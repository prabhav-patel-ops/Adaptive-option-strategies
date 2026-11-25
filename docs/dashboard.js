"use strict";

const byId = id => document.getElementById(id);
const policies = [
  { key: "unhedged", label: "Unhedged", color: "#85d6d4" },
  { key: "daily", label: "Daily", color: "#c6a4ed" },
  { key: "adaptive", label: "Adaptive", color: "#ffca91" },
];
const metrics = {
  pnl: ["Cumulative net P&L", "Historical P&L will appear after an authorized research run."],
  cost: ["Cumulative transaction costs", "Cost comparisons will appear after an authorized research run."],
  drawdown: ["Drawdown from equity peak", "Drawdown comparisons will appear after an authorized research run."],
};
const currency = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});
const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const dayFormat = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
});
const statusFormat = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  hour12: false, timeZone: "Asia/Kolkata",
});
const statusCopy = {
  "awaiting-access": ["Awaiting authorized feed",
    "Research awaits an authorized market-data feed approved for this workflow."],
  private: ["Research results private",
    "Research completed. Public release of derived results is disabled."],
  failed: ["Research refresh failed",
    "The last research refresh failed. Open the workflow run for status."],
  published: ["Historical results published",
    "The latest deployment includes results from validated historical sessions."],
  unavailable: ["Status unavailable",
    "The dashboard could not load the research manifest."],
};
const repo = "https://github.com/prabhav-patel-ops/Adaptive-option-strategies";
const tabs = [...document.querySelectorAll("[data-metric]")];
const performanceChart = byId("performance-chart");
const bandChart = byId("band-chart");
const picker = byId("session-picker");
const gamma = byId("gamma");
const shock = byId("shock");
let displayedMetric = "pnl";
let research = null;
let currentState = "unavailable";
let plot = null;

function canvasFrame(canvas, left) {
  const { width, height } = canvas.getBoundingClientRect();
  if (!width || !height) return null;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.lineJoin = "round";
  context.font = "11px Consolas, monospace";
  return { context, left, right: width - 16, top: 12, bottom: height - 27 };
}

function line(context, x1, y1, x2, y2, color) {
  context.strokeStyle = color;
  context.beginPath();
  context.moveTo(x1, y1);
  context.lineTo(x2, y2);
  context.stroke();
}

function verticalScale(box, low, high, format) {
  const { context, left, right, top, bottom } = box;
  const y = value => bottom - (value - low) / (high - low) * (bottom - top);
  context.textAlign = "right";
  context.textBaseline = "middle";
  for (let index = 0; index <= 4; index++) {
    const value = low + (high - low) * index / 4;
    const gridY = y(value);
    line(context, left, gridY, right, gridY, "#514563");
    context.fillStyle = "#c2b8d5";
    context.fillText(format(value), left - 7, gridY);
  }
  return y;
}

function point(context, x, y, color) {
  context.beginPath();
  context.arc(x, y, 4, 0, 2 * Math.PI);
  context.fillStyle = color;
  context.fill();
}

function drawPerformance() {
  if (!research) return;
  const box = canvasFrame(performanceChart, 67);
  if (!box) return;
  plot = box;
  const { context, left, right, top, bottom } = box;
  const last = research.dates.length - 1;
  const index = Number(picker.value);
  const series = policies.map(policy => research.strategies[policy.key].series[displayedMetric]);
  const values = series.flat();
  let low = Math.min(0, ...values);
  let high = Math.max(0, ...values);
  if (low === high) {
    low = -1;
    high = 1;
  }
  const y = verticalScale(box, low, high, value => compact.format(value));
  const x = value => left + value / last * (right - left);
  context.textAlign = "left";
  context.fillStyle = "#c2b8d5";
  context.fillText(dayFormat.format(new Date(research.dates[0])), left, bottom + 17);
  context.textAlign = "right";
  context.fillText(dayFormat.format(new Date(research.dates[last])), right, bottom + 17);
  line(context, x(index), top, x(index), bottom, "#a98eb7");
  for (const [i, valuesForPolicy] of series.entries()) {
    context.lineWidth = 2.3;
    context.strokeStyle = policies[i].color;
    context.beginPath();
    for (const [session, value] of valuesForPolicy.entries()) {
      if (session === 0) context.moveTo(x(session), y(value));
      else context.lineTo(x(session), y(value));
    }
    context.stroke();
    point(context, x(index), y(valuesForPolicy[index]), policies[i].color);
  }
  const date = dayFormat.format(new Date(research.dates[index]));
  const figures = policies.map((policy, i) => policy.label + " " + currency.format(series[i][index]));
  byId("chart-readout").textContent = [date, ...figures].join(" · ");
  picker.setAttribute("aria-valuetext", date);
}

function drawBand() {
  const selected = Number(gamma.value);
  const stress = Number(shock.value);
  const band = .15;
  const maxGamma = Number(gamma.max);
  const tolerance = value => band / (1 + Math.abs(value * 25_000 * stress) / band);
  byId("gamma-value").value = selected.toFixed(5);
  byId("shock-value").value = (stress * 100).toFixed(2) + "%";
  byId("band-value").value = tolerance(selected).toFixed(4);
  const box = canvasFrame(bandChart, 46);
  if (!box) return;
  const { context, left, right, bottom } = box;
  const y = verticalScale(box, 0, band, value => value.toFixed(3));
  const x = value => left + value / maxGamma * (right - left);
  context.textAlign = "center";
  context.fillStyle = "#c2b8d5";
  for (let index = 0; index <= 4; index++) {
    const value = maxGamma * index / 4;
    context.fillText(value.toFixed(4), x(value), bottom + 17);
  }
  const fill = context.createLinearGradient(0, 12, 0, bottom);
  fill.addColorStop(0, "#ffca913b");
  fill.addColorStop(1, "#ffca9103");
  context.beginPath();
  context.moveTo(left, y(tolerance(0)));
  for (let i = 1; i <= 100; i++) {
    const value = maxGamma * i / 100;
    context.lineTo(x(value), y(tolerance(value)));
  }
  context.lineWidth = 2.5;
  context.strokeStyle = "#ffca91";
  context.stroke();
  context.lineTo(right, bottom);
  context.lineTo(left, bottom);
  context.closePath();
  context.fillStyle = fill;
  context.fill();
  context.lineWidth = 1;
  line(context, x(selected), y(tolerance(selected)), x(selected), bottom, "#c79576");
  point(context, x(selected), y(tolerance(selected)), "#ffe1ad");
}

function renderTable(data) {
  const percent = value => (100 * value).toFixed(2) + "%";
  const rows = [
    ["Net P&L", "pnl", currency.format], ["Total transaction costs", "cost", currency.format],
    ["Futures hedge costs", "hedge_cost", currency.format], ["Futures lots traded", "turnover", value => value.toLocaleString("en-IN")],
    ["Annualized Sharpe", "sharpe", value => value === null ? "—" : value.toFixed(2)],
    ["Maximum drawdown", "max_drawdown", currency.format], ["Maximum drawdown (%)", "max_drawdown_pct", percent],
    ["95% daily VaR", "var_95", currency.format], ["95% daily expected shortfall", "es_95", currency.format],
  ];
  for (const [label, key, format] of rows) {
    const row = document.createElement("tr");
    const header = document.createElement("th");
    header.scope = "row";
    header.textContent = label;
    row.append(header);
    for (const policy of policies) {
      const cell = document.createElement("td");
      cell.textContent = format(data.strategies[policy.key].metrics[key]);
      row.append(cell);
    }
    byId("metrics-body").append(row);
  }
  const tail = data.strategies.adaptive.metrics.tail_observations;
  byId("risk-note").textContent = "Sharpe uses fixed capital and a zero hurdle. The loss tail contains " +
    tail + " of " + data.sessions + " sessions.";
}

function showMetric() {
  byId("chart-title").textContent = metrics[displayedMetric][0];
  if (research) {
    drawPerformance();
    return;
  }
  const empty = byId("empty");
  empty.querySelector("strong").textContent = "No historical series available";
  empty.querySelector("p").textContent = currentState === "awaiting-access"
    ? metrics[displayedMetric][1] : statusCopy[currentState][1];
}

function showStatus(status) {
  currentState = Object.hasOwn(statusCopy, status.state) ? status.state : "unavailable";
  const label = byId("hero-status");
  label.dataset.state = currentState;
  label.replaceChildren(document.createElement("span"), document.createTextNode(statusCopy[currentState][0]));
  byId("run-description").textContent = statusCopy[currentState][1];
  if (status.checked_at && Number.isFinite(Date.parse(status.checked_at))) {
    byId("checked-at").textContent = statusFormat.format(new Date(status.checked_at)) + " IST";
  }
  if (/^\d+$/.test(status.run_id || "")) {
    byId("run-link").href = repo + "/actions/runs/" + status.run_id;
  }
  if (currentState === "published") {
    research = status.research;
    byId("coverage").textContent = [research.from, research.through]
      .map(value => dayFormat.format(new Date(value))).join(" – ");
    byId("session-count").textContent = research.sessions.toLocaleString("en-IN");
    picker.max = research.dates.length - 1;
    picker.value = picker.max;
    renderTable(research);
    byId("empty").hidden = true;
    byId("visual-results").hidden = false;
    byId("metrics").hidden = false;
  }
  showMetric();
}

for (const tab of tabs) {
  tab.addEventListener("click", () => {
    displayedMetric = tab.dataset.metric;
    for (const button of tabs) button.setAttribute("aria-pressed", String(button === tab));
    showMetric();
  });
}
picker.addEventListener("input", drawPerformance);
performanceChart.addEventListener("pointermove", event => {
  if (!plot || event.pointerType === "touch") return;
  const localX = event.clientX - performanceChart.getBoundingClientRect().left;
  const share = (localX - plot.left) / (plot.right - plot.left);
  const index = Math.min(Number(picker.max), Math.max(0, Math.round(share * Number(picker.max))));
  if (index !== Number(picker.value)) {
    picker.value = index;
    drawPerformance();
  }
});
for (const input of [gamma, shock]) input.addEventListener("input", drawBand);
const resize = new ResizeObserver(() => {
  drawBand();
  drawPerformance();
});
resize.observe(bandChart);
resize.observe(performanceChart);
drawBand();
fetch("./research.json", { cache: "no-cache" })
  .then(response => {
    if (!response.ok) throw new Error("Research manifest unavailable");
    return response.json();
  })
  .then(status => {
    if (status.schema !== 1) throw new Error("Unknown manifest schema");
    showStatus(status);
  })
  .catch(() => showStatus({ state: "unavailable" }));
