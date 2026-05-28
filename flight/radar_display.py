#!/usr/bin/env python3
"""
radar_display.py — Flight radar on the Whisplay 1.69" LCD (240x280)
Pulls from your local Flask /api/flights endpoint and draws a
50-100 mile radar ring view using Pillow, pushed via Whisplay.py.

Run from ~/flight-demo/:
    sudo python3 radar_display.py

Requires your Flask app (app.py) to already be running on port 5000.
"""

import sys
import time
import math
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ── Whisplay driver path ──────────────────────────────────────────────────────
sys.path.insert(0, "/home/aaron/Whisplay/Driver")
from Whisplay import Whisplay

# ── Display constants ─────────────────────────────────────────────────────────
W, H        = 240, 280          # physical LCD resolution
HEADER_H    = 36                # pixels reserved for top header bar
MAP_H       = H - HEADER_H     # 244px for the radar area
REFRESH_S   = 30                # seconds between API calls

# Radar geometry - centred in the map area
CX          = W // 2           # 120
CY          = HEADER_H + MAP_H // 2   # 36 + 122 = 158
RING_MILES  = [50, 100]        # rings to draw
# 100 mi fills ~90% of the shorter axis -> pixels per mile
PPM         = (min(W, MAP_H) // 2 - 10) / 100   # ~1.1 px/mi

# ── Colours (RGB tuples) ──────────────────────────────────────────────────────
C_BG        = (6,   11,  16)
C_HEADER    = (11,  20,  32)
C_RING_50   = (13,  42,  64)
C_RING_100  = (20,  60,  90)
C_RING_LBL  = (40,  90, 120)
C_CROSS     = (0,  229, 255)
C_PLANE     = (0,  229, 255)
C_GROUND    = (255, 107, 53)
C_CALL      = (200, 223, 240)
C_HDR_TEXT  = (0,  229, 255)
C_HDR_DIM   = (74, 112, 144)
C_DIVIDER   = (26,  58,  92)

# ── Fonts - falls back to default if no TTF found ────────────────────────────
def load_font(size):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()

FONT_SM  = load_font(9)
FONT_MED = load_font(11)
FONT_LG  = load_font(14)

# ── Coordinate helpers ────────────────────────────────────────────────────────
def geo_to_px(lat, lon, center_lat, center_lon):
    """Convert lat/lon to pixel coords relative to map centre."""
    dlat = lat - center_lat
    dlon = lon - center_lon
    mi_per_deg_lat = 69.0
    mi_per_deg_lon = 69.0 * math.cos(math.radians(center_lat))
    dx =  dlon * mi_per_deg_lon * PPM
    dy = -dlat * mi_per_deg_lat * PPM   # screen y is inverted
    return int(CX + dx), int(CY + dy)

def plane_arrow(draw, x, y, heading_deg, color, size=5):
    """Draw a tiny directional arrow for a plane."""
    rad = math.radians(heading_deg - 90)
    tip_x = x + size * math.cos(rad)
    tip_y = y + size * math.sin(rad)
    left_rad  = rad + math.radians(140)
    right_rad = rad - math.radians(140)
    lx = x + (size * 0.6) * math.cos(left_rad)
    ly = y + (size * 0.6) * math.sin(left_rad)
    rx = x + (size * 0.6) * math.cos(right_rad)
    ry = y + (size * 0.6) * math.sin(right_rad)
    draw.polygon(
        [(tip_x, tip_y), (lx, ly), (x, y), (rx, ry)],
        fill=color
    )

# ── Fetch flights from local Flask API ───────────────────────────────────────
def fetch_flights(lat, lon):
    try:
        r = requests.get(
            f"http://127.0.0.1:5000/api/flights?lat={lat}&lon={lon}",
            timeout=10
        )
        return r.json().get("flights", [])
    except Exception as e:
        print(f"[fetch error] {e}")
        return []

# ── Haversine distance in miles ───────────────────────────────────────────────
def distance_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

# ── Filter to 50-100 mile band ────────────────────────────────────────────────
def filter_band(flights, center_lat, center_lon, inner=50, outer=100):
    result = []
    for f in flights:
        if f.get("lat") and f.get("lon"):
            d = distance_miles(center_lat, center_lon, f["lat"], f["lon"])
            if inner <= d <= outer:
                result.append(f)
    return result

# ── Draw one full frame ───────────────────────────────────────────────────────
def draw_frame(flights, center_lat, center_lon):
    # Skip drawing if location is unknown
    if center_lat is None or center_lon is None:
        img = Image.new("RGB", (W, H), C_BG)
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (W, HEADER_H)], fill=C_HEADER)
        draw.line([(0, HEADER_H), (W, HEADER_H)], fill=C_DIVIDER, width=1)
        draw.text((6, 4), "RADAR", font=FONT_LG, fill=C_HDR_TEXT)
        draw.text((6, 20), "Unknown", font=FONT_SM, fill=C_HDR_DIM)
        draw.text((W - 72, 4), "— AC", font=FONT_LG, fill=C_HDR_TEXT)
        now_str = datetime.now().strftime("%H:%M:%S")
        draw.text((W - 72, 20), now_str, font=FONT_SM, fill=C_HDR_DIM)
        draw.line([(W // 2, 6), (W // 2, HEADER_H - 6)], fill=C_DIVIDER, width=1)
        return img

    img  = Image.new("RGB", (W, H), C_BG)
    draw = ImageDraw.Draw(img)

    now_str  = datetime.now().strftime("%H:%M:%S")
    band     = filter_band(flights, center_lat, center_lon)
    ac_count = len(band)

    # ── Header bar ────────────────────────────────────────────────────────────
    draw.rectangle([(0, 0), (W, HEADER_H)], fill=C_HEADER)
    draw.line([(0, HEADER_H), (W, HEADER_H)], fill=C_DIVIDER, width=1)

    draw.text((6, 4),  "RADAR",     font=FONT_LG, fill=C_HDR_TEXT)
    draw.text((6, 20), "50-100 mi", font=FONT_SM, fill=C_HDR_DIM)

    count_str = f"{ac_count} AC"
    draw.text((W - 72, 4),  count_str, font=FONT_LG, fill=C_HDR_TEXT)
    draw.text((W - 72, 20), now_str,   font=FONT_SM, fill=C_HDR_DIM)

    # Vertical divider in header
    draw.line([(W // 2, 6), (W // 2, HEADER_H - 6)], fill=C_DIVIDER, width=1)

    # ── Radar rings ───────────────────────────────────────────────────────────
    for miles, color in [(100, C_RING_100), (50, C_RING_50)]:
        r = int(miles * PPM)
        draw.ellipse(
            [(CX - r, CY - r), (CX + r, CY + r)],
            outline=color, width=1
        )
        draw.text(
            (CX + 3, CY - r + 2),
            f"{miles}mi",
            font=FONT_SM,
            fill=C_RING_LBL
        )

    # Faint cardinal spokes
    spoke_r = int(100 * PPM)
    spoke_color = (15, 35, 55)
    draw.line([(CX, CY - spoke_r), (CX, CY + spoke_r)], fill=spoke_color, width=1)
    draw.line([(CX - spoke_r, CY), (CX + spoke_r, CY)], fill=spoke_color, width=1)

    # ── Centre crosshair ──────────────────────────────────────────────────────
    cs = 5
    draw.line([(CX - cs, CY), (CX + cs, CY)], fill=C_CROSS, width=1)
    draw.line([(CX, CY - cs), (CX, CY + cs)], fill=C_CROSS, width=1)
    draw.ellipse([(CX - 2, CY - 2), (CX + 2, CY + 2)], fill=C_CROSS)

    # ── Plane markers ─────────────────────────────────────────────────────────
    for f in band:
        px, py = geo_to_px(f["lat"], f["lon"], center_lat, center_lon)

        # Skip if outside drawable screen area
        if not (4 < px < W - 4 and HEADER_H + 4 < py < H - 4):
            continue

        on_ground = f.get("on_ground", False)
        heading   = f.get("heading") or 0
        color     = C_GROUND if on_ground else C_PLANE

        plane_arrow(draw, px, py, heading, color, size=5)

        # Callsign - nudge right, clamp to screen
        call = (f.get("call") or f.get("icao") or "?")[:7]
        lx = min(px + 7, W - 32)
        ly = py - 5
        if ly < HEADER_H + 2:
            ly = py + 7
        draw.text((lx, ly), call, font=FONT_SM, fill=C_CALL)

    return img

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    # Location will be set via LocationProvider in future phases.
    # For now, this script requires manual configuration or should be updated
    # by the controller to receive location from IP geolocation or GPS.
    CENTER_LAT = None   # Will be provided by LocationProvider
    CENTER_LON = None

    print("[radar_display] Starting up...")
    print(f"[radar_display] Centre: {CENTER_LAT}, {CENTER_LON}")
    print(f"[radar_display] Ring: 50-100 miles | Refresh: {REFRESH_S}s")
    print("[radar_display] Waiting for Flask app on port 5000...")

    # Wait for Flask to be ready before first fetch
    for attempt in range(10):
        try:
            requests.get("http://127.0.0.1:5000/", timeout=2)
            print("[radar_display] Flask is up.")
            break
        except Exception:
            print(f"[radar_display] Flask not ready, retry {attempt + 1}/10...")
            time.sleep(3)

    disp = Whisplay()

    flights   = []
    last_fetch = 0

    while True:
        now = time.time()

        if now - last_fetch >= REFRESH_S:
            print("[radar_display] Fetching flights...")
            flights = fetch_flights(CENTER_LAT, CENTER_LON)
            last_fetch = now
            band_count = len(filter_band(flights, CENTER_LAT, CENTER_LON))
            print(f"[radar_display] {len(flights)} total, {band_count} in 50-100mi band")

        frame = draw_frame(flights, CENTER_LAT, CENTER_LON)
        disp.show_image(frame)

        # Redraw every second so the clock ticks live
        # without hitting the API each time
        time.sleep(1)

if __name__ == "__main__":
    main(