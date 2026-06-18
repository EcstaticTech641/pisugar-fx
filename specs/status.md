# pisugar-fx — Project Status & Architecture Summary

> **Last updated:** 2026-06-18  
> **Git HEAD:** `9688ac9`  
> **Python version target:** 3.9+ (Raspberry Pi OS)

---

## 1. What Is This Project?

`pisugar-fx` is a **real-time aircraft (ADS-B) flight tracker display** for a **Raspberry Pi Zero 2W** with a **WhisPlay 1.69" LCD HAT** (240×280 resolution). It renders a radar-style view of nearby aircraft with range rings, directional arrows, callsign labels, an RGB LED density indicator, and a hardware button to cycle through locations.

The name is a visual nod to the [PiSugar](https://github.com/PiSugar) power HAT ecosystem, but the project is **not affiliated with PiSugar**.

**Current operational mode:** Running in **local/antenna mode** — reads live ADS-B data from a physical RTL-SDR dongle via `readsb` / `dump1090`, which writes to `/run/readsb/aircraft.json`.

---

## 2. Two Code Paths in the Repository

### 2.1. Main Path — `flight/` Module (ACTIVE / PRODUCTION)

Entry point: `python3 flight_tracker.py`

This is the **actively developed** full-stack flight tracker. It runs on the Pi Zero 2W with the WhisPlay HAT. The controller (`flight/controller.py`) orchestrates:

- Fetching aircraft data (from local readsb or airplanes.live API)
- Track history with dead-reckoning ghosting
- Radar rendering via Pillow → RGB565 → WhisPlay display driver
- A daemon-threaded Flask web server that mirrors the display over Wi-Fi

**Data source is configurable** via `config/flight_locations.json` → `"source"` field:
- `"local"` — reads `/run/readsb/aircraft.json` (live RTL-SDR / dump1090)
- `"api"` — fetches from `https://api.airplanes.live/v2`

### 2.2. Backup / Prototype Path — `flight/app.py` + `flight/radar_display.py`

This is the **original prototype** that predates the modular `flight/` package:

- **`flight/app.py`** — A self-contained Flask server that proxies airplanes.live and serves a full web UI (Leaflet map, sidebar flight list, detail panel, browser geolocation). No hardware display integration.
- **`flight/radar_display.py`** — A standalone script that draws the radar display on the WhisPlay LCD by polling the Flask app above.

These files are **NOT actively maintained** and are superseded by the `flight/` package. They are kept as reference / backup.

---

## 3. Architecture & Data Flow

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────┐     ┌──────────────┐
│  Data Source  │────▶│  source.py       │────▶│  history.py    │────▶│  display.py  │
│              │     │                  │     │  (trails +     │     │  (radar      │
│  LocalSource  │     │  LocalSource  OR │     │   ghosting /   │     │   renderer)  │
│  (readsb)     │     │  FlightAPI       │     │   dead reckon) │     │              │
│  OR           │     │                  │     │                │     │              │
│  FlightAPI    │     └──────────────────┘     └────────────────┘     └──────┬───────┘
│  (airplanes.) │                                                           │
│  live)        │                                          ┌────────────────▼───────┐
└──────────────┘                                          │  controller.py         │
                                                          │  - Main loop           │
                                                          │  - Location cycling    │
                                                          │  - Button handling     │
                                                          │  - LED density color   │
                                                          │  - Display push        │
                                                          └────────┬───────────────┘
                                                                   │
                                                  ┌────────────────▼───────┐
                                                  │  web_server.py        │
                                                  │  (Flask daemon thread) │
                                                  │  - /snapshot.jpg      │
                                                  │  - /aircraft.json     │
                                                  │  - /map (Leaflet)     │
                                                  │  - /status            │
                                                  └───────────────────────┘
```

### Module Responsibilities

| File | Role |
|---|---|
| `flight_tracker.py` | Entry point; CLI arg parsing; calls `controller.main()` |
| `flight/controller.py` | `FlightTracker` class: main loop, display init, button monitoring, location cycling, LED control |
| `flight/source.py` | `LocalSource` — reads readsb JSON; `_normalize()` and `_haversine_miles()` helpers |
| `flight/api.py` | `FlightAPI` — HTTP client for airplanes.live; `FlightCache` for in-memory TTL caching |
| `flight/config.py` | `FlightTrackerConfig`, `FlightTrackerSettings`, `FlightLocation` dataclasses; JSON loader |
| `flight/display.py` | `FlightRadarScreen` — Pillow-based radar renderer (rings, arrows, crosshairs, header, trails, ghosts) |
| `flight/history.py` | `TrackHistory` — trail position logging, ghost generation via dead reckoning |
| `flight/location.py` | `LocationProvider` — IP geolocation (ipapi.co) → aircraft centroid fallback → nearest town via `data/cities.csv` |
| `flight/web_server.py` | `FlightWebServer` + `SharedState` — Flask daemon mirroring display state |
| `flight/app.py` | **Backup only** — standalone Flask app proxying airplanes.live with full web UI |
| `flight/radar_display.py` | **Backup only** — standalone Whisplay LCD renderer |

---

## 4. Configuration

Main config file: **`config/flight_locations.json`**

```json
{
  "locations": [],
  "settings": {
    "source": "local",
    "display_duration_seconds": 3600,
    "refresh_interval_seconds": 5,
    "brightness": 100,
    "rotation": 0,
    "random_location_enabled": false
  }
}
```

### Key Settings

| Setting | Default | Notes |
|---|---|---|
| `source` | `"api"` | `"local"` = readsb; `"api"` = airplanes.live |
| `display_duration_seconds` | `30` | How long before auto-cycling to next location (3600 = 1h in current config) |
| `refresh_interval_seconds` | `10` | How often to fetch new aircraft data (5s in current config) |
| `brightness` | `100` | Display backlight 0–100 |
| `trail_length` | `8` | Max trail points per aircraft |
| `trail_enabled` | `true` | Show faded position history lines |
| `ghost_enabled` | `true` | Show dead-reckoned positions after signal loss |
| `ghost_holdover_seconds` | `60` | Max time to keep a ghost alive |
| `web_server_enabled` | `true` | Flask web mirror on port 5000 |
| `web_server_port` | `5000` | Port for web UI |

### Location Format

When `source` is `"api"`, locations are specified in `config/flight_locations.json` as objects with `name`, `latitude`, `longitude`, `radius_miles`.  
When `source` is `"local"`, locations array is typically left **empty** (`[]`) — the app auto-detects location via IP geolocation or aircraft centroid.

---

## 5. Display Features

The 240×280 LCD renders:

- **Header bar** — Location name, current time, aircraft count
- **Range rings** — ½ and full radius circles with mile labels
- **Center crosshair** — Cyan cross + dot at observer position
- **Aircraft markers** — Directional arrows (cyan = airborne, orange = on ground)
- **Callsign labels** — Displayed for top 3 nearest/altitude-sorted aircraft
- **Trails** — Fading position history (if `trail_enabled` and <20 aircraft)
- **Ghosts** — Faded hollow arrows for aircraft predicted via dead reckoning
- **Density LED** — Blue (0) → Green (≤5) → Yellow (≤15) → Orange (≤30) → Red (>30) aircraft

---

## 6. Web Server

Runs as a daemon thread on port 5000.

| Endpoint | Description |
|---|---|
| `GET /` | HTML radar mirror page (auto-refreshes JPEG every 2s) |
| `GET /snapshot.jpg` | Current radar frame as JPEG |
| `GET /aircraft.json` | Full aircraft list as JSON |
| `GET /map` | Leaflet.js interactive dark map with click-for-detail panel |
| `GET /status` | JSON: location, count, uptime, LED color |

---

## 7. Hardware & Dependencies

### Hardware
- **Raspberry Pi Zero 2W** (tested; any Pi with GPIO should work)
- **WhisPlay 1.69" LCD HAT** (ST7789-based, 240×280)
- **RTL-SDR USB dongle** (for local/antenna mode) running `readsb` / `dump1090`

### Python Dependencies (`requirements.txt`)
| Package | Min Version | Purpose |
|---|---|---|
| `requests` | 2.31.0 | HTTP client for airplanes.live |
| `Pillow` | 10.0.0 | Image rendering |
| `flask` | 3.0.0 | Web server daemon |
| `st7789` | 1.0.0 | Alternative display driver (not currently used) |
| `pytest` / `pytest-cov` | 7.4.0 / 4.1.0 | Testing |

### Whisplay Driver
The Whisplay HAT driver is expected at:
```
/home/aaron/Whisplay/Driver/
```
The class `WhisPlayBoard` provides:
- `draw_image(x, y, w, h, rgb565_data)` — push raw RGB565 frame
- `set_backlight(brightness)` — 0–100
- `set_rgb(r, g, b)` — set the RGB status LED
- `button_pressed()` — read button state

If the driver is unavailable, the app runs in **headless mode** (no display, no button, no LED), logging what it *would* display.

### readsb Integration
When `source = "local"`, expects readsb to be running and writing to:
```
/run/readsb/aircraft.json
```
This file is updated every ~1 second by readsb / dump1090. The app caches reads for 1 second to avoid re-reading on each 100ms loop iteration.

---

## 8. Testing & Diagnostics

| File | What It Tests |
|---|---|
| `tests/flight_test.py` | Config validation, API connectivity, test radar render, display hardware check |
| `tests/flight_debug.py` | Hardware diagnostics |
| `tests/flight_integration_test.py` | App logic integration checks |
| `tests/range_assessment.py` | Antenna / radio range assessment |
| `flight/test_location.py` | Unit tests for geolocation: nearest town lookup, IP geolocation mock, aircraft centroid algorithm, performance benchmarks |

Run: `python -m pytest tests/ flight/test_location.py -v`

---

## 9. Current State & Maintenance Notes

### Recently added features (post initial prototype):
- **Local ADS-B antenna support** (`flight/source.py` — reads readsb JSON directly)
- **Location auto-detection** (`flight/location.py` — IP geolocation → aircraft centroid fallback)
- **Track history & dead-reckoning ghosts** (`flight/history.py`)
- **Leaflet interactive map** (`GET /map` in `flight/web_server.py`)
- **Web assets** (favicon pack in `flight/web-assets/`)
- **Rigorous unit tests** for location module (`flight/test_location.py`)

### Known issues / things to watch:
1. **Config is set to `"source": "local"` with empty locations** — antenna mode auto-detects location. If switching to API mode, you must add explicit locations to `config/flight_locations.json`.
2. **WhisPlay driver is at a non-standard path** — `/home/aaron/Whisplay/Driver/` — this will need adjustment if the project is set up on a different Pi or user account.
3. **`radar_display.py` and `app.py` are obsolete** — they exist only as reference. The `app.py` Flask route `GET /api/flights` conflicts conceptually with the modern `/snapshot.jpg` + `/aircraft.json` endpoints in `web_server.py`.
4. **`st7789` in requirements.txt** — This is an alternative display library, but the app currently uses the custom Whisplay driver. It's unclear if st7789 is still needed.
5. **No GPS support yet** — The `LocationProvider` docstring mentions GPS as a future option; currently only IP geolocation and aircraft centroid are implemented.
6. **Display rotation in config** — `rotation` setting is parsed but not actually applied in the rendering or display push code.

### Upgrade / evolution path:
- The `flight/` package structure is modular and ready for future features (alerts, weather integration, route prediction, etc.)
- The web server already provides all the data needed for remote monitoring
- The history/ghost system is already production-quality for handling momentary signal dropouts from the antenna

---

## 10. File Layout

```
pisugar-fx/
├── flight_tracker.py           # Entry point
├── config/
│   └── flight_locations.json   # Location & settings
├── data/
│   └── cities.csv              # City database for reverse geocoding
├── flight/
│   ├── __init__.py             # Package init, version 0.1.1
│   ├── api.py                  # airplanes.live API client
│   ├── app.py                  # [OBSOLETE] standalone Flask
│   ├── config.py               # Config dataclasses & loader
│   ├── controller.py           # Main app controller
│   ├── display.py              # Radar rendering engine
│   ├── history.py              # Trail tracking & ghosting
│   ├── location.py             # IP geolocation + centroid fallback
│   ├── radar_display.py        # [OBSOLETE] standalone renderer
│   ├── source.py               # Data source abstraction
│   ├── test_location.py        # Unit tests for location
│   ├── web_server.py           # Flask daemon + SharedState
│   └── web-assets/             # Favicon pack
├── specs/
│   └── status.md               # THIS FILE
├── tests/
│   ├── __init__.py
│   ├── flight_debug.py         # Hardware diagnostics
│   ├── flight_integration_test.py  # Integration tests
│   ├── flight_test.py          # Config + API + render tests
│   └── range_assessment.py     # Antenna range test
├── setup.conf                  # (optional) Pi setup config
├── setup.sh                    # (optional) Pi setup script
├── test_server.py              # (optional) test helper
├── requirements.txt            # Python dependencies
├── README.md                   # User-facing docs
└── LICENSE                     # Apache 2.0