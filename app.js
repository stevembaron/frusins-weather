"use strict";

const STORAGE_KEY = "pool-tracker:v1";
const DEFAULT_LOCATION = { lat: 40.78, lon: -111.83, name: "Perrys Hollow / SLC" };

// WMO weather interpretation codes -> emoji + label.
const WEATHER_CODES = {
  0: ["☀️", "Clear"],
  1: ["🌤️", "Mostly clear"],
  2: ["⛅", "Partly cloudy"],
  3: ["☁️", "Overcast"],
  45: ["🌫️", "Fog"],
  48: ["🌫️", "Rime fog"],
  51: ["🌦️", "Light drizzle"],
  53: ["🌦️", "Drizzle"],
  55: ["🌧️", "Heavy drizzle"],
  56: ["🌧️", "Freezing drizzle"],
  57: ["🌧️", "Freezing drizzle"],
  61: ["🌦️", "Light rain"],
  63: ["🌧️", "Rain"],
  65: ["🌧️", "Heavy rain"],
  66: ["🌧️", "Freezing rain"],
  67: ["🌧️", "Freezing rain"],
  71: ["🌨️", "Light snow"],
  73: ["🌨️", "Snow"],
  75: ["❄️", "Heavy snow"],
  77: ["🌨️", "Snow grains"],
  80: ["🌦️", "Rain showers"],
  81: ["🌧️", "Rain showers"],
  82: ["⛈️", "Violent showers"],
  85: ["🌨️", "Snow showers"],
  86: ["❄️", "Snow showers"],
  95: ["⛈️", "Thunderstorm"],
  96: ["⛈️", "Storm w/ hail"],
  99: ["⛈️", "Storm w/ hail"],
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const el = {
  form: document.getElementById("logForm"),
  date: document.getElementById("dateInput"),
  note: document.getElementById("noteInput"),
  logButton: document.getElementById("logButton"),
  logStatus: document.getElementById("logStatus"),
  stats: document.getElementById("statsGrid"),
  seasonSelect: document.getElementById("seasonSelect"),
  monthChart: document.getElementById("monthChart"),
  tempChart: document.getElementById("tempChart"),
  dayList: document.getElementById("dayList"),
  dayCount: document.getElementById("dayCount"),
  emptyState: document.getElementById("emptyState"),
  locInput: document.getElementById("locInput"),
  locSave: document.getElementById("locSave"),
  exportButton: document.getElementById("exportButton"),
  importButton: document.getElementById("importButton"),
  importFile: document.getElementById("importFile"),
};

let state = loadState();
let selectedSeason = "all";

init();

function init() {
  el.date.value = todayStr();
  el.date.max = todayStr();
  el.locInput.value = `${state.location.lat}, ${state.location.lon}`;
  selectedSeason = String(currentSeasonDefault());

  el.form.addEventListener("submit", onAddDay);
  el.seasonSelect.addEventListener("change", () => {
    selectedSeason = el.seasonSelect.value;
    render();
  });
  el.locSave.addEventListener("click", onSaveLocation);
  el.exportButton.addEventListener("click", onExport);
  el.importButton.addEventListener("click", () => el.importFile.click());
  el.importFile.addEventListener("change", onImport);

  render();
}

/* ---------- State ---------- */

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        version: 1,
        location: parsed.location || { ...DEFAULT_LOCATION },
        days: Array.isArray(parsed.days) ? parsed.days : [],
      };
    }
  } catch (err) {
    console.error("Could not read saved data", err);
  }
  return { version: 1, location: { ...DEFAULT_LOCATION }, days: [] };
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (err) {
    console.error("Could not save data", err);
    setStatus("Could not save to this browser's storage.", "err");
  }
}

/* ---------- Add / edit / delete ---------- */

async function onAddDay(event) {
  event.preventDefault();
  const date = el.date.value;
  if (!date) return;

  if (state.days.some((d) => d.date === date)) {
    setStatus("That day is already logged.", "err");
    return;
  }

  const entry = {
    id: cryptoId(),
    date,
    note: el.note.value.trim(),
    weather: null,
  };
  state.days.push(entry);
  saveState();
  el.note.value = "";
  setStatus("Day added — fetching weather…", "ok");
  render();

  await attachWeather(entry);
  render();
}

async function attachWeather(entry) {
  try {
    entry.weather = await fetchWeather(entry.date);
    setStatus("Saved with weather.", "ok");
  } catch (err) {
    console.error(err);
    entry.weather = null;
    setStatus("Saved, but weather lookup failed. Use ↻ to retry later.", "err");
  }
  saveState();
}

function deleteDay(id) {
  const entry = state.days.find((d) => d.id === id);
  if (!entry) return;
  if (!confirm(`Remove ${formatDate(entry.date)}?`)) return;
  state.days = state.days.filter((d) => d.id !== id);
  saveState();
  render();
}

async function retryWeather(id) {
  const entry = state.days.find((d) => d.id === id);
  if (!entry) return;
  setStatus("Fetching weather…", "");
  await attachWeather(entry);
  render();
}

/* ---------- Weather ---------- */

async function fetchWeather(dateStr) {
  const { lat, lon } = state.location;
  const params = new URLSearchParams({
    latitude: lat,
    longitude: lon,
    daily: "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
    temperature_unit: "fahrenheit",
    precipitation_unit: "inch",
    timezone: "auto",
    start_date: dateStr,
    end_date: dateStr,
  });

  // The forecast API covers recent + upcoming days; the archive API covers
  // older history (with a few days' lag), so pick based on how long ago it was.
  const daysAgo = (Date.now() - parseLocalDate(dateStr).getTime()) / 86400000;
  const base =
    daysAgo > 80
      ? "https://archive-api.open-meteo.com/v1/archive"
      : "https://api.open-meteo.com/v1/forecast";

  const res = await fetch(`${base}?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Open-Meteo returned ${res.status}`);
  const json = await res.json();
  const d = json.daily;
  if (!d || !d.time || !d.time.length) throw new Error("No weather data for that day");

  return {
    tempMax: numOrNull(d.temperature_2m_max[0]),
    tempMin: numOrNull(d.temperature_2m_min[0]),
    precip: numOrNull(d.precipitation_sum[0]),
    code: numOrNull(d.weather_code[0]),
    fetchedAt: Date.now(),
  };
}

/* ---------- Rendering ---------- */

function render() {
  renderSeasonOptions();
  const days = filteredDays();
  renderStats(days);
  renderMonthChart(days);
  renderTempChart(days);
  renderDayList(days);
}

function renderSeasonOptions() {
  const years = [...new Set(state.days.map((d) => seasonOf(d.date)))].sort((a, b) => b - a);
  const options = ["all", ...years.map(String)];
  if (!options.includes(selectedSeason)) selectedSeason = options[0] || "all";

  el.seasonSelect.innerHTML = options
    .map((opt) => {
      const label = opt === "all" ? "All seasons" : opt;
      const sel = opt === selectedSeason ? " selected" : "";
      return `<option value="${opt}"${sel}>${label}</option>`;
    })
    .join("");
}

function renderStats(days) {
  const withTemp = days.filter((d) => d.weather && d.weather.tempMax != null);
  const avgHigh = withTemp.length
    ? Math.round(withTemp.reduce((s, d) => s + d.weather.tempMax, 0) / withTemp.length)
    : null;
  const warmest = withTemp.reduce(
    (best, d) => (best == null || d.weather.tempMax > best.weather.tempMax ? d : best),
    null,
  );
  const rainyDays = days.filter((d) => d.weather && d.weather.precip > 0.01).length;

  const stats = [
    [days.length, selectedSeason === "all" ? "Total pool days" : `Days in ${selectedSeason}`],
    [avgHigh != null ? `${avgHigh}°F` : "—", "Avg high temp"],
    [warmest ? `${Math.round(warmest.weather.tempMax)}°F` : "—", "Warmest pool day"],
    [rainyDays, "Days with rain"],
  ];

  el.stats.innerHTML = stats
    .map(([value, label]) => `<div class="stat"><div class="value">${value}</div><span class="label">${label}</span></div>`)
    .join("");
}

function renderMonthChart(days) {
  const counts = new Array(12).fill(0);
  days.forEach((d) => {
    counts[parseLocalDate(d.date).getMonth()]++;
  });
  const active = counts.map((c, i) => [i, c]).filter(([, c]) => c > 0);
  const max = Math.max(1, ...counts);

  if (!active.length) {
    el.monthChart.innerHTML = `<p class="chart-empty">No days to chart yet.</p>`;
    return;
  }
  el.monthChart.innerHTML = active
    .map(
      ([i, c]) => `
        <div class="bar-row">
          <span>${MONTHS[i]}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${(c / max) * 100}%"></span></span>
          <span class="bar-value">${c}</span>
        </div>`,
    )
    .join("");
}

function renderTempChart(days) {
  const withTemp = days
    .filter((d) => d.weather && d.weather.tempMax != null)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (!withTemp.length) {
    el.tempChart.innerHTML = `<p class="chart-empty">No weather captured yet.</p>`;
    return;
  }
  const temps = withTemp.map((d) => d.weather.tempMax);
  const min = Math.min(...temps);
  const max = Math.max(...temps);
  const span = Math.max(1, max - min);

  el.tempChart.innerHTML = withTemp
    .map((d) => {
      const t = d.weather.tempMax;
      const pct = 12 + ((t - min) / span) * 88; // keep a visible minimum width
      return `
        <div class="bar-row">
          <span>${shortDate(d.date)}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></span>
          <span class="bar-value">${Math.round(t)}°</span>
        </div>`;
    })
    .join("");
}

function renderDayList(days) {
  const sorted = [...days].sort((a, b) => b.date.localeCompare(a.date));
  el.dayCount.textContent = sorted.length ? `(${sorted.length})` : "";
  el.emptyState.style.display = state.days.length ? "none" : "block";

  el.dayList.innerHTML = sorted
    .map((d) => {
      const w = d.weather;
      const [icon, label] = w && w.code != null ? WEATHER_CODES[w.code] || ["🌡️", "Unknown"] : ["⏳", ""];
      let weatherText;
      if (w) {
        const parts = [label];
        if (w.tempMax != null) parts.push(`${Math.round(w.tempMax)}° / ${Math.round(w.tempMin)}°F`);
        if (w.precip != null && w.precip > 0.01) parts.push(`${w.precip.toFixed(2)}" rain`);
        weatherText = parts.filter(Boolean).join(" · ");
      } else {
        weatherText = "Weather not available";
      }
      const retryBtn = w
        ? ""
        : `<button class="icon-btn" data-retry="${d.id}" title="Retry weather">↻</button>`;
      const note = d.note ? `<div class="note">${escapeHtml(d.note)}</div>` : "";
      return `
        <li class="day">
          <span class="icon" aria-hidden="true">${icon}</span>
          <div class="body">
            <div class="date">${formatDate(d.date)}</div>
            <div class="weather">${escapeHtml(weatherText)}</div>
            ${note}
          </div>
          <div class="actions">
            ${retryBtn}
            <button class="icon-btn danger" data-delete="${d.id}" title="Delete">✕</button>
          </div>
        </li>`;
    })
    .join("");

  el.dayList.querySelectorAll("[data-delete]").forEach((b) =>
    b.addEventListener("click", () => deleteDay(b.dataset.delete)),
  );
  el.dayList.querySelectorAll("[data-retry]").forEach((b) =>
    b.addEventListener("click", () => retryWeather(b.dataset.retry)),
  );
}

/* ---------- Settings & backup ---------- */

function onSaveLocation() {
  const match = el.locInput.value.split(",").map((s) => parseFloat(s.trim()));
  if (match.length !== 2 || !Number.isFinite(match[0]) || !Number.isFinite(match[1])) {
    setStatus("Enter location as: latitude, longitude (e.g. 40.78, -111.83).", "err");
    return;
  }
  state.location = { lat: match[0], lon: match[1], name: "Custom" };
  saveState();
  setStatus("Location saved. New days will use it; use ↻ to refresh older days.", "ok");
}

function onExport() {
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `pool-days-${todayStr()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function onImport(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const incoming = JSON.parse(reader.result);
      const incomingDays = Array.isArray(incoming.days) ? incoming.days : [];
      // Merge by date so importing on a second device combines logs.
      const byDate = new Map(state.days.map((d) => [d.date, d]));
      let added = 0;
      incomingDays.forEach((d) => {
        if (!d || !d.date) return;
        if (!byDate.has(d.date)) {
          byDate.set(d.date, { id: d.id || cryptoId(), date: d.date, note: d.note || "", weather: d.weather || null });
          added++;
        }
      });
      state.days = [...byDate.values()];
      if (incoming.location) state.location = incoming.location;
      el.locInput.value = `${state.location.lat}, ${state.location.lon}`;
      saveState();
      render();
      setStatus(`Imported ${added} new day${added === 1 ? "" : "s"}.`, "ok");
    } catch (err) {
      console.error(err);
      setStatus("That file could not be read as a pool backup.", "err");
    }
    el.importFile.value = "";
  };
  reader.readAsText(file);
}

/* ---------- Helpers ---------- */

function filteredDays() {
  if (selectedSeason === "all") return state.days;
  return state.days.filter((d) => String(seasonOf(d.date)) === selectedSeason);
}

function seasonOf(dateStr) {
  return parseLocalDate(dateStr).getFullYear();
}

function currentSeasonDefault() {
  const years = state.days.map((d) => seasonOf(d.date));
  return years.length ? Math.max(...years) : new Date().getFullYear();
}

function setStatus(message, kind) {
  el.logStatus.textContent = message;
  el.logStatus.className = `status ${kind || ""}`.trim();
}

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function parseLocalDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function formatDate(dateStr) {
  return parseLocalDate(dateStr).toLocaleDateString(undefined, {
    weekday: "short",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function shortDate(dateStr) {
  const d = parseLocalDate(dateStr);
  return `${MONTHS[d.getMonth()].slice(0, 1)}${d.getDate()}`;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function numOrNull(v) {
  return Number.isFinite(v) ? v : null;
}

function cryptoId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
