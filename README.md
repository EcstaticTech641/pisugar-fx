# Flight Tracker Display

Real-time aircraft tracking display for Raspberry Pi Zero 2W with WhisPlay 1.69" HAT.

## Quick Start

### 1. Configure Locations

Edit `config/flight_locations.json` to set the locations you want to track:

```json
{
  "locations": [
    {
      "name": "OKC (Will Rogers)",
      "latitude": 35.3898,
      "longitude": -97.6007,
      "radius_miles": 100
    },
    {
      "name": "DFW (Dallas/Fort Worth)",
      "latitude": 32.8975,
      "longitude": -97.0380,
      "radius_miles": 100
    }
  ],
  "settings": {
    "display_duration_seconds": 30,
    "refresh_interval_seconds": 10,
    "brightness": 100,
    "rotation": 0,
    "random_location_enabled": false
  }
}
```

**Configuration Options:**
- `name`: Display name for this location
- `latitude`, `longitude`: Center coordinates
- `radius_miles`: Search radius (10-500 miles)
- `display_duration_seconds`: How long to show each location (default: 30s)
- `refresh_interval_seconds`: How often to fetch new data (default: 10s)
- `brightness`: Display brightness 0-100 (default: 100)
- `rotation`: Display rotation in degrees: 0, 90, 180, 270
- `random_location_enabled`: Not yet implemented

### 2. Test Configuration

Before running on hardware, test your setup:

```bash
python3 flight_test.py
```

This will:
- ✓ Validate configuration file
- ✓ Test API connectivity
- ✓ Render a test radar screen
- ✓ Test display hardware (if available)

### 3. Run the Application

```bash
python3 flight_tracker.py
```

Or with verbose logging:

```bash
python3 flight_tracker.py --debug
```

## Display

The 240x280 LCD screen shows:

```
┌────────────────────────┐
│ OKC (Will Rogers) 12:34│  ← Header: Location, Time
│ 5 aircraft             │
├────────────────────────┤
│                        │
│        100mi           │  ← Range rings: 50mi, 100mi
│     ╱─╲                │
│    │ ✕ │  ← Aircraft   │  ← Cyan = Airborne
│     ╲─╱    arrows      │  ← Orange = Ground
│       50mi             │
│                        │  ← Callsigns for top 3 aircraft
│   AAL   SWA   DAL      │
│                        │
└────────────────────────┘
```

**Controls:**
- **Button**: Press to skip to next location
- **Auto-cycle**: Display shows each location for `display_duration_seconds`
- **Auto-refresh**: Fetches new aircraft every `refresh_interval_seconds`

## Data Source

Flight data comes from **airplanes.live** (free, no API key required):
- Covers worldwide ADS-B receivers
- Updates multiple times per minute
- No antenna needed (uses WiFi-based data)

## Performance

- **Startup time**: ~2 seconds (first API call takes longer)
- **Update rate**: Every 10-15 seconds
- **Network usage**: ~2-5 KB per update (~50-150 KB/hour depending on traffic)
- **Memory**: ~30-50 MB typical

## Troubleshooting

### "No data" displayed
- Check WiFi connection: `ping google.com`
- Verify coordinates are correct (should be in US for good coverage)
- API may be temporarily unavailable (check https://api.airplanes.live/)

### Display is blank
- Verify WhisPlay driver is installed: `ls ~/Whisplay/Driver/`
- Check brightness setting in config (0 would appear blank)
- Run `flight_test.py` to diagnose hardware issues

### No aircraft showing
- Check radius is reasonable (10-500 miles)
- Verify coordinates are correct
- May be fewer aircraft during night hours

## File Structure

```
flight/
├── api.py              # airplanes.live API client
├── config.py           # Configuration loader
├── display.py          # Radar rendering engine
├── controller.py       # Main app loop
└── __init__.py
flight_tracker.py       # Entry point script
flight_test.py          # Testing & validation
config/
└── flight_locations.json    # Location configuration
```

## API Details

Uses **airplanes.live v2 API**:
```
GET https://api.airplanes.live/v2/point/{lat}/{lon}/{radius_miles}
```

Response includes:
- Aircraft ICAO code
- Callsign (flight number)
- Position (lat/lon)
- Altitude & speed
- Heading
- Aircraft type
- Registration (tail number)
- Squawk code
- Ground/airborne status

## Limitations

- **US/North America Focus**: Best coverage over populated areas with ADS-B receivers
- **No Antenna**: Uses WiFi-based data (not as real-time as local antenna data)
- **Coverage Gaps**: Rural areas may have limited aircraft visibility
- **Rate Limiting**: API may throttle if many requests from same IP (unlikely)

## Future Enhancements

- [ ] Random location cycling
- [ ] Aircraft details screen (callsign, aircraft type, etc.)
- [ ] Route prediction display
- [ ] History tracking
- [ ] Integration with weather station data
- [ ] Alert system (watch for specific callsigns)

## License

MIT - Feel free to modify and redistribute

## References

- **airplanes.live**: https://airplanes.live/
- **ADS-B Explained**: https://www.faa.gov/nextgen/how-nextgen-works/surveillance/ads-b/
- **WhisPlay Driver**: Built into Raspberry Pi OS for PiSugar HAT

---

https://github.com/PiSugar/PiSugar/wiki/PiSugarS-Series
https://github.com/PiSugar/Whisplay
https://github.com/topics/raspberry-pi-zero-2-w
https://github.com/flightaware/dump1090
https://github.com/flightaware/piaware

---

**Questions?** Check the specs/ directory for detailed design documentation.
