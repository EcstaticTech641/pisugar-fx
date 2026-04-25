from flask import Flask, jsonify, render_template_string, request
import requests

app = Flask(__name__)

# ── Bounding box from center + miles radius ───────────────────────────────────
def bbox(lat, lon, miles=200):
    import math
    deg_lat = miles / 69.0
    deg_lon = miles / (69.0 * abs(math.cos(math.radians(lat))))
    return lat - deg_lat, lon - deg_lon, lat + deg_lat, lon + deg_lon

# ── airplanes.live API ────────────────────────────────────────────────────────
def fetch_flights(lat, lon, miles=200):
    url = f"https://api.airplanes.live/v2/point/{lat}/{lon}/{miles}"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "OKC-Badge-Demo/1.0"})
        data = r.json()
        ac = data.get("ac", [])
        flights = []
        for a in ac:
            if a.get("lat") and a.get("lon"):
                flights.append({
                    "icao":      a.get("hex", ""),
                    "call":      (a.get("flight") or a.get("r") or "—").strip(),
                    "lat":       a.get("lat"),
                    "lon":       a.get("lon"),
                    "alt_ft":    a.get("alt_baro") or a.get("alt_geom") or 0,
                    "speed":     a.get("gs") or 0,
                    "heading":   a.get("track") or 0,
                    "type":      a.get("t") or "",
                    "reg":       a.get("r") or "",
                    "squawk":    a.get("squawk") or "",
                    "on_ground": a.get("alt_baro") == "ground",
                })
        return flights
    except Exception as e:
        print(f"[airplanes.live error] {e}")
        return []

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/api/flights")
def api_flights():
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
    except (TypeError, ValueError):
        lat, lon = 36.1156, -97.0584  # fallback: Stillwater, OK
    flights = fetch_flights(lat, lon, 200)
    return jsonify({"lat": lat, "lon": lon, "flights": flights})

@app.route("/")
def index():
    return render_template_string(HTML)

# ── HTML/CSS/JS (self-contained) ──────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>✈ OKC Aerospace Badge · Flight Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --bg:        #060b10;
    --panel:     #0b1420;
    --border:    #1a3a5c;
    --accent:    #00e5ff;
    --accent2:   #00ff88;
    --warn:      #ffaa00;
    --text:      #c8dff0;
    --dim:       #4a7090;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; background: var(--bg); color: var(--text);
    font-family: 'Share Tech Mono', monospace; overflow: hidden; }

  #app { display: grid; grid-template-rows: 48px 1fr; height: 100vh; }

  /* ── Header ── */
  #header {
    background: var(--panel); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 16px; padding: 0 18px; z-index: 1000;
  }
  #header .logo {
    font-family: 'Orbitron', sans-serif; font-weight: 900;
    font-size: 13px; letter-spacing: 3px; color: var(--accent);
    text-shadow: 0 0 12px var(--accent);
  }
  #header .sep { color: var(--border); }
  #loc-label { font-size: 11px; color: var(--dim); letter-spacing: 1px; }
  #count-badge {
    margin-left: auto; background: var(--accent); color: #000;
    font-family: 'Orbitron', sans-serif; font-size: 11px; font-weight: 700;
    padding: 2px 10px; border-radius: 2px; min-width: 60px; text-align: center;
  }
  #refresh-btn {
    background: none; border: 1px solid var(--border); color: var(--dim);
    font-family: 'Share Tech Mono', monospace; font-size: 11px;
    padding: 4px 12px; cursor: pointer; letter-spacing: 1px; transition: all .2s;
  }
  #refresh-btn:hover { border-color: var(--accent); color: var(--accent); }
  #status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--accent2); box-shadow: 0 0 8px var(--accent2);
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  /* ── Main ── */
  #main { display: grid; grid-template-columns: 1fr 280px; height: 100%; overflow: hidden; }
  #map { width: 100%; height: 100%; }
  .leaflet-container { background: #040910 !important; }

  /* ── Sidebar ── */
  #sidebar {
    background: var(--panel); border-left: 1px solid var(--border);
    display: flex; flex-direction: column; overflow: hidden;
  }
  #sidebar-header {
    padding: 10px 14px; font-family: 'Orbitron', sans-serif;
    font-size: 10px; letter-spacing: 2px; color: var(--dim);
    border-bottom: 1px solid var(--border);
  }
  #flight-list { flex: 1; overflow-y: auto; padding: 4px 0; }
  #flight-list::-webkit-scrollbar { width: 4px; }
  #flight-list::-webkit-scrollbar-track { background: var(--bg); }
  #flight-list::-webkit-scrollbar-thumb { background: var(--border); }

  .flight-row {
    padding: 8px 14px; border-bottom: 1px solid rgba(26,58,92,.4);
    cursor: pointer; transition: background .15s;
    display: grid; grid-template-columns: 1fr auto; gap: 2px;
  }
  .flight-row:hover { background: rgba(0,229,255,.06); }
  .flight-row.selected { background: rgba(0,229,255,.12); border-left: 2px solid var(--accent); }
  .fr-call { font-size: 13px; color: var(--accent); font-weight: bold; }
  .fr-type { font-size: 10px; color: var(--dim); }
  .fr-alt  { font-size: 11px; color: var(--accent2); text-align: right; }
  .fr-spd  { font-size: 10px; color: var(--dim); text-align: right; }

  /* ── Detail panel ── */
  #detail {
    border-top: 1px solid var(--border); padding: 12px 14px;
    font-size: 11px; min-height: 160px; background: rgba(0,0,0,.3);
  }
  #detail h3 { font-family: 'Orbitron', sans-serif; font-size: 12px;
    color: var(--accent); margin-bottom: 8px; letter-spacing: 1px; }
  .detail-row { display: flex; justify-content: space-between;
    padding: 3px 0; border-bottom: 1px solid rgba(26,58,92,.3); }
  .detail-key { color: var(--dim); }
  .detail-val { color: var(--text); }

  /* ── Geo denied banner ── */
  #geo-banner {
    display: none; position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
    background: var(--panel); border: 1px solid var(--warn); color: var(--warn);
    font-size: 11px; padding: 8px 18px; z-index: 2000; letter-spacing: 1px;
    box-shadow: 0 0 20px rgba(255,170,0,.2);
  }

  /* ── Loading overlay ── */
  #loading {
    position: fixed; inset: 0; background: var(--bg);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    z-index: 9999; transition: opacity .5s;
  }
  #loading .ld-logo { font-family: 'Orbitron', sans-serif; font-size: 28px;
    color: var(--accent); text-shadow: 0 0 30px var(--accent); margin-bottom: 12px; }
  #loading .ld-sub  { font-size: 12px; color: var(--dim); letter-spacing: 3px; }
  #loading .ld-note { font-size: 10px; color: var(--dim); margin-top: 8px; opacity: .6; }
  .spinner { width: 40px; height: 40px; border: 2px solid var(--border);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 1s linear infinite; margin-bottom: 20px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div id="loading">
  <div class="spinner"></div>
  <div class="ld-logo">✈ FLIGHT RADAR</div>
  <div class="ld-sub">ACQUIRING AIRCRAFT · 200 NM</div>
  <div class="ld-note">Allow location access when prompted for best results</div>
</div>

<div id="geo-banner">⚠ Location access denied — centered on Stillwater, OK (fallback)</div>

<div id="app">
  <div id="header">
    <div class="logo">OKC AEROSPACE BADGE</div>
    <div class="sep">|</div>
    <div id="loc-label">ACQUIRING POSITION…</div>
    <div id="status-dot"></div>
    <div id="count-badge">— AC</div>
    <button id="refresh-btn" onclick="refreshNow()">⟳ REFRESH</button>
  </div>
  <div id="main">
    <div id="map"></div>
    <div id="sidebar">
      <div id="sidebar-header">TRAFFIC · 200 NM RADIUS</div>
      <div id="flight-list"></div>
      <div id="detail">
        <h3>SELECT AIRCRAFT</h3>
        <div style="color:var(--dim);font-size:11px">Click a flight row or map marker for details.</div>
      </div>
    </div>
  </div>
</div>

<script>
// ── State ─────────────────────────────────────────────────────────────────────
let centerLat = 36.1156, centerLon = -97.0584;   // Stillwater fallback
let selected   = null;
let allFlights = [];
let markers    = {};

// ── Map ───────────────────────────────────────────────────────────────────────
const map = L.map('map', { zoomControl: true, attributionControl: false });
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  subdomains: 'abcd', maxZoom: 14
}).addTo(map);
map.setView([centerLat, centerLon], 7);

const ringLayer  = L.layerGroup().addTo(map);
const planeLayer = L.layerGroup().addTo(map);

// ── Range rings ───────────────────────────────────────────────────────────────
function drawRings(lat, lon) {
  ringLayer.clearLayers();
  [50, 100, 150, 200].forEach(mi => {
    L.circle([lat, lon], {
      radius: mi * 1609.34,
      color: '#0d2a40', weight: 1, fill: false, dashArray: '4 6', opacity: .8
    }).addTo(ringLayer);
    L.marker([lat + (mi / 69.0) * 0.92, lon], {
      icon: L.divIcon({
        html: `<span style="color:#1a3a5c;font-family:'Share Tech Mono',monospace;font-size:10px">${mi} mi</span>`,
        className: '', iconAnchor: [16, 8]
      })
    }).addTo(ringLayer);
  });
  L.circleMarker([lat, lon], {
    radius: 5, color: '#00e5ff', fillColor: '#00e5ff', fillOpacity: 1, weight: 0
  }).addTo(ringLayer);
}

// ── Plane icon ────────────────────────────────────────────────────────────────
function planeIcon(heading, onGround, isSelected) {
  const color = isSelected ? '#ffaa00' : (onGround ? '#ff6b35' : '#00e5ff');
  const glow  = isSelected ? '#ffaa00' : (onGround ? '#ff6b35' : '#00e5ff');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
    style="transform:rotate(${heading}deg);filter:drop-shadow(0 0 5px ${glow})">
    <path d="M12 2 L15 10 L22 12 L15 14 L13 21 L12 18 L11 21 L9 14 L2 12 L9 10 Z"
      fill="${color}" opacity="${onGround ? 0.6 : 1}"/>
  </svg>`;
  return L.divIcon({ html: svg, className: '', iconSize: [24,24], iconAnchor: [12,12] });
}

// ── Sidebar list ──────────────────────────────────────────────────────────────
function renderList(flights) {
  const list = document.getElementById('flight-list');
  list.innerHTML = '';
  flights.forEach(f => {
    const row = document.createElement('div');
    row.className = 'flight-row' + (selected === f.icao ? ' selected' : '');
    const alt = f.on_ground ? 'GND' : (f.alt_ft ? Number(f.alt_ft).toLocaleString()+' ft' : '—');
    const spd = f.speed ? Math.round(f.speed)+' kt' : '—';
    row.innerHTML = `
      <div>
        <div class="fr-call">${f.call || f.icao}</div>
        <div class="fr-type">${f.type || ''}${f.reg ? ' · '+f.reg : ''}</div>
      </div>
      <div>
        <div class="fr-alt">${alt}</div>
        <div class="fr-spd">${spd}</div>
      </div>`;
    row.addEventListener('click', () => selectFlight(f.icao));
    list.appendChild(row);
  });
}

// ── Detail panel ──────────────────────────────────────────────────────────────
function drow(k, v) {
  return `<div class="detail-row"><span class="detail-key">${k}</span><span class="detail-val">${v}</span></div>`;
}
function showDetail(f) {
  const alt = f.on_ground ? 'On Ground' : (f.alt_ft ? Number(f.alt_ft).toLocaleString()+' ft' : '—');
  document.getElementById('detail').innerHTML = `
    <h3>${f.call || f.icao}</h3>
    ${drow('ICAO',   f.icao)}
    ${drow('REG',    f.reg    || '—')}
    ${drow('TYPE',   f.type   || '—')}
    ${drow('ALT',    alt)}
    ${drow('SPEED',  f.speed  ? Math.round(f.speed)+' kt' : '—')}
    ${drow('HDG',    f.heading ? Math.round(f.heading)+'°' : '—')}
    ${drow('SQUAWK', f.squawk || '—')}
    ${drow('LAT',    f.lat    ? f.lat.toFixed(4) : '—')}
    ${drow('LON',    f.lon    ? f.lon.toFixed(4) : '—')}
  `;
}

// ── Select a flight ───────────────────────────────────────────────────────────
function selectFlight(icao) {
  selected = icao;
  const f = allFlights.find(x => x.icao === icao);
  if (!f) return;
  showDetail(f);
  renderList(allFlights);
  Object.entries(markers).forEach(([id, m]) => {
    const fl = allFlights.find(x => x.icao === id);
    if (fl) m.setIcon(planeIcon(fl.heading, fl.on_ground, id === icao));
  });
  map.panTo([f.lat, f.lon]);
}

// ── Fetch + render ────────────────────────────────────────────────────────────
async function loadFlights(lat, lon) {
  document.getElementById('status-dot').style.background = 'var(--warn)';
  try {
    const res = await fetch(`/api/flights?lat=${lat}&lon=${lon}`);
    const data = await res.json();
    allFlights = data.flights;

    document.getElementById('loc-label').textContent =
      `${lat.toFixed(3)}°N  ${Math.abs(lon).toFixed(3)}°W`;
    document.getElementById('count-badge').textContent = `${data.flights.length} AC`;

    drawRings(lat, lon);

    const incoming = new Set(data.flights.map(f => f.icao));
    Object.keys(markers).forEach(id => {
      if (!incoming.has(id)) { planeLayer.removeLayer(markers[id]); delete markers[id]; }
    });

    data.flights.forEach(f => {
      const icon = planeIcon(f.heading, f.on_ground, f.icao === selected);
      if (markers[f.icao]) {
        markers[f.icao].setLatLng([f.lat, f.lon]).setIcon(icon);
      } else {
        markers[f.icao] = L.marker([f.lat, f.lon], { icon })
          .addTo(planeLayer)
          .on('click', () => selectFlight(f.icao));
      }
    });

    renderList(data.flights);
    document.getElementById('status-dot').style.background = 'var(--accent2)';
  } catch(e) {
    console.error('[loadFlights]', e);
    document.getElementById('status-dot').style.background = '#ff4444';
  }
}

function refreshNow() { loadFlights(centerLat, centerLon); }

function hideLoader() {
  const ld = document.getElementById('loading');
  ld.style.opacity = '0';
  setTimeout(() => ld.style.display = 'none', 500);
}

// ── Boot: request browser location ───────────────────────────────────────────
(async () => {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      // ✅ Granted
      async (pos) => {
        centerLat = pos.coords.latitude;
        centerLon = pos.coords.longitude;
        map.setView([centerLat, centerLon], 7);
        await loadFlights(centerLat, centerLon);
        hideLoader();
      },
      // ❌ Denied or timed out — fall back to Stillwater
      async (err) => {
        console.warn('[geolocation denied]', err.message);
        const banner = document.getElementById('geo-banner');
        banner.style.display = 'block';
        setTimeout(() => banner.style.display = 'none', 6000);
        await loadFlights(centerLat, centerLon);
        hideLoader();
      },
      { timeout: 8000, maximumAge: 60000 }
    );
  } else {
    // No geolocation support
    await loadFlights(centerLat, centerLon);
    hideLoader();
  }

  // Auto-refresh every 30 seconds
  setInterval(() => loadFlights(centerLat, centerLon), 30000);
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)