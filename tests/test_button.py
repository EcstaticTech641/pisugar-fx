import time
from flight.button import ButtonClassifier, ButtonEvent

def test_single_click():
    events = []
    state = {"pressed": False}
    c = ButtonClassifier(lambda: state["pressed"], lambda e: events.append(e))
    c.start()
    
    # Press button
    state["pressed"] = True
    time.sleep(0.1)
    state["pressed"] = False
    
    # Wait for the double click window to elapse
    time.sleep(0.6)
    c.stop()
    assert events == [ButtonEvent.SINGLE_CLICK]

def test_double_click():
    events = []
    state = {"pressed": False}
    c = ButtonClassifier(lambda: state["pressed"], lambda e: events.append(e))
    c.start()
    
    # First press
    state["pressed"] = True
    time.sleep(0.05)
    state["pressed"] = False
    time.sleep(0.1)
    
    # Second press (within double-click window)
    state["pressed"] = True
    time.sleep(0.05)
    state["pressed"] = False
    
    # Wait for completion
    time.sleep(0.6)
    c.stop()
    assert events == [ButtonEvent.DOUBLE_CLICK]

def test_long_press():
    events = []
    state = {"pressed": False}
    c = ButtonClassifier(lambda: state["pressed"], lambda e: events.append(e))
    c.start()
    
    # Long press (held for > LONG_PRESS_THRESHOLD)
    state["pressed"] = True
    time.sleep(1.2)
    state["pressed"] = False
    
    # Wait for any potential trailing events to settle
    time.sleep(0.6)
    c.stop()
    assert events == [ButtonEvent.LONG_PRESS]
