const LOCATIONS = [
  {
    id: "cleveland-belgrave",
    label: "Saks - Cleveland, OH",
    shortName: "Saks",
    address: "2797 Belgrave Rd, Cleveland, OH 44124",
    latitude: 41.515,
    longitude: -81.485,
  },
  {
    id: "slc-perrys-hollow",
    label: "Barons - Salt Lake City, UT",
    shortName: "Barons",
    address: "1380 E Perrys Hollow Road, Salt Lake City, UT 84103",
    latitude: 40.779,
    longitude: -111.848,
  },
  {
    id: "slc-eastwood",
    label: "Tabaks - Salt Lake City, UT",
    shortName: "Tabaks",
    address: "3675 Eastwood Dr, Salt Lake City, UT 84109",
    latitude: 40.706,
    longitude: -111.813,
  },
  {
    id: "slc-2300e",
    label: "Sterns - Salt Lake City, UT",
    shortName: "Sterns",
    address: "859 S 2300 E, Salt Lake City, UT 84108",
    latitude: 40.751,
    longitude: -111.821,
  },
];

const STORAGE_KEY = "weather-default-location-id";
const LINE_COLORS = ["#0f6df2", "#2aa889", "#f18f01", "#e94f37"];

const ICONS = {
  clear: "☀️",
  partly: "🌤️",
  cloudy: "☁️",
  fog: "🌫️",
  rain: "🌧️",
  snow: "❄️",
  storm: "⛈️",
};

const CODE_LABELS = {
  0: "Clear",
  1: "Mostly Clear",
  2: "Partly Cloudy",
  3: "Cloudy",
  45: "Fog",
  48: "Rime Fog",
  51: "Light Drizzle",
  53: "Drizzle",
  55: "Dense Drizzle",
  56: "Freezing Drizzle",
  57: "Freezing Drizzle",
  61: "Light Rain",
  63: "Rain",
  65: "Heavy Rain",
  66: "Freezing Rain",
  67: "Freezing Rain",
  71: "Light Snow",
  73: "Snow",
  75: "Heavy Snow",
  77: "Snow Grains",
  80: "Rain Showers",
  81: "Rain Showers",
  82: "Heavy Showers",
  85: "Snow Showers",
  86: "Heavy Snow Showers",
  95: "Thunderstorm",
  96: "Thunder + Hail",
  99: "Thunder + Hail",
};

const elements = {
  locationSelect: document.getElementById("locationSelect"),
  saveDefaultBtn: document.getElementById("saveDefaultBtn"),
  defaultNote: document.getElementById("defaultNote"),
  refreshBtn: document.getElementById("refreshBtn"),
  heroPanel: document.getElementById("heroPanel"),
  currentStats: document.getElementById("currentStats"),
  chartLegend: document.getElementById("chartLegend"),
  hourlyChart: document.getElementById("hourlyChart"),
  precipTimeline: document.getElementById("precipTimeline"),
  dailyDetails: document.getElementById("dailyDetails"),
  hourlyDetails: document.getElementById("hourlyDetails"),
  comparisonGrid: document.getElementById("comparisonGrid"),
  updatedAt: document.getElementById("updatedAt"),
  compareCardTemplate: document.getElementById("compareCardTemplate"),
};

let weatherByLocation = {};

function init() {
  LOCATIONS.forEach((location) => {
    const option = document.createElement("option");
    option.value = location.id;
    option.textContent = location.label;
    elements.locationSelect.append(option);
  });

  const defaultId = getDefaultLocationId();
  elements.locationSelect.value = defaultId;
  updateDefaultNote(defaultId);

  elements.locationSelect.addEventListener("change", renderAll);
  elements.saveDefaultBtn.addEventListener("click", () => {
    const selectedId = elements.locationSelect.value;
    localStorage.setItem(STORAGE_KEY, selectedId);
    updateDefaultNote(selectedId, true);
    renderAll();
  });
  elements.refreshBtn.addEventListener("click", loadWeather);

  loadWeather();
}

function getDefaultLocationId() {
  const saved = localStorage.getItem(STORAGE_KEY);
  return LOCATIONS.some((location) => location.id === saved) ? saved : LOCATIONS[0].id;
}

function updateDefaultNote(defaultId, showSaved = false) {
  const location = LOCATIONS.find((entry) => entry.id === defaultId);
  if (!location) return;
  elements.defaultNote.textContent = showSaved
    ? `${location.shortName} saved as your default.`
    : `Current default: ${location.shortName}`;
}

async function loadWeather() {
  elements.heroPanel.innerHTML = '<div class="loading">Loading current weather...</div>';
  elements.currentStats.innerHTML = "";
  elements.hourlyChart.innerHTML = "";
  elements.chartLegend.innerHTML = "";
  elements.precipTimeline.innerHTML = "";
  elements.dailyDetails.innerHTML = "";
  elements.hourlyDetails.innerHTML = "";
  elements.comparisonGrid.innerHTML = "";

  try {
    const results = await Promise.all(LOCATIONS.map((location) => fetchWeather(location)));
    weatherByLocation = results.reduce((acc, item) => {
      acc[item.locationId] = item;
      return acc;
    }, {});
    renderAll();
  } catch (error) {
    elements.heroPanel.innerHTML = '<div class="error">Could not load weather right now. Try refresh in a moment.</div>';
    elements.hourlyChart.innerHTML = '<div class="error">Could not load chart data.</div>';
    elements.updatedAt.textContent = "";
    console.error(error);
  }
}

async function fetchWeather(location) {
  const params = new URLSearchParams({
    latitude: location.latitude,
    longitude: location.longitude,
    current: [
      "temperature_2m",
      "apparent_temperature",
      "relative_humidity_2m",
      "is_day",
      "precipitation",
      "rain",
      "showers",
      "snowfall",
      "weather_code",
      "cloud_cover",
      "pressure_msl",
      "surface_pressure",
      "wind_speed_10m",
      "wind_direction_10m",
      "wind_gusts_10m",
    ].join(","),
    hourly: [
      "temperature_2m",
      "relative_humidity_2m",
      "apparent_temperature",
      "precipitation_probability",
      "precipitation",
      "rain",
      "showers",
      "snowfall",
      "weather_code",
      "cloud_cover",
      "pressure_msl",
      "surface_pressure",
      "wind_speed_10m",
      "wind_direction_10m",
      "wind_gusts_10m",
      "dew_point_2m",
      "uv_index",
      "is_day",
    ].join(","),
    daily: [
      "weather_code",
      "temperature_2m_max",
      "temperature_2m_min",
      "apparent_temperature_max",
      "apparent_temperature_min",
      "sunrise",
      "sunset",
      "daylight_duration",
      "sunshine_duration",
      "uv_index_max",
      "uv_index_clear_sky_max",
      "precipitation_sum",
      "rain_sum",
      "showers_sum",
      "snowfall_sum",
      "precipitation_hours",
      "precipitation_probability_max",
      "wind_speed_10m_max",
      "wind_gusts_10m_max",
      "wind_direction_10m_dominant",
    ].join(","),
    forecast_days: "10",
    temperature_unit: "fahrenheit",
    wind_speed_unit: "mph",
    precipitation_unit: "inch",
    timezone: "auto",
  });

  const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Weather API error for ${location.id}`);
  }

  const payload = await response.json();
  return {
    locationId: location.id,
    location,
    timezone: payload.timezone,
    current: payload.current,
    hourly: payload.hourly,
    daily: payload.daily,
  };
}

function renderAll() {
  if (!Object.keys(weatherByLocation).length) return;

  const selectedLocationId = elements.locationSelect.value || getDefaultLocationId();
  const primary = weatherByLocation[selectedLocationId] || weatherByLocation[getDefaultLocationId()];

  tryRender(() => renderHero(primary), elements.heroPanel);
  tryRender(() => renderCurrentStats(primary), elements.currentStats);
  tryRender(() => renderHourlyCharts(primary), elements.hourlyChart);
  tryRender(() => renderDailyDetails(primary), elements.dailyDetails);
  tryRender(() => renderHourlyDetails(primary), elements.hourlyDetails);
  tryRender(() => renderComparison(primary), elements.comparisonGrid);

  const currentTime = new Date().toLocaleString([], {
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  });
  elements.updatedAt.textContent = `Updated ${currentTime}`;
}

function renderHero(data) {
  const weatherCode = data.current.weather_code;
  const icon = iconForCode(weatherCode);
  const label = CODE_LABELS[weatherCode] || "Weather";

  const dayMarkup = data.daily.time
    .slice(0, 10)
    .map((date, index) => {
      const day = new Date(`${date}T12:00:00`).toLocaleDateString([], { weekday: "short" });
      const code = data.daily.weather_code[index];
      const max = round(data.daily.temperature_2m_max[index]);
      const min = round(data.daily.temperature_2m_min[index]);
      const p = round(data.daily.precipitation_probability_max[index]);
      return `
        <div class="forecast-day">
          <div>${day}</div>
          <div class="weather-icon">${iconForCode(code)}</div>
          <strong>${max}F / ${min}F</strong>
          <div class="muted">${p}% precip</div>
        </div>
      `;
    })
    .join("");

  elements.heroPanel.innerHTML = `
    <div class="hero-top">
      <div>
        <h2>${data.location.shortName}</h2>
        <p class="hero-address">${data.location.address}</p>
        <p class="muted">Timezone: ${data.timezone}</p>
      </div>
      <div class="hero-weather">
        <span class="weather-icon">${icon}</span>
        <div>
          <div class="hero-temp">${round(data.current.temperature_2m)}F</div>
          <div class="hero-code">${label}</div>
        </div>
      </div>
    </div>
    <div class="hero-forecast">${dayMarkup}</div>
  `;
}

function renderCurrentStats(primary) {
  const c = primary.current;
  const stats = [
    ["Feels Like", `${round(c.apparent_temperature)}F`],
    ["Humidity", `${round(c.relative_humidity_2m)}%`],
    ["Cloud Cover", `${round(c.cloud_cover)}%`],
    ["Precipitation", `${fixed(c.precipitation, 2)} in`],
    ["Rain", `${fixed(c.rain, 2)} in`],
    ["Showers", `${fixed(c.showers, 2)} in`],
    ["Snowfall", `${fixed(c.snowfall, 2)} in`],
    ["Wind", `${round(c.wind_speed_10m)} mph`],
    ["Wind Gust", `${round(c.wind_gusts_10m)} mph`],
    ["Wind Direction", `${compass(c.wind_direction_10m)}`],
    ["Pressure MSL", `${fixed(hPaToInHg(c.pressure_msl), 2)} inHg`],
    ["Surface Pressure", `${fixed(hPaToInHg(c.surface_pressure), 2)} inHg`],
    ["Day/Night", c.is_day === 1 ? "Day" : "Night"],
  ];

  elements.currentStats.innerHTML = stats
    .map(
      ([label, value]) => `
      <div class="stat-card">
        <span>${label}</span>
        <strong>${value}</strong>
      </div>
    `,
    )
    .join("");
}

function renderDailyDetails(primary) {
  const d = primary.daily;
  if (!d || !Array.isArray(d.time) || d.time.length === 0) {
    elements.dailyDetails.innerHTML = '<div class="muted">Daily forecast data is unavailable.</div>';
    return;
  }
  const cards = d.time
    .slice(0, 10)
    .map((date, i) => {
      const dateLabel = formatDate(`${date}T12:00:00`, { weekday: "short", month: "short", day: "numeric" });
      const sunrise = formatTime(valueAt(d.sunrise, i), { hour: "numeric", minute: "2-digit" });
      const sunset = formatTime(valueAt(d.sunset, i), { hour: "numeric", minute: "2-digit" });
      const code = valueAt(d.weather_code, i);
      return `
        <article class="daily-day-card">
          <div class="daily-day-head">
            <h4>${dateLabel}</h4>
            <span class="weather-icon">${iconForCode(code)}</span>
          </div>
          <p class="muted">${CODE_LABELS[code] || "Weather"}</p>
          <p><strong>${round(valueAt(d.temperature_2m_max, i))}F / ${round(valueAt(d.temperature_2m_min, i))}F</strong> temp</p>
          <p>Feels: ${round(valueAt(d.apparent_temperature_max, i))}F / ${round(valueAt(d.apparent_temperature_min, i))}F</p>
          <p>Precip: ${round(valueAt(d.precipitation_probability_max, i))}% • ${fixed(valueAt(d.precipitation_sum, i), 2)} in</p>
          <p>Rain/Showers/Snow: ${fixed(valueAt(d.rain_sum, i), 2)} / ${fixed(valueAt(d.showers_sum, i), 2)} / ${fixed(valueAt(d.snowfall_sum, i), 2)} in</p>
          <p>Wind: ${compass(valueAt(d.wind_direction_10m_dominant, i))} ${round(valueAt(d.wind_speed_10m_max, i))} mph • gust ${round(valueAt(d.wind_gusts_10m_max, i))} mph</p>
          <p>UV: ${fixed(valueAt(d.uv_index_max, i), 1)} (clear ${fixed(valueAt(d.uv_index_clear_sky_max, i), 1)})</p>
          <p>Sun: ${sunrise} - ${sunset}</p>
          <p>Daylight: ${durationH(valueAt(d.daylight_duration, i))} • Sunshine: ${durationH(valueAt(d.sunshine_duration, i))}</p>
        </article>
      `;
    })
    .join("");

  elements.dailyDetails.innerHTML = `<div class="daily-cards">${cards}</div>`;
}

function renderHourlyDetails(primary) {
  const h = primary.hourly;
  if (!h || !Array.isArray(h.time) || h.time.length === 0) {
    elements.hourlyDetails.innerHTML = '<div class="muted">Hourly detail data is unavailable.</div>';
    return;
  }
  const items = h.time.slice(0, 24).map((timestamp, i) => {
    const timeLabel = formatTime(timestamp, { hour: "numeric", minute: "2-digit" });
    const weatherCode = valueAt(h.weather_code, i);
    const weather = CODE_LABELS[weatherCode] || "Weather";
    const icon = iconForCode(weatherCode);
    const temp = round(valueAt(h.temperature_2m, i));
    const feels = round(valueAt(h.apparent_temperature, i));
    const precipChance = round(valueAt(h.precipitation_probability, i));
    const rainAmount = fixed(valueAt(h.precipitation, i), 2);
    const windDir = compass(valueAt(h.wind_direction_10m, i));
    const windSpeed = round(valueAt(h.wind_speed_10m, i));
    const windGust = round(valueAt(h.wind_gusts_10m, i));
    const humidity = round(valueAt(h.relative_humidity_2m, i));
    const uv = fixed(valueAt(h.uv_index, i), 1);
    return `
      <article class="hourly-card">
        <div class="hourly-top">
          <h4>${timeLabel}</h4>
          <span class="precip-chip">${precipChance}%</span>
        </div>
        <div class="hourly-icon-row">
          <span class="hourly-icon">${icon}</span>
          <span>${weather}</span>
        </div>
        <p class="hourly-temp">${temp}F</p>
        <div class="hourly-chip-grid">
          <span class="hourly-chip">Feels ${feels}F</span>
          <span class="hourly-chip">Wind ${windDir} ${windSpeed}</span>
          <span class="hourly-chip">Gust ${windGust} mph</span>
          <span class="hourly-chip">Humidity ${humidity}%</span>
          <span class="hourly-chip">UV ${uv}</span>
          <span class="hourly-chip">Rain ${rainAmount} in</span>
        </div>
      </article>
    `;
  });

  elements.hourlyDetails.innerHTML = items.join("");
}

function renderHourlyCharts(primary) {
  renderHourlyTemperatureChart();
  renderPrecipTimeline(primary);
}

function renderHourlyTemperatureChart() {
  const firstData = weatherByLocation[LOCATIONS[0].id];
  if (!firstData?.hourly?.time || firstData.hourly.time.length < 24) {
    elements.hourlyChart.innerHTML = '<div class="muted">Hourly chart data is unavailable.</div>';
    elements.chartLegend.innerHTML = "";
    return;
  }
  const hourLabels = firstData.hourly.time.slice(0, 24).map((stamp) =>
    new Date(stamp).toLocaleTimeString([], { hour: "numeric" }),
  );

  const series = LOCATIONS.map((location, index) => ({
    name: location.shortName,
    color: LINE_COLORS[index],
    temps: weatherByLocation[location.id].hourly.temperature_2m.slice(0, 24),
  }));

  const allTemps = series.flatMap((line) => line.temps);
  const minTemp = Math.floor(Math.min(...allTemps) - 2);
  const maxTemp = Math.ceil(Math.max(...allTemps) + 2);

  const width = 1000;
  const height = 320;
  const topPad = 24;
  const rightPad = 18;
  const bottomPad = 48;
  const leftPad = 42;
  const plotWidth = width - leftPad - rightPad;
  const plotHeight = height - topPad - bottomPad;

  const xForIndex = (idx) => leftPad + (idx / 23) * plotWidth;
  const yForTemp = (temp) => topPad + ((maxTemp - temp) / (maxTemp - minTemp || 1)) * plotHeight;

  const horizontalGuides = [0, 0.25, 0.5, 0.75, 1]
    .map((fraction) => {
      const y = topPad + fraction * plotHeight;
      return `<line x1="${leftPad}" y1="${y}" x2="${leftPad + plotWidth}" y2="${y}" stroke="#e3ebfa" stroke-width="1" />`;
    })
    .join("");

  const lines = series
    .map((line) => {
      const points = line.temps.map((temp, idx) => `${xForIndex(idx)},${yForTemp(temp)}`).join(" ");
      return `<polyline points="${points}" fill="none" stroke="${line.color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" />`;
    })
    .join("");

  const axisLabels = [0, 6, 12, 18, 23]
    .map((idx) => {
      const x = xForIndex(idx);
      return `<text x="${x}" y="${height - 18}" text-anchor="middle" fill="#576078" font-size="12">${hourLabels[idx]}</text>`;
    })
    .join("");

  const tempLabels = [minTemp, minTemp + (maxTemp - minTemp) / 2, maxTemp]
    .map((temp) => {
      const rounded = Math.round(temp);
      const y = yForTemp(rounded);
      return `<text x="6" y="${y + 4}" fill="#576078" font-size="12">${rounded}F</text>`;
    })
    .join("");

  elements.hourlyChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="24-hour temperature chart for all four locations">
      ${horizontalGuides}
      ${lines}
      ${axisLabels}
      ${tempLabels}
    </svg>
  `;

  elements.chartLegend.innerHTML = series
    .map(
      (line) => `
      <span class="legend-pill">
        <span class="legend-dot" style="background:${line.color}"></span>
        ${line.name}
      </span>
    `,
    )
    .join("");
}

function renderPrecipTimeline(primary) {
  if (!primary?.hourly?.precipitation_probability || primary.hourly.precipitation_probability.length < 24) {
    elements.precipTimeline.innerHTML = '<div class="muted">Precipitation timeline data is unavailable.</div>';
    return;
  }
  const next24 = primary.hourly.precipitation_probability.slice(0, 24);
  const bars = next24
    .map((value, idx) => {
      const label = new Date(primary.hourly.time[idx]).toLocaleTimeString([], { hour: "numeric" });
      const height = Math.max(4, Math.round(value));
      const showLabel = idx % 3 === 0 || idx === 23;
      return `
        <div class="precip-hour">
          <div class="bar" style="height:${height}px"></div>
          <div class="hour-label">${showLabel ? label : ""}</div>
        </div>
      `;
    })
    .join("");

  const peakChance = Math.max(...next24);
  elements.precipTimeline.innerHTML = `
    <div class="precip-bars">${bars}</div>
    <div class="timeline-meta">Peak chance in next 24h: <strong>${peakChance}%</strong></div>
  `;
}

function renderComparison(primary) {
  const primaryTemp = primary.current.temperature_2m;
  elements.comparisonGrid.innerHTML = "";

  LOCATIONS.forEach((location) => {
    const data = weatherByLocation[location.id];
    if (!data) return;

    const card = elements.compareCardTemplate.content.cloneNode(true);
    card.querySelector(".compare-name").textContent = location.shortName;
    card.querySelector(".code-pill").textContent = CODE_LABELS[data.current.weather_code] || "Weather";
    card.querySelector(".compare-address").textContent = location.address;
    card.querySelector(".weather-icon").textContent = iconForCode(data.current.weather_code);
    card.querySelector(".temp-main").textContent = `${round(data.current.temperature_2m)}F`;

    const delta = data.current.temperature_2m - primaryTemp;
    const deltaNode = card.querySelector(".temp-delta");
    if (location.id === primary.locationId) {
      deltaNode.textContent = "Primary";
    } else {
      const sign = delta > 0 ? "+" : "";
      deltaNode.textContent = `${sign}${Math.round(delta)}F vs primary`;
      deltaNode.classList.add(delta > 0 ? "positive" : "negative");
    }

    card.querySelector(".feels").textContent = `${round(data.current.apparent_temperature)}F`;
    card.querySelector(".humidity").textContent = `${round(data.current.relative_humidity_2m)}%`;
    card.querySelector(".wind").textContent = `${round(data.current.wind_speed_10m)} mph`;
    card.querySelector(".precip").textContent = `${round(data.daily.precipitation_probability_max[0])}%`;

    const makePrimaryBtn = card.querySelector(".make-primary-btn");
    if (location.id === primary.locationId) {
      makePrimaryBtn.textContent = "Current Primary";
      makePrimaryBtn.disabled = true;
    } else {
      makePrimaryBtn.addEventListener("click", () => {
        elements.locationSelect.value = location.id;
        renderAll();
      });
    }

    elements.comparisonGrid.append(card);
  });
}

function iconForCode(code) {
  if (code === 0) return ICONS.clear;
  if ([1, 2].includes(code)) return ICONS.partly;
  if ([3].includes(code)) return ICONS.cloudy;
  if ([45, 48].includes(code)) return ICONS.fog;
  if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return ICONS.rain;
  if ([71, 73, 75, 77, 85, 86].includes(code)) return ICONS.snow;
  if ([95, 96, 99].includes(code)) return ICONS.storm;
  return "🌡️";
}

function fixed(value, digits = 1) {
  return Number.isFinite(value) ? Number(value).toFixed(digits) : "--";
}

function round(value) {
  return Number.isFinite(value) ? Math.round(value) : "--";
}

function durationH(seconds) {
  if (!Number.isFinite(seconds)) return "--";
  return `${(seconds / 3600).toFixed(1)}h`;
}

function compass(degrees) {
  if (!Number.isFinite(degrees)) return "--";
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return dirs[Math.round((degrees % 360) / 45) % 8];
}

function hPaToInHg(value) {
  if (!Number.isFinite(value)) return undefined;
  return value * 0.0295299831;
}

function valueAt(values, index) {
  return Array.isArray(values) ? values[index] : undefined;
}

function formatDate(value, options) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--";
  return parsed.toLocaleDateString([], options);
}

function formatTime(value, options) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--";
  return parsed.toLocaleTimeString([], options);
}

function tryRender(renderFn, fallbackElement) {
  try {
    renderFn();
  } catch (error) {
    console.error(error);
    if (fallbackElement) {
      fallbackElement.innerHTML = '<div class="error">Data for this section is temporarily unavailable.</div>';
    }
  }
}

init();
