"""Configuration management for flight tracker."""

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FlightLocation:
    """Represents a configured flight tracking location."""
    
    name: str
    latitude: float
    longitude: float
    radius_miles: int = 100
    
    def __post_init__(self):
        """Validate coordinates."""
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Invalid longitude: {self.longitude}")
        if self.radius_miles < 10 or self.radius_miles > 500:
            raise ValueError(f"Radius must be 10-500 miles, got {self.radius_miles}")


@dataclass
class FlightTrackerSettings:
    """Application settings for flight tracker."""
    
    display_duration_seconds: int = 30
    refresh_interval_seconds: int = 10
    brightness: int = 100
    rotation: int = 0
    random_location_enabled: bool = False
    source: str = "api"
    web_server_enabled: bool = False
    web_server_port: int = 5000


@dataclass
class FlightTrackerConfig:
    """Complete flight tracker configuration."""
    
    locations: List[FlightLocation]
    settings: FlightTrackerSettings
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.locations:
            logger.warning("No flight tracking locations configured")


def load_config(config_path: Optional[str] = None) -> FlightTrackerConfig:
    """Load flight tracker configuration from JSON file.
    
    Args:
        config_path: Path to config file. Defaults to config/flight_locations.json
        
    Returns:
        FlightTrackerConfig instance
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if config_path is None:
        # Default to config/flight_locations.json in project root
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        config_path = os.path.join(project_root, "config", "flight_locations.json")
    
    config_path = os.path.expanduser(config_path)
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, "r") as f:
        data = json.load(f)
    
    # Parse locations
    locations_data = data.get("locations", [])
    locations = []
    for loc_data in locations_data:
        try:
            location = FlightLocation(
                name=loc_data["name"],
                latitude=float(loc_data["latitude"]),
                longitude=float(loc_data["longitude"]),
                radius_miles=int(loc_data.get("radius_miles", 100)),
            )
            locations.append(location)
        except (KeyError, ValueError) as e:
            logger.warning(f"Skipping invalid location: {e}")
            continue
    
    if not locations:
        logger.info("No locations in config — antenna mode will auto-detect")

    
    # Parse settings
    settings_data = data.get("settings", {})
    settings = FlightTrackerSettings(
        display_duration_seconds=int(settings_data.get("display_duration_seconds", 30)),
        refresh_interval_seconds=int(settings_data.get("refresh_interval_seconds", 10)),
        brightness=int(settings_data.get("brightness", 100)),
        rotation=int(settings_data.get("rotation", 0)),
        random_location_enabled=bool(settings_data.get("random_location_enabled", False)),
        source=str(settings_data.get("source", "api")),
        web_server_enabled=bool(settings_data.get("web_server_enabled", False)),
        web_server_port=int(settings_data.get("web_server_port", 5000)),
    )
    
    logger.info(f"Loaded configuration: {len(locations)} locations")
    
    return FlightTrackerConfig(locations=locations, settings=settings)
