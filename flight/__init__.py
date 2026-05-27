
"""Flight tracking display application."""

__version__ = "0.1.1"

from flight.api import FlightAPI
from flight.config import FlightTrackerConfig, load_config
from flight.display import FlightRadarScreen
# FlightTracker intentionally not imported here —
# it imports the full controller stack and should only
# be loaded by flight_tracker.py at entry point time.

__all__ = [
    "FlightAPI",
    "FlightTrackerConfig",
    "load_config",
    "FlightRadarScreen",
    "FlightTracker",
]
