import unittest
import unittest.mock
import time
import os
import sys

# Add parent directory to path to import flight modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flight.location import nearest_town, LocationProvider, _centroid_from_aircraft

class TestLocation(unittest.TestCase):
    def test_nearest_town_stillwater(self):
        # Stillwater coords: 36.11561, -97.05837
        # We query slightly offset: 36.11, -97.06
        name, country = nearest_town(36.11, -97.06)
        self.assertEqual(name, "Stillwater")
        self.assertEqual(country, "US")

    def test_nearest_town_st_johns(self):
        # Saint John's coords: 17.12096, -61.84329
        # GeoNames stores the name with a right single quotation mark (U+2019)
        name, country = nearest_town(17.12, -61.84)
        self.assertEqual(name, "Saint John\u2019s")
        self.assertEqual(country, "AG")

    def test_nearest_town_perf(self):
        # Query Stillwater coordinates repeatedly to benchmark performance
        lat, lon = 36.11, -97.06

        # Warm up
        nearest_town(lat, lon)

        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            nearest_town(lat, lon)
        end = time.perf_counter()

        avg_ms = ((end - start) / iterations) * 1000
        print(f"\n[Perf Test] Average nearest_town lookup time: {avg_ms:.2f} ms")
        self.assertLess(avg_ms, 20.0, "Lookup should take less than 20ms")

    @unittest.mock.patch("urllib.request.urlopen")
    def test_location_provider_success(self, mock_urlopen):
        # Set up mock response for Stillwater coords
        mock_response = unittest.mock.MagicMock()
        mock_response.read.return_value = b'{"latitude": 36.11561, "longitude": -97.05837, "city": "Stillwater"}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = LocationProvider()
        lat, lon, label = provider.detect()

        self.assertAlmostEqual(lat, 36.11561)
        self.assertAlmostEqual(lon, -97.05837)
        self.assertEqual(label, "Stillwater, US")

    @unittest.mock.patch("urllib.request.urlopen")
    def test_location_provider_failure(self, mock_urlopen):
        # Simulate network error with no aircraft either — full fallback to Unknown
        mock_urlopen.side_effect = Exception("Network timeout")

        provider = LocationProvider()
        lat, lon, label = provider.detect()

        self.assertIsNone(lat)
        self.assertIsNone(lon)
        self.assertEqual(label, "Unknown Location")

    # ── Centroid helper tests ────────────────────────────────────────────────

    def test_centroid_too_few_aircraft(self):
        # Fewer than 3 aircraft → (None, None)
        aircraft = [
            {"lat": 36.1, "lon": -97.0},
            {"lat": 36.2, "lon": -97.1},
        ]
        lat, lon = _centroid_from_aircraft(aircraft)
        self.assertIsNone(lat)
        self.assertIsNone(lon)

    def test_centroid_missing_position(self):
        # Aircraft without lat/lon are ignored; still need 3 with fixes
        aircraft = [
            {"lat": 36.1, "lon": -97.0},
            {"lat": None, "lon": None},   # no fix — ignored
            {"lat": 36.3, "lon": -97.2},
        ]
        lat, lon = _centroid_from_aircraft(aircraft)
        self.assertIsNone(lat)
        self.assertIsNone(lon)

    def test_centroid_odd_count(self):
        # Odd count → middle value is the median
        aircraft = [
            {"lat": 36.0, "lon": -97.0},
            {"lat": 36.2, "lon": -97.2},
            {"lat": 36.4, "lon": -97.4},
        ]
        lat, lon = _centroid_from_aircraft(aircraft)
        self.assertAlmostEqual(lat, 36.2)
        self.assertAlmostEqual(lon, -97.2)

    def test_centroid_even_count(self):
        # Even count → average of two middle values
        aircraft = [
            {"lat": 36.0, "lon": -97.0},
            {"lat": 36.2, "lon": -97.2},
            {"lat": 36.4, "lon": -97.4},
            {"lat": 36.6, "lon": -97.6},
        ]
        lat, lon = _centroid_from_aircraft(aircraft)
        self.assertAlmostEqual(lat, 36.3)
        self.assertAlmostEqual(lon, -97.3)

    @unittest.mock.patch("urllib.request.urlopen")
    def test_centroid_used_when_ip_fails(self, mock_urlopen):
        # IP geolocation fails but 3+ aircraft available →
        # detect() should resolve via centroid
        mock_urlopen.side_effect = Exception("Network timeout")

        # Aircraft clustered near Stillwater, OK
        aircraft = [
            {"lat": 36.0, "lon": -97.0},
            {"lat": 36.1, "lon": -97.1},
            {"lat": 36.2, "lon": -97.2},
        ]

        provider = LocationProvider()
        lat, lon, label = provider.detect(aircraft_list=aircraft)

        self.assertIsNotNone(lat)
        self.assertIsNotNone(lon)
        # Label should be a real town name, not "Unknown Location"
        self.assertNotEqual(label, "Unknown Location")
        print(f"\n[Centroid Test] Resolved to: {label} ({lat:.4f}, {lon:.4f})")

if __name__ == "__main__":
    unittest.main()

