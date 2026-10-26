const TOKEN_KEY = "voyageai_jwt";
const USER_KEY = "voyageai_email";
const byId = id => document.getElementById(id);

// Keep the authenticated session across page refreshes. Sign-out and invalid-token
// responses explicitly clear the session; a page load must not silently sign out.
const clearAuthSession = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  if (typeof updateAuthUi === "function") updateAuthUi();
};

const scrollToHashTarget = (hash, behavior = "smooth") => {
  if (!hash || !hash.startsWith("#")) return;
  const target = document.querySelector(hash);
  if (!target) return;
  const navbar = document.querySelector(".navbar");
  const offset = (navbar?.getBoundingClientRect().height || 0) + 16;
  const top = Math.max(0, target.getBoundingClientRect().top + window.scrollY - offset);
  window.scrollTo({ top, behavior });
};

document.querySelectorAll('a[href="#travel-explorer"]').forEach(link => {
  link.addEventListener("click", event => {
    event.preventDefault();
    history.pushState(null, "", "#travel-explorer");
    scrollToHashTarget("#travel-explorer");
  });
});

if (window.location.hash === "#travel-explorer") {
  window.addEventListener("load", () => {
    requestAnimationFrame(() => requestAnimationFrame(() => scrollToHashTarget("#travel-explorer", "auto")));
  }, { once: true });
}

const getToken = () => localStorage.getItem(TOKEN_KEY);
const authHeaders = (headers = {}) => ({
  ...headers,
  ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
});

const api = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: authHeaders({ "Content-Type": "application/json", ...(options.headers || {}) }),
  });
  if (response.ok) return response.json();
  let message = "Request failed. Please try again.";
  try { message = (await response.json()).detail || message; } catch (_) {}
  if (response.status === 401) {
    clearAuthSession();
    message = "Your session has expired or is invalid. Please sign in again.";
  }
  if (response.status === 403) message = "You do not have permission to perform this action.";
  throw new Error(message);
};

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
const money = amount => `₹${Number(amount || 0).toLocaleString("en-IN")}`;
const updateAuthUi = () => {
  const signedIn = Boolean(getToken());
  byId("authStatus").textContent = signedIn ? localStorage.getItem(USER_KEY) || "Signed in" : "Guest";
  const button = byId("authButton");
  button.textContent = signedIn ? "Sign out" : "Sign in";
  button.dataset.bsToggle = signedIn ? "" : "modal";
  button.dataset.bsTarget = signedIn ? "" : "#loginModal";
};

byId("shareStoryButton").addEventListener("click", event => {
  if (getToken()) return;
  event.preventDefault();
  bootstrap.Modal.getOrCreateInstance(byId("loginModal")).show();
});

byId("authButton").addEventListener("click", event => {
  if (!getToken()) return;
  event.preventDefault();
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  updateAuthUi();
  loadSavedItineraries();
  loadStories();
  byId("chatAnswer").textContent = "You have signed out. Sign in to use the protected AI assistant.";
});

byId("loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const message = byId("loginMessage");
  const button = event.currentTarget.querySelector("button[type='submit']");
  button.disabled = true;
  message.className = "login-message mt-3 mb-0";
  message.textContent = "Signing in...";
  try {
    const body = new URLSearchParams({ username: byId("loginEmail").value, password: byId("loginPassword").value });
    const response = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
    const data = await response.json();
    if (!response.ok || !data.access_token) throw new Error(data.detail || "Could not sign in.");
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, byId("loginEmail").value);

    message.className = "login-message success mt-3 mb-0";
    message.textContent = "Signed in successfully.";

    // Check whether the authenticated user is an administrator.
    try {
      await api("/api/admin/me");

      // Admin → go directly to Admin Dashboard.
      window.location.replace("/admin");
      return;
    } catch (adminError) {
      // Not an admin → continue with the normal traveler experience.
      console.log("Admin check:", adminError.message);
    }

    // Normal traveler.
    updateAuthUi();
    loadSavedItineraries();
    loadStories();

    setTimeout(() => {
      const modal = bootstrap.Modal.getInstance(byId("loginModal"));
      if (modal) modal.hide();
    }, 500);
  } catch (error) {
    message.className = "login-message error mt-3 mb-0";
    message.textContent = error.message;
  } finally { button.disabled = false; }
});


byId("registerForm").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = byId("registerMessage");
  const button = form.querySelector("button[type='submit']");
  button.disabled = true;
  message.className = "login-message mt-3 mb-0";
  try {
    if (byId("registerPassword").value !== byId("registerConfirmPassword").value) {
      throw new Error("Passwords do not match.");
    }
    const response = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: byId("registerUsername").value.trim(),
        full_name: byId("registerName").value.trim(),
        email: byId("registerEmail").value.trim(),
        phone: byId("registerPhone").value.trim(),
        password: byId("registerPassword").value
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Registration failed.");
    const registeredUsername = byId("registerUsername").value.trim();
    message.className = "login-message success mt-3 mb-0";
    message.textContent = "Registration successful. You can sign in now.";
    form.reset();
    setTimeout(() => {
      bootstrap.Modal.getInstance(byId("registerModal")).hide();
      bootstrap.Modal.getOrCreateInstance(byId("loginModal")).show();
      byId("loginEmail").value = registeredUsername;
    }, 700);
  } catch (error) {
    message.className = "login-message error mt-3 mb-0";
    message.textContent = error.message;
  } finally { button.disabled = false; }
});

const renderGuideSection = item => {
  const distance = item.distance_km == null ? "" : `<span>${Number(item.distance_km).toFixed(1)} km from centre</span>`;
  const badge = item.must_visit ? '<span class="guide-badge">Must visit</span>' : "";
  const bestTime = item.best_time_to_visit ? `<p class="visit-time">${escapeHtml(item.best_time_to_visit)}</p>` : "";
  return `<section class="guide-section"><div class="guide-heading"><div><span class="guide-time">${escapeHtml(item.time)}</span><h4>${escapeHtml(item.title)}</h4></div>${badge}</div><p>${escapeHtml(item.description)}</p>${bestTime}<div class="guide-details"><span>${escapeHtml(item.category)}</span>${distance}<span>Estimated: ${money(item.budget_inr)}</span></div></section>`;
};

const renderDaySchedule = day => {
  const events = Array.isArray(day.schedule) ? day.schedule : [];
  if (!events.length) return (day.guide_sections || []).map(renderGuideSection).join("");
  const icons = { visit: "📍", meal: "🍽️", rest: "☕", food_experience: "🥐" };
  return `<div class="day-schedule">${events.map(event => {
    const cost = Number(event.estimated_cost_inr || 0);
    const costText = cost > 0 ? `<span class="schedule-cost">Est. ${money(cost)}</span>` : "";
    return `<div class="schedule-event schedule-event--${escapeHtml(event.kind || "visit")}">
      <div class="schedule-time">${escapeHtml(event.start)}${event.end ? `–${escapeHtml(event.end)}` : ""}</div>
      <div class="schedule-marker" aria-hidden="true">${icons[event.kind] || "•"}</div>
      <div class="schedule-copy"><h4>${escapeHtml(event.title || "Explore")}</h4><p>${escapeHtml(event.description || "")}</p>
      ${(event.category || costText) ? `<div class="schedule-meta">${event.category ? `<span>${escapeHtml(event.category)}</span>` : ""}${costText}</div>` : ""}
      </div></div>`;
  }).join("")}<p class="schedule-disclaimer">Schedule times and costs are estimates. Confirm opening hours, ticket prices, transport and activity availability before travelling.</p></div>`;
};

byId("plannerForm").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const itinerary = byId("itinerary");
  const originalText = button.innerHTML;
  button.disabled = true;
  button.textContent = "Creating your guide...";
  itinerary.innerHTML = '<div class="empty-itinerary"><span class="empty-icon">✦</span><h3>Creating your travel guide...</h3><p>Finding places that match your interests.</p></div>';
  try {
    const data = await api("/api/itineraries/preview", { method: "POST", body: JSON.stringify({ destination: byId("destination").value, days: +byId("days").value, budget: +byId("budget").value, interests: byId("interests").value.split(",").map(item => item.trim()).filter(Boolean) }) });
    const dailyBudget = data.budget / data.days;
    itinerary.innerHTML = `<div class="itinerary-intro"><div class="itinerary-intro-main"><p class="eyebrow accent">PERSONALISED TRAVEL GUIDE</p><h2>${escapeHtml(data.destination)} · ${data.days} days</h2><p class="text-muted mb-1">Trip budget: <strong>${money(data.budget)}</strong> · around ${money(dailyBudget)} per day</p><button type="button" class="btn btn-outline-primary" id="saveItineraryButton">Save this itinerary <span>♡</span></button></div><div class="trip-estimate"><span>ESTIMATED TRIP TOTAL</span><strong>${money(data.estimated_trip_cost_inr)}</strong><small>Includes visits and 3 meals per day${data.budget_estimates_adjusted ? "; estimates adjusted to fit your budget" : ""}</small></div></div>${data.itinerary.map(day => `<article class="trip-day"><div class="day-header"><div><span>DAY ${day.day}</span><h3>${escapeHtml(day.day_title)}</h3></div><strong>${money(day.estimated_day_cost_inr)}<small>day estimate · visits + 3 meals</small></strong></div
${!Array.isArray(day.activities) || day.activities.length === 0
  ? `<div class="empty-itinerary">
       <h4>No named attractions found for this day</h4>
       <p>${escapeHtml(day.availability_note || "No verified attractions were returned for this day. Try another destination or interest.")}</p>
     </div>`
  : (Array.isArray(day.schedule)
      ? renderDaySchedule(day)
      : (day.guide_sections && day.guide_sections.length
          ? day.guide_sections.map(renderGuideSection).join("")
          : `<div class="empty-itinerary">
               <h4>No schedule available</h4>
               <p>${escapeHtml(day.availability_note || "Try another destination or interest.")}</p>
             </div>`))}
</article>`).join("")}`;
    byId("planner")?.scrollIntoView({ behavior: "smooth" });
  } catch (error) { alert(error.message); }
});


async function loadSavedItineraries() {
  const container = byId("savedItineraries");
  if (!container) return;

  if (!getToken()) {
    container.innerHTML = '<div class="saved-empty"><span class="empty-icon">♡</span><h3>Your saved trips will appear here</h3><p>Sign in and save an itinerary to keep it for later.</p></div>';
    return;
  }

  try {
    const response = await api("/api/itineraries");
    const trips = Array.isArray(response)
      ? response
      : Array.isArray(response?.items)
        ? response.items
        : Array.isArray(response?.itineraries)
          ? response.itineraries
          : [];

    if (!trips.length) {
      container.innerHTML = '<div class="saved-empty"><span class="empty-icon">♡</span><h3>No saved trips yet</h3><p>Generate a travel guide and choose “Save this itinerary”.</p></div>';
      return;
    }

    container.innerHTML = trips.map(trip => `
      <article class="saved-itinerary-card">
        <div class="saved-itinerary-card__body">
          <p class="eyebrow accent">SAVED TRIP</p>
          <h3>${escapeHtml(trip.destination || "Travel itinerary")}</h3>
          <p>${Number(trip.days || 0)} day${Number(trip.days || 0) === 1 ? "" : "s"} · Budget ${money(trip.budget)}</p>
          ${trip.created_at ? `<small class="text-muted">Saved ${escapeHtml(String(trip.created_at).slice(0, 10))}</small>` : ""}
        </div>
        <button type="button" class="btn btn-outline-danger btn-sm" data-delete-itinerary="${escapeHtml(trip.id)}">Delete</button>
      </article>
    `).join("");
  } catch (error) {
    container.innerHTML = `<div class="saved-empty"><h3>Could not load saved trips</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

document.addEventListener("click", async event => {
  const saveButton = event.target.closest("#saveItineraryButton");
  if (saveButton) {
    if (!getToken()) {
      bootstrap.Modal.getOrCreateInstance(byId("loginModal")).show();
      return;
    }
    const original = saveButton.innerHTML;
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    try {
      await api("/api/itineraries", {
        method: "POST",
        body: JSON.stringify({
          destination: byId("destination").value.trim(),
          days: Number(byId("days").value),
          budget: Number(byId("budget").value),
          interests: byId("interests").value.split(",").map(item => item.trim()).filter(Boolean)
        })
      });
      saveButton.textContent = "Saved ✓";
      await loadSavedItineraries();
    } catch (error) {
      alert(error.message);
      saveButton.innerHTML = original;
    } finally {
      saveButton.disabled = false;
    }
    return;
  }

  const deleteButton = event.target.closest("[data-delete-itinerary]");
  if (deleteButton) {
    const id = deleteButton.dataset.deleteItinerary;
    if (!id || !confirm("Delete this saved itinerary?")) return;
    deleteButton.disabled = true;
    try {
      await api(`/api/itineraries/${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadSavedItineraries();
    } catch (error) {
      alert(error.message);
      deleteButton.disabled = false;
    }
  }
});

const uploadStatus = byId("uploadStatus");

const explorerStatus = byId("travelExplorerStatus");
const explorerResults = byId("travelExplorerResults");

const explorerProviderLabel = payload => {
  if (!payload) return "";
  const provider = payload.provider || "Unknown provider";
  if (payload.status === "fallback") return `${provider} • live fallback`;
  if (payload.status === "no_data") return `${provider} • no data`;
  return `${provider}${payload.live ? " • live" : ""}`;
};

const renderExplorerError = (title, error) =>
  `<div class="explorer-error"><strong>${escapeHtml(title)}</strong><br>${escapeHtml(error?.message || "Request failed. Please try again.")}</div>`;

const renderExplorerList = (items, type) => {
  if (!Array.isArray(items) || !items.length) {
    return `<p class="explorer-meta">No ${type} were returned for this destination.</p>`;
  }

  const markerType = type === "restaurants" ? "restaurant" : "hotel";

  return `<div class="explorer-list">${items.slice(0, 20).map((item, index) => {
    const coords = item.latitude != null && item.longitude != null
      ? `${Number(item.latitude).toFixed(4)}, ${Number(item.longitude).toFixed(4)}`
      : "";
    const source = item.source || "";
    const markerKey = `${markerType}-${index}`;

    return `<article class="explorer-item"
      data-map-place="${markerKey}"
      tabindex="0"
      role="button"
      aria-label="Show ${escapeHtml(item.name || "Unnamed place")} on map">
      <h4>${escapeHtml(item.name || "Unnamed place")}</h4>
      ${item.address ? `<p class="explorer-meta mb-1">${escapeHtml(item.address)}</p>` : ""}
      ${item.type ? `<span class="explorer-badge">${escapeHtml(item.type)}</span>` : ""}
      ${coords ? `<p class="explorer-meta mb-0 mt-2">Coordinates: ${escapeHtml(coords)}</p>` : ""}
      ${source ? `<p class="explorer-meta mb-0 mt-1">Source: ${escapeHtml(source)}</p>` : ""}
      <p class="explorer-map-link mb-0 mt-2">View on map ↗</p>
    </article>`;
  }).join("")}</div>`;
};


let explorerMap = null;
let explorerMarker = null;
let explorerPlaceMarkers = [];
let explorerActivePopup = null;

const clearExplorerPlaceMarkers = () => {
  explorerActivePopup?.remove();
  explorerActivePopup = null;
  hideExplorerRoutePanel();
  explorerPlaceMarkers.forEach(marker => marker.remove());
  explorerPlaceMarkers = [];
};

const createExplorerPopupHtml = (item, type) => {
  const name = escapeHtml(item?.name || "Unnamed place");
  const address = item?.address
    ? `<div class="explorer-popup-row"><span>Address</span><strong>${escapeHtml(item.address)}</strong></div>`
    : "";

  const phone = item?.phone
    ? `<div class="explorer-popup-row"><span>Phone</span><strong>${escapeHtml(item.phone)}</strong></div>`
    : "";

  const website = item?.website
    ? `<div class="explorer-popup-row"><span>Website</span><a href="${escapeHtml(item.website)}" target="_blank" rel="noopener noreferrer">Open website ↗</a></div>`
    : "";

  const hours = item?.opening_hours
    ? `<div class="explorer-popup-row"><span>Opening hours</span><strong>${escapeHtml(item.opening_hours)}</strong></div>`
    : "";

  const cuisine = item?.cuisine
    ? `<div class="explorer-popup-row"><span>Cuisine</span><strong>${escapeHtml(item.cuisine)}</strong></div>`
    : "";

  const source = item?.source
    ? `<div class="explorer-popup-row"><span>Source</span><strong>${escapeHtml(item.source)}</strong></div>`
    : "";

  const latitude = item?.latitude != null ? Number(item.latitude).toFixed(6) : "";
  const longitude = item?.longitude != null ? Number(item.longitude).toFixed(6) : "";
  const coordinates = latitude && longitude
    ? `<div class="explorer-popup-row"><span>Coordinates</span><strong>${latitude}, ${longitude}</strong></div>`
    : "";

  const routeControls = "";

  const label = type === "restaurant" ? "Restaurant" : "Hotel";

  return `
    <div class="explorer-popup explorer-popup--details">
      <div class="explorer-popup-type">${label}</div>
      <strong class="explorer-popup-title">${name}</strong>
      <div class="explorer-popup-details">
        ${address}
        ${phone}
        ${website}
        ${hours}
        ${cuisine}
        ${coordinates}
        ${source}
      </div>
      ${routeControls}
    </div>
  `;
};

const hideExplorerRoutePanel = () => {
  const panel = document.getElementById("explorerRoutePanel");
  if (panel) {
    panel.innerHTML = "";
    panel.classList.remove("is-visible");
  }
};

const hideExplorerAreaNotice = () => {
  const notice = document.getElementById("explorerAreaNotice");
  if (!notice) return;

  notice.innerHTML = "";
  notice.classList.remove("is-visible");
};

const showExplorerAreaNotice = (item, type) => {
  const notice = document.getElementById("explorerAreaNotice");
  if (!notice) return;

  const label = type === "restaurant" ? "Restaurant" : "Hotel";
  const name = escapeHtml(item?.name || "Selected place");
  const areaType = escapeHtml(explorerDestinationContext?.place_type || "area");

  notice.innerHTML = `
    <div class="explorer-area-notice__content">
      <div>
        <span class="explorer-popup-type">${label}</span>
        <strong>${name}</strong>
      </div>
      <p><strong>Directions unavailable for area searches.</strong> ${areaType} searches show places across the selected area. Use <em>View on map</em> to inspect this place.</p>
    </div>
  `;
  notice.classList.add("is-visible");
};

const showExplorerRoutePanel = (item, type) => {
  const panel = document.getElementById("explorerRoutePanel");
  if (!panel) return;

  const latitude = item?.latitude != null ? Number(item.latitude).toFixed(6) : "";
  const longitude = item?.longitude != null ? Number(item.longitude).toFixed(6) : "";
  if (!latitude || !longitude) {
    hideExplorerRoutePanel();
    return;
  }

  const label = type === "restaurant" ? "Restaurant" : "Hotel";
  const name = escapeHtml(item?.name || "Selected place");

  if (explorerDestinationContext?.is_area) {
    hideExplorerRoutePanel();
    showExplorerAreaNotice(item, type);
    return;
  }

  hideExplorerAreaNotice();

  panel.innerHTML = `
    <div class="explorer-route-controls">
      <div class="explorer-route-panel-place">
        <span class="explorer-popup-type">${label}</span>
        <strong>${name}</strong>
      </div>

      <div class="explorer-route-panel-action">
        <label class="explorer-route-label" for="active-route-mode">Travel mode</label>
        <select
          id="active-route-mode"
          class="explorer-route-mode"
          aria-label="Choose travel mode"
          data-route-mode>
          <option value="drive">🚗 Driving</option>
          <option value="walk">🚶 Walking</option>
          <option value="bicycle">🚲 Bicycle</option>
          <option value="scooter">🛵 Scooter</option>
        </select>
        <button
          type="button"
          class="explorer-route-button"
          data-route-lat="${escapeHtml(latitude)}"
          data-route-lon="${escapeHtml(longitude)}"
          data-route-name="${name}"
          data-route-action>
          Calculate route →
        </button>
      </div>
    </div>
  `;

  panel.classList.add("is-visible");
};

const addExplorerPlaceMarkers = (items, type) => {
  if (!explorerMap || !Array.isArray(items)) return;

  const markerColor = type === "restaurant" ? "#e85d04" : "#2a9d8f";

  items.slice(0, 20).forEach((item, index) => {
    const latitude = Number(item?.latitude);
    const longitude = Number(item?.longitude);

    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;

    const markerKey = `${type}-${index}`;

    const marker = new maplibregl.Marker({ color: markerColor })
      .setLngLat([longitude, latitude])
      .setPopup(
        new maplibregl.Popup({ offset: 25 }).setHTML(
          createExplorerPopupHtml(item, type)
        )
      )
      .addTo(explorerMap);

    marker.__explorerKey = markerKey;
    marker.__explorerItem = item;
    marker.__explorerType = type;

    marker.getElement().addEventListener("click", () => {
      explorerActivePopup?.remove();
      explorerActivePopup = marker.getPopup();
      marker.togglePopup();
      showExplorerRoutePanel(item, type);
      highlightExplorerListItem(markerKey);
    });

    explorerPlaceMarkers.push(marker);
  });
};

const highlightExplorerListItem = markerKey => {
  document.querySelectorAll(".explorer-item.is-map-active").forEach(item => {
    item.classList.remove("is-map-active");
  });

  const item = document.querySelector(`[data-map-place="${markerKey}"]`);
  if (!item) return;

  item.classList.add("is-map-active");
  item.scrollIntoView({ behavior: "smooth", block: "nearest" });

  window.setTimeout(() => {
    item.classList.remove("is-map-active");
  }, 2200);
};

const scrollExplorerMapIntoView = () => {
  const mapElement = document.getElementById("explorerMap");
  if (!mapElement) return;

  const navbar = document.querySelector(".navbar");
  const navbarHeight = navbar?.getBoundingClientRect().height || 0;
  const targetTop = Math.max(
    0,
    mapElement.getBoundingClientRect().top + window.scrollY - navbarHeight - 18
  );

  window.scrollTo({
    top: targetTop,
    behavior: "smooth"
  });
};

const focusExplorerMarkerFromList = markerKey => {
  const marker = explorerPlaceMarkers.find(
    candidate => candidate.__explorerKey === markerKey
  );

  if (!marker || !explorerMap) return;

  const lngLat = marker.getLngLat();
  const mapElement = explorerMap.getContainer();

  // Move the page to the map first so the popup and route controls are visible.
  scrollExplorerMapIntoView();

  // Center the selected place in the upper-middle part of the map. This
  // leaves room below the popup for the travel-mode selector and route button.
  explorerMap.flyTo({
    center: [lngLat.lng, lngLat.lat],
    zoom: Math.max(explorerMap.getZoom(), 14),
    speed: 1.2,
    curve: 1.2,
    offset: [0, -80],
    essential: true
  });

  explorerActivePopup?.remove();
  explorerActivePopup = marker.getPopup();
  marker.togglePopup();
  showExplorerRoutePanel(marker.__explorerItem, marker.__explorerType);
  highlightExplorerListItem(markerKey);

  // Route controls are displayed in a dedicated map overlay,
  // so the place popup itself no longer needs viewport correction.
};

const bindExplorerListInteractions = () => {
  explorerResults.querySelectorAll("[data-map-place]").forEach(item => {
    if (item.dataset.mapBound === "true") return;

    const activate = () => {
      focusExplorerMarkerFromList(item.dataset.mapPlace);
    };

    item.addEventListener("click", activate);

    item.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });

    item.dataset.mapBound = "true";
  });
};


let explorerRouteOrigin = null;
let explorerLastRoute = null;
let explorerDestinationContext = {};

const fitExplorerPlaces = () => {
  if (!explorerMap || !explorerMap.loaded()) return;

  const coordinates = [];

  if (explorerRouteOrigin) {
    const lat = Number(explorerRouteOrigin.latitude);
    const lon = Number(explorerRouteOrigin.longitude);

    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      coordinates.push([lon, lat]);
    }
  }

  explorerPlaceMarkers.forEach(marker => {
    const lngLat = marker.getLngLat();
    if (lngLat && Number.isFinite(lngLat.lng) && Number.isFinite(lngLat.lat)) {
      coordinates.push([lngLat.lng, lngLat.lat]);
    }
  });

  if (!coordinates.length) return;

  if (coordinates.length === 1) {
    explorerMap.flyTo({
      center: coordinates[0],
      zoom: 13,
      speed: 1.2,
      curve: 1.2,
      essential: true
    });
    return;
  }

  const bounds = new maplibregl.LngLatBounds(
    coordinates[0],
    coordinates[0]
  );

  coordinates.slice(1).forEach(coordinate => bounds.extend(coordinate));

  explorerMap.fitBounds(bounds, {
    padding: 70,
    maxZoom: 14,
    duration: 700
  });

  explorerStatus.className = "explorer-status";
  explorerStatus.textContent =
    `Showing ${explorerPlaceMarkers.length} nearby places on the map.`;
};


if (!document.body.dataset.explorerFitPlacesBound) {
  document.addEventListener("click", event => {
    const button = event.target.closest("#fitExplorerPlaces");
    if (!button) return;

    event.preventDefault();
    fitExplorerPlaces();
  });

  document.body.dataset.explorerFitPlacesBound = "true";
}

const clearExplorerRoute = () => {
  // Clearing a route is also a UI-state reset. It must work even when the
  // previous map instance has already been removed while loading a new
  // destination. Otherwise the old route summary can survive the search.
  if (explorerMap) {
    const source = explorerMap.getSource("explorer-route");
    if (source) {
      source.setData({
        type: "FeatureCollection",
        features: []
      });
    }
  }

  explorerLastRoute = null;

  const summary = document.getElementById("explorerRouteSummary");
  if (summary) {
    summary.innerHTML = "";
    summary.classList.remove("is-visible");
  }
};

const resetExplorerRouteState = () => {
  clearExplorerRoute();
  hideExplorerRoutePanel();
  explorerRouteOrigin = null;
  explorerDestinationContext = {};
  hideExplorerAreaNotice();
};

const addExplorerRouteLayer = () => {
  if (!explorerMap || explorerMap.getSource("explorer-route")) return;

  explorerMap.addSource("explorer-route", {
    type: "geojson",
    data: {
      type: "FeatureCollection",
      features: []
    }
  });

  explorerMap.addLayer({
    id: "explorer-route-line",
    type: "line",
    source: "explorer-route",
    layout: {
      "line-cap": "round",
      "line-join": "round"
    },
    paint: {
      "line-color": "#2563d9",
      "line-width": 5,
      "line-opacity": 0.9
    }
  });
};

const collectRouteCoordinates = geometry => {
  if (!geometry?.coordinates) return [];

  const flatten = value => {
    if (!Array.isArray(value) || !value.length) return [];
    if (typeof value[0] === "number") return [value];
    return value.flatMap(flatten);
  };

  return flatten(geometry.coordinates);
};

const renderExplorerRouteSummary = (routePayload, mode) => {
  const summary = document.getElementById("explorerRouteSummary");
  if (!summary) return;

  const feature = routePayload?.features?.[0];
  const properties = feature?.properties || {};
  const distanceKm = Number(properties.distance) / 1000;
  const durationMin = Number(properties.time) / 60;

  const modeLabels = {
    drive: "🚗 Driving",
    walk: "🚶 Walking",
    bicycle: "🚲 Bicycle",
    scooter: "🛵 Scooter"
  };

  const distanceText = Number.isFinite(distanceKm)
    ? `${distanceKm.toFixed(1)} km`
    : "Distance unavailable";

  const durationText = Number.isFinite(durationMin)
    ? `${Math.max(1, Math.round(durationMin))} min`
    : "Time unavailable";

  summary.innerHTML = `
    <div class="explorer-route-summary-card">
      <div>
        <span class="explorer-route-summary-label">Selected route</span>
        <strong>${escapeHtml(modeLabels[mode] || "Route")}</strong>
      </div>
      <div class="explorer-route-stat">
        <span>Distance</span>
        <strong>${escapeHtml(distanceText)}</strong>
      </div>
      <div class="explorer-route-stat">
        <span>Estimated time</span>
        <strong>${escapeHtml(durationText)}</strong>
      </div>
      <button type="button" class="explorer-clear-route" id="clearExplorerRoute">
        Clear route
      </button>
    </div>
  `;

  summary.classList.add("is-visible");

  document.getElementById("clearExplorerRoute")?.addEventListener("click", () => {
    clearExplorerRoute();
    if (explorerRouteOrigin) {
      explorerStatus.className = "explorer-status";
      explorerStatus.textContent =
        `Route cleared. Destination remains ${explorerRouteOrigin.name}.`;
    }
  });
};

const drawExplorerRoute = routePayload => {
  if (!explorerMap || !routePayload?.features?.length) return;

  const source = explorerMap.getSource("explorer-route");
  if (!source) return;

  source.setData(routePayload);
  explorerLastRoute = routePayload;

  const coordinates = routePayload.features.flatMap(feature =>
    collectRouteCoordinates(feature.geometry)
  );

  if (!coordinates.length) return;

  const bounds = new maplibregl.LngLatBounds(
    coordinates[0],
    coordinates[0]
  );

  coordinates.slice(1).forEach(coordinate => bounds.extend(coordinate));

  explorerMap.fitBounds(bounds, {
    padding: 70,
    maxZoom: 15,
    duration: 700
  });

  const firstFeature = routePayload.features[0];
  const properties = firstFeature?.properties || {};
  const distanceKm = Number(properties.distance) / 1000;
  const durationMin = Number(properties.time) / 60;

  if (Number.isFinite(distanceKm) && Number.isFinite(durationMin)) {
    explorerStatus.className = "explorer-status success";
    const modeLabels = {
      drive: "Driving",
      walk: "Walking",
      bicycle: "Bicycle",
      scooter: "Scooter"
    };

    explorerStatus.textContent =
      `Route loaded: ${distanceKm.toFixed(1)} km • approximately ${Math.round(durationMin)} min • ${modeLabels[routePayload.mode] || "Driving"} • Geoapify`;
  } else {
    explorerStatus.className = "explorer-status success";
    explorerStatus.textContent = "Route loaded successfully from Geoapify.";
  }

  renderExplorerRouteSummary(routePayload, routePayload.mode || "drive");
};

const requestExplorerRoute = async (latitude, longitude, placeName, mode = "drive") => {
  if (!explorerMap || !explorerRouteOrigin) return;

  if (explorerDestinationContext?.is_area) {
    clearExplorerRoute();
    hideExplorerRoutePanel();
    explorerStatus.className = "explorer-status error";
    explorerStatus.textContent =
      "Directions are unavailable for area searches. Use View on map to inspect the selected place.";
    return;
  }

  const startLat = Number(explorerRouteOrigin.latitude);
  const startLon = Number(explorerRouteOrigin.longitude);
  const endLat = Number(latitude);
  const endLon = Number(longitude);

  if (![startLat, startLon, endLat, endLon].every(Number.isFinite)) {
    return;
  }

  clearExplorerRoute();
  hideExplorerAreaNotice();

  explorerStatus.className = "explorer-status loading";
  explorerStatus.textContent = `Calculating route from ${explorerRouteOrigin.name} to ${placeName}...`;

  try {
    const params = new URLSearchParams({
      start_lat: String(startLat),
      start_lon: String(startLon),
      end_lat: String(endLat),
      end_lon: String(endLon),
      mode: mode
    });

    const routePayload = await api(`/api/route?${params.toString()}`);

    if (!routePayload?.features?.length) {
      throw new Error("No route was returned for this place.");
    }

    drawExplorerRoute(routePayload);
  } catch (error) {
    clearExplorerRoute();
    hideExplorerRoutePanel();
    explorerStatus.className = "explorer-status error";
    explorerStatus.textContent =
      `Directions unavailable. ${error.message || "The routing service is temporarily unavailable."} You can still view this place on the map.`;
  }
};

if (!document.body.dataset.explorerRouteBound) {
  document.addEventListener("click", event => {
    const button = event.target.closest(".explorer-route-button");
    if (!button) return;

    event.preventDefault();

    const controls = button.closest(".explorer-route-controls");
    const modeSelect = controls?.querySelector("[data-route-mode]");
    const mode = modeSelect?.value || "drive";

    requestExplorerRoute(
      button.dataset.routeLat,
      button.dataset.routeLon,
      button.dataset.routeName || "Selected place",
      mode
    );
  });

  document.body.dataset.explorerRouteBound = "true";
}

const renderExplorerMap = (destination, coordinates, restaurantsResult, hotelsResult, destinationContext = {}) => {
  const mapElement = byId("explorerMap");
  if (!mapElement) return;

  if (!window.maplibregl) {
    mapElement.innerHTML = '<div class="explorer-map-message">Map library could not be loaded. Refresh the page and try again.</div>';
    return;
  }

  const latitude = Number(coordinates?.latitude);
  const longitude = Number(coordinates?.longitude);
  const isArea = Boolean(destinationContext?.is_area);

  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    if (explorerMap) {
      explorerMap.remove();
      explorerMap = null;
    }
    clearExplorerPlaceMarkers();
    mapElement.innerHTML = '<div class="explorer-map-message">Map coordinates are unavailable for this destination.</div>';
    return;
  }

  // A new destination starts a completely fresh explorer state. Remove any
  // previous route before replacing the map so distance/time from the old
  // destination can never remain visible for the new search.
  resetExplorerRouteState();
  explorerDestinationContext = { ...destinationContext, is_area: isArea };

  if (explorerMap) {
    explorerMap.remove();
    explorerMap = null;
  }
  clearExplorerPlaceMarkers();
  explorerRouteOrigin = {
    name: destination,
    latitude,
    longitude
  };

  mapElement.innerHTML = "";

  explorerMap = new maplibregl.Map({
    container: "explorerMap",
    style: {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors"
        }
      },
      layers: [
        {
          id: "osm",
          type: "raster",
          source: "osm"
        }
      ]
    },
    center: [longitude, latitude],
    zoom: isArea ? 7 : 12
  });

  explorerMap.addControl(new maplibregl.NavigationControl(), "top-right");

  // MapLibre can initialize while the explorer section is hidden or its layout
  // is changing (for example after closing the sign-in modal). Recalculate its
  // canvas after the container becomes visible and whenever its dimensions change.
  const resizeExplorerMap = () => {
    if (!explorerMap || !mapElement.isConnected) return;
    const rect = mapElement.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) explorerMap.resize();
  };
  requestAnimationFrame(() => requestAnimationFrame(resizeExplorerMap));
  setTimeout(resizeExplorerMap, 250);
  setTimeout(resizeExplorerMap, 800);
  if (window.ResizeObserver) {
    if (window.__explorerMapResizeObserver) window.__explorerMapResizeObserver.disconnect();
    window.__explorerMapResizeObserver = new ResizeObserver(resizeExplorerMap);
    window.__explorerMapResizeObserver.observe(mapElement);
  }
  window.addEventListener("resize", resizeExplorerMap, { passive: true });

  explorerMap.on("load", () => {
    resizeExplorerMap();
    addExplorerRouteLayer();

    addExplorerPlaceMarkers(restaurantsResult?.restaurants, "restaurant");
    addExplorerPlaceMarkers(hotelsResult?.hotels, "hotel");

    const bounds = new maplibregl.LngLatBounds(
      [longitude, latitude],
      [longitude, latitude]
    );

    let validPlaceCount = 0;

    [...(restaurantsResult?.restaurants || []).slice(0, 20),
     ...(hotelsResult?.hotels || []).slice(0, 20)]
      .forEach(item => {
        const lat = Number(item?.latitude);
        const lon = Number(item?.longitude);

        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

        bounds.extend([lon, lat]);
        validPlaceCount += 1;
      });

    if (validPlaceCount) {
      explorerMap.fitBounds(bounds, {
        padding: 55,
        maxZoom: isArea ? 11 : 14,
        duration: 700
      });
    } else if (isArea && destinationContext?.bounds) {
      const areaBounds = destinationContext.bounds;
      const south = Number(areaBounds.south);
      const west = Number(areaBounds.west);
      const north = Number(areaBounds.north);
      const east = Number(areaBounds.east);

      if ([south, west, north, east].every(Number.isFinite)) {
        explorerMap.fitBounds(
          [[west, south], [east, north]],
          { padding: 45, maxZoom: 9, duration: 700 }
        );
      }
    }
  });

  explorerMap.on("click", event => {
    const target = event.originalEvent?.target;
    if (target?.closest?.(".maplibregl-marker")) return;
    explorerActivePopup?.remove();
    explorerActivePopup = null;
  });

  explorerMap.on("error", event => {
    console.error("MapLibre error:", event?.error || event);
  });

  explorerMarker = new maplibregl.Marker({ color: "#2563d9" })
    .setLngLat([longitude, latitude])
    .setPopup(
      new maplibregl.Popup({ offset: 25 }).setHTML(
        `<div class="explorer-popup"><div class="explorer-popup-type">Destination</div><strong>${escapeHtml(destination)}</strong><div class="explorer-popup-source">${escapeHtml(destinationContext?.formatted || "Resolved destination area")}</div></div>`
      )
    )
    .addTo(explorerMap);

  explorerMarker.getElement().addEventListener("click", () => {
    explorerActivePopup?.remove();
    explorerActivePopup = explorerMarker.getPopup();
    explorerMarker.togglePopup();
  });

  const legend = document.createElement("div");
  legend.className = "explorer-map-legend";
  legend.innerHTML = `
    <span><i class="explorer-legend-marker destination"></i>Destination</span>
    <span><i class="explorer-legend-marker restaurant"></i>Restaurants</span>
    <span><i class="explorer-legend-marker hotel"></i>Hotels</span>
  `;
  mapElement.appendChild(legend);
};

const renderExplorerResults = (destination, mapResult, restaurantsResult, hotelsResult) => {
  const coordinates = mapResult?.coordinates || {};
  const destinationContext = mapResult?.destination_context || {};
  const mapProvider = explorerProviderLabel(mapResult);
  const restaurantProvider = explorerProviderLabel(restaurantsResult);
  const hotelProvider = explorerProviderLabel(hotelsResult);
  const providers = [mapProvider, restaurantProvider, hotelProvider].filter(Boolean).join(" • ");

  explorerResults.innerHTML = `<div class="explorer-grid">
    <article class="explorer-card explorer-card--destination">
      <h3>📍 Destination</h3>
      <h4 class="explorer-destination-name">${escapeHtml(destination)}</h4>
      <p class="explorer-meta explorer-destination-details">${coordinates.latitude != null && coordinates.longitude != null
        ? `Latitude: ${escapeHtml(coordinates.latitude)}<br>Longitude: ${escapeHtml(coordinates.longitude)}`
        : "Coordinates unavailable."}</p>
      ${destinationContext.is_area
        ? `<div class="explorer-scope-badge">Area search · ${escapeHtml(destinationContext.place_type || "region")}</div>`
        : ""}
      ${destinationContext.formatted && destinationContext.formatted !== destination
        ? `<p class="explorer-meta explorer-destination-formatted">Resolved: ${escapeHtml(destinationContext.formatted)}</p>`
        : ""}
      ${mapProvider ? `<div class="explorer-provider">${escapeHtml(mapProvider)}</div>` : ""}
    </article>
    <article class="explorer-card">
      <h3>🍴 Restaurants</h3>
      ${renderExplorerList(restaurantsResult?.restaurants, "restaurants")}
      ${restaurantProvider ? `<div class="explorer-provider">${escapeHtml(restaurantProvider)}</div>` : ""}
    </article>
    <article class="explorer-card">
      <h3>🏨 Hotels</h3>
      ${renderExplorerList(hotelsResult?.hotels, "hotels")}
      ${hotelProvider ? `<div class="explorer-provider">${escapeHtml(hotelProvider)}</div>` : ""}
    </article>
  </div>
  ${providers ? `<p class="explorer-meta mt-3 mb-0">Provider status: ${escapeHtml(providers)}</p>` : ""}`;

  renderExplorerMap(destination, coordinates, restaurantsResult, hotelsResult, destinationContext);
  bindExplorerListInteractions();
};

byId("travelExplorerForm").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = byId("travelExplorerButton");
  const destination = byId("explorerDestination").value.trim();
  const originalText = button.innerHTML;

  if (!destination) return;

  button.disabled = true;
  button.textContent = "Exploring...";

  // Clear the previous route immediately, before the new API requests finish.
  // This prevents a stale distance/time summary from being associated with
  // the destination currently being searched.
  resetExplorerRouteState();

  explorerStatus.className = "explorer-status loading";
  explorerStatus.textContent = `Finding live travel information for ${destination}...`;
  explorerResults.innerHTML = '<div class="explorer-empty"><h3>Loading destination data...</h3><p>Checking location, restaurants and hotels.</p></div>';

  const [mapResult, restaurantsResult, hotelsResult] = await Promise.allSettled([
    api(`/api/maps?destination=${encodeURIComponent(destination)}`),
    api(`/api/restaurants?destination=${encodeURIComponent(destination)}`),
    api(`/api/hotels?destination=${encodeURIComponent(destination)}`)
  ]);

  const mapValue = mapResult.status === "fulfilled" ? mapResult.value : null;
  const restaurantsValue = restaurantsResult.status === "fulfilled" ? restaurantsResult.value : null;
  const hotelsValue = hotelsResult.status === "fulfilled" ? hotelsResult.value : null;
  const failures = [
    mapResult.status === "rejected" ? ["Location", mapResult.reason] : null,
    restaurantsResult.status === "rejected" ? ["Restaurants", restaurantsResult.reason] : null,
    hotelsResult.status === "rejected" ? ["Hotels", hotelsResult.reason] : null
  ].filter(Boolean);

  renderExplorerResults(destination, mapValue, restaurantsValue, hotelsValue);

  if (failures.length === 3) {
    explorerStatus.className = "explorer-status error";
    explorerStatus.textContent = "Could not load destination data. Please try again.";
  } else if (failures.length) {
    explorerStatus.className = "explorer-status error";
    explorerStatus.textContent = `${failures.map(item => item[0]).join(", ")} could not be loaded. Other results are shown.`;
    failures.forEach(([title, error]) => {
      explorerResults.insertAdjacentHTML("beforeend", renderExplorerError(title, error));
    });
  } else {
    const hasCoordinates = Number.isFinite(Number(mapValue?.coordinates?.latitude))
      && Number.isFinite(Number(mapValue?.coordinates?.longitude));
    const hasPlaces = Boolean((restaurantsValue?.restaurants || []).length || (hotelsValue?.hotels || []).length);
    explorerStatus.className = hasCoordinates && hasPlaces ? "explorer-status success" : "explorer-status error";
    explorerStatus.textContent = hasCoordinates && hasPlaces
      ? `Destination data loaded for ${destination}.`
      : hasCoordinates
        ? `Found ${destination}, but no restaurants or hotels were returned. Check provider status below or try a nearby city.`
        : `Could not resolve ${destination}. Check the provider status below and try a more specific destination.`;
  }

  button.disabled = false;
  button.innerHTML = originalText;
});


async function loadKnowledgeStatus() {
  try {
    const status = await api("/api/knowledge/status");
    if (status.ready) {
      uploadStatus.textContent = "Gemini, LangChain and FAISS are ready. Upload a tourism document to add grounded local knowledge.";
      uploadStatus.className = "upload-status success";
    } else if (status.gemini_configured) {
      uploadStatus.textContent = "Gemini key found, but AI packages are missing. Run: .\\venv\\Scripts\\python.exe -m pip install -r requirements.txt";
      uploadStatus.className = "upload-status error";
    } else {
      uploadStatus.textContent = "Add GEMINI_API_KEY to .env and restart the app to enable AI answers and document uploads.";
      uploadStatus.className = "upload-status";
    }
  } catch (_) { uploadStatus.textContent = "Start the FastAPI server to use the AI knowledge base."; uploadStatus.className = "upload-status error"; }
}

byId("knowledgeForm").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const file = byId("knowledgeFile").files[0];
  if (!file) return;
  button.disabled = true; button.textContent = "Adding knowledge...";
  uploadStatus.textContent = `Uploading ${file.name}...`; uploadStatus.className = "upload-status";
  try {
    const formData = new FormData(); formData.append("file", file);
    const response = await fetch("/api/knowledge/upload", { method: "POST", headers: authHeaders(), body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Upload failed.");
    uploadStatus.textContent = `${payload.filename} added successfully (${payload.chunks_added} knowledge sections). Ask the travel assistant a question now.`;
    uploadStatus.className = "upload-status success"; form.reset();
  } catch (error) { uploadStatus.textContent = error.message; uploadStatus.className = "upload-status error"; }
  finally { button.disabled = false; button.textContent = "Add to AI knowledge base"; }
});

byId("expenseForm").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector("button[type='submit'], button:not([type])");
  if (submitButton) submitButton.disabled = true;
  try {
    await api("/api/expenses", {
      method: "POST",
      body: JSON.stringify({
        title: byId("expenseTitle").value.trim(),
        amount: Number(byId("expenseAmount").value),
        category: "General",
        destination: "Current trip"
      })
    });
    form.reset();
    await loadExpenses();
  } catch (error) {
    byId("expenseList").textContent = error.message;
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
});

byId("chatForm").addEventListener("submit", async event => {
  event.preventDefault();
  const answer = byId("chatAnswer"); answer.textContent = "Thinking...";
  if (!getToken()) {
    answer.textContent = "Please sign in first. Your JWT will be sent securely with this AI request.";
    bootstrap.Modal.getOrCreateInstance(byId("loginModal")).show();
    return;
  }
  try {
    const response = await api("/api/chat", { method: "POST", body: JSON.stringify({ question: byId("question").value }) });
    // Render Markdown only through DOMPurify. If either library is unavailable,
    // fall back to escaped plain text rather than inserting untrusted HTML.
    const rawMarkdown = String(response.answer ?? "");
    const renderedAnswer = (window.marked?.parse && window.DOMPurify?.sanitize)
      ? window.DOMPurify.sanitize(window.marked.parse(rawMarkdown, { breaks: true, gfm: true }))
      : `<p>${escapeHtml(rawMarkdown).replace(/\r?\n/g, "<br>")}</p>`;
    const sourceTypeLabels = {
      private_knowledge: "Project knowledge",
      web_travel: "Gemini + Google Search",
      global_travel: "Gemini general travel knowledge",
      none: "No source available"
    };
    const sourceType = sourceTypeLabels[response.source_type] || "Travel assistant";
    const sources = response.sources?.length
      ? `<small class="answer-sources">Source: ${escapeHtml(response.sources.join(", "))}</small>`
      : "";
    answer.innerHTML = `<div class="chat-answer-markdown">${renderedAnswer}</div><small class="answer-source-type">${escapeHtml(sourceType)}</small>${sources}`;
  } catch (error) { answer.textContent = error.message; }
});

const mediaPreview = byId("mediaPreview");
byId("storyMedia").addEventListener("change", event => {
  const files = Array.from(event.target.files || []);
  mediaPreview.innerHTML = "";
  if (!files.length) return;
  if (files.length > 10) {
    event.target.value = "";
    mediaPreview.textContent = "You can select up to 10 files.";
    return;
  }
  files.forEach(file => {
    const source = URL.createObjectURL(file);
    if (file.type.startsWith("image/")) mediaPreview.insertAdjacentHTML("beforeend", `<img src="${source}" alt="Selected travel memory">`);
    else if (file.type.startsWith("audio/")) mediaPreview.insertAdjacentHTML("beforeend", `<audio controls src="${source}"></audio>`);
    else if (file.type.startsWith("video/")) mediaPreview.insertAdjacentHTML("beforeend", `<video controls src="${source}"></video>`);
  });
});

byId("storyForm").addEventListener("submit", async event => {
  event.preventDefault();
  if (!getToken()) {
    bootstrap.Modal.getOrCreateInstance(byId("loginModal")).show();
    return;
  }

  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const status = byId("storyUploadStatus");
  const originalButtonText = button.textContent;
  button.disabled = true;
  status.className = "upload-status";
  status.textContent = "Preparing your story...";

  try {
    let mediaItems = [];
    const files = Array.from(byId("storyMedia").files || []);

    if (files.length > 10) {
      throw new Error("You can select up to 10 media files.");
    }

    // Upload media first. The JSON story is created only after all media uploads succeed.
    if (files.length) {
      status.textContent = `Uploading ${files.length} media file${files.length > 1 ? "s" : ""}...`;
      button.textContent = "Uploading...";
      const formData = new FormData();
      files.forEach(file => formData.append("files", file));
      const response = await fetch("/api/stories/media", {
        method: "POST",
        headers: authHeaders(),
        body: formData
      });
      let payload = {};
      try { payload = await response.json(); } catch (_) {}
      if (!response.ok) {
        throw new Error(payload.detail || `Media upload failed (${response.status}).`);
      }
      mediaItems = payload.media_items || [];
    }

    status.textContent = "Publishing your story...";
    button.textContent = "Publishing...";
    const story = await api("/api/stories", {
      method: "POST",
      body: JSON.stringify({
        author: byId("author").value.trim(),
        destination: byId("storyDestination").value.trim(),
        title: byId("storyTitle").value.trim(),
        content: byId("storyContent").value.trim(),
        media_items: mediaItems
      })
    });

    // Refresh the community feed before closing the modal so the new story is visible immediately.
    await loadStories();
    form.reset();
    mediaPreview.innerHTML = "";
    status.className = "upload-status success";
    status.textContent = "Story published successfully!";

    setTimeout(() => {
      const modal = bootstrap.Modal.getInstance(byId("storyModal"));
      if (modal) modal.hide();
      status.textContent = "";
      status.className = "upload-status";
    }, 700);
  } catch (error) {
    console.error("Story publish error:", error);
    status.className = "upload-status error";
    status.textContent = error.message || "Could not publish the story.";
  } finally {
    button.disabled = false;
    button.textContent = originalButtonText;
  }
});

async function loadExpenses() {
  try { const data = await api("/api/expenses"); byId("expenseList").innerHTML = `<strong>Total spent: ${money(data.total)}</strong>${data.items.map(item => `<div class="d-flex justify-content-between border-top pt-2 mt-2"><span>${escapeHtml(item.title)}</span><span>${money(item.amount)}</span></div>`).join("")}`; } catch (_) { byId("expenseList").innerHTML = '<span class="text-muted">Add an expense to start tracking your trip budget.</span>'; }
}

let communityStories = [];

function renderCommunityStories() {
  const container = byId("stories");
  const search = (byId("storySearch")?.value || "").trim().toLocaleLowerCase();
  const destination = byId("storyDestinationFilter")?.value || "";
  const filtered = communityStories.filter(item => {
    const searchable = [item.destination, item.title, item.content, item.author].filter(Boolean).join(" ").toLocaleLowerCase();
    return (!search || searchable.includes(search)) && (!destination || item.destination === destination);
  });
  const count = byId("storyCount");
  if (count) count.textContent = `${filtered.length} ${filtered.length === 1 ? "story" : "stories"}`;

  if (!filtered.length) {
    container.innerHTML = communityStories.length
      ? '<div class="community-empty"><span class="community-empty-icon">⌕</span><h3>No matching stories</h3><p>Try another destination or search term.</p><button type="button" class="btn btn-outline-primary btn-sm" id="clearStoryFilters">Clear filters</button></div>'
      : '<div class="community-empty"><span class="community-empty-icon">✦</span><h3>The journey starts here</h3><p>Be the first to share a destination, a helpful tip, or a favourite travel memory.</p></div>';
    return;
  }

  container.innerHTML = filtered.map((item, index) => {
    const mediaItems = item.media_items?.length ? item.media_items : (item.media_url ? [{ media_url: item.media_url, media_type: item.media_type }] : []);
    const media = mediaItems.map((mediaItem, mediaIndex) => {
      if (mediaItem.media_type === "image") return `<img class="story-media ${mediaIndex === 0 ? "story-cover" : "story-extra-image"}" src="${escapeHtml(mediaItem.media_url)}" alt="Travel memory from ${escapeHtml(item.destination)}" loading="lazy">`;
      if (mediaItem.media_type === "audio") return `<audio class="story-media story-audio" controls preload="none" src="${escapeHtml(mediaItem.media_url)}" aria-label="Audio travel memory"></audio>`;
      return `<video class="story-media story-video" controls preload="metadata" src="${escapeHtml(mediaItem.media_url)}" aria-label="Video travel memory"></video>`;
    }).join("");
    const content = escapeHtml(item.content || "");
    const showMore = (item.content || "").length > 210;
    return `<article class="story-card">
      <div class="story-card-media">${media || '<div class="story-cover-placeholder"><span aria-hidden="true">✦</span><small>Travel memory</small></div>'}</div>
      <div class="story-card-body">
        <div class="story-card-meta"><span class="story-destination"><span aria-hidden="true">⌖</span> ${escapeHtml(item.destination)}</span><span class="story-community-label">COMMUNITY STORY</span></div>
        <h3 class="story-card-title">${escapeHtml(item.title)}</h3>
        <p class="story-card-content ${showMore ? "is-clamped" : ""}" data-story-content="${index}">${content}</p>
        ${showMore ? `<button class="story-read-more" type="button" data-story-toggle="${index}" aria-expanded="false">Read full story <span aria-hidden="true">↓</span></button>` : ""}
        <div class="story-card-footer"><span class="story-author-avatar" aria-hidden="true">${escapeHtml((item.author || "T").trim().charAt(0).toUpperCase())}</span><span class="story-author"><small>Shared by</small><strong>${escapeHtml(item.author || "Traveller")}</strong></span><span class="story-footer-mark" aria-hidden="true">✦</span></div>
      </div>
    </article>`;
  }).join("");
}

async function loadStories() {
  try {
    const data = await api("/api/stories");
    communityStories = Array.isArray(data) ? data : [];
    const filter = byId("storyDestinationFilter");
    if (filter) {
      const current = filter.value;
      const destinations = [...new Set(communityStories.map(item => (item.destination || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
      filter.innerHTML = '<option value="">All destinations</option>' + destinations.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
      if (destinations.includes(current)) filter.value = current;
    }
    renderCommunityStories();
  } catch (_) {
    communityStories = [];
    byId("stories").innerHTML = '<div class="community-empty"><span class="community-empty-icon">✦</span><h3>Sign in to explore stories</h3><p>Sign in to see travel experiences shared by the VoyageAI community.</p></div>';
    const count = byId("storyCount");
    if (count) count.textContent = "Community feed";
  }
}

byId("storySearch")?.addEventListener("input", renderCommunityStories);
byId("storyDestinationFilter")?.addEventListener("change", renderCommunityStories);
byId("stories")?.addEventListener("click", event => {
  const toggle = event.target.closest("[data-story-toggle]");
  if (toggle) {
    const paragraph = byId("stories").querySelector(`[data-story-content="${toggle.dataset.storyToggle}"]`);
    if (!paragraph) return;
    const expanded = paragraph.classList.toggle("is-expanded");
    paragraph.classList.toggle("is-clamped", !expanded);
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.innerHTML = expanded ? 'Show less <span aria-hidden="true">↑</span>' : 'Read full story <span aria-hidden="true">↓</span>';
    return;
  }
  if (event.target.closest("#clearStoryFilters")) {
    byId("storySearch").value = "";
    byId("storyDestinationFilter").value = "";
    renderCommunityStories();
  }
});

loadExpenses();
loadStories();
loadSavedItineraries();
loadKnowledgeStatus();
updateAuthUi();
