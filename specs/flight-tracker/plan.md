# Implementation Plan: Flight Tracker Display

**Status**: ✅ COMPLETE — Historical Record  
**Date**: 2026-04-24  
**Completed**: 2026-06-22  
**Spec**: specs/flight-tracker/spec.md

> **Note:** This plan is preserved as a historical record of the original implementation stages. All four stages were completed successfully. For the current architecture and implemented feature set, see [`status.md`](./status.md). For the updated specification reflecting the built system, see [`spec.md`](./spec.md).

## Summary

Build a standalone flight tracking app that cycles through configured locations, showing real-time aircraft as a radar-style display on the WhisPlay HAT. Updates every 10-15 seconds with data from airplanes.live API.

## Technical Context

**Language/Version**: Python 3.11+  
**Display**: WhisPlay 1.69" LCD (240x280), RGB565 format  
**Data Source**: airplanes.live API (v2)  
**Primary Dependencies**: requests, PIL/Pillow (already available)  
**Testing**: pytest with mock API responses  
**Performance Target**: <2 sec per display update

## Project Structure

### New Files to Create
```
flight/
├── __init__.py              # Package init
├── config.py                # Config loading for flight locations
├── display.py               # Flight radar rendering engine
├── api.py                   # airplanes.live API client
├── controller.py            # Main app loop & state management
└── requirements.txt         # Dependencies
```

### Modify/Reuse
```
flight/app.py               # Keep Flask backend (optional - we can call API directly)
src/display.py              # Reuse WhisPlayBoard display driver
```

## Implementation Stages

### Stage 1: Core API & Data (Day 1)
- [ ] `flight/api.py` - Fetch flights from airplanes.live
  - Implement `fetch_flights(lat, lon, radius)`
  - Handle timeouts, errors
  - Add caching decorator
- [ ] `flight/config.py` - Load flight locations from JSON
  - Parse `config/flight_locations.json`
  - Validation for coordinates, radius

### Stage 2: Rendering Engine (Day 1)
- [ ] `flight/display.py` - Radar rendering 
  - `FlightRadarScreen` class
  - Header rendering (location name, timestamp, count)
  - Range rings and crosshairs
  - Aircraft arrow drawing (in-air cyan, ground orange)
  - Text labels for top aircraft
  - Color scheme (dark background, accent cyan)

### Stage 3: Application Loop (Day 2)
- [ ] `flight/controller.py` - Main app
  - Location cycling logic
  - Button event handling
  - Thread-safe state management
  - Error recovery and logging

### Stage 4: Configuration & Testing (Day 2)
- [ ] Create `config/flight_locations.json` with sample locations
- [ ] Add pytest test cases for API, rendering
- [ ] Test with real hardware

## Data Flow

```
┌─────────────────────────────┐
│  Start App (controller.py)  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Load Locations & Settings  │
│  (config.py)                │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Fetch Flight Data          │
│  (api.py → airplanes.live)  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Render Radar Screen        │
│  (display.py → PIL Image)   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Display on WhisPlay HAT    │
│  (src/display.py)           │
└──────────────┬──────────────┘
               │
               ▼
   ┌─────────────────────────┐
   │  Wait 10-15 seconds     │
   │  or button press        │
   └──────────┬──────────────┘
              │
              ▼ (button or timer expires)
   ┌─────────────────────────┐
   │  Next Location          │
   │  (cycle)                │
   └──────────┬──────────────┘
              │
              └──────────┐
                         │
                         └──►  (back to Fetch)
```

## Key Components Details

### FlightRadarScreen (display.py)

```python
class FlightRadarScreen:
    def __init__(self, location_name, lat, lon, radius_miles=100):
        self.location_name = location_name
        self.center_lat = lat
        self.center_lon = lon
        self.radius = radius_miles
        self.aircraft = []
        self.timestamp = None
    
    def set_aircraft(self, flights):
        """Update aircraft list from API response."""
        self.aircraft = flights
        self.timestamp = datetime.now()
    
    def render(self) -> Image:
        """Generate PIL Image for display."""
        # Create 240x280 image
        # Draw header (name, time, count)
        # Draw range rings
        # Draw crosshairs
        # Draw aircraft as arrows
        # Draw labels
```

### FlightController (controller.py)

```python
class FlightController:
    def __init__(self, config_path):
        self.locations = load_locations(config_path)
        self.current_index = 0
        self.display_duration = 30  # seconds
        self.last_update = 0
        self.refresh_interval = 10  # seconds
    
    def run(self):
        """Main application loop."""
        while True:
            current_location = self.locations[self.current_index]
            # Fetch flights
            # Render screen
            # Display
            # Wait for input or timeout
            # Cycle if needed
```

### Configuration File (config/flight_locations.json)

```json
{
  "locations": [
    {
      "name": "Okc (Will Rogers)",
      "latitude": 35.3898,
      "longitude": -97.6007,
      "radius_miles": 100
    },
    {
      "name": "DFW Area",
      "latitude": 32.8975,
      "longitude": -97.0380,
      "radius_miles": 100
    }
  ],
  "settings": {
    "display_duration_seconds": 30,
    "refresh_interval_seconds": 10,
    "random_location_enabled": false
  }
}
```

## Testing Strategy

### Unit Tests
- API caching behavior
- Coordinate to pixel transformation
- Aircraft filtering (in-air vs ground)

### Integration Tests
- Full cycle through locations
- Error handling (network timeout, invalid config)
- Display rendering with various aircraft counts

### Manual Testing
- Real hardware display quality
- Button responsiveness
- Long-running stability (1+ hour)

## Success Criteria

✅ **Stage 1**: Can fetch and parse real flight data  
✅ **Stage 2**: Render realistic radar screen with test aircraft  
✅ **Stage 3**: Cycles through locations, responds to button  
✅ **Stage 4**: Runs for 1+ hour without crashes  

## Estimated Timeline

- **Stage 1**: 1-2 hours (API + config)
- **Stage 2**: 2-3 hours (rendering engine)
- **Stage 3**: 1-2 hours (controller + button handling)
- **Stage 4**: 1 hour (testing + refinement)

**Total: 5-8 hours** for MVP with all core features
