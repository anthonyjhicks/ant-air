function buildGradient(ctx, color) {
  const gradient = ctx.createLinearGradient(0, 0, 0, 300);
  gradient.addColorStop(0, color);
  gradient.addColorStop(1, "rgba(255, 255, 255, 0)");
  return gradient;
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

function withAlpha(color, alpha) {
  const value = String(color || "").trim();
  const hex = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    let raw = hex[1];
    if (raw.length === 3) {
      raw = raw
        .split("")
        .map((ch) => ch + ch)
        .join("");
    }
    const r = parseInt(raw.slice(0, 2), 16);
    const g = parseInt(raw.slice(2, 4), 16);
    const b = parseInt(raw.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  const rgb = value.match(/^rgba?\(([^)]+)\)$/i);
  if (rgb) {
    const parts = rgb[1].split(",").slice(0, 3).map((part) => part.trim());
    return `rgba(${parts.join(", ")}, ${alpha})`;
  }
  return value;
}

function isDarkTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark";
}

function chartTheme() {
  const series = [
    cssVar("--chart-1", "#2a4bc4"),
    cssVar("--chart-2", "#e0a800"),
    cssVar("--chart-3", "#0f8b8d"),
    cssVar("--chart-4", "#d95d39"),
    cssVar("--chart-5", "#6b4fbb"),
    cssVar("--chart-6", "#8a93a8"),
    cssVar("--chart-7", "#2f9e44"),
    cssVar("--chart-8", "#c2255c"),
  ];
  return {
    c1: series[0],
    c2: series[1],
    c3: series[2],
    c4: series[3],
    c5: series[4],
    c6: series[5],
    c7: series[6],
    c8: series[7],
    series,
    axis: cssVar("--chart-axis", "#5f667b"),
    grid: cssVar("--chart-grid", "rgba(27, 32, 51, 0.08)"),
    tooltipBg: cssVar("--chart-tooltip-bg", "#1b2033"),
    tooltipTitle: cssVar("--chart-tooltip-title", "#ffffff"),
    tooltipBody: cssVar("--chart-tooltip-body", "#e6e9f2"),
    fontFamily: cssVar("--font-body", "system-ui, sans-serif"),
    monoFamily: cssVar("--font-mono", "ui-monospace, monospace"),
  };
}

function mapTileUrl() {
  // OpenStreetMap's standard tiles need no API key; the dark theme re-tints
  // them with a CSS filter (see .leaflet-tile-pane in styles.css).
  return "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
}

function baseAxisOptions(title) {
  const theme = chartTheme();
  return {
    title: {
      display: true,
      text: title,
      color: theme.axis,
      font: { size: 11, weight: "600", family: theme.monoFamily },
    },
    ticks: {
      color: theme.axis,
      font: { size: 11, family: theme.monoFamily },
    },
    grid: {
      color: theme.grid,
    },
    border: {
      color: theme.grid,
    },
  };
}

function normalizeLabel(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  const normalized = value.trim().toLowerCase().replace(/\s+/g, " ");
  return normalized || null;
}

const DISTANCE_UNITS = {
  mi: {
    short: "mi",
    name: "Miles",
    summaryLabel: "Total Miles",
    chartTitle: "Flights & Miles by Month",
    axisLabel: "Miles",
    datasetLabel: "Miles",
  },
  km: {
    short: "km",
    name: "Kilometers",
    summaryLabel: "Total Kilometers",
    chartTitle: "Flights & Kilometers by Month",
    axisLabel: "Kilometers",
    datasetLabel: "Kilometers",
  },
};

const MILES_TO_KM = 1.60934;

function normalizeDistanceUnit(value) {
  return value === "km" ? "km" : "mi";
}

function getDistanceUnitConfig(value) {
  const unit = normalizeDistanceUnit(value);
  return DISTANCE_UNITS[unit] || DISTANCE_UNITS.mi;
}

function convertDistance(value, unit) {
  if (!Number.isFinite(value)) {
    return value;
  }
  return normalizeDistanceUnit(unit) === "km" ? value * MILES_TO_KM : value;
}

function formatDistance(value, unit) {
  if (!Number.isFinite(value)) {
    return value;
  }
  const converted = convertDistance(value, unit);
  return converted.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function updateDistanceLabels(unit) {
  const config = getDistanceUnitConfig(unit);
  const summaryLabel = document.querySelector("[data-distance-summary-label]");
  if (summaryLabel) {
    summaryLabel.textContent = config.summaryLabel;
  }
  const tableLabel = document.querySelector("[data-distance-table-label]");
  if (tableLabel) {
    tableLabel.textContent = `Distance (${config.short})`;
  }
  const milesLabel = document.querySelector("[data-distance-miles-label]");
  if (milesLabel) {
    milesLabel.textContent = `${config.datasetLabel} (${config.short})`;
  }
  const chartTitle = document.querySelector("[data-distance-chart-title]");
  if (chartTitle) {
    chartTitle.textContent = config.chartTitle;
  }
  const aircraftMilesTitle = document.querySelector(
    "[data-distance-aircraft-miles-title]"
  );
  if (aircraftMilesTitle) {
    aircraftMilesTitle.textContent = `Top Aircraft Type ${config.datasetLabel}`;
  }
}

function loadDistanceUnitPreference() {
  try {
    const stored = window.localStorage?.getItem("dashboardDistanceUnit");
    return normalizeDistanceUnit(stored);
  } catch (error) {
    return "mi";
  }
}

function saveDistanceUnitPreference(unit) {
  try {
    window.localStorage?.setItem(
      "dashboardDistanceUnit",
      normalizeDistanceUnit(unit)
    );
  } catch (error) {
    // Ignore storage failures.
  }
}

function setDashboardDistanceUnit(unit) {
  const normalized = normalizeDistanceUnit(unit);
  window.dashboardDistanceUnit = normalized;
  saveDistanceUnitPreference(normalized);
  updateDistanceLabels(normalized);
  if (Array.isArray(window.dashboardFlights)) {
    applyDashboardFilters();
  } else {
    renderCharts(window.flightCharts, normalized);
  }
}

function renderCharts(
  chartsData = window.flightCharts,
  distanceUnit = window.dashboardDistanceUnit
) {
  if (!chartsData || !window.Chart) {
    return;
  }

  if (!window.chartInstances) {
    window.chartInstances = {};
  }

  const unit = normalizeDistanceUnit(distanceUnit);
  const distanceConfig = getDistanceUnitConfig(unit);
  const P = chartTheme();
  if (window.Chart && window.Chart.defaults) {
    window.Chart.defaults.font.family = P.fontFamily;
    window.Chart.defaults.color = P.axis;
  }

  const mountChart = (key, canvas, config) => {
    if (!canvas) {
      return;
    }
    if (window.chartInstances[key]) {
      window.chartInstances[key].destroy();
    }
    window.chartInstances[key] = new Chart(canvas, config);
  };

  const monthlyCanvas = document.getElementById("monthlyChart");
  if (monthlyCanvas) {
    const ctx = monthlyCanvas.getContext("2d");
    const milesGradient = buildGradient(ctx, withAlpha(P.c2, 0.55));
    const flightsGradient = buildGradient(ctx, withAlpha(P.c1, 0.28));
    const monthlyDistance = (chartsData.monthlyMiles || []).map((value) => {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) {
        return 0;
      }
      return Math.round(convertDistance(numeric, unit) * 100) / 100;
    });
    mountChart("monthly", monthlyCanvas, {
      type: "bar",
      data: {
        labels: chartsData.monthlyLabels,
        datasets: [
          {
            type: "bar",
            label: distanceConfig.datasetLabel,
            data: monthlyDistance,
            backgroundColor: milesGradient,
            borderColor: P.c2,
            borderWidth: 1,
            borderRadius: 6,
            yAxisID: "yMiles",
          },
          {
            type: "line",
            label: "Flights",
            data: chartsData.monthlyCounts,
            borderColor: P.c1,
            backgroundColor: flightsGradient,
            tension: 0.35,
            fill: true,
            pointRadius: 3,
            pointBackgroundColor: P.c1,
            yAxisID: "yFlights",
          },
        ],
      },
      options: {
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            position: "bottom",
            labels: { usePointStyle: true },
          },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Month"),
          yFlights: {
            ...baseAxisOptions("Flights"),
            position: "left",
          },
          yMiles: {
            ...baseAxisOptions(distanceConfig.axisLabel),
            position: "right",
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
  }

  const topCitiesCanvas = document.getElementById("topCitiesChart");
  if (topCitiesCanvas) {
    const ctx = topCitiesCanvas.getContext("2d");
    mountChart("cities", topCitiesCanvas, {
      type: "bar",
      data: {
        labels: chartsData.topCitiesLabels,
        datasets: [
          {
            label: "Flights",
            data: chartsData.topCitiesCounts,
            backgroundColor: buildGradient(ctx, withAlpha(P.c1, 0.6)),
            borderColor: P.c2,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Flights"),
          y: baseAxisOptions("City"),
        },
      },
    });
  }

  const topAirlinesCanvas = document.getElementById("topAirlinesChart");
  if (topAirlinesCanvas) {
    const ctx = topAirlinesCanvas.getContext("2d");
    mountChart("airlines", topAirlinesCanvas, {
      type: "bar",
      data: {
        labels: chartsData.topAirlinesLabels,
        datasets: [
          {
            label: "Flights",
            data: chartsData.topAirlinesCounts,
            backgroundColor: buildGradient(ctx, withAlpha(P.c3, 0.6)),
            borderColor: P.c3,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Flights"),
          y: baseAxisOptions("Airline"),
        },
      },
    });
  }

  const topAircraftCanvas = document.getElementById("topAircraftChart");
  if (topAircraftCanvas) {
    const ctx = topAircraftCanvas.getContext("2d");
    mountChart("aircraft", topAircraftCanvas, {
      type: "bar",
      data: {
        labels: chartsData.topAircraftLabels,
        datasets: [
          {
            label: "Flights",
            data: chartsData.topAircraftCounts,
            backgroundColor: buildGradient(ctx, withAlpha(P.c5, 0.55)),
            borderColor: P.c5,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Flights"),
          y: baseAxisOptions("Aircraft"),
        },
      },
    });
  }

  const topAircraftMilesCanvas = document.getElementById("topAircraftMilesChart");
  if (topAircraftMilesCanvas) {
    const ctx = topAircraftMilesCanvas.getContext("2d");
    const aircraftMiles = (chartsData.topAircraftMilesCounts || []).map(
      (value) => {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
          return 0;
        }
        return Math.round(convertDistance(numeric, unit) * 100) / 100;
      }
    );
    mountChart("aircraft_miles", topAircraftMilesCanvas, {
      type: "bar",
      data: {
        labels: chartsData.topAircraftMilesLabels,
        datasets: [
          {
            label: distanceConfig.datasetLabel,
            data: aircraftMiles,
            backgroundColor: buildGradient(ctx, withAlpha(P.c3, 0.55)),
            borderColor: P.c3,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions(distanceConfig.axisLabel),
          y: baseAxisOptions("Aircraft"),
        },
      },
    });
  }

  const topTailnumbersCanvas = document.getElementById("topTailnumbersChart");
  if (topTailnumbersCanvas) {
    const ctx = topTailnumbersCanvas.getContext("2d");
    mountChart("tailnumbers", topTailnumbersCanvas, {
      type: "bar",
      data: {
        labels: chartsData.topTailnumbersLabels,
        datasets: [
          {
            label: "Flights",
            data: chartsData.topTailnumbersCounts,
            backgroundColor: buildGradient(ctx, withAlpha(P.c4, 0.55)),
            borderColor: P.c4,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Flights"),
          y: baseAxisOptions("Tailnumber"),
        },
      },
    });
  }

  const topCountriesCanvas = document.getElementById("topCountriesChart");
  if (topCountriesCanvas) {
    const palette = [
      ...P.series,
    ];
    mountChart("countries", topCountriesCanvas, {
      type: "doughnut",
      data: {
        labels: chartsData.topCountriesLabels,
        datasets: [
          {
            label: "Flights",
            data: chartsData.topCountriesCounts,
            backgroundColor: palette,
            borderWidth: 0,
          },
        ],
      },
      options: {
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
      },
    });
  }

  const topRoutesCanvas = document.getElementById("topRoutesChart");
  if (topRoutesCanvas) {
    const ctx = topRoutesCanvas.getContext("2d");
    mountChart("routes", topRoutesCanvas, {
      type: "bar",
      data: {
        labels: chartsData.topRoutesLabels,
        datasets: [
          {
            label: "Flights",
            data: chartsData.topRoutesCounts,
            backgroundColor: buildGradient(ctx, withAlpha(P.c7, 0.55)),
            borderColor: P.c7,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Flights"),
          y: baseAxisOptions("Route"),
        },
      },
    });
  }

  const yearlyCanvas = document.getElementById("yearlyChart");
  if (yearlyCanvas) {
    const ctx = yearlyCanvas.getContext("2d");
    mountChart("yearly", yearlyCanvas, {
      type: "bar",
      data: {
        labels: chartsData.yearlyLabels,
        datasets: [
          {
            label: "Flights",
            data: chartsData.yearlyCounts,
            backgroundColor: buildGradient(ctx, withAlpha(P.c1, 0.6)),
            borderColor: P.c1,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Year"),
          y: baseAxisOptions("Flights"),
        },
      },
    });
  }

  const yearlyMilesCanvas = document.getElementById("yearlyMilesChart");
  if (yearlyMilesCanvas) {
    const ctx = yearlyMilesCanvas.getContext("2d");
    const yearlyMilesData = (chartsData.yearlyMilesCounts || []).map(
      (value) => {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
          return 0;
        }
        return Math.round(convertDistance(numeric, unit) * 100) / 100;
      }
    );
    mountChart("yearly_miles", yearlyMilesCanvas, {
      type: "bar",
      data: {
        labels: chartsData.yearlyMilesLabels,
        datasets: [
          {
            label: distanceConfig.datasetLabel,
            data: yearlyMilesData,
            backgroundColor: buildGradient(ctx, withAlpha(P.c3, 0.55)),
            borderColor: P.c3,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Year"),
          y: baseAxisOptions(distanceConfig.axisLabel),
        },
      },
    });
  }

  const yearlyCo2Canvas = document.getElementById("yearlyCo2Chart");
  if (yearlyCo2Canvas) {
    const ctx = yearlyCo2Canvas.getContext("2d");
    mountChart("yearly_co2", yearlyCo2Canvas, {
      type: "bar",
      data: {
        labels: chartsData.yearlyCo2Labels,
        datasets: [
          {
            label: "CO\u2082 (kg)",
            data: chartsData.yearlyCo2Counts,
            backgroundColor: buildGradient(ctx, withAlpha(P.c7, 0.55)),
            borderColor: P.c7,
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: P.tooltipBg,
            titleColor: P.tooltipTitle,
            bodyColor: P.tooltipBody,
          },
        },
        scales: {
          x: baseAxisOptions("Year"),
          y: baseAxisOptions("CO\u2082 (kg)"),
        },
      },
    });
  }
}

// Arc generation function
function createArcPoints(origin, destination, segments = 50) {
  // Haversine distance calculation
  const R = 6371; // Earth radius km
  const dLat = (destination.lat - origin.lat) * Math.PI / 180;
  const dLon = (destination.lon - origin.lon) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(origin.lat * Math.PI / 180) *
            Math.cos(destination.lat * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  const distance = R * c;

  // Arc height scales with distance
  const arcHeight = Math.min(distance / 10, 500);

  // Generate quadratic bezier curve
  const points = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const lat = (1-t)*(1-t)*origin.lat +
                2*(1-t)*t*(origin.lat + destination.lat)/2 +
                t*t*destination.lat;
    const lon = (1-t)*(1-t)*origin.lon +
                2*(1-t)*t*(origin.lon + destination.lon)/2 +
                t*t*destination.lon;
    const latOffset = Math.sin(t * Math.PI) * arcHeight / 111;
    points.push([lat + latOffset, lon]);
  }
  return points;
}

// Route aggregation function
function aggregateRoutes(routes) {
  const routeMap = new Map();
  routes.forEach(route => {
    if (!route.origin_coords || !route.destination_coords) return;
    const cities = [route.origin_name, route.destination_name].sort();
    const routeKey = `${cities[0]}|${cities[1]}`;

    if (!routeMap.has(routeKey)) {
      routeMap.set(routeKey, {
        origin_coords: route.origin_coords,
        destination_coords: route.destination_coords,
        origin_name: route.origin_name,
        destination_name: route.destination_name,
        route_direction: route.route_direction,
        flights: [],
        count: 0
      });
    }

    const agg = routeMap.get(routeKey);
    agg.flights.push(route);
    agg.count++;
  });
  return Array.from(routeMap.values());
}

// Color schemes configuration
const COLOR_SCHEMES = {
  default: {
    getColor: () => cssVar('--map-route', '#2a4bc4'),
    needsLegend: false
  },
  airline: {
    palette: ['#2563eb', '#dc2626', '#16a34a', '#ea580c', '#9333ea', '#0891b2',
              '#ca8a04', '#e11d48', '#7c3aed', '#059669', '#d97706', '#be123c'],
    getColor: (route) => {
      const code = route.flights[0]?.airline_code || 'XX';
      const hash = code.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
      return COLOR_SCHEMES.airline.palette[hash % 12];
    },
    needsLegend: true,
    getLegend: (routes) => {
      const airlines = new Map();
      routes.forEach(r => {
        const code = r.flights[0]?.airline_code;
        if (code && !airlines.has(code)) {
          airlines.set(code, COLOR_SCHEMES.airline.getColor(r));
        }
      });
      return Array.from(airlines.entries()).slice(0, 12).map(([code, color]) => ({
        label: code,
        color
      }));
    }
  },
  year: {
    getColor: (route) => {
      const year = route.flights[0]?.start_date?.substring(0, 4);
      if (!year) return '#94a3b8';
      const yearNum = parseInt(year);
      const minYear = 2000;
      const maxYear = new Date().getFullYear();
      const ratio = (yearNum - minYear) / (maxYear - minYear);
      const r = Math.round(148 - ratio * 111);
      const g = Math.round(163 - ratio * 64);
      const b = Math.round(184 - ratio * 19);
      return `rgb(${r}, ${g}, ${b})`;
    },
    needsLegend: true,
    getLegend: () => [{label: 'Older', color: '#94a3b8'}, {label: 'Recent', color: '#2563eb'}]
  },
  direction: {
    getColor: (route) => (route.route_direction || '').toLowerCase() === 'outbound' ? '#2563eb' : '#16a34a',
    needsLegend: true,
    getLegend: () => [{label: 'Outbound', color: '#2563eb'}, {label: 'Return', color: '#16a34a'}]
  },
  aircraft: {
    getColor: (route) => {
      const aircraft = (route.flights[0]?.aircraft || '').toLowerCase();
      if (aircraft.includes('777') || aircraft.includes('787') || aircraft.includes('a350') || aircraft.includes('a380')) {
        return '#7c3aed'; // Widebody
      } else if (aircraft.includes('737') || aircraft.includes('a320') || aircraft.includes('a321')) {
        return '#2563eb'; // Narrowbody
      } else if (aircraft.includes('emb') || aircraft.includes('crj') || aircraft.includes('dash')) {
        return '#ea580c'; // Regional
      }
      return '#94a3b8'; // Unknown
    },
    needsLegend: true,
    getLegend: () => [
      {label: 'Widebody', color: '#7c3aed'},
      {label: 'Narrowbody', color: '#2563eb'},
      {label: 'Regional', color: '#ea580c'},
      {label: 'Unknown', color: '#94a3b8'}
    ]
  }
};

// Helper functions for map rendering
function buildRoutePopup(route) {
  const div = document.createElement('div');
  div.className = 'route-popup';

  const title = document.createElement('div');
  title.className = 'route-popup-title';
  title.textContent = `${route.origin_name} ↔ ${route.destination_name}`;
  div.appendChild(title);

  const meta = document.createElement('div');
  meta.className = 'route-popup-meta';
  meta.textContent = `${route.count} flight${route.count > 1 ? 's' : ''}`;
  if (route.flights[0]?.distance) {
    const unit = window.dashboardDistanceUnit || 'mi';
    const dist = unit === 'km' ? Math.round(route.flights[0].distance * 1.60934) : Math.round(route.flights[0].distance);
    meta.textContent += ` • ${dist} ${unit}`;
  }
  div.appendChild(meta);

  if (route.count <= 3) {
    const flights = document.createElement('div');
    flights.className = 'route-popup-flights';
    route.flights.forEach(f => {
      const fd = document.createElement('div');
      fd.className = 'route-popup-flight';
      const parts = [];
      if (f.start_date) parts.push(new Date(f.start_date).toLocaleDateString());
      if (f.airline_code && f.flight_number) parts.push(`${f.airline_code}${f.flight_number}`);
      if (f.aircraft) parts.push(f.aircraft);
      fd.textContent = parts.join(' • ');
      flights.appendChild(fd);
    });
    div.appendChild(flights);
  }

  return div;
}

function trackAirport(airportMap, name, coords) {
  if (!airportMap.has(name)) {
    airportMap.set(name, {coords, count: 0});
  }
  airportMap.get(name).count++;
}

function addAirportMarkers(map, airportMap) {
  Array.from(airportMap.entries())
    .filter(([_, data]) => data.count >= 2)
    .forEach(([name, data]) => {
      const marker = L.circleMarker([data.coords.lat, data.coords.lon], {
        radius: 4 + Math.log(data.count) * 2,
        fillColor: cssVar('--map-route', '#2a4bc4'),
        color: isDarkTheme() ? '#0b0f1a' : '#ffffff',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9
      }).addTo(map);
      marker.bindPopup(`<strong>${name}</strong><br>${data.count} route${data.count > 1 ? 's' : ''}`);
    });
}

function updateMapLegend(scheme, routes) {
  const legend = document.querySelector('[data-map-legend]');
  if (!legend) return;

  if (!scheme.needsLegend) {
    legend.hidden = true;
    return;
  }

  legend.hidden = false;
  legend.innerHTML = '';

  scheme.getLegend(routes).forEach(item => {
    const div = document.createElement('div');
    div.className = 'legend-item';
    const color = document.createElement('div');
    color.className = 'legend-color';
    color.style.backgroundColor = item.color;
    const label = document.createElement('span');
    label.textContent = item.label;
    div.appendChild(color);
    div.appendChild(label);
    legend.appendChild(div);
  });
}

function renderMap(routes = window.mapRoutes, colorScheme = 'default') {
  const mapElement = document.getElementById('routeMap');
  const loadingIndicator = document.querySelector('[data-map-loading-indicator]');

  if (!mapElement || !window.L || !routes) return;

  // Show loading indicator
  if (loadingIndicator) {
    loadingIndicator.hidden = false;
  }

  if (window.routeMapInstance) {
    window.routeMapInstance.remove();
  }

  const map = L.map(mapElement, {
    minZoom: 2,
    maxZoom: 8,
    maxBounds: [[-85, -180], [85, 180]],
    maxBoundsViscosity: 1.0,
  }).setView([20, 0], 2);

  window.routeMapInstance = map;

  L.tileLayer(mapTileUrl(), {
    maxZoom: 8,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  const bounds = L.latLngBounds([]);
  const aggregated = aggregateRoutes(routes);
  const scheme = COLOR_SCHEMES[colorScheme] || COLOR_SCHEMES.default;
  const airportMap = new Map();

  aggregated.forEach(route => {
    const origin = {lat: route.origin_coords[0], lon: route.origin_coords[1]};
    const dest = {lat: route.destination_coords[0], lon: route.destination_coords[1]};
    const arcPoints = createArcPoints(origin, dest);
    const weight = Math.min(2 + Math.log(route.count) * 0.5, 6);
    const color = scheme.getColor(route);

    const polyline = L.polyline(arcPoints, {
      color: color,
      weight: weight,
      opacity: 0.7
    }).addTo(map);

    polyline.bindPopup(buildRoutePopup(route));

    bounds.extend([origin.lat, origin.lon]);
    bounds.extend([dest.lat, dest.lon]);

    trackAirport(airportMap, route.origin_name, origin);
    trackAirport(airportMap, route.destination_name, dest);
  });

  addAirportMarkers(map, airportMap);

  if (bounds.isValid()) {
    map.fitBounds(bounds, {padding: [20, 20]});
  }

  updateMapLegend(scheme, aggregated);

  // Hide loading indicator
  setTimeout(() => {
    if (loadingIndicator) {
      loadingIndicator.hidden = true;
    }
  }, 300);
}

function renderStatsTables(tables = window.statsTables) {
  if (!tables) {
    return;
  }

  const distanceUnit = normalizeDistanceUnit(window.dashboardDistanceUnit);
  const perPage = 10;
  const clamp = (value, min, max) => Math.max(min, Math.min(value, max));

  const attachRowFilter = (row, type, key, label) => {
    if (!row) {
      return;
    }
    const normalizedKey = normalizeLabel(key) || "unknown";
    row.dataset.tableFilterType = type;
    row.dataset.tableFilterKey = normalizedKey;
    row.dataset.tableFilterLabel = label || key || "Unknown";
    row.addEventListener("click", () => {
      if (typeof window.addDashboardTableFilter === "function") {
        window.addDashboardTableFilter(type, normalizedKey, label || key);
      }
    });
  };

  const renderAirlineRow = (tbody, code, value) => {
    const row = document.createElement("tr");
    const labelCell = document.createElement("td");
    labelCell.className = "airline-label-cell";

    const icon = document.createElement("img");
    icon.className = "airline-icon";
    const logoUrl = buildAirlineLogoUrl(code);
    if (logoUrl) {
      icon.src = logoUrl;
      icon.alt = `${getAirlineDisplayLabel(code)} logo`;
      icon.loading = "lazy";
      icon.onerror = () => {
        icon.remove();
      };
    } else {
      icon.remove();
    }

    const label = document.createElement("span");
    label.textContent = getAirlineDisplayLabel(code);

    if (icon.isConnected) {
      labelCell.append(icon);
    }
    labelCell.appendChild(label);

    const valueCell = document.createElement("td");
    valueCell.textContent = value;
    row.append(labelCell, valueCell);
    tbody.appendChild(row);
    attachRowFilter(row, "airlines", code || "Unknown", getAirlineDisplayLabel(code));
    return row;
  };

  const renderTable = (key, rows) => {
    const container = document.querySelector(`[data-table="${key}"]`);
    if (!container) {
      return;
    }

    const tbody = container.querySelector("tbody");
    const pagination = container.querySelector("[data-pagination]");
    const emptyMessage = container.dataset.empty || "No data.";
    let currentPage = 1;
    const totalPages = Math.max(1, Math.ceil(rows.length / perPage));

    const buildPagination = () => {
      if (!pagination) {
        return;
      }
      pagination.innerHTML = "";
      if (totalPages <= 1) {
        return;
      }

      const prev = document.createElement("button");
      prev.type = "button";
      prev.textContent = "Previous";
      prev.disabled = currentPage === 1;
      prev.addEventListener("click", () => {
        renderPage(currentPage - 1);
      });

      const next = document.createElement("button");
      next.type = "button";
      next.textContent = "Next";
      next.disabled = currentPage === totalPages;
      next.addEventListener("click", () => {
        renderPage(currentPage + 1);
      });

      const status = document.createElement("span");
      status.textContent = `Page ${currentPage} of ${totalPages}`;

      pagination.append(prev, status, next);
    };

    const renderPage = (page) => {
      currentPage = clamp(page, 1, totalPages);
      tbody.innerHTML = "";

      if (!rows.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 2;
        cell.textContent = emptyMessage;
        row.appendChild(cell);
        tbody.appendChild(row);
        buildPagination();
        return;
      }

      const start = (currentPage - 1) * perPage;
      const pageRows = rows.slice(start, start + perPage);
      pageRows.forEach(([label, value]) => {
        if (key === "airlines") {
          renderAirlineRow(tbody, label, value);
          return;
        }
        const row = document.createElement("tr");
        const labelCell = document.createElement("td");
        labelCell.textContent = label;
        const valueCell = document.createElement("td");
        if (key === "aircraft_miles" || key === "yearly_miles") {
          const numeric = Number(value);
          valueCell.textContent = Number.isFinite(numeric)
            ? formatDistance(numeric, distanceUnit)
            : "-";
        } else {
          valueCell.textContent = value;
        }
        row.append(labelCell, valueCell);
        tbody.appendChild(row);
        attachRowFilter(row, key === "aircraft_miles" ? "aircraft" : key, label, label);
      });

      buildPagination();
    };

    renderPage(1);
  };

  Object.entries(tables).forEach(([key, rows]) => {
    renderTable(key, rows || []);
  });
}

function extractCountry(name) {
  if (!name) {
    return null;
  }
  const trimmed = name.trim();
  if (!trimmed) {
    return null;
  }
  const parenStart = trimmed.indexOf("(");
  const parenEnd = trimmed.indexOf(")");
  if (parenStart !== -1 && parenEnd !== -1 && parenEnd > parenStart) {
    return trimmed.slice(parenStart + 1, parenEnd).trim() || null;
  }
  if (trimmed.includes(",")) {
    const parts = trimmed.split(",");
    return parts[parts.length - 1].trim() || null;
  }
  return null;
}

const AIRLINE_CODE_PATTERN = /^[A-Z0-9]{2,3}$/;
const FLIGHT_NUMBER_PATTERN = /^([A-Z]{2,3})?0*([0-9]{1,5})$/;

function normalizeAirlineCode(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  const normalized = value.trim().toUpperCase();
  return normalized || null;
}

function extractFlightNumberParts(value) {
  if (!value || typeof value !== "string") {
    return { code: null, number: value || null };
  }
  const compact = value.trim().toUpperCase().replace(/\s+/g, "");
  if (!compact) {
    return { code: null, number: null };
  }
  const match = compact.match(FLIGHT_NUMBER_PATTERN);
  if (match) {
    return { code: match[1] || null, number: match[2] || null };
  }
  if (/^\d+$/.test(compact)) {
    return { code: null, number: compact.replace(/^0+/, "") || "0" };
  }
  return { code: null, number: compact };
}

function resolveAirlineCode(airlineCode, flightNumber) {
  const normalized = normalizeAirlineCode(airlineCode);
  if (normalized && AIRLINE_CODE_PATTERN.test(normalized)) {
    return normalized;
  }
  const extracted = extractFlightNumberParts(flightNumber).code;
  const normalizedExtracted = normalizeAirlineCode(extracted);
  return normalizedExtracted && AIRLINE_CODE_PATTERN.test(normalizedExtracted)
    ? normalizedExtracted
    : null;
}

function lookupAirlineName(code) {
  const normalized = normalizeAirlineCode(code);
  if (!normalized) {
    return null;
  }
  const lookup = window.airlineLookup || {};
  return lookup[normalized] || null;
}

function getAirlineDisplayLabel(code) {
  if (!code || code === "Unknown") {
    return "Unknown";
  }
  const name = lookupAirlineName(code);
  if (!name) {
    return code;
  }
  return `${name} (${code})`;
}

function buildAirlineLogoUrl(code) {
  const normalized = normalizeAirlineCode(code);
  if (!normalized || !AIRLINE_CODE_PATTERN.test(normalized)) {
    return null;
  }
  const template = window.airlineLogoTemplate || "";
  if (!template) {
    return null;
  }
  const url = template.replace("{code}", normalized);
  if (normalized.length === 3) {
    return url.replace("iata=", "icao=");
  }
  return url;
}

function summarizeAirlines(flights) {
  const counts = new Map();
  flights.forEach((flight) => {
    const code = resolveAirlineCode(
      flight.airline_code,
      flight.flight_number
    );
    const key = code || "Unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  if (!counts.size) {
    return {
      code: null,
      name: null,
      count: 0,
      logoUrl: null,
    };
  }
  const sorted = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  const [code, count] = sorted[0];
  const resolvedCode = code === "Unknown" ? null : code;
  return {
    code: resolvedCode,
    name: lookupAirlineName(resolvedCode),
    count,
    logoUrl: buildAirlineLogoUrl(resolvedCode),
  };
}

function updateAirlineCard(summary) {
  const label = document.querySelector('[data-summary="top-airline-label"]');
  const count = document.querySelector('[data-summary="top-airline-count"]');
  const code = document.querySelector('[data-summary="top-airline-code"]');
  const logo = document.querySelector("[data-airline-logo]");
  const fallback = document.querySelector("[data-airline-logo-fallback]");
  const displayLabel =
    summary?.name ||
    summary?.code ||
    (summary?.count ? "Unknown airline" : "-");
  const displayCode = summary?.code || "Unknown code";

  if (label) {
    label.textContent = displayLabel;
  }
  if (count) {
    count.textContent = `${summary?.count ?? 0} flights`;
  }
  if (code) {
    code.textContent = displayCode;
  }
  if (logo) {
    if (summary?.logoUrl) {
      logo.hidden = false;
      logo.src = summary.logoUrl;
      logo.alt = `${displayLabel} logo`;
      logo.onerror = () => {
        logo.hidden = true;
        if (fallback) {
          fallback.hidden = false;
        }
      };
      if (fallback) {
        fallback.hidden = true;
      }
    } else {
      logo.hidden = true;
      if (fallback) {
        fallback.hidden = false;
      }
    }
  }
}

function buildDashboardStats(flights) {
  const topCities = new Map();
  const topRoutes = new Map();
  const topCountries = new Map();
  const topAirlines = new Map();
  const topAircrafts = new Map();
  const aircraftLabels = new Map();
  const topAircraftMiles = new Map();
  const topTailnumbers = new Map();
  const tailnumberLabels = new Map();
  const monthlyCounts = new Map();
  const monthlyMiles = new Map();
  const yearlyCounts = new Map();
  const yearlyMilesMap = new Map();
  const yearlyCo2Map = new Map();
  let totalMiles = 0;

  flights.forEach((flight) => {
    const origin = flight.origin_name || "Unknown";
    const destination = flight.destination_name || "Unknown";
    const distance = Number(flight.distance || 0);

    totalMiles += Number.isFinite(distance) ? distance : 0;
    topCities.set(destination, (topCities.get(destination) || 0) + 1);
    topRoutes.set(
      `${origin} → ${destination}`,
      (topRoutes.get(`${origin} → ${destination}`) || 0) + 1
    );

    const destinationCountry =
      flight.end_country || extractCountry(destination) || "Unknown";
    topCountries.set(
      destinationCountry,
      (topCountries.get(destinationCountry) || 0) + 1
    );

    const airlineCode = resolveAirlineCode(
      flight.airline_code,
      flight.flight_number
    );
    const airlineKey = airlineCode || "Unknown";
    topAirlines.set(airlineKey, (topAirlines.get(airlineKey) || 0) + 1);

    const aircraftLabel = flight.aircraft_type_normalized
      ? flight.aircraft_type_normalized.trim()
      : "";
    const aircraftKey = normalizeLabel(aircraftLabel) || "unknown";
    topAircrafts.set(aircraftKey, (topAircrafts.get(aircraftKey) || 0) + 1);
    topAircraftMiles.set(
      aircraftKey,
      (topAircraftMiles.get(aircraftKey) || 0) +
        (Number.isFinite(distance) ? distance : 0)
    );
    const labelKey = aircraftLabel || "Unknown";
    const labelCounts = aircraftLabels.get(aircraftKey) || new Map();
    labelCounts.set(labelKey, (labelCounts.get(labelKey) || 0) + 1);
    aircraftLabels.set(aircraftKey, labelCounts);

    const tailnumberLabel = flight.aircraft_registration
      ? flight.aircraft_registration.trim().toUpperCase()
      : "";
    const tailnumberKey = normalizeLabel(tailnumberLabel) || "unknown";
    topTailnumbers.set(
      tailnumberKey,
      (topTailnumbers.get(tailnumberKey) || 0) + 1
    );
    const tailnumberDisplay = tailnumberLabel || "Unknown";
    const tailnumberCounts = tailnumberLabels.get(tailnumberKey) || new Map();
    tailnumberCounts.set(
      tailnumberDisplay,
      (tailnumberCounts.get(tailnumberDisplay) || 0) + 1
    );
    tailnumberLabels.set(tailnumberKey, tailnumberCounts);

    if (flight.start_date) {
      const monthKey = flight.start_date.slice(0, 7);
      const yearKey = flight.start_date.slice(0, 4);
      monthlyCounts.set(monthKey, (monthlyCounts.get(monthKey) || 0) + 1);
      monthlyMiles.set(
        monthKey,
        (monthlyMiles.get(monthKey) || 0) + (Number.isFinite(distance) ? distance : 0)
      );
      yearlyCounts.set(yearKey, (yearlyCounts.get(yearKey) || 0) + 1);
      yearlyMilesMap.set(
        yearKey,
        (yearlyMilesMap.get(yearKey) || 0) + (Number.isFinite(distance) ? distance : 0)
      );
      const co2Kg = (Number.isFinite(distance) ? distance : 0) * 1.60934 * 0.255;
      yearlyCo2Map.set(yearKey, (yearlyCo2Map.get(yearKey) || 0) + co2Kg);
    }
  });

  const toSortedArray = (map) =>
    Array.from(map.entries()).sort(
      (a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]))
    );

  const isUnknownLabel = (label) => {
    const normalized = normalizeLabel(label) || "";
    return ["unknown", "-", "n/a", "na", ""].includes(normalized);
  };

  const selectTopEntry = (entries, excludedLabels = []) => {
    const excludedSet = new Set(
      excludedLabels.map((value) => normalizeLabel(value)).filter(Boolean)
    );
    for (const [label, count] of entries) {
      const normalized = normalizeLabel(label) || "";
      if (!normalized || excludedSet.has(normalized) || isUnknownLabel(label)) {
        continue;
      }
      return [label, count];
    }
    return ["-", 0];
  };

  const citiesData = toSortedArray(topCities);
  const routesData = toSortedArray(topRoutes);
  const countriesData = toSortedArray(topCountries);
  const airlinesData = toSortedArray(topAirlines);
  const aircraftData = Array.from(topAircrafts.entries())
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .map(([key, count]) => {
      const labels = aircraftLabels.get(key);
      const label = labels
        ? Array.from(labels.entries()).sort((a, b) => b[1] - a[1])[0][0]
        : "Unknown";
      return [label, count];
    });
  const aircraftMilesData = Array.from(topAircraftMiles.entries())
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .map(([key, miles]) => {
      const labels = aircraftLabels.get(key);
      const label = labels
        ? Array.from(labels.entries()).sort((a, b) => b[1] - a[1])[0][0]
        : "Unknown";
      return [label, Math.round(miles * 100) / 100];
    });
  const tailnumberData = Array.from(topTailnumbers.entries())
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .map(([key, count]) => {
      const labels = tailnumberLabels.get(key);
      const label = labels
        ? Array.from(labels.entries()).sort((a, b) => b[1] - a[1])[0][0]
        : "Unknown";
      return [label, count];
    });
  const monthlyData = Array.from(monthlyCounts.entries()).sort((a, b) =>
    String(a[0]).localeCompare(String(b[0]))
  );
  const yearlyData = Array.from(yearlyCounts.entries()).sort((a, b) =>
    String(a[0]).localeCompare(String(b[0]))
  );
  const yearlyMilesData = yearlyData.map(([year]) => [
    year,
    Math.round((yearlyMilesMap.get(year) || 0) * 100) / 100,
  ]);
  const yearlyCo2Data = yearlyData.map(([year]) => [
    year,
    Math.round((yearlyCo2Map.get(year) || 0) * 10) / 10,
  ]);

  const topCity = selectTopEntry(
    citiesData,
    window.homeCity ? [window.homeCity] : []
  );
  const topCountry = selectTopEntry(
    countriesData,
    window.homeCountry ? [window.homeCountry] : []
  );
  const topYear = yearlyData.length
    ? yearlyData.reduce((best, current) =>
        current[1] > best[1] ? current : best
      )
    : ["-", 0];
  const topAirline = summarizeAirlines(flights);
  const topAircraft = selectTopEntry(aircraftData);
  const topTailnumber = selectTopEntry(tailnumberData);

  const chartPayload = {
    monthlyLabels: monthlyData.map((item) => item[0]),
    monthlyCounts: monthlyData.map((item) => item[1]),
    monthlyMiles: monthlyData.map((item) =>
      Math.round((monthlyMiles.get(item[0]) || 0) * 100) / 100
    ),
    topCitiesLabels: citiesData.slice(0, 10).map((item) => item[0]),
    topCitiesCounts: citiesData.slice(0, 10).map((item) => item[1]),
    topCountriesLabels: countriesData.slice(0, 8).map((item) => item[0]),
    topCountriesCounts: countriesData.slice(0, 8).map((item) => item[1]),
    topAirlinesLabels: airlinesData
      .slice(0, 10)
      .map((item) => getAirlineDisplayLabel(item[0])),
    topAirlinesCounts: airlinesData.slice(0, 10).map((item) => item[1]),
    topAircraftLabels: aircraftData.slice(0, 10).map((item) => item[0]),
    topAircraftCounts: aircraftData.slice(0, 10).map((item) => item[1]),
    topAircraftMilesLabels: aircraftMilesData
      .slice(0, 10)
      .map((item) => item[0]),
    topAircraftMilesCounts: aircraftMilesData
      .slice(0, 10)
      .map((item) => item[1]),
    topTailnumbersLabels: tailnumberData.slice(0, 10).map((item) => item[0]),
    topTailnumbersCounts: tailnumberData.slice(0, 10).map((item) => item[1]),
    topRoutesLabels: routesData.slice(0, 10).map((item) => item[0]),
    topRoutesCounts: routesData.slice(0, 10).map((item) => item[1]),
    yearlyLabels: yearlyData.map((item) => item[0]),
    yearlyCounts: yearlyData.map((item) => item[1]),
    yearlyMilesLabels: yearlyMilesData.map((item) => item[0]),
    yearlyMilesCounts: yearlyMilesData.map((item) => item[1]),
    yearlyCo2Labels: yearlyCo2Data.map((item) => item[0]),
    yearlyCo2Counts: yearlyCo2Data.map((item) => item[1]),
  };

  const routes = flights.map((flight) => ({
    origin_coords:
      flight.start_lat != null && flight.start_long != null
        ? [flight.start_lat, flight.start_long]
        : null,
    destination_coords:
      flight.end_lat != null && flight.end_long != null
        ? [flight.end_lat, flight.end_long]
        : null,
    origin_name: flight.origin_name,
    destination_name: flight.destination_name,
  }));

  const recentFlights = [...flights].sort((a, b) => {
    const aDate = a.start_date ? Date.parse(a.start_date) : 0;
    const bDate = b.start_date ? Date.parse(b.start_date) : 0;
    return bDate - aDate;
  });

  return {
    summary: {
      totalFlights: flights.length,
      totalMiles: Math.round(totalMiles * 100) / 100,
      topCity,
      topCountry,
      topYear,
      topAirline,
      topAircraft,
      topTailnumber,
    },
    tables: {
      cities: citiesData,
      airlines: airlinesData,
      aircraft: aircraftData,
      aircraft_miles: aircraftMilesData,
      tailnumbers: tailnumberData,
      countries: countriesData,
      routes: routesData,
      years: yearlyData,
      yearly_miles: yearlyMilesData,
      yearly_co2: yearlyCo2Data,
    },
    charts: chartPayload,
    routes,
    recentFlights,
  };
}

function updateDashboardSummary(summary, distanceUnit) {
  const unit = normalizeDistanceUnit(distanceUnit);
  const formatCount = (value) =>
    Number.isFinite(value) ? value.toLocaleString() : value;
  const formatMiles = (value) => formatDistance(value, unit);

  const totalFlights = document.querySelector('[data-summary="total-flights"]');
  const totalMiles = document.querySelector('[data-summary="total-miles"]');
  const topCityLabel = document.querySelector(
    '[data-summary="top-city-label"]'
  );
  const topCityCount = document.querySelector(
    '[data-summary="top-city-count"]'
  );
  const topCountryLabel = document.querySelector(
    '[data-summary="top-country-label"]'
  );
  const topCountryCount = document.querySelector(
    '[data-summary="top-country-count"]'
  );
  const topYearLabel = document.querySelector(
    '[data-summary="top-year-label"]'
  );
  const topYearCount = document.querySelector(
    '[data-summary="top-year-count"]'
  );
  const topAircraftLabel = document.querySelector(
    '[data-summary="top-aircraft-label"]'
  );
  const topAircraftCount = document.querySelector(
    '[data-summary="top-aircraft-count"]'
  );
  const topTailnumberLabel = document.querySelector(
    '[data-summary="top-tailnumber-label"]'
  );
  const topTailnumberCount = document.querySelector(
    '[data-summary="top-tailnumber-count"]'
  );

  if (totalFlights) {
    totalFlights.textContent = formatCount(summary.totalFlights);
  }
  if (totalMiles) {
    totalMiles.textContent = formatMiles(summary.totalMiles);
  }
  if (topCityLabel) {
    topCityLabel.textContent = summary.topCity[0];
  }
  if (topCityCount) {
    topCityCount.textContent = `${formatCount(summary.topCity[1])} flights`;
  }
  if (topCountryLabel) {
    topCountryLabel.textContent = summary.topCountry[0];
  }
  if (topCountryCount) {
    topCountryCount.textContent = `${formatCount(summary.topCountry[1])} flights`;
  }
  if (topYearLabel) {
    topYearLabel.textContent = summary.topYear[0];
  }
  if (topYearCount) {
    topYearCount.textContent = `${formatCount(summary.topYear[1])} flights`;
  }
  if (topAircraftLabel) {
    topAircraftLabel.textContent = summary.topAircraft[0];
  }
  if (topAircraftCount) {
    topAircraftCount.textContent = `${formatCount(summary.topAircraft[1])} flights`;
  }
  if (topTailnumberLabel) {
    topTailnumberLabel.textContent = summary.topTailnumber[0];
  }
  if (topTailnumberCount) {
    topTailnumberCount.textContent = `${formatCount(
      summary.topTailnumber[1]
    )} flights`;
  }

  // Update the tailnumber lightbox button attributes so clicking shows the correct aircraft
  const tailnumberButton = document.querySelector(
    ".summary-card--tailnumber[data-aircraft-lightbox]"
  );
  if (tailnumberButton) {
    const newReg = (summary.topTailnumber[0] || "").trim().toUpperCase();
    const currentTitle = (tailnumberButton.dataset.title || "").trim().toUpperCase();
    if (newReg && newReg !== "-" && newReg !== currentTitle) {
      tailnumberButton.dataset.title = newReg;
      // Fetch the new aircraft photo and update the button + thumbnail
      fetch(`/api/aircraft/${encodeURIComponent(newReg)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (!data || !data.details) return;
          const photoUrl = data.details.url_photo || "";
          const thumbUrl = data.details.url_photo_thumbnail || photoUrl;
          if (photoUrl) {
            tailnumberButton.dataset.fullSrc = photoUrl;
          }
          const thumbImg = tailnumberButton.querySelector(".summary-thumb img");
          const thumbFallback = tailnumberButton.querySelector(
            ".summary-thumb__fallback"
          );
          if (thumbImg && thumbUrl) {
            thumbImg.src = thumbUrl;
          } else if (!thumbImg && thumbUrl && tailnumberButton.querySelector(".summary-thumb")) {
            const img = document.createElement("img");
            img.src = thumbUrl;
            img.alt = "Top tail number thumbnail";
            img.loading = "lazy";
            const container = tailnumberButton.querySelector(".summary-thumb");
            if (thumbFallback) thumbFallback.remove();
            container.appendChild(img);
          }
        })
        .catch(() => {});
    }
  }
  if (summary.topAirline) {
    updateAirlineCard(summary.topAirline);
  }
}

function updatePanelMeta(tables) {
  const metaMap = {
    cities: "cities-total",
    airlines: "airlines-total",
    aircraft: "aircraft-total",
    aircraft_miles: "aircraft-miles-total",
    tailnumbers: "tailnumbers-total",
    countries: "countries-total",
    routes: "routes-total",
    years: "years-total",
    yearly_co2: "yearly-co2-total",
  };
  Object.entries(metaMap).forEach(([key, metaKey]) => {
    const meta = document.querySelector(`[data-meta="${metaKey}"]`);
    if (meta) {
      meta.textContent = `${tables[key]?.length || 0} total`;
    }
  });
}

function renderRecentFlights(flights, totalCount, filterState, distanceUnit) {
  const unit = normalizeDistanceUnit(distanceUnit);
  const tbody = document.querySelector("[data-recent-flights]");
  const editUrlTemplate = window.flightEditUrlTemplate;
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";

  if (!totalCount) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No flights yet.";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  if (!flights.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "filter-empty";
    if (filterState?.hasFilters) {
      if (
        filterState.hasTravellerFilters &&
        !filterState.hasBookingSiteFilters
      ) {
        cell.textContent =
          filterState.travellerMode === "exclude"
            ? "No flights remain after excluding those travellers."
            : "No flights match those travellers.";
      } else {
        cell.textContent = "No flights match those filters.";
      }
    } else {
      cell.textContent = "No flights yet.";
    }
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  flights.slice(0, 10).forEach((flight) => {
    const row = document.createElement("tr");
    const dateCell = document.createElement("td");
    dateCell.textContent = flight.start_date || "-";
    const originCell = document.createElement("td");
    originCell.textContent = flight.origin_name || "-";
    const destinationCell = document.createElement("td");
    destinationCell.textContent = flight.destination_name || "-";
    const flightCell = document.createElement("td");
    flightCell.textContent = flight.flight_number || "-";
    const distanceCell = document.createElement("td");
    distanceCell.textContent =
      flight.distance == null
        ? "-"
        : formatDistance(Number(flight.distance), unit);
    const editCell = document.createElement("td");
    if (typeof editUrlTemplate === "string" && flight.id != null) {
      const group = document.createElement("div");
      group.className = "row-action-group";

      const quickButton = document.createElement("button");
      quickButton.type = "button";
      quickButton.className = "button ghost";
      quickButton.dataset.quickEditOpen = String(flight.id);
      quickButton.title = "Quick edit";
      quickButton.setAttribute("aria-label", "Quick edit");
      const quickIcon = document.createElement("i");
      quickIcon.className = "fa-solid fa-bolt";
      quickIcon.setAttribute("aria-hidden", "true");
      const quickLabel = document.createElement("span");
      quickLabel.className = "sr-only";
      quickLabel.textContent = "Quick edit";
      quickButton.append(quickIcon, quickLabel);
      group.appendChild(quickButton);

      const editLink = document.createElement("a");
      editLink.className = "button ghost";
      editLink.href = editUrlTemplate.replace(
        "/0/edit",
        `/${flight.id}/edit`
      );
      editLink.setAttribute("aria-label", "Edit");
      editLink.title = "Edit";
      const editIcon = document.createElement("i");
      editIcon.className = "fa-solid fa-pen-to-square";
      editIcon.setAttribute("aria-hidden", "true");
      const editLabel = document.createElement("span");
      editLabel.className = "sr-only";
      editLabel.textContent = "Edit";
      editLink.append(editIcon, editLabel);
      group.appendChild(editLink);

      editCell.appendChild(group);
    } else {
      editCell.textContent = "-";
    }
    row.append(
      dateCell,
      originCell,
      destinationCell,
      flightCell,
      distanceCell,
      editCell
    );
    tbody.appendChild(row);
  });
}

function applyDashboardFilter(
  travellerKeys,
  mode = "include",
  bookingSiteKeys,
  tableFilters = {}
) {
  const distanceUnit = normalizeDistanceUnit(window.dashboardDistanceUnit);
  const allFlights = Array.isArray(window.dashboardFlights)
    ? window.dashboardFlights
    : null;
  if (!allFlights) {
    return;
  }
  const activeTravellerKeys = Array.isArray(travellerKeys) ? travellerKeys : [];
  const activeBookingSiteKeys = Array.isArray(bookingSiteKeys)
    ? bookingSiteKeys
    : [];
  const activeTableFilters = tableFilters || {};
  const travellerSet = new Set(activeTravellerKeys);
  const bookingSiteSet = new Set(activeBookingSiteKeys);
  const normalizeKey = (value) => normalizeLabel(value) || "unknown";
  const tableFilterSets = {
    cities: activeTableFilters.cities || new Set(),
    airlines: activeTableFilters.airlines || new Set(),
    aircraft: activeTableFilters.aircraft || new Set(),
    tailnumbers: activeTableFilters.tailnumbers || new Set(),
    countries: activeTableFilters.countries || new Set(),
    routes: activeTableFilters.routes || new Set(),
    years: activeTableFilters.years || new Set(),
  };

  const matchesTableFilters = (flight) => {
    const hasFilters = Object.values(tableFilterSets).some(
      (set) => set && set.size
    );
    if (!hasFilters) {
      return true;
    }

    const destination = flight.destination_name || "Unknown";
    const destinationCountry =
      flight.end_country || extractCountry(destination) || "Unknown";
    const routeLabel = `${flight.origin_name || "Unknown"} → ${destination}`;
    const airlineCode =
      resolveAirlineCode(flight.airline_code, flight.flight_number) || "Unknown";
    const aircraftLabel = flight.aircraft_type_normalized
      ? flight.aircraft_type_normalized.trim()
      : "Unknown";
    const tailnumberLabel = flight.aircraft_registration
      ? flight.aircraft_registration.trim().toUpperCase()
      : "Unknown";
    const yearLabel = flight.start_date
      ? String(flight.start_date).slice(0, 4)
      : "Unknown";

    if (
      tableFilterSets.cities.size &&
      !tableFilterSets.cities.has(normalizeKey(destination))
    ) {
      return false;
    }
    if (
      tableFilterSets.countries.size &&
      !tableFilterSets.countries.has(normalizeKey(destinationCountry))
    ) {
      return false;
    }
    if (
      tableFilterSets.routes.size &&
      !tableFilterSets.routes.has(normalizeKey(routeLabel))
    ) {
      return false;
    }
    if (
      tableFilterSets.years.size &&
      !tableFilterSets.years.has(normalizeKey(yearLabel))
    ) {
      return false;
    }
    if (
      tableFilterSets.airlines.size &&
      !tableFilterSets.airlines.has(normalizeKey(airlineCode))
    ) {
      return false;
    }
    if (
      tableFilterSets.aircraft.size &&
      !tableFilterSets.aircraft.has(normalizeKey(aircraftLabel))
    ) {
      return false;
    }
    if (
      tableFilterSets.tailnumbers.size &&
      !tableFilterSets.tailnumbers.has(normalizeKey(tailnumberLabel))
    ) {
      return false;
    }
    return true;
  };
  let filteredFlights = activeTravellerKeys.length
    ? allFlights.filter((flight) => {
        const key = flight.traveller_key;
        const isMatch = travellerSet.has(key);
        return mode === "exclude" ? !isMatch : isMatch;
      })
    : allFlights;
  if (activeBookingSiteKeys.length) {
    filteredFlights = filteredFlights.filter((flight) =>
      bookingSiteSet.has(flight.booking_site_key)
    );
  }
  filteredFlights = filteredFlights.filter(matchesTableFilters);
  if (dashboardSearchIds) {
    filteredFlights = filteredFlights.filter((flight) =>
      dashboardSearchIds.has(String(flight.id))
    );
  }

  const stats = buildDashboardStats(filteredFlights);
  updateDistanceLabels(distanceUnit);
  updateDashboardSummary(stats.summary, distanceUnit);
  updatePanelMeta(stats.tables);
  renderCharts(stats.charts, distanceUnit);
  renderStatsTables(stats.tables);
  renderMap(stats.routes);
  renderRecentFlights(
    stats.recentFlights,
    allFlights.length,
    {
      hasFilters:
        activeTravellerKeys.length > 0 ||
        activeBookingSiteKeys.length > 0 ||
        Object.values(tableFilterSets).some((set) => set.size) ||
        Boolean(dashboardSearchIds),
      hasTravellerFilters: activeTravellerKeys.length > 0,
      hasBookingSiteFilters: activeBookingSiteKeys.length > 0,
      travellerMode: mode,
    },
    distanceUnit
  );
}

const dashboardFilterState = {
  travellerKeys: new Set(),
  travellerMode: "include",
  bookingSiteKeys: new Set(),
  tableFilters: {
    cities: new Map(),
    airlines: new Map(),
    aircraft: new Map(),
    tailnumbers: new Map(),
    countries: new Map(),
    routes: new Map(),
    years: new Map(),
  },
};

function applyDashboardFilters() {
  const tableFilters = Object.fromEntries(
    Object.entries(dashboardFilterState.tableFilters || {}).map(
      ([type, map]) => [type, new Set(map?.keys ? map.keys() : [])]
    )
  );
  applyDashboardFilter(
    Array.from(dashboardFilterState.travellerKeys),
    dashboardFilterState.travellerMode,
    Array.from(dashboardFilterState.bookingSiteKeys),
    tableFilters
  );
}

function openDashboardFilters() {
  const filtersPanel = document.querySelector(".dashboard-filter");
  if (filtersPanel && !filtersPanel.open) {
    filtersPanel.open = true;
  }
}

function saveLastTravellerFilter(value) {
  if (!value) {
    return;
  }
  const encoded = encodeURIComponent(value);
  document.cookie = `dashboardTravellerFilter=${encoded}; max-age=2592000; path=/`;
}

function getLastTravellerFilter() {
  const entries = document.cookie.split(";").map((cookie) => cookie.trim());
  const match = entries.find((cookie) =>
    cookie.startsWith("dashboardTravellerFilter=")
  );
  if (!match) {
    return null;
  }
  const value = match.split("=").slice(1).join("=");
  return value ? decodeURIComponent(value) : null;
}

function saveLastTravellerFilterMode(mode) {
  if (!mode) {
    return;
  }
  const encoded = encodeURIComponent(mode);
  document.cookie = `dashboardTravellerFilterMode=${encoded}; max-age=2592000; path=/`;
}

function getLastTravellerFilterMode() {
  const entries = document.cookie.split(";").map((cookie) => cookie.trim());
  const match = entries.find((cookie) =>
    cookie.startsWith("dashboardTravellerFilterMode=")
  );
  if (!match) {
    return null;
  }
  const value = match.split("=").slice(1).join("=");
  return value ? decodeURIComponent(value) : null;
}

function saveLastBookingSiteFilter(value) {
  if (!value) {
    return;
  }
  const encoded = encodeURIComponent(value);
  document.cookie = `dashboardBookingSiteFilter=${encoded}; max-age=2592000; path=/`;
}

function getLastBookingSiteFilter() {
  const entries = document.cookie.split(";").map((cookie) => cookie.trim());
  const match = entries.find((cookie) =>
    cookie.startsWith("dashboardBookingSiteFilter=")
  );
  if (!match) {
    return null;
  }
  const value = match.split("=").slice(1).join("=");
  return value ? decodeURIComponent(value) : null;
}

function setupFlightsFilters() {
  const advancedFilterContainer = document.querySelector(
    "[data-flights-advanced-filter]"
  );
  if (!advancedFilterContainer) {
    return;
  }

  const rows = Array.from(
    document.querySelectorAll("tbody tr[data-traveller]")
  );
  const emptyRow = document.querySelector("[data-filter-empty]");
  const travellerName = document.querySelector("[data-traveller-name]");
  const travellerCount = document.querySelector("[data-traveller-count]");
  const bookingSiteName = document.querySelector("[data-booking-site-name]");
  const bookingSiteCount = document.querySelector("[data-booking-site-count]");
  const missingLegsToggle = document.querySelector("[data-missing-legs-toggle]");
  const duplicatesToggle = document.querySelector("[data-duplicates-toggle]");
  const mismatchToggle = document.querySelector("[data-mismatch-toggle]");
  const collapseGroupsToggle = document.querySelector(
    "[data-collapse-groups-toggle]"
  );
  const flightsTable = document.querySelector("[data-flight-table]");
  const advancedFilterMap = {
    aircraft: "aircraft",
    traveller: "travellerLabel",
    airline: "airline",
    source: "sourceLabel",
    airports: "airports",
    countries: "countries",
    cities: "cities",
    flight_number: "flightNumber",
    supplier_confirmation: "supplierConfirmation",
  };

  const getAdvancedFilters = () =>
    typeof window.getFlightsAdvancedFilters === "function"
      ? window.getFlightsAdvancedFilters()
      : [];

  const matchesAdvancedFilters = (row) => {
    const filters = getAdvancedFilters();
    if (!filters.length) {
      return true;
    }
    return filters.every((filter) => {
      const datasetKey = advancedFilterMap[filter.type];
      if (!datasetKey) {
        return true;
      }
      const raw = row.dataset[datasetKey];
      if (!raw) {
        return false;
      }
      const values = raw
        .split("|")
        .map((value) => normalizeLabel(value))
        .filter(Boolean);
      if (!values.length) {
        return false;
      }
      return values.some((value) => value.includes(filter.normalized));
    });
  };

  const applyFilters = () => {
    const advancedFilters = getAdvancedFilters();
    const hasTravellerFilters = advancedFilters.some(
      (filter) => filter.type === "traveller"
    );
    const hasSourceFilters = advancedFilters.some(
      (filter) => filter.type === "source"
    );
    const collapseGroups = Boolean(collapseGroupsToggle?.checked);
    const mismatchOnly = Boolean(mismatchToggle?.checked);
    if (flightsTable) {
      flightsTable.classList.toggle("collapse-groups", collapseGroups);
    }
    let visibleCount = 0;

    rows.forEach((row) => {
      if (!row.isConnected) {
        return;
      }
      const matchesGroup = !collapseGroups || row.dataset.groupPrimary === "1";
      const matchesAdvanced = matchesAdvancedFilters(row);
      const matchesMismatch = !mismatchOnly || row.dataset.geminiMismatch === "1";
      const matchesSearch = !flightsSearchIds || flightsSearchIds.has(row.dataset.flightId);
      const matches = matchesGroup && matchesAdvanced && matchesMismatch && matchesSearch;
      row.style.display = matches ? "" : "none";
      if (matches) {
        visibleCount += 1;
      }
    });

    const geminiRows = Array.from(
      document.querySelectorAll("[data-gemini-row]")
    );
    geminiRows.forEach((row) => {
      const flightId = row.dataset.flightId;
      if (!flightId) {
        return;
      }
      const flightRow = document.querySelector(
        `tr[data-flight-id="${flightId}"][data-traveller]`
      );
      if (!flightRow) {
        return;
      }
      row.style.display = flightRow.style.display === "none" ? "none" : "";
    });

    if (emptyRow) {
      emptyRow.style.display = visibleCount === 0 ? "" : "none";
    }

    if (travellerName) {
      travellerName.textContent = hasTravellerFilters
        ? "Filtered"
        : "All travellers";
    }
    if (travellerCount) {
      travellerCount.textContent = `${visibleCount} flights`;
    }
    if (bookingSiteName) {
      bookingSiteName.textContent = hasSourceFilters
        ? "Filtered"
        : "All booking sites";
    }
    if (bookingSiteCount) {
      bookingSiteCount.textContent = `${visibleCount} flights`;
    }
  };

  window.applyFlightsFilters = applyFilters;
  const applyHighlightToggles = () => {
    if (!flightsTable) {
      return;
    }
    flightsTable.classList.toggle(
      "show-missing-legs",
      Boolean(missingLegsToggle?.checked)
    );
    flightsTable.classList.toggle(
      "show-duplicates",
      Boolean(duplicatesToggle?.checked)
    );
  };

  if (missingLegsToggle) {
    missingLegsToggle.addEventListener("change", applyHighlightToggles);
  }
  if (duplicatesToggle) {
    duplicatesToggle.addEventListener("change", applyHighlightToggles);
  }
  if (mismatchToggle) {
    mismatchToggle.addEventListener("change", applyFilters);
  }
  if (collapseGroupsToggle) {
    collapseGroupsToggle.addEventListener("change", applyFilters);
  }

  updateGeminiMismatchGroups();
  applyFilters();
  applyHighlightToggles();
}

function setupFlightsAdvancedFilters() {
  const container = document.querySelector("[data-flights-advanced-filter]");
  if (!container) {
    return;
  }

  const chipList = container.querySelector("[data-chip-list]");
  const clearButton = container.querySelector("[data-flights-filter-clear]");
  const inputs = Array.from(
    container.querySelectorAll("[data-advanced-filter-input]")
  );
  const datalists = Array.from(
    container.querySelectorAll("[data-filter-datalist]")
  );
  const activeFilters = new Map();
  const typeLabels = {
    aircraft: "Aircraft type",
    traveller: "Traveller",
    airline: "Airline",
    source: "Source",
    airports: "Airport",
    countries: "Country",
    cities: "City",
    flight_number: "Flight number",
    supplier_confirmation: "Supplier confirmation",
  };

  const buildOptions = () => {
    const options = new Map();
    const flights = Array.isArray(window.flightsMergeData)
      ? window.flightsMergeData
      : [];

    const addOption = (type, value) => {
      const normalized = normalizeLabel(value);
      if (!normalized) {
        return;
      }
      if (!options.has(type)) {
        options.set(type, new Map());
      }
      const bucket = options.get(type);
      if (!bucket.has(normalized)) {
        bucket.set(normalized, value.trim());
      }
    };

    flights.forEach((flight) => {
      addOption("aircraft", flight.aircraft);
      addOption("traveller", flight.traveller);
      addOption("airline", flight.airline_code);
      addOption("airline", flight.operating_airline_code);
      addOption("source", flight.booking_site);
      addOption("airports", flight.start_airport);
      addOption("airports", flight.end_airport);
      addOption("airports", flight.origin_name);
      addOption("airports", flight.destination_name);
      addOption("countries", flight.start_country);
      addOption("countries", flight.end_country);
      addOption("cities", flight.start_city_name);
      addOption("cities", flight.end_city_name);
      addOption("flight_number", flight.flight_number);
      if (flight.airline_code && flight.flight_number) {
        addOption("flight_number", `${flight.airline_code}${flight.flight_number}`);
        addOption("flight_number", `${flight.airline_code} ${flight.flight_number}`);
      }
      addOption("supplier_confirmation", flight.supplier_confirmation);
    });

    return options;
  };

  const renderOptions = () => {
    const options = buildOptions();
    datalists.forEach((datalist) => {
      const type = datalist.dataset.filterDatalist;
      if (!type) {
        return;
      }
      const values = options.get(type);
      datalist.innerHTML = "";
      if (!values) {
        return;
      }
      Array.from(values.values())
        .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }))
        .forEach((label) => {
          const option = document.createElement("option");
          option.value = label;
          datalist.appendChild(option);
        });
    });
  };

  const updateControls = () => {
    if (clearButton) {
      clearButton.disabled = activeFilters.size === 0;
    }
  };

  const removeFilter = (key, chip) => {
    activeFilters.delete(key);
    chip?.remove();
    updateControls();
    if (typeof window.applyFlightsFilters === "function") {
      window.applyFlightsFilters();
    }
  };

  const createChip = (filter) => {
    if (!chipList) {
      return;
    }
    const chip = document.createElement("span");
    chip.className = "chip chip--removable";
    chip.dataset.filterKey = filter.key;
    chip.textContent = `${typeLabels[filter.type] || "Filter"}: ${filter.label}`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chip__remove";
    remove.setAttribute("aria-label", `Remove ${filter.label}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => removeFilter(filter.key, chip));

    chip.appendChild(remove);
    chipList.appendChild(chip);
  };

  const addFilter = (type, value) => {
    const normalized = normalizeLabel(value);
    if (!normalized) {
      return;
    }
    const label = value.trim();
    const key = `${type}:${normalized}`;
    if (activeFilters.has(key)) {
      return;
    }
    const filter = { key, type, label, normalized };
    activeFilters.set(key, filter);
    createChip(filter);
    updateControls();
    if (typeof window.applyFlightsFilters === "function") {
      window.applyFlightsFilters();
    }
  };

  const addChipFromInput = (input) => {
    if (!input) {
      return;
    }
    const raw = input.value;
    if (!raw) {
      return;
    }
    const type = input.dataset.filterType || "aircraft";
    raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach((item) => addFilter(type, item));
    input.value = "";
  };

  inputs.forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === ",") {
        event.preventDefault();
        addChipFromInput(input);
      }
    });
    input.addEventListener("blur", () => addChipFromInput(input));
    input.addEventListener("change", () => addChipFromInput(input));
    input.addEventListener("paste", (event) => {
      const paste = event.clipboardData.getData("text");
      if (!paste) {
        return;
      }
      event.preventDefault();
      const type = input.dataset.filterType || "aircraft";
      paste
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .forEach((item) => addFilter(type, item));
      input.value = "";
    });
  });

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      activeFilters.clear();
      if (chipList) {
        chipList.innerHTML = "";
      }
      updateControls();
      if (typeof window.applyFlightsFilters === "function") {
        window.applyFlightsFilters();
      }
    });
  }

  window.getFlightsAdvancedFilters = () => Array.from(activeFilters.values());
  renderOptions();
  updateControls();
}

function setupFlightsDelete() {
  const deleteForms = Array.from(
    document.querySelectorAll("[data-flight-delete]")
  );
  if (!deleteForms.length) {
    return;
  }

  const updateChipCounts = (group, key, delta) => {
    if (!group) {
      return;
    }
    const chips = Array.from(group.querySelectorAll(".chip"));
    const updateChip = (chip) => {
      const current = Number.parseInt(chip.dataset.count || "0", 10);
      const next = Math.max(current + delta, 0);
      chip.dataset.count = String(next);
      const label = chip.dataset.label || chip.textContent || "";
      if (chip.dataset.filter === "all") {
        chip.textContent = `All (${next})`;
      } else {
        chip.textContent = `${label} (${next})`;
      }
    };
    const allChip = chips.find((chip) => chip.dataset.filter === "all");
    if (allChip) {
      updateChip(allChip);
    }
    if (key) {
      const matchingChip = chips.find((chip) => chip.dataset.filter === key);
      if (matchingChip) {
        updateChip(matchingChip);
      }
    }
  };

  deleteForms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const row = form.closest("tr");
      const button = form.querySelector("button[type='submit']");
      if (!window.confirm("Delete this flight? This cannot be undone.")) {
        return;
      }
      if (button) {
        button.dataset.originalLabel = button.textContent;
        button.textContent = "Deleting...";
        button.disabled = true;
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || "Unable to delete flight.");
        }

        const checkbox = row?.querySelector("[data-merge-select]");
        if (checkbox && checkbox.checked) {
          checkbox.checked = false;
          checkbox.dispatchEvent(new Event("change", { bubbles: true }));
        }
        const travellerKey = row?.dataset.traveller;
        const bookingKey = row?.dataset.bookingSite;
        row?.remove();

        if (Array.isArray(window.flightsMergeData)) {
          const removedId = form.dataset.flightId;
          window.flightsMergeData = window.flightsMergeData.filter(
            (flight) => String(flight.id) !== String(removedId)
          );
        }

        updateChipCounts(
          document.querySelector("[data-traveller-filter]"),
          travellerKey,
          -1
        );
        updateChipCounts(
          document.querySelector("[data-booking-site-filter]"),
          bookingKey,
          -1
        );
        if (typeof window.applyFlightsFilters === "function") {
          window.applyFlightsFilters();
        }
      } catch (error) {
        alert(error.message || "Unable to delete flight.");
        if (button) {
          button.textContent = button.dataset.originalLabel || "Delete";
          delete button.dataset.originalLabel;
          button.disabled = false;
        }
      }
    });
  });
}

function setupHistoryDelete() {
  const deleteForms = Array.from(
    document.querySelectorAll("[data-history-delete]")
  );
  if (!deleteForms.length) {
    return;
  }
  deleteForms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm("Delete this history entry? This cannot be undone.")) {
        event.preventDefault();
      }
    });
  });
}

function setupFlightFollowUp() {
  const followUpForms = Array.from(
    document.querySelectorAll("[data-follow-up-form]")
  );
  if (!followUpForms.length) {
    return;
  }

  followUpForms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("[data-follow-up-button]");
      const input = form.querySelector("[data-follow-up-input]");
      const pill = form.closest("tr")?.querySelector("[data-follow-up-pill]");
      if (button) {
        button.dataset.originalLabel = button.textContent;
        button.textContent = "Updating...";
        button.disabled = true;
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || "Unable to update follow up flag.");
        }
        const isFlagged = Boolean(payload.follow_up);
        if (input) {
          input.value = isFlagged ? "0" : "1";
        }
        if (pill) {
          pill.hidden = !isFlagged;
        }
        if (button) {
          button.textContent = isFlagged ? "Unflag" : "Flag";
        }
      } catch (error) {
        alert(error.message || "Unable to update follow up flag.");
        if (button && button.dataset.originalLabel) {
          button.textContent = button.dataset.originalLabel;
        }
      } finally {
        if (button) {
          delete button.dataset.originalLabel;
          button.disabled = false;
        }
      }
    });
  });
}

function setupFlightExclude() {
  const excludeForms = Array.from(
    document.querySelectorAll("[data-exclude-form]")
  );
  if (!excludeForms.length) {
    return;
  }

  excludeForms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("[data-exclude-button]");
      const input = form.querySelector("[data-exclude-input]");
      if (button) {
        button.dataset.originalLabel = button.textContent;
        button.textContent = "Updating...";
        button.disabled = true;
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || "Unable to update exclude flag.");
        }
        const isExcluded = Boolean(payload.exclude_from_stats);
        if (input) {
          input.value = isExcluded ? "0" : "1";
        }
        if (button) {
          button.textContent = isExcluded ? "Include" : "Exclude";
          button.classList.toggle("danger", isExcluded);
          button.classList.toggle("ghost", !isExcluded);
        }
      } catch (error) {
        alert(error.message || "Unable to update exclude flag.");
        if (button && button.dataset.originalLabel) {
          button.textContent = button.dataset.originalLabel;
        }
      } finally {
        if (button) {
          delete button.dataset.originalLabel;
          button.disabled = false;
        }
      }
    });
  });
}

function setupFlightRegistrationClear() {
  const clearForms = Array.from(
    document.querySelectorAll("[data-clear-registration-form]")
  );
  if (!clearForms.length) {
    return;
  }

  clearForms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("[data-clear-registration-button]");
      if (button) {
        button.dataset.originalHtml = button.innerHTML;
        button.innerHTML = "Clearing...";
        button.disabled = true;
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || "Unable to clear registration.");
        }
        window.location.reload();
        return;
      } catch (error) {
        alert(error.message || "Unable to clear registration.");
      } finally {
        if (button) {
          button.innerHTML = button.dataset.originalHtml || button.innerHTML;
          delete button.dataset.originalHtml;
          button.disabled = false;
        }
      }
    });
  });
}

function normalizeFlightValue(value) {
  if (!value || value === "-") {
    return null;
  }
  return `${value}`.trim() || null;
}

function applyGeminiDiff(flightValue, geminiValue, ...targets) {
  const flightType = normalizeFlightValue(flightValue);
  const geminiType = normalizeFlightValue(geminiValue);
  const shouldDiff = Boolean(flightType && geminiType && flightType !== geminiType);
  targets.forEach((target) => {
    if (!target) {
      return;
    }
    target.classList.toggle("diff-value", shouldDiff);
  });
}

function isGeminiMismatch(flightSpan, geminiSpan) {
  const flightValue = normalizeFlightValue(flightSpan?.textContent);
  const geminiValue = normalizeFlightValue(geminiSpan?.textContent);
  return Boolean(flightValue && geminiValue && flightValue !== geminiValue);
}

function updateGeminiMismatchGroups() {
  const geminiRows = Array.from(document.querySelectorAll("[data-gemini-row]"));
  if (!geminiRows.length) {
    return;
  }

  const groupMismatch = new Map();
  geminiRows.forEach((row) => {
    const groupKey = row.dataset.groupKey;
    if (!groupKey) {
      return;
    }
    const flightTypeSpan = row.querySelector("[data-flight-aircraft-type]");
    const geminiTypeSpan = row.querySelector("[data-gemini-aircraft-type]");
    const flightRegSpan = row.querySelector(
      "[data-flight-aircraft-registration]"
    );
    const geminiRegSpan = row.querySelector(
      "[data-gemini-aircraft-registration]"
    );
    const mismatch =
      isGeminiMismatch(flightTypeSpan, geminiTypeSpan) ||
      isGeminiMismatch(flightRegSpan, geminiRegSpan);
    if (mismatch) {
      groupMismatch.set(groupKey, true);
    } else if (!groupMismatch.has(groupKey)) {
      groupMismatch.set(groupKey, false);
    }
  });

  const groupedRows = Array.from(
    document.querySelectorAll("[data-group-key]")
  );
  groupedRows.forEach((row) => {
    const groupKey = row.dataset.groupKey;
    if (!groupKey) {
      return;
    }
    if (groupMismatch.get(groupKey)) {
      row.dataset.geminiMismatch = "1";
    } else {
      delete row.dataset.geminiMismatch;
    }
  });
}

function updateHistoryFields(row, payload) {
  if (!row || !payload) {
    return;
  }
  const registration = payload.aircraft_registration || "-";
  const aircraftType = payload.aircraft_type || null;
  const historyId = payload.history_id;
  const registrationSpan = row.querySelector("[data-history-registration]");
  const typeWrap = row.querySelector("[data-history-aircraft-type-wrap]");
  const typeSpan = row.querySelector("[data-history-aircraft-type]");
  const linkWrap = row.querySelector("[data-history-link-wrap]");
  const link = row.querySelector("[data-history-link]");

  if (registrationSpan) {
    registrationSpan.textContent = registration;
  }
  if (typeSpan) {
    typeSpan.textContent = aircraftType || "-";
  }
  if (typeWrap) {
    typeWrap.hidden = !aircraftType;
  }
  if (linkWrap) {
    linkWrap.hidden = !historyId;
  }
  if (link && historyId) {
    link.href = `/flights/history/${historyId}`;
  }
}

function setupFlightGeminiAircraftOverwrite() {
  const forms = Array.from(
    document.querySelectorAll("[data-overwrite-gemini-form]")
  );
  if (!forms.length) {
    return;
  }

  forms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("[data-overwrite-gemini-button]");
      if (button) {
        button.dataset.originalHtml = button.innerHTML;
        button.innerHTML = "Updating...";
        button.disabled = true;
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || "Unable to update aircraft type.");
        }

        const updatedType = payload.aircraft_type || payload.aircraft || "-";
        const geminiRow = form.closest("tr");
        const flightRow = geminiRow ? geminiRow.previousElementSibling : null;
        const groupKey =
          payload.group_key || (flightRow ? flightRow.dataset.groupKey : null);
        const targetGeminiRows = groupKey
          ? Array.from(
              document.querySelectorAll(
                `[data-gemini-row][data-group-key="${groupKey}"]`
              )
            )
          : geminiRow
          ? [geminiRow]
          : [];

        targetGeminiRows.forEach((row) => {
          const flightTypeSpan = row.querySelector("[data-flight-aircraft-type]");
          const geminiTypeSpan = row.querySelector("[data-gemini-aircraft-type]");
          if (flightTypeSpan) {
            flightTypeSpan.textContent = updatedType || "-";
          }
          applyGeminiDiff(
            updatedType,
            geminiTypeSpan ? geminiTypeSpan.textContent : null,
            flightTypeSpan,
            geminiTypeSpan
          );
        });

        if (groupKey) {
          const aircraftValue = normalizeFlightValue(updatedType);
          const flightRows = Array.from(
            document.querySelectorAll(`[data-group-key="${groupKey}"]`)
          ).filter((row) => !row.hasAttribute("data-gemini-row"));
          flightRows.forEach((row) => {
            row.dataset.aircraft = aircraftValue
              ? aircraftValue.toLowerCase()
              : "";
          });
        } else if (flightRow) {
          const aircraftValue = normalizeFlightValue(updatedType);
          flightRow.dataset.aircraft = aircraftValue
            ? aircraftValue.toLowerCase()
            : "";
        }
        updateGeminiMismatchGroups();
        if (typeof window.applyFlightsFilters === "function") {
          window.applyFlightsFilters();
        }
      } catch (error) {
        alert(error.message || "Unable to update aircraft type.");
      } finally {
        if (button) {
          button.innerHTML = button.dataset.originalHtml || button.innerHTML;
          delete button.dataset.originalHtml;
          button.disabled = false;
        }
      }
    });
  });
}

function setupGeminiHistoryDelete() {
  const forms = Array.from(
    document.querySelectorAll("[data-gemini-history-delete]")
  );
  if (!forms.length) {
    return;
  }

  forms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const button = form.querySelector("[data-gemini-history-delete-button]");
      if (button) {
        button.dataset.originalHtml = button.innerHTML;
        button.innerHTML = "Deleting...";
        button.disabled = true;
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || "Unable to delete history entry.");
        }

        const geminiRow = form.closest("tr");
        if (geminiRow) {
          const flightTypeSpan = geminiRow.querySelector(
            "[data-flight-aircraft-type]"
          );
          const geminiTypeSpan = geminiRow.querySelector(
            "[data-gemini-aircraft-type]"
          );
          const flightRegSpan = geminiRow.querySelector(
            "[data-flight-aircraft-registration]"
          );
          const geminiRegSpan = geminiRow.querySelector(
            "[data-gemini-aircraft-registration]"
          );
          const reasoning = geminiRow.querySelector("[data-gemini-reasoning]");

          if (geminiTypeSpan) {
            geminiTypeSpan.textContent = "-";
          }
          if (geminiRegSpan) {
            geminiRegSpan.textContent = "-";
          }
          if (reasoning) {
            reasoning.textContent = "-";
          }

          applyGeminiDiff(
            flightTypeSpan ? flightTypeSpan.textContent : null,
            geminiTypeSpan ? geminiTypeSpan.textContent : null,
            flightTypeSpan,
            geminiTypeSpan
          );
          applyGeminiDiff(
            flightRegSpan ? flightRegSpan.textContent : null,
            geminiRegSpan ? geminiRegSpan.textContent : null,
            flightRegSpan,
            geminiRegSpan
          );
        }

        form.remove();
        updateGeminiMismatchGroups();
        if (typeof window.applyFlightsFilters === "function") {
          window.applyFlightsFilters();
        }
      } catch (error) {
        alert(error.message || "Unable to delete history entry.");
      } finally {
        if (button) {
          button.innerHTML = button.dataset.originalHtml || button.innerHTML;
          delete button.dataset.originalHtml;
          button.disabled = false;
        }
      }
    });
  });
}

function setupFlightAircraftApply() {
  const forms = Array.from(
    document.querySelectorAll("[data-apply-flight-aircraft-form]")
  );
  if (!forms.length) {
    return;
  }

  forms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("[data-apply-flight-aircraft-button]");
      if (button) {
        button.dataset.originalHtml = button.innerHTML;
        button.innerHTML = "Updating...";
        button.disabled = true;
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "fetch",
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || "Unable to apply aircraft type.");
        }

        const updatedType = payload.aircraft_type || payload.aircraft || "-";
        const groupKey = payload.group_key;
        const targetGeminiRows = groupKey
          ? Array.from(
              document.querySelectorAll(
                `[data-gemini-row][data-group-key="${groupKey}"]`
              )
            )
          : [];
        targetGeminiRows.forEach((row) => {
          const flightTypeSpan = row.querySelector("[data-flight-aircraft-type]");
          const geminiTypeSpan = row.querySelector("[data-gemini-aircraft-type]");
          if (flightTypeSpan) {
            flightTypeSpan.textContent = updatedType || "-";
          }
          applyGeminiDiff(
            updatedType,
            geminiTypeSpan ? geminiTypeSpan.textContent : null,
            flightTypeSpan,
            geminiTypeSpan
          );
        });

        const aircraftValue = normalizeFlightValue(updatedType);
        const flightRows = groupKey
          ? Array.from(
              document.querySelectorAll(`[data-group-key="${groupKey}"]`)
            ).filter((row) => !row.hasAttribute("data-gemini-row"))
          : [];
        flightRows.forEach((row) => {
          row.dataset.aircraft = aircraftValue ? aircraftValue.toLowerCase() : "";
        });

        updateGeminiMismatchGroups();
        if (typeof window.applyFlightsFilters === "function") {
          window.applyFlightsFilters();
        }
      } catch (error) {
        alert(error.message || "Unable to apply aircraft type.");
      } finally {
        if (button) {
          button.innerHTML = button.dataset.originalHtml || button.innerHTML;
          delete button.dataset.originalHtml;
          button.disabled = false;
        }
      }
    });
  });
}

function setupFlightMerge() {
  const toolbar = document.querySelector("[data-merge-toolbar]");
  const mergeButton = document.querySelector("[data-merge-button]");
  const groupForm = document.querySelector("[data-merge-group-form]");
  const groupButton = document.querySelector("[data-group-button]");
  const groupInput = document.querySelector("[data-merge-group-selected]");
  const ungroupForm = document.querySelector("[data-ungroup-form]");
  const ungroupButton = document.querySelector("[data-ungroup-button]");
  const ungroupInput = document.querySelector("[data-ungroup-selected]");
  const countLabel = document.querySelector("[data-merge-count]");
  const modal = document.querySelector("[data-merge-modal]");
  const summary = document.querySelector("[data-merge-summary]");
  const primaryOptions = document.querySelector("[data-merge-primary-options]");
  const fieldsContainer = document.querySelector("[data-merge-fields]");
  const confirmButton = document.querySelector("[data-merge-confirm]");
  const cancelButtons = modal
    ? Array.from(modal.querySelectorAll("[data-merge-cancel]"))
    : [];
  const primaryInput = document.querySelector("[data-merge-primary-input]");
  const selectedInput = document.querySelector("[data-merge-selected-input]");
  const checkboxes = Array.from(document.querySelectorAll("[data-merge-select]"));

  if (!toolbar || !mergeButton || !countLabel || !checkboxes.length || !modal) {
    return;
  }

  const flights = Array.isArray(window.flightsMergeData)
    ? window.flightsMergeData
    : [];
  const flightMap = new Map(
    flights.map((flight) => [String(flight.id), flight])
  );

  const MERGE_FIELDS = [
    "trip_name",
    "trip_id",
    "trip_type",
    "activity_id",
    "activity_cost",
    "url",
    "booking_site",
    "supplier_confirmation",
    "booking_date",
    "booking_site_phone",
    "traveller",
    "ticket_number",
    "airline_code",
    "aircraft",
    "service_class",
    "flight_number",
    "start_country",
    "start_city_name",
    "start_airport",
    "start_terminal",
    "start_lat",
    "start_long",
    "start_date",
    "start_time",
    "end_country",
    "end_city_name",
    "end_airport",
    "end_terminal",
    "end_lat",
    "end_long",
    "end_date",
    "end_time",
    "stops",
    "route_direction",
    "distance",
  ];

  const PREVIEW_FIELDS = [
    { key: "trip_name", label: "Trip name" },
    { key: "trip_id", label: "Trip id" },
    { key: "trip_type", label: "Trip type" },
    { key: "activity_id", label: "Activity id" },
    { key: "activity_cost", label: "Activity cost" },
    { key: "url", label: "Booking URL" },
    { key: "booking_site", label: "Booking site" },
    { key: "supplier_confirmation", label: "Supplier confirmation" },
    { key: "booking_date", label: "Booking date" },
    { key: "booking_site_phone", label: "Booking phone" },
    { key: "traveller", label: "Traveller" },
    { key: "ticket_number", label: "Ticket number" },
    { key: "airline_code", label: "Airline code" },
    { key: "flight_number", label: "Flight number" },
    { key: "service_class", label: "Service class" },
    { key: "aircraft", label: "Aircraft" },
    { key: "stops", label: "Stops" },
    { key: "distance", label: "Distance" },
    { key: "start_date", label: "Start date" },
    { key: "start_time", label: "Start time" },
    { key: "start_country", label: "Start country" },
    { key: "start_city_name", label: "Start city" },
    { key: "start_airport", label: "Start airport" },
    { key: "start_terminal", label: "Start terminal" },
    { key: "start_lat", label: "Start latitude" },
    { key: "start_long", label: "Start longitude" },
    { key: "end_date", label: "End date" },
    { key: "end_time", label: "End time" },
    { key: "end_country", label: "End country" },
    { key: "end_city_name", label: "End city" },
    { key: "end_airport", label: "End airport" },
    { key: "end_terminal", label: "End terminal" },
    { key: "end_lat", label: "End latitude" },
    { key: "end_long", label: "End longitude" },
    { key: "route_direction", label: "Route direction" },
  ];

  const isEmpty = (value) =>
    value == null || (typeof value === "string" && value.trim() === "");

  const formatValue = (value) => (isEmpty(value) ? "-" : value);

  const mergeBookingSites = (...values) => {
    const sites = [];
    const seen = new Set();
    values.forEach((value) => {
      if (value == null) {
        return;
      }
      String(value)
        .split("+")
        .forEach((part) => {
          const trimmed = part.trim();
          if (!trimmed) {
            return;
          }
          const key = trimmed.toLowerCase();
          if (seen.has(key)) {
            return;
          }
          seen.add(key);
          sites.push(trimmed);
        });
    });
    return sites.length ? sites.join("+") : null;
  };

  const summarizeFlight = (flight) => {
    if (!flight) {
      return "Unknown flight";
    }
    const dateLabel = flight.start_date || "Unknown date";
    const originLabel = flight.origin_name || "Unknown start";
    const destinationLabel = flight.destination_name || "Unknown end";
    const flightLabel = flight.flight_number
      ? ` · ${flight.flight_number}`
      : "";
    return `${dateLabel} · ${originLabel} → ${destinationLabel}${flightLabel}`;
  };

  const buildMerged = (primary, others) => {
    if (!primary) {
      return null;
    }
    const merged = { ...primary };
    others.forEach((source) => {
      if (!source) {
        return;
      }
      MERGE_FIELDS.forEach((key) => {
        if (key === "booking_site") {
          const mergedBookingSite = mergeBookingSites(
            merged.booking_site,
            source.booking_site
          );
          if (mergedBookingSite !== merged.booking_site) {
            merged.booking_site = mergedBookingSite;
          }
          return;
        }
        if (isEmpty(merged[key]) && !isEmpty(source[key])) {
          merged[key] = source[key];
        }
      });
    });
    return merged;
  };

  const selectedIds = () =>
    checkboxes
      .filter((checkbox) => checkbox.isConnected && checkbox.checked)
      .map((checkbox) => checkbox.value);

  const updateToolbar = () => {
    const ids = selectedIds();
    countLabel.textContent = `${ids.length} selected`;
    mergeButton.disabled = ids.length < 2;
    if (groupButton) {
      groupButton.disabled = ids.length < 2;
    }
    if (groupInput) {
      groupInput.value = ids.join(",");
    }
    if (ungroupButton) {
      ungroupButton.disabled = ids.length < 2;
    }
    if (ungroupInput) {
      ungroupInput.value = ids.join(",");
    }
  };

  let activePrimaryId = null;
  let activeSelected = [];

  const renderPrimaryOptions = () => {
    if (!primaryOptions) {
      return;
    }
    primaryOptions.innerHTML = "";
    activeSelected.forEach((id) => {
      const flight = flightMap.get(String(id));
      const option = document.createElement("label");
      option.className = "merge-preview__option";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "merge-primary";
      radio.value = id;
      radio.checked = id === activePrimaryId;
      radio.addEventListener("change", () => {
        activePrimaryId = id;
        updatePreview();
      });

      const text = document.createElement("span");
      text.textContent = summarizeFlight(flight);

      option.append(radio, text);
      primaryOptions.appendChild(option);
    });
  };

  const renderMergedFields = (merged) => {
    if (!fieldsContainer) {
      return;
    }
    fieldsContainer.innerHTML = "";
    PREVIEW_FIELDS.forEach(({ key, label }) => {
      const row = document.createElement("div");
      row.className = "merge-preview__field is-editable";

      const term = document.createElement("dt");
      term.textContent = label;
      const desc = document.createElement("dd");
      const input = document.createElement("input");
      input.type = "text";
      input.name = key;
      if (merged && merged[key] != null) {
        input.value = merged[key];
      }
      input.placeholder = "-";
      desc.appendChild(input);

      row.append(term, desc);
      fieldsContainer.appendChild(row);
    });
  };

  const updatePreview = () => {
    if (!modal || modal.hidden) {
      return;
    }
    const primary = flightMap.get(String(activePrimaryId));
    const others = activeSelected
      .filter((id) => id !== activePrimaryId)
      .map((id) => flightMap.get(String(id)))
      .filter(Boolean);
    const merged = buildMerged(primary, others);

    if (summary) {
      if (activeSelected.length >= 2 && primary) {
        summary.textContent = `Merging ${activeSelected.length} records into flight ${primary.id}.`;
      } else {
        summary.textContent = "Select at least two flights to merge.";
      }
    }

    if (primaryInput) {
      primaryInput.value = activePrimaryId || "";
    }
    if (selectedInput) {
      selectedInput.value = activeSelected.join(",");
    }
    if (confirmButton) {
      confirmButton.disabled = activeSelected.length < 2 || !primary;
    }

    renderMergedFields(merged);
  };

  const openModal = () => {
    activeSelected = selectedIds();
    activePrimaryId = activeSelected[0] || null;
    modal.hidden = false;
    renderPrimaryOptions();
    updatePreview();
  };

  const closeModal = () => {
    modal.hidden = true;
  };

  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      updateToolbar();
      if (!modal || modal.hidden) {
        return;
      }
      activeSelected = selectedIds();
      if (!activeSelected.includes(activePrimaryId)) {
        activePrimaryId = activeSelected[0] || null;
      }
      renderPrimaryOptions();
      updatePreview();
    });
  });

  mergeButton.addEventListener("click", openModal);
  cancelButtons.forEach((button) => {
    button.addEventListener("click", closeModal);
  });

  updateToolbar();
}

function setupGeminiCodeshareLookup() {
  const button = document.querySelector("[data-gemini-lookup]");
  if (!button) {
    return;
  }
  const status = document.querySelector("[data-gemini-status]");
  const overwriteInput = document.querySelector("[data-gemini-overwrite]");
  const recordUrl = button.dataset.geminiRecordUrl;
  const modal = document.querySelector("[data-gemini-modal]");
  const requestEl = modal?.querySelector("[data-gemini-request]");
  const responseEl = modal?.querySelector("[data-gemini-response]");
  const closeButtons = modal
    ? Array.from(modal.querySelectorAll("[data-gemini-close]"))
    : [];
  const form = button.closest("form");
  if (!form) {
    return;
  }

  const setStatus = (message, isError = false) => {
    if (!status) {
      return;
    }
    if (!message) {
      status.textContent = "";
      status.hidden = true;
      status.classList.remove("errors");
      status.classList.add("muted");
      return;
    }
    status.textContent = message;
    status.hidden = false;
    status.classList.toggle("errors", isError);
    status.classList.toggle("muted", !isError);
  };

  const setButtonLoading = (isLoading, label = "Looking up...") => {
    if (isLoading) {
      button.dataset.originalLabel = button.textContent;
      button.textContent = label;
      button.disabled = true;
      return;
    }
    if (button.dataset.originalLabel) {
      button.textContent = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
    }
    button.disabled = false;
  };

  const openModal = () => {
    if (modal) {
      modal.hidden = false;
    }
  };

  const closeModal = () => {
    if (modal) {
      modal.hidden = true;
    }
  };

  closeButtons.forEach((closeButton) => {
    closeButton.addEventListener("click", closeModal);
  });

  const setJsonBlock = (element, value) => {
    if (!element) {
      return;
    }
    if (!value) {
      element.textContent = "No data returned.";
      return;
    }
    element.textContent = JSON.stringify(value, null, 2);
  };

  const setFieldValue = (name, value) => {
    if (!value) {
      return false;
    }
    const field = form.querySelector(`input[name="${name}"]`);
    if (!field) {
      return false;
    }
    const shouldOverwrite = overwriteInput ? overwriteInput.checked : true;
    if (!shouldOverwrite && field.value) {
      return false;
    }
    field.value = value;
    return true;
  };

  button.addEventListener("click", async () => {
    const url = button.dataset.geminiUrl;
    if (!url) {
      return;
    }
    setStatus("");
    setButtonLoading(true);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const payload = await response.json();
      const requestInfo = payload?.request;
      const responseInfo = payload?.response;
      if (requestInfo || responseInfo) {
        setJsonBlock(requestEl, requestInfo);
        setJsonBlock(responseEl, responseInfo);
        openModal();
      }
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Lookup failed.");
      }
      const details = payload.details || {};
      let updates = 0;
      updates += setFieldValue("aircraft", details.aircraft_type) ? 1 : 0;
      updates += setFieldValue(
        "operating_airline_code",
        details.operating_airline_code
      )
        ? 1
        : 0;
      updates += setFieldValue(
        "operating_flight_number",
        details.operating_flight_number
      )
        ? 1
        : 0;
      if (updates && recordUrl) {
        const appliedFields = [];
        if (details.aircraft_type) {
          appliedFields.push("aircraft");
        }
        if (details.operating_airline_code) {
          appliedFields.push("operating_airline_code");
        }
        if (details.operating_flight_number) {
          appliedFields.push("operating_flight_number");
        }
        fetch(recordUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            details,
            request: requestInfo,
            response: responseInfo,
            applied_fields: appliedFields,
          }),
        }).catch(() => {});
      }
      if (updates) {
        setStatus("Gemini lookup applied to form fields.");
      } else {
        setStatus("Gemini lookup returned no new fields.");
      }
    } catch (err) {
      setStatus(err?.message || "Lookup failed.", true);
    } finally {
      setButtonLoading(false, "Gemini codeshare lookup");
    }
  });
}

function setupFlightHistoryRefresh() {
  const buttons = Array.from(
    document.querySelectorAll("[data-flight-history-refresh]")
  );
  if (!buttons.length) {
    return;
  }

  const startLoading = (button, label = "Refreshing...") => {
    if (!button) {
      return;
    }
    if (!button.dataset.originalLabel) {
      button.dataset.originalLabel = button.textContent;
    }
    button.textContent = label;
    button.disabled = true;
  };

  const endLoading = (button) => {
    if (!button) {
      return;
    }
    if (button.dataset.originalLabel) {
      button.textContent = button.dataset.originalLabel;
    }
    button.disabled = false;
  };

  buttons.forEach((button) => {
    button.addEventListener("click", async () => {
      const url = button.dataset.flightHistoryUrl;
      if (!url) {
        return;
      }
      console.info("[FlightHistory] Request", {
        url,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "fetch",
        },
      });
      startLoading(button);
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "fetch",
          },
        });
        const rawText = await response.text();
        let payload = null;
        try {
          payload = rawText ? JSON.parse(rawText) : null;
        } catch (err) {
          console.warn("[FlightHistory] Non-JSON response", rawText);
        }
        console.info("[FlightHistory] Response", {
          status: response.status,
          ok: response.ok,
          payload,
          rawText: payload ? undefined : rawText,
        });
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Refresh failed.");
        }
        if (button.dataset.flightHistoryTarget === "history") {
          const row = button.closest("tr");
          updateHistoryFields(row, payload);
        }
        if (button.dataset.flightHistoryReload === "true") {
          window.location.reload();
          return;
        }
        const originalLabel = button.dataset.originalLabel || "Refresh history";
        endLoading(button);
        button.textContent = "History updated";
        setTimeout(() => {
          button.textContent = originalLabel;
        }, 1500);
      } catch (err) {
        endLoading(button);
        window.alert(err?.message || "Refresh failed.");
      }
    });
  });
}

function setupAuditMerge() {
  const modal = document.querySelector("[data-audit-merge-modal]");
  const openButtons = Array.from(
    document.querySelectorAll("[data-audit-merge-button]")
  );
  if (!modal || !openButtons.length) {
    return;
  }

  const summary = modal.querySelector("[data-audit-merge-summary]");
  const options = modal.querySelector("[data-audit-merge-options]");
  const fieldsContainer = modal.querySelector("[data-audit-merge-fields]");
  const primaryInput = modal.querySelector("[data-audit-merge-primary]");
  const selectedInput = modal.querySelector("[data-audit-merge-selected]");
  const confirmButton = modal.querySelector("[data-audit-merge-confirm]");
  const cancelButtons = Array.from(
    modal.querySelectorAll("[data-audit-merge-cancel]")
  );

  const flights = Array.isArray(window.auditFlights) ? window.auditFlights : [];
  const flightMap = new Map(
    flights.map((flight) => [String(flight.id), flight])
  );

  const MERGE_FIELDS = [
    "trip_name",
    "trip_id",
    "trip_type",
    "activity_id",
    "activity_cost",
    "url",
    "booking_site",
    "supplier_confirmation",
    "booking_date",
    "booking_site_phone",
    "traveller",
    "ticket_number",
    "airline_code",
    "aircraft",
    "service_class",
    "flight_number",
    "start_country",
    "start_city_name",
    "start_airport",
    "start_terminal",
    "start_lat",
    "start_long",
    "start_date",
    "start_time",
    "end_country",
    "end_city_name",
    "end_airport",
    "end_terminal",
    "end_lat",
    "end_long",
    "end_date",
    "end_time",
    "stops",
    "route_direction",
    "distance",
  ];

  const PREVIEW_FIELDS = [
    { key: "trip_name", label: "Trip name" },
    { key: "trip_id", label: "Trip id" },
    { key: "trip_type", label: "Trip type" },
    { key: "activity_id", label: "Activity id" },
    { key: "activity_cost", label: "Activity cost" },
    { key: "url", label: "Booking URL" },
    { key: "booking_site", label: "Booking site" },
    { key: "supplier_confirmation", label: "Supplier confirmation" },
    { key: "booking_date", label: "Booking date" },
    { key: "booking_site_phone", label: "Booking phone" },
    { key: "traveller", label: "Traveller" },
    { key: "ticket_number", label: "Ticket number" },
    { key: "airline_code", label: "Airline code" },
    { key: "flight_number", label: "Flight number" },
    { key: "service_class", label: "Service class" },
    { key: "aircraft", label: "Aircraft" },
    { key: "stops", label: "Stops" },
    { key: "distance", label: "Distance" },
    { key: "start_date", label: "Start date" },
    { key: "start_time", label: "Start time" },
    { key: "start_country", label: "Start country" },
    { key: "start_city_name", label: "Start city" },
    { key: "start_airport", label: "Start airport" },
    { key: "start_terminal", label: "Start terminal" },
    { key: "start_lat", label: "Start latitude" },
    { key: "start_long", label: "Start longitude" },
    { key: "end_date", label: "End date" },
    { key: "end_time", label: "End time" },
    { key: "end_country", label: "End country" },
    { key: "end_city_name", label: "End city" },
    { key: "end_airport", label: "End airport" },
    { key: "end_terminal", label: "End terminal" },
    { key: "end_lat", label: "End latitude" },
    { key: "end_long", label: "End longitude" },
    { key: "route_direction", label: "Route direction" },
  ];

  const confirmValue = (value, fallback) => {
    if (value == null) {
      return fallback;
    }
    if (typeof value === "string") {
      const trimmed = value.trim();
      return trimmed ? trimmed : fallback;
    }
    return value;
  };

  const summarizeFlight = (flight) => {
    if (!flight) {
      return "Unknown flight";
    }
    const dateLabel = flight.start_date || "Unknown date";
    const originLabel = confirmValue(flight.origin_name, "Unknown start");
    const destinationLabel = confirmValue(flight.destination_name, "Unknown end");
    const flightLabel = flight.flight_number
      ? ` · ${flight.flight_number}`
      : "";
    return `${dateLabel} · ${originLabel} → ${destinationLabel}${flightLabel}`;
  };

  const isEmpty = (value) =>
    value == null || (typeof value === "string" && value.trim() === "");

  const formatValue = (value) => (isEmpty(value) ? "-" : value);

  const mergeBookingSites = (...values) => {
    const sites = [];
    const seen = new Set();
    values.forEach((value) => {
      if (value == null) {
        return;
      }
      String(value)
        .split("+")
        .forEach((part) => {
          const trimmed = part.trim();
          if (!trimmed) {
            return;
          }
          const key = trimmed.toLowerCase();
          if (seen.has(key)) {
            return;
          }
          seen.add(key);
          sites.push(trimmed);
        });
    });
    return sites.length ? sites.join("+") : null;
  };

  const buildMerged = (primary, others) => {
    if (!primary) {
      return null;
    }
    const merged = { ...primary };
    others.forEach((source) => {
      if (!source) {
        return;
      }
      MERGE_FIELDS.forEach((key) => {
        if (key === "booking_site") {
          const mergedBookingSite = mergeBookingSites(
            merged.booking_site,
            source.booking_site
          );
          if (mergedBookingSite !== merged.booking_site) {
            merged.booking_site = mergedBookingSite;
          }
          return;
        }
        if (isEmpty(merged[key]) && !isEmpty(source[key])) {
          merged[key] = source[key];
        }
      });
    });
    return merged;
  };

  const renderMergedFields = (merged) => {
    if (!fieldsContainer) {
      return;
    }
    fieldsContainer.innerHTML = "";
    PREVIEW_FIELDS.forEach(({ key, label }) => {
      const row = document.createElement("div");
      row.className = "merge-preview__field";

      const term = document.createElement("dt");
      term.textContent = label;
      const desc = document.createElement("dd");
      desc.textContent = formatValue(merged ? merged[key] : null);

      row.append(term, desc);
      fieldsContainer.appendChild(row);
    });
  };

  let activePrimaryId = null;
  let activeSelected = [];

  const renderOptions = () => {
    if (!options) {
      return;
    }
    options.innerHTML = "";
    activeSelected.forEach((id) => {
      const flight = flightMap.get(String(id));
      const option = document.createElement("label");
      option.className = "merge-preview__option";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "audit-merge-primary";
      radio.value = id;
      radio.checked = id === activePrimaryId;
      radio.addEventListener("change", () => {
        activePrimaryId = id;
        updateForm();
      });

      const text = document.createElement("span");
      text.textContent = summarizeFlight(flight);

      option.append(radio, text);
      options.appendChild(option);
    });
  };

  const updateForm = () => {
    const primary = flightMap.get(String(activePrimaryId));
    const others = activeSelected
      .filter((id) => id !== activePrimaryId)
      .map((id) => flightMap.get(String(id)))
      .filter(Boolean);
    const merged = buildMerged(primary, others);

    if (primaryInput) {
      primaryInput.value = activePrimaryId || "";
    }
    if (selectedInput) {
      selectedInput.value = activeSelected.join(",");
    }
    if (confirmButton) {
      confirmButton.disabled = activeSelected.length < 2 || !activePrimaryId;
    }

    renderMergedFields(merged);
  };

  const openModal = (ids) => {
    activeSelected = ids;
    activePrimaryId = ids[0] || null;
    if (summary) {
      summary.textContent = `Merging ${ids.length} records. Choose the primary record.`;
    }
    renderOptions();
    updateForm();
    modal.hidden = false;
  };

  const closeModal = () => {
    modal.hidden = true;
  };

  openButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const raw = button.dataset.mergeIds || "";
      const ids = raw
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      if (ids.length < 2) {
        return;
      }
      openModal(ids);
    });
  });

  cancelButtons.forEach((button) => {
    button.addEventListener("click", closeModal);
  });
}

function setupTravellerChipInput() {
  const container = document.querySelector("[data-traveller-chip-input]");
  if (!container) {
    return;
  }

  const chipList = container.querySelector("[data-chip-list]");
  const input = container.querySelector("[data-chip-input]");
  const activeKeys = new Map();
  const travellerOptions = Array.isArray(window.travellerOptions)
    ? window.travellerOptions
    : [];
  const allowedKeys = new Map(
    travellerOptions.map((option) => [option.key, option.label])
  );
  const datalist = container.querySelector("#traveller-options");
  const labelToKey = new Map(
    travellerOptions.map((option) => [option.label, option.key])
  );
  const normalizedLookup = travellerOptions.reduce((acc, option) => {
    const normalized = option.label.trim().toLowerCase();
    if (!normalized) {
      return acc;
    }
    if (!acc.has(normalized)) {
      acc.set(normalized, []);
    }
    acc.get(normalized).push(option);
    return acc;
  }, new Map());
  const filterSummary = document.querySelector("[data-filter-summary]");
  const modeToggle = document.querySelector("[data-traveller-mode-toggle]");
  const modeButtons = modeToggle
    ? Array.from(modeToggle.querySelectorAll("[data-filter-mode]"))
    : [];
  let filterMode = dashboardFilterState.travellerMode || "include";

  const resolveKey = (value) => {
    if (!value) {
      return null;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    if (labelToKey.has(trimmed)) {
      return { key: labelToKey.get(trimmed), label: trimmed };
    }
    const normalized = trimmed.toLowerCase();
    const matches = normalizedLookup.get(normalized) || [];
    if (matches.length === 1) {
      return { key: matches[0].key, label: matches[0].label };
    }
    return null;
  };

  const applyFilters = () => {
    const keys = Array.from(activeKeys.keys());
    if (filterSummary) {
      if (keys.length) {
        const modeLabel = filterMode === "exclude" ? "Excluding" : "Including";
        filterSummary.textContent = `${modeLabel} ${keys.length} traveller${
          keys.length === 1 ? "" : "s"
        }`;
      } else {
        filterSummary.textContent = "All travellers";
      }
    }
    if (datalist) {
      datalist.innerHTML = "";
      travellerOptions.forEach((option) => {
        if (activeKeys.has(option.key)) {
          return;
        }
        const opt = document.createElement("option");
        opt.value = option.label;
        opt.textContent = option.label;
        datalist.appendChild(opt);
      });
    }
    dashboardFilterState.travellerKeys = new Set(keys);
    dashboardFilterState.travellerMode = filterMode;
    applyDashboardFilters();
  };

  const syncModeButtons = () => {
    modeButtons.forEach((button) => {
      button.classList.toggle(
        "is-active",
        button.dataset.filterMode === filterMode
      );
    });
  };

  modeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.filterMode;
      if (!mode || mode === filterMode) {
        return;
      }
      filterMode = mode === "exclude" ? "exclude" : "include";
      syncModeButtons();
      saveLastTravellerFilterMode(filterMode);
      applyFilters();
    });
  });

  const removeChip = (key, chip) => {
    activeKeys.delete(key);
    chip.remove();
    applyFilters();
  };

  const createChip = (label, key) => {
    const chip = document.createElement("span");
    chip.className = "chip chip--removable";
    chip.dataset.key = key;
    chip.textContent = label;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chip__remove";
    remove.setAttribute("aria-label", `Remove ${label}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => removeChip(key, chip));

    chip.appendChild(remove);
    chipList.appendChild(chip);
  };

  const addChipFromInput = () => {
    if (!input) {
      return;
    }
    const raw = input.value.trim();
    if (!raw) {
      return;
    }

    const resolved = resolveKey(raw);
    if (!resolved) {
      input.value = "";
      return;
    }
    if (!activeKeys.has(resolved.key)) {
      activeKeys.set(resolved.key, resolved.label);
      createChip(resolved.label, resolved.key);
      saveLastTravellerFilter(resolved.label);
      openDashboardFilters();
    }
    input.value = "";
    applyFilters();
  };

  const addChip = (value) => {
    if (!value) {
      return;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    const resolved = resolveKey(trimmed);
    if (!resolved) {
      return;
    }
    if (!activeKeys.has(resolved.key)) {
      activeKeys.set(resolved.key, resolved.label);
      createChip(resolved.label, resolved.key);
      saveLastTravellerFilter(resolved.label);
      applyFilters();
    }
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addChipFromInput();
    } else if (event.key === "Backspace" && !input.value && chipList) {
      const lastChip = chipList.lastElementChild;
      if (lastChip) {
        const key = lastChip.dataset.key;
        if (key) {
          removeChip(key, lastChip);
        }
      }
    }
  });

  input.addEventListener("blur", addChipFromInput);

  input.addEventListener("paste", (event) => {
    const paste = event.clipboardData.getData("text");
    if (!paste) {
      return;
    }
    event.preventDefault();
    paste
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach(addChip);
    input.value = "";
  });

  const savedMode = getLastTravellerFilterMode();
  if (savedMode === "exclude") {
    filterMode = "exclude";
  }
  syncModeButtons();

  const savedFilter = getLastTravellerFilter();
  if (savedFilter) {
    addChip(savedFilter);
  }

  applyFilters();
}

function setupBookingSiteChipInput() {
  const container = document.querySelector("[data-booking-site-chip-input]");
  if (!container) {
    return;
  }

  const chipList = container.querySelector("[data-chip-list]");
  const input = container.querySelector("[data-chip-input]");
  const activeKeys = new Map();
  const bookingSiteOptions = Array.isArray(window.bookingSiteOptions)
    ? window.bookingSiteOptions
    : [];
  const datalist = container.querySelector("#booking-site-options");
  const labelToKey = new Map(
    bookingSiteOptions.map((option) => [option.label, option.key])
  );
  const normalizedLookup = bookingSiteOptions.reduce((acc, option) => {
    const normalized = option.label.trim().toLowerCase();
    if (!normalized) {
      return acc;
    }
    if (!acc.has(normalized)) {
      acc.set(normalized, []);
    }
    acc.get(normalized).push(option);
    return acc;
  }, new Map());
  const filterSummary = document.querySelector("[data-booking-site-summary]");

  const resolveKey = (value) => {
    if (!value) {
      return null;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    if (labelToKey.has(trimmed)) {
      return { key: labelToKey.get(trimmed), label: trimmed };
    }
    const normalized = trimmed.toLowerCase();
    const matches = normalizedLookup.get(normalized) || [];
    if (matches.length === 1) {
      return { key: matches[0].key, label: matches[0].label };
    }
    return null;
  };

  const applyFilters = () => {
    const keys = Array.from(activeKeys.keys());
    if (filterSummary) {
      if (keys.length) {
        filterSummary.textContent = `Filtering ${keys.length} booking site${
          keys.length === 1 ? "" : "s"
        }`;
      } else {
        filterSummary.textContent = "All booking sites";
      }
    }
    if (datalist) {
      datalist.innerHTML = "";
      bookingSiteOptions.forEach((option) => {
        if (activeKeys.has(option.key)) {
          return;
        }
        const opt = document.createElement("option");
        opt.value = option.label;
        opt.textContent = option.label;
        datalist.appendChild(opt);
      });
    }
    dashboardFilterState.bookingSiteKeys = new Set(keys);
    applyDashboardFilters();
  };

  const removeChip = (key, chip) => {
    activeKeys.delete(key);
    chip.remove();
    applyFilters();
  };

  const createChip = (label, key) => {
    const chip = document.createElement("span");
    chip.className = "chip chip--removable";
    chip.dataset.key = key;
    chip.textContent = label;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chip__remove";
    remove.setAttribute("aria-label", `Remove ${label}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => removeChip(key, chip));

    chip.appendChild(remove);
    chipList.appendChild(chip);
  };

  const addChipFromInput = () => {
    if (!input) {
      return;
    }
    const raw = input.value.trim();
    if (!raw) {
      return;
    }

    const resolved = resolveKey(raw);
    if (!resolved) {
      input.value = "";
      return;
    }
    if (!activeKeys.has(resolved.key)) {
      activeKeys.set(resolved.key, resolved.label);
      createChip(resolved.label, resolved.key);
      saveLastBookingSiteFilter(resolved.label);
      openDashboardFilters();
    }
    input.value = "";
    applyFilters();
  };

  const addChip = (value) => {
    if (!value) {
      return;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    const resolved = resolveKey(trimmed);
    if (!resolved) {
      return;
    }
    if (!activeKeys.has(resolved.key)) {
      activeKeys.set(resolved.key, resolved.label);
      createChip(resolved.label, resolved.key);
      saveLastBookingSiteFilter(resolved.label);
      applyFilters();
    }
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addChipFromInput();
    } else if (event.key === "Backspace" && !input.value && chipList) {
      const lastChip = chipList.lastElementChild;
      if (lastChip) {
        const key = lastChip.dataset.key;
        if (key) {
          removeChip(key, lastChip);
        }
      }
    }
  });

  input.addEventListener("blur", addChipFromInput);

  input.addEventListener("paste", (event) => {
    const paste = event.clipboardData.getData("text");
    if (!paste) {
      return;
    }
    event.preventDefault();
    paste
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach(addChip);
    input.value = "";
  });

  const savedFilter = getLastBookingSiteFilter();
  if (savedFilter) {
    addChip(savedFilter);
  }

  applyFilters();
}

function setupDashboardTableFilters() {
  const container = document.querySelector("[data-dashboard-table-filter]");
  if (!container) {
    return;
  }

  const chipList = container.querySelector("[data-dashboard-table-chip-list]");
  const clearButton = container.querySelector("[data-dashboard-table-clear]");
  const emptyHint = document.querySelector("[data-dashboard-table-empty]");
  const filterMaps = dashboardFilterState.tableFilters || {};
  const typeLabels = {
    cities: "City",
    airlines: "Airline",
    aircraft: "Aircraft",
    tailnumbers: "Tailnumber",
    countries: "Country",
    routes: "Route",
    years: "Year",
  };

  const countFilters = () =>
    Object.values(filterMaps).reduce(
      (total, map) => total + (map?.size || 0),
      0
    );

  const updateControls = () => {
    const total = countFilters();
    if (clearButton) {
      clearButton.disabled = total === 0;
    }
    if (emptyHint) {
      emptyHint.hidden = total > 0;
    }
  };

  const removeFilter = (type, key, chip) => {
    if (filterMaps[type]) {
      filterMaps[type].delete(key);
    }
    chip?.remove();
    updateControls();
    applyDashboardFilters();
  };

  const createChip = (type, key, label) => {
    if (!chipList) {
      return;
    }
    const chip = document.createElement("span");
    chip.className = "chip chip--removable";
    chip.dataset.filterType = type;
    chip.dataset.filterKey = key;
    chip.textContent = `${typeLabels[type] || "Filter"}: ${label}`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chip__remove";
    remove.setAttribute("aria-label", `Remove ${label}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => removeFilter(type, key, chip));

    chip.appendChild(remove);
    chipList.appendChild(chip);
  };

  const addFilter = (type, key, label) => {
    if (!type || !key || !filterMaps[type]) {
      return;
    }
    const normalizedKey = normalizeLabel(key) || "unknown";
    if (filterMaps[type].has(normalizedKey)) {
      return;
    }
    const displayLabel = label || key || "Unknown";
    filterMaps[type].set(normalizedKey, displayLabel);
    createChip(type, normalizedKey, displayLabel);
    openDashboardFilters();
    updateControls();
    applyDashboardFilters();
  };

  const clearAll = () => {
    Object.values(filterMaps).forEach((map) => map?.clear());
    if (chipList) {
      chipList.innerHTML = "";
    }
    updateControls();
    applyDashboardFilters();
  };

  if (clearButton) {
    clearButton.addEventListener("click", clearAll);
  }

  window.addDashboardTableFilter = addFilter;
  updateControls();
}

function setupAuditGrouping() {
  const forms = Array.from(document.querySelectorAll("[data-audit-group-form]"));
  if (!forms.length) {
    return;
  }

  const setButtonLoading = (button, isLoading, label = "Updating...") => {
    if (!button) {
      return;
    }
    if (isLoading) {
      button.dataset.originalLabel = button.textContent;
      button.textContent = label;
      button.disabled = true;
      return;
    }
    if (button.dataset.originalLabel) {
      button.textContent = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
    }
    button.disabled = false;
  };

  forms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("[data-audit-group-button]");
      const panel = form.closest("[data-audit-group-panel]");
      if (!button || !panel) {
        form.submit();
        return;
      }

      const currentGroupingId = panel.dataset.groupingId || "";
      const nextUrl = currentGroupingId
        ? button.dataset.ungroupUrl
        : button.dataset.confirmUrl;
      if (!nextUrl) {
        form.submit();
        return;
      }

      setButtonLoading(button, true);
      try {
        const response = await fetch(nextUrl, {
          method: "POST",
          headers: {
            Accept: "application/json",
          },
          body: new FormData(form),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Update failed.");
        }

        const groupingId = payload.grouping_id || "";
        panel.dataset.groupingId = groupingId;
        panel.classList.toggle("panel--grouped", Boolean(groupingId));
        if (typeof window.applyAuditGroupedFilter === "function") {
          window.applyAuditGroupedFilter();
        }

        const label = panel.querySelector("[data-audit-group-label]");
        const idTarget = panel.querySelector("[data-audit-group-id]");
        if (label) {
          label.hidden = !groupingId;
        }
        if (idTarget) {
          idTarget.textContent = groupingId;
        }

        setButtonLoading(button, false);
        delete button.dataset.originalLabel;
        button.textContent = groupingId
          ? button.dataset.labelUngroup || "Ungroup"
          : button.dataset.labelConfirm || "Confirm grouping";
      } catch (err) {
        form.submit();
      } finally {
        if (button && button.disabled) {
          setButtonLoading(button, false);
        }
      }
    });
  });
}

function applyAuditGroupedFilter() {
  const toggle = document.querySelector("[data-audit-group-toggle]");
  const panels = Array.from(
    document.querySelectorAll("[data-audit-group-panel]")
  );
  if (!toggle || !panels.length) {
    return;
  }
  const hideGrouped = toggle.checked;
  panels.forEach((panel) => {
    const isGrouped = Boolean(panel.dataset.groupingId);
    panel.style.display = hideGrouped && isGrouped ? "none" : "";
  });
}

function setupAuditGroupedToggle() {
  const toggle = document.querySelector("[data-audit-group-toggle]");
  if (!toggle) {
    return;
  }
  window.applyAuditGroupedFilter = applyAuditGroupedFilter;
  toggle.addEventListener("change", applyAuditGroupedFilter);
  applyAuditGroupedFilter();
}

function setupAuditMissingGroupedToggle() {
  const toggle = document.querySelector("[data-audit-missing-grouped-toggle]");
  if (!toggle) {
    return;
  }
  toggle.addEventListener("change", () => {
    const params = new URLSearchParams(window.location.search);
    if (toggle.checked) {
      params.set("exclude_grouped", "1");
    } else {
      params.delete("exclude_grouped");
    }
    const query = params.toString();
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.location.assign(nextUrl);
  });
}

function setupAuditMissingLegsToggle() {
  const toggle = document.querySelector("[data-audit-legs-ungrouped-toggle]");
  if (!toggle) {
    return;
  }
  toggle.addEventListener("change", () => {
    const params = new URLSearchParams(window.location.search);
    if (toggle.checked) {
      params.set("include_ungrouped", "1");
    } else {
      params.delete("include_ungrouped");
    }
    const query = params.toString();
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.location.assign(nextUrl);
  });
}

function setupAuditSuggestedToggle() {
  const toggle = document.querySelector("[data-audit-legs-suggested-toggle]");
  const rows = Array.from(document.querySelectorAll("[data-audit-suggested-row]"));
  if (!toggle || !rows.length) {
    return;
  }

  const applyToggle = () => {
    const showSuggested = toggle.checked;
    rows.forEach((row) => {
      row.style.display = showSuggested ? "" : "none";
    });
  };

  toggle.addEventListener("change", applyToggle);
  applyToggle();
}

function setupAircraftLightbox() {
  const modal = document.querySelector("[data-aircraft-modal]");
  if (!modal) {
    return;
  }

  const image = modal.querySelector("[data-aircraft-modal-image]");
  const title = modal.querySelector("[data-aircraft-modal-title]");
  const closeButtons = Array.from(modal.querySelectorAll("[data-aircraft-close]"));

  const closeModal = () => {
    modal.hidden = true;
    if (image) {
      image.src = "";
      image.alt = "";
    }
  };

  const openModal = (src, label) => {
    if (!image || !src) {
      return;
    }
    image.src = src;
    image.alt = label ? `Aircraft ${label}` : "Aircraft image";
    if (title) {
      title.textContent = label ? `Aircraft ${label}` : "Aircraft image";
    }
    modal.hidden = false;
  };

  // Setup triggers for aircraft page
  const triggers = Array.from(
    document.querySelectorAll("[data-aircraft-lightbox]")
  );
  triggers.forEach((button) => {
    button.addEventListener("click", () => {
      const src = button.dataset.fullSrc;
      if (!src) {
        return;
      }
      const label = button.dataset.title || "";
      openModal(src, label);
    });
  });

  // Setup close buttons (always, even if no triggers on this page)
  closeButtons.forEach((button) => {
    button.addEventListener("click", closeModal);
  });

  // ESC key to close
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      closeModal();
    }
  });
}

function setupTripLegEditor() {
  const container = document.querySelector("[data-trip-legs]");
  const template = document.querySelector("[data-leg-template]");
  const addButton = document.querySelector("[data-leg-add]");
  const prefillButton = document.querySelector("[data-leg-add-prefill]");
  if (!container || !template || !addButton) {
    return;
  }
  let nextIndex = Number(container.dataset.nextIndex || "0");

  const getSequenceInput = (leg) =>
    leg ? leg.querySelector('[name$="-sequence"]') : null;
  const parseSequenceValue = (input) => {
    if (!input) {
      return null;
    }
    const parsed = Number.parseInt(input.value || "", 10);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const getVisibleLegs = () =>
    Array.from(container.querySelectorAll("[data-trip-leg]")).filter((leg) => {
      const deleteInput = leg.querySelector("[data-leg-delete]");
      if (leg.hidden) {
        return false;
      }
      if (deleteInput && deleteInput.value === "1") {
        return false;
      }
      return true;
    });
  const updateLegTitles = () => {
    const visibleLegs = getVisibleLegs();
    visibleLegs.forEach((leg, index) => {
      const title = leg.querySelector("[data-leg-title]");
      if (!title) {
        return;
      }
      const sequence = parseSequenceValue(getSequenceInput(leg)) ?? index + 1;
      title.textContent = `Leg ${sequence}`;
    });
  };

  const insertLegAfter = (afterLeg) => {
    if (!afterLeg) {
      return;
    }
    const visibleLegs = getVisibleLegs();
    const afterIndex = visibleLegs.indexOf(afterLeg);
    const baseSequence =
      parseSequenceValue(getSequenceInput(afterLeg)) ?? afterIndex + 1;
    const html = template.innerHTML.replace(/__index__/g, String(nextIndex));
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    const newLeg = wrapper.firstElementChild;
    if (!newLeg) {
      return;
    }
    afterLeg.insertAdjacentElement("afterend", newLeg);
    attachLegHandlers(newLeg);
    const sequenceInput = getSequenceInput(newLeg);
    if (sequenceInput) {
      sequenceInput.value = String(baseSequence + 1);
    }
    if (typeof setupAirportLookup === "function") {
      setupAirportLookup();
    }
    nextIndex += 1;
    container.dataset.nextIndex = String(nextIndex);

    const refreshedLegs = getVisibleLegs();
    const newIndex = refreshedLegs.indexOf(newLeg);
    const newSequence =
      parseSequenceValue(getSequenceInput(newLeg)) ?? newIndex + 1;
    for (let idx = newIndex + 1; idx < refreshedLegs.length; idx += 1) {
      const input = getSequenceInput(refreshedLegs[idx]);
      if (!input) {
        continue;
      }
      const current = parseSequenceValue(input);
      input.value =
        current === null
          ? String(newSequence + (idx - newIndex))
          : String(current + 1);
    }
    updateLegTitles();
  };

  const attachLegHandlers = (leg) => {
    const removeButton = leg.querySelector("[data-leg-remove]");
    const deleteInput = leg.querySelector("[data-leg-delete]");
    if (!removeButton || !deleteInput) {
      return;
    }
    const insertButton = leg.querySelector("[data-leg-insert]");
    removeButton.addEventListener("click", () => {
      deleteInput.value = "1";
      leg.classList.add("is-removed");
      leg.hidden = true;
      updateLegTitles();
    });
    if (insertButton) {
      insertButton.addEventListener("click", () => {
        insertLegAfter(leg);
      });
    }
  };

  const addLeg = (prefillFrom = null) => {
    const lastLeg = resolveLastLeg();
    const html = template.innerHTML.replace(/__index__/g, String(nextIndex));
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    const newLeg = wrapper.firstElementChild;
    if (!newLeg) {
      return;
    }
    container.appendChild(newLeg);
    attachLegHandlers(newLeg);
    if (!prefillFrom) {
      const sequenceInput = getSequenceInput(newLeg);
      if (sequenceInput) {
        const lastSequence =
          parseSequenceValue(getSequenceInput(lastLeg)) ??
          (lastLeg ? getVisibleLegs().length - 1 : 0);
        sequenceInput.value = String(lastSequence + 1);
      }
    }
    if (typeof setupAirportLookup === "function") {
      setupAirportLookup();
    }
    if (prefillFrom) {
      const fields = [
        "sequence",
        "mode",
        "carrier_name",
        "carrier_code",
        "service_class",
        "flight_number",
        "start_country",
        "start_city_name",
        "start_airport",
        "end_country",
        "end_city_name",
        "end_airport",
        "start_year",
        "start_month",
        "start_day",
        "start_precision",
        "end_year",
        "end_month",
        "end_day",
        "end_precision",
        "notes",
      ];
      fields.forEach((field) => {
        const source = prefillFrom.querySelector(
          `[name$="-${field}"]`
        );
        const target = newLeg.querySelector(`[name$="-${field}"]`);
        if (!source || !target) {
          return;
        }
        target.value = source.value || "";
      });
      const sourceSequence = prefillFrom.querySelector('[name$="-sequence"]');
      const targetSequence = newLeg.querySelector('[name$="-sequence"]');
      if (sourceSequence && targetSequence) {
        const parsed = Number.parseInt(sourceSequence.value || "0", 10);
        targetSequence.value = Number.isFinite(parsed) ? String(parsed + 1) : "";
      }
      const movePairs = [
        ["end_country", "start_country"],
        ["end_city_name", "start_city_name"],
        ["end_airport", "start_airport"],
        ["end_year", "start_year"],
        ["end_month", "start_month"],
        ["end_day", "start_day"],
        ["end_precision", "start_precision"],
      ];
      movePairs.forEach(([from, to]) => {
        const source = prefillFrom.querySelector(`[name$="-${from}"]`);
        const target = newLeg.querySelector(`[name$="-${to}"]`);
        if (source && target) {
          target.value = source.value || "";
        }
        const clearTarget = newLeg.querySelector(`[name$="-${from}"]`);
        if (clearTarget) {
          clearTarget.value = "";
        }
      });
      const startYear = newLeg.querySelector('[name$="-start_year"]');
      const startMonth = newLeg.querySelector('[name$="-start_month"]');
      const endYear = newLeg.querySelector('[name$="-end_year"]');
      const endMonth = newLeg.querySelector('[name$="-end_month"]');
      if (startYear && endYear) {
        endYear.value = startYear.value || "";
      }
      if (startMonth && endMonth) {
        endMonth.value = startMonth.value || "";
      }
    }
    nextIndex += 1;
    container.dataset.nextIndex = String(nextIndex);
    updateLegTitles();
  };

  Array.from(container.querySelectorAll("[data-trip-leg]")).forEach(
    attachLegHandlers
  );
  const resolveLastLeg = () => {
    const legs = Array.from(container.querySelectorAll("[data-trip-leg]"));
    for (let idx = legs.length - 1; idx >= 0; idx -= 1) {
      const leg = legs[idx];
      const deleteInput = leg.querySelector("[data-leg-delete]");
      if (deleteInput && deleteInput.value === "1") {
        continue;
      }
      if (leg.hidden) {
        continue;
      }
      return leg;
    }
    return null;
  };

  addButton.addEventListener("click", () => addLeg());
  if (prefillButton) {
    prefillButton.addEventListener("click", () => {
      const lastLeg = resolveLastLeg();
      addLeg(lastLeg);
    });
  }
  updateLegTitles();
}

let airportIndexPromise = null;
let airportIndex = null;

function parseCsvLine(line) {
  const fields = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      fields.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  fields.push(current);
  return fields;
}

function loadAirportIndex() {
  if (airportIndexPromise) {
    return airportIndexPromise;
  }
  const url = window.airportDataUrl || "/static/airports.dat";
  airportIndexPromise = fetch(url)
    .then((response) => (response.ok ? response.text() : ""))
    .then((text) => {
      const entries = [];
      const lines = text.split(/\r?\n/);
      lines.forEach((line) => {
        if (!line) {
          return;
        }
        const fields = parseCsvLine(line);
        if (fields.length < 6) {
          return;
        }
        const name = fields[1] || "";
        const city = fields[2] || "";
        const country = fields[3] || "";
        const iata = fields[4] || "";
        const icao = fields[5] || "";
        const code = iata && iata !== "\\N" ? iata : icao;
        if (!code || code === "\\N") {
          return;
        }
        const lat = parseFloat(fields[6]);
        const lng = parseFloat(fields[7]);
        entries.push({
          code: code.toUpperCase(),
          name,
          city,
          country,
          latitude: Number.isFinite(lat) ? lat : null,
          longitude: Number.isFinite(lng) ? lng : null,
        });
      });
      airportIndex = entries;
      return entries;
    })
    .catch(() => {
      airportIndex = [];
      return [];
    });
  return airportIndexPromise;
}

function setupAirportLookup() {
  const inputs = Array.from(document.querySelectorAll("[data-airport-lookup]"));
  if (!inputs.length) {
    return;
  }

  const findScopedInput = (input, field) => {
    const scope = input.closest("[data-trip-leg]") || input.closest("form");
    if (!scope) {
      return null;
    }
    const legMatch = input.name.includes("legs-");
    if (legMatch) {
      return scope.querySelector(`[name$="-${field}"]`);
    }
    return scope.querySelector(`[name="${field}"]`);
  };

  const buildLabel = (entry) =>
    `${entry.code} · ${entry.name} (${entry.city}, ${entry.country})`;

  const attach = (input) => {
    if (input.dataset.airportBound === "1") {
      return;
    }
    const cityField = input.dataset.airportCityField;
    const countryField = input.dataset.airportCountryField;
    const label = input.closest("label");
    if (!label) {
      return;
    }
    label.style.position = "relative";
    const dropdown = document.createElement("div");
    dropdown.className = "airport-suggest";
    dropdown.hidden = true;
    label.appendChild(dropdown);

    const closeDropdown = () => {
      dropdown.hidden = true;
      dropdown.innerHTML = "";
    };

    const renderResults = (results) => {
      dropdown.innerHTML = "";
      if (!results.length) {
        closeDropdown();
        return;
      }
      results.forEach((entry) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "airport-suggest__item";
        item.textContent = buildLabel(entry);
        item.addEventListener("click", () => {
          input.value = entry.code;
          const cityTarget = cityField
            ? findScopedInput(input, cityField)
            : null;
          const countryTarget = countryField
            ? findScopedInput(input, countryField)
            : null;
          if (cityTarget && entry.city) {
            cityTarget.value = entry.city;
          }
          if (countryTarget && entry.country) {
            countryTarget.value = entry.country;
          }
          const latField = input.name.startsWith("start_")
            ? "start_lat"
            : input.name.startsWith("end_")
              ? "end_lat"
              : null;
          const lngField = input.name.startsWith("start_")
            ? "start_long"
            : input.name.startsWith("end_")
              ? "end_long"
              : null;
          if (latField && entry.latitude != null) {
            const target = findScopedInput(input, latField);
            if (target) target.value = entry.latitude;
          }
          if (lngField && entry.longitude != null) {
            const target = findScopedInput(input, lngField);
            if (target) target.value = entry.longitude;
          }
          input.dispatchEvent(new Event("airport:resolved", { bubbles: true }));
          closeDropdown();
        });
        dropdown.appendChild(item);
      });
      dropdown.hidden = false;
    };

    const searchAirports = (query) => {
      const normalized = query.trim().toLowerCase();
      if (!normalized) {
        closeDropdown();
        return;
      }
      loadAirportIndex().then((entries) => {
        const results = entries
          .filter((entry) => {
            const code = entry.code.toLowerCase();
            const city = (entry.city || "").toLowerCase();
            const name = (entry.name || "").toLowerCase();
            return (
              code.startsWith(normalized) ||
              city.includes(normalized) ||
              name.includes(normalized)
            );
          })
          .slice(0, 8);
        renderResults(results);
      });
    };

    input.addEventListener("input", () => {
      searchAirports(input.value);
    });
    input.addEventListener("focus", () => {
      if (input.value) {
        searchAirports(input.value);
      }
    });
    input.addEventListener("blur", () => {
      setTimeout(closeDropdown, 150);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeDropdown();
      }
    });
    input.dataset.airportBound = "1";
  };

  inputs.forEach(attach);
}

function setupMobileNav() {
  const nav = document.querySelector(".navbar");
  const toggle = document.querySelector(".nav-toggle");
  if (!nav || !toggle) {
    return;
  }

  const isMobile = () => window.innerWidth <= 900;

  const setExpanded = (isOpen) => {
    nav.classList.toggle("is-open", isOpen);
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    if (!isOpen) {
      nav.querySelectorAll(".nav-dropdown.is-open").forEach((d) => d.classList.remove("is-open"));
    }
  };

  toggle.addEventListener("click", () => {
    const isOpen = !nav.classList.contains("is-open");
    setExpanded(isOpen);
  });

  /* Dropdown click-to-toggle on mobile */
  nav.querySelectorAll(".nav-dropdown__button").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      if (!isMobile()) return;
      e.preventDefault();
      const dropdown = btn.closest(".nav-dropdown");
      const wasOpen = dropdown.classList.contains("is-open");
      /* Close any other open dropdowns */
      nav.querySelectorAll(".nav-dropdown.is-open").forEach((d) => {
        if (d !== dropdown) d.classList.remove("is-open");
      });
      dropdown.classList.toggle("is-open", !wasOpen);
    });
  });

  const links = Array.from(nav.querySelectorAll(".nav-links a"));
  links.forEach((link) => {
    link.addEventListener("click", () => setExpanded(false));
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) {
      setExpanded(false);
    }
  });
}

function setupDashboardDistanceToggle() {
  const toggle = document.querySelector("[data-distance-unit-toggle]");
  if (!toggle) {
    window.dashboardDistanceUnit = "mi";
    return;
  }
  const initialUnit = loadDistanceUnitPreference();
  window.dashboardDistanceUnit = initialUnit;
  toggle.checked = initialUnit === "km";
  updateDistanceLabels(initialUnit);
  toggle.addEventListener("change", () => {
    setDashboardDistanceUnit(toggle.checked ? "km" : "mi");
  });
}

function setupScriptRunner() {
  const select = document.querySelector("[data-script-select]");
  if (!select || !Array.isArray(window.scriptCatalog)) {
    return;
  }

  const description = document.querySelector("[data-script-description]");
  const argsContainer = document.querySelector("[data-script-arguments]");
  const optionsContainer = document.querySelector("[data-script-options]");
  const runButton = document.querySelector("[data-script-run]");
  const stopButton = document.querySelector("[data-script-stop]");
  const clearButton = document.querySelector("[data-script-clear]");
  const output = document.querySelector("[data-script-output]");
  const status = document.querySelector("[data-script-status]");
  const commandEl = document.querySelector("[data-script-command]");
  const historyContainer = document.querySelector("[data-script-history]");

  if (!description || !argsContainer || !optionsContainer || !runButton || !output) {
    return;
  }

  const scriptsByKey = new Map(
    window.scriptCatalog.map((script) => [script.key, script])
  );
  let activeRunId = null;
  let pollTimer = null;
  let cursor = 0;

  const setStatus = (text, isRunning = false) => {
    if (status) {
      status.textContent = text;
    }
    runButton.disabled = !select.value || isRunning;
    select.disabled = isRunning;
    if (stopButton) {
      stopButton.disabled = !isRunning;
    }
  };

  const setCommand = (command) => {
    if (!commandEl) {
      return;
    }
    if (!command) {
      commandEl.textContent = "";
      return;
    }
    commandEl.textContent = Array.isArray(command) ? command.join(" ") : command;
  };

  const clearContainers = () => {
    argsContainer.innerHTML = "";
    optionsContainer.innerHTML = "";
  };

  const addSectionTitle = (container, title) => {
    const heading = document.createElement("div");
    heading.className = "panel-meta";
    heading.textContent = title;
    container.appendChild(heading);
  };

  const renderScript = (script) => {
    if (!script) {
      description.textContent = "Choose a script to view its details.";
      clearContainers();
      setCommand("");
      setStatus("Idle", false);
      return;
    }

    description.textContent = script.description || "";
    clearContainers();

    if (script.arguments && script.arguments.length > 0) {
      addSectionTitle(argsContainer, "Arguments");
      const argList = document.createElement("div");
      argList.className = "script-runner__arg-list";
      script.arguments.forEach((arg) => {
        const label = document.createElement("label");
        label.textContent = arg.label;
        const input = document.createElement("input");
        input.type = "text";
        input.dataset.scriptArgument = arg.id;
        input.placeholder = arg.help || "";
        if (arg.required) {
          input.required = true;
        }
        label.appendChild(input);
        argList.appendChild(label);
      });
      argsContainer.appendChild(argList);
    }

    if (script.options && script.options.length > 0) {
      addSectionTitle(optionsContainer, "Options");
      const optionList = document.createElement("div");
      optionList.className = "script-runner__option-list";
      script.options.forEach((option) => {
        if (option.type === "toggle") {
          const toggle = document.createElement("label");
          toggle.className = "audit-toggle";
          const input = document.createElement("input");
          input.type = "checkbox";
          input.className = "audit-toggle__input";
          input.dataset.scriptOption = option.id;
          if (option.default) {
            input.checked = true;
          }
          const track = document.createElement("span");
          track.className = "audit-toggle__track";
          const thumb = document.createElement("span");
          thumb.className = "audit-toggle__thumb";
          track.appendChild(thumb);
          const labelText = document.createElement("span");
          labelText.className = "audit-toggle__label";
          labelText.textContent = option.label;
          toggle.appendChild(input);
          toggle.appendChild(track);
          toggle.appendChild(labelText);
          optionList.appendChild(toggle);
        } else {
          const label = document.createElement("label");
          label.textContent = option.label;
          const input = document.createElement("input");
          input.type = "text";
          input.dataset.scriptOption = option.id;
          input.placeholder = option.help || "";
          if (option.default) {
            input.value = option.default;
          }
          label.appendChild(input);
          optionList.appendChild(label);
        }
      });
      optionsContainer.appendChild(optionList);
    }

    setCommand(`python scripts/${script.filename}`);
    setStatus("Ready", false);
  };

  const clearPolling = () => {
    if (pollTimer) {
      window.clearTimeout(pollTimer);
    }
    pollTimer = null;
  };

  const appendOutput = (lines) => {
    if (!lines || lines.length === 0) {
      return;
    }
    output.value += lines.join("");
    output.scrollTop = output.scrollHeight;
  };

  const formatTimestamp = (value) => {
    if (!value) {
      return "Unknown time";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleString();
  };

  const renderHistory = (history) => {
    if (!historyContainer) {
      return;
    }
    historyContainer.innerHTML = "";
    if (!history || history.length === 0) {
      const empty = document.createElement("div");
      empty.className = "muted";
      empty.textContent = "No history yet.";
      historyContainer.appendChild(empty);
      return;
    }
    history.forEach((entry) => {
      const item = document.createElement("div");
      item.className = "script-history__item";

      const left = document.createElement("div");
      const title = document.createElement("div");
      title.className = "script-history__title";
      title.textContent = entry.script_key
        ? entry.script_key.replace(/_/g, " ")
        : "Unknown script";
      const command = document.createElement("div");
      command.className = "script-history__command";
      command.textContent = Array.isArray(entry.command)
        ? entry.command.join(" ")
        : entry.command || "";
      const meta = document.createElement("div");
      meta.className = "script-history__meta";
      meta.textContent = `Started ${formatTimestamp(entry.created_at)}`;
      left.appendChild(title);
      left.appendChild(command);
      left.appendChild(meta);

      const right = document.createElement("div");
      right.className = "script-history__right";
      const statusEl = document.createElement("div");
      statusEl.className = "script-history__status";
      const exitSuffix =
        entry.exit_code === null || entry.exit_code === undefined
          ? ""
          : ` (exit ${entry.exit_code})`;
      statusEl.textContent = `${entry.status || "unknown"}${exitSuffix}`;
      const finished = document.createElement("div");
      finished.className = "script-history__meta";
      finished.textContent = entry.finished_at
        ? `Finished ${formatTimestamp(entry.finished_at)}`
        : "Still running";
      right.appendChild(statusEl);
      right.appendChild(finished);

      item.appendChild(left);
      item.appendChild(right);
      historyContainer.appendChild(item);
    });
  };

  const refreshHistory = async () => {
    if (!historyContainer) {
      return;
    }
    try {
      const response = await fetch("/utilities/scripts/history", {
        headers: { "X-Requested-With": "fetch" },
      });
      const payload = await response.json();
      if (payload.ok) {
        renderHistory(payload.history);
      }
    } catch (error) {
      // Ignore history refresh failures.
    }
  };

  const pollRun = async () => {
    if (!activeRunId) {
      return;
    }
    try {
      const response = await fetch(
        `/utilities/scripts/status/${activeRunId}?cursor=${cursor}`,
        { headers: { "X-Requested-With": "fetch" } }
      );
      const payload = await response.json();
      if (!payload.ok) {
        setStatus(payload.error || "Failed to fetch status.");
        runButton.disabled = false;
        return;
      }
      appendOutput(payload.output);
      cursor = payload.next_cursor || cursor;
      setCommand(payload.command);
      if (payload.status === "running" || payload.status === "stopping") {
        setStatus("Running...", true);
        pollTimer = window.setTimeout(pollRun, 1000);
      } else {
        let resultLabel = "Failed";
        if (payload.status === "success") {
          resultLabel = "Completed";
        } else if (payload.status === "stopped") {
          resultLabel = "Stopped";
        }
        const exitSuffix =
          payload.exit_code === null || payload.exit_code === undefined
            ? ""
            : ` (exit ${payload.exit_code})`;
        setStatus(`${resultLabel}${exitSuffix}`, false);
        activeRunId = null;
        refreshHistory();
      }
    } catch (error) {
      setStatus("Failed to fetch status.");
      runButton.disabled = false;
    }
  };

  const startRun = async () => {
    const scriptKey = select.value;
    if (!scriptKey) {
      return;
    }

    const argumentsPayload = {};
    const argumentInputs = argsContainer.querySelectorAll("[data-script-argument]");
    argumentInputs.forEach((input) => {
      const value = input.value.trim();
      if (value) {
        argumentsPayload[input.dataset.scriptArgument] = value;
      }
    });

    const optionsPayload = {};
    const optionInputs = optionsContainer.querySelectorAll("[data-script-option]");
    optionInputs.forEach((input) => {
      if (input.type === "checkbox") {
        optionsPayload[input.dataset.scriptOption] = input.checked;
      } else if (input.value.trim()) {
        optionsPayload[input.dataset.scriptOption] = input.value.trim();
      }
    });

    setStatus("Starting...", true);
    clearPolling();
    activeRunId = null;
    cursor = 0;
    output.value = "";

    try {
      const response = await fetch("/utilities/scripts/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "fetch",
        },
        body: JSON.stringify({
          script_key: scriptKey,
          options: optionsPayload,
          arguments: argumentsPayload,
        }),
      });
      const payload = await response.json();
      if (!payload.ok) {
        setStatus(payload.error || "Failed to start script.");
        runButton.disabled = false;
        return;
      }
      activeRunId = payload.run_id;
      setCommand(payload.command);
      setStatus("Running...", true);
      refreshHistory();
      pollTimer = window.setTimeout(pollRun, 800);
    } catch (error) {
      setStatus("Failed to start script.");
      runButton.disabled = false;
    }
  };

  const stopRun = async () => {
    if (!activeRunId) {
      return;
    }
    try {
      const response = await fetch("/utilities/scripts/stop", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "fetch",
        },
        body: JSON.stringify({ run_id: activeRunId }),
      });
      const payload = await response.json();
      if (!payload.ok) {
        setStatus(payload.error || "Failed to stop script.");
        return;
      }
      setStatus("Stopping...", true);
      pollTimer = window.setTimeout(pollRun, 800);
    } catch (error) {
      setStatus("Failed to stop script.");
    }
  };

  select.addEventListener("change", () => {
    renderScript(scriptsByKey.get(select.value));
  });

  runButton.addEventListener("click", startRun);

  if (stopButton) {
    stopButton.addEventListener("click", stopRun);
  }

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      output.value = "";
      cursor = 0;
    });
  }

  renderScript(scriptsByKey.get(select.value));
  refreshHistory();
}

function setupMapControls() {
  const select = document.querySelector('[data-map-color-scheme]');
  if (!select) return;

  const saved = localStorage.getItem('mapColorScheme') || 'default';
  select.value = saved;
  window.currentMapColorScheme = saved;

  select.addEventListener('change', (e) => {
    const scheme = e.target.value;
    window.currentMapColorScheme = scheme;
    localStorage.setItem('mapColorScheme', scheme);
    renderMap(window.mapRoutes, scheme);
  });

  // Setup fullscreen toggle
  const fullscreenBtn = document.querySelector('[data-map-fullscreen-toggle]');
  const mapPanel = document.querySelector('[data-map-panel]');

  if (fullscreenBtn && mapPanel) {
    fullscreenBtn.addEventListener('click', () => {
      const isFullscreen = mapPanel.hasAttribute('data-fullscreen');

      if (isFullscreen) {
        mapPanel.removeAttribute('data-fullscreen');
      } else {
        mapPanel.setAttribute('data-fullscreen', '');
      }

      // Invalidate map size after transition
      setTimeout(() => {
        if (window.routeMapInstance) {
          window.routeMapInstance.invalidateSize();
        }
      }, 100);
    });

    // Also support ESC key to exit fullscreen
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && mapPanel.hasAttribute('data-fullscreen')) {
        mapPanel.removeAttribute('data-fullscreen');
        setTimeout(() => {
          if (window.routeMapInstance) {
            window.routeMapInstance.invalidateSize();
          }
        }, 100);
      }
    });
  }
}

// Timeline View Handlers
function setupTimelineView() {
  // Expand/collapse trip groups
  document.addEventListener('click', (e) => {
    const tripHeader = e.target.closest('[data-timeline-trip-header]');
    if (tripHeader) {
      const tripItem = tripHeader.closest('[data-timeline-trip]');
      tripItem.classList.toggle('timeline-item--collapsed');
    }
  });

  // Aircraft photo lightbox
  document.addEventListener('click', (e) => {
    const thumb = e.target.closest('[data-timeline-aircraft-thumb]');
    if (thumb) {
      const fullSrc = thumb.dataset.fullSrc;
      const title = thumb.dataset.title;

      const modal = document.querySelector('[data-aircraft-modal]');
      if (modal) {
        const img = modal.querySelector('[data-aircraft-modal-image]');
        const titleEl = modal.querySelector('[data-aircraft-modal-title]');

        if (img) img.src = fullSrc;
        if (titleEl) titleEl.textContent = title;

        modal.hidden = false;
      }
    }
  });

  // Sort toggle
  const sortButtons = document.querySelectorAll('[data-timeline-sort]');
  sortButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const sortOrder = btn.dataset.timelineSort;
      const url = new URL(window.location.href);
      url.searchParams.set('sort', sortOrder);
      window.location.href = url.toString();
    });
  });

  // Group toggle
  const groupButtons = document.querySelectorAll('[data-timeline-group]');
  groupButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const groupMode = btn.dataset.timelineGroup;
      const url = new URL(window.location.href);
      url.searchParams.set('group', groupMode);
      window.location.href = url.toString();
    });
  });
}

// Achievement Detail Modal
function setupAchievementModal() {
  const modal = document.querySelector('[data-achievement-modal]');
  if (!modal) return;

  const closeButtons = modal.querySelectorAll('[data-achievement-close]');
  const badges = document.querySelectorAll('.achievement-badge');

  const closeModal = () => {
    modal.hidden = true;
  };

  closeButtons.forEach(btn => {
    btn.addEventListener('click', closeModal);
  });

  badges.forEach(badge => {
    badge.addEventListener('click', () => {
      const badgeId = badge.dataset.badgeId;
      const title = badge.querySelector('.achievement-badge__title').textContent;
      const description = badge.querySelector('.achievement-badge__description').textContent;
      const icon = badge.querySelector('.achievement-badge__icon').innerHTML;

      modal.querySelector('[data-achievement-modal-title]').textContent = title;
      modal.querySelector('[data-achievement-modal-description]').textContent = description;
      modal.querySelector('[data-achievement-modal-icon]').innerHTML = icon;

      modal.hidden = false;
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) {
      closeModal();
    }
  });
}

function setupGlobalSearch() {
  const searchInput = document.querySelector("[data-search-input]");
  const dropdown = document.querySelector("[data-search-dropdown]");
  const resultsContainer = document.querySelector("[data-search-results]");
  const loadingEl = document.querySelector("[data-search-loading]");
  const emptyEl = document.querySelector("[data-search-empty]");
  const kbdEl = document.querySelector("[data-search-kbd]");
  if (!searchInput || !dropdown || !resultsContainer) {
    return;
  }

  let debounceTimer = null;
  let activeIndex = -1;
  let currentResults = [];

  const detectPageType = () => {
    if (document.querySelector("[data-recent-flights]")) return "dashboard";
    if (document.querySelector("[data-flight-table]")) return "flights";
    if (document.querySelector("[data-aircraft-grid]")) return "aircraft";
    return null;
  };

  const pageType = detectPageType();

  const showDropdown = () => {
    dropdown.hidden = false;
  };
  const hideDropdown = () => {
    dropdown.hidden = true;
    activeIndex = -1;
  };

  const renderDropdownResults = (data) => {
    resultsContainer.innerHTML = "";
    currentResults = [];
    const flights = data.flights || [];
    const aircraft = data.aircraft || [];
    if (!flights.length && !aircraft.length) {
      emptyEl.hidden = false;
      loadingEl.hidden = true;
      return;
    }
    emptyEl.hidden = true;
    loadingEl.hidden = true;

    if (flights.length) {
      const heading = document.createElement("div");
      heading.className = "search-section__title";
      heading.textContent = `Flights (${flights.length})`;
      resultsContainer.appendChild(heading);

      flights.slice(0, 15).forEach((flight) => {
        const item = document.createElement("a");
        item.className = "search-result";
        item.href =
          (window.flightEditUrlBase || "").replace("/0/edit", `/${flight.id}/edit`);
        item.innerHTML = `
          <div class="search-result__main">
            <span class="search-result__highlight">
              ${escapeHtml(flight.origin_name || "-")} &rarr; ${escapeHtml(flight.destination_name || "-")}
              ${flight.flight_number ? `<span class="search-result__badge">${escapeHtml(flight.flight_number)}</span>` : ""}
            </span>
          </div>
          <div class="search-result__sub">
            ${escapeHtml(flight.start_date || "-")}
            ${flight.airline_code ? " · " + escapeHtml(flight.airline_code) : ""}
            ${flight.aircraft_registration ? " · " + escapeHtml(flight.aircraft_registration) : ""}
          </div>`;
        resultsContainer.appendChild(item);
        currentResults.push(item);
      });
    }

    if (aircraft.length) {
      const heading = document.createElement("div");
      heading.className = "search-section__title";
      heading.textContent = `Aircraft (${aircraft.length})`;
      resultsContainer.appendChild(heading);

      aircraft.slice(0, 10).forEach((ac) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "search-result";
        item.innerHTML = `
          <div class="search-result__main">
            <span class="search-result__highlight">
              ${escapeHtml(ac.registration)}
              ${ac.icao_type ? `<span class="search-result__badge">${escapeHtml(ac.icao_type)}</span>` : ""}
            </span>
          </div>
          <div class="search-result__sub">
            ${escapeHtml(ac.type || "-")}
            ${ac.manufacturer ? " · " + escapeHtml(ac.manufacturer) : ""}
            ${ac.owner ? " · " + escapeHtml(ac.owner) : ""}
          </div>`;
        item.addEventListener("click", () => {
          hideDropdown();
          openRegLookup(ac.registration);
        });
        resultsContainer.appendChild(item);
        currentResults.push(item);
      });
    }

    const hasActions = pageType || searchInput.value.trim().length >= 2;
    if (hasActions) {
      const divider = document.createElement("div");
      divider.className = "search-section__title";
      divider.textContent = "Actions";
      resultsContainer.appendChild(divider);

      if (pageType && (flights.length || aircraft.length)) {
        const filterBtn = document.createElement("button");
        filterBtn.type = "button";
        filterBtn.className = "search-result";
        const countLabel =
          flights.length + aircraft.length === 1
            ? "1 result"
            : `${flights.length + aircraft.length} results`;
        filterBtn.innerHTML = `
          <div class="search-result__main">
            <i class="fa-solid fa-filter" aria-hidden="true"></i>
            Filter this page to ${countLabel}
          </div>`;
        filterBtn.addEventListener("click", () => {
          applyPageFilter(searchInput.value.trim(), data);
          hideDropdown();
        });
        resultsContainer.appendChild(filterBtn);
        currentResults.push(filterBtn);
      }

      const regBtn = document.createElement("button");
      regBtn.type = "button";
      regBtn.className = "search-result";
      const regQuery = searchInput.value.trim().toUpperCase();
      regBtn.innerHTML = `
        <div class="search-result__main">
          <i class="fa-solid fa-plane" aria-hidden="true"></i>
          Look up registration <strong>${escapeHtml(regQuery)}</strong>
        </div>
        <div class="search-result__sub">View aircraft details, flight history &amp; photos</div>`;
      regBtn.addEventListener("click", () => {
        hideDropdown();
        openRegLookup(regQuery);
      });
      resultsContainer.appendChild(regBtn);
      currentResults.push(regBtn);
    }
  };

  const doSearch = (query) => {
    if (!query || query.length < 2) {
      hideDropdown();
      return;
    }
    showDropdown();
    loadingEl.hidden = false;
    emptyEl.hidden = true;
    resultsContainer.innerHTML = "";

    const url = `${window.searchApiUrl}?q=${encodeURIComponent(query)}`;
    fetch(url, { headers: { "X-Requested-With": "fetch" } })
      .then((res) => res.json())
      .then((data) => {
        renderDropdownResults(data);
      })
      .catch(() => {
        loadingEl.hidden = true;
        emptyEl.hidden = false;
        emptyEl.textContent = "Search failed.";
      });
  };

  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    activeIndex = -1;
    const q = searchInput.value.trim();
    if (!q || q.length < 2) {
      hideDropdown();
      return;
    }
    debounceTimer = setTimeout(() => doSearch(q), 250);
  });

  searchInput.addEventListener("keydown", (e) => {
    if (!dropdown.hidden && currentResults.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, currentResults.length - 1);
        updateActiveResult();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        updateActiveResult();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (activeIndex >= 0 && currentResults[activeIndex]) {
          currentResults[activeIndex].click();
        } else if (searchInput.value.trim().length >= 2) {
          doSearch(searchInput.value.trim());
        }
      }
    }
    if (e.key === "Escape") {
      hideDropdown();
      searchInput.blur();
    }
  });

  const updateActiveResult = () => {
    currentResults.forEach((el, i) => {
      el.classList.toggle("is-active", i === activeIndex);
    });
    if (activeIndex >= 0 && currentResults[activeIndex]) {
      currentResults[activeIndex].scrollIntoView({ block: "nearest" });
    }
  };

  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-nav-search]")) {
      hideDropdown();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (
      e.key === "/" &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.altKey &&
      document.activeElement?.tagName !== "INPUT" &&
      document.activeElement?.tagName !== "TEXTAREA" &&
      !document.activeElement?.isContentEditable
    ) {
      e.preventDefault();
      searchInput.focus();
    }
  });

  // ── In-page filtering logic ──

  const banner = document.querySelector("[data-page-search-banner]");
  const bannerText = document.querySelector("[data-page-search-text]");
  const bannerClear = document.querySelector("[data-page-search-clear]");

  const showBanner = (text) => {
    if (banner && bannerText) {
      bannerText.textContent = text;
      banner.classList.add("is-visible");
    }
  };
  const hideBanner = () => {
    if (banner) {
      banner.classList.remove("is-visible");
    }
  };

  const applyPageFilter = (query, data) => {
    if (!pageType) return;
    const matchedFlightIds = new Set((data.flights || []).map((f) => String(f.id)));
    const matchedRegistrations = new Set(
      (data.aircraft || []).map((a) => (a.registration || "").toLowerCase())
    );
    const total = matchedFlightIds.size + matchedRegistrations.size;
    showBanner(
      `Showing ${total} result${total === 1 ? "" : "s"} for "${query}"`
    );

    if (pageType === "dashboard") {
      applyDashboardSearchFilter(matchedFlightIds, query);
    } else if (pageType === "flights") {
      applyFlightsSearchFilter(matchedFlightIds, query);
    } else if (pageType === "aircraft") {
      applyAircraftSearchFilter(matchedRegistrations, query);
    }
  };

  if (bannerClear) {
    bannerClear.addEventListener("click", () => {
      hideBanner();
      searchInput.value = "";
      if (pageType === "dashboard") {
        clearDashboardSearchFilter();
      } else if (pageType === "flights") {
        clearFlightsSearchFilter();
      } else if (pageType === "aircraft") {
        clearAircraftSearchFilter();
      }
    });
  }
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ── Dashboard search filter ──

let dashboardSearchIds = null;

function applyDashboardSearchFilter(flightIds, query) {
  dashboardSearchIds = flightIds;
  applyDashboardFilters();
}

function clearDashboardSearchFilter() {
  dashboardSearchIds = null;
  applyDashboardFilters();
}

// ── Flights search filter ──

let flightsSearchIds = null;

function applyFlightsSearchFilter(flightIds, query) {
  flightsSearchIds = flightIds;
  if (typeof window.applyFlightsFilters === "function") {
    window.applyFlightsFilters();
  }
}

function clearFlightsSearchFilter() {
  flightsSearchIds = null;
  if (typeof window.applyFlightsFilters === "function") {
    window.applyFlightsFilters();
  }
}

// ── Aircraft search filter ──

function applyAircraftSearchFilter(registrations, query) {
  const cards = document.querySelectorAll("[data-aircraft-search]");
  let visible = 0;
  cards.forEach((card) => {
    const searchText = card.dataset.aircraftSearch || "";
    const matchesTerm = searchText.includes(query.toLowerCase());
    const matchesReg = registrations.size === 0 || Array.from(registrations).some(
      (reg) => searchText.includes(reg)
    );
    const show = matchesTerm || matchesReg;
    card.style.display = show ? "" : "none";
    if (show) visible++;
  });
}

function clearAircraftSearchFilter() {
  const cards = document.querySelectorAll("[data-aircraft-search]");
  cards.forEach((card) => {
    card.style.display = "";
  });
}

// ── Registration lookup ──

function openRegLookup(registration) {
  const modal = document.querySelector("[data-reg-lookup-modal]");
  if (!modal) return;
  const input = modal.querySelector("[data-reg-lookup-input]");
  if (input) input.value = registration || "";
  modal.hidden = false;
  if (registration) {
    performRegLookup(registration);
  } else if (input) {
    input.focus();
  }
}

function performRegLookup(registration) {
  const modal = document.querySelector("[data-reg-lookup-modal]");
  if (!modal) return;

  const reg = (registration || "").trim().toUpperCase();
  if (!reg) return;

  const loading = modal.querySelector("[data-reg-lookup-loading]");
  const error = modal.querySelector("[data-reg-lookup-error]");
  const content = modal.querySelector("[data-reg-lookup-content]");
  const title = modal.querySelector("[data-reg-lookup-title]");

  loading.hidden = false;
  error.hidden = true;
  content.hidden = true;
  if (title) title.textContent = reg;

  const url = (window.aircraftLookupUrlBase || "").replace("__REG__", encodeURIComponent(reg));
  fetch(url, { headers: { "X-Requested-With": "fetch" } })
    .then((res) => {
      if (!res.ok) throw new Error("Lookup failed");
      return res.json();
    })
    .then((data) => {
      loading.hidden = true;
      renderRegLookup(modal, data);
    })
    .catch((err) => {
      loading.hidden = true;
      error.hidden = false;
      error.textContent = `Could not look up ${reg}. ${err.message || ""}`;
    });
}

function renderRegLookup(modal, data) {
  const content = modal.querySelector("[data-reg-lookup-content]");
  const photoCol = modal.querySelector("[data-reg-lookup-photo-col]");
  const photoEl = modal.querySelector("[data-reg-lookup-photo]");
  const detailsDl = modal.querySelector("[data-reg-lookup-details]");
  const flightsBody = modal.querySelector("[data-reg-lookup-flights-body]");
  const flightsSection = modal.querySelector("[data-reg-lookup-flights-section]");
  const flightsTitle = modal.querySelector("[data-reg-lookup-flights-title]");
  const airnavBody = modal.querySelector("[data-reg-lookup-history-body]");
  const airnavSection = modal.querySelector("[data-reg-lookup-history-section]");
  const airnavTitle = modal.querySelector("[data-reg-lookup-history-title]");
  const editBase = window.flightEditUrlBase || "";

  content.hidden = false;

  const d = data.details || {};
  if (d.url_photo) {
    photoCol.hidden = false;
    photoEl.src = d.url_photo_thumbnail || d.url_photo;
    photoEl.alt = `${data.registration} aircraft photo`;
    photoEl.onclick = () => {
      const lb = document.querySelector("[data-aircraft-modal]");
      if (lb) {
        lb.querySelector("[data-aircraft-modal-image]").src = d.url_photo;
        lb.querySelector("[data-aircraft-modal-title]").textContent = data.registration;
        lb.hidden = false;
      }
    };
  } else {
    photoCol.hidden = true;
  }

  const fields = [
    ["Registration", data.registration],
    ["Type", d.type],
    ["ICAO Type", d.icao_type],
    ["Manufacturer", d.manufacturer],
    ["Mode S", d.mode_s],
    ["Owner", d.registered_owner],
    ["Operator", d.registered_owner_operator_flag_code],
    ["Owner Country", d.registered_owner_country_name],
  ];
  detailsDl.innerHTML = "";
  fields.forEach(([label, value]) => {
    const div = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value || "-";
    div.append(dt, dd);
    detailsDl.appendChild(div);
  });

  const flights = data.flights || [];
  if (flightsTitle) {
    flightsTitle.textContent = `Your Flights (${flights.length})`;
  }
  flightsBody.innerHTML = "";
  if (!flights.length) {
    const row = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "reg-lookup__no-data";
    td.textContent = "No flights recorded on this aircraft.";
    row.appendChild(td);
    flightsBody.appendChild(row);
  } else {
    flights.forEach((f) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${escapeHtml(f.start_date || "-")}</td>
        <td>${escapeHtml(f.origin_name || "-")}</td>
        <td>${escapeHtml(f.destination_name || "-")}</td>
        <td>${escapeHtml(f.flight_number || "-")}</td>
        <td>${f.distance != null ? Number(f.distance).toLocaleString(undefined, { maximumFractionDigits: 0 }) : "-"}</td>
        <td><a class="button ghost" href="${editBase.replace("/0/edit", `/${f.id}/edit`)}" title="Edit"><i class="fa-solid fa-pen-to-square" aria-hidden="true"></i></a></td>`;
      flightsBody.appendChild(row);
    });
  }

  const airnav = data.airnav_history || [];
  if (airnavTitle) {
    airnavTitle.textContent = `Flight History (${airnav.length})`;
  }
  airnavBody.innerHTML = "";
  if (!airnav.length) {
    airnavSection.hidden = true;
  } else {
    airnavSection.hidden = false;
    airnav.forEach((h) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${escapeHtml(h.dep_date || "-")}</td>
        <td>${escapeHtml(h.flight_number || "-")}</td>
        <td>${escapeHtml(h.dep_airport || "-")}${h.dep_city ? " " + escapeHtml(h.dep_city) : ""}</td>
        <td>${escapeHtml(h.arr_airport || "-")}${h.arr_city ? " " + escapeHtml(h.arr_city) : ""}</td>
        <td>${escapeHtml(h.airline_name || "-")}</td>
        <td>${escapeHtml(h.status || "-")}</td>`;
      airnavBody.appendChild(row);
    });
  }
}

function setupRegistrationScanner() {
  const modal = document.querySelector("[data-scan-modal]");
  const trigger = document.querySelector("[data-scan-trigger]");
  if (!modal || !trigger) return;

  const closeButtons = modal.querySelectorAll("[data-scan-close]");
  const cameraBtn = modal.querySelector("[data-scan-camera]");
  const galleryBtn = modal.querySelector("[data-scan-gallery]");
  const cameraInput = modal.querySelector("[data-scan-camera-input]");
  const galleryInput = modal.querySelector("[data-scan-gallery-input]");
  const preview = modal.querySelector("[data-scan-preview]");
  const previewImg = modal.querySelector("[data-scan-preview-img]");
  const actions = modal.querySelector("[data-scan-actions]");
  const submitBtn = modal.querySelector("[data-scan-submit]");
  const retakeBtn = modal.querySelector("[data-scan-retake]");
  const loading = modal.querySelector("[data-scan-loading]");
  const result = modal.querySelector("[data-scan-result]");
  const resultReg = modal.querySelector("[data-scan-result-reg]");
  const resultMeta = modal.querySelector("[data-scan-result-meta]");
  const lookupBtn = modal.querySelector("[data-scan-lookup]");
  const anotherBtn = modal.querySelector("[data-scan-another]");
  const errorEl = modal.querySelector("[data-scan-error]");
  const captureButtons = modal.querySelector("[data-scan-buttons]");

  let currentFile = null;
  let lastRegistration = null;

  function openScanner() {
    modal.hidden = false;
    resetScanner();
  }

  function closeScanner() {
    modal.hidden = true;
    resetScanner();
  }

  function resetScanner() {
    currentFile = null;
    lastRegistration = null;
    preview.hidden = true;
    actions.hidden = true;
    loading.hidden = true;
    result.hidden = true;
    errorEl.hidden = true;
    captureButtons.hidden = false;
    previewImg.src = "";
    if (cameraInput) cameraInput.value = "";
    if (galleryInput) galleryInput.value = "";
  }

  function handleImageSelect(file) {
    if (!file) return;
    currentFile = file;
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImg.src = e.target.result;
      preview.hidden = false;
      actions.hidden = false;
      captureButtons.hidden = true;
    };
    reader.readAsDataURL(file);
  }

  function resizeImage(file) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const MAX_DIM = 1920;
        let w = img.width;
        let h = img.height;
        if (w > MAX_DIM || h > MAX_DIM) {
          if (w > h) {
            h = Math.round(h * (MAX_DIM / w));
            w = MAX_DIM;
          } else {
            w = Math.round(w * (MAX_DIM / h));
            h = MAX_DIM;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        canvas.toBlob(
          (blob) => resolve(blob),
          "image/jpeg",
          0.85
        );
      };
      img.src = URL.createObjectURL(file);
    });
  }

  async function submitScan() {
    if (!currentFile) return;
    loading.hidden = false;
    actions.hidden = true;
    errorEl.hidden = true;
    result.hidden = true;

    try {
      const resized = await resizeImage(currentFile);
      const formData = new FormData();
      formData.append("image", resized, "scan.jpg");

      const resp = await fetch(window.scanRegistrationUrl, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: formData,
      });
      const data = await resp.json();
      loading.hidden = true;

      if (data.error) {
        errorEl.textContent = data.error;
        errorEl.hidden = false;
        actions.hidden = false;
        return;
      }

      if (!data.registration) {
        errorEl.textContent = "No registration found in image. Try a clearer photo.";
        errorEl.hidden = false;
        actions.hidden = false;
        return;
      }

      lastRegistration = data.registration;
      resultReg.textContent = data.registration;

      const metaParts = [];
      if (data.confidence != null) {
        const pct = Math.round(data.confidence * 100);
        metaParts.push("Confidence: " + pct + "%");
      }
      if (data.location_on_aircraft) {
        metaParts.push("Location: " + data.location_on_aircraft);
      }
      if (data.aircraft_type_guess) {
        metaParts.push("Type: " + data.aircraft_type_guess);
      }
      resultMeta.textContent = metaParts.join(" \u00b7 ");

      if (data.low_confidence) {
        resultReg.classList.add("scan-result__reg--low");
      } else {
        resultReg.classList.remove("scan-result__reg--low");
      }

      result.hidden = false;

      if (data.confidence >= 0.5) {
        // Auto-open lookup after a brief pause
        setTimeout(() => {
          closeScanner();
          openRegLookup(data.registration);
        }, 1200);
      }
    } catch (err) {
      loading.hidden = true;
      errorEl.textContent = "Scan failed: " + err.message;
      errorEl.hidden = false;
      actions.hidden = false;
    }
  }

  trigger.addEventListener("click", openScanner);
  closeButtons.forEach((btn) => btn.addEventListener("click", closeScanner));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeScanner();
  });

  if (cameraBtn && cameraInput) {
    cameraBtn.addEventListener("click", () => cameraInput.click());
    cameraInput.addEventListener("change", (e) => {
      if (e.target.files[0]) handleImageSelect(e.target.files[0]);
    });
  }
  if (galleryBtn && galleryInput) {
    galleryBtn.addEventListener("click", () => galleryInput.click());
    galleryInput.addEventListener("change", (e) => {
      if (e.target.files[0]) handleImageSelect(e.target.files[0]);
    });
  }

  if (submitBtn) submitBtn.addEventListener("click", submitScan);
  if (retakeBtn) retakeBtn.addEventListener("click", resetScanner);
  if (lookupBtn) {
    lookupBtn.addEventListener("click", () => {
      if (lastRegistration) {
        closeScanner();
        openRegLookup(lastRegistration);
      }
    });
  }
  if (anotherBtn) anotherBtn.addEventListener("click", resetScanner);
}

function setupRegLookup() {
  const modal = document.querySelector("[data-reg-lookup-modal]");
  if (!modal) return;

  const closeButtons = modal.querySelectorAll("[data-reg-lookup-close]");
  const input = modal.querySelector("[data-reg-lookup-input]");
  const goButton = modal.querySelector("[data-reg-lookup-go]");

  const closeModal = () => {
    modal.hidden = true;
  };

  closeButtons.forEach((btn) => btn.addEventListener("click", closeModal));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) {
      closeModal();
    }
  });

  if (goButton && input) {
    goButton.addEventListener("click", () => {
      const reg = input.value.trim().toUpperCase();
      if (reg) performRegLookup(reg);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const reg = input.value.trim().toUpperCase();
        if (reg) performRegLookup(reg);
      }
    });
  }
}

/* ── AI Insights ─────────────────────────────────────────── */

function renderInsightCards(container, highlights) {
  if (!container || !Array.isArray(highlights)) return;
  container.innerHTML = "";
  highlights.forEach((h) => {
    const card = document.createElement("div");
    card.className = "insight-card";
    card.innerHTML =
      '<div class="insight-card__icon">' + (h.icon || "") + "</div>" +
      '<div class="insight-card__body">' +
        '<div class="insight-card__title">' + escapeHtml(h.title || "") + "</div>" +
        '<div class="insight-card__value">' + escapeHtml(h.value || "") + "</div>" +
        '<div class="insight-card__detail">' + escapeHtml(h.detail || "") + "</div>" +
      "</div>";
    container.appendChild(card);
  });
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function renderInsights(data) {
  if (!data) return;

  const content = document.querySelector("[data-insights-content]");
  const empty = document.querySelector("[data-insights-empty]");
  const loading = document.querySelector("[data-insights-loading]");
  const error = document.querySelector("[data-insights-error]");
  if (loading) loading.hidden = true;
  if (error) error.hidden = true;
  if (empty) empty.hidden = true;
  if (content) content.hidden = false;

  // Update generate button label
  document.querySelectorAll("[data-insights-generate-label]").forEach((el) => {
    el.textContent = "Regenerate";
  });

  // --- Personality hero ---
  const p = data.travel_personality;
  if (p) {
    const title = document.querySelector("[data-insights-personality-title]");
    const subtitle = document.querySelector("[data-insights-personality-subtitle]");
    const desc = document.querySelector("[data-insights-personality-description]");
    const traits = document.querySelector("[data-insights-personality-traits]");
    if (title) title.textContent = p.title || "";
    if (subtitle) subtitle.textContent = p.subtitle || "";
    if (desc) desc.textContent = p.description || "";
    if (traits) {
      traits.innerHTML = "";
      (p.traits || []).forEach((t) => {
        const pill = document.createElement("span");
        pill.className = "insights-trait";
        pill.innerHTML = "<strong>" + escapeHtml(t.name || "") + "</strong> " + escapeHtml(t.description || "");
        traits.appendChild(pill);
      });
    }
  }

  // --- Quick stats ---
  const quickStats = document.querySelector("[data-insights-quick-stats]");
  if (quickStats) {
    quickStats.innerHTML = "";
    const items = [];
    if (data.geographic && data.geographic.map_completion) {
      items.push({ icon: "🌍", label: "Countries", value: data.geographic.map_completion.visited_countries || "—" });
      items.push({ icon: "📊", label: "Global Coverage", value: (data.geographic.map_completion.percentage || 0) + "%" });
    }
    if (data.aircraft_aviation) {
      items.push({ icon: "✈️", label: "Aircraft Diversity", value: (data.aircraft_aviation.diversity_score || 0) + "/100" });
      items.push({ icon: "📸", label: "Spotter Score", value: (data.aircraft_aviation.plane_spotter_score || 0) + "/100" });
    }
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "summary-card";
      card.innerHTML =
        '<div class="summary-card__icon">' + item.icon + "</div>" +
        '<div class="summary-card__value">' + escapeHtml(String(item.value)) + "</div>" +
        '<div class="summary-card__label">' + escapeHtml(item.label) + "</div>";
      quickStats.appendChild(card);
    });
  }

  // --- Category highlights ---
  renderInsightCards(document.querySelector('[data-insights-cards="geographic"]'), (data.geographic || {}).highlights);
  renderInsightCards(document.querySelector('[data-insights-cards="aircraft"]'), (data.aircraft_aviation || {}).highlights);
  renderInsightCards(document.querySelector('[data-insights-cards="airline"]'), (data.airline || {}).highlights);
  renderInsightCards(document.querySelector('[data-insights-cards="temporal"]'), (data.temporal || {}).highlights);

  // --- Geographic sub-sections ---
  const mapComp = document.querySelector("[data-insights-map-completion]");
  if (mapComp && data.geographic) {
    const mc = data.geographic.map_completion;
    const hb = data.geographic.hemisphere_balance;
    const md = data.geographic.missing_destinations;
    let html = "";
    if (mc) {
      html += '<div class="insights-stat-bar">' +
        '<div class="insights-stat-bar__label">Global Map Completion</div>' +
        '<div class="insights-stat-bar__track"><div class="insights-stat-bar__fill" style="width:' + Math.min(mc.percentage || 0, 100) + '%"></div></div>' +
        '<div class="insights-stat-bar__value">' + escapeHtml(String(mc.percentage || 0)) + '% (' + escapeHtml(String(mc.visited_countries || 0)) + ' countries)</div>' +
        '<div class="insights-stat-bar__detail">' + escapeHtml(mc.detail || "") + '</div>' +
      '</div>';
    }
    if (hb) {
      html += '<div class="insights-hemisphere">' +
        '<div><strong>N/S Balance:</strong> ' + escapeHtml(hb.north_south || "") + '</div>' +
        '<div><strong>E/W Balance:</strong> ' + escapeHtml(hb.east_west || "") + '</div>' +
      '</div>';
    }
    mapComp.innerHTML = html;
  }

  const missingDest = document.querySelector("[data-insights-missing-destinations]");
  if (missingDest && data.geographic && Array.isArray(data.geographic.missing_destinations) && data.geographic.missing_destinations.length) {
    missingDest.innerHTML =
      '<h4 class="insights-sub-title">Destinations You Might Like</h4>' +
      '<div class="insights-pills">' +
      data.geographic.missing_destinations.map((d) => '<span class="insights-pill">🎯 ' + escapeHtml(d) + "</span>").join("") +
      "</div>";
  }

  // --- Aircraft scores ---
  const aircraftScores = document.querySelector("[data-insights-aircraft-scores]");
  if (aircraftScores && data.aircraft_aviation) {
    const aa = data.aircraft_aviation;
    aircraftScores.innerHTML =
      '<div class="insights-score-grid">' +
        renderScoreCard("Aircraft Diversity", aa.diversity_score, aa.diversity_detail, "✈️") +
        renderScoreCard("Plane Spotter", aa.plane_spotter_score, aa.spotter_detail, "📸") +
      '</div>' +
      '<div class="insights-detail-items">' +
        (aa.manufacturer_loyalty ? '<div class="insights-detail-item"><strong>Manufacturer Loyalty:</strong> ' + escapeHtml(aa.manufacturer_loyalty) + '</div>' : '') +
        (aa.widebody_ratio ? '<div class="insights-detail-item"><strong>Widebody Preference:</strong> ' + escapeHtml(aa.widebody_ratio) + '</div>' : '') +
      '</div>';
  }

  // --- Airline scores ---
  const airlineScores = document.querySelector("[data-insights-airline-scores]");
  if (airlineScores && data.airline) {
    const al = data.airline;
    airlineScores.innerHTML =
      '<div class="insights-score-grid">' +
        renderScoreCard("Airline Loyalty", al.loyalty_index, al.loyalty_detail, "💎") +
      '</div>' +
      '<div class="insights-detail-items">' +
        (al.alliance_analysis ? '<div class="insights-detail-item"><strong>Alliance:</strong> ' + escapeHtml(al.alliance_analysis) + '</div>' : '') +
        (al.fsc_lcc_ratio ? '<div class="insights-detail-item"><strong>Carrier Type:</strong> ' + escapeHtml(al.fsc_lcc_ratio) + '</div>' : '') +
      '</div>';
  }

  // --- Superlatives ---
  const superlatives = document.querySelector("[data-insights-superlatives]");
  if (superlatives && Array.isArray(data.superlatives)) {
    superlatives.innerHTML = "";
    data.superlatives.forEach((s) => {
      const card = document.createElement("div");
      card.className = "insight-card insight-card--superlative";
      card.innerHTML =
        '<div class="insight-card__icon">' + (s.icon || "🏆") + "</div>" +
        '<div class="insight-card__body">' +
          '<div class="insight-card__title">' + escapeHtml(s.title || "") + "</div>" +
          '<div class="insight-card__value">' + escapeHtml(s.value || "") + "</div>" +
          '<div class="insight-card__detail">' + escapeHtml(s.detail || "") + "</div>" +
        "</div>";
      superlatives.appendChild(card);
    });
  }

  // --- Fun comparisons ---
  const comparisons = document.querySelector("[data-insights-comparisons]");
  if (comparisons && Array.isArray(data.fun_comparisons)) {
    comparisons.innerHTML = "";
    data.fun_comparisons.forEach((c) => {
      const item = document.createElement("div");
      item.className = "insights-comparison";
      item.innerHTML =
        '<span class="insights-comparison__icon">' + (c.icon || "📏") + "</span>" +
        '<span class="insights-comparison__text">' + escapeHtml(c.comparison || "") + "</span>" +
        '<span class="insights-comparison__value">' + escapeHtml(c.value || "") + "</span>";
      comparisons.appendChild(item);
    });
  }

  // --- Predictions ---
  const predictions = document.querySelector("[data-insights-predictions]");
  if (predictions && data.predictions) {
    const pr = data.predictions;
    predictions.innerHTML = "";
    if (pr.next_destination) {
      const card = document.createElement("div");
      card.className = "insight-card";
      card.innerHTML =
        '<div class="insight-card__icon">🔮</div>' +
        '<div class="insight-card__body">' +
          '<div class="insight-card__title">Next Destination</div>' +
          '<div class="insight-card__value">' + escapeHtml(pr.next_destination.destination || "") + "</div>" +
          '<div class="insight-card__detail">' + escapeHtml(pr.next_destination.reasoning || "") + "</div>" +
        "</div>";
      predictions.appendChild(card);
    }
    if (pr.travel_twin) {
      const card = document.createElement("div");
      card.className = "insight-card";
      card.innerHTML =
        '<div class="insight-card__icon">👤</div>' +
        '<div class="insight-card__body">' +
          '<div class="insight-card__title">Travel Twin</div>' +
          '<div class="insight-card__value">' + escapeHtml(pr.travel_twin.archetype || "") + "</div>" +
          '<div class="insight-card__detail">' + escapeHtml(pr.travel_twin.reasoning || "") + "</div>" +
        "</div>";
      predictions.appendChild(card);
    }
    if (pr.growth_trend) {
      const card = document.createElement("div");
      card.className = "insight-card";
      card.innerHTML =
        '<div class="insight-card__icon">📈</div>' +
        '<div class="insight-card__body">' +
          '<div class="insight-card__title">Growth Trend</div>' +
          '<div class="insight-card__value">' + escapeHtml(pr.growth_trend || "") + "</div>" +
        "</div>";
      predictions.appendChild(card);
    }
  }

  // --- Timestamp ---
  const ts = document.querySelector("[data-insights-timestamp]");
  if (ts) ts.textContent = "Generated just now by AI — results may vary on regeneration";
}

function renderScoreCard(label, score, detail, icon) {
  const pct = Math.min(Math.max(score || 0, 0), 100);
  return (
    '<div class="insights-score-card">' +
      '<div class="insights-score-card__header">' +
        '<span>' + (icon || "") + " " + escapeHtml(label) + "</span>" +
        '<span class="insights-score-card__value">' + pct + "/100</span>" +
      "</div>" +
      '<div class="insights-stat-bar__track"><div class="insights-stat-bar__fill" style="width:' + pct + '%"></div></div>' +
      (detail ? '<div class="insights-score-card__detail">' + escapeHtml(detail) + "</div>" : "") +
    "</div>"
  );
}

function startInsightsProgress() {
  const steps = document.querySelectorAll("[data-insights-loading] [data-step]");
  const bar = document.querySelector("[data-insights-progress-bar]");
  const title = document.querySelector("[data-insights-loading-title]");
  const elapsed = document.querySelector("[data-insights-elapsed]");
  const titles = [
    "Preparing your flight data...",
    "Sending to AI for analysis...",
    "AI is analysing patterns and trends...",
    "Generating personalised insights...",
  ];
  let currentStep = 0;
  const startTime = Date.now();

  // Reset all steps
  steps.forEach((s, i) => {
    s.classList.toggle("is-active", i === 0);
    s.classList.remove("is-done");
  });
  if (bar) bar.style.width = "5%";

  const stepInterval = setInterval(() => {
    if (currentStep < steps.length - 1) {
      steps[currentStep].classList.remove("is-active");
      steps[currentStep].classList.add("is-done");
      currentStep++;
      steps[currentStep].classList.add("is-active");
      if (title) title.textContent = titles[currentStep] || titles[0];
      if (bar) bar.style.width = Math.min(15 + currentStep * 25, 90) + "%";
    }
  }, 3000);

  const timerInterval = setInterval(() => {
    const secs = Math.floor((Date.now() - startTime) / 1000);
    if (elapsed) elapsed.textContent = secs + "s elapsed";
  }, 1000);

  return {
    stop() {
      clearInterval(stepInterval);
      clearInterval(timerInterval);
      if (bar) bar.style.width = "100%";
      steps.forEach((s) => { s.classList.remove("is-active"); s.classList.add("is-done"); });
    },
  };
}

function setupInsights() {
  const page = document.querySelector("[data-insights-page]");
  if (!page) return;

  // Render cached data if available
  if (window.insightsData) {
    renderInsights(window.insightsData);
    // Show timestamp from cache
    const ts = document.querySelector("[data-insights-timestamp]");
    if (ts && window.insightsGeneratedAt) {
      const staleNote = window.insightsStale ? " (your data has changed since — regenerate for updated insights)" : "";
      ts.textContent = "Generated " + window.insightsGeneratedAt + staleNote;
    }
  }

  // Wire up all generate buttons
  let progress = null;
  page.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-insights-generate]");
    if (!btn) return;
    e.preventDefault();

    const loading = document.querySelector("[data-insights-loading]");
    const content = document.querySelector("[data-insights-content]");
    const empty = document.querySelector("[data-insights-empty]");
    const error = document.querySelector("[data-insights-error]");

    // Show loading
    if (loading) loading.hidden = false;
    if (content) content.hidden = true;
    if (empty) empty.hidden = true;
    if (error) error.hidden = true;

    // Start progress animation
    progress = startInsightsProgress();

    // Disable all generate buttons
    page.querySelectorAll("[data-insights-generate]").forEach((b) => {
      b.disabled = true;
    });

    fetch("/api/insights/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
    })
      .then((res) => res.json())
      .then((data) => {
        if (progress) progress.stop();
        if (data.ok && data.insights) {
          window.insightsData = data.insights;
          window.insightsStale = false;
          window.scrollTo({ top: 0 });
          renderInsights(data.insights);
        } else {
          if (loading) loading.hidden = true;
          if (error) error.hidden = false;
          const msg = document.querySelector("[data-insights-error-message]");
          if (msg) msg.textContent = data.error || "Failed to generate insights. Please try again.";
        }
      })
      .catch(() => {
        if (progress) progress.stop();
        if (loading) loading.hidden = true;
        if (error) error.hidden = false;
        const msg = document.querySelector("[data-insights-error-message]");
        if (msg) msg.textContent = "Network error. Please check your connection and try again.";
      })
      .finally(() => {
        page.querySelectorAll("[data-insights-generate]").forEach((b) => {
          b.disabled = false;
        });
      });
  });
}

function setupThemeToggle() {
  const btn = document.querySelector("[data-theme-toggle]");
  if (!btn) return;
  const icon = btn.querySelector("i");

  function updateIcon() {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    icon.className = isDark ? "fa-solid fa-sun" : "fa-solid fa-moon";
    btn.title = isDark ? "Switch to light mode" : "Switch to dark mode";
  }

  updateIcon();

  btn.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch (e) {
      /* storage unavailable */
    }
    updateIcon();
    rerenderForTheme();
  });
}

function rerenderForTheme() {
  if (window.flightCharts) {
    if (Array.isArray(window.dashboardFlights)) {
      applyDashboardFilters();
    } else {
      renderCharts();
    }
  }
  if (window.routeMapInstance && window.mapRoutes) {
    renderMap(window.mapRoutes, window.currentMapColorScheme || "default");
  }
}

function setupNextFlightCountdown() {
  const el = document.querySelector("[data-next-flight-countdown]");
  if (!el || !el.dataset.departure) return;
  const departure = new Date(`${el.dataset.departure}T00:00:00`);
  if (Number.isNaN(departure.getTime())) return;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((departure - today) / 86400000);
  let label;
  if (days <= 0) {
    label = "Today";
  } else if (days === 1) {
    label = "Tomorrow";
  } else if (days < 14) {
    label = `In ${days} days`;
  } else if (days < 60) {
    label = `In ${Math.round(days / 7)} weeks`;
  } else {
    label = `In ${Math.round(days / 30)} months`;
  }
  el.textContent = label;
}

function setupNextFlightModal() {
  const trigger = document.querySelector("[data-next-flight-trigger]");
  const modal = document.querySelector("[data-next-flight-modal]");
  if (!trigger || !modal) return;

  const closeButtons = modal.querySelectorAll("[data-next-flight-close]");
  const loadingEl = modal.querySelector("[data-nf-aircraft-loading]");
  const contentEl = modal.querySelector("[data-nf-aircraft-content]");
  const emptyEl = modal.querySelector("[data-nf-aircraft-empty]");
  const photoCol = modal.querySelector("[data-nf-photo-col]");
  const photoEl = modal.querySelector("[data-nf-photo]");
  const detailsDl = modal.querySelector("[data-nf-aircraft-details]");
  const registration = (trigger.dataset.aircraftRegistration || "").trim();
  let fetched = false;

  const closeModal = () => { modal.hidden = true; };

  closeButtons.forEach((btn) => btn.addEventListener("click", closeModal));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  const renderAircraftDetails = (data) => {
    const d = data.details || {};
    if (d.url_photo) {
      photoCol.hidden = false;
      photoEl.src = d.url_photo;
      photoEl.alt = `${data.registration} aircraft photo`;
      photoEl.onclick = () => {
        const lb = document.querySelector("[data-aircraft-modal]");
        if (lb) {
          lb.querySelector("[data-aircraft-modal-image]").src = d.url_photo;
          lb.querySelector("[data-aircraft-modal-title]").textContent = data.registration;
          lb.hidden = false;
        }
      };
    } else {
      photoCol.hidden = true;
    }

    const fields = [
      ["Registration", data.registration],
      ["Type", d.type],
      ["ICAO Type", d.icao_type],
      ["Manufacturer", d.manufacturer],
      ["Mode S", d.mode_s],
      ["Owner", d.registered_owner],
      ["Operator", d.registered_owner_operator_flag_code],
      ["Owner Country", d.registered_owner_country_name],
    ];
    detailsDl.innerHTML = "";
    fields.forEach(([label, value]) => {
      if (!value) return;
      const div = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      div.append(dt, dd);
      detailsDl.appendChild(div);
    });
    contentEl.hidden = false;
  };

  const fetchAircraftDetails = async () => {
    if (!registration || fetched) return;
    fetched = true;
    loadingEl.hidden = false;
    emptyEl.hidden = true;
    contentEl.hidden = true;

    try {
      const url = window.aircraftLookupUrlBase.replace("__REG__", encodeURIComponent(registration));
      const response = await fetch(url, {
        headers: { "X-Requested-With": "fetch" },
      });
      const data = await response.json();
      loadingEl.hidden = true;
      if (!data.details || (!data.details.type && !data.details.url_photo)) {
        emptyEl.hidden = false;
        return;
      }
      renderAircraftDetails(data);
    } catch (err) {
      loadingEl.hidden = true;
      emptyEl.hidden = false;
    }
  };

  trigger.addEventListener("click", () => {
    modal.hidden = false;
    if (registration) {
      fetchAircraftDetails();
    } else {
      emptyEl.hidden = false;
      loadingEl.hidden = true;
      contentEl.hidden = true;
    }
  });
}

function setupRefreshTodayHistory() {
  const btn = document.querySelector("[data-refresh-today-history]");
  if (!btn || !window.refreshTodayHistoryUrl) return;

  btn.addEventListener("click", async () => {
    if (btn.disabled) return;
    const icon = btn.querySelector("i");
    const origClass = icon.className;
    icon.className = "fa-solid fa-rotate fa-spin";
    btn.disabled = true;
    btn.title = "Refreshing history for today's flights...";

    try {
      const response = await fetch(window.refreshTodayHistoryUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "fetch",
        },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Refresh failed.");
      }
      const { total, saved } = payload;
      btn.title = `Done: ${saved} of ${total} flight(s) updated`;
      icon.className = "fa-solid fa-check";
      setTimeout(() => {
        icon.className = origClass;
        btn.title = "Refresh aircraft history for today's flights";
      }, 3000);
    } catch (err) {
      btn.title = err.message || "Refresh failed";
      icon.className = "fa-solid fa-xmark";
      setTimeout(() => {
        icon.className = origClass;
        btn.title = "Refresh aircraft history for today's flights";
      }, 3000);
    } finally {
      btn.disabled = false;
    }
  });
}

/* ── Flying planes background control ── */
function setupFlyingPlanes() {
  var container = document.querySelector("[data-flying-planes]");
  var countEl = document.querySelector("[data-plane-count]");
  var minusBtn = document.querySelector("[data-plane-minus]");
  var plusBtn = document.querySelector("[data-plane-plus]");
  if (!container) return;

  var MAX_PLANES = 30;
  var DEFAULT_COUNT = 5;

  var PRESETS = [
    { top: 12, size: 1.6, duration: 28, delay: 0,  reverse: false },
    { top: 35, size: 1.1, duration: 38, delay: 6,  reverse: false },
    { top: 58, size: 2.0, duration: 22, delay: 12, reverse: false },
    { top: 78, size: 0.9, duration: 45, delay: 3,  reverse: false },
    { top: 22, size: 1.3, duration: 34, delay: 18, reverse: true  },
  ];

  function seededRandom(index) {
    var x = Math.sin(index * 9301 + 49297) * 49297;
    return x - Math.floor(x);
  }

  function getPlaneConfig(index) {
    if (index < PRESETS.length) return PRESETS[index];
    var r1 = seededRandom(index);
    var r2 = seededRandom(index + 100);
    var r3 = seededRandom(index + 200);
    var r4 = seededRandom(index + 300);
    var r5 = seededRandom(index + 400);
    return {
      top: 5 + r1 * 85,
      size: 0.8 + r2 * 1.4,
      duration: 18 + r3 * 35,
      delay: r4 * 20,
      reverse: r5 > 0.75,
    };
  }

  function renderPlanes(count) {
    container.innerHTML = "";
    for (var i = 0; i < count; i++) {
      var cfg = getPlaneConfig(i);
      var div = document.createElement("div");
      div.className = "flying-plane" + (cfg.reverse ? " flying-plane--reverse" : "");
      div.style.top = cfg.top + "%";
      div.style.fontSize = cfg.size + "rem";
      var anim = cfg.reverse ? "flyAcrossReverse" : "flyAcross";
      div.style.animation = anim + " " + cfg.duration + "s linear " + cfg.delay + "s infinite";
      div.innerHTML = '<i class="fa-solid fa-plane"></i>';
      container.appendChild(div);
    }
  }

  var saved = localStorage.getItem("flyingPlaneCount");
  var count = saved !== null ? Math.max(0, Math.min(MAX_PLANES, parseInt(saved, 10) || 0)) : DEFAULT_COUNT;

  function update(newCount) {
    count = Math.max(0, Math.min(MAX_PLANES, newCount));
    localStorage.setItem("flyingPlaneCount", count);
    if (countEl) countEl.textContent = count;
    renderPlanes(count);
  }

  if (minusBtn) {
    minusBtn.addEventListener("click", function () { update(count - 1); });
  }
  if (plusBtn) {
    plusBtn.addEventListener("click", function () { update(count + 1); });
  }

  update(count);
}

function quickAddSerializeForm(form) {
  const data = {};
  Array.from(form.elements).forEach((el) => {
    if (!el.name) return;
    if (el.type === "submit" || el.type === "button" || el.type === "reset") return;
    data[el.name] = el.value;
  });
  return data;
}

function setupQuickAddForm() {
  const form = document.querySelector("[data-quick-add-form]");
  if (!form) return;

  const errorEl = form.querySelector("[data-quick-error]");
  const resolvedEl = form.querySelector("[data-quick-resolved]");
  const submitBtn = form.querySelector("[data-quick-submit]");

  const showError = (message) => {
    if (!errorEl) return;
    if (!message) {
      errorEl.hidden = true;
      errorEl.textContent = "";
      return;
    }
    errorEl.hidden = false;
    errorEl.textContent = message;
  };

  const updateResolved = () => {
    if (!resolvedEl) return;
    const fromCity = form.querySelector('[name="start_city_name"]').value;
    const fromCountry = form.querySelector('[name="start_country"]').value;
    const toCity = form.querySelector('[name="end_city_name"]').value;
    const toCountry = form.querySelector('[name="end_country"]').value;
    if (fromCity || toCity) {
      resolvedEl.hidden = false;
      const fromText = [fromCity, fromCountry].filter(Boolean).join(", ") || "?";
      const toText = [toCity, toCountry].filter(Boolean).join(", ") || "?";
      resolvedEl.textContent = `${fromText} → ${toText}`;
    } else {
      resolvedEl.hidden = true;
    }
  };

  form.addEventListener("airport:resolved", updateResolved);
  updateResolved();

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    showError("");
    const payload = quickAddSerializeForm(form);
    if (!payload.start_airport || !payload.end_airport) {
      showError("Please choose both airports.");
      return;
    }
    if (!payload.start_date) {
      showError("Departure date is required.");
      return;
    }
    if (submitBtn) submitBtn.disabled = true;
    fetch("/flights/quick-add", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
      },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          throw new Error(data.error || "Could not save flight.");
        }
        window.location.reload();
      })
      .catch((err) => {
        showError(err.message || "Could not save flight.");
      })
      .finally(() => {
        if (submitBtn) submitBtn.disabled = false;
      });
  });

  form.addEventListener("reset", () => {
    showError("");
    setTimeout(() => {
      const today = new Date().toISOString().slice(0, 10);
      const startInput = form.querySelector("[data-quick-start-date]");
      const endInput = form.querySelector("[data-quick-end-date]");
      if (startInput) startInput.value = today;
      if (endInput) endInput.value = today;
      updateResolved();
    }, 0);
  });
}

function setupQuickEditModal() {
  const modal = document.querySelector("[data-quick-edit-modal]");
  const form = document.querySelector("[data-quick-edit-form]");
  if (!modal || !form) return;

  const subtitle = modal.querySelector("[data-quick-edit-subtitle]");
  const errorEl = modal.querySelector("[data-quick-edit-error]");
  const resolvedEl = modal.querySelector("[data-quick-edit-resolved]");
  const fullLink = modal.querySelector("[data-quick-edit-full]");
  const idField = form.querySelector("[data-quick-edit-id]");
  const editUrlTemplate = window.flightEditUrlTemplate;

  const showError = (message) => {
    if (!errorEl) return;
    if (!message) {
      errorEl.hidden = true;
      errorEl.textContent = "";
    } else {
      errorEl.hidden = false;
      errorEl.textContent = message;
    }
  };

  const updateResolved = () => {
    if (!resolvedEl) return;
    const fromCity = form.querySelector('[name="start_city_name"]').value;
    const fromCountry = form.querySelector('[name="start_country"]').value;
    const toCity = form.querySelector('[name="end_city_name"]').value;
    const toCountry = form.querySelector('[name="end_country"]').value;
    if (fromCity || toCity) {
      resolvedEl.hidden = false;
      const fromText = [fromCity, fromCountry].filter(Boolean).join(", ") || "?";
      const toText = [toCity, toCountry].filter(Boolean).join(", ") || "?";
      resolvedEl.textContent = `${fromText} → ${toText}`;
    } else {
      resolvedEl.hidden = true;
    }
  };

  form.addEventListener("airport:resolved", updateResolved);

  const closeModal = () => {
    modal.hidden = true;
    showError("");
  };

  modal.querySelectorAll("[data-quick-edit-close]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      closeModal();
    }
  });

  const populate = (flight) => {
    idField.value = flight.id || "";
    form.querySelector('[name="aircraft_registration"]').value =
      flight.aircraft_registration || "";
    const aircraftField = form.querySelector('[name="aircraft"]');
    if (aircraftField) aircraftField.value = flight.aircraft || "";
    const airlineField = form.querySelector('[name="airline_code"]');
    if (airlineField) airlineField.value = flight.airline_code || "";
    const flightNumberField = form.querySelector('[name="flight_number"]');
    if (flightNumberField) flightNumberField.value = flight.flight_number || "";
    form.querySelector('[name="start_airport"]').value =
      flight.start_airport || "";
    form.querySelector('[name="start_city_name"]').value =
      flight.start_city_name || "";
    form.querySelector('[name="start_country"]').value =
      flight.start_country || "";
    form.querySelector('[name="end_airport"]').value =
      flight.end_airport || "";
    form.querySelector('[name="end_city_name"]').value =
      flight.end_city_name || "";
    form.querySelector('[name="end_country"]').value =
      flight.end_country || "";
    form.querySelector('[name="start_date"]').value = flight.start_date || "";
    form.querySelector('[name="end_date"]').value = flight.end_date || "";

    if (subtitle) {
      const fnum = [flight.airline_code, flight.flight_number]
        .filter(Boolean)
        .join("");
      const tag = fnum ? ` · ${fnum}` : "";
      subtitle.textContent = `Flight #${flight.id}${tag}`;
    }
    if (fullLink && typeof editUrlTemplate === "string") {
      fullLink.href = editUrlTemplate.replace("/0/edit", `/${flight.id}/edit`);
    }
    updateResolved();
  };

  const openModalFor = (flightId) => {
    showError("");
    populate({ id: flightId });
    modal.hidden = false;
    fetch(`/flights/${flightId}/quick-edit`, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" },
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "Could not load flight.");
        populate(data.flight);
      })
      .catch((err) => showError(err.message || "Could not load flight."));
  };

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-quick-edit-open]");
    if (!trigger) return;
    event.preventDefault();
    const flightId = trigger.getAttribute("data-quick-edit-open");
    if (flightId) openModalFor(flightId);
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    showError("");
    const flightId = idField.value;
    if (!flightId) {
      showError("Missing flight id.");
      return;
    }
    const payload = quickAddSerializeForm(form);
    if (!payload.start_airport || !payload.end_airport) {
      showError("Please choose both airports.");
      return;
    }
    if (!payload.start_date) {
      showError("Departure date is required.");
      return;
    }
    fetch(`/flights/${flightId}/quick-edit`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
      },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok || !data.ok) {
          throw new Error(data.error || "Could not save flight.");
        }
        window.location.reload();
      })
      .catch((err) => showError(err.message || "Could not save flight."));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupFlyingPlanes();
  setupThemeToggle();
  setupNextFlightCountdown();
  setupDashboardDistanceToggle();
  setupMapControls();
  setupTimelineView();
  if (Array.isArray(window.dashboardFlights)) {
    applyDashboardFilters();
  } else {
    renderCharts();
    renderMap();
    renderStatsTables();
  }
  setupFlightsAdvancedFilters();
  setupFlightsFilters();
  setupFlightsDelete();
  setupHistoryDelete();
  setupFlightFollowUp();
  setupFlightExclude();
  setupFlightRegistrationClear();
  setupFlightGeminiAircraftOverwrite();
  setupFlightAircraftApply();
  setupGeminiHistoryDelete();
  setupTravellerChipInput();
  setupBookingSiteChipInput();
  setupDashboardTableFilters();
  setupFlightMerge();
  setupGeminiCodeshareLookup();
  setupFlightHistoryRefresh();
  setupAuditMerge();
  setupAuditGrouping();
  setupAuditGroupedToggle();
  setupAuditMissingGroupedToggle();
  setupAuditMissingLegsToggle();
  setupAuditSuggestedToggle();
  setupAircraftLightbox();
  setupNextFlightModal();
  setupAchievementModal();
  setupTripLegEditor();
  setupAirportLookup();
  setupMobileNav();
  setupScriptRunner();
  setupGlobalSearch();
  setupRegLookup();
  setupRegistrationScanner();
  setupRefreshTodayHistory();
  setupInsights();
  setupQuickAddForm();
  setupQuickEditModal();
});
