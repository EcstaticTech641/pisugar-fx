"""
flight/web_server.py

Mirrors the pisugar-fx radar display and aircraft data to any browser
on the same Wi-Fi network.

Endpoints
---------
  GET /              HTML radar mirror (auto-refreshing image)
  GET /snapshot.jpg  Current radar frame as JPEG
  GET /aircraft.json Filtered aircraft list as JSON
  GET /map           Leaflet.js interactive map
  GET /status        JSON status object
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


# ---------------------------------------------------------------------------
# SharedState — written by main loop, read by web server thread
# ---------------------------------------------------------------------------

class SharedState:
    """
    Thread-safe bridge between the display loop and the web server.

    The main loop calls update() after each render.
    The web server calls get_jpeg() / get_aircraft() on each HTTP request.
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
        Call this from the controller after each radar render.

        Args:
            image:         PIL.Image.Image — the current rendered radar frame
            aircraft:      list of normalized aircraft dicts (already distance-filtered)
            location_name: display name for the current location
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


# ---------------------------------------------------------------------------
# FlightWebServer
# ---------------------------------------------------------------------------

class FlightWebServer:
    """
    Lightweight Flask server running as a background daemon thread.

    Usage:
        state  = SharedState()
        server = FlightWebServer(state, port=5000)
        server.start()
        # ... main loop calls state.update(image, aircraft, name) each frame
    """

    def __init__(self, shared_state: SharedState, port: int = 5000) -> None:
        self._state = shared_state
        self._port = port
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Non-blocking start. Server runs in a daemon thread."""
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="pisugar-fx-webserver",
        )
        self._thread.start()
        local_ip = _get_local_ip()
        logger.info("[WebServer] Radar mirror available at:")
        logger.info("[WebServer]   http://%s:%d        (radar)", local_ip, self._port)
        logger.info("[WebServer]   http://%s:%d/map    (interactive map)", local_ip, self._port)

    def _run(self) -> None:
        try:
            from flask import Flask, Response, jsonify
        except ImportError:
            logger.error(
                "[WebServer] Flask is not installed — web server disabled. "
                "Fix with: pip install flask"
            )
            return

        app = Flask(__name__)
        # Suppress per-request Werkzeug logs; pisugar-fx uses its own logger
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        state = self._state  # local alias for route closures

        # ── Routes ────────────────────────────────────────────────── #

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
            return jsonify(
                {
                    "location": state.location_name,
                    "aircraft_count": len(state.get_aircraft()),
                    "last_updated": state.last_updated,
                    "uptime_seconds": round(time.time() - state.start_time, 1),
                }
            )

        # ── Run ───────────────────────────────────────────────────── #
        app.run(
            host="0.0.0.0",
            port=self._port,
            threaded=True,
            use_reloader=False,
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _get_local_ip() -> str:
    """Best-effort local IP for startup log message."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"


def _blank_jpeg() -> bytes:
    """240×280 black JPEG placeholder shown before the first frame renders."""
    try:
        from PIL import Image

        img = Image.new("RGB", (240, 280), (0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return b""


# ---------------------------------------------------------------------------
# HTML — Radar Mirror (/)
# ---------------------------------------------------------------------------

def _html_index() -> str:
    return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>pisugar-fx · Radar Mirror</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #080808;
      color: #d0d0d0;
      font-family: 'Courier New', monospace;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 100vh;
      padding: 24px 16px;
      gap: 18px;
    }
    h1 { color: #00ffcc; font-size: 1.1rem; letter-spacing: 0.2em; text-transform: uppercase; }
    .subtitle { color: #555; font-size: 0.72rem; margin-top: 4px; }

    .frame {
      border: 2px solid #1c4a3a;
      border-radius: 10px;
      padding: 10px;
      background: #000;
      box-shadow: 0 0 32px rgba(0, 255, 180, 0.12);
    }
    #radar {
      display: block;
      width: 240px;
      height: 280px;
      image-rendering: pixelated;
    }

    .meta { font-size: 0.68rem; color: #555; text-align: center; line-height: 2; }
    .live { color: #00ffcc; }
    .dim  { color: #888; }

    .pulse {
      display: inline-block;
      width: 7px; height: 7px;
      border-radius: 50%;
      background: #00ffcc;
      margin-right: 5px;
      vertical-align: middle;
      animation: pulse 2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; box-shadow: 0 0 5px #00ffcc; }
      50%       { opacity: 0.2; box-shadow: none; }
    }

    nav { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
    nav a {
      color: #00ffcc;
      text-decoration: none;
      border: 1px solid #1c4a3a;
      padding: 7px 18px;
      border-radius: 5px;
      font-size: 0.78rem;
      transition: background 0.2s, border-color 0.2s;
    }
    nav a:hover { background: #1c4a3a; border-color: #00ffcc; }
  </style>
</head>
<body>
  <header style="text-align:center">
    <h1>✈&nbsp; pisugar-fx</h1>
    <div class="subtitle">Radar Mirror &nbsp;·&nbsp; Live Display Feed</div>
  </header>

  <div class="frame">
    <img id="radar" src="/snapshot.jpg" alt="Radar">
  </div>

  <div class="meta">
    <span class="pulse"></span>
    <span class="live" id="ac-count">—</span> aircraft &nbsp;·&nbsp;
    <span class="live" id="location">—</span>
    <br>
    Refreshed: <span class="dim" id="ts">—</span>
  </div>

  <nav>
    <a href="/map">🗺&nbsp; Interactive Map</a>
    <a href="/aircraft.json">📡&nbsp; Raw JSON</a>
    <a href="/status">ℹ️&nbsp; Status</a>
  </nav>

  <script>
    const radar = document.getElementById('radar');
    const acEl  = document.getElementById('ac-count');
    const locEl = document.getElementById('location');
    const tsEl  = document.getElementById('ts');

    function refreshImage() {
      // Cache-bust with timestamp so browser always fetches the latest frame
      radar.src = '/snapshot.jpg?t=' + Date.now();
    }

    async function refreshMeta() {
      try {
        const d = await (await fetch('/status')).json();
        acEl.textContent  = d.aircraft_count;
        locEl.textContent = d.location || '—';
        tsEl.textContent  = new Date().toLocaleTimeString();
      } catch (_) {}
    }

    setInterval(refreshImage, 2000);  // new frame every 2 s
    setInterval(refreshMeta,  5000);  // status every 5 s
    refreshMeta();
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTML — Leaflet Map (/map)
# ---------------------------------------------------------------------------

def _html_map() -> str:
    return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>pisugar-fx · Live Map</title>
  <link rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; background: #080808; }
    #map { width: 100%; height: 100vh; }

    .overlay {
      position: fixed; z-index: 1000;
      background: rgba(0,0,0,0.82);
      border: 1px solid #1c4a3a;
      border-radius: 5px;
      color: #00ffcc;
      font-family: 'Courier New', monospace;
      font-size: 0.74rem;
      padding: 7px 16px;
    }
    #info-bar {
      top: 10px; left: 50%; transform: translateX(-50%);
      white-space: nowrap; pointer-events: none;
    }
    #back-btn {
      bottom: 14px; left: 14px;
      text-decoration: none;
    }
    #back-btn:hover { background: #1c4a3a; }
  </style>
</head>
<body>
  <div id="info-bar" class="overlay">
    ✈ pisugar-fx &nbsp;·&nbsp; <span id="count">loading…</span>
  </div>
  <div id="map"></div>
  <a id="back-btn" class="overlay" href="/">← Radar Mirror</a>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV/XN/WLs=" crossorigin=""></script>
  <script>
    const map = L.map('map');

    // Dark base tiles (CartoDB Dark Matter — no API key required)
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      { attribution: '© OpenStreetMap © CARTO', subdomains: 'abcd', maxZoom: 14 }
    ).addTo(map);

    // Rotated SVG aircraft arrow icon
    function makeIcon(color, heading) {
      const angle = heading ?? 0;
      return L.divIcon({
        html: `<div style="transform:rotate(${angle}deg);width:24px;height:24px">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <polygon points="12,2 16,20 12,16 8,20"
              fill="${color}" stroke="#000" stroke-width="1.2"/>
          </svg></div>`,
        className: '',
        iconSize:   [24, 24],
        iconAnchor: [12, 12],
        popupAnchor:[0, -14],
      });
    }

    const AIRBORNE = '#00ffcc';
    const GROUND   = '#ff8c00';

    let markers  = {};
    let centered = false;

    function buildPopup(ac) {
      const alt = ac.alt_baro != null ? ac.alt_baro.toLocaleString() + ' ft' : '—';
      const gs  = ac.gs       != null ? Math.round(ac.gs)    + ' kt'         : '—';
      const hdg = ac.track    != null ? Math.round(ac.track) + '°'           : '—';
      return `<b style="font-family:monospace">${ac.flight || ac.hex || '?'}</b><br>
              <small>ICAO: ${ac.hex || '—'}</small><br>
              Alt: ${alt} &nbsp; GS: ${gs} &nbsp; Hdg: ${hdg}`;
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
          const color = ac.airborne === false ? GROUND : AIRBORNE;
          const icon  = makeIcon(color, ac.track);
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

        // Remove aircraft no longer in range
        for (const k of Object.keys(markers)) {
          if (!seen.has(k)) { map.removeLayer(markers[k]); delete markers[k]; }
        }

        // Center map on first load
        if (!centered) {
          const pts = aircraft.filter(a => a.lat != null && a.lon != null);
          if (pts.length) {
            const lat = pts.reduce((s, a) => s + a.lat, 0) / pts.length;
            const lon = pts.reduce((s, a) => s + a.lon, 0) / pts.length;
            map.setView([lat, lon], 7);
          } else {
            map.setView([36.1156, -97.0584], 7);  // Stillwater fallback
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