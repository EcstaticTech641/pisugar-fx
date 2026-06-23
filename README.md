# Flight Tracker Display

Real-time aircraft tracking display for Raspberry Pi Zero 2W with WhisPlay 1.69" HAT.

> Disclaimer: Although the project name is inspired by PiSugar, this project is not affiliated with or sponsored by [@PiSugar](https://github.com/PiSugar) in any way.

---

## Quick Start

### 1. Configure the Data Source

Edit `config/flight_locations.json`. The `"source"` setting determines which data backend the app uses: 

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

**See [Operational Modes](#operational-modes) below** for a full explanation of `"local"` vs `"api"` mode and when to set explicit coordinates.

### 2. Test Configuration

Before running on hardware, test your setup:

```bash
python3 tests/flight_test.py
```

This will:
- ✓ Validate configuration file
- ✓ Test data source connectivity (API or local file)
- ✓ Render a test radar screen
- ✓ Test display hardware (if available)

### 3. Run the Application

```bash
python3 flight_tracker.py
```

Or with verbose logging:

```bash
python3 flight_tracker.py --debug
```

---

## Operational Modes

The app supports two data source modes, selected via the `"source"` field in `config/flight_locations.json`.

### Local SDR Mode — `"source": "local"` *(Production Default)*

Reads live ADS-B data directly from a connected **RTL-SDR USB dongle** running `readsb` or `dump1090`. The decoder writes decoded aircraft positions to:

```
/run/readsb/aircraft.json
```

This file is polled every ~1 second for maximum freshness. No internet connection is required for aircraft data.

**Location detection is automatic.** When `source` is `"local"`, the `locations` array can safely be left empty (`[]`). The `LocationProvider` subsystem resolves position through a priority chain:

1. **IP Geolocation** — queries `ipapi.co` to get approximate coordinates from the device's public IP
2. **Aircraft Centroid Fallback** — if geolocation is unavailable or returns no nearby aircraft, computes the centroid of all currently-visible aircraft
3. **Nearest Town Lookup** — resolves the detected coordinate to the nearest named town using `data/cities.csv`

### API Mode — `"source": "api"` *(Network / No-Antenna Fallback)*

Fetches aircraft data from **airplanes.live** over Wi-Fi. No RTL-SDR dongle required. When using API mode, the `locations` array **must** contain at least one explicit entry:

```json
{
  "locations": [
    {
      "name": "OKC (Will Rogers)",
      "latitude": 35.3898,
      "longitude": -97.6007,
      "radius_miles": 100
    },
    {
      "name": "DFW (Dallas/Fort Worth)",
      "latitude": 32.8975,
      "longitude": -97.0380,
      "radius_miles": 100
    }
  ],
  "settings": {
    "source": "api",
    "display_duration_seconds": 30,
    "refresh_interval_seconds": 10,
    "brightness": 100,
    "rotation": 0
  }
}
```

The API endpoint used:
```
GET https://api.airplanes.live/v2/point/{lat}/{lon}/{radius_miles}
```

---

## Features

### Core Display

The 240×280 LCD renders a radar-style view:

```
┌────────────────────────┐
│ OKC (Will Rogers) 12:34│  ← Header: Location name, current time
│ 5 aircraft             │  ← Aircraft count
├────────────────────────┤
│                        │
│        100mi           │  ← Range rings: ½ radius and full radius
│     ╱─╲                │
│    │ ✕ │  ← Aircraft   │  ← Cyan = Airborne, Orange = On Ground
│     ╲─╱    arrows      │
│       50mi             │
│                        │
│   AAL   SWA   DAL      │  ← Callsigns for top 3 aircraft
│                        │
└────────────────────────┘
```

- **Header bar** — Location name, current time, aircraft count
- **Range rings** — ½ radius and full radius circles with mile labels
- **Center crosshair** — Cyan cross + dot at observer position
- **Aircraft markers** — Directional arrows (cyan = airborne, orange = on ground)
- **Callsign labels** — Displayed for the top 3 nearest/highest-altitude aircraft

### Track History & Dead-Reckoning Ghosts

The `history.py` module maintains a position log for every tracked aircraft:

- **Trails** — Fading position history lines are rendered behind each aircraft (when there are fewer than 20 aircraft visible, to maintain performance). Trail length is configurable via `trail_length`.
- **Dead-Reckoning Ghosts** — When an aircraft's ADS-B signal is lost, the app continues to project its likely position forward in time using its last known heading and speed. These ghost markers appear as faded hollow arrows and persist for up to `ghost_holdover_seconds` before being removed.

### RGB LED Density Indicator

The WhisPlay HAT's onboard RGB LED provides an at-a-glance aircraft count indicator:

| Color  | Aircraft Count |
|--------|----------------|
| 🔵 Blue   | 0 (no aircraft) |
| 🟢 Green  | 1–5            |
| 🟡 Yellow | 6–15           |
| 🟠 Orange | 16–30          |
| 🔴 Red    | > 30           |

### Flask Web Mirror & Leaflet.js Map

A Flask web server runs as a daemon thread on **port 5000**, mirroring the display state over Wi-Fi. Access it from any browser on the same network at `http://<pi-ip>:5000/`.

| Endpoint | Description |
|---|---|
| `GET /` | HTML radar mirror page — auto-refreshes JPEG snapshot every 2 seconds |
| `GET /snapshot.jpg` | Current radar frame as JPEG |
| `GET /aircraft.json` | Full aircraft list as JSON |
| `GET /map` | **Leaflet.js interactive dark map** with click-for-detail panel |
| `GET /status` | JSON: current location, aircraft count, uptime, LED color |

### Button Control

- **Single press** — Skip to the next configured location (API mode) or manually trigger a location refresh (local mode)
- **Auto-cycle** — Display rotates through locations after `display_duration_seconds`
- **Auto-refresh** — Aircraft data fetched every `refresh_interval_seconds`

---

## Configuration Reference

Main config file: `config/flight_locations.json`

### Settings

| Setting | Default | Description |
|---|---|---|
| `source` | `"api"` | `"local"` = RTL-SDR/readsb antenna; `"api"` = airplanes.live |
| `display_duration_seconds` | `30` | How long to show each location before auto-cycling |
| `refresh_interval_seconds` | `10` | How often to fetch new aircraft data |
| `brightness` | `100` | Display backlight level (0–100) |
| `rotation` | `0` | Display rotation in degrees: 0, 90, 180, 270 *(parsed but not currently applied in rendering)* |
| `random_location_enabled` | `false` | Not yet implemented |
| `trail_length` | `8` | Maximum trail points stored per aircraft |
| `trail_enabled` | `true` | Show faded position history lines |
| `ghost_enabled` | `true` | Show dead-reckoned positions after signal loss |
| `ghost_holdover_seconds` | `60` | Max seconds to keep a ghost before removing it |
| `web_server_enabled` | `true` | Enable Flask web mirror daemon |
| `web_server_port` | `5000` | Port for the web UI |

### Location Format (API Mode Only)

When `source` is `"api"`, define one or more locations:

| Field | Description |
|---|---|
| `name` | Display name shown in the header bar |
| `latitude` | Center latitude (decimal degrees) |
| `longitude` | Center longitude (decimal degrees) |
| `radius_miles` | Search radius (10–500 miles) |

---

## Hardware

| Component | Notes |
|---|---|
| **Raspberry Pi Zero 2W** | Tested platform; any Pi with GPIO should work |
| **WhisPlay 1.69" LCD HAT** | ST7789-based, 240×280 resolution, RGB565 format |
| **RTL-SDR USB dongle** | Required for `"source": "local"` mode; runs `readsb` or `dump1090` |

> **Headless / No-Hardware Mode:** If the WhisPlay driver is unavailable (e.g., running on a non-Pi machine), the app runs in headless mode — the main loop continues, data is fetched, and all state is logged, but no display push, LED, or button operations are performed. The web server and snapshot endpoints remain fully functional in headless mode.

### WhisPlay Driver

The Whisplay HAT driver is expected at:
```
/home/aaron/Whisplay/Driver/
```

> **Note:** This path is currently hardcoded to a specific user directory. If running on a different Pi or user account, this path will need to be adjusted in the source.

The `WhisPlayBoard` class provides:
- `draw_image(x, y, w, h, rgb565_data)` — push a raw RGB565 frame
- `set_backlight(brightness)` — set brightness 0–100
- `set_rgb(r, g, b)` — control the RGB status LED
- `button_pressed()` — read the physical button state

### readsb Integration

When `source = "local"`, `readsb` or `dump1090` must be running and writing to:
```
/run/readsb/aircraft.json
```
This file is updated every ~1 second. The app caches reads for 1 second to avoid redundant reads within each 100ms control loop iteration.

---

## File Structure

```
pisugar-fx/
├── flight_tracker.py               # Entry point; CLI arg parsing
├── config/
│   └── flight_locations.json       # Data source, locations, and settings
├── data/
│   └── cities.csv                  # City database for reverse geocoding
├── flight/
│   ├── __init__.py                 # Package init (v0.1.1)
│   ├── api.py                      # airplanes.live HTTP client + TTL cache
│   ├── app.py                      # [OBSOLETE / REFERENCE ONLY] standalone Flask proxy
│   ├── config.py                   # Config dataclasses & JSON loader
│   ├── controller.py               # FlightTracker: main loop, button, LED, location cycling
│   ├── display.py                  # FlightRadarScreen: Pillow radar renderer
│   ├── history.py                  # TrackHistory: trail logging + dead-reckoning ghosts
│   ├── location.py                 # LocationProvider: IP geolocation → centroid → city lookup
│   ├── radar_display.py            # [OBSOLETE / REFERENCE ONLY] standalone LCD renderer
│   ├── source.py                   # LocalSource (readsb JSON) + normalization helpers
│   ├── test_location.py            # Unit tests for the location module
│   ├── web_server.py               # FlightWebServer + SharedState Flask daemon
│   └── web-assets/                 # Favicon pack for web UI
├── tests/
│   ├── flight_test.py              # Config validation, API/source check, test render
│   ├── flight_debug.py             # Hardware diagnostics
│   ├── flight_integration_test.py  # App logic integration checks
│   └── range_assessment.py        # Antenna range assessment
├── specs/
│   ├── flight-tracker/
│   │   ├── spec.md                 # Implementation spec (Option A — reflects built system)
│   │   ├── status.md               # Source-of-truth architecture & current state
│   │   ├── plan.md                 # Historical implementation plan (complete)
│   │   └── hotspot-nfc.md          # Hotspot/NFC setup notes
├── setup.conf                      # Pi setup configuration
├── setup.sh                        # Pi setup script
├── requirements.txt                # Python dependencies
└── LICENSE                         # Apache 2.0
```

> **⚠ Warning — Obsolete Files:** `flight/app.py` and `flight/radar_display.py` are **not part of the active application**. They are the original prototype — a self-contained Flask server that proxied airplanes.live directly and a paired standalone LCD renderer. The endpoints in `app.py` (`/api/flights`) conflict conceptually with the modern web server (`/aircraft.json`, `/snapshot.jpg`). Do not attempt to run `flight/app.py` as a replacement for `flight_tracker.py`.

---

## Performance

| Metric | Local SDR Mode | API Mode |
|---|---|---|
| Startup time | ~2 seconds | ~3–5 seconds (first API call) |
| Data freshness | ~1 second | 10–15 seconds |
| Update rate | Every 5 seconds | Every 10 seconds (configurable) |
| Network data | None (local antenna) | ~2–5 KB per update (~50–150 KB/hour) |
| Memory | ~30–50 MB typical | ~30–50 MB typical |

---

## Troubleshooting

### "No data" displayed
- **Local mode:** Verify `readsb` is running: `ls -la /run/readsb/aircraft.json`
- **API mode:** Check Wi-Fi: `ping google.com` — API may be temporarily unavailable
- Verify coordinates are correct (API mode) or that the RTL-SDR dongle is detected (local mode)

### Display is blank
- Verify WhisPlay driver is installed: `ls ~/Whisplay/Driver/`
- Check `brightness` setting in config (0 would appear blank)
- Run `python3 tests/flight_debug.py` to diagnose hardware issues

### No aircraft showing
- **Local mode:** Confirm the RTL-SDR antenna has line-of-sight and `readsb` is actively decoding
- **API mode:** Check radius (10–500 miles) and verify coordinates
- May be fewer aircraft during night hours

### Web server not accessible
- Confirm `web_server_enabled: true` in config
- Check that port 5000 is not blocked by a firewall on the Pi
- Visit `http://<pi-ip>:5000/status` to confirm the daemon is running

---

## Limitations

- **WhisPlay driver path is user-specific** — currently hardcoded to `/home/aaron/Whisplay/Driver/`; must be manually updated for a different user or machine.
- **GPS not yet integrated** — `LocationProvider` uses IP geolocation and aircraft centroid; direct GPS hardware is a planned future option.
- **`rotation` setting is not applied** — the `rotation` field is parsed from config but is not currently applied in the rendering or display push pipeline.
- **Local mode coverage is antenna-dependent** — reception range is limited by antenna placement, local RF environment, and terrain. Rural or obstructed sites may see fewer aircraft than a well-placed rooftop antenna.
- **API mode rate limits** — airplanes.live may throttle requests from the same IP under heavy load (unlikely at normal polling rates).

---

## Testing

Run the full test suite:

```bash
python -m pytest tests/ flight/test_location.py -v
```

| File | What It Tests |
|---|---|
| `tests/flight_test.py` | Config validation, source connectivity, test radar render, display hardware |
| `tests/flight_debug.py` | Hardware diagnostics |
| `tests/flight_integration_test.py` | App logic integration checks |
| `tests/range_assessment.py` | Antenna / radio range assessment |
| `flight/test_location.py` | Unit tests: nearest town lookup, IP geolocation mock, centroid algorithm, benchmarks |

---

## Future Enhancements

- [ ] Aircraft details screen (callsign, type, altitude, speed, squawk)
- [ ] Route prediction / planned flight path overlay
- [ ] GPS hardware integration for precise self-location
- [ ] Apply `rotation` config setting to the display pipeline
- [ ] Integration with weather station data
- [ ] Alert system (watch for specific callsigns or aircraft types)
- [ ] Make WhisPlay driver path configurable via `setup.conf`

---

## License

Apache 2.0

---

## References

- **airplanes.live**: https://airplanes.live/
- **ADS-B Explained (FAA)**: https://www.faa.gov/nextgen/how-nextgen-works/surveillance/ads-b/
- **readsb** (ADS-B decoder): https://github.com/wiedehopf/readsb
- **dump1090** (ADS-B decoder): https://github.com/flightaware/dump1090
- **PiSugar / WhisPlay HAT**: https://github.com/PiSugar/Whisplay
- **PiSugar Wiki**: https://github.com/PiSugar/PiSugar/wiki/PiSugarS-Series

---

**Questions?** Check the `specs/` directory — `status.md` is the authoritative architecture reference, and `spec.md` is the full implementation specification.
