import time
import threading
from flight.web_server import SharedState, FlightWebServer
from PIL import Image

def main():
    state = SharedState()
    
    # Mock data
    img = Image.new('RGB', (240, 280), color = 'red')
    aircraft = [
        {"hex": "a123", "lat": 36.1, "lon": -97.0, "alt_ft": 10000, "gs": 400, "heading": 90, "on_ground": False, "call": "TEST12"}
    ]
    state.update(img, aircraft, "Test Location")
    
    server = FlightWebServer(state, port=5000)
    server.start()
    
    time.sleep(10) # Run for 10 seconds

if __name__ == "__main__":
    main()
