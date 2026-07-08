"""Display mode state machine for radar / list / detail views."""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class DisplayMode(Enum):
    RADAR = "radar"
    AIRCRAFT_LIST = "list"
    DETAIL = "detail"


@dataclass
class Aircraft:
    icao: str
    call: str
    lat: float
    lon: float
    alt_ft: int
    speed: int
    heading: int
    type: str = ""
    reg: str = ""
    squawk: str = ""
    on_ground: bool = False
    rssi: Optional[float] = None
    seen: Optional[float] = None


class DisplayStateMachine:
    """Tracks current display mode and aircraft selection. No rendering here."""

    DETAIL_VIEW_TIMEOUT = 60.0  # seconds of inactivity before auto-return to radar

    def __init__(self):
        self.mode = DisplayMode.RADAR
        self.aircraft: List[Aircraft] = []
        self.selected_index = 0
        self._last_interaction_time = time.time()

    def set_aircraft(self, aircraft: List[Aircraft]):
        """Called every refresh cycle regardless of current mode."""
        self.aircraft = sorted(aircraft, key=lambda a: a.alt_ft, reverse=True)
        if self.aircraft:
            self.selected_index = min(self.selected_index, len(self.aircraft) - 1)
        else:
            self.selected_index = 0

    def get_selected_aircraft(self) -> Optional[Aircraft]:
        if self.aircraft and 0 <= self.selected_index < len(self.aircraft):
            return self.aircraft[self.selected_index]
        return None

    def check_detail_timeout(self):
        """Call every loop iteration. Auto-returns to radar after 60s inactivity."""
        if self.mode == DisplayMode.DETAIL:
            if time.time() - self._last_interaction_time >= self.DETAIL_VIEW_TIMEOUT:
                logger.info("Detail view timed out after 60s — returning to radar")
                self.mode = DisplayMode.RADAR

    def handle_single_click(self):
        self._last_interaction_time = time.time()
        if self.mode == DisplayMode.RADAR:
            self.mode = DisplayMode.AIRCRAFT_LIST
        elif self.mode == DisplayMode.AIRCRAFT_LIST:
            self._scroll_to_next()
        elif self.mode == DisplayMode.DETAIL:
            self._scroll_to_next()

    def handle_double_click(self):
        self._last_interaction_time = time.time()
        if self.mode == DisplayMode.AIRCRAFT_LIST and self.aircraft:
            self.mode = DisplayMode.DETAIL

    def handle_long_press(self):
        self._last_interaction_time = time.time()
        if self.mode == DisplayMode.AIRCRAFT_LIST:
            self.mode = DisplayMode.RADAR
        elif self.mode == DisplayMode.DETAIL:
            self.mode = DisplayMode.AIRCRAFT_LIST

    def _scroll_to_next(self):
        if not self.aircraft:
            return
        self.selected_index = (self.selected_index + 1) % len(self.aircraft)
