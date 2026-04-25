"""Main flight tracker application controller."""

import logging
import sys
import threading
import time
from typing import Optional

from flight.api import FlightAPI
from flight.config import load_config, FlightTrackerConfig
from flight.display import FlightRadarScreen

logger = logging.getLogger(__name__)


class FlightTracker:
    """Main flight tracker application controller."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize flight tracker.
        
        Args:
            config_path: Path to flight_locations.json config file
        """
        # Load configuration
        self.config: FlightTrackerConfig = load_config(config_path)
        self.locations = self.config.locations
        self.settings = self.config.settings
        
        # Initialize API client
        self.api = FlightAPI(cache_ttl_seconds=self.settings.refresh_interval_seconds)
        
        # State management
        self.current_location_index = 0
        self.current_screen: Optional[FlightRadarScreen] = None
        self.running = False
        self.last_display_update = time.time() - self.settings.refresh_interval_seconds  # Force update on first iteration
        self.location_start_time = 0
        
        # Display setup
        self._setup_display()
        
        # Button event handling
        self.button_pressed = False
        self._button_thread = None
        self._setup_button_handler()
    
    def _setup_display(self) -> None:
        """Initialize display driver."""
        try:
            # Try to import the display driver
            sys.path.insert(0, "/home/aaron/Whisplay/Driver")
            from WhisPlay import WhisPlayBoard
            
            self.display_board = WhisPlayBoard()
            self.display_board.set_backlight(self.settings.brightness)
            logger.info("WhisPlay display initialized")
            
            # Log available methods
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
            # Start button monitoring thread
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
        
        # Use button_pressed() API from WhisPlayBoard
        last_state = False
        
        while self.running:
            try:
                # Call button_pressed() to get current state
                current_state = self.display_board.button_pressed()
                
                # Detect rising edge (button press - transition from False to True)
                if current_state and not last_state:
                    logger.info("🔘 Button pressed - cycling to next location")
                    self.button_pressed = True
                
                last_state = current_state
                time.sleep(0.1)  # Check button every 100ms
                
            except Exception as e:
                logger.error(f"Button monitor error: {e}")
                time.sleep(0.5)
    
    def _display_image(self, image) -> None:
        """Send image to display.
        
        Args:
            image: PIL Image to display
        """
        if not self.has_display or not self.display_board:
            # In headless mode, just log
            logger.debug(f"Would display image: {image.size}")
            return
        
        try:
            # Resize to display size
            if image.size != (240, 280):
                image = image.resize((240, 280))
            
            # Convert to RGB if needed
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Convert RGB to RGB565 format
            pixels = list(image.getdata())
            rgb565_data = []
            for r, g, b in pixels:
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                rgb565_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])
            
            logger.debug(f"Sending {len(rgb565_data)} bytes to display")
            
            # Use draw_image() - verified working by diagnostics
            self.display_board.draw_image(0, 0, 240, 280, rgb565_data)
            logger.debug("Display updated via draw_image()")
            
            self.last_display_update = time.time()
        except Exception as e:
            logger.error(f"Failed to display image: {e}", exc_info=True)
    
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
        self.current_location_index = (self.current_location_index + 1) % len(
            self.locations
        )
        self.location_start_time = time.time()
        logger.info(
            f"Cycled to location {self.current_location_index + 1}/{len(self.locations)}: "
            f"{self.locations[self.current_location_index].name}"
        )
    
    def _update_current_screen(self) -> None:
        """Fetch flights and update current screen."""
        location = self.locations[self.current_location_index]
        
        # Create or update screen
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
        
        # Fetch flights
        flights = self.api.fetch_flights(
            latitude=location.latitude,
            longitude=location.longitude,
            radius_miles=location.radius_miles,
            use_cache=True,
        )
        
        # Update screen with aircraft data
        self.current_screen.set_aircraft(flights)
    
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
                    
                    # Log state every 5 seconds for debugging
                    if current_time - last_log_time >= 5:
                        elapsed_location = current_time - self.location_start_time
                        logger.debug(
                            f"[Loop {loop_count}] Location: {self.current_location_index + 1}/{len(self.locations)}, "
                            f"Elapsed: {elapsed_location:.1f}s/{self.settings.display_duration_seconds}s, "
                            f"Aircraft: {len(self.current_screen.aircraft) if self.current_screen else 0}, "
                            f"Button: {self.button_pressed}"
                        )
                        last_log_time = current_time
                    
                    # Check if time to cycle FIRST (before updating screen)
                    if self._should_cycle_location():
                        logger.info(f"🔄 Cycling to next location (button_pressed={self.button_pressed})")
                        self._cycle_to_next_location()
                        last_displayed_time = 0  # Force immediate display of new location
                    
                    # Update aircraft data if refresh interval elapsed
                    time_since_update = current_time - self.last_display_update
                    if time_since_update >= self.settings.refresh_interval_seconds:
                        logger.debug(f"Fetching aircraft (last update: {time_since_update:.1f}s ago)")
                        self._update_current_screen()
                        last_displayed_time = 0  # Force render after data update
                    
                    # Render and display if needed (throttled to 2 FPS max)
                    if current_time - last_displayed_time >= 0.5:
                        if self.current_screen:
                            image = self.current_screen.render()
                            self._display_image(image)
                            last_displayed_time = current_time
                        else:
                            logger.warning("No current screen to display")
                    
                    # Sleep a bit
                    time.sleep(0.1)
                    
                except KeyboardInterrupt:
                    logger.info("Interrupted by user")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(1)  # Backoff on error
        
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the application."""
        self.running = False
        logger.info("Flight tracker stopped")


def main(config_path: Optional[str] = None):
    """Main entry point.
    
    Args:
        config_path: Optional path to config file
    """
    # Setup logging
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
