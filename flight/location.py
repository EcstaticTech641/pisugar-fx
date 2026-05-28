import csv
import math
import os
import logging
import urllib.request
import json
from typing import Tuple, Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Cache of the cities database to avoid re-reading the file on every lookup.
# Each entry is a tuple: (name, x, y, z, country)
_CITIES_CACHE: Optional[List[Tuple[str, float, float, float, str]]] = None


def _load_cities() -> List[Tuple[str, float, float, float, str]]:
    """Load the cities dataset and precompute 3D unit vector coordinates."""
    global _CITIES_CACHE
    if _CITIES_CACHE is not None:
        return _CITIES_CACHE

    cities = []
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(project_root, "data", "cities.csv")

    if not os.path.exists(csv_path):
        logger.error(f"Cities database not found at {csv_path}")
        _CITIES_CACHE = []
        return []

    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["name"]
                lat = float(row["lat"])
                lon = float(row["lon"])
                country = row["country"]

                lat_rad = math.radians(lat)
                lon_rad = math.radians(lon)
                cos_lat = math.cos(lat_rad)
                x = cos_lat * math.cos(lon_rad)
                y = cos_lat * math.sin(lon_rad)
                z = math.sin(lat_rad)

                cities.append((name, x, y, z, country))
    except Exception as e:
        logger.error(f"Failed to load cities database: {e}")
        _CITIES_CACHE = []
        return []

    _CITIES_CACHE = cities
    logger.info(f"Loaded {len(cities)} cities into location cache")
    return cities


def nearest_town(lat: float, lon: float) -> Tuple[Optional[str], Optional[str]]:
    """
    Find the nearest town name and country code using a 3D unit vector dot
    product scan.  Returns (name, country) or (None, None) if the cities
    database is empty.
    """
    cities = _load_cities()
    if not cities:
        return None, None

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    cos_lat = math.cos(lat_rad)
    xq = cos_lat * math.cos(lon_rad)
    yq = cos_lat * math.sin(lon_rad)
    zq = math.sin(lat_rad)

    best_name = None
    best_country = None
    best_dot = -2.0

    for name, xc, yc, zc, country in cities:
        dot = xq * xc + yq * yc + zq * zc
        if dot > best_dot:
            best_dot = dot
            best_name = name
            best_country = country

    return best_name, best_country


def _centroid_from_aircraft(
    aircraft_list: List[Dict[str, Any]]
) -> Tuple[Optional[float], Optional[float]]:
    """
    Estimate position from the median lat/lon of aircraft with position fixes.

    Returns (median_lat, median_lon), or (None, None) when fewer than 3
    aircraft have both lat and lon set (below that threshold the centroid is
    not meaningful).
    """
    lats = []
    lons = []
    for ac in aircraft_list:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is not None and lon is not None:
            try:
                lats.append(float(lat))
                lons.append(float(lon))
            except (TypeError, ValueError):
                pass

    if len(lats) < 3:
        return None, None

    lats_sorted = sorted(lats)
    lons_sorted = sorted(lons)
    mid = len(lats_sorted) // 2

    # Median for odd-length lists; average of two middle values for even.
    if len(lats_sorted) % 2 == 1:
        median_lat = lats_sorted[mid]
        median_lon = lons_sorted[mid]
    else:
        median_lat = (lats_sorted[mid - 1] + lats_sorted[mid]) / 2
        median_lon = (lons_sorted[mid - 1] + lons_sorted[mid]) / 2

    return median_lat, median_lon


def _format_label(lat: float, lon: float) -> str:
    """Return a human-readable location label for the given coordinates."""
    name, country = nearest_town(lat, lon)
    if name:
        return f"{name}, {country}" if country else name
    return f"{lat:.4f}, {lon:.4f}"


class LocationProvider:
    """
    Provides current device location using a two-step fallback chain:

    1. IP Geolocation  (ipapi.co)
    2. Aircraft centroid  (median lat/lon of aircraft with position fixes,
       requires 3+ aircraft)

    Each successful result is reverse-geocoded through nearest_town() so
    the display label is always a human-readable city name rather than raw
    coordinates.  GPS drops in as a future subclass / config flag.
    """

    def __init__(self) -> None:
        self.current_lat: Optional[float] = None
        self.current_lon: Optional[float] = None
        self.current_label: str = "Unknown Location"

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_location_from_ip(self) -> Tuple[Optional[float], Optional[float]]:
        """Query the IP geolocation API and return (lat, lon) or (None, None)."""
        try:
            with urllib.request.urlopen("https://ipapi.co/json/", timeout=5) as r:
                data = json.load(r)
                lat = float(data["latitude"])
                lon = float(data["longitude"])
                return lat, lon
        except Exception as e:
            logger.warning(f"IP geolocation failed: {e}")
            return None, None

    def _apply(
        self, lat: float, lon: float, source: str
    ) -> Tuple[float, float, str]:
        """Store coordinates, compute label, log, and return the triple."""
        self.current_lat = lat
        self.current_lon = lon
        self.current_label = _format_label(lat, lon)
        logger.info(
            f"Location via {source}: {self.current_label} ({lat:.4f}, {lon:.4f})"
        )
        return self.current_lat, self.current_lon, self.current_label

    # ── Public API ───────────────────────────────────────────────────────────

    def detect(
        self, aircraft_list: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[float], Optional[float], str]:
        """
        Run the fallback chain and return (lat, lon, label).

        Parameters
        ----------
        aircraft_list:
            Optional list of aircraft dicts (same shape returned by the API).
            When provided and IP geolocation fails, the centroid of aircraft
            with position fixes is tried as a secondary fallback.
        """
        # Step 1 — IP Geolocation
        lat, lon = self._get_location_from_ip()
        if lat is not None and lon is not None:
            return self._apply(lat, lon, "IP")

        # Step 2 — Aircraft centroid (only when caller supplies flight data)
        if aircraft_list:
            lat, lon = _centroid_from_aircraft(aircraft_list)
            if lat is not None and lon is not None:
                return self._apply(lat, lon, "aircraft centroid")

        # Final fallback
        self.current_lat = None
        self.current_lon = None
        self.current_label = "Unknown Location"
        logger.warning("Location detection failed — all fallbacks exhausted")
        return None, None, "Unknown Location"
