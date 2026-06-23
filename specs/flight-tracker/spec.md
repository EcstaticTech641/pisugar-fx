# Specification: Flight Tracker Display

**Project**: pisugar-fx Flight Tracker  
**Original Date**: 2026-04-24  
**Last Updated**: 2026-06-22  
**Status**: `IMPLEMENTED / PRODUCTION`  
**Hardware**: Raspberry Pi Zero 2W + WhisPlay 1.69" HAT (240×280) + RTL-SDR USB dongle

> **Note:** This document reflects the system as built. For a living architecture summary, current known issues, and module-level detail, see [`specs/flight-tracker/status.md`](./status.md). For the original implementation plan (historical), see [`specs/flight-tracker/plan.md`](./plan.md).

---

## Overview

`pisugar-fx` is a real-time ADS-B flight tracker display running on a Raspberry Pi Zero 2W with the WhisPlay 1.69" LCD HAT (240×280). It renders a radar-style view of nearby aircraft, including directional arrows, range rings, callsign labels, position history trails, dead-reckoning ghost markers, an RGB LED density indicator, and a browser-accessible Leaflet.js interactive map.

The application supports two data source modes:

- **Local SDR Mode** (`"source": "local"`) — Reads live ADS-B data from a connected RTL-SDR dongle via `readsb`/`dump1090`, which writes decoded aircraft positions to `/run/readsb/aircraft.json`. This is the production default. Location detection is automatic via the `LocationProvider` subsystem.
- **API Mode** (`"source": "api"`) — Fetches aircraft data from the `airplanes.live` v2 API over Wi-Fi. Requires explicit location coordinates in `config/flight_locations.json`.

---

## User Stories

### US1: View Aircraft Radar `[IMPLEMENTED]` *(Priority: P1 — MVP)*

**As a** user with a Raspberry Pi  
**I want** to see nearby aircraft plotted on a radar display  
**So that** I can track flights in real-time around my location

**Acceptance Criteria:**
- Display shows center crosshairs and two range rings (½ radius, full radius)
- Each aircraft shown as a directional arrow with heading
- Aircraft colored differently if on ground (orange) vs in air (cyan)
- Location name, current time, and aircraft count shown in header
- Display updates every `refresh_interval_seconds` (default: 5s in local mode, 10s in API mode)
- Position history trails rendered behind each aircraft (when < 20 aircraft visible)
- Dead-reckoning ghost markers shown for recently-lost signals

### US2: Automatic or Configured Location `[IMPLEMENTED]` *(Priority: P1 — MVP)*

**As a** user running in local/antenna mode  
**I want** the system to automatically determine my location  
**So that** I do not need to manually configure GPS coordinates

**Acceptance Criteria:**
- When `source = "local"`, `locations` array may be empty (`[]`)
- `LocationProvider` resolves position via priority chain: IP geolocation → aircraft centroid fallback → `data/cities.csv` nearest-town lookup
- When `source = "api"`, locations are defined explicitly in `config/flight_locations.json` and the app cycles through them
- Each location displays for `display_duration_seconds` before auto-cycling

### US3: Show Aircraft Details `[IMPLEMENTED]` *(Priority: P2)*

**As a** flight enthusiast  
**I want** to see details about the nearest aircraft  
**So that** I understand what types of flights are in the area

**Acceptance Criteria:**
- Callsigns displayed for the **top 3** nearest/highest-altitude aircraft
- Heading indicator shows aircraft direction (directional arrow)
- Ground traffic (orange) vs airborne (cyan) clearly distinguished
- Web UI at `/map` provides click-for-detail panel with callsign, altitude, speed, and squawk

### US4: Responsive Button Control `[IMPLEMENTED]` *(Priority: P1 — MVP)*

**As a** user  
**I want** to press the WhisPlay button to skip to the next location  
**So that** I can quickly browse different monitored areas

**Acceptance Criteria:**
- Single button press cycles to next location (API mode) or triggers location refresh (local mode)
- No perceptible delay in response
- Button state is polled within the 100ms control loop

---

## Functional Requirements

### FR1: Data Source `[IMPLEMENTED]`

Two data source backends are supported, selected via `"source"` in `config/flight_locations.json`.

**FR1a — Local SDR Source (`"local"`)**
- Reads `/run/readsb/aircraft.json`, written by `readsb` / `dump1090` every ~1 second
- Implemented in `flight/source.py` → `LocalSource`
- Aircraft records are normalized via `_normalize()` into a standard internal dict format
- Haversine distance filtering via `_haversine_miles()` to restrict to the configured radius
- File reads are cached for 1 second to avoid redundant disk access within the 100ms loop
- No internet connection required for aircraft data

**FR1b — API Source (`"api"`)**
- Endpoint: `GET https://api.airplanes.live/v2/point/{lat}/{lon}/{radius_miles}`
- Implemented in `flight/api.py` → `FlightAPI` class with `FlightCache` in-memory TTL caching
- Response fields used: ICAO, callsign, lat/lon, altitude, speed, heading, aircraft type, registration, squawk, ground/airborne status
- Cache TTL: 60 seconds

### FR2: Radar Rendering `[IMPLEMENTED]`

- Display dimensions: 240×280 pixels
- Header bar: 36px height — location name, current timestamp, aircraft count
- Radar area: remaining 244px with centered crosshair
- Range rings: ½ radius and full radius, labeled with mile markers
- Center point: (120, 158)
- Scale: ~1.1 pixel/mile for 100-mile radius
- Implemented in `flight/display.py` → `FlightRadarScreen`
- Rendered via Pillow → RGB565 conversion → WhisPlayBoard `draw_image()` push

### FR3: Aircraft Rendering `[IMPLEMENTED]`

- Directional arrows rotated to aircraft heading
- Airborne aircraft: cyan (`#00E5FF`)
- Ground aircraft: orange (`#FF6B35`)
- **Callsign labels** rendered for the **top 3** nearest/highest-altitude aircraft
- **Trails** — fading position history lines drawn behind each aircraft; active only when fewer than 20 aircraft are visible (performance threshold); trail opacity decreases with age
- **Ghost markers** — faded hollow arrows rendered at dead-reckoned positions for recently-lost targets; rendered until `ghost_holdover_seconds` expires or signal is re-acquired
- All rendering implemented in `flight/display.py`; trail/ghost data sourced from `flight/history.py`

### FR4: Performance `[IMPLEMENTED]`

- Local source file read completes in < 50ms
- API call should complete within 5 seconds (timeout enforced)
- Display render + push completes within 2 seconds
- Control loop runs at ~100ms polling intervals
- Memory target: < 60 MB on Pi Zero 2W

### FR5: Error Handling `[IMPLEMENTED]`

- Network timeout (API mode): show "No data" in header, continue cycling
- API errors: log and skip that location's fetch; display last valid frame
- Missing/unreadable `/run/readsb/aircraft.json` (local mode): log warning, show last valid frame
- Graceful degradation — no crash on network or file I/O errors
- Display continues to show last valid data if any fetch fails

### FR6: Caching `[IMPLEMENTED]`

- API mode: in-memory TTL cache (`FlightCache`) — 60-second TTL to reduce API calls
- Local mode: file read cached for 1 second within the control loop

### FR7: Track History & Dead Reckoning `[IMPLEMENTED]`

Implemented in `flight/history.py` → `TrackHistory`.

- **Trail logging** — Each aircraft's position is appended to a bounded deque of length `trail_length` (default: 8 points) on every update cycle
- **Ghost generation** — When an aircraft's ICAO disappears from the current data frame, its last known position, heading, and speed are used to project a forward position: `position = last_pos + speed × elapsed_time × heading_vector`
- **Ghost expiry** — Ghost markers are retained for up to `ghost_holdover_seconds` (default: 60s). After expiry, or if the signal is re-acquired, the ghost is removed
- **Rendering trigger** — `display.py` receives both the live aircraft list and the ghost list from `controller.py` on each render call

### FR8: Location Auto-Detection `[IMPLEMENTED]`

Implemented in `flight/location.py` → `LocationProvider`.

Priority resolution chain when `source = "local"` and `locations = []`:

1. **IP Geolocation** — HTTP `GET https://ipapi.co/json/` → extracts `latitude`, `longitude`
2. **Aircraft Centroid Fallback** — if IP geolocation fails or returns no useful fix, computes the geographic centroid (mean lat/lon) of all currently-visible aircraft from the most recent readsb frame
3. **Nearest Town Lookup** — final resolved coordinate is matched against `data/cities.csv` using Haversine distance to find and display the nearest named city/town in the header

When `source = "api"` and explicit locations are configured, `LocationProvider` is bypassed.

### FR9: RGB LED Density Indicator `[IMPLEMENTED]`

The WhisPlay HAT's onboard RGB LED provides an at-a-glance aircraft traffic density indicator. Updated on every display push via `WhisPlayBoard.set_rgb(r, g, b)`.

| Aircraft Count | LED Color | RGB Value |
|---|---|---|
| 0 | Blue | `(0, 0, 255)` |
| 1–5 | Green | `(0, 255, 0)` |
| 6–15 | Yellow | `(255, 255, 0)` |
| 16–30 | Orange | `(255, 165, 0)` |
| > 30 | Red | `(255, 0, 0)` |

Implemented in `flight/controller.py` → `FlightTracker._update_led()`.

### FR10: Asynchronous Web Server Mirror `[IMPLEMENTED]`

Implemented in `flight/web_server.py` → `FlightWebServer` + `SharedState`.

- Flask HTTP server launched as a **daemon thread** at startup alongside the main display loop
- `SharedState` is a thread-safe container (using `threading.Lock`) holding the latest rendered JPEG snapshot and the current aircraft list
- The controller pushes updated state to `SharedState` on every display cycle
- The web server reads from `SharedState` to serve requests without blocking the display loop

| Endpoint | Response | Description |
|---|---|---|
| `GET /` | HTML | Auto-refresh radar mirror; polls `/snapshot.jpg` every 2 seconds |
| `GET /snapshot.jpg` | JPEG | Current radar frame as compressed JPEG |
| `GET /aircraft.json` | JSON | Full aircraft list with all fields |
| `GET /map` | HTML | Leaflet.js interactive dark map; click aircraft marker for detail panel |
| `GET /status` | JSON | Current location name, aircraft count, uptime, LED color string |

Default port: `5000`. Configurable via `web_server_port`. Can be disabled via `web_server_enabled: false`.

---

## Non-Functional Requirements

### NFR1: Display Quality `[IMPLEMENTED]`

- Clear, readable text within 240×280 constraint
- High contrast dark background (`#0A0A0F`) with bright accent colors for outdoor/dim-light viewing
- Smooth rendering; no flicker between updates (full-frame push via RGB565)

### NFR2: Hardware Integration `[IMPLEMENTED]`

- WhisPlay HAT driver (`WhisPlayBoard`) used for all hardware I/O: display push, brightness, LED, button
- RGB565 frame format enforced by Pillow → `tobytes("raw", "RGB")` + manual byte-swap conversion
- RTL-SDR dongle operates independently via `readsb`; the app only reads the output JSON file
- Button input polled within the 100ms control loop

**Headless Fallback Mode:**  
If the WhisPlay driver is not found at its expected path (e.g., running on a non-Pi development machine), the app detects the missing driver at startup and enters headless mode:
- `draw_image()`, `set_backlight()`, `set_rgb()`, and `button_pressed()` calls are silently no-oped
- The main display/data loop continues running normally
- All state is logged via the standard Python `logging` module
- The Flask web server daemon and all endpoints (`/`, `/snapshot.jpg`, `/aircraft.json`, `/map`, `/status`) remain fully functional in headless mode
- This allows development, testing, and remote monitoring without physical hardware

### NFR3: Reliability `[IMPLEMENTED]`

- Main loop runs indefinitely; all exceptions within the fetch/render cycle are caught and logged without crashing the process
- Graceful recovery from: network timeouts, missing readsb file, corrupt aircraft JSON, WhisPlay driver errors
- Ghost system ensures display continuity when aircraft signals momentarily drop

### NFR4: User Experience `[IMPLEMENTED]`

- First display frame appears within ~2 seconds of start (local mode) or ~5 seconds (API mode, first fetch)
- Location name resolved and shown in header on first frame
- Button response latency < 200ms (100ms poll loop + render time)

---

## Success Criteria

✅ **FR1** — Local SDR and API data sources both operational  
✅ **FR2** — Radar rendering: rings, crosshair, header — correct layout at 240×280  
✅ **FR3** — Aircraft arrows, callsigns (top 3), trails, ghost markers all rendered  
✅ **FR4** — Render + push completes in < 2 seconds on Pi Zero 2W  
✅ **FR5** — Error handling: no crashes on network loss or missing readsb file  
✅ **FR6** — Caching: API TTL cache and local 1-second read cache active  
✅ **FR7** — Trail history and dead-reckoning ghosts implemented and tested  
✅ **FR8** — Location auto-detection: IP geolocation → centroid → city lookup  
✅ **FR9** — RGB LED density indicator: 5-tier color scale updating on each frame  
✅ **FR10** — Flask web server daemon: all 5 endpoints functional including Leaflet `/map`  
✅ **NFR2** — Headless fallback mode: runs without physical WhisPlay hardware  
✅ **NFR3** — Long-running stability: handles network errors and signal dropouts gracefully
