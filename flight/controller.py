"""Main flight tracker application controller."""

import logging
import sys
import threading
import time
import signal
from typing import Optional

from flight.config import load_config, FlightTrackerConfig
from flight.display import FlightRadarScreen
from flight.web_server import FlightWebServer, SharedState

logger = logging.getLogger(__name__)

def _get_location_from_ip():
    """Auto-detect location from IP address for portable antenna mode."""
    try:
        import urllib.request
        import json
        with urllib.request.urlopen("https://ipapi.co/json/", timeout=5) as r:
            data = json.load(r)
            lat = data["latitude"]
            lon = data["longitude"]
            city = data.get("city", "Unknown")
            logger.info(f"Auto-detected location: {city} ({lat:.4f}, {lon:.4f})")
            return lat, lon, city
    except Exception as e:
        logger.warning(f"IP geolocation failed: {e} — location unknown")
        return None, None, "Unknown Location"
    
class FlightTracker:
    """Main flight tracker application controller."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize flight tracker."""
        # Load configuration
        self.config: FlightTrackerConfig = load_config(config_path)
        self.locations = self.config.locations
        self.settings = self.config.settings

        # Initialize data source
        from flight.source import LocalSource
        from flight.api import FlightAPI

        source_type = getattr(self.settings, "source", "api")
        if source_type == "local":
            self.api = LocalSource()
            logger.info("Using local antenna source (readsb)")
        else:
            self.api = FlightAPI(cache_ttl_seconds=self.settings.refresh_interval_seconds)
            logger.info("Using API source (airplanes.live)")
        if source_type == "local":
            lat, lon, city = _get_location_from_ip()
            from flight.config import FlightLocation
            self.locations = [
                FlightLocation(
                    name=city,
                    latitude=lat,
                    longitude=lon,
                    radius_miles=100,
                )
            ]
            if lat is None:
                logger.warning("Antenna mode: location unknown — distance filter and radar centre disabled")
            else:
                logger.info(f"Antenna mode: single location '{city}' set automatically")


        # State management
        self.current_location_index = 0
        self.current_screen: Optional[FlightRadarScreen] = None
        self.running = False
        self.last_display_update = time.time() - self.settings.refresh_interval_seconds
        self.location_start_time = 0
        
        from flight.history import TrackHistory
        self.history = TrackHistory(
            trail_length=getattr(self.settings, "trail_length", 8),
            ghost_holdover_seconds=getattr(self.settings, "ghost_holdover_seconds", 15),
            trail_enabled=getattr(self.settings, "trail_enabled", True),
            ghost_enabled=getattr(self.settings, "ghost_enabled", True)
        )

        # Display setup
        self._setup_display()

        # Initialize web server
        self._shared_state = SharedState()
        
        if getattr(self.settings, "web_server_enabled", True):
            self._web_server = FlightWebServer(
                self._shared_state,
                port=getattr(self.settings, "web_server_port", 5000),
            )
            self._web_server.start()
        else:
            self._web_server = None

        # Button event handling
        self.button_pressed = False
        self._button_thread = None
        self._setup_button_handler()

        # Shutdown handler
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received")
        self.running = False
        if self.has_display and self.display_board:
            try:
                self.display_board.set_backlight(0)
                self.display_board.set_rgb(0, 0, 0)
                logger.info("Display backlight off")
            except Exception as e:
                logger.error(f"Error turning off display: {e}")
        sys.exit(0)

    def _setup_display(self) -> None:
        """Initialize display driver."""
        try:
            sys.path.insert(0, "/home/aaron/Whisplay/Driver")
            from WhisPlay import WhisPlayBoard

            self.display_board = WhisPlayBoard()
            self.display_board.set_backlight(self.settings.brightness)
            logger.info("WhisPlay display initialized")

            methods = [m for m in dir(self.display_board) if not m.startswith('_')]
            logger.debug(f"WhisPlayBoard available methods: {methods}")

            self.has_display = True
        except Exception as e:
            logger.warning(f"Display not available: {e}. Running in headless mode.")
            self.display_board = None
            self.has_display = False

    def _setup_button_handler(self) -> None:
        """Setup button event monitoring."""
        if not self.has_display:
            logger.debug("Button handler disabled (no display)")
            return

        try:
            self._button_thread = threading.Thread(
                target=self._monitor_button,
                daemon=True,
            )
            self._button_thread.start()
            logger.info("Button monitoring started")
        except Exception as e:
            logger.warning(f"Failed to setup button handler: {e}")

    def _monitor_button(self) -> None:
        """Monitor button press events (runs in background thread)."""
        logger.debug("Button monitor thread started")

        if not self.display_board:
            logger.debug("No display board - button monitoring disabled")
            return

        last_state = False

        while self.running:
            try:
                current_state = self.display_board.button_pressed()

                if current_state and not last_state:
                    logger.info("🔘 Button pressed - cycling to next location")
                    self.button_pressed = True

                last_state = current_state
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Button monitor error: {e}")
                time.sleep(0.5)

    def _display_image(self, image) -> None:
        """Send image to display."""
        if not self.has_display or not self.display_board:
            logger.debug(f"Would display image: {image.size}")
            return

        try:
            if image.size != (240, 280):
                image = image.resize((240, 280))

            if image.mode != "RGB":
                image = image.convert("RGB")

            pixels = list(image.getdata())
            rgb565_data = []
            for r, g, b in pixels:
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                rgb565_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])

            logger.debug(f"Sending {len(rgb565_data)} bytes to display")
            self.display_board.draw_image(0, 0, 240, 280, rgb565_data)
            logger.debug("Display updated via draw_image()")

        except Exception as e:
            logger.error(f"Failed to display image: {e}", exc_info=True)

    def _update_led(self, aircraft_count: int) -> tuple[int, int, int]:
        """Map aircraft count to RGB LED color as a density indicator."""
        # Calculate color
        if aircraft_count == 0:
            r, g, b = 0, 0, 255       # blue — nothing around
        elif aircraft_count <= 5:
            r, g, b = 0, 255, 0       # green
        elif aircraft_count <= 15:
            r, g, b = 255, 255, 0     # yellow
        elif aircraft_count <= 30:
            r, g, b = 255, 80, 0      # orange
        else:
            r, g, b = 255, 0, 0       # red — busy sky
            
        if self.has_display and self.display_board:
            try:
                self.display_board.set_rgb(r, g, b)
            except Exception as e:
                logger.warning(f"LED update failed: {e}")
                
        return (r, g, b)

    def _should_cycle_location(self) -> bool:
        """Check if it's time to cycle to next location."""
        elapsed = time.time() - self.location_start_time
        should_cycle = elapsed >= self.settings.display_duration_seconds or self.button_pressed

        if should_cycle and self.button_pressed:
            logger.debug(f"Cycle triggered by button press (elapsed={elapsed:.1f}s)")
        elif should_cycle:
            logger.debug(f"Cycle triggered by timer ({elapsed:.1f}s >= {self.settings.display_duration_seconds}s)")

        return should_cycle

    def _cycle_to_next_location(self) -> None:
        """Move to next location in the list."""
        self.button_pressed = False
        self.current_location_index = (self.current_location_index + 1) % len(self.locations)
        self.location_start_time = time.time()
        
        from flight.history import TrackHistory
        self.history = TrackHistory(
            trail_length=getattr(self.settings, "trail_length", 8),
            ghost_holdover_seconds=getattr(self.settings, "ghost_holdover_seconds", 60),
            trail_enabled=getattr(self.settings, "trail_enabled", True),
            ghost_enabled=getattr(self.settings, "ghost_enabled", True)
        )
        
        logger.info(
            f"Cycled to location {self.current_location_index + 1}/{len(self.locations)}: "
            f"{self.locations[self.current_location_index].name}"
        )

    def _update_current_screen(self) -> None:
        """Fetch flights and update current screen."""
        location = self.locations[self.current_location_index]

        if (
            not self.current_screen
            or self.current_screen.location_name != location.name
        ):
            self.current_screen = FlightRadarScreen(
                location_name=location.name,
                latitude=location.latitude,
                longitude=location.longitude,
                radius_miles=location.radius_miles,
            )

        # Can't query the API without coordinates
        if location.latitude is None or location.longitude is None:
            logger.debug("Skipping flight fetch — location coords unknown")
            self.current_screen.set_aircraft([])
            self.last_display_update = time.time()
            return

        flights = self.api.fetch_flights(
            latitude=location.latitude,
            longitude=location.longitude,
            radius_miles=location.radius_miles,
            use_cache=True,
        )
        self.last_display_update = time.time()  # fix: prevent immediate re-fetch
        
        enriched_flights = self.history.update(flights)
        self.current_screen.set_aircraft(enriched_flights)

    def run(self) -> None:
        """Main application loop."""
        self.running = True
        logger.info("Flight tracker starting")
        logger.info(f"Tracking {len(self.locations)} locations")

        self.location_start_time = time.time()
        loop_count = 0
        last_log_time = time.time()
        last_displayed_time = 0

        try:
            while self.running:
                try:
                    loop_count += 1
                    current_time = time.time()

                    if current_time - last_log_time >= 5:
                        elapsed_location = current_time - self.location_start_time
                        logger.debug(
                            f"[Loop {loop_count}] Location: {self.current_location_index + 1}/{len(self.locations)}, "
                            f"Elapsed: {elapsed_location:.1f}s/{self.settings.display_duration_seconds}s, "
                            f"Aircraft: {len(self.current_screen.aircraft) if self.current_screen else 0}, "
                            f"Button: {self.button_pressed}"
                        )
                        last_log_time = current_time

                    if self._should_cycle_location():
                        logger.info(f"🔄 Cycling to next location (button_pressed={self.button_pressed})")
                        self._cycle_to_next_location()
                        last_displayed_time = 0

                    time_since_update = current_time - self.last_display_update
                    if time_since_update >= self.settings.refresh_interval_seconds:
                        logger.debug(f"Fetching aircraft (last update: {time_since_update:.1f}s ago)")
                        self._update_current_screen()
                        last_displayed_time = 0

                    if current_time - last_displayed_time >= 0.5:
                        if self.current_screen:
                            image = self.current_screen.render()
                            led_color = self._update_led(len(self.current_screen.aircraft))
                            
                            self._shared_state.update(
                                image,
                                self.current_screen.aircraft,
                                self.current_screen.location_name,
                                led_color=led_color
                            )
                            self._display_image(image)
                            
                            last_displayed_time = current_time
                        else:
                            logger.warning("No current screen to display")

                    time.sleep(0.1)

                except KeyboardInterrupt:
                    logger.info("Interrupted by user")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(1)

        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the application."""
        self.running = False
        logger.info("Flight tracker stopped")


def main(config_path: Optional[str] = None):
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        tracker = FlightTracker(config_path=config_path)
        tracker.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()