"""Flight data source abstraction — API or local antenna (readsb/dump1090)."""
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in miles between two lat/lon points."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normalize(a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a readsb aircraft dict to pisugar-fx flight dict."""
    if not a.get("lat") or not a.get("lon"):
        return None

    alt_baro = a.get("alt_baro")
    alt_geom = a.get("alt_geom")

    if alt_baro == "ground":
        alt_ft = 0
        on_ground = True
    else:
        alt_ft = int(alt_baro) if isinstance(alt_baro, (int, float)) else 0
        if alt_ft == 0 and alt_geom:
            alt_ft = int(alt_geom) if isinstance(alt_geom, (int, float)) else 0
        on_ground = False

    return {
        "icao": a.get("hex", "").upper(),
        "hex": a.get("hex", "").upper(),
        "call": (a.get("flight") or a.get("r") or "—").strip(),
        "lat": a.get("lat"),
        "lon": a.get("lon"),
        "alt_ft": alt_ft,
        "speed": int(a.get("gs") or 0),
        "gs": int(a.get("gs") or 0),
        "heading": int(a.get("track") or 0),
        "type": a.get("t", ""),
        "category": a.get("category") or a.get("t", ""),
        "reg": a.get("r", ""),
        "squawk": a.get("squawk") or "",
        "on_ground": on_ground,
        "messages": a.get("messages"),
        "rssi": a.get("rssi"),
        "seen": a.get("seen"),
    }


class LocalSource:
    """Reads aircraft data from local readsb JSON file.
    
    Replaces API calls with a direct read of /run/readsb/aircraft.json,
    which readsb updates every second from the RTL-SDR via dump1090.
    """

    def __init__(self, json_path: str = "/run/readsb/aircraft.json"):
        self.json_path = json_path
        self._last_read = 0.0
        self._cache: List[Dict[str, Any]] = []

    def fetch_flights(
        self,
        latitude: float,
        longitude: float,
        radius_miles: int = 100,
        use_cache: bool = True,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Return aircraft within radius_miles of lat/lon from local readsb file."""
        now = time.time()

        # Cache for 1 second — readsb only writes every second anyway
        if use_cache and (now - self._last_read) < 1.0:
            return self._cache

        try:
            with open(self.json_path) as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.error(f"readsb JSON not found at {self.json_path} — is readsb running?")
            return self._cache
        except json.JSONDecodeError as e:
            logger.error(f"Bad JSON from readsb: {e}")
            return self._cache

        flights = []
        for a in data.get("aircraft", []):
            flight = _normalize(a)
            if flight is None:
                continue
            dist = _haversine_miles(latitude, longitude, flight["lat"], flight["lon"])
            if dist <= radius_miles:
                flight["distance_miles"] = dist
                flights.append(flight)

        logger.info(f"LocalSource: {len(flights)} aircraft within {radius_miles}mi of {latitude:.2f},{longitude:.2f}")
        self._last_read = now
        self._cache = flights
        return flights