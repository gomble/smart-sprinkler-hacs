/**
 * Smart Sprinkler Card — Lovelace custom card
 * Version: 1.0.0
 */

const CARD_VERSION = "1.0.0";

const STATUS_COLORS = {
  idle: "#4caf50",
  running: "#2196f3",
  rain_delay: "#9c27b0",
  suspended: "#ff9800",
  error: "#f44336",
};

const STATUS_ICONS = {
  idle: "mdi:sprinkler",
  running: "mdi:sprinkler-variant",
  rain_delay: "mdi:weather-rainy",
  suspended: "mdi:pause-circle",
  error: "mdi:alert-circle",
};

class SmartSprinklerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
  }

  static get properties() {
    return { hass: {}, config: {} };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define a status sensor entity");
    }
    this._config = {
      title: "Smart Sprinkler",
      show_weather_info: true,
      show_water_stats: true,
      compact: false,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _getEntityState(entityId) {
    return this._hass?.states?.[entityId] ?? null;
  }

  _formatSeconds(seconds) {
    if (!seconds || seconds <= 0) return "—";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  _formatDateTime(isoString) {
    if (!isoString) return "Never";
    try {
      const d = new Date(isoString);
      return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  }

  _callService(domain, service, data) {
    this._hass?.callService(domain, service, data);
  }

  _startZone(zoneId, duration) {
    this._callService("smart_sprinkler", "start_zone", {
      zone_id: zoneId,
      duration: duration,
    });
  }

  _stopZone(zoneId) {
    this._callService("smart_sprinkler", "stop_zone", { zone_id: zoneId });
  }

  _stopAll() {
    this._callService("smart_sprinkler", "stop_all", {});
  }

  _render() {
    if (!this._hass || !this._config.entity) return;

    const statusEntity = this._getEntityState(this._config.entity);
    if (!statusEntity) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px;color:var(--error-color)">Entity not found: ${this._config.entity}</div></ha-card>`;
      return;
    }

    const status = statusEntity.state ?? "idle";
    const attrs = statusEntity.attributes ?? {};
    const activeZone = attrs.active_zone ?? null;
    const rainDelayUntil = attrs.rain_delay_until ?? null;
    const weatherSkip = attrs.weather_skip_reason ?? null;
    const statusColor = STATUS_COLORS[status] ?? "#9e9e9e";

    // Collect zone entities from config
    const zones = this._config.zones ?? [];

    const zonesHtml = zones.map((zoneCfg) => this._renderZone(zoneCfg, activeZone)).join("");

    const weatherBanner =
      weatherSkip
        ? `<div class="weather-banner"><ha-icon icon="mdi:weather-cloudy-alert"></ha-icon> Skipped: ${weatherSkip}</div>`
        : "";

    const rainDelayBanner =
      rainDelayUntil
        ? `<div class="rain-delay-banner"><ha-icon icon="mdi:weather-rainy"></ha-icon> Rain delay until ${this._formatDateTime(rainDelayUntil)}</div>`
        : "";

    const waterStats = this._config.show_water_stats && this._config.water_time_entity
      ? this._renderWaterStats()
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card {
          padding: 0;
          overflow: hidden;
          border-radius: var(--ha-card-border-radius, 12px);
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px 16px 8px;
          background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 50%, #388e3c 100%);
          color: #fff;
        }
        .card-header .title { font-size: 1.1em; font-weight: 600; flex: 1; }
        .status-badge {
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(255,255,255,0.15);
          border-radius: 20px;
          padding: 4px 10px;
          font-size: 0.8em;
          text-transform: capitalize;
        }
        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: ${statusColor};
          box-shadow: 0 0 6px ${statusColor};
        }
        .stop-all-btn {
          background: rgba(244,67,54,0.8);
          border: none;
          border-radius: 8px;
          color: #fff;
          padding: 4px 10px;
          cursor: pointer;
          font-size: 0.8em;
          display: ${status === "running" ? "flex" : "none"};
          align-items: center;
          gap: 4px;
        }
        .weather-banner, .rain-delay-banner {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
          font-size: 0.82em;
          font-weight: 500;
        }
        .weather-banner { background: #fff3e0; color: #e65100; }
        .rain-delay-banner { background: #ede7f6; color: #4527a0; }
        .zones-container { padding: 8px; display: flex; flex-direction: column; gap: 6px; }
        .zone-row {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          border-radius: 10px;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border: 1px solid var(--divider-color, #e0e0e0);
          transition: border-color 0.2s;
        }
        .zone-row.active {
          border-color: #2196f3;
          background: rgba(33,150,243,0.05);
        }
        .zone-icon { color: var(--primary-color); flex-shrink: 0; }
        .zone-icon.active { color: #2196f3; }
        .zone-info { flex: 1; min-width: 0; }
        .zone-name { font-weight: 500; font-size: 0.95em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .zone-meta { font-size: 0.78em; color: var(--secondary-text-color); margin-top: 2px; }
        .zone-progress {
          width: 100%;
          height: 3px;
          background: var(--divider-color);
          border-radius: 2px;
          margin-top: 6px;
          overflow: hidden;
          display: none;
        }
        .zone-progress.visible { display: block; }
        .zone-progress-bar {
          height: 100%;
          background: #2196f3;
          transition: width 1s linear;
          border-radius: 2px;
        }
        .zone-actions { display: flex; gap: 6px; align-items: center; }
        .btn-run {
          background: var(--primary-color);
          color: #fff;
          border: none;
          border-radius: 8px;
          padding: 5px 12px;
          cursor: pointer;
          font-size: 0.82em;
          display: flex;
          align-items: center;
          gap: 4px;
          white-space: nowrap;
        }
        .btn-stop {
          background: #f44336;
          color: #fff;
          border: none;
          border-radius: 8px;
          padding: 5px 12px;
          cursor: pointer;
          font-size: 0.82em;
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .btn-disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
        .water-stats {
          display: flex;
          gap: 12px;
          padding: 8px 16px 12px;
          border-top: 1px solid var(--divider-color);
          flex-wrap: wrap;
        }
        .stat-chip {
          display: flex;
          flex-direction: column;
          align-items: center;
          background: var(--secondary-background-color, #f5f5f5);
          border-radius: 8px;
          padding: 6px 12px;
          min-width: 70px;
        }
        .stat-value { font-size: 1em; font-weight: 600; }
        .stat-label { font-size: 0.72em; color: var(--secondary-text-color); margin-top: 2px; }
      </style>

      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:sprinkler-variant" style="color:#a5d6a7;"></ha-icon>
          <span class="title">${this._config.title}</span>
          <div class="status-badge">
            <div class="status-dot"></div>
            <span>${status.replace("_", " ")}</span>
          </div>
          <button class="stop-all-btn" id="stopAllBtn">
            <ha-icon icon="mdi:stop-circle" style="width:16px;height:16px;"></ha-icon>
            Stop All
          </button>
        </div>

        ${rainDelayBanner}
        ${weatherBanner}

        <div class="zones-container">
          ${zonesHtml}
        </div>

        ${waterStats}
      </ha-card>
    `;

    // Attach stop all button
    const stopAllBtn = this.shadowRoot.getElementById("stopAllBtn");
    if (stopAllBtn) {
      stopAllBtn.addEventListener("click", () => this._stopAll());
    }

    // Attach zone buttons
    zones.forEach((zoneCfg) => {
      const runBtn = this.shadowRoot.getElementById(`run-${zoneCfg.zone_id}`);
      const stopBtn = this.shadowRoot.getElementById(`stop-${zoneCfg.zone_id}`);
      if (runBtn) {
        runBtn.addEventListener("click", () =>
          this._startZone(zoneCfg.zone_id, zoneCfg.duration ?? 600)
        );
      }
      if (stopBtn) {
        stopBtn.addEventListener("click", () => this._stopZone(zoneCfg.zone_id));
      }
    });
  }

  _renderZone(zoneCfg, activeZone) {
    const zoneId = zoneCfg.zone_id;
    const zoneName = zoneCfg.name ?? zoneId;
    const isActive = activeZone === zoneId;
    const duration = zoneCfg.duration ?? 600;

    // Try to read sensor entities for this zone
    const remainingEntity = this._getEntityState(zoneCfg.remaining_entity ?? "");
    const waterTimeEntity = this._getEntityState(zoneCfg.water_time_entity ?? "");
    const switchEntity = this._getEntityState(zoneCfg.switch_entity ?? "");

    const remainingSecs = parseInt(remainingEntity?.state ?? "0") || 0;
    const waterTimeSecs = parseInt(waterTimeEntity?.state ?? "0") || 0;
    const isRunning = switchEntity?.state === "on" || isActive;

    const progress = isRunning && duration > 0
      ? Math.max(0, Math.min(100, ((duration - remainingSecs) / duration) * 100))
      : 0;

    const metaText = isRunning
      ? `Running — ${this._formatSeconds(remainingSecs)} remaining`
      : waterTimeSecs > 0
      ? `Today: ${this._formatSeconds(waterTimeSecs)}`
      : `Duration: ${this._formatSeconds(duration)}`;

    return `
      <div class="zone-row ${isRunning ? "active" : ""}">
        <ha-icon class="zone-icon ${isRunning ? "active" : ""}" icon="${isRunning ? "mdi:water" : "mdi:sprinkler"}"></ha-icon>
        <div class="zone-info">
          <div class="zone-name">${zoneName}</div>
          <div class="zone-meta">${metaText}</div>
          <div class="zone-progress ${isRunning ? "visible" : ""}">
            <div class="zone-progress-bar" style="width:${progress}%"></div>
          </div>
        </div>
        <div class="zone-actions">
          ${isRunning
            ? `<button class="btn-stop" id="stop-${zoneId}"><ha-icon icon="mdi:stop" style="width:14px;height:14px;"></ha-icon> Stop</button>`
            : `<button class="btn-run" id="run-${zoneId}"><ha-icon icon="mdi:play" style="width:14px;height:14px;"></ha-icon> Run</button>`
          }
        </div>
      </div>
    `;
  }

  _renderWaterStats() {
    const totalEntity = this._getEntityState(this._config.water_time_entity ?? "");
    const total = parseInt(totalEntity?.state ?? "0") || 0;
    return `
      <div class="water-stats">
        <div class="stat-chip">
          <span class="stat-value">${Math.round(total / 60)}m</span>
          <span class="stat-label">Today</span>
        </div>
      </div>
    `;
  }

  getCardSize() {
    const zones = this._config.zones ?? [];
    return 2 + zones.length;
  }

  static getConfigElement() {
    return document.createElement("smart-sprinkler-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.my_garden_status",
      title: "Smart Sprinkler",
      show_weather_info: true,
      show_water_stats: true,
      zones: [
        {
          zone_id: "abc12345",
          name: "Front Lawn",
          duration: 600,
          switch_entity: "switch.front_lawn",
          remaining_entity: "sensor.front_lawn_remaining_time",
          water_time_entity: "sensor.front_lawn_water_time_today",
        },
      ],
    };
  }
}

customElements.define("smart-sprinkler-card", SmartSprinklerCard);

window.customCards = window.customCards ?? [];
window.customCards.push({
  type: "smart-sprinkler-card",
  name: "Smart Sprinkler Card",
  description: "Control and monitor your Smart Sprinkler zones",
  preview: true,
  documentationURL: "https://github.com/gomble/smart-sprinkler-hacs",
});

console.info(
  `%c SMART-SPRINKLER-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#2e7d32;font-weight:700;padding:2px 6px;border-radius:4px 0 0 4px;",
  "color:#2e7d32;background:#e8f5e9;font-weight:700;padding:2px 6px;border-radius:0 4px 4px 0;"
);
