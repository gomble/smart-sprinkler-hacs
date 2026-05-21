"""Constants for the Smart Sprinkler integration."""

DOMAIN = "smart_sprinkler"
NAME = "Smart Sprinkler"

# Frontend
URL_BASE = "/smart_sprinkler"
SMART_SPRINKLER_CARDS = [
    {
        "name": "Smart Sprinkler Card",
        "filename": "smart-sprinkler-card.js",
        "version": "1.0.0",
    }
]

# Config keys
CONF_CONTROLLER_NAME = "controller_name"
CONF_ZONES = "zones"
CONF_ZONE_NAME = "zone_name"
CONF_ZONE_VALVE_GPIO = "zone_valve_gpio"
CONF_PUMP_SWITCH = "pump_switch"
CONF_MASTER_SWITCH = "master_switch"
CONF_VALVE_DELAY = "valve_delay"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_RAIN_THRESHOLD = "rain_threshold"
CONF_WIND_THRESHOLD = "wind_threshold"
CONF_TEMP_MIN = "temp_min"
CONF_FREEZE_THRESHOLD = "freeze_threshold"
CONF_ENABLE_WEATHER = "enable_weather"

# Defaults
DEFAULT_VALVE_DELAY = 0             # seconds — delay between pump/master on and zone valve open
DEFAULT_RAIN_THRESHOLD = 2.0        # mm — skip if forecast rain >= this
DEFAULT_WIND_THRESHOLD = 40.0       # km/h — skip if wind >= this
DEFAULT_TEMP_MIN = 2.0              # °C — skip if temp <= this (freeze protection)
DEFAULT_FREEZE_THRESHOLD = 4.0      # °C
DEFAULT_RUN_DURATION = 10           # minutes
DEFAULT_SOAK_TIME = 5               # minutes between cycles (soak & cycle mode)
DEFAULT_CYCLE_COUNT = 1

# Schedule modes
SCHEDULE_MODE_DAILY = "daily"
SCHEDULE_MODE_INTERVAL = "interval"
SCHEDULE_MODE_ODD = "odd_days"
SCHEDULE_MODE_EVEN = "even_days"
SCHEDULE_MODE_WEEKDAYS = "weekdays"
SCHEDULE_MODE_CUSTOM = "custom"

SCHEDULE_MODES = [
    SCHEDULE_MODE_DAILY,
    SCHEDULE_MODE_INTERVAL,
    SCHEDULE_MODE_ODD,
    SCHEDULE_MODE_EVEN,
    SCHEDULE_MODE_WEEKDAYS,
    SCHEDULE_MODE_CUSTOM,
]

# Weekday names
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Controller status
STATUS_IDLE = "idle"
STATUS_WAITING = "waiting"          # pump/master on, waiting for startup delay before valve opens
STATUS_RUNNING = "running"
STATUS_STOPPING = "stopping"        # valve closed, waiting for shutdown delay before pump/master off
STATUS_SUSPENDED = "suspended"
STATUS_RAIN_DELAY = "rain_delay"
STATUS_ERROR = "error"

# Service names
SERVICE_START_ZONE = "start_zone"
SERVICE_STOP_ZONE = "stop_zone"
SERVICE_STOP_ALL = "stop_all"
SERVICE_RUN_PROGRAM = "run_program"
SERVICE_SET_RAIN_DELAY = "set_rain_delay"

# Attributes
ATTR_ZONE_ID = "zone_id"
ATTR_DURATION = "duration"
ATTR_RAIN_DELAY_DAYS = "rain_delay_days"
ATTR_NEXT_RUN = "next_run"
ATTR_LAST_RUN = "last_run"
ATTR_TOTAL_WATER_TIME = "total_water_time_today"
ATTR_REMAINING_TIME = "remaining_time"
ATTR_WEATHER_SKIP_REASON = "weather_skip_reason"
