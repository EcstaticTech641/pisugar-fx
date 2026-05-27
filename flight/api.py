"""Flight data API client for airplanes.live service."""

import logging
import math
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import requests

def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in miles between two lat/lon points."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

logger = logging.getLogger(__name__)


class FlightCache:
    """Simple in-memory cache for flight API responses."""
    
    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[Any, float]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key not in self._cache:
            return None
        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl_seconds:
            del self._cache[key]
            return None
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Store value in cache."""
        self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()


class FlightAPI:
    """Client for airplanes.live API."""
    
    BASE_URL = "https://api.airplanes.live/v2"
    REQUEST_TIMEOUT = 10
    USER_AGENT = "pisugar-flight-tracker/0.1.0"
    
    def __init__(self, cache_ttl_seconds: int = 60):
        self.cache = FlightCache(ttl_seconds=cache_ttl_seconds)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
    
    def fetch_flights(
        self,
        latitude: float,
        longitude: float,
        radius_miles: int = 100,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch aircraft within radius of given coordinates.
        
        Args:
            latitude: Center latitude
            longitude: Center longitude  
            radius_miles: Search radius in miles (default 100)
            use_cache: Whether to use cached response (default True)
            
        Returns:
            List of aircraft dictionaries with keys:
            - icao: Aircraft ICAO code (hex)
            - call: Callsign/flight number
            - lat, lon: Position
            - alt_ft: Altitude in feet
            - speed: Ground speed in knots
            - heading: Track heading 0-359 degrees
            - type: Aircraft type code
            - reg: Registration/tail number
            - squawk: Transponder code
            - on_ground: Boolean if landed
            
        Raises:
            requests.RequestException: If API call fails
        """
        # Check cache first
        cache_key = f"{latitude:.4f},{longitude:.4f},{radius_miles}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {cache_key}: {len(cached)} aircraft")
                return cached
        
        try:
            url = f"{self.BASE_URL}/point/{latitude}/{longitude}/{radius_miles}"
            logger.debug(f"Fetching flights from {url}")
            
            response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            aircraft = data.get("ac", [])
            
            # Filter and normalize aircraft data
            flights = []
            for a in aircraft:
                # Skip aircraft without position
                if not a.get("lat") or not a.get("lon"):
                    continue
                
                # Get altitude, handling both numeric and "ground" string values
                alt_baro = a.get("alt_baro")
                alt_geom = a.get("alt_geom")
                
                # Convert altitude to number, defaulting to 0
                if alt_baro == "ground":
                    alt_ft = 0
                    on_ground = True
                else:
                    alt_ft = int(alt_baro) if isinstance(alt_baro, int) else 0
                    if alt_ft == 0 and alt_geom:
                        alt_ft = int(alt_geom) if isinstance(alt_geom, int) else 0
                    on_ground = False
                
                flight = {
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
                    "distance_miles": _haversine_miles(latitude, longitude, a.get("lat"), a.get("lon")),
                }
                flights.append(flight)
            
            logger.info(f"Fetched {len(flights)} aircraft from {latitude:.2f},{longitude:.2f}")
            
            # Cache the result
            if use_cache:
                self.cache.set(cache_key, flights)
            
            return flights
            
        except requests.Timeout:
            logger.error(f"API request timed out (>{self.REQUEST_TIMEOUT}s)")
            return []
        except requests.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            return []
        except requests.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e}")
            return []
        except ValueError as e:
            logger.error(f"Invalid JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching flights: {e}")
            return []
    
    def clear_cache(self) -> None:
        """Clear the response cache."""
        self.cache.clear()
