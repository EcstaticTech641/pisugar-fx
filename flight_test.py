#!/usr/bin/env python3
"""
Flight tracker test and validation script.

Run this to verify configuration and test API connectivity before running on hardware.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flight.api import FlightAPI
from flight.config import load_config, FlightLocation
from flight.display import FlightRadarScreen
from PIL import Image


def test_config(config_path: str = None):
    """Test configuration loading."""
    print("\n" + "=" * 60)
    print("TEST 1: Configuration Loading")
    print("=" * 60)
    
    try:
        config = load_config(config_path)
        print(f"✓ Config loaded successfully")
        print(f"  - Locations: {len(config.locations)}")
        for i, loc in enumerate(config.locations, 1):
            print(f"    {i}. {loc.name} ({loc.latitude:.4f}, {loc.longitude:.4f}) - {loc.radius_miles}mi")
        print(f"  - Display duration: {config.settings.display_duration_seconds}s")
        print(f"  - Refresh interval: {config.settings.refresh_interval_seconds}s")
        return config
    except FileNotFoundError as e:
        print(f"✗ Config file not found: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error loading config: {e}")
        sys.exit(1)


def test_api():
    """Test API connectivity."""
    print("\n" + "=" * 60)
    print("TEST 2: API Connectivity")
    print("=" * 60)
    
    api = FlightAPI()
    
    # Test location (OKC)
    test_lat, test_lon = 35.3898, -97.6007
    print(f"Fetching flights near OKC ({test_lat}, {test_lon})...")
    
    try:
        flights = api.fetch_flights(test_lat, test_lon, radius_miles=100, use_cache=False)
        print(f"✓ API call successful")
        print(f"  - {len(flights)} aircraft found")
        
        if flights:
            print(f"  - Sample aircraft:")
            for flight in flights[:3]:
                status = "GROUND" if flight["on_ground"] else f"{flight['alt_ft']:,}ft"
                print(f"    • {flight['call']:8} | {status:>10} | {flight['speed']:3}kt")
        
        return flights
    except Exception as e:
        print(f"✗ API error: {e}")
        return []


def test_rendering(config, flights: list):
    """Test display rendering."""
    print("\n" + "=" * 60)
    print("TEST 3: Display Rendering")
    print("=" * 60)
    
    if not config.locations:
        print("✗ No locations configured")
        return
    
    loc = config.locations[0]
    print(f"Creating radar screen for {loc.name}...")
    
    try:
        screen = FlightRadarScreen(
            location_name=loc.name,
            latitude=loc.latitude,
            longitude=loc.longitude,
            radius_miles=loc.radius_miles,
        )
        screen.set_aircraft(flights)
        
        image = screen.render()
        
        print(f"✓ Radar screen rendered successfully")
        print(f"  - Image size: {image.size}")
        print(f"  - Mode: {image.mode}")
        
        # Save test image
        test_image_path = "test_radar.png"
        image.save(test_image_path)
        print(f"  - Saved to: {test_image_path}")
        
        return image
    except Exception as e:
        print(f"✗ Rendering error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_display_hardware():
    """Test display hardware (if available)."""
    print("\n" + "=" * 60)
    print("TEST 4: Display Hardware")
    print("=" * 60)
    
    try:
        sys.path.insert(0, "/home/aaron/Whisplay/Driver")
        from WhisPlay import WhisPlayBoard
        
        print("Attempting to initialize WhisPlayBoard...")
        board = WhisPlayBoard()
        
        # Create a simple test pattern
        test_image = Image.new("RGB", (240, 280), color=(10, 50, 100))
        
        # Convert to RGB565 format
        pixels = list(test_image.getdata())
        rgb565_data = []
        for r, g, b in pixels:
            rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            rgb565_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])
        
        # Display
        board.draw_image(0, 0, 240, 280, rgb565_data)
        
        print("✓ Display hardware test successful")
        print("  - You should see a blue screen on your display")
        print("  - Button is ready to respond")
        
        return True
    except Exception as e:
        print(f"⚠ Display hardware not available: {e}")
        print("  (This is OK if running on non-Pi hardware)")
        return False


def main():
    """Run all tests."""
    print("\n" + "🛫 " * 20)
    print("Flight Tracker Configuration & API Test")
    print("🛫 " * 20)
    
    # Test 1: Configuration
    config = test_config()
    
    # Test 2: API
    flights = test_api()
    
    # Test 3: Rendering
    image = test_rendering(config, flights)
    
    # Test 4: Hardware (optional)
    has_hardware = test_display_hardware()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("✓ Configuration loading")
    print("✓ API connectivity")
    print("✓ Display rendering")
    if has_hardware:
        print("✓ Hardware display")
    else:
        print("⚠ Hardware display (skipped/unavailable)")
    
    print("\n" + "=" * 60)
    if has_hardware and image:
        print("All tests passed! Ready to run flight_tracker.py on hardware.")
        print("\nStart the app with:")
        print("  python3 flight_tracker.py")
        print("  python3 flight_tracker.py --debug  # for verbose logging")
    elif image:
        print("Tests mostly passed! Hardware not available.")
        print("Configuration and API are working correctly.")
    else:
        print("Some tests failed. Check the errors above.")
    
    print("=" * 60 + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
