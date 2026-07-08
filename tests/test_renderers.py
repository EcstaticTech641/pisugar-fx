from flight.display_modes import Aircraft
from flight.display import render_aircraft_list, render_aircraft_detail
from PIL import Image

def test_render_aircraft_list():
    ac_list = [
        Aircraft(icao="ABC123", call="TEST1", lat=35.0, lon=-97.0, alt_ft=12000, speed=250, heading=90, reg="N123", type="C172", squawk="1200"),
        Aircraft(icao="DEF456", call="TEST2", lat=35.1, lon=-97.1, alt_ft=8000, speed=180, heading=180, reg="N456", type="PA28", squawk="1200", on_ground=True),
    ]
    img = render_aircraft_list(ac_list, selected_index=0)
    assert isinstance(img, Image.Image)
    assert img.size == (240, 280)

def test_render_aircraft_detail():
    ac = Aircraft(icao="ABC123", call="TEST1", lat=35.0, lon=-97.0, alt_ft=12000, speed=250, heading=90, reg="N123", type="C172", squawk="1200", rssi=-10.5, seen=1.2)
    img = render_aircraft_detail(ac, observer_lat=35.0, observer_lon=-97.0)
    assert isinstance(img, Image.Image)
    assert img.size == (240, 280)
