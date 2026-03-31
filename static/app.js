let map;
let markers = [];
let userMarker;
let hasFlightaware = false;
const DETAILS_CACHE_TTL = 7200000; // 2 hours in ms

function getCachedDetails(callsign) {
  try {
    const raw = localStorage.getItem("fa_" + callsign);
    if (!raw) return null;
    const entry = JSON.parse(raw);
    if (Date.now() - entry.timestamp > DETAILS_CACHE_TTL) {
      localStorage.removeItem("fa_" + callsign);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

function setCachedDetails(callsign, data) {
  try {
    localStorage.setItem(
      "fa_" + callsign,
      JSON.stringify({ data, timestamp: Date.now() })
    );
  } catch {
    // localStorage full or unavailable — ignore
  }
}

function escapeHtml(str) {
  if (!str) return str;
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

const PLANE_SVG_PATH =
  "M14 2L16.5 10L24 13V15L16.5 13L16.5 20L19 23V25L14 23L9 25V23L11.5 20L11.5 13L4 15V13L11.5 10L14 2Z";

function initMap() {
  map = L.map("map").setView([47.6062, -122.3321], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 18,
  }).addTo(map);
}

function clearMarkers() {
  markers.forEach((m) => map.removeLayer(m));
  markers = [];
}

function formatAltitude(meters) {
  if (meters === null) return "N/A";
  const feet = Math.round(meters * 3.281);
  return `${feet.toLocaleString()} ft`;
}

function formatSpeed(ms) {
  if (ms === null) return "N/A";
  const mph = Math.round(ms * 2.237);
  return `${mph} mph`;
}

function formatAirport(icaoCode) {
  if (!icaoCode) return null;
  if (icaoCode.length === 4 && icaoCode.startsWith("K")) {
    return icaoCode.slice(1);
  }
  return icaoCode;
}

function formatRoute(dep, arr) {
  const from = formatAirport(dep);
  const to = formatAirport(arr);
  if (from && to) return `${from} → ${to}`;
  if (from) return `${from} → ?`;
  if (to) return `? → ${to}`;
  return null;
}

function formatTimeInAir(minutes) {
  if (minutes === null || minutes === undefined) return null;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function planeIcon(heading) {
  const rotation = heading || 0;
  const svg = `<svg width="48" height="48" viewBox="0 0 28 28" style="transform:rotate(${rotation}deg)" fill="none">
    <path d="${PLANE_SVG_PATH}" fill="#e70074"/>
  </svg>`;
  return L.divIcon({
    html: svg,
    className: "plane-icon",
    iconSize: [48, 48],
    iconAnchor: [24, 24],
  });
}

function showLoading() {
  const list = document.getElementById("aircraft-list");
  list.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <div class="loading-text">Scanning the skies...</div>
    </div>
  `;
}

function showEmpty() {
  const list = document.getElementById("aircraft-list");
  list.innerHTML = `
    <div class="empty-state">
      <svg class="empty-plane-icon" viewBox="0 0 28 28" fill="none">
        <path d="${PLANE_SVG_PATH}" fill="#64748b"/>
      </svg>
      <p class="empty-title">All clear up there!</p>
      <p class="empty-sub">No aircraft detected nearby. Try refreshing in a moment.</p>
    </div>
  `;
}

function renderFlightDetails(container, data) {
  const route = formatRoute(data.departure_airport, data.arrival_airport);
  const timeInAir = formatTimeInAir(data.time_in_air_min);
  container.innerHTML = `
    <div class="card-details">
      ${data.airline ? `<div class="detail-row"><span class="detail-label">Airline</span> ${escapeHtml(data.airline)}</div>` : ""}
      ${route ? `<div class="detail-row"><span class="detail-label">Route</span> ${escapeHtml(route)}</div>` : ""}
      ${data.departure_airport_name ? `<div class="detail-row"><span class="detail-label">From</span> ${escapeHtml(data.departure_airport_name)}</div>` : ""}
      ${data.arrival_airport_name ? `<div class="detail-row"><span class="detail-label">To</span> ${escapeHtml(data.arrival_airport_name)}</div>` : ""}
      ${data.aircraft_type ? `<div class="detail-row"><span class="detail-label">Aircraft</span> ${escapeHtml(data.aircraft_type)}</div>` : ""}
      ${timeInAir ? `<div class="detail-row"><span class="detail-label">In air</span> ${timeInAir}</div>` : ""}
    </div>
  `;
}

function fetchFlightDetails(callsign, container, btn) {
  // Check localStorage cache
  const cached = getCachedDetails(callsign);
  if (cached) {
    renderFlightDetails(container, cached);
    btn.style.display = "none";
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="detail-spinner"></span>';

  fetch(`/api/flight-details?callsign=${encodeURIComponent(callsign)}`)
    .then((r) => {
      if (!r.ok) throw new Error("Not found");
      return r.json();
    })
    .then((data) => {
      setCachedDetails(callsign, data);
      renderFlightDetails(container, data);
      btn.style.display = "none";
    })
    .catch(() => {
      container.innerHTML =
        '<div class="card-details"><span class="detail-error">No details available</span></div>';
      btn.style.display = "none";
    });
}

function showAircraft(aircraft) {
  const list = document.getElementById("aircraft-list");
  list.innerHTML = "";
  clearMarkers();

  if (aircraft.length === 0) {
    showEmpty();
    return;
  }

  aircraft.forEach((ac, i) => {
    const card = document.createElement("div");
    card.className = "aircraft-card";
    card.style.animationDelay = `${i * 0.06}s`;
    const route = formatRoute(ac.departure_airport, ac.arrival_airport);
    const timeInAir = formatTimeInAir(ac.time_in_air_min);
    const isPrivate = !ac.airline && ac.callsign && /^[A-Z]{1,2}[-\d]/.test(ac.callsign);
    const airlineLabel = ac.airline || (isPrivate ? "Private Aircraft" : "");
    const showDetailsBtn = hasFlightaware && ac.callsign && !isPrivate;
    card.innerHTML = `
      <div class="card-header">
        <div>
          <div class="callsign">${escapeHtml(ac.callsign) || "Unknown"}</div>
          ${airlineLabel ? `<div class="airline-name">${escapeHtml(airlineLabel)}</div>` : ""}
        </div>
        ${showDetailsBtn ? '<button class="detail-btn">Details</button>' : ""}
      </div>
      <div class="details">
        <span class="badge badge-country">${escapeHtml(ac.origin_country)}</span>
        ${route ? `<span class="badge badge-route">${escapeHtml(route)}</span>` : ""}
        ${timeInAir ? `<span class="badge badge-time">${timeInAir} in air</span>` : ""}
        <span class="badge badge-alt">${formatAltitude(ac.altitude_m)}</span>
        <span class="badge badge-speed">${formatSpeed(ac.velocity_ms)}</span>
        <span class="badge badge-dist">${ac.distance_km} km</span>
      </div>
      <div class="details-container"></div>
    `;

    // Details button handler
    const detailBtn = card.querySelector(".detail-btn");
    const detailsContainer = card.querySelector(".details-container");
    if (detailBtn) {
      detailBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fetchFlightDetails(ac.callsign, detailsContainer, detailBtn);
      });
    }

    // Card click → pan to plane
    card.addEventListener("click", () => {
      map.setView([ac.latitude, ac.longitude], 13);
      const tabMap = document.getElementById("tab-map");
      const tabList = document.getElementById("tab-list");
      const sidebar = document.getElementById("sidebar");
      if (window.innerWidth <= 768) {
        tabMap.classList.add("active");
        tabList.classList.remove("active");
        sidebar.classList.remove("mobile-visible");
        map.invalidateSize();
      }
    });
    list.appendChild(card);

    if (ac.latitude && ac.longitude) {
      const marker = L.marker([ac.latitude, ac.longitude], {
        icon: planeIcon(ac.heading),
      })
        .addTo(map)
        .bindPopup(
          `<b>${escapeHtml(ac.callsign) || "Unknown"}</b>` +
            (ac.airline ? `<br>${escapeHtml(ac.airline)}` : "") +
            (route ? `<br>${escapeHtml(route)}` : "") +
            (timeInAir ? `<br>${timeInAir} in air` : "") +
            `<br>${formatAltitude(ac.altitude_m)}` +
            `<br>${formatSpeed(ac.velocity_ms)}` +
            `<br>${ac.distance_km} km away`
        );
      markers.push(marker);
    }
  });
}

function createUserMarker(lat, lon) {
  if (userMarker) map.removeLayer(userMarker);
  const icon = L.divIcon({
    html: `<div class="user-marker"><div class="user-pulse"></div><div class="user-dot"></div></div>`,
    className: "",
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
  userMarker = L.marker([lat, lon], { icon })
    .addTo(map)
    .bindPopup("You are here");
}

function fetchOverhead(lat, lon) {
  const status = document.getElementById("status");
  status.textContent = "Scanning for aircraft...";
  showLoading();

  fetch(`/api/overhead?lat=${lat}&lon=${lon}&radius=15`)
    .then((r) => r.json())
    .then((data) => {
      hasFlightaware = data.has_flightaware || false;
      status.textContent = `Found ${data.count} aircraft nearby`;
      showAircraft(data.aircraft);
    })
    .catch((err) => {
      status.textContent = "Error fetching aircraft data";
      showEmpty();
      console.error(err);
    });
}

function locate() {
  const status = document.getElementById("status");

  if (!navigator.geolocation) {
    status.textContent = "Geolocation is not supported by your browser.";
    return;
  }

  status.textContent = "Getting your location...";

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude } = pos.coords;
      map.setView([latitude, longitude], 12);
      createUserMarker(latitude, longitude);
      fetchOverhead(latitude, longitude);
    },
    (err) => {
      status.textContent = "Unable to get location. Using default (Seattle).";
      fetchOverhead(47.6062, -122.3321);
    },
    { timeout: 5000, maximumAge: 60000 }
  );
}

function setupMobileTabs() {
  const tabMap = document.getElementById("tab-map");
  const tabList = document.getElementById("tab-list");
  const sidebar = document.getElementById("sidebar");

  tabMap.addEventListener("click", () => {
    tabMap.classList.add("active");
    tabList.classList.remove("active");
    sidebar.classList.remove("mobile-visible");
    map.invalidateSize();
  });

  tabList.addEventListener("click", () => {
    tabList.classList.add("active");
    tabMap.classList.remove("active");
    sidebar.classList.add("mobile-visible");
  });
}

initMap();
locate();
setupMobileTabs();
setInterval(locate, 60000);

document.getElementById("refresh-btn").addEventListener("click", locate);
