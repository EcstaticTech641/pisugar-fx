"""Button event classification: single click, double click, long press."""

import logging
import threading
import time
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ButtonEvent(Enum):
    SINGLE_CLICK = "single_click"
    DOUBLE_CLICK = "double_click"
    LONG_PRESS = "long_press"


class ButtonClassifier:
    """Classifies raw button presses into single/double click or long press."""

    LONG_PRESS_THRESHOLD = 1.0   # seconds held = long press
    DOUBLE_CLICK_WINDOW = 0.4    # seconds between clicks = double click
    POLL_INTERVAL = 0.03         # 30ms poll rate

    def __init__(self, button_state_fn: Callable[[], bool], on_event: Callable[[ButtonEvent], None]):
        self._button_state_fn = button_state_fn
        self._on_event = on_event
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Button classifier started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        last_state = False
        press_start: Optional[float] = None
        pending_single_click_time: Optional[float] = None

        while self._running:
            try:
                current_state = self._button_state_fn()

                if current_state and not last_state:
                    press_start = time.time()

                if not current_state and last_state and press_start is not None:
                    duration = time.time() - press_start
                    press_start = None

                    if duration >= self.LONG_PRESS_THRESHOLD:
                        self._emit(ButtonEvent.LONG_PRESS)
                        pending_single_click_time = None
                    else:
                        if pending_single_click_time is not None:
                            self._emit(ButtonEvent.DOUBLE_CLICK)
                            pending_single_click_time = None
                        else:
                            pending_single_click_time = time.time()

                if pending_single_click_time is not None:
                    if time.time() - pending_single_click_time >= self.DOUBLE_CLICK_WINDOW:
                        self._emit(ButtonEvent.SINGLE_CLICK)
                        pending_single_click_time = None

                last_state = current_state
                time.sleep(self.POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Button classifier error: {e}")
                time.sleep(0.5)

    def _emit(self, event: ButtonEvent):
        logger.debug(f"Button event: {event.value}")
        try:
            self._on_event(event)
        except Exception as e:
            logger.error(f"Error handling button event {event}: {e}")
