"""Flight radar display rendering engine."""

import logging
import math
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class FlightRadarScreen:
    """Renders a radar-style display of aircraft around a location."""
    
    # Display dimensions
    WIDTH = 240
    HEIGHT = 280
    HEADER_HEIGHT = 36
    MAP_HEIGHT = HEIGHT - HEADER_HEIGHT  # 244
    
    # Radar geometry
    CENTER_X = WIDTH // 2  # 120
    CENTER_Y = HEADER_HEIGHT + MAP_HEIGHT // 2  # 158
    
    # Colors (RGB tuples)
    C_BG = (6, 11, 16)           # Very dark blue
    C_HEADER = (11, 20, 32)      # Slightly lighter blue
    C_RING_50 = (13, 42, 64)     # Ring color for 50mi
    C_RING_100 = (20, 60, 90)    # Ring color for 100mi
    C_RING_LABEL = (40, 90, 120) # Ring label color
    C_CROSSHAIR = (0, 229, 255)  # Cyan
    C_AIRCRAFT_AIR = (0, 229, 255)      # Cyan for airborne
    C_AIRCRAFT_GND = (255, 107, 53)     # Orange for ground
    C_CALLSIGN = (200, 223, 240)        # Light cyan
    C_HEADER_TEXT = (0, 229, 255)       # Cyan
    C_HEADER_DIM = (74, 112, 144)       # Dimmed text
    C_DIVIDER = (26, 58, 92)            # Divider line
    
    def __init__(
        self,
        location_name: str,
        latitude: Optional[float],
        longitude: Optional[float],
        radius_miles: int = 100,
    ):
        self.location_name = location_name
        self.center_lat = latitude
        self.center_lon = longitude
        self.radius_miles = radius_miles
        self.aircraft: List[Dict[str, Any]] = []
        self.timestamp = datetime.now()
        self._fonts = self._load_fonts()
    
    @property
    def _has_location(self) -> bool:
        """True when we have real coordinates to plot against."""
        return self.center_lat is not None and self.center_lon is not None
    
    def _load_fonts(self) -> Dict[str, ImageFont.FreeTypeFont]:
        """Load TrueType fonts, falling back to default if needed."""
        fonts = {}
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
        
        for size_name, size_px in [("small", 8), ("medium", 11), ("large", 14)]:
            for path in font_paths:
                try:
                    fonts[size_name] = ImageFont.truetype(path, size_px)
                    break
                except (OSError, IOError):
                    continue
            else:
                # Fallback to default
                fonts[size_name] = ImageFont.load_default()
        
        return fonts
    
    @property
    def PX_PER_MILE(self) -> float:
        return (min(self.WIDTH, self.MAP_HEIGHT) // 2 - 10) / float(self.radius_miles)

    def _ring_miles(self) -> List[float]:
        return [self.radius_miles / 2.0, float(self.radius_miles)]

    def set_aircraft(self, flights: List[Dict[str, Any]]) -> None:
        """Update aircraft list and timestamp.
        
        Args:
            flights: List of flight dictionaries from API
        """
        self.aircraft = flights
        self.timestamp = datetime.now()
    
    def _geo_to_px(self, lat: float, lon: float) -> Tuple[int, int]:
        """Convert lat/lon to pixel coordinates relative to map center.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            (x, y) pixel coordinates, or map center when location is unknown
        """
        if not self._has_location:
            return self.CENTER_X, self.CENTER_Y
        
        dlat = lat - self.center_lat
        dlon = lon - self.center_lon
        
        # Mile per degree calculations
        mi_per_deg_lat = 69.0
        mi_per_deg_lon = 69.0 * math.cos(math.radians(self.center_lat))
        
        # Convert to miles then to pixels
        dx = dlon * mi_per_deg_lon * self.PX_PER_MILE
        dy = -dlat * mi_per_deg_lat * self.PX_PER_MILE  # screen y is inverted
        
        return int(self.CENTER_X + dx), int(self.CENTER_Y + dy)
    
    def _draw_aircraft_arrow(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        heading: float,
        color: Tuple[int, int, int],
        size: int = 5,
        is_ghost: bool = False,
    ) -> None:
        """Draw a directional arrow for an aircraft.
        
        Args:
            draw: PIL ImageDraw object
            x, y: Position in pixels
            heading: Heading in degrees (0-359)
            color: RGB color tuple
            size: Size of arrow in pixels
            is_ghost: Render as a hollow dashed arrow for predicted position
        """
        rad = math.radians(heading - 90)
        
        # Triangle pointing in heading direction
        tip_x = x + size * math.cos(rad)
        tip_y = y + size * math.sin(rad)
        
        # Base corners
        left_rad = rad + math.radians(140)
        right_rad = rad - math.radians(140)
        
        lx = x + (size * 0.6) * math.cos(left_rad)
        ly = y + (size * 0.6) * math.sin(left_rad)
        rx = x + (size * 0.6) * math.cos(right_rad)
        ry = y + (size * 0.6) * math.sin(right_rad)
        
        if is_ghost:
            # Hollow arrow outline
            draw.polygon([(tip_x, tip_y), (lx, ly), (rx, ry)], outline=color)
            
            # Dashed circle
            r = size + 4
            draw.arc([x-r, y-r, x+r, y+r], 0, 45, fill=color)
            draw.arc([x-r, y-r, x+r, y+r], 90, 135, fill=color)
            draw.arc([x-r, y-r, x+r, y+r], 180, 225, fill=color)
            draw.arc([x-r, y-r, x+r, y+r], 270, 315, fill=color)
        else:
            # Draw filled triangle
            draw.polygon([(tip_x, tip_y), (lx, ly), (rx, ry)], fill=color)

            # Draw stem
            stem_len = size * 0.55
            stem_x = x - stem_len * math.cos(rad)
            stem_y = y - stem_len * math.sin(rad)
            draw.line((stem_x, stem_y, x, y), fill=color, width=1)
    
    def render(self) -> Image.Image:
        """Generate radar display image.
        
        Returns:
            PIL Image (RGB, 240x280)
        """
        # Create background
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), color=self.C_BG)
        draw = ImageDraw.Draw(img)
        
        # Draw header background
        draw.rectangle(
            [(0, 0), (self.WIDTH, self.HEADER_HEIGHT)],
            fill=self.C_HEADER,
        )
        
        # Draw divider line
        draw.line(
            [(0, self.HEADER_HEIGHT), (self.WIDTH, self.HEADER_HEIGHT)],
            fill=self.C_DIVIDER,
            width=1,
        )
        
        # Draw header text
        self._draw_header(draw)
        
        # Draw radar background (range rings and crosshairs)
        self._draw_radar_background(draw)
        
        # Draw aircraft
        self._draw_aircraft(draw)
        
        return img
    
    def _draw_header(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw header with location, time, and aircraft count."""
        # Location name (left-aligned); dim if unknown
        display_name = self.location_name if self.location_name else "Unknown Location"
        name_color = self.C_HEADER_DIM if not self._has_location else self.C_HEADER_TEXT
        draw.text(
            (8, 8),
            display_name,
            fill=name_color,
            font=self._fonts["small"],
        )
        
        # Time (right-aligned, just show HH:MM)
        time_str = self.timestamp.strftime("%H:%M")
        time_bbox = draw.textbbox((0, 0), time_str, font=self._fonts["small"])
        time_width = time_bbox[2] - time_bbox[0]
        draw.text(
            (self.WIDTH - 8 - time_width, 8),
            time_str,
            fill=self.C_HEADER_DIM,
            font=self._fonts["small"],
        )
        
        # Aircraft count (center)
        count_str = f"{len(self.aircraft)} aircraft"
        count_bbox = draw.textbbox((0, 0), count_str, font=self._fonts["small"])
        count_width = count_bbox[2] - count_bbox[0]
        draw.text(
            ((self.WIDTH - count_width) // 2, 20),
            count_str,
            fill=self.C_HEADER_DIM,
            font=self._fonts["small"],
        )
    
    def _draw_radar_background(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw range rings and crosshairs."""
        # Skip range rings when location is unknown (miles-per-pixel is meaningless)
        if not self._has_location:
            self._draw_crosshair(draw)
            return
        
        # Draw range rings
        rings = self._ring_miles()
        for idx, ring_miles in enumerate(rings):
            radius_px = int(ring_miles * self.PX_PER_MILE)
            color = self.C_RING_50 if idx == 0 else self.C_RING_100
            
            # Draw circle
            draw.ellipse(
                [
                    self.CENTER_X - radius_px,
                    self.CENTER_Y - radius_px,
                    self.CENTER_X + radius_px,
                    self.CENTER_Y + radius_px,
                ],
                outline=color,
                width=1,
            )
            
            # Draw label at top of ring
            label = f"{ring_miles}mi"
            label_y = self.CENTER_Y - radius_px - 10
            label_bbox = draw.textbbox((0, 0), label, font=self._fonts["small"])
            label_width = label_bbox[2] - label_bbox[0]
            draw.text(
                ((self.WIDTH - label_width) // 2, label_y),
                label,
                fill=self.C_RING_LABEL,
                font=self._fonts["small"],
            )
        
        # Draw crosshairs (center plus sign)
        self._draw_crosshair(draw)
    
    def _draw_crosshair(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw center crosshair and dot."""
        cross_size = 12
        draw.line(
            [
                (self.CENTER_X - cross_size, self.CENTER_Y),
                (self.CENTER_X + cross_size, self.CENTER_Y),
            ],
            fill=self.C_CROSSHAIR,
            width=1,
        )
        draw.line(
            [
                (self.CENTER_X, self.CENTER_Y - cross_size),
                (self.CENTER_X, self.CENTER_Y + cross_size),
            ],
            fill=self.C_CROSSHAIR,
            width=1,
        )
        
        # Center dot
        draw.ellipse(
            [
                self.CENTER_X - 2,
                self.CENTER_Y - 2,
                self.CENTER_X + 2,
                self.CENTER_Y + 2,
            ],
            fill=self.C_CROSSHAIR,
        )
    
    def _clamp_label_pos(self, draw: ImageDraw.ImageDraw, text: str, x: int, y: int, font: Any) -> Tuple[int, int]:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        nx = max(0, min(x - w // 2, self.WIDTH - w - 1))
        ny = max(self.HEADER_HEIGHT + 1, min(y - h - 2, self.HEIGHT - h - 1))
        return int(nx), int(ny)

    def _draw_trail(self, draw: ImageDraw.ImageDraw, flight: Dict[str, Any], trail: List[Dict[str, Any]]) -> None:
        """Draw history trail for an aircraft fading into background."""
        base_color = self.C_AIRCRAFT_GND if flight.get("on_ground", False) else self.C_AIRCRAFT_AIR
        if flight.get("ghost", False):
            base_color = (0, 80, 89)
            
        points = []
        for p in trail:
            px, py = self._geo_to_px(p["lat"], p["lon"])
            points.append((px, py))
            
        px, py = self._geo_to_px(flight["lat"], flight["lon"])
        points.append((px, py))
        
        num_segs = len(points) - 1
        for i in range(num_segs):
            ratio = (i + 1) / float(num_segs)
            r = int(self.C_BG[0] + (base_color[0] - self.C_BG[0]) * ratio)
            g = int(self.C_BG[1] + (base_color[1] - self.C_BG[1]) * ratio)
            b = int(self.C_BG[2] + (base_color[2] - self.C_BG[2]) * ratio)
            
            draw.line([points[i], points[i+1]], fill=(r, g, b), width=1)

    def _draw_aircraft(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw aircraft as directional arrows."""
        if not self.aircraft:
            return
        
        # Sort by altitude (highest first) so they draw in good order
        sorted_aircraft = sorted(
            self.aircraft,
            key=lambda a: a.get("alt_ft", 0),
            reverse=True,
        )
        
        # Draw trails first (underneath blips) if < 20 aircraft
        if len(self.aircraft) < 20:
            for flight in sorted_aircraft:
                trail = flight.get("trail", [])
                if len(trail) > 0:
                    self._draw_trail(draw, flight, trail)
        
        # Draw each aircraft
        for idx, flight in enumerate(sorted_aircraft):
            # Get screen position
            px, py = self._geo_to_px(flight["lat"], flight["lon"])
            
            # Check if on screen (with margin)
            margin = 20
            if not (
                -margin < px < self.WIDTH + margin
                and self.HEADER_HEIGHT - margin < py < self.HEIGHT + margin
            ):
                continue
                
            is_ghost = flight.get("ghost", False)
            
            # Ghost boundary check: disappear immediately when crossing radius ring
            if is_ghost:
                dist_px = math.sqrt((px - self.CENTER_X)**2 + (py - self.CENTER_Y)**2)
                max_radius_px = self.radius_miles * self.PX_PER_MILE
                if dist_px > max_radius_px:
                    continue
            
            # Choose color
            if is_ghost:
                color = (0, 80, 89)
            elif flight.get("on_ground", False):
                color = self.C_AIRCRAFT_GND
            else:
                color = self.C_AIRCRAFT_AIR
            
            # Draw arrow
            self._draw_aircraft_arrow(
                draw,
                px,
                py,
                flight.get("heading", 0),
                color,
                size=5,
                is_ghost=is_ghost,
            )
            
            # Draw callsign label for top 3 aircraft (or all if < 3 on screen)
            if not is_ghost and idx < 3 and flight.get("call", "—") != "—":
                label = flight["call"][:6]  # Truncate to fit
                lx, ly = self._clamp_label_pos(draw, label, px, py, self._fonts["small"])
                draw.text(
                    (lx, ly),
                    label,
                    fill=self.C_CALLSIGN,
                    font=self._fonts["small"],
                )
