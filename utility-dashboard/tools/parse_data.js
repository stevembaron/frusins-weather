#!/usr/bin/env node
// Regenerates data.js from raw utility exports. Files are recognized by their
// header row, so filenames don't matter:
//   - SLC Public Utilities water bill CSV ("Bill Date","Service Period",...)
//   - Rocky Mountain Power monthly CSV (Period,Usage(kwh),...,Billing total)
//   - Rocky Mountain Power daily CSV (Period,Usage(kwh),...,Est. Rounded Amount)
//   - Dominion Energy usage history CSV (Account ID,...,Actual Dth Used,...)
// Gas costs come from the gasBills table below (Dominion account ledger,
// "Billed Charges" rows) — append new bills as they arrive.
//
// Usage: node tools/parse_data.js <exportFolder> <outFile>

const fs = require('fs');
const path = require('path');

// [bill date, billed amount] from the Dominion account ledger
const gasBills = [
  ['2026-07-10', 30.04], ['2026-06-09', 169.62], ['2026-05-11', 71.56],
  ['2026-04-10', 86.95], ['2026-03-10', 161.63], ['2026-02-06', 179.29],
  ['2026-01-08', 189.63], ['2025-12-05', 105.22], ['2025-11-07', 52.06],
  ['2025-10-08', 166.06], ['2025-09-10', 22.35], ['2025-08-12', 28.44],
  ['2025-07-11', 22.89], ['2025-06-12', 305.30], ['2025-05-12', 66.81],
  ['2025-04-09', 114.24], ['2025-03-11', 176.57], ['2025-02-11', 229.40],
  ['2025-01-13', 210.76], ['2024-12-10', 149.94], ['2024-11-13', 80.54],
  ['2024-10-10', 156.26], ['2024-09-11', 142.72], ['2024-08-12', 25.34],
  ['2024-07-11', 109.26], ['2024-06-12', 302.80], ['2024-05-10', 132.39],
  ['2024-04-10', 205.45], ['2024-03-12', 247.86], ['2024-02-12', 320.59],
  ['2024-01-11', 326.40], ['2023-12-12', 249.56], ['2023-11-09', 86.55],
  ['2023-10-11', 272.18], ['2023-09-14', 238.00], ['2023-08-10', 31.93],
];

const [, , exportDir, outFile] = process.argv;
if (!exportDir || !outFile) {
  console.error('usage: node tools/parse_data.js <exportFolder> <outFile>');
  process.exit(1);
}

function parseCSV(text) {
  const rows = [];
  let row = [], field = '', inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows.filter(r => r.length > 1 || (r[0] && r[0].trim()));
}

const money = s => Math.round(parseFloat(String(s).replace(/[$,\s]/g, '')) * 100) / 100;
const num = s => parseFloat(String(s).replace(/[,\s]/g, ''));
const pad = n => String(n).padStart(2, '0');

// Classify every CSV in the folder by its header row
const buckets = { water: [], elecMonthly: [], elecDaily: [], gas: [] };
for (const f of fs.readdirSync(exportDir)) {
  if (!f.toLowerCase().endsWith('.csv')) continue;
  const rows = parseCSV(fs.readFileSync(path.join(exportDir, f), 'utf8'));
  if (rows.length < 2) continue;
  const header = rows[0].map(h => h.trim());
  const records = rows.slice(1).map(r => Object.fromEntries(header.map((h, i) => [h.trim(), r[i]])));
  const has = c => header.includes(c);
  if (has('Service Period') && has('Consumption (cubic feet)')) buckets.water.push(...records);
  else if (has('Usage(kwh)') && has('Billing total')) buckets.elecMonthly.push(...records);
  else if (has('Usage(kwh)') && has('Est. Rounded Amount')) buckets.elecDaily.push(...records);
  else if (has('Actual Dth Used')) buckets.gas.push(...records);
  else console.error(`WARN unrecognized CSV skipped: ${f}`);
}

// ---------- Water ----------
const parseMDY = s => { const [m, d, y] = s.split('/').map(Number); return `${y}-${pad(m)}-${pad(d)}`; };
const water = buckets.water.map(r => {
  const [startS, endS] = r['Service Period'].split(' - ').map(s => s.trim());
  const start = parseMDY(startS), end = parseMDY(endS);
  return {
    month: start.slice(0, 7), // periods run ~2nd–1st, so the start month is the consumption month
    periodStart: start,
    periodEnd: end,
    cubicFeet: num(r['Consumption (cubic feet)']),
    cost: money(r['Curr Charges']),
    breakdown: {
      water: money(r['Water']),
      sewer: money(r['Sewer']),
      sanitation: money(r['Sanitation']),
      stormWater: money(r['Storm Water']),
      streetLight: money(r['Street Light']),
      franchiseFee: money(r['Franchise Fee']),
    },
  };
}).sort((a, b) => a.periodStart.localeCompare(b.periodStart));

// ---------- Electricity ----------
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const electricityMonthly = buckets.elecMonthly.map(r => {
  const [mon, year] = r['Period'].split(' ');
  return {
    month: `${year}-${pad(MONTHS.indexOf(mon) + 1)}`,
    kwh: num(r['Usage(kwh)']),
    avgTempF: num(r['Average Temperature']),
    cost: money(r['Billing total']),
  };
}).sort((a, b) => a.month.localeCompare(b.month));

const electricityDaily = buckets.elecDaily.map(r => ({
  date: r['Period'],
  kwh: num(r['Usage(kwh)']),
  avgTempF: num(r['Average Temperature']),
  estCost: money(r['Est. Rounded Amount']),
})).sort((a, b) => a.date.localeCompare(b.date));

// ---------- Gas ----------
const dayMs = 86400000;
const toDate = s => new Date(s + 'T00:00:00Z');
const gasRows = buckets.gas
  .map(r => ({ end: r['End Date'], dth: num(r['Actual Dth Used']), dthWeatherAdj: num(r['Weather Adj. Dth Used']) }))
  .sort((a, b) => a.end.localeCompare(b.end));

const gas = gasRows.map((r, i) => {
  const prev = gasRows[i - 1];
  const start = prev ? new Date(toDate(prev.end).getTime() + dayMs) : null;
  // Consumption month = month containing the period midpoint (export has end dates only)
  const mid = start
    ? new Date((toDate(r.end).getTime() + start.getTime()) / 2)
    : new Date(toDate(r.end).getTime() - 15 * dayMs);
  let cost = null, bestGap = Infinity;
  for (const [d, amt] of gasBills) {
    const gap = Math.abs(toDate(d) - toDate(r.end)) / dayMs;
    if (gap < bestGap) { bestGap = gap; cost = amt; }
  }
  if (bestGap > 7) cost = null;
  return {
    month: mid.toISOString().slice(0, 7),
    periodStart: start ? start.toISOString().slice(0, 10) : null,
    periodEnd: r.end,
    dth: Math.round(r.dth * 100) / 100,
    dthWeatherAdj: Math.round(r.dthWeatherAdj * 100) / 100,
    cost,
  };
});

// ---------- sanity checks & output ----------
for (const [name, rows] of [['water', water], ['electricityMonthly', electricityMonthly], ['gas', gas]]) {
  const seen = new Set();
  for (const r of rows) {
    if (seen.has(r.month)) console.error(`WARN duplicate month in ${name}: ${r.month}`);
    seen.add(r.month);
  }
  if (!rows.length) console.error(`WARN no ${name} rows found`);
}
const unbilled = gas.filter(g => g.cost == null).length;
if (unbilled) console.error(`WARN ${unbilled} gas periods have no matching bill — update gasBills`);

console.log(`water: ${water.length} months | electricity: ${electricityMonthly.length} months + ${electricityDaily.length} days | gas: ${gas.length} periods`);

const out = {
  generated: new Date().toISOString().slice(0, 10),
  location: 'Salt Lake City, UT',
  water, electricityMonthly, electricityDaily, gas,
};
fs.writeFileSync(outFile,
  '// Home utility data — generated by tools/parse_data.js (see README). Do not hand-edit.\n' +
  'window.UTILITY_DATA = ' + JSON.stringify(out, null, 2) + ';\n');
console.log('wrote ' + outFile);
