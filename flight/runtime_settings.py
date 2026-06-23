"""
flight/runtime_settings.py

Thread-safe wrapper around FlightTrackerSettings.

The controller holds one RuntimeSettings instance and passes it to
FlightWebServer and the display loop.  All reads and writes go through
the RLock so neither the Flask thread nor the button-monitor thread can
observe a partially-updated settings object.

Usage
-----
    from flight.runtime_settings import RuntimeSettings
    from flight.config import FlightTrackerSettings

    rt = RuntimeSettings(FlightTrackerSettings())

    # controller hot-reload path:
    rt.update(new_settings)

    # consumer path (read a snapshot):
    s = rt.get()
    brightness = s.brightness
"""

import threading
from dataclasses import asdict

from flight.config import FlightTrackerSettings


class RuntimeSettings:
    """Lock-protected live view of FlightTrackerSettings.

    The underlying ``FlightTrackerSettings`` instance is replaced atomically
    on every ``update()`` call — consumers that hold a reference to a previous
    snapshot via ``get()`` continue to see the old values, which is the
    desired behaviour (no partial reads mid-render).
    """

    def __init__(self, settings: FlightTrackerSettings) -> None:
        self._lock = threading.RLock()
        self._settings: FlightTrackerSettings = settings

    def update(self, new_settings: FlightTrackerSettings) -> None:
        """Replace settings atomically.

        Called from the hot-reload path in the controller.  The previous
        object is discarded; any thread that already called ``get()`` and
        holds a local reference will keep seeing the old snapshot — that is
        safe because ``FlightTrackerSettings`` is a plain dataclass with no
        internal mutation after construction.

        Args:
            new_settings: Fully-parsed replacement ``FlightTrackerSettings``.
        """
        with self._lock:
            self._settings = new_settings

    def get(self) -> FlightTrackerSettings:
        """Return a snapshot of the current settings.

        The returned object is the live instance (not a copy).  Callers
        should read what they need immediately and not store the reference
        across a yield point where hot-reload might occur.  Because the
        dataclass is never mutated in place (``update()`` replaces the whole
        object), brief reads are always consistent.

        Returns:
            Current ``FlightTrackerSettings`` instance.
        """
        with self._lock:
            return self._settings

    def as_dict(self) -> dict:
        """Return the current settings as a plain dictionary.

        Useful for the ``/settings`` GET endpoint which needs to serialise
        all values to populate the HTML form.

        Returns:
            Flat ``dict`` produced by ``dataclasses.asdict()``.
        """
        with self._lock:
            return asdict(self._settings)
