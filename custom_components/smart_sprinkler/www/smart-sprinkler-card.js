/**
 * Smart Sprinkler Card — Lovelace custom card
 * Version: 1.2.0
 *
 * No YAML zone config needed — zones are auto-discovered from the HA entity registry.
 * Only required config: entity (the status sensor, e.g. sensor.my_garden_status)
 */

const CARD_VERSION = "1.2.0";

const STATUS_COLORS = {
  idle:      "#4caf50",
  waiting:   "#ff9800",
  running:   "#2196f3",
  stopping:  "#ff9800",
  rain_delay:"#9c27b0",
  suspended: "#607d8b",
  error:     "#f44336",
};

const SCHEDULE_MODE_LABELS = {
  daily:     "Daily",
  interval:  "Interval",
  odd_days:  "Odd Days",
  even_days: "Even Days",
  weekdays:  "Weekdays",
  custom:    "Custom",
};

const WEEKDAY_LABELS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const WEEKDAY_KEYS   = ["mon","tue","wed","thu","fri","sat","sun"];

// ─────────────────────────────────────────────────────────────────────────────
// Main card
// ─────────────────────────────────────────────────────────────────────────────

class SmartSprinklerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config  = {};
    this._hass    = null;
    this._built   = false;
    this._pending = {};
    this._expanded = {};  // zone_id → true if schedule section is expanded
  }

  // ── HA lifecycle ──────────────────────────────────────────────────────────

  setConfig(config) {
    this._config = { title: "Smart Sprinkler", ...config };
    this._built = false;
    this._buildDOM();
  }

  set hass(hass) {
    this._hass = hass;
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

  _autoDetectStatusEntity() {
    if (!this._hass) return null;
    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};
    const STATUS_STATES = new Set(["idle","waiting","running","stopping","rain_delay","suspended","error"]);

    for (const [id, entry] of Object.entries(entities)) {
      if (entry.platform === "smart_sprinkler" && id.startsWith("sensor.")) {
        if (STATUS_STATES.has(states[id]?.state)) return id;
      }
    }
    for (const [id, s] of Object.entries(states)) {
      if (id.startsWith("sensor.") && STATUS_STATES.has(s.state) &&
          s.attributes.active_zones !== undefined) return id;
    }
    return null;
  }

  getCardSize() { return 3 + this._discoverZones().length * 2; }

  static getConfigElement() { return document.createElement("smart-sprinkler-card-editor"); }

  static getStubConfig(hass) {
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

  // ── Zone & entity discovery ──────────────────────────────────────────────

  _discoverZones() {
    if (!this._hass) return [];
    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};

    const statusEntry = entities[this._config.entity];
    const deviceId    = statusEntry?.device_id;

    let candidates;
    if (deviceId) {
      candidates = Object.values(entities)
        .filter(e => e.device_id === deviceId && e.entity_id.startsWith("switch."));
    } else {
      candidates = Object.values(entities)
        .filter(e => e.platform === "smart_sprinkler" && e.entity_id.startsWith("switch."));
    }

    return candidates
      .filter(e => states[e.entity_id]?.attributes?.zone_id)
      .map(e => {
        const s    = states[e.entity_id];
        const attr = s.attributes;
        const zoneId = attr.zone_id;
        return {
          zone_id:          zoneId,
          name:             attr.friendly_name || e.entity_id,
          entity_id:        e.entity_id,
          is_on:            s.state === "on",
          remaining_seconds: attr.remaining_seconds || 0,
          water_time_today: attr.water_time_today_seconds || 0,
          default_duration: attr.default_duration_seconds || 600,
          enabled:          attr.enabled !== false,
          last_run:         attr.last_run || null,
          ...this._getScheduleInfo(deviceId, zoneId),
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _getScheduleInfo(deviceId, zoneId) {
    if (!this._hass || !deviceId) return {};
    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};

    let scheduleMode = "daily";
    let startTime = "06:00";
    let weekdays = "";
    let intervalDays = 2;
    let nextRun = null;

    for (const ent of Object.values(entities)) {
      if (ent.device_id !== deviceId) continue;
      const s = states[ent.entity_id];
      if (!s) continue;

      // Schedule mode select
      if (ent.entity_id.includes("schedule_mode") && ent.entity_id.includes(zoneId.substring(0, 6))) {
        scheduleMode = s.state || "daily";
      }
      // Start time
      if (ent.entity_id.includes("start_time") && ent.entity_id.includes(zoneId.substring(0, 6))) {
        startTime = s.state || "06:00";
      }
      // Weekdays
      if (ent.entity_id.includes("weekdays") && ent.entity_id.includes(zoneId.substring(0, 6))) {
        weekdays = s.state || "";
      }
      // Interval days
      if (ent.entity_id.includes("interval_days") && ent.entity_id.includes(zoneId.substring(0, 6))) {
        intervalDays = parseInt(s.state) || 2;
      }
      // Next run sensor
      if (ent.entity_id.includes("next_run") && ent.entity_id.includes(zoneId.substring(0, 6))) {
        nextRun = s.state && s.state !== "unknown" && s.state !== "unavailable" ? s.state : null;
      }
    }

    return { scheduleMode, startTime, weekdays, intervalDays, nextRun };
  }

  _findScheduleEntities(deviceId, zoneId) {
    if (!this._hass || !deviceId) return {};
    const entities = this._hass.entities || {};
    const result = {};
    const prefix = zoneId.substring(0, 6);

    for (const ent of Object.values(entities)) {
      if (ent.device_id !== deviceId) continue;
      if (ent.entity_id.includes("schedule_mode") && ent.entity_id.includes(prefix))
        result.scheduleMode = ent.entity_id;
      if (ent.entity_id.includes("start_time") && ent.entity_id.includes(prefix))
        result.startTime = ent.entity_id;
      if (ent.entity_id.includes("weekdays") && ent.entity_id.includes(prefix))
        result.weekdays = ent.entity_id;
      if (ent.entity_id.includes("interval_days") && ent.entity_id.includes(prefix))
        result.intervalDays = ent.entity_id;
    }
    return result;
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  _statusState() { return this._hass?.states?.[this._config.entity] ?? null; }

  _findAllStatusCandidates() {
    if (!this._hass) return [];
    const STATUS_STATES = new Set(["idle","waiting","running","stopping","rain_delay","suspended","error"]);
    const entities = this._hass.entities || {};
    const states   = this._hass.states  || {};
    const results  = [];
    for (const [id, entry] of Object.entries(entities)) {
      if (entry.platform === "smart_sprinkler" && id.startsWith("sensor.") && STATUS_STATES.has(states[id]?.state))
        results.push(id);
    }
    if (!results.length) {
      for (const [id, s] of Object.entries(states)) {
        if (id.startsWith("sensor.") && STATUS_STATES.has(s.state) && s.attributes.active_zones !== undefined)
          results.push(id);
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
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString(undefined, { month:"short", day:"numeric", hour:"2-digit", minute:"2-digit" });
    } catch { return iso; }
  }

  _fmtTime(timeStr) {
    if (!timeStr) return "06:00";
    return timeStr.substring(0, 5);
  }

  _svc(domain, service, data) { this._hass?.callService(domain, service, data); }

  // ── Optimistic click handlers ─────────────────────────────────────────────

  _onRun(zone) {
    this._pending[zone.zone_id] = "on";
    this._patch();
    const overrides = this._config.zone_durations || {};
    const duration  = overrides[zone.zone_id] || zone.default_duration;
    this._svc("smart_sprinkler", "start_zone", { zone_id: zone.zone_id, duration });
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

  // ── Schedule control handlers ─────────────────────────────────────────────

  _onScheduleChange(zoneId, field, value) {
    const statusEntry = (this._hass.entities || {})[this._config.entity];
    const deviceId = statusEntry?.device_id;
    const ents = this._findScheduleEntities(deviceId, zoneId);

    if (field === "mode" && ents.scheduleMode) {
      this._svc("select", "select_option", { entity_id: ents.scheduleMode, option: value });
    } else if (field === "time" && ents.startTime) {
      this._svc("time", "set_value", { entity_id: ents.startTime, time: value });
    } else if (field === "weekdays" && ents.weekdays) {
      this._svc("select", "select_option", { entity_id: ents.weekdays, option: value });
    } else if (field === "interval" && ents.intervalDays) {
      this._svc("number", "set_value", { entity_id: ents.intervalDays, value: parseFloat(value) });
    }
  }

  // ── Full DOM build (once) ─────────────────────────────────────────────────

  _buildDOM() {
    if (!this._hass) return;

    const statusEnt = this._statusState();
    if (!statusEnt) {
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
        .status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

        .btn-stop-all {
          display: none; align-items: center; gap: 4px;
          background: rgba(244,67,54,0.85); color: #fff;
          border: none; border-radius: 8px; padding: 4px 10px;
          cursor: pointer; font-size: 0.78em; --mdc-icon-size: 15px;
        }
        .btn-stop-all.visible { display: flex; }
        .btn-stop-all:active  { background: rgba(198,40,40,0.95); }

        .info-bar {
          display: flex; gap: 12px; padding: 8px 16px;
          font-size: 0.77em; color: var(--secondary-text-color);
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          flex-wrap: wrap;
        }
        .info-bar .info-item { display: flex; align-items: center; gap: 4px; --mdc-icon-size: 14px; }
        .info-bar.hidden { display: none; }

        .banner {
          display: flex; align-items: center; gap: 8px;
          padding: 7px 14px; font-size: 0.81em; font-weight: 500; --mdc-icon-size: 18px;
        }
        .banner.rain    { background: #ede7f6; color: #4527a0; }
        .banner.weather { background: #fff3e0; color: #e65100; }
        .banner.hidden  { display: none; }

        .zones-container { padding: 8px; display: flex; flex-direction: column; gap: 6px; }

        .zone-card {
          border-radius: 10px;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border: 1px solid var(--divider-color, #e0e0e0);
          transition: border-color 0.2s, background 0.2s;
          overflow: hidden;
        }
        .zone-card.active { border-color: #2196f3; background: rgba(33,150,243,0.03); }

        .zone-main {
          display: flex; align-items: center; gap: 10px;
          padding: 10px 12px;
        }

        .zone-icon { --mdc-icon-size: 20px; color: var(--primary-color); flex-shrink: 0; }
        .zone-icon.active { color: #2196f3; }

        .zone-info { flex: 1; min-width: 0; }
        .zone-name { font-weight: 500; font-size: 0.93em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .zone-meta { font-size: 0.77em; color: var(--secondary-text-color); margin-top: 2px; display: flex; gap: 10px; flex-wrap: wrap; }

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
          white-space: nowrap; line-height: 1; --mdc-icon-size: 15px;
          transition: filter 0.1s, transform 0.1s;
        }
        .btn:active { filter: brightness(0.85); transform: scale(0.96); }
        .btn-run  { background: var(--primary-color, #03a9f4); color: #fff; }
        .btn-stop { background: #ef5350; color: #fff; }

        .btn-schedule-toggle {
          background: none; border: none; padding: 4px; cursor: pointer;
          color: var(--secondary-text-color); --mdc-icon-size: 18px;
          border-radius: 50%; transition: background 0.15s;
        }
        .btn-schedule-toggle:hover { background: var(--secondary-background-color, #f0f0f0); }
        .btn-schedule-toggle.active { color: var(--primary-color); }

        .schedule-panel {
          display: none; padding: 8px 12px 10px; border-top: 1px solid var(--divider-color, #e0e0e0);
          background: var(--secondary-background-color, #fafafa);
        }
        .schedule-panel.open { display: block; }

        .sched-row {
          display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
          font-size: 0.82em;
        }
        .sched-row label { min-width: 65px; color: var(--secondary-text-color); flex-shrink: 0; }
        .sched-row select, .sched-row input {
          padding: 4px 7px; border-radius: 6px;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          font-size: 0.9em; font-family: inherit;
        }
        .sched-row select { appearance: auto; }
        .sched-row input[type=time] { width: 100px; }
        .sched-row input[type=number] { width: 60px; }

        .weekday-chips {
          display: flex; gap: 3px; flex-wrap: wrap;
        }
        .weekday-chip {
          padding: 2px 7px; border-radius: 4px; font-size: 0.78em; cursor: pointer;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          transition: background 0.15s, border-color 0.15s;
          user-select: none;
        }
        .weekday-chip.selected {
          background: var(--primary-color); color: #fff;
          border-color: var(--primary-color);
        }

        .sched-next {
          font-size: 0.76em; color: var(--secondary-text-color);
          margin-top: 4px; padding-top: 4px;
          border-top: 1px dashed var(--divider-color, #e0e0e0);
        }
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

        <div class="info-bar" id="infoBar">
          <div class="info-item" id="infoWaterToday">
            <ha-icon icon="mdi:water-percent"></ha-icon><span></span>
          </div>
          <div class="info-item" id="infoValveDelay" style="display:none">
            <ha-icon icon="mdi:timer-sand"></ha-icon><span></span>
          </div>
          <div class="info-item" id="infoActiveZones" style="display:none">
            <ha-icon icon="mdi:sprinkler"></ha-icon><span></span>
          </div>
        </div>

        <div class="banner rain hidden" id="rainBanner">
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

    this.shadowRoot.getElementById("stopAllBtn")
      .addEventListener("click", () => this._onStopAll());

    const container = this.shadowRoot.getElementById("zonesContainer");
    container.addEventListener("click", e => {
      const runBtn  = e.target.closest("[data-action='run']");
      const stopBtn = e.target.closest("[data-action='stop']");
      const schedBtn = e.target.closest("[data-action='toggle-schedule']");
      const chipBtn  = e.target.closest(".weekday-chip");

      if (runBtn)  this._onRun(JSON.parse(runBtn.dataset.zone));
      if (stopBtn) this._onStop(JSON.parse(stopBtn.dataset.zone));
      if (schedBtn) {
        const zoneId = schedBtn.dataset.zoneId;
        this._expanded[zoneId] = !this._expanded[zoneId];
        this._patch();
      }
      if (chipBtn) {
        const zoneId = chipBtn.dataset.zoneId;
        chipBtn.classList.toggle("selected");
        const panel = chipBtn.closest(".schedule-panel");
        const chips = panel.querySelectorAll(".weekday-chip");
        const selected = [];
        chips.forEach(c => { if (c.classList.contains("selected")) selected.push(c.dataset.day); });
        this._onScheduleChange(zoneId, "weekdays", selected.join(","));
      }
    });

    container.addEventListener("change", e => {
      const target = e.target;
      const zoneId = target.dataset.zoneId;
      if (!zoneId) return;
      const field = target.dataset.field;
      if (field) this._onScheduleChange(zoneId, field, target.value);
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

    // Info bar
    const waterTodayEl = this.shadowRoot.querySelector("#infoWaterToday span");
    if (waterTodayEl) {
      const totalWater = attrs.total_water_time_today || 0;
      waterTodayEl.textContent = `Today: ${this._fmt(totalWater)}`;
    }

    const valveEl = this.shadowRoot.getElementById("infoValveDelay");
    if (valveEl) {
      const vd = attrs.valve_delay_remaining || 0;
      if (vd > 0) {
        valveEl.style.display = "flex";
        valveEl.querySelector("span").textContent = `Valve delay: ${vd}s`;
      } else {
        valveEl.style.display = "none";
      }
    }

    const activeEl = this.shadowRoot.getElementById("infoActiveZones");
    if (activeEl) {
      const active = attrs.active_zones || [];
      if (active.length > 0) {
        activeEl.style.display = "flex";
        activeEl.querySelector("span").textContent = `${active.length} zone${active.length > 1 ? "s" : ""} active`;
      } else {
        activeEl.style.display = "none";
      }
    }

    // Banners
    const rainBanner = this.shadowRoot.getElementById("rainBanner");
    const rainTxt    = this.shadowRoot.getElementById("rainBannerText");
    if (rainBanner && attrs.rain_delay_until) {
      rainBanner.classList.remove("hidden");
      rainTxt.textContent = `Rain delay until ${this._fmtDate(attrs.rain_delay_until)}`;
    } else if (rainBanner) { rainBanner.classList.add("hidden"); }

    const wxBanner = this.shadowRoot.getElementById("weatherBanner");
    const wxTxt    = this.shadowRoot.getElementById("weatherBannerText");
    if (wxBanner && attrs.weather_skip_reason) {
      wxBanner.classList.remove("hidden");
      wxTxt.textContent = `Skipped: ${attrs.weather_skip_reason}`;
    } else if (wxBanner) { wxBanner.classList.add("hidden"); }

    // Zones
    const container = this.shadowRoot.getElementById("zonesContainer");
    if (!container) return;

    const zones = this._discoverZones();
    if (zones.length === 0) {
      container.innerHTML = `<div style="padding:12px;font-size:0.85em;color:var(--secondary-text-color)">
        No zones found. Make sure the Smart Sprinkler integration is loaded.</div>`;
      return;
    }

    zones.forEach((zone, i) => {
      const isOn = this._pending[zone.zone_id] !== undefined
        ? this._pending[zone.zone_id] === "on"
        : zone.is_on;

      const overrides = this._config.zone_durations || {};
      const duration  = overrides[zone.zone_id] || zone.default_duration;
      const remaining = zone.remaining_seconds;
      const progress  = (isOn && duration > 0)
        ? Math.max(0, Math.min(100, ((duration - remaining) / duration) * 100)) : 0;
      const expanded = this._expanded[zone.zone_id] || false;

      const zoneData = JSON.stringify({ zone_id: zone.zone_id, default_duration: zone.default_duration });

      let card = container.children[i];

      if (!card || card.dataset.zoneId !== zone.zone_id) {
        const div = document.createElement("div");
        div.className = "zone-card";
        div.dataset.zoneId = zone.zone_id;
        div.innerHTML = `
          <div class="zone-main">
            <ha-icon class="zone-icon" icon="mdi:sprinkler"></ha-icon>
            <div class="zone-info">
              <div class="zone-name"></div>
              <div class="zone-meta"></div>
              <div class="zone-progress"><div class="zone-progress-bar"></div></div>
            </div>
            <div class="zone-actions">
              <button class="btn-schedule-toggle" data-action="toggle-schedule" data-zone-id="${zone.zone_id}">
                <ha-icon icon="mdi:calendar-clock"></ha-icon>
              </button>
              <button class="btn" data-action="run" data-zone='${zoneData}'>
                <ha-icon icon="mdi:play"></ha-icon><span></span>
              </button>
            </div>
          </div>
          <div class="schedule-panel" data-zone-id="${zone.zone_id}"></div>`;
        if (card) { container.replaceChild(div, card); } else { container.appendChild(div); }
        card = div;
      }

      // Update main row in-place
      card.className = `zone-card ${isOn ? "active" : ""}`;
      const icon = card.querySelector(".zone-icon");
      icon.setAttribute("icon", isOn ? "mdi:water" : "mdi:sprinkler");
      icon.className = `zone-icon ${isOn ? "active" : ""}`;

      card.querySelector(".zone-name").textContent = zone.name;

      // Build meta line
      const metaParts = [];
      if (isOn) {
        metaParts.push(`<span>Running — ${this._fmt(remaining)} left</span>`);
      } else {
        if (zone.water_time_today > 0)
          metaParts.push(`<span>Today: ${this._fmt(zone.water_time_today)}</span>`);
        if (zone.nextRun)
          metaParts.push(`<span>Next: ${this._fmtDate(zone.nextRun)}</span>`);
        else if (zone.scheduleMode)
          metaParts.push(`<span>${SCHEDULE_MODE_LABELS[zone.scheduleMode] || zone.scheduleMode} @ ${this._fmtTime(zone.startTime)}</span>`);
      }
      if (!metaParts.length) metaParts.push(`<span>Duration: ${this._fmt(duration)}</span>`);
      card.querySelector(".zone-meta").innerHTML = metaParts.join("");

      const prog = card.querySelector(".zone-progress");
      prog.className = `zone-progress ${isOn ? "visible" : ""}`;
      card.querySelector(".zone-progress-bar").style.width = `${progress}%`;

      // Action button
      const btn = card.querySelector(".zone-actions .btn[data-action]");
      const btnIsStop = btn.dataset.action === "stop";
      if (isOn !== btnIsStop) {
        btn.dataset.action = isOn ? "stop" : "run";
        btn.dataset.zone   = zoneData;
        btn.className      = `btn ${isOn ? "btn-stop" : "btn-run"}`;
        btn.querySelector("ha-icon").setAttribute("icon", isOn ? "mdi:stop" : "mdi:play");
        btn.querySelector("span").textContent = isOn ? "Stop" : "Run";
      } else { btn.dataset.zone = zoneData; }

      // Schedule toggle button highlight
      const schedToggle = card.querySelector(".btn-schedule-toggle");
      schedToggle.classList.toggle("active", expanded);

      // Schedule panel
      const panel = card.querySelector(".schedule-panel");
      panel.classList.toggle("open", expanded);
      if (expanded) {
        this._renderSchedulePanel(panel, zone);
      }
    });

    while (container.children.length > zones.length) {
      container.removeChild(container.lastChild);
    }
  }

  _renderSchedulePanel(panel, zone) {
    const mode = zone.scheduleMode || "daily";
    const time = this._fmtTime(zone.startTime);
    const weekdays = (zone.weekdays || "").split(",").filter(Boolean);
    const interval = zone.intervalDays || 2;
    const zoneId = zone.zone_id;

    const modeOptions = Object.entries(SCHEDULE_MODE_LABELS)
      .map(([val, lbl]) => `<option value="${val}" ${val === mode ? "selected" : ""}>${lbl}</option>`)
      .join("");

    const weekdayChips = WEEKDAY_KEYS.map((key, idx) =>
      `<span class="weekday-chip ${weekdays.includes(key) ? "selected" : ""}" data-zone-id="${zoneId}" data-day="${key}">${WEEKDAY_LABELS[idx]}</span>`
    ).join("");

    const showWeekdays = ["weekdays", "custom"].includes(mode);
    const showInterval = mode === "interval";

    panel.innerHTML = `
      <div class="sched-row">
        <label>Mode</label>
        <select data-zone-id="${zoneId}" data-field="mode">${modeOptions}</select>
      </div>
      <div class="sched-row">
        <label>Time</label>
        <input type="time" value="${time}" data-zone-id="${zoneId}" data-field="time">
      </div>
      ${showWeekdays ? `<div class="sched-row">
        <label>Days</label>
        <div class="weekday-chips">${weekdayChips}</div>
      </div>` : ""}
      ${showInterval ? `<div class="sched-row">
        <label>Every</label>
        <input type="number" min="1" max="14" value="${interval}" data-zone-id="${zoneId}" data-field="interval"> days
      </div>` : ""}
      ${zone.nextRun ? `<div class="sched-next">Next run: ${this._fmtDate(zone.nextRun)}</div>` : ""}
      ${zone.last_run ? `<div class="sched-next">Last run: ${this._fmtDate(zone.last_run)}</div>` : ""}
    `;
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
    if (!this._built) { this._buildDOM(); }
  }

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
          font-size: 0.9em; font-family: inherit; appearance: auto;
        }
        select:focus, input:focus { outline: 2px solid var(--primary-color); border-color: transparent; }

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
          <select id="entitySelect"><option value="">— loading… —</option></select>
          <div class="hint">Auto-detected from Smart Sprinkler integration</div>
        </div>
        <div class="field">
          <label>Card Title</label>
          <input id="titleInput" type="text" placeholder="Smart Sprinkler">
        </div>
        <p class="section-title">Zone Settings (Duration Override)</p>
        <div class="hint" style="margin-bottom:8px">Leave blank to use the default duration set in the integration options.</div>
        <div class="zone-rows" id="zoneRows"><div class="no-zones">Loading zones…</div></div>
      </div>
    `;

    this.shadowRoot.getElementById("entitySelect").addEventListener("change", e => {
      this._config = { ...this._config, entity: e.target.value };
      this._renderZoneRows();
      this._fire();
    });
    this.shadowRoot.getElementById("titleInput").addEventListener("input", e => {
      this._config = { ...this._config, title: e.target.value };
      this._fire();
    });
    this.shadowRoot.getElementById("zoneRows").addEventListener("change", e => {
      const input = e.target.closest("input[data-zone-id]");
      if (!input) return;
      const overrides = { ...(this._config.zone_durations || {}) };
      const val = parseInt(input.value);
      if (val > 0) overrides[input.dataset.zoneId] = val;
      else delete overrides[input.dataset.zoneId];
      this._config = { ...this._config, zone_durations: overrides };
      this._fire();
    });

    this._built = true;
    this._patchValues();
    this._updateEntityOptions();
    this._renderZoneRows();
  }

  _patchValues() {
    const titleEl = this.shadowRoot.getElementById("titleInput");
    if (titleEl) titleEl.value = this._config.title ?? "Smart Sprinkler";
  }

  _updateEntityOptions() {
    const sel = this.shadowRoot.getElementById("entitySelect");
    if (!sel || !this._hass) return;
    const candidates = this._collectCandidates();
    if (this._config.entity && !candidates.includes(this._config.entity)) candidates.push(this._config.entity);
    sel.innerHTML = `<option value="">— select entity —</option>` +
      candidates.map(id => `<option value="${id}" ${id === this._config.entity ? "selected" : ""}>${id}</option>`).join("");
  }

  _renderZoneRows() {
    const container = this.shadowRoot.getElementById("zoneRows");
    if (!container || !this._hass) return;
    const zones = this._discoverZones();
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
          <input type="number" min="60" max="7200" step="60" data-zone-id="${z.zone_id}"
            placeholder="${z.default_duration} (default)" value="${override[z.zone_id] || ""}">
        </div>
      </div>`).join("");
  }

  _collectCandidates() {
    const STATUS_STATES = new Set(["idle","waiting","running","stopping","rain_delay","suspended","error"]);
    const entities = this._hass.entities || {};
    const states = this._hass.states || {};
    const results = new Set();
    for (const [id, entry] of Object.entries(entities)) {
      if (entry.platform === "smart_sprinkler" && id.startsWith("sensor.") && STATUS_STATES.has(states[id]?.state))
        results.add(id);
    }
    if (!results.size) {
      for (const [id, s] of Object.entries(states)) {
        if (id.startsWith("sensor.") && STATUS_STATES.has(s.state) && s.attributes.active_zones !== undefined)
          results.add(id);
      }
    }
    return [...results];
  }

  _discoverZones() {
    if (!this._hass) return [];
    const entities = this._hass.entities || {};
    const states = this._hass.states || {};
    const statusEntry = this._config.entity ? entities[this._config.entity] : null;
    const deviceId = statusEntry?.device_id;
    let candidates;
    if (deviceId) {
      candidates = Object.values(entities).filter(e => e.device_id === deviceId && e.entity_id.startsWith("switch."));
    } else {
      candidates = Object.values(entities).filter(e => e.platform === "smart_sprinkler" && e.entity_id.startsWith("switch."));
    }
    return candidates
      .filter(e => states[e.entity_id]?.attributes?.zone_id)
      .map(e => ({
        zone_id: states[e.entity_id].attributes.zone_id,
        name: states[e.entity_id].attributes.friendly_name || e.entity_id,
        default_duration: states[e.entity_id].attributes.default_duration_seconds || 600,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _fire() {
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Registration
// ─────────────────────────────────────────────────────────────────────────────

customElements.define("smart-sprinkler-card", SmartSprinklerCard);
customElements.define("smart-sprinkler-card-editor", SmartSprinklerCardEditor);

window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "smart-sprinkler-card",
  name: "Smart Sprinkler Card",
  description: "Control and monitor Smart Sprinkler zones with schedule management — auto-discovered, no YAML needed",
  preview: true,
  documentationURL: "https://github.com/gomble/smart-sprinkler-hacs",
});

console.info(
  `%c SMART-SPRINKLER-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#2e7d32;font-weight:700;padding:2px 6px;border-radius:4px 0 0 4px;",
  "color:#2e7d32;background:#e8f5e9;font-weight:700;padding:2px 6px;border-radius:0 4px 4px 0;"
);
