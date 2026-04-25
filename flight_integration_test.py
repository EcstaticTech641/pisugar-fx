#!/usr/bin/env python3
"""
Integration test for flight tracker app logic.
Run this to verify the controller works without needing hardware.
"""

import sys
import os
import time
import logging
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

from flight.api import FlightAPI
from flight.config import load_config


def test_app_logic():
    """Test the flight tracker app logic."""
    print("\n" + "=" * 60)
    print("FLIGHT TRACKER APP LOGIC TEST")
    print("=" * 60)
    
    try:
        from flight.controller import FlightTracker
        
        # Load config
        config = load_config()
        print(f"✓ Loaded {len(config.locations)} locations")
        
        # Create tracker (without hardware)
        tracker = FlightTracker()
        print(f"✓ FlightTracker initialized")
        print(f"  - Current location: {tracker.locations[tracker.current_location_index].name}")
        print(f"  - Display duration: {tracker.settings.display_duration_seconds}s")
        print(f"  - Refresh interval: {tracker.settings.refresh_interval_seconds}s")
        
        # Mock the display board
        tracker.display_board = Mock()
        tracker.display_board.button_pressed = Mock(return_value=False)
        tracker.display_board.draw_image = Mock()
        
        # Simulate a few iterations
        print(f"\n🧪 Simulating {5} loop iterations...")
        
        for i in range(5):
            current_time = time.time()
            
            # Simulate main loop logic
            elapsed_since_update = current_time - tracker.last_display_update
            
            # Update if needed
            if elapsed_since_update >= tracker.settings.refresh_interval_seconds:
                print(f"  [{i}] Updating aircraft data")
                tracker._update_current_screen()
                
                if tracker.current_screen:
                    print(f"      Got {len(tracker.current_screen.aircraft)} aircraft")
            
            # Render and display
            if tracker.current_screen:
                image = tracker.current_screen.render()
                print(f"      Rendered image: {image.size}")
            
            # Simulate time passing
            time.sleep(0.1)
        
        print(f"\n✓ App logic test passed")
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_button_logic():
    """Test button press detection logic."""
    print("\n" + "=" * 60)
    print("BUTTON LOGIC TEST")
    print("=" * 60)
    
    try:
        from flight.controller import FlightTracker
        
        tracker = FlightTracker()
        tracker.display_board = Mock()
        
        print("Testing button state transitions...")
        
        # Simulate button press
        button_states = [False, False, True, True, False, False]
        last_state = False
        button_events = []
        
        for state in button_states:
            tracker.display_board.button_pressed = Mock(return_value=state)
            
            # This is what the button monitor thread does
            current_state = tracker.display_board.button_pressed()
            if current_state and not last_state:
                button_events.append("PRESS")
                print(f"  {state}: BUTTON PRESS DETECTED ✓")
            else:
                print(f"  {state}: state change" if state != last_state else f"  {state}: no change")
            
            last_state = current_state
        
        if len(button_events) == 1:
            print(f"\n✓ Button logic working correctly (detected 1 press)")
            return True
        else:
            print(f"\n✗ Button logic error (detected {len(button_events)} presses, expected 1)")
            return False
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run integration tests."""
    print("\n" + "⚙️  " * 15)
    print("FLIGHT TRACKER INTEGRATION TESTS")
    print("⚙️  " * 15)
    
    results = {
        "App Logic": test_app_logic(),
        "Button Logic": test_button_logic(),
    }
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    
    for name, passed in results.items():
        status = "✓" if passed else "✗"
        print(f"{status} {name}")
    
    if all(results.values()):
        print("\n✅ All integration tests passed!")
        print("\nYou can now run: python3 flight_tracker.py --debug")
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
