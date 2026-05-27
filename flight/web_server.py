"""
flight/web_server.py

Mirrors the pisugar-fx radar display and aircraft data to any browser
on the same Wi-Fi network.

Endpoints
---------
  GET /              HTML radar mirror  (JPEG frame, auto-refreshes every 2 s)
  GET /snapshot.jpg  Current radar frame as JPEG
  GET /aircraft.json Filtered aircraft list as JSON
  GET /map           Leaflet.js interactive dark map with click-to-detail panel
  GET /status        JSON: location name, count, uptime
"""

from __future__ import annotations
import io, json, logging, socket, threading, time
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SharedState
# ---------------------------------------------------------------------------
class SharedState:
    """Thread-safe bridge between the display loop and the web server thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpeg_bytes: Optional[bytes] = None
        self._aircraft: List[dict] = []
        self._location_name: str = "pisugar-fx"
        self.last_updated: float = 0.0
        self.start_time: float = time.time()

    def update(self, image, aircraft: List[dict], location_name: str) -> None:
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
        with self._lock: return self._jpeg_bytes

    def get_aircraft(self) -> List[dict]:
        with self._lock: return list(self._aircraft)

    @property
    def location_name(self) -> str:
        with self._lock: return self._location_name


# ---------------------------------------------------------------------------
# FlightWebServer
# ---------------------------------------------------------------------------
class FlightWebServer:
    """Lightweight Flask server running as a daemon thread alongside the main loop."""

    def __init__(self, shared_state: SharedState, port: int = 5000) -> None:
        self._state = shared_state
        self._port  = port
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="pisugar-fx-webserver")
        self._thread.start()
        ip = _get_local_ip()
        logger.info("[WebServer] Radar mirror:    http://%s:%d/", ip, self._port)
        logger.info("[WebServer] Interactive map: http://%s:%d/map", ip, self._port)

    def _run(self) -> None:
        try:
            from flask import Flask, Response, jsonify
        except ImportError:
            logger.error("[WebServer] Flask not installed. Fix: pip install flask")
            return
        app = Flask(__name__)
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        state = self._state

        @app.route("/")
        def index(): return _html_index()

        @app.route("/snapshot.jpg")
        def snapshot():
            data = state.get_jpeg() or _blank_jpeg()
            return Response(data, mimetype="image/jpeg",
                            headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

        @app.route("/aircraft.json")
        def aircraft_json():
            return Response(json.dumps(state.get_aircraft(), indent=2),
                            mimetype="application/json",
                            headers={"Cache-Control": "no-store",
                                     "Access-Control-Allow-Origin": "*"})

        @app.route("/map")
        def leaflet_map(): return _html_map()

        @app.route("/status")
        def status():
            return jsonify({"location":       state.location_name,
                            "aircraft_count": len(state.get_aircraft()),
                            "last_updated":   state.last_updated,
                            "uptime_seconds": round(time.time() - state.start_time, 1)})

        app.run(host="0.0.0.0", port=self._port, threaded=True, use_reloader=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"


def _blank_jpeg() -> bytes:
    try:
        from PIL import Image
        img = Image.new("RGB", (240, 280), (0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return b""


# ---------------------------------------------------------------------------
# HTML templates — stored as plain Python strings with real < > characters.
# Never copy these from a rendered chat message; always use the file download.
# ---------------------------------------------------------------------------
def _html_index() -> str:
    return '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>pisugar-fx &middot; Radar Mirror</title>\n  <style>\n    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n    body {\n      background: #080808; color: #d0d0d0;\n      font-family: \'Courier New\', monospace;\n      display: flex; flex-direction: column; align-items: center;\n      min-height: 100vh; padding: 24px 16px; gap: 18px;\n    }\n    h1 { color: #00ffcc; font-size: 1.1rem; letter-spacing: .2em; text-transform: uppercase; }\n    .subtitle { color: #555; font-size: .72rem; margin-top: 4px; }\n    .frame {\n      border: 2px solid #1c4a3a; border-radius: 10px;\n      padding: 10px; background: #000;\n      box-shadow: 0 0 32px rgba(0,255,180,.12);\n    }\n    .meta { font-size: .68rem; color: #555; text-align: center; line-height: 2; }\n    .live { color: #00ffcc; }\n    .dim  { color: #888; }\n    .pulse {\n      display: inline-block; width: 7px; height: 7px; border-radius: 50%;\n      background: #00ffcc; margin-right: 5px; vertical-align: middle;\n      animation: pulse 2s ease-in-out infinite;\n    }\n    @keyframes pulse {\n      0%,100% { opacity: 1; box-shadow: 0 0 5px #00ffcc; }\n      50%      { opacity: .2; box-shadow: none; }\n    }\n    nav { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }\n    nav a {\n      color: #00ffcc; text-decoration: none;\n      border: 1px solid #1c4a3a; padding: 7px 18px; border-radius: 5px;\n      font-size: .78rem; transition: background .2s, border-color .2s;\n    }\n    nav a:hover { background: #1c4a3a; border-color: #00ffcc; }\n  </style>\n</head>\n<body>\n  <header style="text-align:center">\n    <h1>&#x2708;&#xFE0F;&nbsp; pisugar-fx</h1>\n    <div class="subtitle">Radar Mirror &nbsp;&middot;&nbsp; Live Display Feed</div>\n  </header>\n\n  <div class="frame">\n    <img id="radar" src="/snapshot.jpg" alt="Radar display"\n         width="240" height="280"\n         style="display:block;image-rendering:pixelated;">\n  </div>\n\n  <div class="meta">\n    <span class="pulse"></span>\n    <span class="live" id="ac-count">&mdash;</span> aircraft &nbsp;&middot;&nbsp;\n    <span class="live" id="location">&mdash;</span>\n    <br>Refreshed: <span class="dim" id="ts">&mdash;</span>\n  </div>\n\n  <nav>\n    <a href="/map">&#x1F5FA;&#xFE0F;&nbsp; Interactive Map</a>\n    <a href="/aircraft.json">&#x1F4E1;&nbsp; Aircraft JSON</a>\n    <a href="/status">&#x2139;&#xFE0F;&nbsp; Status</a>\n  </nav>\n\n  <script>\n    const radar = document.getElementById(\'radar\');\n    const acEl  = document.getElementById(\'ac-count\');\n    const locEl = document.getElementById(\'location\');\n    const tsEl  = document.getElementById(\'ts\');\n\n    function refreshImage() {\n      radar.src = \'/snapshot.jpg?t=\' + Date.now();\n    }\n\n    async function refreshMeta() {\n      try {\n        const d = await (await fetch(\'/status\')).json();\n        acEl.textContent  = d.aircraft_count;\n        locEl.textContent = d.location || \'—\';\n        tsEl.textContent  = new Date().toLocaleTimeString();\n      } catch (_) {}\n    }\n\n    setInterval(refreshImage, 2000);\n    setInterval(refreshMeta,  5000);\n    refreshMeta();\n  </script>\n</body>\n</html>'


def _html_map() -> str:
    return '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>pisugar-fx &middot; Live Map</title>\n  <link rel="stylesheet"\n        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"\n        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="\n        crossorigin="">\n  <style>\n    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n    html, body {\n      height: 100%; background: #080808;\n      font-family: \'Courier New\', monospace; overflow: hidden;\n    }\n    #app { display: flex; height: 100vh; width: 100vw; }\n    #map-wrap { flex: 1; position: relative; }\n    #map { width: 100%; height: 100%; }\n    #detail {\n      width: 0; min-width: 0; overflow: hidden;\n      background: #0b1520; border-left: 1px solid #1c4a3a;\n      display: flex; flex-direction: column;\n      transition: width .3s ease, min-width .3s ease;\n    }\n    #detail.open { width: 300px; min-width: 260px; }\n    #detail-inner { padding: 16px; overflow-y: auto; flex: 1; }\n    .panel-header {\n      display: flex; justify-content: space-between; align-items: flex-start;\n      margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid #1c4a3a;\n    }\n    .callsign { color: #00ffcc; font-size: 1.4rem; font-weight: bold; letter-spacing: .08em; line-height: 1.1; }\n    .icao { color: #4a6070; font-size: .7rem; margin-top: 3px; }\n    .close-btn {\n      background: none; border: 1px solid #1c4a3a; color: #00ffcc;\n      border-radius: 4px; padding: 3px 8px; cursor: pointer;\n      font-family: \'Courier New\', monospace; font-size: .75rem;\n      flex-shrink: 0; margin-left: 8px; transition: background .2s;\n    }\n    .close-btn:hover { background: #1c4a3a; }\n    .badge {\n      display: inline-block; padding: 2px 10px; border-radius: 10px;\n      font-size: .68rem; font-weight: bold; margin-bottom: 14px;\n      letter-spacing: .1em; text-transform: uppercase;\n    }\n    .badge.airborne  { background: rgba(0,255,204,.15); color: #00ffcc; border: 1px solid #00ffcc44; }\n    .badge.ground    { background: rgba(255,140,0,.15);  color: #ff8c00; border: 1px solid #ff8c0044; }\n    .badge.emergency {\n      background: rgba(255,50,50,.25); color: #ff4444;\n      border: 1px solid #ff444488; animation: blink 1s step-start infinite;\n    }\n    @keyframes blink { 50% { opacity: .4; } }\n    .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }\n    .card { background: #0f1e2e; border: 1px solid #1c4a3a; border-radius: 6px; padding: 8px 10px; }\n    .card-label { color: #4a7090; font-size: .62rem; text-transform: uppercase; letter-spacing: .1em; }\n    .card-value { color: #c8dff0; font-size: .95rem; margin-top: 2px; }\n    .card-value.warn { color: #ff4444; font-weight: bold; }\n    .info-table { width: 100%; border-collapse: collapse; font-size: .72rem; }\n    .info-table td { padding: 5px 4px; border-bottom: 1px solid #111e2a; }\n    .info-table td:first-child { color: #4a7090; width: 44%; }\n    .info-table td:last-child  { color: #c8dff0; }\n    #info-bar {\n      position: absolute; z-index: 1000;\n      top: 10px; left: 50%; transform: translateX(-50%);\n      background: rgba(0,0,0,.82); border: 1px solid #1c4a3a; border-radius: 5px;\n      color: #00ffcc; font-size: .74rem; padding: 7px 16px;\n      white-space: nowrap; pointer-events: none;\n    }\n    #back-btn {\n      position: absolute; z-index: 1000; bottom: 14px; left: 14px;\n      background: rgba(0,0,0,.82); border: 1px solid #1c4a3a; border-radius: 5px;\n      color: #00ffcc; font-size: .74rem; padding: 7px 16px;\n      text-decoration: none; transition: background .2s;\n    }\n    #back-btn:hover { background: #1c4a3a; }\n    @media (max-width: 600px) {\n      #app { flex-direction: column; }\n      #detail {\n        width: 100%; min-width: 0; height: 0;\n        border-left: none; border-top: 1px solid #1c4a3a;\n        transition: height .3s ease;\n      }\n      #detail.open { width: 100%; height: 55vh; }\n    }\n  </style>\n</head>\n<body>\n  <div id="app">\n    <div id="map-wrap">\n      <div id="map"></div>\n      <div id="info-bar">&#x2708; pisugar-fx &nbsp;&middot;&nbsp; <span id="count">loading&hellip;</span></div>\n      <a id="back-btn" href="/">&larr; Radar Mirror</a>\n    </div>\n    <div id="detail">\n      <div id="detail-inner">\n        <div class="panel-header">\n          <div>\n            <div class="callsign" id="d-call">---</div>\n            <div class="icao"     id="d-icao">ICAO: ---</div>\n          </div>\n          <button class="close-btn" onclick="closeDetail()">&#x2715; Close</button>\n        </div>\n        <div id="d-badge" class="badge airborne">Airborne</div>\n        <div class="cards">\n          <div class="card"><div class="card-label">Altitude</div><div class="card-value" id="d-alt">---</div></div>\n          <div class="card"><div class="card-label">Gnd Speed</div><div class="card-value" id="d-gs">---</div></div>\n          <div class="card"><div class="card-label">Heading</div><div class="card-value" id="d-hdg">---</div></div>\n          <div class="card"><div class="card-label">Squawk</div><div class="card-value" id="d-squawk">---</div></div>\n        </div>\n        <table class="info-table">\n          <tbody>\n            <tr><td>Distance</td>     <td id="d-dist">---</td></tr>\n            <tr><td>Category</td>     <td id="d-cat">---</td></tr>\n            <tr><td>Messages</td>     <td id="d-msg">---</td></tr>\n            <tr><td>Signal (RSSI)</td><td id="d-rssi">---</td></tr>\n            <tr><td>Last seen</td>    <td id="d-seen">---</td></tr>\n          </tbody>\n        </table>\n      </div>\n    </div>\n  </div>\n\n  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"\n          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV/XN/WLs="\n          crossorigin=""></script>\n  <script>\n    const map = L.map(\'map\');\n    L.tileLayer(\'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png\', {\n      attribution: \'© OpenStreetMap © CARTO\',\n      subdomains: \'abcd\', maxZoom: 14,\n    }).addTo(map);\n\n    const AIRBORNE = \'#00ffcc\';\n    const GROUND   = \'#ff8c00\';\n    const EMERGENCY_SQUAWKS = new Set([\'7500\',\'7600\',\'7700\']);\n\n    function makeIcon(color, heading) {\n      const a = heading ?? 0;\n      const svg = \'<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">\'\n                + \'<polygon points="12,2 16,20 12,16 8,20" fill="\' + color\n                + \'" stroke="#000" stroke-width="1.2"/></svg>\';\n      return L.divIcon({\n        html: \'<div style="transform:rotate(\' + a + \'deg);width:24px;height:24px">\' + svg + \'</div>\',\n        className: \'\', iconSize: [24,24], iconAnchor: [12,12], popupAnchor: [0,-14],\n      });\n    }\n\n    const detail = document.getElementById(\'detail\');\n    let selectedKey = null;\n\n    function fmt(v, unit) {\n      if (v == null || v === \'\') return \'—\';\n      return unit ? v + \'\xa0\' + unit : String(v);\n    }\n\n    function squawkLabel(sq) {\n      if (!sq) return \'—\';\n      const labels = {\n        \'7500\': \'7500 ⚠ HIJACK\',\n        \'7600\': \'7600 ⚠ RADIO FAIL\',\n        \'7700\': \'7700 ⚠ EMERGENCY\',\n      };\n      return labels[String(sq)] || String(sq);\n    }\n\n    function openDetail(ac) {\n      selectedKey = ac.hex || (ac.lat + \':\' + ac.lon);\n      const isGround    = ac.on_ground === true;\n      const isEmergency = EMERGENCY_SQUAWKS.has(String(ac.squawk || \'\'));\n\n      document.getElementById(\'d-call\').textContent = ac.call || ac.hex || \'Unknown\';\n      document.getElementById(\'d-icao\').textContent = \'ICAO: \' + (ac.hex || \'---\');\n\n      const badge = document.getElementById(\'d-badge\');\n      if (isEmergency) {\n        badge.className = \'badge emergency\';\n        badge.textContent = \'⚠ EMERGENCY\';\n      } else if (isGround) {\n        badge.className = \'badge ground\';\n        badge.textContent = \'On Ground\';\n      } else {\n        badge.className = \'badge airborne\';\n        badge.textContent = \'Airborne\';\n      }\n\n      document.getElementById(\'d-alt\').textContent  =\n        ac.alt_ft != null ? ac.alt_ft.toLocaleString() + \'\xa0ft\' : \'—\';\n      document.getElementById(\'d-gs\').textContent   =\n        ac.gs != null ? Math.round(ac.gs) + \'\xa0kt\' : \'—\';\n      document.getElementById(\'d-hdg\').textContent  =\n        ac.heading != null ? Math.round(ac.heading) + \'°\' : \'—\';\n\n      const squawkEl = document.getElementById(\'d-squawk\');\n      squawkEl.textContent = squawkLabel(ac.squawk);\n      squawkEl.className   = \'card-value\' + (isEmergency ? \' warn\' : \'\');\n\n      document.getElementById(\'d-dist\').textContent =\n        ac.distance_miles != null ? ac.distance_miles.toFixed(1) + \'\xa0mi\' : \'—\';\n      document.getElementById(\'d-cat\').textContent  = fmt(ac.category);\n      document.getElementById(\'d-msg\').textContent  = fmt(ac.messages);\n      document.getElementById(\'d-rssi\').textContent =\n        ac.rssi != null ? ac.rssi.toFixed(1) + \'\xa0dBFS\' : \'—\';\n      document.getElementById(\'d-seen\').textContent =\n        ac.seen != null ? ac.seen.toFixed(1) + \'\xa0s ago\' : \'—\';\n\n      detail.classList.add(\'open\');\n      setTimeout(() => map.invalidateSize(), 320);\n    }\n\n    function closeDetail() {\n      selectedKey = null;\n      detail.classList.remove(\'open\');\n      setTimeout(() => map.invalidateSize(), 320);\n    }\n\n    let markers = {}, centered = false;\n\n    async function refresh() {\n      try {\n        const aircraft = await (await fetch(\'/aircraft.json\')).json();\n        document.getElementById(\'count\').textContent =\n          aircraft.length + \' aircraft in range\';\n\n        const seen = new Set();\n        aircraft.forEach(ac => {\n          if (ac.lat == null || ac.lon == null) return;\n          const key   = ac.hex || (ac.lat + \':\' + ac.lon);\n          const color = ac.on_ground ? GROUND : AIRBORNE;\n          const icon  = makeIcon(color, ac.heading);\n          seen.add(key);\n\n          if (markers[key]) {\n            markers[key].setLatLng([ac.lat, ac.lon]).setIcon(icon);\n            markers[key]._acData = ac;\n          } else {\n            const m = L.marker([ac.lat, ac.lon], { icon });\n            m._acData = ac;\n            m.on(\'click\', () => openDetail(m._acData));\n            m.addTo(map);\n            markers[key] = m;\n          }\n          if (key === selectedKey) openDetail(ac);\n        });\n\n        for (const k of Object.keys(markers)) {\n          if (!seen.has(k)) {\n            map.removeLayer(markers[k]);\n            delete markers[k];\n            if (k === selectedKey) closeDetail();\n          }\n        }\n\n        if (!centered) {\n          const pts = aircraft.filter(a => a.lat != null && a.lon != null);\n          if (pts.length) {\n            map.setView([\n              pts.reduce((s, a) => s + a.lat, 0) / pts.length,\n              pts.reduce((s, a) => s + a.lon, 0) / pts.length,\n            ], 7);\n          } else {\n            map.setView([36.1156, -97.0584], 7);\n          }\n          centered = true;\n        }\n      } catch (e) { console.warn(\'[pisugar-fx] map refresh error:\', e); }\n    }\n\n    refresh();\n    setInterval(refresh, 5000);\n  </script>\n</body>\n</html>'


if __name__ == "__main__":
    idx = _html_index()
    mp  = _html_map()
    assert "<img "               in idx, "index: img tag missing"
    assert 'href="/map"'        in idx, "index: /map link missing"
    assert 'href="/aircraft.json"' in idx, "index: aircraft link missing"
    assert 'href="/status"'     in idx, "index: status link missing"
    assert "leaflet"             in mp.lower(), "map: leaflet missing"
    assert "openDetail"          in mp, "map: openDetail missing"
    assert "closeDetail"         in mp, "map: closeDetail missing"
    assert "d-squawk"            in mp, "map: squawk element missing"
    assert "d-rssi"              in mp, "map: rssi element missing"
    assert "&lt;"               not in idx, "CORRUPTED: HTML entities in index"
    assert "&lt;"               not in mp,  "CORRUPTED: HTML entities in map"
    print("All smoke tests passed.")
    print(f"  _html_index(): {len(idx):,} chars")
    print(f"  _html_map():   {len(mp):,} chars")
