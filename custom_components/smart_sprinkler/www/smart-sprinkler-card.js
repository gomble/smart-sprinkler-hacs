/**
 * Smart Sprinkler Card — Lovelace custom card
 * Version: 1.1.0
 *
 * No YAML zone config needed — zones are auto-discovered from the HA entity registry.
 * Only required config: entity (the status sensor, e.g. sensor.my_garden_status)
 */

const CARD_VERSION = "1.1.3";

const STATUS_COLORS = {
  idle:      "#4caf50",
  waiting:   "#ff9800",
  running:   "#2196f3",
  stopping:  "#ff9800",
  rain_delay:"#9c27b0",
  suspended: "#607d8b",
  error:     "#f44336",
};

// ─────────────────────────────────────────────────────────────────────────────
// Main card
// ─────────────────────────────────────────────────────────────────────────────

class SmartSprinklerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config  = {};
    this._hass    = null;
    this._built   = false;          // full DOM built yet?
    this._pending = {};             // optimistic zone states: {zoneId: "on"|"off"}
  }

  // ── HA lifecycle ──────────────────────────────────────────────────────────

  setConfig(config) {
    // entity is optional — auto-detected from hass on first render
    this._config = { title: "Smart Sprinkler", ...config };
    this._built = false;
    this._buildDOM();
  }

  set hass(hass) {
    this._hass = hass;
    // Auto-detect entity if not set yet
    if (!this._config.entity) {
      const found = this._autoDetectStatusEntity();
      if (found) this._config = { ...this._config, entity: found };
    }
    if (!this._built) {
      this._buildDOM();
    } else {
      this._patch();
    }
  }

  // Find the first smart_sprinkler status sensor in the registry
  _autoDetectStatusEntity() {
    if (!this._hass) return null;
    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};

    // Look for entities from smart_sprinkler platform that are sensors with a status-like state
    const STATUS_STATES = new Set(["idle","waiting","running","stopping","rain_delay","suspended","error"]);

    for (const [id, entry] of Object.entries(entities)) {
      if (entry.platform === "smart_sprinkler" && id.startsWith("sensor.")) {
        const state = states[id]?.state;
        if (STATUS_STATES.has(state)) return id;
      }
    }

    // Broader fallback: any sensor whose state is a known status value
    for (const [id, s] of Object.entries(states)) {
      if (id.startsWith("sensor.") && STATUS_STATES.has(s.state) &&
          s.attributes.active_zones !== undefined) {
        return id;
      }
    }
    return null;
  }

  getCardSize() {
    return 3 + this._discoverZones().length;
  }

  // ── Static card registration ──────────────────────────────────────────────

  static getConfigElement() {
    return document.createElement("smart-sprinkler-card-editor");
  }

  static getStubConfig(hass) {
    // Try to auto-detect a status sensor when card is added from picker
    const entities = hass?.entities || {};
    const states   = hass?.states  || {};
    const STATUS_STATES = new Set(["idle","waiting","running","stopping","rain_delay","suspended","error"]);

    for (const [id, entry] of Object.entries(entities)) {
      if (entry.platform === "smart_sprinkler" && id.startsWith("sensor.")) {
        if (STATUS_STATES.has(states[id]?.state)) return { entity: id, title: "Smart Sprinkler" };
      }
    }
    return { entity: "", title: "Smart Sprinkler" };
  }

  // ── Zone discovery ────────────────────────────────────────────────────────

  _discoverZones() {
    if (!this._hass) return [];

    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};

    // Find the device_id of the configured status sensor
    const statusEntry = entities[this._config.entity];
    const deviceId    = statusEntry?.device_id;

    let candidates;
    if (deviceId) {
      // All switches on the same device
      candidates = Object.values(entities)
        .filter(e => e.device_id === deviceId && e.entity_id.startsWith("switch."));
    } else {
      // Fallback: any switch with a zone_id attribute (any controller)
      candidates = Object.values(entities)
        .filter(e => e.platform === "smart_sprinkler" && e.entity_id.startsWith("switch."));
    }

    return candidates
      .filter(e => states[e.entity_id]?.attributes?.zone_id)
      .map(e => {
        const s    = states[e.entity_id];
        const attr = s.attributes;
        return {
          zone_id:          attr.zone_id,
          name:             attr.friendly_name || e.entity_id,
          entity_id:        e.entity_id,
          is_on:            s.state === "on",
          remaining_seconds: attr.remaining_seconds || 0,
          water_time_today: attr.water_time_today_seconds || 0,
          default_duration: attr.default_duration_seconds || 600,
          enabled:          attr.enabled !== false,
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  _statusState() {
    return this._hass?.states?.[this._config.entity] ?? null;
  }

  _findAllStatusCandidates() {
    if (!this._hass) return [];
    const STATUS_STATES = new Set(["idle","waiting","running","stopping","rain_delay","suspended","error"]);
    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};
    const results  = [];

    // Platform-based (most reliable)
    for (const [id, entry] of Object.entries(entities)) {
      if (entry.platform === "smart_sprinkler" && id.startsWith("sensor.")) {
        if (STATUS_STATES.has(states[id]?.state)) results.push(id);
      }
    }
    // Attribute-based fallback (works even without entity registry access)
    if (results.length === 0) {
      for (const [id, s] of Object.entries(states)) {
        if (id.startsWith("sensor.") && STATUS_STATES.has(s.state) &&
            s.attributes.active_zones !== undefined) {
          results.push(id);
        }
      }
    }
    return results;
  }

  _fmt(seconds) {
    if (!seconds || seconds <= 0) return "—";
    const m = Math.floor(seconds / 60), s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  _fmtDate(iso) {
    if (!iso) return "Never";
    try {
      return new Date(iso).toLocaleString(undefined, { month:"short", day:"numeric", hour:"2-digit", minute:"2-digit" });
    } catch { return iso; }
  }

  _svc(domain, service, data) {
    this._hass?.callService(domain, service, data);
  }

  // ── Optimistic click handlers ─────────────────────────────────────────────

  _onRun(zone) {
    this._pending[zone.zone_id] = "on";
    this._patch();
    const overrides = this._config.zone_durations || {};
    const duration  = overrides[zone.zone_id] || zone.default_duration;
    this._svc("smart_sprinkler", "start_zone", {
      zone_id:  zone.zone_id,
      duration: duration,
    });
    // Clear optimistic state after 5 s (HA will have confirmed by then)
    setTimeout(() => { delete this._pending[zone.zone_id]; this._patch(); }, 5000);
  }

  _onStop(zone) {
    this._pending[zone.zone_id] = "off";
    this._patch();
    this._svc("smart_sprinkler", "stop_zone", { zone_id: zone.zone_id });
    setTimeout(() => { delete this._pending[zone.zone_id]; this._patch(); }, 5000);
  }

  _onStopAll() {
    this._discoverZones().forEach(z => { this._pending[z.zone_id] = "off"; });
    this._patch();
    this._svc("smart_sprinkler", "stop_all", {});
    setTimeout(() => { this._pending = {}; this._patch(); }, 5000);
  }

  // ── Full DOM build (once) ─────────────────────────────────────────────────

  _buildDOM() {
    if (!this._hass) return;

    const statusEnt = this._statusState();
    if (!statusEnt) {
      // Build a helpful selector screen showing all candidate entities
      const candidates = this._findAllStatusCandidates();
      const rows = candidates.length
        ? candidates.map(id => `
            <div class="candidate" data-entity="${id}">
              <span>${id}</span>
              <span class="cand-state">${this._hass.states[id]?.state ?? ""}</span>
            </div>`).join("")
        : `<div style="color:var(--secondary-text-color);font-size:0.85em">
             No Smart Sprinkler status sensors found. Make sure the integration is loaded.
           </div>`;

      this.shadowRoot.innerHTML = `
        <style>
          ha-card { padding: 16px; }
          h3 { margin: 0 0 10px; font-size: 1em; }
          .candidate {
            display: flex; justify-content: space-between; align-items: center;
            padding: 9px 12px; border-radius: 8px; margin-bottom: 6px;
            background: var(--secondary-background-color, #f5f5f5);
            cursor: pointer; font-size: 0.88em;
          }
          .candidate:hover { background: var(--primary-color); color: #fff; }
          .candidate:hover .cand-state { color: rgba(255,255,255,0.7); }
          .cand-state { font-size: 0.82em; color: var(--secondary-text-color); }
          p { font-size: 0.82em; color: var(--secondary-text-color); margin: 0 0 12px; }
        </style>
        <ha-card>
          <h3>Smart Sprinkler — Select status sensor</h3>
          <p>Click the entity to use for this card, or set it via the visual editor (pencil icon).</p>
          ${rows}
        </ha-card>`;

      this.shadowRoot.querySelectorAll(".candidate").forEach(el => {
        el.addEventListener("click", () => {
          this._config = { ...this._config, entity: el.dataset.entity };
          this._built = false;
          this._buildDOM();
          // Persist the selection via config-changed event
          this.dispatchEvent(new CustomEvent("config-changed", {
            detail: { config: this._config }, bubbles: true, composed: true,
          }));
        });
      });
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }

        ha-card { padding: 0; overflow: hidden; border-radius: var(--ha-card-border-radius, 12px); }

        .card-header {
          display: flex; align-items: center; gap: 10px;
          padding: 14px 16px 10px;
          background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 50%, #388e3c 100%);
          color: #fff;
        }
        .header-icon { --mdc-icon-size: 22px; color: #a5d6a7; flex-shrink: 0; }
        .title       { font-size: 1.05em; font-weight: 600; flex: 1; }

        .status-badge {
          display: flex; align-items: center; gap: 5px;
          background: rgba(255,255,255,0.15); border-radius: 20px;
          padding: 3px 10px; font-size: 0.78em; text-transform: capitalize;
        }
        .status-dot {
          width: 7px; height: 7px; border-radius: 50%;
          flex-shrink: 0;
        }

        .btn-stop-all {
          display: none; align-items: center; gap: 4px;
          background: rgba(244,67,54,0.85); color: #fff;
          border: none; border-radius: 8px; padding: 4px 10px;
          cursor: pointer; font-size: 0.78em;
          --mdc-icon-size: 15px;
        }
        .btn-stop-all.visible { display: flex; }
        .btn-stop-all:active  { background: rgba(198,40,40,0.95); }

        .banner {
          display: flex; align-items: center; gap: 8px;
          padding: 7px 14px; font-size: 0.81em; font-weight: 500;
          --mdc-icon-size: 18px;
        }
        .banner.rain    { background: #ede7f6; color: #4527a0; }
        .banner.weather { background: #fff3e0; color: #e65100; }
        .banner.hidden  { display: none; }

        .zones-container { padding: 8px; display: flex; flex-direction: column; gap: 6px; }

        .zone-row {
          display: flex; align-items: center; gap: 10px;
          padding: 10px 12px; border-radius: 10px;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border: 1px solid var(--divider-color, #e0e0e0);
          transition: border-color 0.2s, background 0.2s;
        }
        .zone-row.active { border-color: #2196f3; background: rgba(33,150,243,0.05); }

        .zone-icon { --mdc-icon-size: 20px; color: var(--primary-color); flex-shrink: 0; }
        .zone-icon.active { color: #2196f3; }

        .zone-info { flex: 1; min-width: 0; }
        .zone-name { font-weight: 500; font-size: 0.93em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .zone-meta { font-size: 0.77em; color: var(--secondary-text-color); margin-top: 2px; }

        .zone-progress {
          width: 100%; height: 3px;
          background: var(--divider-color, #e0e0e0); border-radius: 2px;
          margin-top: 6px; overflow: hidden; display: none;
        }
        .zone-progress.visible { display: block; }
        .zone-progress-bar { height: 100%; background: #2196f3; border-radius: 2px; transition: width 1s linear; }

        .zone-actions { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }

        .btn {
          display: inline-flex; align-items: center; gap: 5px;
          border: none; border-radius: 8px; padding: 5px 12px;
          cursor: pointer; font-size: 0.82em; font-family: inherit;
          white-space: nowrap; line-height: 1;
          --mdc-icon-size: 15px;
          transition: filter 0.1s, transform 0.1s;
        }
        .btn:active { filter: brightness(0.85); transform: scale(0.96); }

        .btn-run  { background: var(--primary-color, #03a9f4); color: #fff; }
        .btn-stop { background: #ef5350; color: #fff; }
      </style>

      <ha-card>
        <div class="card-header">
          <ha-icon class="header-icon" icon="mdi:sprinkler-variant"></ha-icon>
          <span class="title">${this._config.title}</span>
          <div class="status-badge">
            <div class="status-dot" id="statusDot"></div>
            <span id="statusText"></span>
          </div>
          <button class="btn-stop-all" id="stopAllBtn">
            <ha-icon icon="mdi:stop-circle"></ha-icon>Stop All
          </button>
        </div>

        <div class="banner rain hidden"   id="rainBanner">
          <ha-icon icon="mdi:weather-rainy"></ha-icon>
          <span id="rainBannerText"></span>
        </div>
        <div class="banner weather hidden" id="weatherBanner">
          <ha-icon icon="mdi:weather-cloudy-alert"></ha-icon>
          <span id="weatherBannerText"></span>
        </div>

        <div class="zones-container" id="zonesContainer"></div>
      </ha-card>
    `;

    // Stop-All button — event delegation safe, only attached once
    this.shadowRoot.getElementById("stopAllBtn")
      .addEventListener("click", () => this._onStopAll());

    // Event delegation for zone buttons (survives zone row re-renders)
    this.shadowRoot.getElementById("zonesContainer")
      .addEventListener("click", e => {
        const runBtn  = e.target.closest("[data-action='run']");
        const stopBtn = e.target.closest("[data-action='stop']");
        if (runBtn)  this._onRun( JSON.parse(runBtn.dataset.zone));
        if (stopBtn) this._onStop(JSON.parse(stopBtn.dataset.zone));
      });

    this._built = true;
    this._patch();
  }

  // ── Patch — update only dynamic parts ────────────────────────────────────

  _patch() {
    if (!this._built || !this._hass) return;

    const statusEnt = this._statusState();
    if (!statusEnt) return;

    const status     = statusEnt.state ?? "idle";
    const attrs      = statusEnt.attributes ?? {};
    const color      = STATUS_COLORS[status] ?? "#9e9e9e";
    const anyRunning = ["waiting","running","stopping"].includes(status);

    // Header
    const dot = this.shadowRoot.getElementById("statusDot");
    if (dot) { dot.style.background = color; dot.style.boxShadow = `0 0 5px ${color}`; }
    const txt = this.shadowRoot.getElementById("statusText");
    if (txt) txt.textContent = status.replace(/_/g, " ");
    const stopAll = this.shadowRoot.getElementById("stopAllBtn");
    if (stopAll) stopAll.classList.toggle("visible", anyRunning);

    // Banners
    const rainBanner = this.shadowRoot.getElementById("rainBanner");
    const rainTxt    = this.shadowRoot.getElementById("rainBannerText");
    if (rainBanner && attrs.rain_delay_until) {
      rainBanner.classList.remove("hidden");
      rainTxt.textContent = `Rain delay until ${this._fmtDate(attrs.rain_delay_until)}`;
    } else if (rainBanner) {
      rainBanner.classList.add("hidden");
    }

    const wxBanner = this.shadowRoot.getElementById("weatherBanner");
    const wxTxt    = this.shadowRoot.getElementById("weatherBannerText");
    if (wxBanner && attrs.weather_skip_reason) {
      wxBanner.classList.remove("hidden");
      wxTxt.textContent = `Skipped: ${attrs.weather_skip_reason}`;
    } else if (wxBanner) {
      wxBanner.classList.add("hidden");
    }

    // Zones — rebuild zone rows (lightweight, no listeners attached inline)
    const container = this.shadowRoot.getElementById("zonesContainer");
    if (!container) return;

    const zones = this._discoverZones();
    if (zones.length === 0) {
      container.innerHTML =
        `<div style="padding:12px;font-size:0.85em;color:var(--secondary-text-color)">
          No zones found. Make sure the Smart Sprinkler integration is loaded.
        </div>`;
      return;
    }

    // Reconcile rows: reuse existing, add/remove as needed
    const existingRows = Array.from(container.children);
    zones.forEach((zone, i) => {
      const isOn = this._pending[zone.zone_id] !== undefined
        ? this._pending[zone.zone_id] === "on"
        : zone.is_on;

      const overrides = this._config.zone_durations || {};
      const duration  = overrides[zone.zone_id] || zone.default_duration;
      const remaining = zone.remaining_seconds;

      const meta = isOn
        ? `Running — ${this._fmt(remaining)} remaining`
        : zone.water_time_today > 0
        ? `Today: ${this._fmt(zone.water_time_today)}`
        : `Duration: ${this._fmt(duration)}`;
      const progress  = (isOn && duration > 0)
        ? Math.max(0, Math.min(100, ((duration - remaining) / duration) * 100))
        : 0;

      // Minimal zone data to embed in button (avoid circular refs)
      const zoneData = JSON.stringify({
        zone_id: zone.zone_id,
        default_duration: zone.default_duration,
      });

      const actionBtn = isOn
        ? `<button class="btn btn-stop" data-action="stop" data-zone='${zoneData}'>
             <ha-icon icon="mdi:stop"></ha-icon>Stop
           </button>`
        : `<button class="btn btn-run" data-action="run" data-zone='${zoneData}'>
             <ha-icon icon="mdi:play"></ha-icon>Run
           </button>`;

      const html = `
        <div class="zone-row ${isOn ? "active" : ""}">
          <ha-icon class="zone-icon ${isOn ? "active" : ""}" icon="${isOn ? "mdi:water" : "mdi:sprinkler"}"></ha-icon>
          <div class="zone-info">
            <div class="zone-name">${zone.name}</div>
            <div class="zone-meta">${meta}</div>
            <div class="zone-progress ${isOn ? "visible" : ""}">
              <div class="zone-progress-bar" style="width:${progress}%"></div>
            </div>
          </div>
          <div class="zone-actions">${actionBtn}</div>
        </div>`;

      if (existingRows[i]) {
        existingRows[i].outerHTML = html;
      } else {
        container.insertAdjacentHTML("beforeend", html);
      }
    });

    // Remove extra rows if zones were deleted
    while (container.children.length > zones.length) {
      container.removeChild(container.lastChild);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Visual editor — build DOM once, patch values on subsequent hass updates
// ─────────────────────────────────────────────────────────────────────────────

class SmartSprinklerCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config   = {};
    this._hass     = null;
    this._built    = false;
  }

  setConfig(config) {
    this._config = { title: "Smart Sprinkler", ...config };
    if (this._built) {
      this._patchValues();
      this._renderZoneRows();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._buildDOM();
    }
  }

  // ── Build once ────────────────────────────────────────────────────────────

  _buildDOM() {
    if (!this._hass) return;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .editor { padding: 4px 0; }
        .section-title {
          font-size: 0.78em; font-weight: 700; text-transform: uppercase;
          letter-spacing: 0.06em; color: var(--secondary-text-color);
          padding: 12px 0 6px; margin: 0;
        }
        .field { margin-bottom: 12px; }
        label  { font-size: 0.88em; font-weight: 500; display: block; margin-bottom: 4px; }
        .hint  { font-size: 0.76em; color: var(--secondary-text-color); margin-top: 3px; }

        select, input[type=text], input[type=number] {
          width: 100%; box-sizing: border-box;
          padding: 8px 10px; border-radius: 8px;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--secondary-background-color, #f5f5f5);
          color: var(--primary-text-color);
          font-size: 0.9em; font-family: inherit;
          appearance: auto;
        }
        select:focus, input:focus {
          outline: 2px solid var(--primary-color); border-color: transparent;
        }

        .zone-rows { display: flex; flex-direction: column; gap: 8px; }
        .zone-row {
          background: var(--secondary-background-color, #f5f5f5);
          border-radius: 10px; padding: 10px 12px;
          display: flex; flex-direction: column; gap: 6px;
        }
        .zone-row-header { font-weight: 600; font-size: 0.88em; }
        .zone-field { display: flex; align-items: center; gap: 8px; }
        .zone-field label { margin: 0; min-width: 100px; font-size: 0.82em; flex-shrink: 0; }
        .zone-field input { flex: 1; padding: 5px 8px; font-size: 0.85em; }
        .no-zones { font-size: 0.82em; color: var(--secondary-text-color); padding: 4px 0; }
      </style>
      <div class="editor">
        <p class="section-title">General</p>

        <div class="field">
          <label>Status Sensor Entity</label>
          <select id="entitySelect">
            <option value="">— loading… —</option>
          </select>
          <div class="hint">Auto-detected from Smart Sprinkler integration</div>
        </div>

        <div class="field">
          <label>Card Title</label>
          <input id="titleInput" type="text" placeholder="Smart Sprinkler">
        </div>

        <p class="section-title">Zone Settings (Duration Override)</p>
        <div class="hint" style="margin-bottom:8px">
          Leave blank to use the default duration set in the integration options.
        </div>
        <div class="zone-rows" id="zoneRows">
          <div class="no-zones">Loading zones…</div>
        </div>
      </div>
    `;

    // Attach listeners ONCE — they read current DOM values, never re-register
    this.shadowRoot.getElementById("entitySelect").addEventListener("change", e => {
      this._config = { ...this._config, entity: e.target.value };
      this._renderZoneRows();
      this._fire();
    });

    this.shadowRoot.getElementById("titleInput").addEventListener("input", e => {
      this._config = { ...this._config, title: e.target.value };
      this._fire();
    });

    // Zone duration changes — event delegation on the container
    this.shadowRoot.getElementById("zoneRows").addEventListener("change", e => {
      const input = e.target.closest("input[data-zone-id]");
      if (!input) return;
      const zoneId = input.dataset.zoneId;
      const val    = parseInt(input.value);
      const overrides = { ...(this._config.zone_durations || {}) };
      if (val > 0) overrides[zoneId] = val;
      else         delete overrides[zoneId];
      this._config = { ...this._config, zone_durations: overrides };
      this._fire();
    });

    this._built = true;
    this._patchValues();
    this._updateEntityOptions();
    this._renderZoneRows();
  }

  // ── Patch values into existing DOM (no innerHTML replacement) ─────────────

  _patchValues() {
    const titleEl = this.shadowRoot.getElementById("titleInput");
    if (titleEl) titleEl.value = this._config.title ?? "Smart Sprinkler";
  }

  _updateEntityOptions() {
    const sel = this.shadowRoot.getElementById("entitySelect");
    if (!sel || !this._hass) return;

    const candidates = this._collectCandidates();
    if (this._config.entity && !candidates.includes(this._config.entity)) {
      candidates.push(this._config.entity);
    }

    // Rebuild options without touching the rest of the DOM
    sel.innerHTML = `<option value="">— select entity —</option>` +
      candidates.map(id =>
        `<option value="${id}" ${id === this._config.entity ? "selected" : ""}>${id}</option>`
      ).join("");
  }

  _renderZoneRows() {
    const container = this.shadowRoot.getElementById("zoneRows");
    if (!container || !this._hass) return;

    const zones    = this._discoverZones();
    const override = this._config.zone_durations || {};

    if (!zones.length) {
      container.innerHTML = `<div class="no-zones">No zones found yet — make sure the integration is loaded.</div>`;
      return;
    }

    container.innerHTML = zones.map(z => `
      <div class="zone-row">
        <div class="zone-row-header">${z.name}</div>
        <div class="zone-field">
          <label>Duration (s)</label>
          <input type="number" min="60" max="7200" step="60"
            data-zone-id="${z.zone_id}"
            placeholder="${z.default_duration} (default)"
            value="${override[z.zone_id] || ""}">
        </div>
      </div>`
    ).join("");
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  _collectCandidates() {
    const STATUS_STATES = new Set(["idle","waiting","running","stopping","rain_delay","suspended","error"]);
    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};
    const results  = new Set();

    for (const [id, entry] of Object.entries(entities)) {
      if (entry.platform === "smart_sprinkler" && id.startsWith("sensor.") &&
          STATUS_STATES.has(states[id]?.state)) results.add(id);
    }
    if (!results.size) {
      for (const [id, s] of Object.entries(states)) {
        if (id.startsWith("sensor.") && STATUS_STATES.has(s.state) &&
            s.attributes.active_zones !== undefined) results.add(id);
      }
    }
    return [...results];
  }

  _discoverZones() {
    if (!this._hass) return [];
    const entities  = this._hass.entities || {};
    const states    = this._hass.states   || {};
    const entityCfg = this._config.entity;

    const statusEntry = entityCfg ? entities[entityCfg] : null;
    const deviceId    = statusEntry?.device_id;

    let candidates;
    if (deviceId) {
      candidates = Object.values(entities).filter(e =>
        e.device_id === deviceId && e.entity_id.startsWith("switch."));
    } else {
      candidates = Object.values(entities).filter(e =>
        e.platform === "smart_sprinkler" && e.entity_id.startsWith("switch."));
    }

    return candidates
      .filter(e => states[e.entity_id]?.attributes?.zone_id)
      .map(e => ({
        zone_id:          states[e.entity_id].attributes.zone_id,
        name:             states[e.entity_id].attributes.friendly_name || e.entity_id,
        default_duration: states[e.entity_id].attributes.default_duration_seconds || 600,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _fire() {
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: this._config }, bubbles: true, composed: true,
    }));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Registration
// ─────────────────────────────────────────────────────────────────────────────

customElements.define("smart-sprinkler-card",        SmartSprinklerCard);
customElements.define("smart-sprinkler-card-editor", SmartSprinklerCardEditor);

window.customCards = window.customCards ?? [];
window.customCards.push({
  type:             "smart-sprinkler-card",
  name:             "Smart Sprinkler Card",
  description:      "Control and monitor Smart Sprinkler zones — zones auto-discovered, no YAML needed",
  preview:          true,
  documentationURL: "https://github.com/gomble/smart-sprinkler-hacs",
});

console.info(
  `%c SMART-SPRINKLER-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#2e7d32;font-weight:700;padding:2px 6px;border-radius:4px 0 0 4px;",
  "color:#2e7d32;background:#e8f5e9;font-weight:700;padding:2px 6px;border-radius:0 4px 4px 0;"
);
