"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const REFRESH_MS = 15000;
const RANGE_KEY = "aeromancer.range";

const state = {
  range: loadRange(),
  series: null,
  oracle: null,
  kabbalah: null,
  latest: null,
  filter: null,
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

// ---------- stacked line chart ----------

/**
 * Panels stacked on one time axis, one unit per panel.
 * panel: { title, height, series, keys, tick, format, minPad, floor, refs, ticks }
 * series: { label, name, color, rows: [ts, mean, min, max][], band, interval, area }
 *   area: filled down to the axis, behind the lines that follow it
 * opts: { retrograde, lunations, moves, describe }
 */
function stackedChart(container, panels, opts) {
  container.replaceChildren();
  const any = panels.some(p => p.series.some(s => s.rows.length));
  container.classList.toggle("empty", !any);
  if (!any) { container.style.height = ""; return; }

  const TOP = 18, TITLE = 22, GAP = 14, BOTTOM = 26;
  const m = { left: 44, right: 52 };
  const W = container.clientWidth;
  let cursor = TOP;
  const layout = panels.map(p => {
    const top = cursor + TITLE;
    cursor = top + p.height + GAP;
    return { ...p, top, y: null };
  });
  const H = cursor - GAP + BOTTOM;
  container.style.height = `${H}px`;
  const pw = W - m.left - m.right;
  const plotTop = layout[0].top;
  const plotBottom = layout.at(-1).top + layout.at(-1).height;
  const { start, end, bucket } = state.series;
  const x = t => m.left + ((t - start) / (end - start)) * pw;
  // Break a line where its source was not running.
  const gapOf = s => Math.max(bucket * 3, 120, (s.interval || 0) * 2.5);

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, tabindex: 0, role: "img", "aria-label": opts.describe }, container);

  // Mercury retrograde spans sit behind everything.
  const retro = svg("g", { class: "retro" }, root);
  for (const [a, b] of opts.retrograde || []) {
    const x0 = x(a), x1 = x(b);
    for (const p of layout) svg("rect", { x: x0, y: p.top, width: Math.max(1, x1 - x0), height: p.height }, retro);
    if (x1 - x0 > 34) svg("text", { x: x0 + 6, y: plotBottom - 6, class: "retro-label" }, retro).textContent = "☿ ℞";
  }

  const grid = svg("g", { class: "grid" }, root);
  const axis = svg("g", { class: "axis" }, root);
  const marks = svg("g", {}, root);
  const labels = svg("g", {}, root);

  for (const p of layout) {
    const head = html("div", { class: "panel-title", style: `top:${p.top - TITLE}px; left:${m.left}px` }, container);
    html("span", { class: "name" }, head, p.title);
    if (p.keys) {
      for (const s of p.series) {
        const item = html("span", { class: "item" }, head);
        html("span", { class: "key key-line", style: `background:${s.color}` }, item);
        item.append(s.name);
      }
    }
    svg("line", { class: "baseline", x1: m.left, x2: m.left + pw, y1: p.top + p.height + 0.5, y2: p.top + p.height + 0.5 }, root);

    const rows = p.series.flatMap(s => s.rows);
    if (!rows.length) {
      svg("text", { x: m.left + pw / 2, y: p.top + p.height / 2 + 4, "text-anchor": "middle", class: "panel-empty" }, root)
        .textContent = "No readings in this range";
      continue;
    }
    let lo = Math.min(...rows.map(r => r[2]));
    let hi = Math.max(...rows.map(r => r[3]));
    const pad = Math.max((hi - lo) * 0.08, p.minPad);
    const yt = niceTicks(Math.max(p.floor ?? -Infinity, lo - pad), hi + pad, p.ticks ?? Math.max(2, Math.round(p.height / 48)));
    lo = yt[0]; hi = yt.at(-1);
    const y = p.y = v => p.top + (1 - (v - lo) / (hi - lo)) * p.height;

    for (const v of yt) {
      if (v !== lo) svg("line", { x1: m.left, x2: m.left + pw, y1: Math.round(y(v)) + 0.5, y2: Math.round(y(v)) + 0.5 }, grid);
      svg("text", { x: m.left - 8, y: y(v) + 4, "text-anchor": "end" }, axis)
        .textContent = Math.abs(v) >= 10000 ? fmtCompact.format(v) : p.tick(v);
    }
    for (const ref of p.refs || []) {
      if (ref.value <= lo || ref.value >= hi) continue;
      const g = svg("g", { class: "ref" }, root);
      const yy = Math.round(y(ref.value)) + 0.5;
      svg("line", { x1: m.left, x2: m.left + pw, y1: yy, y2: yy }, g);
      svg("text", { x: m.left + pw - 4, y: yy - 5, "text-anchor": "end" }, g).textContent = ref.label;
    }

    const ends = [];
    for (const s of p.series) {
      if (!s.rows.length) continue;
      const segments = [];
      let seg = [];
      for (const r of s.rows) {
        if (seg.length && r[0] - seg.at(-1)[0] > gapOf(s)) { segments.push(seg); seg = []; }
        seg.push(r);
      }
      segments.push(seg);
      if (s.band) {
        for (const g of segments) {
          const band = g.map(r => `${x(r[0])},${y(r[3])}`).concat(g.slice().reverse().map(r => `${x(r[0])},${y(r[2])}`));
          svg("polygon", { points: band.join(" "), fill: s.color, "fill-opacity": 0.12 }, marks);
        }
      }
      if (s.area) {
        const base = p.top + p.height;
        for (const g of segments) {
          const pts = g.map(r => `${x(r[0]).toFixed(1)},${y(r[1]).toFixed(1)}`);
          svg("polygon", { points: [`${x(g[0][0]).toFixed(1)},${base}`, ...pts, `${x(g.at(-1)[0]).toFixed(1)},${base}`].join(" "), fill: s.color, "fill-opacity": 0.14 }, marks);
        }
      }
      for (const g of segments) {
        const d = g.map((r, i) => `${i ? "L" : "M"}${x(r[0]).toFixed(1)},${y(r[1]).toFixed(1)}`).join("");
        svg("path", { d: g.length > 1 ? d : `${d}h0.1`, fill: "none", stroke: s.color, "stroke-width": s.area ? 1 : 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, marks);
      }
      const last = s.rows.at(-1);
      svg("circle", { cx: x(last[0]), cy: y(last[1]), r: 4, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2 }, labels);
      ends.push({ x: x(last[0]), y: y(last[1]), text: p.tick(last[1]) });
    }
    // Value labels at the line ends, unless they would collide; the tooltip has them then.
    ends.sort((a, b) => a.y - b.y);
    if (ends.every((e, i) => !i || e.y - ends[i - 1].y >= 14)) {
      for (const e of ends) svg("text", { x: e.x + 9, y: e.y + 4, class: "end-label" }, labels).textContent = e.text;
    }
  }

  for (const { t, label } of timeTicks(start, end, Math.max(2, Math.floor(pw / 96)))) {
    svg("text", { x: x(t), y: H - 6, "text-anchor": "middle" }, axis).textContent = label;
  }
  // A device was moved here: its readings before and after measure different air.
  const DEVICE_NAMES = { zytemp: "zyTemp", blueair: "Blueair" };
  for (const mv of opts.moves || []) {
    const g = svg("g", { class: "move" }, root);
    const xx = Math.round(x(mv.ts)) + 0.5;
    svg("line", { x1: xx, x2: xx, y1: plotTop, y2: plotBottom }, g);
    const where = mv.spot ? `${mv.room}, ${mv.spot}` : mv.room;
    const left = xx > m.left + pw / 2;  // keep the label inside the plot
    svg("text", { x: left ? xx - 4 : xx + 4, y: plotTop + 12, "text-anchor": left ? "end" : "start", class: "move-label" }, g)
      .textContent = `${DEVICE_NAMES[mv.device] || mv.device} → ${where}`;
  }
  for (const [t, kind] of opts.lunations || []) {
    const c = svg("circle", { cx: x(t), cy: 9, r: 4.5, class: `moon-mark ${kind}` }, root);
    svg("title", {}, c).textContent = `${kind === "full" ? "Full" : "New"} moon, ${fmtFull.format(new Date(t * 1000))}`;
  }

  // Hover & keyboard layer: one crosshair through every panel, one tooltip for every series.
  const cross = svg("line", { class: "crosshair", y1: plotTop, y2: plotBottom, visibility: "hidden" }, root);
  const tracked = layout.flatMap(p => (p.y ? p.series.filter(s => s.rows.length) : []).map(s => ({
    p, s,
    times: s.rows.map(r => r[0]),
    dot: svg("circle", { r: 4.5, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2, visibility: "hidden", "pointer-events": "none" }, root),
  })));
  const hit = svg("rect", { x: m.left, y: 0, width: pw, height: H, fill: "transparent" }, root);
  // Keyboard steps follow the densest series.
  const timeline = tracked.reduce((a, d) => (d.s.rows.length > a.length ? d.s.rows : a), []).map(r => r[0]);
  let index = timeline.length - 1;

  const nearest = (times, t) => {
    let a = 0, b = times.length - 1;
    while (b - a > 1) { const mid = (a + b) >> 1; if (times[mid] < t) a = mid; else b = mid; }
    return Math.abs(times[a] - t) < Math.abs(times[b] - t) ? a : b;
  };
  const show = (t, py) => {
    const cx = x(t);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
    cross.setAttribute("visibility", "visible");
    const lines = [];
    for (const { p, s, times, dot } of tracked) {
      const r = s.rows[nearest(times, t)];
      const near = Math.abs(r[0] - t) <= gapOf(s) / 2;
      dot.setAttribute("visibility", near ? "visible" : "hidden");
      if (!near) continue;
      dot.setAttribute("cx", x(r[0])); dot.setAttribute("cy", p.y(r[1]));
      lines.push({ color: s.color, label: s.label, value: p.format(r[1]) });
    }
    const box = root.getBoundingClientRect();
    showTooltip(box.left + (cx / W) * box.width, box.top + (py / H) * box.height, fmtFull.format(new Date(t * 1000)), lines);
  };
  const showIndex = i => {
    index = Math.max(0, Math.min(timeline.length - 1, i));
    show(timeline[index], plotTop + 40);
  };
  const hide = () => {
    cross.setAttribute("visibility", "hidden");
    for (const { dot } of tracked) dot.setAttribute("visibility", "hidden");
    hideTooltip();
  };
  hit.addEventListener("pointermove", e => {
    const box = root.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const py = ((e.clientY - box.top) / box.height) * H;
    index = nearest(timeline, start + ((px - m.left) / pw) * (end - start));
    show(timeline[index], py);
  });
  hit.addEventListener("pointerleave", hide);
  root.addEventListener("focus", () => showIndex(index));
  root.addEventListener("blur", hide);
  root.addEventListener("keydown", e => {
    const step = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowLeft") { showIndex(index - step); e.preventDefault(); }
    else if (e.key === "ArrowRight") { showIndex(index + step); e.preventDefault(); }
    else if (e.key === "Home") { showIndex(0); e.preventDefault(); }
    else if (e.key === "End") { showIndex(timeline.length - 1); e.preventDefault(); }
    else if (e.key === "Escape") hide();
  });
}

const tooltip = document.getElementById("tooltip");

function showTooltip(px, py, time, lines) {
  tooltip.replaceChildren();
  html("div", { class: "t-time" }, tooltip, time);
  const rows = html("div", { class: "t-rows" }, tooltip);
  for (const l of lines) {
    html("i", { style: `background:${l.color}` }, rows);
    html("span", { class: "t-label" }, rows, l.label);
    html("span", { class: "t-value" }, rows, l.value);
  }
  tooltip.hidden = false;
  const w = tooltip.offsetWidth, h = tooltip.offsetHeight;
  let left = px + 14, top = py - h / 2;
  if (left + w > window.innerWidth - 8) left = px - w - 14;
  top = Math.max(8, Math.min(top, window.innerHeight - h - 8));
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideTooltip() { tooltip.hidden = true; }

// ---------- rendering ----------

const BLUEAIR_INTERVAL = 300;  // seconds between the purifier's uploads
const OUTDOOR_INTERVAL = 3600;  // NEA publishes hourly means, stamped mid-hour
const WEATHER_INTERVAL = 300;  // one point per 5 minutes from the nearest NEA weather station

function renderCharts() {
  if (!state.series) return;
  const { series: s, retrograde, lunations, moves } = state.series;
  const style = getComputedStyle(document.documentElement);
  const color = name => style.getPropertyValue(`--series-${name}`).trim();
  const meter = (label, rows) => ({ label, name: "zyTemp", color: color("meter"), rows, band: true });
  const outdoor = (label, rows) => ({ label, name: "NEA outdoor", color: color("outdoor"), rows: rows || [], interval: WEATHER_INTERVAL });
  const blueair = (label, rows, extra = {}) => ({ label, name: "Blueair", color: color("blueair"), rows, interval: BLUEAIR_INTERVAL, ...extra });
  const int = { tick: v => fmtInt.format(v) };
  const one = { tick: v => fmt1.format(v) };
  const describe = (name, panels) => {
    const parts = panels.flatMap(p => p.series.filter(x => x.rows.length).map(x => `${x.label} ${p.format(x.rows.at(-1)[1])}`));
    return parts.length ? `${name}, latest: ${parts.join(", ")}. Use arrow keys to inspect.` : `${name}: no data`;
  };

  const air = [
    {
      title: "CO₂, ppm", height: 190, minPad: 40, ...int, format: v => `${fmtInt.format(v)} ppm`,
      // In haze, airing trades CO₂ for particles, so the advice changes with the outdoor air.
      refs: [{ value: 1000, label: state.latest?.hazy ? "1000 ppm · haze: thin the crowd" : "1000 ppm · open a window" }],
      series: [meter("CO₂ zyTemp", s.co2)],
    },
    {
      title: "Particles, µg/m³", height: 180, ticks: 5, minPad: 2, floor: 0, keys: true, ...int, format: v => `${fmtInt.format(v)} µg/m³`,
      series: [
        // Outdoor first: a shaded backdrop that the indoor lines sit on.
        { label: "PM2.5 outdoor", name: "PM2.5 outdoor", color: color("outdoor"), rows: s.outdoor_pm25 || [], interval: OUTDOOR_INTERVAL, area: true },
        blueair("PM1", s.blueair_pm1, { name: "PM1", color: color("pm1") }),
        blueair("PM2.5", s.blueair_pm25, { name: "PM2.5" }),
        blueair("PM10", s.blueair_pm10, { name: "PM10", color: color("pm10") }),
      ].filter(x => x.rows.length || !x.area),
    },
    {
      title: "Volatile organic compounds, ppb", height: 100, minPad: 5, floor: 0, ...int, format: v => `${fmtInt.format(v)} ppb`,
      series: [blueair("VOC", s.blueair_voc)],
    },
    {
      title: "Blueair pollution index, %", height: 100, minPad: 2, floor: 0, ...int, format: v => `${fmtInt.format(v)} %`,
      series: [blueair("Pollution index", s.blueair_all_pollution)],
    },
  ];
  document.getElementById("outdoor-key").hidden = !s.outdoor_pm25?.length;
  stackedChart(document.getElementById("air-chart"), air, { retrograde, lunations, moves, describe: describe("Air", air) });

  const climate = [
    {
      title: "Temperature, °C", height: 150, minPad: 0.3, ...one, format: v => `${fmt1.format(v)} °C`,
      series: [meter("Temperature zyTemp", s.temperature), blueair("Temperature Blueair", s.blueair_temperature), outdoor("Temperature outdoor", s.outdoor_temperature)]
        .filter((x, i) => x.rows.length || i < 2),
    },
    {
      title: "Relative humidity, %", height: 110, minPad: 2, ...int, format: v => `${fmtInt.format(v)} %`,
      series: [meter("Humidity zyTemp", s.humidity), blueair("Humidity Blueair", s.blueair_humidity), outdoor("Humidity outdoor", s.outdoor_humidity)].filter(x => x.rows.length),
    },
  ];
  document.getElementById("climate-outdoor-key").hidden = !s.outdoor_temperature?.length && !s.outdoor_humidity?.length;
  stackedChart(document.getElementById("climate-chart"), climate, { retrograde, moves, describe: describe("Climate", climate) });
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

const fmtDate = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" });
const fmtMonth = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short" });
const date = (ts, f = fmtDate) => f.format(new Date(ts * 1000));

const pct = h => `${fmtInt.format(h * 100)} %`;
const span90 = (lo, hi, f = fmtDate) => `90 %: ${date(lo, f)} – ${hi ? date(hi, f) : "never"}`;

// The tile: the last decay test's health and the two replacement dates; the card below the charts: how they were made
// (docs/blueair.md#filter-health).
function renderFilter() {
  const f = state.filter;
  const tile = document.getElementById("filter-tile");
  const card = document.getElementById("filter-card");
  tile.hidden = card.hidden = !f || (f.app_days_left === null && !f.tests.length);
  if (tile.hidden) return;
  const test = f.tests.at(-1);
  const measured = test && "health" in test;
  const fc = f.forecast || {};
  document.getElementById("filter-now").textContent = measured ? fmtInt.format(test.health * 100) : "–";
  document.getElementById("filter-unit").hidden = !measured;
  const dates = [fc.age, fc.caught].filter(d => d?.due).map(d => date(d.due));
  document.getElementById("filter-due").textContent = measured && test.health <= f.replace_at ? "replace now"
    : dates.length ? `replace: ${dates.join(" / ")}`
    : f.app_days_left !== null ? `app: ${f.app_days_left} days left` : "";
  tile.title = "Clean air delivery as a share of a fresh filter's, from the last decay test. "
    + "Replace: the forecast by age / by what it caught. Details below the charts.";

  const grid = document.getElementById("filter-details");
  grid.replaceChildren();
  const block = (title, value, lines) => {
    const b = html("div", { class: "filter-block" }, grid);
    html("h3", {}, b, title);
    html("p", { class: "value" }, b, value);
    for (const line of lines.filter(Boolean)) html("p", { class: "sub" }, b, line);
  };
  const since = f.replaced ? `since the replacement on ${date(f.replaced)}${f.replaced_recorded ? "" : " (from the filter counter)"}` : "";
  if (!test) block("Decay test", "none yet", [`none ${since}`, "how: docs/blueair.md#filter-health"]);
  else if (!measured) block("Last decay test", `${fmt1.format(test.rate)} /h`, [
    `${date(test.start)}, at speed 1`,
    "set room_volume and cadr in the purifier's config to turn it into health",
  ]);
  else block("Last decay test", pct(test.health), [
    `${pct(test.health_low)} – ${test.health_high === null ? "?" : pct(test.health_high)} of a fresh filter (90 %)`,
    `${date(test.start)}: ${fmt1.format(test.rate)} ± ${fmt1.format(test.rate_error)} /h at speed 1, ${test.points} uploads fitted`,
    f.background && `with ${fmt1.format(f.background[0])}–${fmt1.format(f.background[1])} /h lost without the fan`,
    `${f.tests.length} test${f.tests.length === 1 ? "" : "s"} ${since}`,
  ]);
  if (fc.age?.due) block("By age", date(fc.age.due), [
    span90(fc.age.due_early, fc.age.due_late),
    `health = exp(−age / ${fmtInt.format(fc.age.scale)} days); now ~${pct(fc.age.now)}`,
  ]);
  if (fc.caught?.due) block("By what it caught", date(fc.caught.due), [
    span90(fc.caught.due_early, fc.caught.due_late),
    `${fmt1.format(fc.caught_mg / 1000)} g so far, ${fmtInt.format(fc.caught_mg_per_day)} mg a day over the last week`,
    `health = exp(−caught / ${fmt1.format(fc.caught.scale / 1000)} g); now ~${pct(fc.caught.now)}`,
  ]);
  block("The app's timer", f.expired ? "replace" : f.app_days_left === null ? "–" : `${f.app_days_left} days left`, [
    "counts the filter's running time only, 180 days of it",
  ]);
  document.getElementById("filter-note").textContent = f.replace_at
    ? `Replace at ${pct(f.replace_at)} of a fresh filter. One test fits both forecasts alike; repeat it every few weeks, and after haze, to tell them apart.`
    : "";
}

// ---------- the Oracle ----------

// Each household member wears its colour from the charts; the sky wears the Oracle's.
const GROUP_COLORS = { zytemp: "var(--series-meter)", blueair: "var(--series-blueair)", outdoor: "var(--series-outdoor)", sky: "var(--oracle-accent)" };
const GROUP_NAMES = { zytemp: "zyTemp", blueair: "Blueair", outdoor: "Outdoor", sky: "Sky" };
const ELEMENT_COLORS = { Wood: "var(--wood)", Fire: "var(--fire)", Earth: "var(--earth)", Metal: "var(--metal)", Water: "var(--water)" };
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
const HARMONIOUS = new Set(["trine", "sextile"]);

// Where each finding goes: [id, span], span being 1, 2 (columns) or "wide" (the whole row). A "pair"
// section has two equal columns. Anything unlisted lands in a last section.
const ORACLE_SECTIONS = [
  { title: "Today", glyph: "✦", pair: true, cards: [["horoscope"], ["iching"]] },
  { title: "The household", glyph: "⌂", pair: true, cards: [["society"], ["choir"], ["souls"], ["births"], ["signals", "wide"]] },
  { title: "The heavens", glyph: "☉", cards: [["clock", "wide"], ["moon"], ["mercury"], ["zodiac"], ["schumann"]] },
  { title: "The island", glyph: "☴", cards: [["elements", 2], ["winds"], ["ward"]] },
  { title: "Numbers and energies", glyph: "∞", cards: [["aura"], ["chakra"], ["golden"], ["numerology"]] },
];

const signed = (v, digits = 2) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}`;
const cents = c => `${c >= 0 ? "+" : "−"}${Math.abs(Math.round(c))}¢`;
const capitalize = s => s.charAt(0).toUpperCase() + s.slice(1);

function duration(seconds) {
  return seconds >= 5400 ? `${fmt1.format(seconds / 3600)} h` : `${Math.round(seconds / 60)} min`;
}

function headline(f) {
  return html("p", { class: "headline" }, null, f.headline);
}

function bodyText(card, f) {
  html("p", { class: "body" }, card, f.body);
}

// items: [{ key: "dot" | "line" | "dash" | "swatch", color, label }]
function legendRow(parent, items) {
  const row = html("p", { class: "legend figure-legend" }, parent);
  for (const it of items) {
    const item = html("span", { class: "item" }, row);
    html("span", { class: `key key-${it.key}`, style: it.key === "dash" ? `color:${it.color}` : `background:${it.color}` }, item);
    item.append(it.label);
  }
  return row;
}

// The shared tooltip, for a mark that is hovered or focused; ``lines`` may be a function, called when shown.
function hoverTip(el, title, lines) {
  const show = e => {
    const box = el.getBoundingClientRect();
    showTooltip(e?.clientX ?? box.left + box.width / 2, e?.clientY ?? box.top + box.height / 2, title, typeof lines === "function" ? lines() : lines);
  };
  el.addEventListener("pointermove", show);
  el.addEventListener("pointerleave", hideTooltip);
  el.addEventListener("focus", () => show());
  el.addEventListener("blur", hideTooltip);
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

function sparkline(values, W = 128, H = 30) {
  const pad = 3;
  const s = svg("svg", { class: "spark", width: W, height: H, viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true" });
  const lo = Math.min(...values), hi = Math.max(...values);
  const x = i => pad + (i / Math.max(1, values.length - 1)) * (W - 2 * pad);
  const y = v => (hi === lo ? H / 2 : pad + (1 - (v - lo) / (hi - lo)) * (H - 2 * pad));
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  svg("path", { d, fill: "none", stroke: "var(--oracle-accent)", "stroke-width": 1.5, "stroke-linejoin": "round", "stroke-linecap": "round" }, s);
  svg("circle", { cx: x(values.length - 1), cy: y(values.at(-1)), r: 2.5, fill: "var(--oracle-accent)" }, s);
  return s;
}

// ---------- the figures, one per finding ----------

function plainFigure(card, f) {
  card.append(headline(f));
  bodyText(card, f);
}

function auraFigure(card, f) {
  const figure = html("div", { class: "figure" }, card);
  html("div", {
    class: "aura-orb",
    style: `background: radial-gradient(circle at 40% 35%, hsl(${f.hue} ${f.saturation}% 88%), hsl(${f.hue} ${f.saturation}% 60% / .85) 45%, hsl(${f.hue} ${f.saturation}% 50% / 0) 72%)`,
    "aria-hidden": "true",
  }, figure);
  figure.append(headline(f));
  bodyText(card, f);
}

function moonFigure(card, f) {
  const figure = html("div", { class: "figure" }, card);
  figure.append(moonSvg(f.phase), headline(f));
  bodyText(card, f);
}

function numerologyFigure(card, f) {
  html("p", { class: "numeral" }, card, f.headline);
  bodyText(card, f);
}

function chakraFigure(card, f) {
  plainFigure(card, f);
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
}

function zodiacFigure(card, f) {
  card.append(headline(f));
  const rows = html("div", { class: "glyph-rows" }, card);
  for (const s of f.signs) {
    html("span", { class: "glyph", "aria-hidden": "true" }, rows, s.glyph);
    const d = html("span", {}, rows);
    html("span", { class: "sign" }, d, `${s.role} in ${s.sign}`);
    html("div", { class: "why" }, d, s.why);
  }
}

function signalsFigure(card, f) {
  plainFigure(card, f);
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
    html("div", {}, stats, r === null ? "follows nothing" : `r ${signed(r)}`);
  }
}

function schumannFigure(card, f) {
  plainFigure(card, f);
  if (f.cents !== null) card.append(meter((f.cents + 600) / 1200, { center: true, labels: ["600¢ flat", "in tune", "600¢ sharp"] }));
}

function goldenFigure(card, f) {
  plainFigure(card, f);
  if (f.attainment !== null) card.append(meter(f.attainment, { labels: ["profane", "φ"] }));
}

// Mercury's next (or current) retrograde, with the shadows either side of it.
function mercuryFigure(card, f) {
  plainFigure(card, f);
  const { shadow_start: a, retrograde: b, direct: c, shadow_end: d } = f.cycle;
  const now = state.latest?.now ?? Date.now() / 1000;
  const lo = Math.min(now, a) - 2 * 86400, hi = Math.max(now, d) + 2 * 86400;
  const W = 250, y = 18;
  const x = t => 6 + ((t - lo) / (hi - lo)) * (W - 12);
  const day = t => fmtDay.format(new Date(t * 1000));
  const s = svg("svg", { class: "timeline", viewBox: `0 0 ${W} 50`, role: "img", "aria-label": `Shadow from ${day(a)}, retrograde from ${day(b)} to ${day(c)}, shadow until ${day(d)}` }, card);
  svg("rect", { x: 6, y, width: W - 12, height: 6, rx: 3, class: "track" }, s);
  svg("rect", { x: x(a), y, width: x(b) - x(a), height: 6, class: "shadow" }, s);
  svg("rect", { x: x(b), y, width: x(c) - x(b), height: 6, class: "retro" }, s);
  svg("rect", { x: x(c), y, width: x(d) - x(c), height: 6, class: "shadow" }, s);
  [[a, "start", day(a)], [b, "middle", `℞ ${day(b)}`], [c, "middle", `D ${day(c)}`], [d, "end", day(d)]].forEach(([t, anchor, label]) => {
    svg("text", { x: x(t), y: y + 22, "text-anchor": anchor, class: "tick-label" }, s).textContent = label;
  });
  const g = svg("g", { class: "now" }, s);
  svg("line", { x1: x(now), x2: x(now), y1: y - 5, y2: y + 11 }, g);
  svg("text", { x: x(now), y: y - 8, "text-anchor": "middle" }, g).textContent = "now";
  legendRow(card, [
    { key: "swatch", color: "color-mix(in srgb, var(--oracle-accent) 35%, transparent)", label: "shadow" },
    { key: "swatch", color: "var(--oracle-accent)", label: "retrograde" },
  ]);
}

function hexBar(yang, width, height, changing = false) {
  const s = svg("svg", { class: `hex-bar${changing ? " changing" : ""}`, width, height, viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" });
  const gap = Math.round(width * 0.16);
  const parts = yang ? [[0, width]] : [[0, (width - gap) / 2], [(width + gap) / 2, (width - gap) / 2]];
  for (const [x, w] of parts) svg("rect", { x, width: w, height, rx: Math.min(2, height / 3) }, s);
  return s;
}

// Three (or six) lines, given from the bottom, drawn rather than trusted to a font's tiny ☰.
function linesSvg(lines, width, attrs = {}) {
  const bar = Math.max(2, Math.round(width / 6)), gap = Math.max(1.5, Math.round(bar * 0.7)), split = Math.round(width * 0.2);
  const height = lines.length * bar + (lines.length - 1) * gap;
  const s = svg("svg", { class: "lines-svg", width, height, viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true", ...attrs });
  lines.forEach((yang, i) => {
    const y = height - (i + 1) * bar - i * gap;
    const parts = yang ? [[0, width]] : [[0, (width - split) / 2], [(width + split) / 2, (width - split) / 2]];
    for (const [x, w] of parts) svg("rect", { x, y, width: w, height: bar, rx: 1 }, s);
  });
  return s;
}

// The hexagram as cast: top line first, each with whoever cast it.
function ichingFigure(card, f) {
  card.append(headline(f));
  const figure = html("div", { class: "iching" }, card);
  const grid = html("div", { class: "hex-lines", role: "list", "aria-label": "The six lines, from the top" }, figure);
  f.trigrams.forEach((t, k) => {  // lower, then upper
    const tri = html("div", { class: "trigram", style: `grid-row: ${k ? 1 : 4} / span 3`, title: `${t.name}, ${t.image}` }, grid);
    tri.append(linesSvg(t.lines, 24));
    html("span", { class: "tri-name" }, tri, t.image);
  });
  f.lines.forEach((line, i) => {
    const row = `grid-row: ${6 - i}`;
    const bar = hexBar(line.yang, 112, 11, line.changing);
    bar.setAttribute("style", row);
    grid.append(bar);
    html("span", { class: "mark", style: row, title: line.changing ? "a changing line" : "", "aria-hidden": "true" }, grid, line.changing ? (line.yang ? "○" : "×") : "");
    const label = html("span", { class: "line-label", style: row, role: "listitem" }, grid);
    html("span", { class: "who" }, label, line.caster);
    label.append(` ${line.why}`);
    if (line.changing) html("span", { class: "sr-only" }, label, ", a changing line");
  });
  if (f.becomes) {
    const to = html("div", { class: "becomes" }, figure);
    const mini = html("div", { class: "hex-mini", "aria-hidden": "true" }, to);
    for (let i = 5; i >= 0; i--) mini.append(hexBar(f.becomes.lines[i], 36, 5));
    const text = html("div", {}, to);
    html("div", { class: "becomes-label" }, text, "changing into");
    html("div", { class: "becomes-name" }, text, `${f.becomes.number}. ${f.becomes.name}`);
  }
  bodyText(card, f);
}

// Everyone on a circle; a curve for each pair that moves together (or against each other).
function societyFigure(card, f) {
  card.append(headline(f));
  const narrow = card.clientWidth < 480;
  const W = narrow ? 380 : 560, H = narrow ? 300 : 360, cx = W / 2, cy = H / 2, R = narrow ? 92 : 128;
  const s = svg("svg", { class: "network", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": f.body }, card);
  const at = new Map(f.members.map((m, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / f.members.length;
    return [m.id, { m, a, x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) }];
  }));
  const isPair = (pair, e) => pair && pair.includes(e.a) && pair.includes(e.b);
  const edges = svg("g", {}, s), marks = svg("g", {}, s), nodes = svg("g", {}, s);
  const drawn = [];
  for (const e of [...f.edges].reverse()) {  // the strongest on top
    const p = at.get(e.a), q = at.get(e.b);
    const c = { x: cx + ((p.x + q.x) / 2 - cx) * 0.3, y: cy + ((p.y + q.y) / 2 - cy) * 0.3 };  // bowed towards the middle
    const strength = Math.min(1, (Math.abs(e.r) - 0.5) / 0.5);
    const role = isPair(f.soulmates, e) ? "soulmates" : isPair(f.nemeses, e) ? "nemeses" : "";
    const path = svg("path", {
      d: `M${p.x.toFixed(1)},${p.y.toFixed(1)}Q${c.x.toFixed(1)},${c.y.toFixed(1)} ${q.x.toFixed(1)},${q.y.toFixed(1)}`,
      class: `edge ${e.r > 0 ? "friend" : "rival"} ${role}`,
      "stroke-width": (1 + 2.5 * strength).toFixed(2),
      "stroke-opacity": role ? 1 : (0.25 + 0.5 * strength).toFixed(2),
    }, edges);
    drawn.push({ e, path });
    const hit = svg("path", { d: path.getAttribute("d"), class: "edge-hit" }, edges);
    hoverTip(hit, `${p.m.label} and ${q.m.label}`, [{ color: e.r > 0 ? "var(--text-secondary)" : "var(--rival)", label: e.r > 0 ? "move together" : "move apart", value: `r ${signed(e.r)}` }]);
    if (role) {  // a heart for the soulmates, a cross for the nemeses, halfway along their curve
      const mx = 0.25 * p.x + 0.5 * c.x + 0.25 * q.x, my = 0.25 * p.y + 0.5 * c.y + 0.25 * q.y;
      const mark = svg("g", { class: `edge-mark ${role}`, transform: `translate(${mx.toFixed(1)},${my.toFixed(1)})` }, marks);
      svg("circle", { r: 10 }, mark);
      if (role === "soulmates") svg("path", { d: "M0 5.5C-1 4.6-6 1.6-6-1.8-6-3.9-4.5-5.2-2.9-5.2-1.6-5.2-.6-4.4 0-3.4.6-4.4 1.6-5.2 2.9-5.2 4.5-5.2 6-3.9 6-1.8 6 1.6 1 4.6 0 5.5Z" }, mark);
      else svg("path", { d: "M-4-4L4 4M4-4L-4 4" }, mark);
    }
  }
  const nodeEls = new Map();
  for (const [id, p] of at) {
    const ties = f.edges.filter(e => e.a === id || e.b === id).sort((x, y) => Math.abs(y.r) - Math.abs(x.r));
    const g = svg("g", { class: "node", tabindex: 0, "aria-label": `${p.m.label}: ${p.m.friends} friends` }, nodes);
    svg("circle", { cx: p.x, cy: p.y, r: 14, fill: "transparent" }, g);
    svg("circle", { cx: p.x, cy: p.y, r: 6, fill: GROUP_COLORS[p.m.group], stroke: "var(--surface-1)", "stroke-width": 2 }, g);
    const cos = Math.cos(p.a), sin = Math.sin(p.a);
    svg("text", {
      x: p.x + cos * 13, y: p.y + sin * (Math.abs(cos) < 0.3 ? 19 : 13) + 4,
      "text-anchor": cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle", class: "node-label",
    }, g).textContent = p.m.label;
    nodeEls.set(id, g);
    hoverTip(g, p.m.label, () => ties.length
      ? ties.map(e => { const other = at.get(e.a === id ? e.b : e.a).m; return { color: GROUP_COLORS[other.group], label: other.label, value: `r ${signed(e.r)}` }; })
      : [{ color: "var(--text-muted)", label: "talks to no one", value: "" }]);
    const focus = on => {
      s.classList.toggle("focused", on);
      g.classList.toggle("on", on);
      for (const { e, path } of drawn) path.classList.toggle("on", on && (e.a === id || e.b === id));
      for (const e of ties) nodeEls.get(e.a === id ? e.b : e.a).classList.toggle("on", on);
    };
    g.addEventListener("pointerenter", () => focus(true));
    g.addEventListener("pointerleave", () => focus(false));
    g.addEventListener("focus", () => focus(true));
    g.addEventListener("blur", () => focus(false));
  }
  const groups = [...new Set(f.members.map(m => m.group))];
  legendRow(card, [
    ...groups.map(g => ({ key: "dot", color: GROUP_COLORS[g], label: GROUP_NAMES[g] })),
    { key: "line", color: "var(--text-secondary)", label: "together, r ≥ +0.5" },
    { key: "dash", color: "var(--rival)", label: "apart, r ≤ −0.5" },
  ]);
  bodyText(card, f);
}

// The choir, as it sounds. Each leitmotif has its own instrument, shaped by how its guest feels;
// the house sings up close, the world through the glass, both over the Earth's drone.
const choirAudio = { ctx: null, master: null, noise: null, nodes: [], timer: 0, frame: 0, playing: false, start: 0, spb: 1 };
const NOTE_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
const THEME_NAMES = {
  breath: "the Breath", warmth: "the Warmth", damp: "the Damp", dust: "the Dust", vapour: "the Vapours",
  ground: "the Ground", haze: "the Haze", harp: "the Aeolian harp", rain: "the Rain", chord: "the cadence",
};
const THEME_SOUNDS = {
  breath: "swells like a lung",
  warmth: "shimmers more as it gets hotter",
  damp: "echoes more as the air gets wetter",
  dust: "plucked, and gritty with its particles",
  vapour: "two reeds that beat against each other as the VOCs rise",
  ground: "a ground bass, a pulse for each step of the fan",
  haze: "a low drone, hissing with its particles",
  harp: "the harmonics of the tonic, plucked by the wind",
  rain: "a drop for every two-thirds of a millimetre an hour",
  chord: "each side's home chord, in its own mode",
};
const hzOf = midi => 440 * 2 ** ((midi - 69) / 12);

function noteName(midi) {
  const m = Math.round(midi), off = (midi - m) * 100;
  return `${NOTE_NAMES[((m % 12) + 12) % 12]}${Math.floor(m / 12) - 1}${Math.abs(off) >= 1 ? ` ${cents(off)}` : ""}`;
}

function setListening(playing) {
  choirAudio.playing = playing;
  for (const b of document.querySelectorAll(".listen")) {
    b.textContent = playing ? "■ Stop" : "▶ Listen";
    b.setAttribute("aria-pressed", String(playing));
  }
  if (!playing) for (const p of document.querySelectorAll(".score .playhead")) p.setAttribute("visibility", "hidden");
}

function stopChoir() {
  const { ctx, master } = choirAudio;
  if (ctx && master) {
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.setTargetAtTime(0, ctx.currentTime, 0.06);
    for (const n of choirAudio.nodes) n.stop(ctx.currentTime + 0.4);
  }
  choirAudio.nodes = [];
  clearTimeout(choirAudio.timer);
  cancelAnimationFrame(choirAudio.frame);
  setListening(false);
}

// The playhead, on whichever copy of the score is on the page now: the Oracle redraws its cards.
function followChoir() {
  const { ctx, start, spb } = choirAudio;
  const beat = (ctx.currentTime - start) / spb;
  for (const p of document.querySelectorAll(".score .playhead")) {
    const x = Math.min(Number(p.dataset.width), Math.max(0, beat * Number(p.dataset.perBeat)));
    p.setAttribute("transform", `translate(${x.toFixed(1)},0)`);
    p.setAttribute("visibility", beat >= 0 ? "visible" : "hidden");
  }
  if (choirAudio.playing) choirAudio.frame = requestAnimationFrame(followChoir);
}

function noiseBuffer(ctx) {
  if (choirAudio.noise?.sampleRate === ctx.sampleRate) return choirAudio.noise;
  const buffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  return (choirAudio.noise = buffer);
}

// A hall to sing in: two seconds of decaying noise.
function reverb(ctx, seconds) {
  const conv = ctx.createConvolver(), len = Math.round(ctx.sampleRate * seconds);
  const ir = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let c = 0; c < 2; c++) {
    const data = ir.getChannelData(c);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 2.5;
  }
  conv.buffer = ir;
  return conv;
}

function playChoir(f) {
  stopChoir();
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) return;
  const ctx = (choirAudio.ctx ||= new Context());
  ctx.resume();
  const spb = 60 / f.tempo.bpm, release = 2.4;
  const start = ctx.currentTime + 0.1, end = start + f.beats * spb;
  Object.assign(choirAudio, { start, spb });
  const stopAt = end + release + 0.2;
  const keep = n => (choirAudio.nodes.push(n), n);

  const master = (choirAudio.master = ctx.createGain());
  const soften = ctx.createBiquadFilter();
  soften.type = "lowpass";
  soften.frequency.value = 6000;
  const limit = ctx.createDynamicsCompressor();
  master.connect(soften).connect(limit).connect(ctx.destination);
  master.gain.setValueAtTime(0.0001, start);
  master.gain.exponentialRampToValueAtTime(0.9, start + 0.3);
  master.gain.setValueAtTime(0.9, end);
  master.gain.exponentialRampToValueAtTime(0.0001, end + release);
  const hall = reverb(ctx, 2.6);
  hall.connect(master);

  // Each side's air colours everything it sings: heavy air is muffled, and the world is heard through the glass.
  const airs = Object.fromEntries(f.airs.map(a => [a.id, a]));
  const buses = {};
  for (const where of ["inside", "outside"]) {
    const d = airs[where]?.distress ?? 0, outside = where === "outside";
    const tone = ctx.createBiquadFilter();
    tone.type = "lowpass";
    tone.frequency.value = (outside ? 500 + 2300 * (1 - d) : 700 + 5000 * (1 - d) ** 1.5);
    tone.Q.value = 0.5;
    const gain = ctx.createGain();
    gain.gain.value = outside ? 0.7 : 1;
    const wet = ctx.createGain();
    wet.gain.value = outside ? 0.45 : 0.15;
    tone.connect(gain).connect(master);
    gain.connect(wet).connect(hall);
    buses[where] = tone;
  }

  const n = f.themes.filter(t => t.notes.length).length;
  const level = 0.5 / Math.max(3, Math.sqrt(n) * 2);
  const env = (g, at, attack, hold, decay, peak) => {
    g.gain.setValueAtTime(0, at);
    g.gain.linearRampToValueAtTime(peak, at + attack);
    g.gain.setValueAtTime(peak, at + attack + hold);
    g.gain.exponentialRampToValueAtTime(0.0001, at + attack + hold + decay);
    return at + attack + hold + decay + 0.05;
  };
  const osc = (type, hz, at, until, out) => {
    const o = keep(ctx.createOscillator());
    o.type = type;
    o.frequency.value = hz;
    o.connect(out);
    o.start(at);
    o.stop(Math.min(until, stopAt));
    return o;
  };
  const noise = (at, until, out) => {
    const s = keep(ctx.createBufferSource());
    s.buffer = noiseBuffer(ctx);
    s.loop = true;
    s.connect(out);
    s.start(at, Math.random());
    s.stop(Math.min(until, stopAt));
    return s;
  };

  const instruments = {
    breath(hz, at, dur, peak, out) {
      const g = ctx.createGain();
      g.connect(out);
      const until = env(g, at, dur * 0.45, dur * 0.1, dur * 0.6, peak);
      osc("sine", hz, at, until, g);
      const h = ctx.createGain();
      h.gain.value = 0.18;
      h.connect(g);
      osc("triangle", hz * 2, at, until, h);
    },
    warmth(hz, at, dur, peak, out, t) {
      const g = ctx.createGain();
      g.connect(out);
      const until = env(g, at, 0.06, dur * 0.7, 0.35, peak);
      const o = osc("triangle", hz, at, until, g);
      const lfo = keep(ctx.createOscillator()), depth = ctx.createGain();
      lfo.frequency.value = 5.5;
      depth.gain.value = hz * (2 ** ((4 + 30 * (t.distress ?? 0)) / 1200) - 1);  // heat shimmers
      lfo.connect(depth).connect(o.frequency);
      lfo.start(at);
      lfo.stop(Math.min(until, stopAt));
    },
    damp(hz, at, dur, peak, out, t) {
      const g = ctx.createGain();
      g.connect(out);
      const until = env(g, at, 0.3, dur * 0.6, dur * 0.5, peak);
      osc("sine", hz, at, until, g);
      const echo = ctx.createDelay(2), back = ctx.createGain();
      echo.delayTime.value = spb * 0.75;
      back.gain.value = 0.2 + 0.55 * Math.min(1, (t.value ?? 60) / 100);  // wetter air, longer echoes
      g.connect(echo).connect(back).connect(echo);
      back.connect(out);
    },
    dust(hz, at, dur, peak, out, t) {
      const g = ctx.createGain();
      g.connect(out);
      osc("triangle", hz, at, env(g, at, 0.005, 0, 0.3, peak), g);
      const grit = ctx.createBiquadFilter();
      grit.type = "bandpass";
      grit.frequency.value = 3500;
      grit.Q.value = 1.5;
      grit.connect(out);
      const grains = 1 + Math.round(4 * (t.distress ?? 0));  // the more particles, the more grit
      for (let i = 0; i < grains; i++) {
        const gg = ctx.createGain(), when = at + Math.random() * dur * 2;
        gg.connect(grit);
        noise(when, env(gg, when, 0.002, 0, 0.03, peak * 0.9), gg);
      }
    },
    vapour(hz, at, dur, peak, out, t) {
      const g = ctx.createGain(), dull = ctx.createBiquadFilter();
      dull.type = "lowpass";
      dull.frequency.value = 1400;
      g.connect(dull).connect(out);
      const until = env(g, at, dur * 0.3, dur * 0.4, dur * 0.5, peak * 0.6);
      const spread = 3 + 30 * (t.distress ?? 0);  // VOCs beat against each other
      for (const c of [-spread, spread]) osc("sawtooth", hz * 2 ** (c / 1200), at, until, g);
    },
    ground(hz, at, dur, peak, out) {
      const g = ctx.createGain(), dull = ctx.createBiquadFilter();
      dull.type = "lowpass";
      dull.frequency.value = 600;
      g.connect(dull).connect(out);
      osc("square", hz, at, env(g, at, 0.01, dur * 0.4, dur * 0.5, peak * 0.7), g);
    },
    haze(hz, at, dur, peak, out, t) {
      const g = ctx.createGain(), dull = ctx.createBiquadFilter();
      dull.type = "lowpass";
      dull.frequency.value = 450;
      g.connect(dull).connect(out);
      const until = env(g, at, dur * 0.4, dur * 0.3, dur * 0.6, peak);
      osc("sawtooth", hz, at, until, g);
      const hiss = ctx.createGain(), band = ctx.createBiquadFilter();
      band.type = "bandpass";
      band.frequency.value = hz * 6;
      band.Q.value = 0.8;
      hiss.connect(band).connect(out);
      noise(at, env(hiss, at, dur * 0.4, dur * 0.3, dur * 0.6, peak * 1.6 * (t.distress ?? 0)), hiss);
    },
    harp(hz, at, dur, peak, out) {
      const g = ctx.createGain(), pan = ctx.createStereoPanner();
      pan.pan.value = Math.random() * 1.6 - 0.8;
      g.connect(pan).connect(out);
      osc("sine", hz, at, env(g, at, 0.01, 0, dur, peak), g);
    },
    rain(hz, at, dur, peak, out) {
      const g = ctx.createGain(), pan = ctx.createStereoPanner();
      pan.pan.value = Math.random() * 1.8 - 0.9;
      g.connect(pan).connect(out);
      const o = osc("sine", hz, at, env(g, at, 0.002, 0, 0.14, peak), g);
      o.frequency.setValueAtTime(hz * 1.06, at);
      o.frequency.exponentialRampToValueAtTime(hz, at + 0.05);  // a drop lands, and settles
    },
    chord(hz, at, dur, peak, out) {
      const g = ctx.createGain();
      g.connect(out);
      const until = env(g, at, 0.5, dur - 0.5, release, peak);
      osc("sine", hz, at, until, g);
      const h = ctx.createGain();
      h.gain.value = 0.25;
      h.connect(g);
      osc("triangle", hz, at, until, h);
    },
  };
  // The Earth hums two octaves below its note, trembling at its own 7.83 Hz.
  const drone = ctx.createGain();
  drone.connect(master);
  env(drone, start, 1.5, f.beats * spb - 1.5, release, level * 0.45);  // under the choir, not over it
  osc("sine", f.earth.hz / 4, start, stopAt, drone);
  const depth = ctx.createGain();
  depth.gain.value = level * 0.15;
  depth.connect(drone.gain);
  osc("sine", 7.83, start, stopAt, depth);

  f.themes.forEach((t, i) => {
    const pan = ctx.createStereoPanner();
    const spread = t.layer === "outside" ? 0.7 : 0.3;
    pan.pan.value = n > 1 ? -spread + (2 * spread * (i % n)) / (n - 1) : 0;
    pan.connect(buses[t.layer]);
    for (const [beat, midi, beats, loud] of t.notes) instruments[t.theme](hzOf(midi), start + beat * spb, beats * spb, level * loud, pan, t);
  });
  setListening(true);
  choirAudio.frame = requestAnimationFrame(followChoir);
  choirAudio.timer = setTimeout(stopChoir, (stopAt - ctx.currentTime) * 1000 + 300);
}

// Inside against outside, each a third clear, middling or heavy, with the mood of every pairing.
const MOOD_GRID = [["Serenade", "Pastorale", "Sanctuary"], ["Invitation", "Nocturne", "Vigil"], ["Longing", "Lament", "Dirge"]];

function moodMap(f) {
  const inside = f.airs.find(a => a.id === "inside"), outside = f.airs.find(a => a.id === "outside");
  const cell = 62, left = 20, top = 16, W = left + 3 * cell + 2, H = top + 3 * cell + 4;
  const s = svg("svg", { class: "mood-map", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Mood: ${f.mood}, from the air inside and outside` });
  svg("text", { x: left + 1.5 * cell, y: 10, "text-anchor": "middle", class: "axis-label" }, s).textContent = "outside: clear → heavy";
  svg("text", { x: 10, y: top + 1.5 * cell, "text-anchor": "middle", class: "axis-label", transform: `rotate(-90 10 ${top + 1.5 * cell})` }, s).textContent = "inside: clear → heavy";
  MOOD_GRID.forEach((row, r) => row.forEach((name, c) => {
    const on = name === f.mood;
    svg("rect", { x: left + c * cell + 1, y: top + r * cell + 1, width: cell - 2, height: cell - 2, rx: 6, class: on ? "mood-cell on" : "mood-cell" }, s);
    svg("text", { x: left + (c + 0.5) * cell, y: top + (r + 0.5) * cell + 4, "text-anchor": "middle", class: on ? "mood-name on" : "mood-name" }, s).textContent = name;
  }));
  const dot = svg("g", { class: "mood-dot", tabindex: 0 }, s);
  svg("circle", { cx: left + outside.distress * 3 * cell, cy: top + inside.distress * 3 * cell, r: 6 }, dot);
  hoverTip(dot, f.mood, [
    { color: GROUP_COLORS.zytemp, label: `inside, ${inside.band_name}`, value: `${Math.round(inside.distress * 100)}% heavy` },
    { color: GROUP_COLORS.outdoor, label: `outside, ${outside.band_name}`, value: `${Math.round(outside.distress * 100)}% heavy` },
  ]);
  return s;
}

function airPanel(a) {
  const box = html("div", { class: "air" });
  const title = html("p", { class: "air-title" }, box);
  html("b", {}, title, a.id === "inside" ? "The house" : "The world");
  title.append(` sings in ${a.key}`);
  for (const x of a.factors) {
    const row = html("div", { class: `air-row${x.id === a.worst ? " worst" : ""}` }, box);
    html("span", { class: "air-label" }, row, x.label);
    const bar = html("span", { class: "air-bar" }, row);
    html("i", { style: `width:${Math.max(2, x.distress * 100).toFixed(0)}%;background:${GROUP_COLORS[x.group]}` }, bar);
    const digits = ["°C", "m/s", "mm/h"].includes(x.unit) ? 1 : 0;
    html("span", { class: "air-value" }, row, `${x.value.toFixed(digits)}${x.unit === "%" ? "%" : ` ${x.unit}`}`);
  }
  return box;
}

// The score as a piano roll: every leitmotif's notes in time, by pitch, in its guest's colour.
function scoreSvg(f) {
  const W = 560, H = 190, m = { left: 30, right: 6, top: 18, bottom: 8 };
  const notes = f.themes.flatMap(t => t.notes.map(n => ({ t, beat: n[0], midi: n[1], beats: n[2], loud: n[3] })));
  const lo = Math.floor(Math.min(...notes.map(n => n.midi)) / 12) * 12, hi = Math.ceil((Math.max(...notes.map(n => n.midi)) + 1) / 12) * 12;
  const perBeat = (W - m.left - m.right) / f.beats;
  const x = b => m.left + b * perBeat;
  const y = midi => m.top + (1 - (midi - lo) / (hi - lo)) * (H - m.top - m.bottom);
  const row = Math.max(2.5, Math.min(6, (H - m.top - m.bottom) / (hi - lo)));
  const s = svg("svg", { class: "score", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `The score: ${f.themes.length} leitmotifs over ${f.beats} beats at ${f.tempo.bpm} a minute` });
  f.sections.forEach((sec, i) => {
    svg("rect", { x: x(sec.start), y: m.top, width: (sec.end - sec.start) * perBeat, height: H - m.top - m.bottom, class: i % 2 ? "section odd" : "section" }, s);
    svg("text", { x: x(sec.start) + 4, y: 11, class: "section-label" }, s).textContent = sec.label;
  });
  svg("text", { x: x(f.beats - 4) + 4, y: 11, class: "section-label" }, s).textContent = "Cadence";
  for (let c = lo; c <= hi; c += 12) {
    svg("line", { x1: m.left, x2: W - m.right, y1: Math.round(y(c)) + 0.5, y2: Math.round(y(c)) + 0.5, class: "grid-line" }, s);
    svg("text", { x: m.left - 5, y: y(c) + 3.5, "text-anchor": "end", class: "tick" }, s).textContent = `C${c / 12 - 1}`;
  }
  for (const nt of notes) {
    const g = svg("g", { class: "note", tabindex: -1 }, s);
    svg("rect", {
      x: x(nt.beat), y: y(nt.midi) - row / 2, width: Math.max(2.5, Math.min(nt.beats, f.beats - nt.beat) * perBeat - 1), height: row, rx: Math.min(2, row / 2),
      fill: GROUP_COLORS[nt.t.group], "fill-opacity": (0.35 + 0.65 * nt.loud).toFixed(2),
    }, g);
    hoverTip(g, `${nt.t.label}: ${THEME_NAMES[nt.t.theme]}`, [
      { color: GROUP_COLORS[nt.t.group], label: noteName(nt.midi), value: `beat ${fmt1.format(nt.beat + 1)}` },
      { color: "transparent", label: THEME_SOUNDS[nt.t.theme], value: "" },
    ]);
  }
  svg("line", { x1: x(0), x2: x(0), y1: m.top - 4, y2: H - m.bottom, class: "playhead", visibility: "hidden", "data-per-beat": perBeat, "data-width": f.beats * perBeat }, s);
  return s;
}

function choirFigure(card, f, header) {
  const button = html("button", { class: "listen", type: "button", "aria-pressed": "false" }, header);
  button.addEventListener("click", () => (choirAudio.playing ? stopChoir() : playChoir(f)));
  setListening(choirAudio.playing);
  card.append(headline(f));
  const keys = f.airs.map(a => `${a.id === "inside" ? "the house" : "the world"} in ${a.key}`);
  html("p", { class: "mood-facts" }, card, `${f.tempo.marking}, ${f.tempo.bpm} beats a minute · ${keys.join(" against ")}`);
  const row = html("div", { class: "mood-row" }, card);
  if (f.airs.length === 2) row.append(moodMap(f));
  const panels = html("div", { class: "airs" }, row);
  for (const a of f.airs) if (a.factors.length) panels.append(airPanel(a));
  card.append(scoreSvg(f));
  const list = html("ul", { class: "voices", "aria-label": "Leitmotifs" }, card);
  for (const t of f.themes) {
    if (t.theme === "chord" || !t.notes.length) continue;
    const li = html("li", { title: THEME_SOUNDS[t.theme] }, list);
    html("i", { style: `background:${GROUP_COLORS[t.group]}` }, li);
    li.append(`${t.label} `);
    html("b", {}, li, THEME_NAMES[t.theme]);
  }
  bodyText(card, f);
}

// A soul is a ghost; part of a soul is a ghost filled part of the way.
const GHOST = "M1 23V10a9 9 0 0 1 18 0v13l-3-2.4-3 2.4-3-2.4-3 2.4-3-2.4z";

function ghosts(n, prefix = "soul") {
  const row = html("div", { class: "ghosts", "aria-hidden": "true" });
  if (n === null) return row;
  const count = Math.min(6, Math.ceil(Math.abs(n)));
  for (let i = 0; i < count; i++) {
    const full = Math.max(0, Math.min(1, Math.abs(n) - i));
    const s = svg("svg", { width: 30, height: 36, viewBox: "0 0 20 24", class: `ghost${n < 0 ? " inverted" : ""}`, style: `animation-delay:${-i * 0.7}s` }, row);
    const clip = svg("clipPath", { id: `${prefix}-${i}` }, svg("defs", {}, s));
    svg("rect", { x: 0, y: 24 * (1 - full), width: 20, height: 24 * full }, clip);
    svg("path", { d: GHOST, class: "outline" }, s);
    svg("path", { d: GHOST, class: "body", "clip-path": `url(#${prefix}-${i})` }, s);
    for (const x of [7, 13]) svg("circle", { cx: x, cy: 10, r: 1.6, class: full > 0.6 ? "eye lit" : "eye" }, s);
  }
  if (Math.abs(n) > 6) html("span", { class: "more" }, row, `+${Math.round(Math.abs(n) - 6)}`);
  return row;
}

function soulsFigure(card, f) {
  card.append(ghosts(f.souls), headline(f));
  bodyText(card, f);
  if (f.spark.length > 1) {
    const row = html("div", { class: "spark-row" }, card);
    row.append(sparkline(f.spark, 220, 40));
    html("span", {}, row, `souls over the window, from ${fmt1.format(Math.min(...f.spark))} to ${fmt1.format(Math.max(...f.spark))}`);
  }
}

function rhythmBar(r) {
  const W = 36, H = 12;
  const s = svg("svg", { class: `rhythm${r.critical ? " critical" : ""}`, width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${r.cycle} ${Math.round(r.value * 100)}%${r.critical ? ", a critical day" : ""}` });
  svg("rect", { y: H / 2 - 1, width: W, height: 2, rx: 1, class: "track" }, s);
  const w = Math.max(1.5, Math.abs(r.value) * (W / 2));
  svg("rect", { x: r.value >= 0 ? W / 2 : W / 2 - w, y: 2, width: w, height: H - 4, rx: 2, class: "bar" }, s);
  svg("rect", { x: W / 2 - 0.5, width: 1, height: H, class: "zero" }, s);
  return s;
}

function birthsFigure(card, f) {
  card.append(headline(f));
  const table = html("div", { class: "births" }, card);
  for (const label of ["", "", "phys.", "emot.", "intel."]) html("span", { class: "births-head" }, table, label);
  for (const m of f.members) {
    html("span", { class: "sign-glyph", title: m.sign, "aria-hidden": "true" }, table, m.glyph);
    const who = html("span", { class: "member" }, table);
    html("span", { class: "member-name" }, who, capitalize(m.name));
    html("small", {}, who, `${fmtDay.format(new Date(m.born * 1000))} · ${m.sign} · ${m.element} ${m.animal}`);
    for (const r of m.rhythms) table.append(rhythmBar(r));
  }
  bodyText(card, f);
}

// A day as an astrological wheel, by solar time: noon at the top, sunrise on the left, as the Sun moves.
function clockFigure(card, f) {
  card.append(headline(f));
  const wrap = html("div", { class: "clock" }, card);
  const S = 400, c = S / 2;
  const R = { out: 172, hours: 148, houses: 124, orbit: 104, core: 22 };
  const s = svg("svg", { class: "wheel", viewBox: `-36 0 ${S + 72} ${S}`, role: "img", "aria-label": `A day as a wheel of solar time. ${f.body}` }, wrap);
  const pt = (h, r) => { const a = ((h - 12) / 12) * Math.PI; return [c + r * Math.sin(a), c - r * Math.cos(a)]; };
  const span = (a, b) => (b < a ? b + 24 : b);
  const arc = (h0, h1, r0, r1) => {
    h1 = span(h0, h1);
    const big = h1 - h0 > 12 ? 1 : 0;
    const [x0, y0] = pt(h0, r1), [x1, y1] = pt(h1, r1), [x2, y2] = pt(h1, r0), [x3, y3] = pt(h0, r0);
    return `M${x0},${y0}A${r1},${r1} 0 ${big} 1 ${x1},${y1}L${x2},${y2}A${r0},${r0} 0 ${big} 0 ${x3},${y3}Z`;
  };
  // The planetary hours, ruler by ruler.
  f.hours.forEach((hour, i) => {
    const now = f.now >= hour.start ? f.now < span(hour.start, hour.end) : f.now + 24 < span(hour.start, hour.end);
    const seg = svg("path", { d: arc(hour.start, hour.end, R.hours, R.out), class: `hour ${i < 12 ? "day" : "night"}${now ? " now" : ""}` }, s);
    const [x, y] = pt((hour.start + span(hour.start, hour.end)) / 2, (R.hours + R.out) / 2);
    svg("text", { x, y: y + 4.5, "text-anchor": "middle", class: "hour-glyph" }, s).textContent = hour.glyph;
    svg("title", {}, seg).textContent = `Hour of ${["Sun", "Moon"].includes(hour.ruler) ? "the " : ""}${hour.ruler}`;
  });
  for (const r of [R.hours, R.houses]) svg("circle", { cx: c, cy: c, r, class: "ring" }, s);
  // The houses, counted from sunrise against the Sun's motion, two hours each.
  for (let k = 1; k <= 12; k++) {
    const cusp = (((6 - 2 * k) % 24) + 24) % 24;
    const [x0, y0] = pt(cusp, R.core), [x1, y1] = pt(cusp, R.hours);
    svg("line", { x1: x0, y1: y0, x2: x1, y2: y1, class: cusp % 6 === 0 ? "angle" : "cusp" }, s);
    const [tx, ty] = pt(cusp + 1, (R.houses + R.hours) / 2);
    svg("text", { x: tx, y: ty + 3.5, "text-anchor": "middle", class: "house-num" }, s).textContent = ROMAN[k - 1];
  }
  for (const [h, angle, label] of [[12, "MC", "noon"], [18, "DSC", "sunset"], [0, "IC", "midnight"], [6, "ASC", "sunrise"]]) {
    const [x, y] = pt(h, R.out + 10);
    const anchor = h === 18 ? "start" : h === 6 ? "end" : "middle";
    if (h % 12 === 0) {
      svg("text", { x, y: y + (h ? -2 : 9), "text-anchor": anchor, class: "angle-label" }, s).textContent = `${angle} · ${label}`;
    } else {  // on the horizon there is room only for two short lines
      svg("text", { x, y: y - 2, "text-anchor": anchor, class: "angle-label" }, s).textContent = angle;
      svg("text", { x, y: y + 10, "text-anchor": anchor, class: "angle-label" }, s).textContent = label;
    }
  }
  // Planets that would overlap step inwards.
  const place = new Map();
  let previous = -Infinity, lane = 0;
  for (const p of [...f.planets].sort((a, b) => a.hour - b.hour)) {
    lane = (p.hour - previous) * 15 < 7 ? (lane + 1) % 3 : 0;
    previous = p.hour;
    place.set(p.id, pt(p.hour, R.orbit - lane * 17));
  }
  for (const a of f.aspects) {
    if (a.kind === "conjunction") continue;  // they touch already
    const [x1, y1] = place.get(a.a), [x2, y2] = place.get(a.b);
    svg("line", { x1, y1, x2, y2, class: `aspect ${HARMONIOUS.has(a.kind) ? "harmonious" : "tense"}` }, s);
  }
  const [hx, hy] = pt(f.now, R.out);
  svg("line", { x1: c, y1: c, x2: hx, y2: hy, class: "hand" }, s);
  svg("circle", { cx: hx, cy: hy, r: 3.5, class: "hand-tip" }, s);
  const dayGlyph = f.hours[0].glyph;
  svg("circle", { cx: c, cy: c, r: R.core, class: "core" }, s);
  const core = svg("text", { x: c, y: c + 7, "text-anchor": "middle", class: "core-glyph" }, s);
  core.textContent = dayGlyph;
  svg("title", {}, core).textContent = `A day of ${["Sun", "Moon"].includes(f.day_ruler) ? "the " : ""}${f.day_ruler}`;
  for (const p of f.planets) {
    const [x, y] = place.get(p.id);
    const g = svg("g", { class: "planet", tabindex: 0 }, s);
    svg("circle", { cx: x, cy: y, r: 12, fill: "transparent" }, g);
    if (p.group === "sky") {
      svg("circle", { cx: x, cy: y, r: 9, class: "sky-disc" }, g);
      svg("text", { x, y: y + 5, "text-anchor": "middle", class: "sky-glyph" }, g).textContent = p.id === "sun" ? "☉" : "☽";
    } else {
      svg("circle", { cx: x, cy: y, r: 5.5, fill: GROUP_COLORS[p.group], stroke: "var(--surface-1)", "stroke-width": 2 }, g);
    }
    hoverTip(g, p.label, [{ color: GROUP_COLORS[p.group], label: `culminates ${p.clock}`, value: `${ROMAN[p.house - 1]} house` }]);
  }

  const side = html("div", { class: "clock-side" }, wrap);
  const list = html("ol", { class: "planet-list", "aria-label": "When each culminates" }, side);
  for (const p of [...f.planets].sort((a, b) => a.clock.localeCompare(b.clock))) {
    const li = html("li", {}, list);
    if (p.group === "sky") html("span", { class: "sky-glyph", "aria-hidden": "true" }, li, p.id === "sun" ? "☉" : "☽");
    else html("i", { style: `background:${GROUP_COLORS[p.group]}` }, li);
    html("span", { class: "planet-name" }, li, p.label);
    html("span", { class: "planet-time" }, li, `${p.clock} · ${ROMAN[p.house - 1]}`);
  }
  legendRow(side, [
    { key: "line", color: "var(--oracle-accent)", label: "trine, sextile" },
    { key: "line", color: "var(--rival)", label: "square, opposition" },
  ]);
  bodyText(side, f);
}

// The five phases on their pentagon: the generating cycle runs clockwise around it, the overcoming one across it.
function elementsFigure(card, f) {
  card.append(headline(f));
  if (!f.elements.length) return bodyText(card, f);
  const narrow = card.clientWidth < 480;
  const W = narrow ? 360 : 520, H = narrow ? 330 : 372, cx = W / 2, cy = narrow ? 162 : 196, R = narrow ? 88 : 112;
  const PLACES = ["Fire", "Earth", "Metal", "Water", "Wood"];
  const s = svg("svg", { class: "pentagon", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": f.body }, card);
  const defs = svg("defs", {}, s);
  for (const kind of ["feeds", "checks", "strikes"]) {
    const m = svg("marker", { id: `arrow-${kind}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse", class: `arrowhead ${kind}` }, defs);
    svg("path", { d: "M0,1L10,5L0,9z" }, m);
  }
  const biggest = Math.max(...f.elements.map(e => e.mean));
  const node = new Map(f.elements.map(e => {
    const a = -Math.PI / 2 + (PLACES.indexOf(e.element) * 2 * Math.PI) / 5;
    return [e.element, { e, a, x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), r: (narrow ? 0.75 : 1) * (15 + 21 * Math.sqrt(e.mean / biggest)) }];
  }));
  for (const n of node.values()) {
    const m = node.get(n.e.generates);
    const a0 = n.a + (n.r + 7) / R, a1 = m.a + (m.a < n.a ? 2 * Math.PI : 0) - (m.r + 9) / R;
    svg("path", { d: `M${cx + R * Math.cos(a0)},${cy + R * Math.sin(a0)}A${R},${R} 0 0 1 ${cx + R * Math.cos(a1)},${cy + R * Math.sin(a1)}`, class: "cycle feeds", "marker-end": "url(#arrow-feeds)" }, s);
  }
  for (const n of node.values()) {
    const m = node.get(n.e.overcomes);
    const dx = m.x - n.x, dy = m.y - n.y, d = Math.hypot(dx, dy);
    const strikes = n.e.element === f.excess;
    const kind = strikes ? "strikes" : "checks";
    svg("line", { x1: n.x + (dx / d) * (n.r + 5), y1: n.y + (dy / d) * (n.r + 5), x2: m.x - (dx / d) * (m.r + 8), y2: m.y - (dy / d) * (m.r + 8), class: `cycle ${kind}`, "marker-end": `url(#arrow-${kind})` }, s);
    if (strikes) {
      const side = dx > 0 ? 1 : -1;  // the normal that points up, out of the star
      const lx = n.x + dx * 0.5 + (dy / d) * 13 * side, ly = n.y + dy * 0.5 - (dx / d) * 13 * side;
      svg("text", { x: lx, y: ly + 4, "text-anchor": "middle", class: "verb" }, s).textContent = n.e.verb;
    }
  }
  for (const n of node.values()) {
    const g = svg("g", { class: `element${n.e.element === f.excess ? " excess" : ""}`, tabindex: 0 }, s);
    svg("circle", { cx: n.x, cy: n.y, r: n.r, fill: ELEMENT_COLORS[n.e.element] }, g);
    svg("text", { x: n.x, y: n.y + n.r * 0.36, "text-anchor": "middle", class: `hanzi${["Earth", "Wood"].includes(n.e.element) ? " dark" : ""}`, style: `font-size:${Math.round(n.r)}px` }, g).textContent = n.e.char;
    const cos = Math.cos(n.a), sin = Math.sin(n.a), out = R + n.r + (narrow ? 8 : 14);
    const lines = narrow
      ? [[n.e.element, "element-name"], [n.e.region, "element-value"], [`${fmtInt.format(n.e.mean)} µg/m³`, "element-value"]]
      : [[`${n.e.element} · ${n.e.region}`, "element-name"], [`${fmtInt.format(n.e.mean)} µg/m³ · ${Math.round(n.e.share * 100)}%`, "element-value"]];
    const tall = (lines.length - 1) * 14;
    const lx = cx + out * cos, ly = cy + out * sin + (sin < -0.5 ? -tall - 4 : sin > 0.5 ? 10 : 4 - tall / 2);
    const anchor = cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle";
    lines.forEach(([text, cls], i) => {
      svg("text", { x: lx, y: ly + i * 14, "text-anchor": anchor, class: cls }, g).textContent = text;
    });
    hoverTip(g, `${n.e.element}, the ${n.e.region}`, [
      { color: ELEMENT_COLORS[n.e.element], label: "PM2.5", value: `${fmtInt.format(n.e.mean)} µg/m³` },
      { color: "transparent", label: `feeds ${n.e.generates}, ${n.e.verb} ${n.e.overcomes}`, value: "" },
    ]);
  }
  legendRow(card, [
    { key: "line", color: "var(--axis)", label: "feeds (around)" },
    { key: "line", color: "var(--rival)", label: `${f.excess} ${node.get(f.excess)?.e.verb ?? "overcomes"} (across)` },
  ]);
  bodyText(card, f);
}

// Where the wind came from, on the eight trigrams: petal length is how often, darker is hazier.
function windsFigure(card, f) {
  card.append(headline(f));
  const S = 250, c = S / 2, R = 70;
  const s = svg("svg", { class: "rose", viewBox: `0 0 ${S} ${S}`, role: "img", "aria-label": f.body }, card);
  const most = Math.max(...f.sectors.map(x => x.share), 1e-9);
  const hazes = f.sectors.map(x => x.haze).filter(h => h !== null);
  const [lo, hi] = hazes.length ? [Math.min(...hazes), Math.max(...hazes)] : [0, 1];
  for (const k of [1 / 3, 2 / 3, 1]) svg("circle", { cx: c, cy: c, r: R * k, class: "rose-ring" }, s);
  const calm = 15;  // petals grow out from the calm disc in the middle
  f.sectors.forEach((sector, i) => {
    const mid = ((i * 45 - 90) * Math.PI) / 180, half = (19 * Math.PI) / 180;
    const r = calm + ((R - calm) * sector.share) / most;
    if (sector.share > 0) {
      const at = (radius, a) => `${(c + radius * Math.cos(a)).toFixed(1)},${(c + radius * Math.sin(a)).toFixed(1)}`;
      const d = `M${at(calm, mid - half)}L${at(r, mid - half)}A${r},${r} 0 0 1 ${at(r, mid + half)}L${at(calm, mid + half)}A${calm},${calm} 0 0 0 ${at(calm, mid - half)}Z`;
      const shade = sector.haze === null ? 0.3 : 0.35 + (0.6 * (sector.haze - lo)) / Math.max(1, hi - lo);
      const petal = svg("path", { d, class: "petal", "fill-opacity": shade.toFixed(2), tabindex: 0 }, s);
      const lines = [{ color: "var(--series-outdoor)", label: "of the time", value: `${Math.round(sector.share * 100)}%` }];
      if (sector.speed !== null) lines.push({ color: "transparent", label: "speed", value: `${fmt1.format(sector.speed)} m/s` });
      if (sector.haze !== null) lines.push({ color: "transparent", label: "haze it carried", value: `${fmtInt.format(sector.haze)} µg/m³` });
      hoverTip(petal, `${sector.wind}, from the ${sector.direction} · ${sector.trigram[0]} ${sector.trigram[2]}`, lines);
    }
    const tx = c + (R + 20) * Math.cos(mid), ty = c + (R + 20) * Math.sin(mid);
    const tri = linesSvg(sector.lines, 18, { class: "rose-trigram" });
    tri.setAttribute("x", (tx - 9).toFixed(1));
    tri.setAttribute("y", (ty - tri.getAttribute("height") / 2).toFixed(1));
    s.append(tri);
    svg("text", { x: c + (R + 40) * Math.cos(mid), y: c + (R + 40) * Math.sin(mid) + 4, "text-anchor": "middle", class: "rose-dir" }, s).textContent = sector.abbr;
  });
  const still = svg("g", { class: "rose-calm", tabindex: 0 }, s);
  svg("circle", { cx: c, cy: c, r: calm - 2 }, still);
  svg("text", { x: c, y: c + 3.5, "text-anchor": "middle" }, still).textContent = `${Math.round(f.calm * 100)}%`;
  hoverTip(still, "Calm", [{ color: "transparent", label: `slower than ${fmt1.format(0.5)} m/s`, value: `${Math.round(f.calm * 100)}% of the time` }]);
  bodyText(card, f);
}

// Outside and inside, hour by hour; the shaded gap between them is what the ward holds back.
function wardChart(hours) {
  const W = 250, H = 120, m = { left: 30, right: 6, top: 8, bottom: 18 };
  const t0 = hours[0][0], t1 = hours.at(-1)[0];
  const ticks = niceTicks(0, Math.max(...hours.map(h => Math.max(h[1], h[2]))), 3);
  const x = t => m.left + (t1 > t0 ? (t - t0) / (t1 - t0) : 0.5) * (W - m.left - m.right);
  const y = v => m.top + (1 - v / ticks.at(-1)) * (H - m.top - m.bottom);
  const s = svg("svg", { class: "ward-chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Outdoor and indoor PM2.5 over ${hours.length} hours` });
  for (const v of ticks) {
    svg("line", { x1: m.left, x2: W - m.right, y1: Math.round(y(v)) + 0.5, y2: Math.round(y(v)) + 0.5, class: v ? "grid-line" : "base-line" }, s);
    svg("text", { x: m.left - 6, y: y(v) + 3.5, "text-anchor": "end", class: "tick" }, s).textContent = fmtInt.format(v);
  }
  // Runs of consecutive hours: NEA's gaps and the purifier's break the lines.
  const runs = [];
  for (const h of hours) {
    if (!runs.length || h[0] - runs.at(-1).at(-1)[0] > 2 * 3600) runs.push([]);
    runs.at(-1).push(h);
  }
  for (const run of runs) {
    const outside = run.map(h => `${x(h[0]).toFixed(1)},${y(h[1]).toFixed(1)}`);
    const inside = run.map(h => `${x(h[0]).toFixed(1)},${y(h[2]).toFixed(1)}`);
    svg("polygon", { points: [...outside, ...inside.reverse()].join(" "), class: "held-back" }, s);
    for (const [k, color] of [[1, "var(--series-outdoor)"], [2, "var(--series-blueair)"]]) {
      const d = run.map((h, i) => `${i ? "L" : "M"}${x(h[0]).toFixed(1)},${y(h[k]).toFixed(1)}`).join("");
      svg("path", { d: run.length > 1 ? d : `${d}h0.1`, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, s);
    }
  }
  for (const [t, anchor] of [[t0, "start"], [t1, "end"]]) {
    svg("text", { x: x(t), y: H - 4, "text-anchor": anchor, class: "tick" }, s).textContent = fmtFull.format(new Date(t * 1000));
  }
  const step = hours.length > 1 ? (x(t1) - x(t0)) / (hours.length - 1) : 20;
  for (const [t, outside, inside] of hours) {
    const hit = svg("rect", { x: x(t) - step / 2, y: m.top, width: Math.max(step, 4), height: H - m.top - m.bottom, fill: "transparent" }, s);
    hoverTip(hit, fmtFull.format(new Date(t * 1000)), [
      { color: "var(--series-outdoor)", label: "outside", value: `${fmtInt.format(outside)} µg/m³` },
      { color: "var(--series-blueair)", label: "inside", value: `${fmtInt.format(inside)} µg/m³` },
      { color: "transparent", label: "held back", value: `${Math.round((1 - inside / outside) * 100)}%` },
    ]);
  }
  return s;
}

function wardFigure(card, f) {
  card.append(headline(f));
  if (f.strength !== null) {
    const bars = html("div", { class: "bars ward-bars" }, card);
    const most = Math.max(f.outdoor, f.indoor);
    for (const [label, value, color] of [["Outside", f.outdoor, "var(--series-outdoor)"], ["Inside", f.indoor, "var(--series-blueair)"]]) {
      html("span", { class: "label" }, bars, label);
      const track = html("span", { class: "track" }, bars);
      html("span", { class: "bar", style: `width:${((value / most) * 100).toFixed(1)}%; background:${color}` }, track);
      html("span", { class: "pct" }, bars, `${fmtInt.format(value)} µg/m³`);
    }
    if (f.hours.length > 1) {
      card.append(wardChart(f.hours));
      legendRow(card, [
        { key: "line", color: "var(--series-outdoor)", label: "outside" },
        { key: "line", color: "var(--series-blueair)", label: "inside" },
        { key: "swatch", color: "color-mix(in srgb, var(--oracle-accent) 16%, transparent)", label: "held back" },
      ]);
    }
  }
  bodyText(card, f);
}

const FIGURES = {
  aura: auraFigure, moon: moonFigure, numerology: numerologyFigure, chakra: chakraFigure, zodiac: zodiacFigure,
  signals: signalsFigure, schumann: schumannFigure, golden: goldenFigure, mercury: mercuryFigure,
  iching: ichingFigure, society: societyFigure, choir: choirFigure, souls: soulsFigure, births: birthsFigure,
  clock: clockFigure, elements: elementsFigure, winds: windsFigure, ward: wardFigure,
};

function oracleCard(grid, f, span) {
  const card = html("article", { class: `oracle-card${span === 1 ? "" : span === "wide" ? " wide" : " span-2"}`, id: `omen-${f.id}` }, grid);
  const header = html("header", { class: "card-top" }, card);
  html("h3", {}, header, f.title);
  (FIGURES[f.id] || plainFigure)(card, f, header);
  html("p", { class: "certainty" }, card, f.certainty);
}

// The headlines worth a glance, linked to their cards, under the page header.
function renderOmens(byId) {
  const bar = document.getElementById("omens");
  bar.replaceChildren();
  const omens = [
    ["iching", f => ["", f.name]],
    ["clock", f => [f.hours.find(h => h.ruler === f.ruler).glyph, f.headline]],
    ["mercury", f => ["☿", f.headline]],
    ["moon", f => ["☽", f.headline]],
    ["souls", f => (f.souls === null ? null : ["", f.headline])],
    ["choir", f => ["♪", f.headline]],
    ["elements", f => (f.colour ? [f.elements.find(e => e.element === f.excess).char, `wear ${f.colour}`] : null)],
  ];
  for (const [id, omen] of omens) {
    const f = byId.get(id);
    const parts = f && omen(f);
    if (!parts) continue;
    const a = html("a", { href: `#omen-${id}`, title: f.title }, bar);
    const glyph = html("span", { class: "glyph", "aria-hidden": "true" }, a, parts[0]);
    if (id === "souls") glyph.append(ghosts(1, "omen-soul").firstChild);
    if (id === "iching") glyph.append(linesSvg(f.lines.map(l => l.yang), 12));
    a.append(parts[1]);
  }
  bar.hidden = !bar.childElementCount;
}

function renderOracle() {
  const root = document.getElementById("oracle");
  root.replaceChildren();
  if (!state.oracle) return;
  document.getElementById("disclaimer").textContent = state.oracle.disclaimer;
  const byId = new Map(state.oracle.findings.map(f => [f.id, f]));
  const sections = ORACLE_SECTIONS.map(s => ({ ...s, cards: s.cards.filter(([id]) => byId.has(id)) }));
  const placed = new Set(sections.flatMap(s => s.cards.map(([id]) => id)));
  const rest = [...byId.keys()].filter(id => !placed.has(id));
  if (rest.length) sections.push({ title: "Further omens", glyph: "✧", cards: rest.map(id => [id]) });
  for (const s of sections.filter(s => s.cards.length)) {
    const section = html("section", { class: "oracle-section" }, root);
    const title = html("h3", { class: "section-title" }, section);
    html("span", { class: "glyph", "aria-hidden": "true" }, title, s.glyph);
    title.append(s.title);
    const grid = html("div", { class: `oracle-grid${s.pair ? " pair" : ""}` }, section);
    for (const [id, span = 1] of s.cards) oracleCard(grid, byId.get(id), span);
  }
  renderOmens(byId);
}

// ---------- the Tree of Life ----------

function hoverable(node, label, show) {
  node.setAttribute("tabindex", "0");
  node.setAttribute("aria-label", label);
  const at = e => {
    const r = node.getBoundingClientRect();
    show(e?.clientX ?? r.left + r.width / 2, e?.clientY ?? r.top + r.height / 2);
  };
  node.addEventListener("pointerenter", at);
  node.addEventListener("pointermove", at);
  node.addEventListener("focus", () => at());
  node.addEventListener("pointerleave", hideTooltip);
  node.addEventListener("blur", hideTooltip);
}

// Hebrew words and numerals, isolated so the English around them keeps its order.
const HEBREW_RUN = /([א-ת][א-ת׳״ ]*[א-ת׳])|([א-ת])/g;

function withHebrew(parent, text) {
  let at = 0;
  for (const m of text.matchAll(HEBREW_RUN)) {
    parent.append(text.slice(at, m.index));
    html("bdi", { lang: "he" }, parent, m[0]);
    at = m.index + m[0].length;
  }
  parent.append(text.slice(at));
  return parent;
}

function bandText(s) {
  if (s.lower === null) return `${s.trend}, <${s.upper} ppm`;
  if (s.upper === null) return `${s.trend}, ${s.lower}+ ppm`;
  return `${s.trend}, ${s.lower}–${s.upper} ppm`;
}

function formatInstrument(instrument, value) {
  const text = value.toLocaleString(undefined, { minimumFractionDigits: instrument.decimals, maximumFractionDigits: instrument.decimals });
  return instrument.unit ? `${text} ${instrument.unit}` : text;
}

function treeSvg(f, instruments) {
  const DX = 72, DY = 44, R = 19, LABEL = 68;  // room beside the side pillars for their names
  const W = 2 * (DX + R + LABEL), H = 7 * DY + 2 * R + 12;
  const x = s => W / 2 + s.x * DX, y = s => R + 6 + s.y * DY;
  const s = svg("svg", { class: "tree", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": "Tree of Life" });
  const byName = Object.fromEntries(f.sefirot.map(n => [n.name, n]));
  const accent = "var(--oracle-accent)";

  const maxCount = Math.max(1, ...f.paths.map(p => p.count));
  const paths = svg("g", { class: "tree-paths" }, s);
  const letters = svg("g", { class: "tree-letters" }, s);
  for (const p of f.paths) {
    const a = byName[p.a], b = byName[p.b];
    const coords = { x1: x(a), y1: y(a), x2: x(b), y2: y(b) };
    svg("line", { ...coords, class: p.count ? "trodden" : "untrodden", "stroke-width": p.count ? 1 + 5 * p.count / maxCount : 1 }, paths);
    const hit = svg("line", { ...coords, class: "hit" }, paths);
    // Horizontal paths keep their letter off the central pillar's line.
    const t = a.y === b.y ? 0.4 : 0.5;
    svg("text", { x: x(a) + (x(b) - x(a)) * t, y: y(a) + (y(b) - y(a)) * t, dy: "0.35em", lang: "he" }, letters).textContent = p.letter;
    hoverable(hit, `Path ${p.name}, ${p.a} to ${p.b}: ${p.count} moves`, (px, py) =>
      showTooltip(px, py, `${p.name} (${p.letter})`, [{ color: accent, label: `${p.a} ↔ ${p.b}`, value: `${p.count} move${p.count === 1 ? "" : "s"}` }]));
  }

  const maxShare = Math.max(...f.sefirot.map(n => n.share));
  const nodes = svg("g", { class: "tree-nodes" }, s);
  for (const n of f.sefirot) {
    const g = svg("g", { transform: `translate(${x(n)},${y(n)})` }, nodes);
    svg("circle", { r: R, class: "ring" }, g);
    if (n.share > 0) svg("circle", { r: Math.max(2.5, R * Math.sqrt(n.share / maxShare)), class: "fill" }, g);
    // Names sit outward of the side pillars and to the right of the middle one, clear of the paths.
    svg("text", {
      x: n.x < 0 ? -(R + 6) : R + 6,
      dy: "0.35em",
      "text-anchor": n.x < 0 ? "end" : "start",
      class: n.share === maxShare ? "name dominant" : "name",
    }, g).textContent = n.name;
    const share = `${Math.round(n.share * 100)}%`;
    // The other instruments' means while the air was here, unmarked: they are context, not a series on the tree.
    const means = instruments.filter(i => n.means[i.key] != null).map(i => ({
      color: "transparent", label: i.label, value: formatInstrument(i, n.means[i.key]),
    }));
    hoverable(svg("circle", { r: R + 4, class: "hit" }, g), `${n.name}, ${n.meaning}, ${bandText(n)}: ${share} of the time`, (px, py) =>
      showTooltip(px, py, `${n.name} · ${n.hebrew} · ${n.meaning}`, [{ color: accent, label: bandText(n), value: share }, ...means]));
  }
  return s;
}

const WEEK_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];  // the API's days start on Sunday

function renderKabbalah() {
  const grid = document.getElementById("kabbalah");
  grid.replaceChildren();
  if (!state.kabbalah) return;
  document.getElementById("kabbalah-disclaimer").textContent = state.kabbalah.disclaimer;

  for (const f of state.kabbalah.findings) {
    const card = html("article", { class: `oracle-card ${["tree", "llull", "coincidences"].includes(f.id) ? "wide" : ""}` }, grid);
    let text = card;
    if (f.id === "tree") {
      const layout = html("div", { class: "tree-layout" }, card);
      layout.append(treeSvg(f, state.kabbalah.instruments.filter(i => i.key !== "co2")));
      text = html("div", { class: "tree-text" }, layout);
    }
    html("h3", {}, text, f.title);
    if (f.id === "gematria" || f.id === "temurah") {
      html("p", { class: "numeral hebrew", lang: "he", dir: "rtl" }, text, f.headline);
    } else {
      html("p", { class: "headline" }, text, f.headline);
    }
    withHebrew(html("p", { class: "body" }, text), f.body);

    if (f.id === "tree") {
      const pillars = html("p", { class: "pillars" }, text);
      for (const [name, trend] of [["Severity", "rising"], ["Balance", "steady"], ["Mercy", "falling"]]) {
        const item = html("span", {}, pillars);
        html("b", {}, item, name);
        item.append(` = CO₂ ${trend}`);
      }
      html("p", { class: "tree-note" }, text, "Height on the tree is how much CO₂; the pillar is where it is heading. Disc area is time spent there; path width is how often the air moved along it.");
    } else if (f.id === "week") {
      const bars = html("div", { class: "bars" }, card);
      const means = f.days.map(d => d.mean).filter(m => m !== null);
      const top = Math.max(...means);
      f.days.forEach((d, i) => {
        const rowClass = d.today ? "row-dominant" : "";
        const label = html("span", { class: `label ${rowClass}` }, bars, WEEK_SHORT[i] + " ");
        html("small", {}, label, d.sefira);
        const track = html("span", { class: `track ${rowClass}` }, bars);
        if (d.mean !== null) html("span", { class: "bar", style: `width:${(d.mean / top * 100).toFixed(1)}%` }, track);
        html("span", { class: "pct" }, bars, d.mean === null ? "–" : fmtInt.format(d.mean));
      });
    } else if (f.id === "llull") {
      const chant = html("p", { class: "chant", lang: "he", dir: "rtl", "aria-label": "The chant around the first Name heard" }, text);
      const [a, b] = f.mark || [f.excerpt.length, f.excerpt.length];
      const [before, after] = f.excerpt_cut;
      chant.append(before ? "…" : "", f.excerpt.slice(0, a));
      if (f.mark) html("mark", {}, chant, f.excerpt.slice(a, b));
      chant.append(f.excerpt.slice(b), after ? "…" : "");
      const speaking = f.voices.filter(v => v.found > 0);
      if (f.voices.length > 1 && speaking.length) {
        const voices = html("p", { class: "tree-voices" }, text);
        speaking.forEach((v, i) => {
          const item = html("span", {}, voices);
          html("b", {}, item, v.label);
          item.append(` ${v.found} / ${fmt1.format(v.expected)}`);
          if (i < speaking.length - 1) voices.append(" · ");
        });
        const silent = f.voices.length - speaking.length;
        if (silent) voices.append(` · ${silent} silent`);
        html("p", { class: "tree-note" }, text, "Words heard / words its letters would give shuffled, per instrument.");
      }
      const chips = html("div", { class: "name-chips" }, text);
      for (const n of f.names) {
        const chip = html("span", { class: "name-chip" }, chips);
        html("bdi", { lang: "he", class: "word" }, chip, n.word);
        chip.append(` ${n.meaning} `);
        html("span", { class: "count" }, chip, `×${n.count}`);
      }
    } else if (f.id === "coincidences") {
      const list = html("div", { class: "coincidence-list" }, text);
      for (const c of f.coincidences) {
        const row = html("div", { class: "coincidence" }, list);
        html("span", { class: "pair" }, row, `${c.value} · ${c.sacred}`);
        withHebrew(html("span", {}, row), c.text);
      }
    } else if (f.id === "vessels") {
      // Share of the time each vessel spent broken, on a common 0–100% scale.
      const bars = html("div", { class: "bars" }, card);
      for (const v of f.vessels) {
        const rowClass = v.broken ? "row-dominant" : "";
        const label = html("span", { class: `label ${rowClass}` }, bars, `${v.label} `);
        html("small", {}, label, `≥${v.limit} ${v.unit}`);
        const track = html("span", { class: `track ${rowClass}` }, bars);
        if (v.exile_share > 0) html("span", { class: "bar", style: `width:${(v.exile_share * 100).toFixed(1)}%` }, track);
        html("span", { class: "pct" }, bars, `${Math.round(v.exile_share * 100)}%`);
      }
      html("p", { class: "tree-note" }, card, "Share of the time each vessel lay broken; bold ones are broken now.");
    }

    html("p", { class: "certainty" }, text, f.certainty);
  }
}

// ---------- data flow ----------

const ORACLE_REFRESH_MS = 60000;  // the Oracle changes its mind slowly, and redrawing it would drop a hover
let oracleFetched = 0;

async function refresh({ rangeChanged = false } = {}) {
  const charts = document.querySelectorAll(".chart");
  if (rangeChanged) charts.forEach(c => c.classList.add("loading"));
  const r = encodeURIComponent(state.range);
  const divine = rangeChanged || Date.now() - oracleFetched >= ORACLE_REFRESH_MS;
  try {
    const [latest, series, oracle, kabbalah, filter] = await Promise.all([
      getJSON("api/latest"),
      getJSON(`api/series?range=${r}`),
      divine ? getJSON(`api/oracle?range=${r}`) : null,
      divine ? getJSON(`api/kabbalah?range=${r}`) : null,
      divine ? getJSON("api/filter") : null,
    ]);
    Object.assign(state, { latest, series });
    renderTiles();
    renderCharts();
    if (oracle) {
      Object.assign(state, { oracle, kabbalah, filter });
      renderFilter();
      oracleFetched = Date.now();
      renderOracle();
      renderKabbalah();
    }
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
