# Changelog

## [1.0.0] — 2026-05-22

### Added
- Initial release
- Multi-zone sprinkler controller with switch entities per zone
- Weather-based skipping (rain, wind, freeze protection)
- Manual rain delay (1–14 days)
- Per-zone schedule modes: daily, interval, odd/even days, weekdays, custom
- Soak & cycle mode per zone
- Pump and master valve support
- Binary sensors: zone active, any-zone running, rain delay active
- Sensors: water time today, remaining time, next run, controller status, total water time
- Number entities: durations, thresholds (live-adjustable)
- Select entity: schedule mode per zone
- Services: start_zone, stop_zone, stop_all, set_rain_delay
- Custom Lovelace card with progress bar and quick controls
- German and English translations
