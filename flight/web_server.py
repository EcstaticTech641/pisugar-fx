"""
flight/web_server.py

Mirrors the pisugar-fx radar display and aircraft data to any browser
on the same Wi-Fi network.

Endpoints
---------
  GET /              HTML radar mirror  (JPEG frame, auto-refreshes every 2 s)
  GET /snapshot.jpg  Current radar frame as JPEG
  GET /aircraft.json Filtered aircraft list as JSON (same data the display uses)
  GET /map           Leaflet.js interactive dark map (updates every 5 s)
  GET /status        JSON: location name, count, uptime
"""

from __future__ import annotations

import io
import json
import logging
import socket
import threading
import time
from typing import List, Optional

logger = logging.getLogger(__name__)


# ── SharedState ──────────────────────────────────────────────────────────────

class SharedState:
    """
    Thread-safe bridge between the display loop and the web server thread.

    The main loop calls update() after each render().
    Flask route handlers call get_jpeg() / get_aircraft() on each HTTP request.
    No locks are ever held across the network boundary.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpeg_bytes: Optional[bytes] = None
        self._aircraft: List[dict] = []
        self._location_name: str = "pisugar-fx"
        self.last_updated: float = 0.0
        self.start_time: float = time.time()

    def update(self, image, aircraft: List[dict], location_name: str) -> None:
        """
        Called from the controller after every render().

        Args:
            image:         PIL.Image.Image — the rendered radar frame
            aircraft:      distance-filtered aircraft list (same list display.py used)
            location_name: FlightRadarScreen.location_name
        """
        jpeg: Optional[bytes] = None
        try:
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=85)
            jpeg = buf.getvalue()
        except Exception as exc:
            logger.warning("[SharedState] JPEG encode failed: %s", exc)

        with self._lock:
            if jpeg is not None:
                self._jpeg_bytes = jpeg
            self._aircraft = list(aircraft)
            self._location_name = location_name
            self.last_updated = time.time()

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg_bytes

    def get_aircraft(self) -> List[dict]:
        with self._lock:
            return list(self._aircraft)

    @property
    def location_name(self) -> str:
        with self._lock:
            return self._location_name


# ── FlightWebServer ──────────────────────────────────────────────────────────

class FlightWebServer:
    """Lightweight Flask server running as a daemon thread alongside the main loop."""

    def __init__(self, shared_state: SharedState, port: int = 5000) -> None:
        self._state = shared_state
        self._port = port
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Non-blocking. Server runs in a daemon thread and exits when the main process does."""
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="pisugar-fx-webserver",
        )
        self._thread.start()
        ip = _get_local_ip()
        logger.info("[WebServer] Radar mirror:    http://%s:%d/", ip, self._port)
        logger.info("[WebServer] Interactive map: http://%s:%d/map", ip, self._port)

    def _run(self) -> None:
        try:
            from flask import Flask, Response, jsonify
        except ImportError:
            logger.error(
                "[WebServer] Flask not installed — web server disabled. "
                "Fix with:  pip install flask"
            )
            return

        app = Flask(__name__)
        # Suppress per-request Werkzeug access logs; pisugar-fx has its own logger
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        state = self._state  # closure alias

        @app.route("/")
        def index():
            return _html_index()

        @app.route("/snapshot.jpg")
        def snapshot():
            data = state.get_jpeg() or _blank_jpeg()
            return Response(
                data,
                mimetype="image/jpeg",
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
            )

        @app.route("/aircraft.json")
        def aircraft_json():
            return Response(
                json.dumps(state.get_aircraft(), indent=2),
                mimetype="application/json",
                headers={
                    "Cache-Control": "no-store",
                    "Access-Control-Allow-Origin": "*",
                },
            )

        @app.route("/map")
        def leaflet_map():
            return _html_map()

        @app.route("/status")
        def status():
            return jsonify({
                "location":       state.location_name,
                "aircraft_count": len(state.get_aircraft()),
                "last_updated":   state.last_updated,
                "uptime_seconds": round(time.time() - state.start_time, 1),
            })

        app.run(host="0.0.0.0", port=self._port, threaded=True, use_reloader=False)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_local_ip() -> str:
    """Best-effort LAN IP for the startup log message."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"


def _blank_jpeg() -> bytes:
    """240×280 black JPEG placeholder served before the first frame is ready."""
    try:
        from PIL import Image
        img = Image.new("RGB", (240, 280), (0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return b""


# ── HTML: Radar Mirror (/) ────────────────────────────────────────────────────

def _html_index() -> str:
    """Full-page radar mirror. JPEG refreshes every 2 s; status badge every 5 s."""
    return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>pisugar-fx &middot; Radar Mirror</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #080808; color: #d0d0d0;
      font-family: 'Courier New', monospace;
      display: flex; flex-direction: column; align-items: center;
      min-height: 100vh; padding: 24px 16px; gap: 18px;
    }
    h1 { color: #00ffcc; font-size: 1.1rem; letter-spacing: .2em; text-transform: uppercase; }
    .subtitle { color: #555; font-size: .72rem; margin-top: 4px; }
    .frame {
      border: 2px solid #1c4a3a; border-radius: 10px;
      padding: 10px; background: #000;
      box-shadow: 0 0 32px rgba(0,255,180,.12);
    }
    #radar { display: block; width: 240px; height: 280px; image-rendering: pixelated; }
    .meta { font-size: .68rem; color: #555; text-align: center; line-height: 2; }
    .live { color: #00ffcc; }
    .dim  { color: #888; }
    .pulse {
      display: inline-block; width: 7px; height: 7px; border-radius: 50%;
      background: #00ffcc; margin-right: 5px; vertical-align: middle;
      animation: pulse 2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%,100% { opacity: 1; box-shadow: 0 0 5px #00ffcc; }
      50%      { opacity: .2; box-shadow: none; }
    }
    nav { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
    nav a {
      color: #00ffcc; text-decoration: none;
      border: 1px solid #1c4a3a; padding: 7px 18px; border-radius: 5px;
      font-size: .78rem; transition: background .2s, border-color .2s;
    }
    nav a:hover { background: #1c4a3a; border-color: #00ffcc; }
  </style>
</head>
<body>
  <header style="text-align:center">
    <h1>&#x2708;&#xFE0F;&nbsp; pisugar-fx</h1>
    <div class="subtitle">Radar Mirror &nbsp;&middot;&nbsp; Live Display Feed</div>
  </header>

  <div class="frame">
    <img id="radar" src="/

  <div class="meta">
    <span class="pulse"></span>
    <span class="live" id="ac-count">&mdash;</span> aircraft &nbsp;&middot;&nbsp;
    <span class="live" id="location">&mdash;</span>
    <br>Refreshed: <span class="dim" id="ts">&mdash;</span>
  </div>

  <nav>
    /map&#x1F5FA;&nbsp; Interactive Map</a>
    /aircraft.json&#x1F4E1;&nbsp; Raw JSON</a>
    /status&#x2139;&#xFE0F;&nbsp; Status</a>
  </nav>

  <script>
    const radar = document.getElementById('radar');
    const acEl  = document.getElementById('ac-count');
    const locEl = document.getElementById('location');
    const tsEl  = document.getElementById('ts');

    function refreshImage() {
      // Timestamp query string busts browser cache every cycle
      radar.src = '/snapshot.jpg?t=' + Date.now();
    }

    async function refreshMeta() {
      try {
        const d = await (await fetch('/status')).json();
        acEl.textContent  = d.aircraft_count;
        locEl.textContent = d.location || '&mdash;';
        tsEl.textContent  = new Date().toLocaleTimeString();
      } catch (_) { /* server may not be ready yet */ }
    }

    setInterval(refreshImage, 2000);   // new JPEG every 2 s
    setInterval(refreshMeta,  5000);   // status badge every 5 s
    refreshMeta();
  </script>
</body>
</html>"""


# ── HTML: Leaflet Map (/map) ──────────────────────────────────────────────────

def _html_map() -> str:
    """
    Dark-themed Leaflet map.  Aircraft field names match the pisugar-fx
    normalized format confirmed in display.py:
      call, alt_ft, heading, on_ground, lat, lon, hex, gs
    """
    return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>pisugar-fx &middot; Live Map</title>
  <link rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossorigin="">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; background: #080808; }
    #map { width: 100%; height: 100vh; }
    .overlay {
      position: fixed; z-index: 1000;
      background: rgba(0,0,0,.82); border: 1px solid #1c4a3a; border-radius: 5px;
      color: #00ffcc; font-family: 'Courier New', monospace;
      font-size: .74rem; padding: 7px 16px;
    }
    #info-bar {
      top: 10px; left: 50%; transform: translateX(-50%);
      white-space: nowrap; pointer-events: none;
    }
    #back-btn { bottom: 14px; left: 14px; text-decoration: none; }
    #back-btn:hover { background: #1c4a3a; }
  </style>
</head>
<body>
  <div id="info-bar" class="overlay">
    &#x2708; pisugar-fx &nbsp;&middot;&nbsp; <span id="count">loading&hellip;</span>
  </div>
  <div id="map"></div>
  <a id="back-btn" class="overlay" href="/">&larr; Radar Mirror</a>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV/XN/WLs="
          crossorigin=""></script>
  <script>
    const map = L.map('map');

    // CartoDB Dark Matter — no API key required
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      subdomains: 'abcd', maxZoom: 14,
    }).addTo(map);

    // Rotated SVG aircraft arrow, same visual language as the radar display
    function makeIcon(color, heading) {
      const a = heading ?? 0;
      const svg = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
                + '<polygon points="12,2 16,20 12,16 8,20" fill="' + color
                + '" stroke="#000" stroke-width="1.2"/></svg>';
      return L.divIcon({
        html: '<div style="transform:rotate(' + a + 'deg);width:24px;height:24px">' + svg + '</div>',
        className: '',
        iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -14],
      });
    }

    const AIRBORNE = '#00ffcc';   // matches C_AIRCRAFT_AIR in display.py
    const GROUND   = '#ff8c00';   // matches C_AIRCRAFT_GND in display.py
    let markers = {}, centered = false;

    // Field names match the pisugar-fx normalized format (display.py confirmed):
    //   call, alt_ft, heading, on_ground, lat, lon   — definitely present
    //   hex, gs                                       — present if source.py passes them through
    function buildPopup(ac) {
      const name = ac.call    || ac.hex || '?';
      const alt  = ac.alt_ft  != null ? ac.alt_ft.toLocaleString()    + '&nbsp;ft'  : '&mdash;';
      const gs   = ac.gs      != null ? Math.round(ac.gs)             + '&nbsp;kt'  : '&mdash;';
      const hdg  = ac.heading != null ? Math.round(ac.heading)        + '&deg;'     : '&mdash;';
      return '<b style="font-family:monospace">' + name + '</b><br>'
           + '<small>ICAO:&nbsp;' + (ac.hex || '&mdash;') + '</small><br>'
           + 'Alt:&nbsp;' + alt + '&emsp;GS:&nbsp;' + gs + '&emsp;Hdg:&nbsp;' + hdg;
    }

    async function refresh() {
      try {
        const aircraft = await (await fetch('/aircraft.json')).json();
        document.getElementById('count').textContent =
          aircraft.length + ' aircraft in range';

        const seen = new Set();
        aircraft.forEach(ac => {
          if (ac.lat == null || ac.lon == null) return;
          const key   = ac.hex || (ac.lat + ':' + ac.lon);
          const color = ac.on_ground ? GROUND : AIRBORNE;
          const icon  = makeIcon(color, ac.heading);
          seen.add(key);

          if (markers[key]) {
            markers[key]
              .setLatLng([ac.lat, ac.lon])
              .setIcon(icon)
              .setPopupContent(buildPopup(ac));
          } else {
            markers[key] = L.marker([ac.lat, ac.lon], { icon })
              .bindPopup(buildPopup(ac))
              .addTo(map);
          }
        });

        // Remove aircraft that have left range
        for (const k of Object.keys(markers)) {
          if (!seen.has(k)) { map.removeLayer(markers[k]); delete markers[k]; }
        }

        // Center on first load — average of current aircraft, fall back to Stillwater
        if (!centered) {
          const pts = aircraft.filter(a => a.lat != null && a.lon != null);
          if (pts.length) {
            map.setView([
              pts.reduce((s, a) => s + a.lat, 0) / pts.length,
              pts.reduce((s, a) => s + a.lon, 0) / pts.length,
            ], 7);
          } else {
            map.setView([36.1156, -97.0584], 7);
          }
          centered = true;
        }
      } catch (e) { console.warn('[pisugar-fx] map refresh error:', e); }
    }

    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>"""