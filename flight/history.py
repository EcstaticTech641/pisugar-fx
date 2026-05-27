"""Flight track history and dead reckoning."""

import time
import math
from collections import deque
from typing import List, Dict, Any

class TrackHistory:
    """Manages aircraft trails and dead reckoning (ghosting)."""
    
    def __init__(
        self, 
        trail_length: int = 8, 
        ghost_holdover_seconds: int = 15,
        trail_enabled: bool = True,
        ghost_enabled: bool = True
    ):
        self.trail_length = trail_length
        self.ghost_holdover_seconds = ghost_holdover_seconds
        self.trail_enabled = trail_enabled
        self.ghost_enabled = ghost_enabled
        
        # hex -> deque of {"lat": float, "lon": float, "ts": float}
        self._trails: Dict[str, deque] = {}
        
        # hex -> last seen full aircraft dict
        self._last_state: Dict[str, Dict[str, Any]] = {}
        
        # hex -> ghost entry: {"ac": dict, "lost_ts": float}
        self._ghosts: Dict[str, Dict[str, Any]] = {}
        
    def update(self, live_aircraft: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process current aircraft, update trails, and generate ghosts."""
        now = time.time()
        live_hexes = set()
        
        enriched_list = []
        
        for ac in live_aircraft:
            hex_id = ac.get("hex")
            if not hex_id or "lat" not in ac or "lon" not in ac:
                enriched_list.append(ac)
                continue
                
            live_hexes.add(hex_id)
            self._last_state[hex_id] = ac.copy()
            
            # Remove from ghosts if it came back
            if hex_id in self._ghosts:
                del self._ghosts[hex_id]
                
            # Update trail
            if self.trail_enabled:
                if hex_id not in self._trails:
                    self._trails[hex_id] = deque(maxlen=self.trail_length)
                
                trail = self._trails[hex_id]
                if not trail or trail[-1]["lat"] != ac["lat"] or trail[-1]["lon"] != ac["lon"]:
                    trail.append({
                        "lat": ac["lat"],
                        "lon": ac["lon"],
                        "ts": now
                    })
                
                # Attach trail
                ac["trail"] = list(trail)
            else:
                ac["trail"] = []
                
            ac["ghost"] = False
            enriched_list.append(ac)
            
        # Handle missing aircraft -> ghosts
        if self.ghost_enabled:
            for hex_id, last_ac in list(self._last_state.items()):
                if hex_id not in live_hexes:
                    if hex_id not in self._ghosts:
                        # newly missing -> promote to ghost
                        self._ghosts[hex_id] = {
                            "ac": last_ac.copy(),
                            "lost_ts": now
                        }
                        
            # Process ghosts
            for hex_id, ghost_entry in list(self._ghosts.items()):
                elapsed = now - ghost_entry["lost_ts"]
                if elapsed > self.ghost_holdover_seconds:
                    # Expired
                    del self._ghosts[hex_id]
                    if hex_id in self._last_state:
                        del self._last_state[hex_id]
                    continue
                
                ac = ghost_entry["ac"].copy()
                if ac.get("gs") is not None and ac.get("heading") is not None:
                    new_lat, new_lon = self._dead_reckon(ac["lat"], ac["lon"], ac["heading"], ac["gs"], elapsed)
                    ac["lat"] = new_lat
                    ac["lon"] = new_lon
                    
                ac["ghost"] = True
                if self.trail_enabled and hex_id in self._trails:
                    ac["trail"] = list(self._trails[hex_id])
                else:
                    ac["trail"] = []
                    
                enriched_list.append(ac)
                
        self.purge_expired(now)
        return enriched_list
        
    def _dead_reckon(self, lat: float, lon: float, heading: float, gs_knots: float, elapsed_seconds: float) -> tuple[float, float]:
        """Project new position using dead reckoning."""
        if gs_knots is None or heading is None:
            return lat, lon
            
        miles_per_sec = (gs_knots * 1.15078) / 3600.0
        distance_miles = miles_per_sec * elapsed_seconds
        
        heading_rad = math.radians(heading)
        lat_rad = math.radians(lat)
        
        dlat = (distance_miles * math.cos(heading_rad)) / 69.0
        dlon = (distance_miles * math.sin(heading_rad)) / (69.0 * math.cos(lat_rad))
        
        return lat + dlat, lon + dlon
        
    def purge_expired(self, now: float, max_age_seconds: int = 300) -> None:
        """Remove old trails for aircraft not seen in a long time."""
        to_delete = []
        for hex_id, trail in self._trails.items():
            if not trail:
                to_delete.append(hex_id)
                continue
            
            last_ts = trail[-1]["ts"]
            if now - last_ts > max_age_seconds:
                to_delete.append(hex_id)
                
        for hex_id in to_delete:
            del self._trails[hex_id]
            if hex_id in self._last_state:
                del self._last_state[hex_id]
            if hex_id in self._ghosts:
                del self._ghosts[hex_id]
