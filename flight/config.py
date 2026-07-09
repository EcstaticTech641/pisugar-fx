"""Configuration management for flight tracker."""

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FlightLocation:
    """Represents a configured flight tracking location."""

    name: str
    latitude: Optional[float]
    longitude: Optional[float]
    radius_miles: int = 100

    def __post_init__(self):
        """Validate coordinates when present."""
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError(f"Invalid longitude: {self.longitude}")
        if self.radius_miles < 10 or self.radius_miles > 500:
            raise ValueError(f"Radius must be 10-500 miles, got {self.radius_miles}")


@dataclass
class FlightTrackerSettings:
    """Application settings for flight tracker."""

    # Core / restart-required
    source: str = "api"
    web_server_enabled: bool = True
    web_server_port: int = 5000
    rotation: int = 0

    # Display cycle
    display_duration_seconds: int = 3600
    random_location_enabled: bool = False

    # Hot-reloadable — refresh & brightness
    refresh_interval_seconds: int = 5
    brightness: int = 100

    # Hot-reloadable — trails & ghosts
    trail_length: int = 8
    trail_enabled: bool = True
    ghost_holdover_seconds: int = 60
    ghost_enabled: bool = True

    # Hot-reloadable — web mirror
    web_mirror_jpeg_quality: int = 85
    web_mirror_refresh_ms: int = 2000

    # Hot-reloadable — LED density thresholds
    # [green_max, yellow_max, orange_max]
    # blue=0, green<=t[0], yellow<=t[1], orange<=t[2], red>t[2]
    led_thresholds: List[int] = field(default_factory=lambda: [5, 15, 30])

    # Hot-reloadable — callsign label selection rule
    callsign_rule: str = "nearest"  # "nearest" | "highest" | "busiest"

    # Hot-reloadable — auto-dim
    auto_dim_enabled: bool = False
    auto_dim_brightness: int = 20
    auto_dim_after_seconds: int = 300

    # Phase 2 button nav (not yet wired, stored for future use)
    default_view_mode: str = "radar"  # "radar" | "list" | "detail"

    # radius_miles override applied at next FlightRadarScreen construction
    radius_miles: Optional[int] = None

    # /settings web auth credentials
    web_settings_user: str = "admin"
    web_settings_password: str = "changeme"
    web_settings_secret_key: str = ""  # empty = Flask generates one at startup


@dataclass
class AuthConfig:
    """HTTP Basic Auth credentials for the /settings page."""

    username: str = "admin"
    password: str = "changeme"


@dataclass
class FlightTrackerConfig:
    """Complete flight tracker configuration."""

    locations: List[FlightLocation]
    settings: FlightTrackerSettings
    auth: AuthConfig = None  # populated in __post_init__

    def __post_init__(self):
        """Validate configuration and fill defaults."""
        if not self.locations:
            logger.warning("No flight tracking locations configured")
        if self.auth is None:
            self.auth = AuthConfig()


def _default_config_path() -> str:
    """Return the default path to flight_locations.json."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "config", "flight_locations.json")


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
        config_path = _default_config_path()

    config_path = os.path.expanduser(config_path)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r") as f:
        data = json.load(f)

    # ── Parse locations ──────────────────────────────────────────────────────
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

    # ── Parse settings ───────────────────────────────────────────────────────
    sd = data.get("settings", {})

    # led_thresholds: validate it's a list of 3 ints, else use default
    raw_thresholds = sd.get("led_thresholds", [5, 15, 30])
    if (
        isinstance(raw_thresholds, list)
        and len(raw_thresholds) == 3
        and all(isinstance(v, int) for v in raw_thresholds)
    ):
        led_thresholds = raw_thresholds
    else:
        logger.warning("led_thresholds invalid in config, using default [5, 15, 30]")
        led_thresholds = [5, 15, 30]

    # radius_miles override (optional; None means "use per-location value")
    raw_radius = sd.get("radius_miles")
    radius_miles_override = int(raw_radius) if raw_radius is not None else None

    settings = FlightTrackerSettings(
        # Restart-required
        source=str(sd.get("source", "api")),
        web_server_enabled=bool(sd.get("web_server_enabled", True)),
        web_server_port=int(sd.get("web_server_port", 5000)),
        rotation=int(sd.get("rotation", 0)),
        # Display cycle
        display_duration_seconds=int(sd.get("display_duration_seconds", 3600)),
        random_location_enabled=bool(sd.get("random_location_enabled", False)),
        # Hot-reloadable
        refresh_interval_seconds=int(sd.get("refresh_interval_seconds", 5)),
        brightness=int(sd.get("brightness", 100)),
        trail_length=int(sd.get("trail_length", 8)),
        trail_enabled=bool(sd.get("trail_enabled", True)),
        ghost_holdover_seconds=int(sd.get("ghost_holdover_seconds", 60)),
        ghost_enabled=bool(sd.get("ghost_enabled", True)),
        web_mirror_jpeg_quality=int(sd.get("web_mirror_jpeg_quality", 85)),
        web_mirror_refresh_ms=int(sd.get("web_mirror_refresh_ms", 2000)),
        led_thresholds=led_thresholds,
        callsign_rule=str(sd.get("callsign_rule", "nearest")),
        auto_dim_enabled=bool(sd.get("auto_dim_enabled", False)),
        auto_dim_brightness=int(sd.get("auto_dim_brightness", 20)),
        auto_dim_after_seconds=int(sd.get("auto_dim_after_seconds", 300)),
        default_view_mode=str(sd.get("default_view_mode", "radar")),
        radius_miles=radius_miles_override,
        # /settings web auth
        web_settings_user=str(sd.get("web_settings_user", "admin")),
        web_settings_password=str(sd.get("web_settings_password", "changeme")),
        web_settings_secret_key=str(sd.get("web_settings_secret_key", "")),
    )

    # ── Parse auth ───────────────────────────────────────────────────────────
    auth_data = data.get("auth", {})
    auth = AuthConfig(
        username=str(auth_data.get("username", "admin")),
        password=str(auth_data.get("password", "changeme")),
    )

    logger.info(f"Loaded configuration: {len(locations)} locations")

    return FlightTrackerConfig(locations=locations, settings=settings, auth=auth)


def save_settings(config_path: str, settings_data: dict) -> None:
    """Atomically merge updated settings into the config JSON file.

    Only the ``settings`` block is touched; ``locations`` and ``auth`` are
    preserved as-is.  Uses write-to-temp + os.replace() for atomic writes on
    both POSIX and Windows (same-filesystem rename).

    Args:
        config_path:   Absolute path to flight_locations.json.
        settings_data: Flat dict of setting keys to update/add.
    """
    config_path = os.path.expanduser(config_path)
    with open(config_path, "r") as f:
        data = json.load(f)

    data["settings"] = {**data.get("settings", {}), **settings_data}

    dir_ = os.path.dirname(config_path)
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tf:
        json.dump(data, tf, indent=2)
        tmp_path = tf.name

    os.replace(tmp_path, config_path)  # atomic on POSIX; best-effort on Windows
    logger.info("save_settings: config written to %s", config_path)