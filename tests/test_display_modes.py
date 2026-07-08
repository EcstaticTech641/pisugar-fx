import time
from flight.display_modes import DisplayStateMachine, DisplayMode, Aircraft

def make_aircraft(call="TEST1", alt=10000):
    return Aircraft(icao="ABC123", call=call, lat=35.0, lon=-97.0,
                     alt_ft=alt, speed=300, heading=90)

def test_radar_to_list_single_click():
    sm = DisplayStateMachine()
    sm.handle_single_click()
    assert sm.mode == DisplayMode.AIRCRAFT_LIST

def test_list_scroll_wraps():
    sm = DisplayStateMachine()
    sm.set_aircraft([make_aircraft("A"), make_aircraft("B"), make_aircraft("C")])
    sm.mode = DisplayMode.AIRCRAFT_LIST
    sm.handle_single_click()
    assert sm.selected_index == 1
    sm.handle_single_click()
    assert sm.selected_index == 2
    sm.handle_single_click()
    assert sm.selected_index == 0

def test_double_click_enters_detail():
    sm = DisplayStateMachine()
    sm.set_aircraft([make_aircraft()])
    sm.mode = DisplayMode.AIRCRAFT_LIST
    sm.handle_double_click()
    assert sm.mode == DisplayMode.DETAIL

def test_long_press_from_list_returns_to_radar():
    sm = DisplayStateMachine()
    sm.mode = DisplayMode.AIRCRAFT_LIST
    sm.handle_long_press()
    assert sm.mode == DisplayMode.RADAR

def test_long_press_from_detail_returns_to_list():
    sm = DisplayStateMachine()
    sm.mode = DisplayMode.DETAIL
    sm.handle_long_press()
    assert sm.mode == DisplayMode.AIRCRAFT_LIST

def test_detail_timeout_returns_to_radar():
    sm = DisplayStateMachine()
    sm.mode = DisplayMode.DETAIL
    sm.DETAIL_VIEW_TIMEOUT = 0.1
    sm._last_interaction_time = time.time() - 1.0
    sm.check_detail_timeout()
    assert sm.mode == DisplayMode.RADAR

def test_radar_double_click_is_noop():
    sm = DisplayStateMachine()
    sm.handle_double_click()
    assert sm.mode == DisplayMode.RADAR
