# Smart Sprinkler

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/gomble/smart-sprinkler-hacs.svg)](https://github.com/gomble/smart-sprinkler-hacs/releases)

A feature-rich Home Assistant integration for garden sprinkler controllers with weather-based automation, zone scheduling, and a beautiful Lovelace card.

---

## Features

### Zone Control
- Add unlimited watering zones, each mapped to a HA switch entity
- Start / stop individual zones via the UI, card, or automations
- Per-zone default duration (configurable as a Number entity)
- Emergency stop-all button

### Scheduling
- **Schedule modes**: Daily, Every N days, Odd days, Even days, Weekdays only, or Custom day selection
- Per-zone start time configuration
- Schedule shown as `next_run` sensor for use in automations

### Soak & Cycle
- Optional per-zone soak-and-cycle mode to prevent runoff on slopes
- Configure cycle duration, soak pause, and number of repetitions

### Weather-Based Skipping
- Connect any HA `weather.*` entity with forecast support
- Automatically skips watering when:
  - Rain is forecast (configurable threshold in mm)
  - Wind speed exceeds threshold (km/h)
  - Temperature is at or below freeze threshold (°C)
- Manual rain delay (1–14 days)

### Pump & Master Valve
- Optional pump switch: activated before any zone starts, deactivated when all zones stop
- Optional master valve switch: same behavior as pump switch
- Both are fully optional — works without them

### Binary Sensors
- Per-zone `active` sensor (device class: running)
- Controller-level `running` sensor (any zone active)
- `Rain Delay` sensor (true when rain delay is active)

### Sensors
- Per-zone: water time today, remaining time, next run timestamp
- Controller: status (idle / running / rain\_delay / suspended), total water time today

### Number Entities (live-adjustable)
- Per-zone: duration, cycle duration, soak duration, cycle count
- Controller: rain threshold, wind threshold, freeze threshold

### Select Entities
- Per-zone schedule mode selector

### Services
| Service | Parameters | Description |
|---------|-----------|-------------|
| `smart_sprinkler.start_zone` | `zone_id`, `duration` (s) | Start a zone |
| `smart_sprinkler.stop_zone` | `zone_id` | Stop a zone |
| `smart_sprinkler.stop_all` | — | Stop all zones |
| `smart_sprinkler.set_rain_delay` | `rain_delay_days` | Set rain delay |

---

## Installation

### HACS (recommended)
1. Open HACS → Integrations → Custom repositories
2. Add `https://github.com/gomble/smart-sprinkler-hacs` as **Integration**
3. Install **Smart Sprinkler**
4. Restart Home Assistant

### Manual
1. Copy `custom_components/smart_sprinkler` into your HA `custom_components` folder
2. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Smart Sprinkler**
3. Follow the setup wizard:
   - Controller name
   - Optional: pump switch, master valve switch
   - Weather entity and thresholds
   - Add zones (name + optional HA switch entity)

---

## Lovelace Card

Add the card to your dashboard:

```yaml
type: custom:smart-sprinkler-card
entity: sensor.my_garden_status
title: My Garden
show_weather_info: true
show_water_stats: true
water_time_entity: sensor.my_garden_total_water_time_today
zones:
  - zone_id: abc12345
    name: Front Lawn
    duration: 600
    switch_entity: switch.front_lawn
    remaining_entity: sensor.front_lawn_remaining_time
    water_time_entity: sensor.front_lawn_water_time_today
  - zone_id: def67890
    name: Back Garden
    duration: 900
    switch_entity: switch.back_garden
    remaining_entity: sensor.back_garden_remaining_time
    water_time_entity: sensor.back_garden_water_time_today
```

> Find your `zone_id` values in the `extra_state_attributes` of any zone switch entity.

---

## Automation Examples

### Water every morning at 6:00 — skip if raining

```yaml
automation:
  alias: Morning Watering
  trigger:
    - platform: time
      at: "06:00:00"
  action:
    - service: smart_sprinkler.start_zone
      data:
        zone_id: abc12345
        duration: 600
```

*(The integration automatically checks weather and skips if conditions are unfavorable.)*

### Rain delay after actual rain sensor

```yaml
automation:
  alias: Set Rain Delay After Rain
  trigger:
    - platform: numeric_state
      entity_id: sensor.precipitation_today
      above: 5
  action:
    - service: smart_sprinkler.set_rain_delay
      data:
        rain_delay_days: 2
```

---

## License

MIT License — see [LICENSE](LICENSE)
