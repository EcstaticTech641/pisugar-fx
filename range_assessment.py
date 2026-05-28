#!/usr/bin/env python3
"""
range_assessment.py — Antenna range assessment for pisugar-fx.

Samples /run/readsb/aircraft.json repeatedly over a collection window,
then reports max/average range and RSSI statistics to help tune
radius_miles and display ring labels.

Usage:
    python3 range_assessment.py [--duration 300] [--interval 5] [--lat LAT] [--lon LON]
    
    Note: --lat and --lon are required (no hardcoded defaults)
"""

import argparse
import json
import math
import time
import sys
from collections import defaultdict


# --- Haversine distance (miles) -------------------------------------------

def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# --- Single sample -----------------------------------------------------------

def sample(home_lat, home_lon, json_path="/run/readsb/aircraft.json"):
    """Read aircraft.json and return list of (hex, flight, distance_miles, rssi)."""
    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [warn] Could not read {json_path}: {e}", file=sys.stderr)
        return []

    results = []
    for ac in data.get("aircraft", []):
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue  # no position fix yet
        dist = haversine_miles(home_lat, home_lon, lat, lon)
        rssi = ac.get("rssi")
        flight = ac.get("flight", ac.get("hex", "?")).strip()
        results.append((ac["hex"], flight, dist, rssi))
    return results


# --- Main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Assess RTL-SDR antenna range.")
    parser.add_argument("--duration", type=int, default=300,
                        help="Collection window in seconds (default: 300)")
    parser.add_argument("--interval", type=int, default=5,
                        help="Sample interval in seconds (default: 5)")
    parser.add_argument("--lat", type=float, required=True,
                        help="Home latitude (required)")
    parser.add_argument("--lon", type=float, required=True,
                        help="Home longitude (required)")
    parser.add_argument("--json", default="/run/readsb/aircraft.json",
                        help="Path to aircraft.json (default: /run/readsb/aircraft.json)")
    args = parser.parse_args()

    print(f"Antenna Range Assessment")
    print(f"  Home: {args.lat:.4f}, {args.lon:.4f}")
    print(f"  Collecting for {args.duration}s, sampling every {args.interval}s")
    print(f"  Press Ctrl+C to stop early and see results.\n")

    # Per-aircraft: track max distance and all rssi readings
    aircraft_max_dist = {}       # hex -> max distance seen
    aircraft_best_rssi = {}      # hex -> best (least negative) rssi
    aircraft_flight = {}         # hex -> callsign
    aircraft_distances = defaultdict(list)  # hex -> [dist, ...]

    all_distances = []
    sample_count = 0
    start = time.time()

    try:
        while time.time() - start < args.duration:
            elapsed = time.time() - start
            contacts = sample(args.lat, args.lon, args.json)
            sample_count += 1

            for hex_id, flight, dist, rssi in contacts:
                aircraft_flight[hex_id] = flight
                aircraft_distances[hex_id].append(dist)
                all_distances.append(dist)
                if hex_id not in aircraft_max_dist or dist > aircraft_max_dist[hex_id]:
                    aircraft_max_dist[hex_id] = dist
                if rssi is not None:
                    if hex_id not in aircraft_best_rssi or rssi > aircraft_best_rssi[hex_id]:
                        aircraft_best_rssi[hex_id] = rssi

            # Progress line
            n = len(contacts)
            far = max((d for _, _, d, _ in contacts), default=0)
            print(f"  [{elapsed:5.0f}s] {n:3d} contacts  farthest this sample: {far:5.1f} mi", end="\r")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n  (stopped early)")

    print(f"\n\n{'='*55}")
    print(f"  Results after {sample_count} samples")
    print(f"{'='*55}")

    if not all_distances:
        print("  No aircraft with position fixes observed.")
        return

    max_dist = max(all_distances)
    avg_dist = sum(all_distances) / len(all_distances)
    median_dist = sorted(all_distances)[len(all_distances) // 2]
    p90_dist = sorted(all_distances)[int(len(all_distances) * 0.9)]

    print(f"  Total position fixes : {len(all_distances)}")
    print(f"  Unique aircraft      : {len(aircraft_max_dist)}")
    print(f"  Max range            : {max_dist:.1f} mi")
    print(f"  90th percentile      : {p90_dist:.1f} mi")
    print(f"  Median range         : {median_dist:.1f} mi")
    print(f"  Average range        : {avg_dist:.1f} mi")

    # Top 10 farthest aircraft
    print(f"\n  Top 10 farthest contacts:")
    print(f"  {'Callsign':<12} {'Max dist (mi)':>14} {'Best RSSI (dBFS)':>17}")
    print(f"  {'-'*12} {'-'*14} {'-'*17}")
    top10 = sorted(aircraft_max_dist.items(), key=lambda x: x[1], reverse=True)[:10]
    for hex_id, dist in top10:
        flight = aircraft_flight.get(hex_id, hex_id)
        rssi = aircraft_best_rssi.get(hex_id, None)
        rssi_str = f"{rssi:.1f}" if rssi is not None else "  n/a"
        print(f"  {flight:<12} {dist:>14.1f} {rssi_str:>17}")

    # Ring suggestions
    print(f"\n  Suggested radius_miles settings:")
    tight  = round(p90_dist * 0.6 / 25) * 25   # 60% of p90, rounded to 25mi
    medium = round(p90_dist * 0.9 / 25) * 25   # 90% of p90
    wide   = round(max_dist  * 0.9 / 25) * 25  # 90% of max

    print(f"    Tight  (most contacts centered): {tight} mi")
    print(f"    Medium (good spread)            : {medium} mi")
    print(f"    Wide   (max coverage)           : {wide} mi")
    print(f"\n  Inner ring (50% of radius):")
    print(f"    Tight: {tight//2} mi  |  Medium: {medium//2} mi  |  Wide: {wide//2} mi")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
