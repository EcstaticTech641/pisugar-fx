# Specification: Flight Tracker Display

**Project**: PiSugar Flight Tracker  
**Date**: 2026-04-24  
**Status**: Active Development  
**Hardware**: Raspberry Pi Zero 2W + WhisPlay 1.69" HAT (240x280)

## Overview

Display real-time aircraft tracking on a 240x280 LCD screen. Cycles through multiple configured locations, showing a radar-style view of nearby aircraft within a 50-100 mile radius. Fetches live flight data from airplanes.live API via WiFi.

## User Stories

### US1: View Aircraft Radar (Priority: P1) MVP
**As a** user with a Raspberry Pi
**I want** to see nearby aircraft plotted on a radar display  
**So that** I can track flights in real-time around my location

**Acceptance Criteria:**
- Display shows center crosshairs and two range rings (50 mi, 100 mi)
- Each aircraft shown as directional arrow with heading
- Aircraft colored differently if on ground vs in air
- Location name shown in header
- Display updates every 10-15 seconds

### US2: Cycle Multiple Locations (Priority: P1) MVP
**As a** a user with multiple locations of interest
**I want** to cycle through different locations with configurable duration  
**So that** I can monitor aircraft activity around multiple airports/areas

**Acceptance Criteria:**
- Locations defined in `config/flight_locations.json`
- Each location displays for 30 seconds before cycling
- Button press skips to next location
- Configuration includes: name, latitude, longitude, radius (optional)
- Random location option available

### US3: Show Aircraft Details (Priority: P2)
**As a** a flight enthusiast
**I want** to see details about highlighted/nearest aircraft  
**So that** I understand what types of flights are in the area

**Acceptance Criteria:**
- Callsign displayed for selected aircraft
- Optional: altitude, speed, squawk code shown in list/detail view
- Heading indicator shows aircraft direction
- Ground traffic vs airborne clearly distinguished

### US4: Responsive Button Control (Priority: P1) MVP
**As a** a user
**I want** to press the WhisPlay button to skip to next location
**So that** I can quickly browse through different areas

**Acceptance Criteria:**
- Single button press cycles to next location
- Same button behavior as weather app
- No delay in response

## Functional Requirements

### FR1: Data Source
- Primary: airplanes.live API endpoint (`/v2/point/{lat}/{lon}/{miles}`)
- Query: All aircraft within specified radius
- Response contains: ICAO, callsign, lat/lon, altitude, speed, heading, type, registration, squawk

### FR2: Radar Rendering
- Display dimensions: 240x280 pixels
- Header: location name, timestamp, aircraft count (36px height)
- Radar area: 244px height with center crosshairs
- Range rings: 50 miles, 100 miles
- Center point: (120, 158)
- Scale: ~1.1 pixel/mile for 100-mile radius

### FR3: Aircraft Rendering
- Directional arrows showing heading
- In-air aircraft: cyan (#00E5FF)
- Ground aircraft: orange (#FF6B35)
- Callsign label for top 1-2 aircraft per location
- Plane symbol updates position every 10-15 seconds

### FR4: Performance
- API call should complete within 5 seconds
- Display update should complete within 2 seconds
- Cycling loop runs indefinitely with configurable timing
- Minimal memory usage on Pi Zero 2W

### FR5: Error Handling
- Network timeout: show "No data" in header, continue cycling
- API errors: log and skip that location's fetch
- Display continues to show last valid data if fetch fails
- Graceful degradation (no crash on network issues)

### FR6: Caching
- Cache recent responses for 60 seconds to reduce API calls
- Implement smart request rate limiting

## Non-Functional Requirements

### NFR1: Display Quality
- Clear, readable text in 240x280 constraint
- High contrast for outdoor/bright viewing
- Smooth, no flicker between updates

### NFR2: Hardware Integration
- Work with WhisPlay HAT RGB565 format
- Use WhisPlayBoard driver correctly
- Respect button input through WhisPlayBoard
- Handle display brightness appropriately

### NFR3: Reliability
- Run continuously without crashes
- Recover gracefully from network issues
- Handle location cycling indefinitely

### NFR4: User Experience
- First display appears within 5 seconds of start
- Smooth transitions between locations
- Intuitive controls (button = next location)
