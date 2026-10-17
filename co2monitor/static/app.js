"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const REFRESH_MS = 15000;
const RANGE_KEY = "co2monitor.range";

const state = {
  range: loadRange(),
  series: null,
  oracle: null,
  latest: null,
};

// ---------- helpers ----------

function loadRange() {
  try { return localStorage.getItem(RANGE_KEY) || "24h"; } catch { return "24h"; }
}
function saveRange(r) {
  try { localStorage.setItem(RANGE_KEY, r); } catch { /* private mode */ }
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

function svg(tag, attrs = {}, parent = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function html(tag, attrs = {}, parent = null, text = null) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== null) node.textContent = text;
  if (parent) parent.appendChild(node);
  return node;
}

const fmtInt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const fmt1 = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmtCompact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const fmtTime = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
const fmtDay = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const fmtFull = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

function ago(seconds) {
  if (seconds < 90) return `${Math.max(0, Math.round(seconds))} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

function co2Status(ppm) {
  if (ppm < 800) return { level: "good", label: "Fresh", icon: "check" };
  if (ppm < 1200) return { level: "warning", label: "Stuffy", icon: "bang" };
  if (ppm < 2000) return { level: "serious", label: "Ventilate", icon: "bang" };
  return { level: "critical", label: "Leave the room", icon: "cross" };
}

function statusIcon(level, icon) {
  const s = svg("svg", { width: 14, height: 14, viewBox: "0 0 14 14", "aria-hidden": "true" });
  svg("circle", { cx: 7, cy: 7, r: 7, fill: `var(--${level})` }, s);
  const ink = { stroke: "#fff", "stroke-width": 1.8, "stroke-linecap": "round", fill: "none" };
  if (icon === "check") svg("path", { d: "M4 7.2l2 2 4-4.4", ...ink }, s);
  else if (icon === "cross") svg("path", { d: "M4.6 4.6l4.8 4.8M9.4 4.6l-4.8 4.8", ...ink }, s);
  else { svg("path", { d: "M7 3.6v4.2", ...ink }, s); svg("circle", { cx: 7, cy: 10.3, r: 1, fill: "#fff" }, s); }
  return s;
}

function chakraOf(ppm) {
  const bands = state.oracle?.findings.find(f => f.id === "chakra")?.bands;
  if (!bands) return null;
  return bands.find(b => b.upper === null || ppm < b.upper).name;
}

// ---------- scales & ticks ----------

function niceTicks(lo, hi, count) {
  const span = hi - lo || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

const TIME_STEPS = [60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800, 1209600, 2592000];

function timeTicks(start, end, count) {
  const step = TIME_STEPS.find(s => (end - start) / s <= count) || TIME_STEPS.at(-1);
  const ticks = [];
  if (step >= 86400) {
    const d = new Date(start * 1000);
    d.setHours(0, 0, 0, 0);
    while (d.getTime() / 1000 <= end) {
      const t = d.getTime() / 1000;
      if (t >= start) ticks.push(t);
      d.setDate(d.getDate() + step / 86400);
    }
  } else {
    const offset = -new Date(start * 1000).getTimezoneOffset() * 60;
    for (let t = Math.ceil((start + offset) / step) * step - offset; t <= end; t += step) ticks.push(t);
  }
  const daily = step >= 86400;
  const label = t => {
    const d = new Date(t * 1000);
    if (daily) return fmtDay.format(d);
    return d.getHours() === 0 && d.getMinutes() === 0 ? fmtDay.format(d) : fmtTime.format(d);
  };
  return ticks.map(t => ({ t, label: label(t) }));
}

// ---------- line chart ----------

/**
 * rows: [ts, mean, min, max][]; opts: { color, unit, format, refs, retrograde, lunations, describe }
 */
function lineChart(container, rows, opts) {
  container.replaceChildren();
  container.classList.toggle("empty", rows.length === 0);
  if (!rows.length) return;

  const W = container.clientWidth;
  const H = container.clientHeight;
  const m = { top: 22, right: 52, bottom: 26, left: 44 };
  const pw = W - m.left - m.right;
  const ph = H - m.top - m.bottom;
  const { start, end, bucket } = state.series;

  let lo = Math.min(...rows.map(r => r[2]));
  let hi = Math.max(...rows.map(r => r[3]));
  const pad = Math.max((hi - lo) * 0.08, opts.minPad);
  const yt = niceTicks(lo - pad, hi + pad, Math.max(3, Math.round(ph / 56)));
  lo = yt[0]; hi = yt.at(-1);
  const x = t => m.left + ((t - start) / (end - start)) * pw;
  const y = v => m.top + (1 - (v - lo) / (hi - lo)) * ph;

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, tabindex: 0, role: "img", "aria-label": opts.describe(rows) }, container);

  // Mercury retrograde spans sit behind everything.
  const retro = svg("g", { class: "retro" }, root);
  for (const [a, b] of opts.retrograde || []) {
    const x0 = x(a), x1 = x(b);
    svg("rect", { x: x0, y: m.top, width: Math.max(1, x1 - x0), height: ph }, retro);
    if (x1 - x0 > 34) svg("text", { x: x0 + 6, y: m.top + 14, class: "retro-label" }, retro).textContent = "☿ ℞";
  }

  const grid = svg("g", { class: "grid" }, root);
  const axis = svg("g", { class: "axis" }, root);
  for (const v of yt) {
    svg("line", { x1: m.left, x2: m.left + pw, y1: Math.round(y(v)) + 0.5, y2: Math.round(y(v)) + 0.5 }, grid);
    const label = svg("text", { x: m.left - 8, y: y(v) + 4, "text-anchor": "end" }, axis);
    label.textContent = Math.abs(v) >= 10000 ? fmtCompact.format(v) : opts.tick(v);
  }
  svg("line", { class: "baseline", x1: m.left, x2: m.left + pw, y1: m.top + ph + 0.5, y2: m.top + ph + 0.5 }, root);
  const xt = timeTicks(start, end, Math.max(2, Math.floor(pw / 96)));
  for (const { t, label } of xt) {
    const text = svg("text", { x: x(t), y: H - 6, "text-anchor": "middle" }, axis);
    text.textContent = label;
  }

  for (const ref of opts.refs || []) {
    if (ref.value <= lo || ref.value >= hi) continue;
    const g = svg("g", { class: "ref" }, root);
    const yy = Math.round(y(ref.value)) + 0.5;
    svg("line", { x1: m.left, x2: m.left + pw, y1: yy, y2: yy }, g);
    svg("text", { x: m.left + pw - 4, y: yy - 5, "text-anchor": "end" }, g).textContent = ref.label;
  }

  for (const [t, kind] of opts.lunations || []) {
    const c = svg("circle", { cx: x(t), cy: 9, r: 4.5, class: `moon-mark ${kind}` }, root);
    svg("title", {}, c).textContent = `${kind === "full" ? "Full" : "New"} moon, ${fmtFull.format(new Date(t * 1000))}`;
  }

  // Break the line where the recorder was not running.
  const gap = Math.max(bucket * 3, 120);
  const segments = [];
  let seg = [];
  for (const r of rows) {
    if (seg.length && r[0] - seg.at(-1)[0] > gap) { segments.push(seg); seg = []; }
    seg.push(r);
  }
  segments.push(seg);

  for (const s of segments) {
    const band = s.map(r => `${x(r[0])},${y(r[3])}`).concat(s.slice().reverse().map(r => `${x(r[0])},${y(r[2])}`));
    svg("polygon", { points: band.join(" "), fill: opts.color, "fill-opacity": 0.12 }, root);
  }
  for (const s of segments) {
    const d = s.map((r, i) => `${i ? "L" : "M"}${x(r[0]).toFixed(1)},${y(r[1]).toFixed(1)}`).join("");
    svg("path", { d: s.length > 1 ? d : `${d}h0.1`, fill: "none", stroke: opts.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, root);
  }

  const last = rows.at(-1);
  svg("circle", { cx: x(last[0]), cy: y(last[1]), r: 4, fill: opts.color, stroke: "var(--surface-1)", "stroke-width": 2 }, root);
  svg("text", { x: x(last[0]) + 9, y: y(last[1]) + 4, class: "end-label" }, root).textContent = opts.tick(last[1]);

  // Hover & keyboard layer.
  const cross = svg("line", { class: "crosshair", y1: m.top, y2: m.top + ph, visibility: "hidden" }, root);
  const dot = svg("circle", { r: 4.5, fill: opts.color, stroke: "var(--surface-1)", "stroke-width": 2, visibility: "hidden", "pointer-events": "none" }, root);
  const hit = svg("rect", { x: m.left, y: 0, width: pw, height: H, fill: "transparent" }, root);
  let index = rows.length - 1;

  const show = i => {
    index = Math.max(0, Math.min(rows.length - 1, i));
    const r = rows[index];
    const cx = x(r[0]), cy = y(r[1]);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
    dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
    cross.setAttribute("visibility", "visible"); dot.setAttribute("visibility", "visible");
    const box = root.getBoundingClientRect();
    showTooltip(box.left + (cx / W) * box.width, box.top + (cy / H) * box.height, opts.color, opts.format(r[1]), opts.sub(r), fmtFull.format(new Date(r[0] * 1000)));
  };
  const hide = () => {
    cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden");
    hideTooltip();
  };
  const nearest = t => {
    let a = 0, b = rows.length - 1;
    while (b - a > 1) { const mid = (a + b) >> 1; if (rows[mid][0] < t) a = mid; else b = mid; }
    return Math.abs(rows[a][0] - t) < Math.abs(rows[b][0] - t) ? a : b;
  };
  hit.addEventListener("pointermove", e => {
    const box = root.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    show(nearest(start + ((px - m.left) / pw) * (end - start)));
  });
  hit.addEventListener("pointerleave", hide);
  root.addEventListener("focus", () => show(index));
  root.addEventListener("blur", hide);
  root.addEventListener("keydown", e => {
    const step = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowLeft") { show(index - step); e.preventDefault(); }
    else if (e.key === "ArrowRight") { show(index + step); e.preventDefault(); }
    else if (e.key === "Home") { show(0); e.preventDefault(); }
    else if (e.key === "End") { show(rows.length - 1); e.preventDefault(); }
    else if (e.key === "Escape") hide();
  });
}

const tooltip = document.getElementById("tooltip");

function showTooltip(px, py, color, value, sub, time) {
  tooltip.replaceChildren();
  const v = html("div", { class: "t-value" }, tooltip);
  html("i", { style: `background:${color}` }, v);
  v.append(value);
  if (sub) html("div", { class: "t-sub" }, tooltip, sub);
  html("div", { class: "t-time" }, tooltip, time);
  tooltip.hidden = false;
  const w = tooltip.offsetWidth, h = tooltip.offsetHeight;
  let left = px + 14, top = py - h - 12;
  if (left + w > window.innerWidth - 8) left = px - w - 14;
  if (top < 8) top = py + 14;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideTooltip() { tooltip.hidden = true; }

// ---------- rendering ----------

function renderCharts() {
  if (!state.series) return;
  const { series, retrograde, lunations } = state.series;
  const describe = (name, unit) => rows => {
    if (!rows.length) return `${name}: no data`;
    const vals = rows.map(r => r[1]);
    return `${name} from ${fmtFull.format(new Date(rows[0][0] * 1000))}: latest ${fmt1.format(vals.at(-1))} ${unit}, ` +
      `range ${fmt1.format(Math.min(...vals))} to ${fmt1.format(Math.max(...vals))} ${unit}. Use arrow keys to inspect.`;
  };
  const style = getComputedStyle(document.documentElement);

  lineChart(document.getElementById("co2-chart"), series.co2, {
    color: style.getPropertyValue("--series-co2").trim(),
    minPad: 40,
    tick: v => fmtInt.format(v),
    format: v => `${fmtInt.format(v)} ppm`,
    sub: r => {
      const chakra = chakraOf(r[1]);
      const spread = r[2] !== r[3] ? `${fmtInt.format(r[2])}–${fmtInt.format(r[3])} ppm` : null;
      return [spread, chakra && `${chakra} chakra`].filter(Boolean).join(" · ");
    },
    refs: [{ value: 1000, label: "1000 ppm · open a window" }],
    retrograde,
    lunations,
    describe: describe("CO₂", "ppm"),
  });

  lineChart(document.getElementById("temp-chart"), series.temperature, {
    color: style.getPropertyValue("--series-temp").trim(),
    minPad: 0.3,
    tick: v => fmt1.format(v),
    format: v => `${fmt1.format(v)} °C`,
    sub: r => (r[2] !== r[3] ? `${fmt1.format(r[2])}–${fmt1.format(r[3])} °C` : null),
    retrograde,
    describe: describe("Temperature", "°C"),
  });
}

function renderTiles() {
  const { latest, now, count, first_ts, recorder } = state.latest;
  const co2 = latest.co2, temp = latest.temperature, hum = latest.humidity;

  document.getElementById("co2-now").textContent = co2 ? fmtInt.format(co2.value) : "–";
  const pill = document.getElementById("co2-status");
  if (co2) {
    const s = co2Status(co2.value);
    pill.replaceChildren(statusIcon(s.level, s.icon), s.label);
    pill.hidden = false;
  } else pill.hidden = true;

  document.getElementById("temp-now").textContent = temp ? fmt1.format(temp.value) : "–";
  document.getElementById("temp-sub").textContent = temp ? `${fmt1.format(temp.value * 9 / 5 + 32)} °F` : "";
  document.getElementById("hum-tile").hidden = !hum;
  if (hum) document.getElementById("hum-now").textContent = fmtInt.format(hum.value);

  document.getElementById("count").textContent = fmtCompact.format(count);
  document.getElementById("since").textContent = first_ts ? `since ${fmtDay.format(new Date(first_ts * 1000))}` : "";

  const status = document.getElementById("recorder-status");
  const lastTs = Math.max(co2?.ts ?? 0, temp?.ts ?? 0);
  const updated = lastTs ? `last reading ${ago(now - lastTs)}` : "no readings yet";
  status.classList.remove("live", "down");
  if (!recorder) {
    status.textContent = `Dashboard only · ${updated}`;
  } else if (recorder.connected) {
    status.classList.add("live");
    status.textContent = `Recording from ${recorder.device} · ${updated}`;
  } else {
    status.classList.add("down");
    status.textContent = `Not recording: ${recorder.error || "device disconnected"} · ${updated}`;
  }

  const rows = state.series?.series.co2 || [];
  const avg = rows.length ? rows.reduce((a, r) => a + r[1], 0) / rows.length : null;
  document.getElementById("co2-avg").textContent = avg === null ? "–" : fmtInt.format(avg);
  document.getElementById("co2-range").textContent = rows.length
    ? `${fmtInt.format(Math.min(...rows.map(r => r[2])))}–${fmtInt.format(Math.max(...rows.map(r => r[3])))} ppm`
    : "";
}

function renderTable() {
  const table = document.getElementById("data-table");
  table.replaceChildren();
  if (!state.series) return;
  const { series, bucket } = state.series;
  const temps = new Map(series.temperature.map(r => [Math.floor(r[0] / bucket), r[1]]));
  const head = html("tr", {}, html("thead", {}, table));
  for (const h of ["Time", "CO₂ mean (ppm)", "CO₂ min", "CO₂ max", "Temperature (°C)"]) html("th", {}, head, h);
  const body = html("tbody", {}, table);
  for (const r of series.co2.slice().reverse()) {
    const tr = html("tr", {}, body);
    html("td", {}, tr, fmtFull.format(new Date(r[0] * 1000)));
    html("td", {}, tr, fmtInt.format(r[1]));
    html("td", {}, tr, fmtInt.format(r[2]));
    html("td", {}, tr, fmtInt.format(r[3]));
    const t = temps.get(Math.floor(r[0] / bucket));
    html("td", {}, tr, t === undefined ? "–" : fmt1.format(t));
  }
}

function moonSvg(phase) {
  const r = 30;
  const s = svg("svg", { class: "moon-svg", width: 76, height: 76, viewBox: "-38 -38 76 76", "aria-hidden": "true" });
  svg("circle", { r, class: "dark-side" }, s);
  const k = Math.cos(phase * 2 * Math.PI);  // 1 at new moon, -1 at full
  const waxing = phase < 0.5;
  const outer = waxing ? 1 : 0;
  const inner = waxing ? (k > 0 ? 0 : 1) : (k > 0 ? 1 : 0);
  const rx = Math.abs(k) * r;
  svg("path", { class: "lit", d: `M0,${-r}A${r},${r} 0 0 ${outer} 0,${r}A${rx},${r} 0 0 ${inner} 0,${-r}Z` }, s);
  return s;
}

function meter(fraction, scale) {
  const wrap = html("div");
  const m = html("div", { class: "meter" }, wrap);
  html("div", { class: "track" }, m);
  if (scale.center) {
    html("div", { class: "center" }, m);
    html("div", { class: "needle", style: `left:${(fraction * 100).toFixed(1)}%` }, m);
  } else {
    html("div", { class: "fill", style: `width:${(fraction * 100).toFixed(1)}%` }, m);
  }
  const sc = html("div", { class: "meter-scale" }, wrap);
  for (const label of scale.labels) html("span", {}, sc, label);
  return wrap;
}

function sparkline(values) {
  const W = 128, H = 30, pad = 3;
  const s = svg("svg", { class: "spark", width: W, height: H, viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true" });
  const lo = Math.min(...values), hi = Math.max(...values);
  const x = i => pad + (i / Math.max(1, values.length - 1)) * (W - 2 * pad);
  const y = v => (hi === lo ? H / 2 : pad + (1 - (v - lo) / (hi - lo)) * (H - 2 * pad));
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  svg("path", { d, fill: "none", stroke: "var(--oracle-accent)", "stroke-width": 1.5, "stroke-linejoin": "round", "stroke-linecap": "round" }, s);
  svg("circle", { cx: x(values.length - 1), cy: y(values.at(-1)), r: 2.5, fill: "var(--oracle-accent)" }, s);
  return s;
}

const ORACLE_ORDER = ["horoscope", "signals", "aura", "moon", "mercury", "chakra", "zodiac", "schumann", "golden", "numerology"];

function renderOracle() {
  const grid = document.getElementById("oracle");
  grid.replaceChildren();
  if (!state.oracle) return;
  document.getElementById("disclaimer").textContent = state.oracle.disclaimer;
  const findings = [...state.oracle.findings].sort((a, b) => ORACLE_ORDER.indexOf(a.id) - ORACLE_ORDER.indexOf(b.id));

  for (const f of findings) {
    const card = html("article", { class: `oracle-card ${["horoscope", "signals"].includes(f.id) ? "wide" : ""}` }, grid);
    html("h3", {}, card, f.title);
    let figure = null;
    const text = () => {
      const box = html("div");
      html("p", { class: "headline" }, box, f.headline);
      return box;
    };

    if (f.id === "aura") {
      figure = html("div", { class: "figure" }, card);
      html("div", {
        class: "aura-orb",
        style: `background: radial-gradient(circle at 40% 35%, hsl(${f.hue} ${f.saturation}% 88%), hsl(${f.hue} ${f.saturation}% 60% / .85) 45%, hsl(${f.hue} ${f.saturation}% 50% / 0) 72%)`,
        "aria-hidden": "true",
      }, figure);
      figure.append(text());
    } else if (f.id === "moon") {
      figure = html("div", { class: "figure" }, card);
      figure.append(moonSvg(f.phase), text());
    } else if (f.id === "numerology") {
      html("p", { class: "numeral" }, card, f.headline);
    } else {
      card.append(text());
    }

    html("p", { class: "body" }, card, f.body);

    if (f.id === "chakra") {
      const bars = html("div", { class: "bars" }, card);
      const dominant = Math.max(...f.bands.map(b => b.share));
      for (const b of f.bands) {
        const rowClass = b.share === dominant ? "row-dominant" : "";
        const label = html("span", { class: `label ${rowClass}` }, bars, b.name + " ");
        html("small", {}, label, b.upper === null ? "2000+" : `<${b.upper}`);
        const track = html("span", { class: `track ${rowClass}` }, bars);
        if (b.share > 0) html("span", { class: "bar", style: `width:${(b.share / dominant * 100).toFixed(1)}%` }, track);
        html("span", { class: "pct" }, bars, `${Math.round(b.share * 100)}%`);
      }
    } else if (f.id === "zodiac") {
      card.querySelector(".body").remove();
      const rows = html("div", { class: "glyph-rows" }, card);
      for (const s of f.signs) {
        html("span", { class: "glyph", "aria-hidden": "true" }, rows, s.glyph);
        const d = html("span", {}, rows);
        html("span", { class: "sign" }, d, `${s.role} in ${s.sign}`);
        html("div", { class: "why" }, d, s.why);
      }
    } else if (f.id === "signals") {
      const list = html("div", { class: "signals" }, card);
      for (const s of f.signals) {
        const row = html("div", { class: "signal" }, list);
        html("code", { class: "op" }, row, s.op);
        const text = html("div", {}, row);
        html("div", { class: "persona" }, text, s.persona);
        html("div", { class: "reading" }, text, s.reading);
        row.append(sparkline(s.spark));
        const stats = html("div", { class: "signal-stats" }, row);
        html("div", {}, stats, s.min === s.max ? fmtInt.format(s.min) : `${fmtInt.format(s.min)}–${fmtInt.format(s.max)}`);
        const r = s.follows ? s.correlations[s.follows] : null;
        html("div", {}, stats, r === null ? "follows nothing" : `r ${r >= 0 ? "+" : "−"}${Math.abs(r).toFixed(2)}`);
      }
    } else if (f.id === "schumann" && f.cents !== null) {
      card.append(meter((f.cents + 600) / 1200, { center: true, labels: ["600¢ flat", "in tune", "600¢ sharp"] }));
    } else if (f.id === "golden" && f.attainment !== null) {
      card.append(meter(f.attainment, { labels: ["profane", "φ"] }));
    }

    html("p", { class: "certainty" }, card, f.certainty);
  }
}

// ---------- data flow ----------

async function refresh({ rangeChanged = false } = {}) {
  const charts = document.querySelectorAll(".chart");
  if (rangeChanged) charts.forEach(c => c.classList.add("loading"));
  const r = encodeURIComponent(state.range);
  try {
    const [latest, series, oracle] = await Promise.all([
      getJSON("api/latest"),
      getJSON(`api/series?range=${r}`),
      getJSON(`api/oracle?range=${r}`),
    ]);
    Object.assign(state, { latest, series, oracle });
    renderTiles();
    renderCharts();
    renderTable();
    renderOracle();
  } catch (e) {
    const status = document.getElementById("recorder-status");
    status.classList.remove("live");
    status.classList.add("down");
    status.textContent = `Dashboard server unreachable (${e.message})`;
  } finally {
    charts.forEach(c => c.classList.remove("loading"));
  }
}

for (const button of document.querySelectorAll(".ranges button")) {
  button.setAttribute("aria-pressed", String(button.dataset.range === state.range));
  button.addEventListener("click", () => {
    state.range = button.dataset.range;
    saveRange(state.range);
    for (const b of document.querySelectorAll(".ranges button")) b.setAttribute("aria-pressed", String(b === button));
    refresh({ rangeChanged: true });
  });
}

let resizeFrame = 0;
new ResizeObserver(() => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(renderCharts);
}).observe(document.querySelector("main"));
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderCharts);

refresh();
setInterval(refresh, REFRESH_MS);
