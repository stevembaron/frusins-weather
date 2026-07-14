/* Home utility dashboard — vanilla JS, no build step.
   Renders from window.UTILITY_DATA (see data.js / README). */
(() => {
  const DATA = window.UTILITY_DATA;
  const SVGNS = 'http://www.w3.org/2000/svg';
  const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const GAL_PER_CUFT = 7.48052;

  const UTIL = {
    water: { label: 'Water', color: 'var(--c-water)' },
    gas: { label: 'Gas', color: 'var(--c-gas)' },
    elec: { label: 'Electricity', color: 'var(--c-elec)' },
  };

  const state = { range: 24 };

  // ---------- formatting ----------
  const fmtInt = n => n.toLocaleString('en-US', { maximumFractionDigits: 0 });
  const fmtMoney = n => '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtMoney0 = n => '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 });
  const fmt1 = n => n.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const monthLabel = m => { const [y, mo] = m.split('-'); return `${MONTH_NAMES[+mo - 1]} ${y}`; };
  const monthShort = m => { const [y, mo] = m.split('-'); return `${MONTH_NAMES[+mo - 1]} ’${y.slice(2)}`; };
  const dayLabel = d => { const [, mo, dd] = d.split('-'); return `${MONTH_NAMES[+mo - 1]} ${+dd}`; };

  function addMonths(month, k) {
    const [y, m] = month.split('-').map(Number);
    const t = y * 12 + (m - 1) + k;
    return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`;
  }

  // ---------- data indexes ----------
  const byMonth = rows => new Map(rows.map(r => [r.month, r]));
  const waterM = byMonth(DATA.water);
  const elecM = byMonth(DATA.electricityMonthly);
  const gasM = byMonth(DATA.gas);

  const allMonths = [...new Set([...waterM.keys(), ...elecM.keys(), ...gasM.keys()])].sort();
  const lastMonth = allMonths[allMonths.length - 1];

  function monthsInRange() {
    if (state.range === 'all') return allMonths;
    const start = addMonths(lastMonth, -(state.range - 1));
    return allMonths.filter(m => m >= start);
  }

  // ---------- projections ----------
  const PROJ_HORIZON = 6;
  const daysInMonth = m => new Date(+m.slice(0, 4), +m.slice(5, 7), 0).getDate();

  // trend factor: last three actual months vs the same months a year earlier, clamped
  function yoyFactor(map, getVal) {
    let num = 0, den = 0;
    for (let i = 0; i < 3; i++) {
      const m = addMonths(lastMonth, -i);
      const a = map.get(m), b = map.get(addMonths(m, -12));
      if (a && b && getVal(a) != null && getVal(b) != null) { num += getVal(a); den += getVal(b); }
    }
    if (!den || !num) return 1;
    return Math.min(1.4, Math.max(0.7, num / den));
  }

  const PROJ = (() => {
    const months = Array.from({ length: PROJ_HORIZON }, (_, i) => addMonths(lastMonth, i + 1));
    const out = { months, water: new Map(), elec: new Map(), gas: new Map() };
    const defs = [
      ['water', waterM, r => r.cubicFeet, r => r.cost],
      ['elec', elecM, r => r.kwh, r => r.cost],
      ['gas', gasM, r => r.dth, r => r.cost],
    ];
    for (const [key, map, getU, getC] of defs) {
      const fU = yoyFactor(map, getU), fC = yoyFactor(map, getC);
      for (const m of months) {
        const base = map.get(addMonths(m, -12));
        if (!base || getU(base) == null) continue;
        out[key].set(m, {
          usage: getU(base) * fU,
          cost: getC(base) != null ? getC(base) * fC : null,
        });
      }
    }
    // Current month electricity: nowcast from daily actuals. Month-to-date is real;
    // remaining days run at the average of the trailing 7 days and last year's
    // trend-adjusted daily rate for this month.
    const cur = months[0];
    const daily = DATA.electricityDaily.filter(d => d.date.startsWith(cur));
    const lastYear = elecM.get(addMonths(cur, -12));
    if (daily.length && lastYear) {
      const mtd = daily.reduce((s, d) => s + d.kwh, 0);
      const lastDay = Math.max(...daily.map(d => +d.date.slice(8)));
      const remaining = daysInMonth(cur) - lastDay;
      const tail = DATA.electricityDaily.slice(-7);
      const recentRate = tail.reduce((s, d) => s + d.kwh, 0) / tail.length;
      const seasonalRate = (lastYear.kwh / daysInMonth(addMonths(cur, -12))) * yoyFactor(elecM, r => r.kwh);
      const kwh = mtd + remaining * (recentRate + seasonalRate) / 2;
      const lastYearRate = lastYear.cost / lastYear.kwh;
      out.elec.set(cur, {
        usage: kwh,
        cost: kwh * lastYearRate * yoyFactor(elecM, r => r.cost) / yoyFactor(elecM, r => r.kwh),
        nowcast: { mtd, lastDay },
      });
    }
    return out;
  })();

  const projTotal = m => {
    const parts = [PROJ.water.get(m)?.cost, PROJ.elec.get(m)?.cost, PROJ.gas.get(m)?.cost];
    return parts.every(p => p != null) ? parts.reduce((a, b) => a + b, 0) : null;
  };

  // ---------- DOM helpers ----------
  const $ = id => document.getElementById(id);

  function svgEl(name, attrs = {}) {
    const e = document.createElementNS(SVGNS, name);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  }

  function div(cls, text) {
    const e = document.createElement('div');
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // ---------- tooltip (values reachable without it via the data tables) ----------
  const tooltip = $('tooltip');

  function tipShow(title, rows, x, y) {
    tooltip.replaceChildren();
    tooltip.append(div('tip-title', title));
    for (const r of rows) {
      const row = div('tip-row');
      const k = document.createElement('span');
      k.className = 'k';
      if (r.color) {
        const key = document.createElement('span');
        key.className = 'key';
        key.style.background = r.color;
        k.append(key);
      }
      k.append(document.createTextNode(r.label));
      const v = div('v', r.value);
      row.append(k, v);
      tooltip.append(row);
    }
    tooltip.style.display = 'block';
    tipMove(x, y);
  }

  function tipMove(x, y) {
    const pad = 12;
    const r = tooltip.getBoundingClientRect();
    let left = x + pad, top = y + pad;
    if (left + r.width > innerWidth - 8) left = x - r.width - pad;
    if (top + r.height > innerHeight - 8) top = y - r.height - pad;
    tooltip.style.left = Math.max(8, left) + 'px';
    tooltip.style.top = Math.max(8, top) + 'px';
  }

  const tipHide = () => { tooltip.style.display = 'none'; };

  // ---------- scales & ticks ----------
  function niceMax(max, count = 4) {
    if (max <= 0) return 1;
    const raw = max / count;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].find(s => s * mag >= raw) * mag;
    return { max: Math.ceil(max / step) * step, step };
  }

  function baseChart(container, height, margin) {
    container.replaceChildren();
    const width = Math.max(280, container.clientWidth);
    const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, width, height, role: 'img' });
    container.append(svg);
    return { svg, width, height, iw: width - margin.l - margin.r, ih: height - margin.t - margin.b, m: margin };
  }

  function drawYAxis(c, yMax, step, format) {
    for (let v = 0; v <= yMax + 1e-9; v += step) {
      const y = c.m.t + c.ih - (v / yMax) * c.ih;
      if (v > 0) c.svg.append(svgEl('line', { x1: c.m.l, x2: c.m.l + c.iw, y1: y, y2: y, class: 'gridline' }));
      const t = svgEl('text', { x: c.m.l - 6, y: y + 3.5, 'text-anchor': 'end', class: 'tick-label' });
      t.textContent = format(v);
      c.svg.append(t);
    }
    c.svg.append(svgEl('line', {
      x1: c.m.l, x2: c.m.l + c.iw, y1: c.m.t + c.ih, y2: c.m.t + c.ih, class: 'baseline',
    }));
  }

  function xTickEvery(n, width) {
    const fit = Math.max(1, Math.floor(width / 62));
    return Math.ceil(n / fit);
  }

  // top-rounded rect path, square at the baseline
  function barPath(x, y, w, h, rWant = 4) {
    const r = Math.max(0, Math.min(rWant, w / 2, h));
    return `M${x},${y + h} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} L${x + w},${y + h} Z`;
  }

  // ---------- column chart (single series or stacked) ----------
  // items: [{key, label, segments: [{name, value, color}], tipRows, tipTitle}]
  function columnChart(container, items, opts) {
    const c = baseChart(container, opts.height || 220, { t: 12, r: 8, b: 26, l: opts.left || 46 });
    const totals = items.map(d => d.segments.reduce((s, g) => s + (g.value || 0), 0));
    const { max: yMax, step } = niceMax(Math.max(...totals, 1e-9), opts.yTicks || 4);
    drawYAxis(c, yMax, step, opts.yFormat || fmtInt);

    const n = items.length;
    const bw = c.iw / n;
    const barW = Math.min(24, Math.max(2, bw - 2));
    const every = xTickEvery(n, c.iw);
    const yOf = v => c.m.t + c.ih - (v / yMax) * c.ih;

    items.forEach((d, i) => {
      const x = c.m.l + i * bw + (bw - barW) / 2;
      let acc = 0;
      const drawn = d.segments.filter(s => (s.value || 0) > 0);
      drawn.forEach((s, si) => {
        const y0 = yOf(acc), y1 = yOf(acc + s.value);
        const isTop = si === drawn.length - 1;
        // 2px surface gap between stacked segments; rounded end on the top segment only
        const gap = isTop ? 0 : 2;
        const h = Math.max(0.75, y0 - y1 - gap);
        const y = y0 - h - gap;
        const mark = isTop
          ? svgEl('path', { d: barPath(x, y, barW, h), fill: s.color })
          : svgEl('rect', { x, y, width: barW, height: h, fill: s.color });
        if (d.projected) mark.setAttribute('fill-opacity', '0.4');
        c.svg.append(mark);
        acc += s.value;
      });
      if (i % every === 0) {
        const t = svgEl('text', { x: c.m.l + i * bw + bw / 2, y: c.m.t + c.ih + 16, 'text-anchor': 'middle', class: 'tick-label' });
        t.textContent = d.label;
        c.svg.append(t);
      }
    });

    // hit targets: the full column slot, keyboard focusable
    items.forEach((d, i) => {
      const hit = svgEl('rect', {
        x: c.m.l + i * bw, y: c.m.t, width: bw, height: c.ih,
        class: 'hit', tabindex: '0', 'aria-label': d.tipTitle + ': ' + d.tipRows.map(r => `${r.label} ${r.value}`).join(', '),
      });
      const show = (x, y) => tipShow(d.tipTitle, d.tipRows, x, y);
      hit.addEventListener('pointerenter', e => show(e.clientX, e.clientY));
      hit.addEventListener('pointermove', e => tipMove(e.clientX, e.clientY));
      hit.addEventListener('pointerleave', tipHide);
      hit.addEventListener('focus', () => {
        const r = hit.getBoundingClientRect();
        show(r.left + r.width / 2, r.top + 20);
      });
      hit.addEventListener('blur', tipHide);
      c.svg.append(hit);
    });
  }

  // ---------- year-over-year line chart ----------
  // series: [{name, color, width, values: (number|null)[12]}] — later series drawn on top
  function yoyChart(container, series, opts) {
    const c = baseChart(container, opts.height || 210, { t: 12, r: 10, b: 26, l: opts.left || 46 });
    const all = series.flatMap(s => s.values.filter(v => v != null));
    const { max: yMax, step } = niceMax(Math.max(...all, 1e-9), 4);
    drawYAxis(c, yMax, step, opts.yFormat || fmtInt);

    const xOf = i => c.m.l + (i + 0.5) * (c.iw / 12);
    const yOf = v => c.m.t + c.ih - (v / yMax) * c.ih;

    MONTH_NAMES.forEach((mn, i) => {
      if (i % (c.iw < 420 ? 2 : 1)) return;
      const t = svgEl('text', { x: xOf(i), y: c.m.t + c.ih + 16, 'text-anchor': 'middle', class: 'tick-label' });
      t.textContent = mn;
      c.svg.append(t);
    });

    for (const s of series) {
      let d = '';
      s.values.forEach((v, i) => {
        if (v == null) return;
        const prev = i > 0 ? s.values[i - 1] : null;
        d += (prev == null ? 'M' : 'L') + xOf(i).toFixed(1) + ',' + yOf(v).toFixed(1);
      });
      if (d) c.svg.append(svgEl('path', {
        d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2,
        'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      }));
    }

    // crosshair + one tooltip listing every year at that month
    const cross = svgEl('line', { y1: c.m.t, y2: c.m.t + c.ih, class: 'crosshair', visibility: 'hidden' });
    c.svg.append(cross);
    const overlay = svgEl('rect', { x: c.m.l, y: c.m.t, width: c.iw, height: c.ih, class: 'hit' });
    overlay.addEventListener('pointermove', e => {
      const box = overlay.getBoundingClientRect();
      const i = Math.max(0, Math.min(11, Math.floor(((e.clientX - box.left) / box.width) * 12)));
      cross.setAttribute('x1', xOf(i));
      cross.setAttribute('x2', xOf(i));
      cross.setAttribute('visibility', 'visible');
      const rows = series
        .map(s => ({ label: s.name, color: s.color, v: s.values[i] }))
        .filter(r => r.v != null)
        .sort((a, b) => b.label.localeCompare(a.label))
        .map(r => ({ label: r.label, color: r.color, value: opts.tipFormat(r.v) }));
      if (rows.length) tipShow(MONTH_NAMES[i], rows, e.clientX, e.clientY);
      else tipHide();
    });
    overlay.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); tipHide(); });
    c.svg.append(overlay);
  }

  // ---------- scatter ----------
  // points: [{x, y, tipTitle, tipRows}]
  function scatterChart(container, points, opts) {
    const c = baseChart(container, opts.height || 230, { t: 12, r: 12, b: 40, l: opts.left || 50 });
    const ys = points.map(p => p.y);
    const xs = points.map(p => p.x);
    const { max: yMax, step } = niceMax(Math.max(...ys, 1e-9), 4);
    drawYAxis(c, yMax, step, opts.yFormat || fmtInt);

    const xMin = Math.floor(Math.min(...xs) / 10) * 10;
    const xMax = Math.ceil(Math.max(...xs) / 10) * 10;
    const xOf = v => c.m.l + ((v - xMin) / (xMax - xMin)) * c.iw;
    const yOf = v => c.m.t + c.ih - (v / yMax) * c.ih;

    for (let v = xMin; v <= xMax; v += 10) {
      const t = svgEl('text', { x: xOf(v), y: c.m.t + c.ih + 16, 'text-anchor': 'middle', class: 'tick-label' });
      t.textContent = v + '°';
      c.svg.append(t);
    }
    const xt = svgEl('text', { x: c.m.l + c.iw / 2, y: c.height - 6, 'text-anchor': 'middle', class: 'axis-title' });
    xt.textContent = opts.xTitle;
    c.svg.append(xt);

    for (const p of points) {
      c.svg.append(svgEl('circle', {
        cx: xOf(p.x), cy: yOf(p.y), r: 5, fill: opts.color,
        stroke: 'var(--surface)', 'stroke-width': 2,
      }));
    }

    // nearest-point hover: the pointer only has to be closest, not dead-center
    const overlay = svgEl('rect', { x: c.m.l, y: c.m.t, width: c.iw, height: c.ih, class: 'hit' });
    overlay.addEventListener('pointermove', e => {
      const box = c.svg.getBoundingClientRect();
      const px = e.clientX - box.left, py = e.clientY - box.top;
      let best = null, bestD = 24 * 24;
      for (const p of points) {
        const dx = xOf(p.x) - px, dy = yOf(p.y) - py, d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; best = p; }
      }
      if (best) tipShow(best.tipTitle, best.tipRows, e.clientX, e.clientY);
      else tipHide();
    });
    overlay.addEventListener('pointerleave', tipHide);
    c.svg.append(overlay);
  }

  // ---------- data tables ----------
  function fillTable(id, cols, rows) {
    const scroller = $(id).querySelector('.scroller');
    scroller.replaceChildren();
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    for (const cname of cols) {
      const th = document.createElement('th');
      th.textContent = cname;
      tr.append(th);
    }
    thead.append(tr);
    const tbody = document.createElement('tbody');
    for (const r of rows) {
      const trr = document.createElement('tr');
      for (const cell of r) {
        const td = document.createElement('td');
        td.textContent = cell ?? '—';
        trr.append(td);
      }
      tbody.append(trr);
    }
    table.append(thead, tbody);
    scroller.append(table);
  }

  function legend(id, items) {
    const box = $(id);
    box.replaceChildren();
    for (const it of items) {
      const item = div('item');
      const sw = document.createElement('span');
      sw.className = it.line ? 'line-key' : 'swatch';
      sw.style.background = it.color;
      item.append(sw, document.createTextNode(it.label));
      box.append(item);
    }
  }

  // ---------- KPI tiles ----------
  function sparkline(values, color) {
    const w = 120, h = 28, n = values.length;
    const svg = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, height: h, 'aria-hidden': 'true' });
    const vs = values.filter(v => v != null);
    if (vs.length < 2) return svg;
    const max = Math.max(...vs), min = Math.min(...vs);
    const xOf = i => 2 + (i / (n - 1)) * (w - 8);
    const yOf = v => max === min ? h / 2 : 3 + (1 - (v - min) / (max - min)) * (h - 8);
    let d = '';
    values.forEach((v, i) => { if (v != null) d += (d && values[i - 1] != null ? 'L' : 'M') + xOf(i).toFixed(1) + ',' + yOf(v).toFixed(1); });
    svg.append(svgEl('path', { d, fill: 'none', stroke: 'var(--deemph)', 'stroke-width': 1.5, 'stroke-linecap': 'round' }));
    const last = values.length - 1;
    if (values[last] != null) svg.append(svgEl('circle', { cx: xOf(last), cy: yOf(values[last]), r: 3, fill: color }));
    return svg;
  }

  function deltaNode(cur, prior, priorLabel) {
    const d = div('delta');
    if (prior == null || cur == null || prior === 0) {
      d.textContent = `no ${priorLabel} data`;
      return d;
    }
    const pct = ((cur - prior) / prior) * 100;
    const s = document.createElement('span');
    s.className = pct >= 0 ? 'up' : 'down';
    s.textContent = `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct).toFixed(0)}%`;
    d.append(s, document.createTextNode(` vs ${priorLabel}`));
    return d;
  }

  function tile(label, valueHTMLParts, cur, prior, priorLabel, sparkVals, color) {
    const t = div('tile');
    t.append(div('label', label));
    const v = div('value');
    v.append(document.createTextNode(valueHTMLParts[0]));
    if (valueHTMLParts[1]) {
      const small = document.createElement('small');
      small.textContent = ' ' + valueHTMLParts[1];
      v.append(small);
    }
    t.append(v, deltaNode(cur, prior, priorLabel));
    if (sparkVals) t.append(sparkline(sparkVals, color));
    return t;
  }

  function renderKpis() {
    const box = $('kpis');
    box.replaceChildren();
    const m = lastMonth, prev = addMonths(m, -12);
    const label = monthLabel(m), prevLabel = monthLabel(prev);
    const spark = key => {
      const map = { water: waterM, elec: elecM, gas: gasM };
      return Array.from({ length: 12 }, (_, i) => {
        const r = map[key].get(addMonths(m, i - 11));
        if (!r) return null;
        return key === 'water' ? r.cubicFeet : key === 'elec' ? r.kwh : r.dth;
      });
    };
    const total = mo => {
      const parts = [waterM.get(mo)?.cost, elecM.get(mo)?.cost, gasM.get(mo)?.cost];
      return parts.every(p => p != null) ? parts.reduce((a, b) => a + b, 0) : null;
    };
    const sparkTotal = Array.from({ length: 12 }, (_, i) => total(addMonths(m, i - 11)));

    const t = total(m), tPrev = total(prev);
    box.append(tile(`Total spend — ${label}`, [t != null ? fmtMoney0(t) : '—'], t, tPrev, prevLabel, sparkTotal, 'var(--ink-2)'));

    const w = waterM.get(m), wp = waterM.get(prev);
    box.append(tile(`Water — ${label}`, w ? [fmtInt(w.cubicFeet), 'cu ft'] : ['—'],
      w?.cubicFeet, wp?.cubicFeet, prevLabel, spark('water'), 'var(--c-water)'));

    const e = elecM.get(m), ep = elecM.get(prev);
    box.append(tile(`Electricity — ${label}`, e ? [fmtInt(e.kwh), 'kWh'] : ['—'],
      e?.kwh, ep?.kwh, prevLabel, spark('elec'), 'var(--c-elec)'));

    const g = gasM.get(m), gp = gasM.get(prev);
    box.append(tile(`Gas — ${label}`, g ? [fmt1(g.dth), 'Dth'] : ['—'],
      g?.dth, gp?.dth, prevLabel, spark('gas'), 'var(--c-gas)'));

    // projected current month
    const pm = PROJ.months[0];
    const pTotal = projTotal(pm);
    if (pTotal != null) {
      const pPrev = addMonths(pm, -12);
      const actualPrev = [waterM.get(pPrev)?.cost, elecM.get(pPrev)?.cost, gasM.get(pPrev)?.cost];
      const prevTotal = actualPrev.every(p => p != null) ? actualPrev.reduce((a, b) => a + b, 0) : null;
      const t = tile(`Projected spend — ${monthLabel(pm)}`, [fmtMoney0(pTotal)], pTotal, prevTotal, monthLabel(pPrev), null, null);
      const parts = div('delta');
      parts.textContent = `water ${fmtMoney0(PROJ.water.get(pm).cost)} · elec ${fmtMoney0(PROJ.elec.get(pm).cost)} · gas ${fmtMoney0(PROJ.gas.get(pm).cost)}`;
      t.append(parts);
      box.append(t);
    }
  }

  // ---------- sections ----------
  function renderSpend() {
    const months = monthsInRange();
    const costsOf = mo => ({
      w: waterM.get(mo)?.cost ?? null,
      g: gasM.get(mo)?.cost ?? null,
      e: elecM.get(mo)?.cost ?? null,
      projected: false,
    });
    const projCostsOf = mo => ({
      w: PROJ.water.get(mo)?.cost ?? null,
      g: PROJ.gas.get(mo)?.cost ?? null,
      e: PROJ.elec.get(mo)?.cost ?? null,
      projected: true,
    });
    const entries = [
      ...months.map(mo => [mo, costsOf(mo)]),
      ...PROJ.months.map(mo => [mo, projCostsOf(mo)]),
    ];
    const items = entries.map(([mo, c]) => {
      const suffix = c.projected ? ' — projected' : '';
      const rows = [
        { label: 'Electricity', color: UTIL.elec.color, value: c.e != null ? fmtMoney(c.e) : 'no data' },
        { label: 'Gas', color: UTIL.gas.color, value: c.g != null ? fmtMoney(c.g) : 'no data' },
        { label: 'Water', color: UTIL.water.color, value: c.w != null ? fmtMoney(c.w) : 'no data' },
        { label: 'Total', value: fmtMoney((c.w || 0) + (c.g || 0) + (c.e || 0)) },
      ];
      return {
        label: monthShort(mo),
        projected: c.projected,
        tipTitle: monthLabel(mo) + suffix,
        tipRows: rows,
        segments: [
          { name: 'Water', value: c.w || 0, color: UTIL.water.color },
          { name: 'Gas', value: c.g || 0, color: UTIL.gas.color },
          { name: 'Electricity', value: c.e || 0, color: UTIL.elec.color },
        ],
      };
    });
    columnChart($('spendChart'), items, { height: 250, yFormat: fmtMoney0, left: 52 });
    legend('spendLegend', [
      { label: 'Water', color: UTIL.water.color },
      { label: 'Gas', color: UTIL.gas.color },
      { label: 'Electricity', color: UTIL.elec.color },
      { label: 'Projected', color: 'var(--deemph)' },
    ]);
    fillTable('spendTable', ['Month', 'Water', 'Gas', 'Electricity', 'Total'], entries.map(([mo, c]) =>
      [monthLabel(mo) + (c.projected ? ' (proj.)' : ''),
        c.w != null ? fmtMoney(c.w) : null, c.g != null ? fmtMoney(c.g) : null,
        c.e != null ? fmtMoney(c.e) : null, fmtMoney((c.w || 0) + (c.g || 0) + (c.e || 0))]));
  }

  function renderProjections() {
    const rows = PROJ.months.map(mo => {
      const w = PROJ.water.get(mo), e = PROJ.elec.get(mo), g = PROJ.gas.get(mo);
      const t = projTotal(mo);
      return [
        monthLabel(mo) + (e?.nowcast ? ' (in progress)' : ''),
        w ? fmtInt(w.usage) : null, w?.cost != null ? fmtMoney0(w.cost) : null,
        e ? fmtInt(e.usage) : null, e?.cost != null ? fmtMoney0(e.cost) : null,
        g ? fmt1(g.usage) : null, g?.cost != null ? fmtMoney0(g.cost) : null,
        t != null ? fmtMoney0(t) : null,
      ];
    });
    fillTable('projTable', ['Month', 'Water cu ft', 'Water $', 'Elec kWh', 'Elec $', 'Gas Dth', 'Gas $', 'Total $'], rows);
    const e0 = PROJ.elec.get(PROJ.months[0]);
    if (e0?.nowcast) {
      $('projCaption').textContent =
        `Same month last year scaled by the last three months' year-over-year trend. ${monthLabel(PROJ.months[0])} electricity blends ` +
        `${fmtInt(e0.nowcast.mtd)} kWh of actual usage through the ${e0.nowcast.lastDay}th with that seasonal estimate for the remaining days.`;
    }
  }

  function renderUsageCards() {
    const months = monthsInRange();
    const projItems = (projMap, color, fmtUsage, unit) => PROJ.months
      .filter(mo => projMap.has(mo))
      .map(mo => {
        const p = projMap.get(mo);
        return {
          label: monthShort(mo),
          projected: true,
          tipTitle: monthLabel(mo) + ' — projected',
          tipRows: [
            { label: 'Usage', value: `${fmtUsage(p.usage)} ${unit}` },
            { label: 'Est. bill', value: p.cost != null ? fmtMoney0(p.cost) : 'n/a' },
          ],
          segments: [{ name: 'proj', value: p.usage, color }],
        };
      });

    const wRows = months.filter(mo => waterM.has(mo)).map(mo => waterM.get(mo));
    columnChart($('waterChart'), [...wRows.map(r => ({
      label: monthShort(r.month),
      tipTitle: monthLabel(r.month),
      tipRows: [
        { label: 'Usage', value: `${fmtInt(r.cubicFeet)} cu ft` },
        { label: '≈ gallons', value: fmtInt(r.cubicFeet * GAL_PER_CUFT) },
        { label: 'Bill', value: fmtMoney(r.cost) },
      ],
      segments: [{ name: 'Water', value: r.cubicFeet, color: UTIL.water.color }],
    })), ...projItems(PROJ.water, UTIL.water.color, fmtInt, 'cu ft')], { height: 200 });
    fillTable('waterTable', ['Month', 'Cu ft', 'Gallons', 'Bill'], [
      ...wRows.map(r => [monthLabel(r.month), fmtInt(r.cubicFeet), fmtInt(r.cubicFeet * GAL_PER_CUFT), fmtMoney(r.cost)]),
      ...PROJ.months.filter(mo => PROJ.water.has(mo)).map(mo => {
        const p = PROJ.water.get(mo);
        return [monthLabel(mo) + ' (proj.)', fmtInt(p.usage), fmtInt(p.usage * GAL_PER_CUFT), fmtMoney0(p.cost)];
      }),
    ]);

    const eRows = months.filter(mo => elecM.has(mo)).map(mo => elecM.get(mo));
    columnChart($('elecChart'), [...eRows.map(r => ({
      label: monthShort(r.month),
      tipTitle: monthLabel(r.month),
      tipRows: [
        { label: 'Usage', value: `${fmtInt(r.kwh)} kWh` },
        { label: 'Avg temp', value: `${r.avgTempF.toFixed(0)}°F` },
        { label: 'Bill', value: fmtMoney(r.cost) },
      ],
      segments: [{ name: 'Electricity', value: r.kwh, color: UTIL.elec.color }],
    })), ...projItems(PROJ.elec, UTIL.elec.color, fmtInt, 'kWh')], { height: 200 });
    fillTable('elecTable', ['Month', 'kWh', 'Avg temp', 'Bill'], [
      ...eRows.map(r => [monthLabel(r.month), fmtInt(r.kwh), r.avgTempF.toFixed(1) + '°F', fmtMoney(r.cost)]),
      ...PROJ.months.filter(mo => PROJ.elec.has(mo)).map(mo => {
        const p = PROJ.elec.get(mo);
        return [monthLabel(mo) + ' (proj.)', fmtInt(p.usage), null, fmtMoney0(p.cost)];
      }),
    ]);

    const gRows = months.filter(mo => gasM.has(mo)).map(mo => gasM.get(mo));
    columnChart($('gasChart'), [...gRows.map(r => ({
      label: monthShort(r.month),
      tipTitle: monthLabel(r.month),
      tipRows: [
        { label: 'Usage', value: `${fmt1(r.dth)} Dth` },
        { label: 'Weather-adj.', value: `${fmt1(r.dthWeatherAdj)} Dth` },
        { label: 'Bill', value: r.cost != null ? fmtMoney(r.cost) : 'n/a' },
      ],
      segments: [{ name: 'Gas', value: r.dth, color: UTIL.gas.color }],
    })), ...projItems(PROJ.gas, UTIL.gas.color, fmt1, 'Dth')], { height: 200 });
    fillTable('gasTable', ['Month', 'Dth', 'Weather-adj. Dth', 'Bill'], [
      ...gRows.map(r => [monthLabel(r.month), fmt1(r.dth), fmt1(r.dthWeatherAdj), r.cost != null ? fmtMoney(r.cost) : null]),
      ...PROJ.months.filter(mo => PROJ.gas.has(mo)).map(mo => {
        const p = PROJ.gas.get(mo);
        return [monthLabel(mo) + ' (proj.)', fmt1(p.usage), null, fmtMoney0(p.cost)];
      }),
    ]);
  }

  function renderYoy(key, chartId, legendId, tableId, map, getVal, yFormat, tipFormat, color) {
    const months = monthsInRange().filter(mo => map.has(mo));
    const years = [...new Set(months.map(mo => mo.slice(0, 4)))].sort();
    const curYear = years[years.length - 1];
    const series = years.map(y => ({
      name: y,
      color: y === curYear ? color : 'var(--deemph)',
      width: y === curYear ? 2.5 : 2,
      values: Array.from({ length: 12 }, (_, i) => {
        const r = map.get(`${y}-${String(i + 1).padStart(2, '0')}`);
        return r && months.includes(r.month) ? getVal(r) : null;
      }),
    }));
    yoyChart($(chartId), series, { yFormat, tipFormat });
    const items = [{ label: curYear, color, line: true }];
    if (years.length > 1) {
      items.push({
        label: years.length === 2 ? years[0] : `${years[0]}–${years[years.length - 2]}`,
        color: 'var(--deemph)', line: true,
      });
    }
    legend(legendId, items);
    fillTable(tableId, ['Month', ...years], MONTH_NAMES.map((mn, i) =>
      [mn, ...series.map(s => s.values[i] != null ? tipFormat(s.values[i]) : null)]));
  }

  function renderScatters() {
    const months = monthsInRange();
    const ePts = months.filter(mo => elecM.has(mo)).map(mo => elecM.get(mo)).map(r => ({
      x: r.avgTempF, y: r.kwh,
      tipTitle: monthLabel(r.month),
      tipRows: [
        { label: 'Usage', value: `${fmtInt(r.kwh)} kWh` },
        { label: 'Avg temp', value: `${r.avgTempF.toFixed(1)}°F` },
      ],
    }));
    scatterChart($('elecScatter'), ePts, { color: UTIL.elec.color, xTitle: 'Average temperature (°F)' });
    fillTable('elecScatterTable', ['Month', 'Avg temp', 'kWh'],
      months.filter(mo => elecM.has(mo)).map(mo => elecM.get(mo)).map(r =>
        [monthLabel(r.month), r.avgTempF.toFixed(1) + '°F', fmtInt(r.kwh)]));

    const gPts = months
      .filter(mo => gasM.has(mo) && elecM.has(mo))
      .map(mo => ({ g: gasM.get(mo), t: elecM.get(mo).avgTempF }))
      .map(({ g, t }) => ({
        x: t, y: g.dth,
        tipTitle: monthLabel(g.month),
        tipRows: [
          { label: 'Usage', value: `${fmt1(g.dth)} Dth` },
          { label: 'Avg temp', value: `${t.toFixed(1)}°F` },
        ],
      }));
    scatterChart($('gasScatter'), gPts, { color: UTIL.gas.color, xTitle: 'Average temperature (°F), from electric bill' });
    fillTable('gasScatterTable', ['Month', 'Avg temp', 'Dth'],
      months.filter(mo => gasM.has(mo) && elecM.has(mo)).map(mo =>
        [monthLabel(mo), elecM.get(mo).avgTempF.toFixed(1) + '°F', fmt1(gasM.get(mo).dth)]));
  }

  function renderDaily() {
    const rows = DATA.electricityDaily;
    columnChart($('dailyChart'), rows.map(r => ({
      label: dayLabel(r.date),
      tipTitle: r.date,
      tipRows: [
        { label: 'Usage', value: `${fmt1(r.kwh)} kWh` },
        { label: 'Avg temp', value: `${r.avgTempF.toFixed(0)}°F` },
        { label: 'Est. cost', value: fmtMoney0(r.estCost) },
      ],
      segments: [{ name: 'Electricity', value: r.kwh, color: UTIL.elec.color }],
    })), { height: 210 });
    fillTable('dailyTable', ['Date', 'kWh', 'Avg temp', 'Est. cost'], rows.map(r =>
      [r.date, fmt1(r.kwh), r.avgTempF.toFixed(1) + '°F', fmtMoney0(r.estCost)]));
  }

  function renderAll() {
    renderKpis();
    renderSpend();
    renderProjections();
    renderUsageCards();
    renderYoy('water', 'waterYoy', 'waterYoyLegend', 'waterYoyTable', waterM,
      r => r.cubicFeet, fmtInt, v => `${fmtInt(v)} cu ft`, UTIL.water.color);
    renderYoy('elec', 'elecYoy', 'elecYoyLegend', 'elecYoyTable', elecM,
      r => r.kwh, fmtInt, v => `${fmtInt(v)} kWh`, UTIL.elec.color);
    renderYoy('gas', 'gasYoy', 'gasYoyLegend', 'gasYoyTable', gasM,
      r => r.dth, fmtInt, v => `${fmt1(v)} Dth`, UTIL.gas.color);
    renderScatters();
    renderDaily();
  }

  // ---------- filters ----------
  $('filters').addEventListener('click', e => {
    const btn = e.target.closest('button[data-range]');
    if (!btn) return;
    state.range = btn.dataset.range === 'all' ? 'all' : Number(btn.dataset.range);
    for (const b of $('filters').querySelectorAll('button')) {
      b.setAttribute('aria-pressed', String(b === btn));
    }
    renderAll();
  });

  let resizeTimer;
  addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderAll, 150);
  });

  $('coverage').textContent = `Data ${monthLabel(allMonths[0])} – ${monthLabel(lastMonth)}.`;
  renderAll();
})();
