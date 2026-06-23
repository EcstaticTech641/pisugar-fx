#!/usr/bin/env python3
"""Flight tracker application entry point.

Pipeline
--------
1. Parse CLI arguments.
2. Load ``config/flight_locations.json`` (or ``--config`` path).
3. Apply any CLI overrides (CLI wins over JSON file values).
4. Hand the fully-cooked config to the controller.

CLI flags let you tweak hot-reloadable settings at startup without editing
the JSON file.  They do *not* persist — the JSON file is unchanged.
"""

import argparse
import logging
import os
import sys

# Ensure the project root is importable whether the script is run from the
# project root or from another directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flight.config import load_config


def apply_cli_overrides(config, args):
    """Overlay non-None CLI arguments on top of the loaded config.

    CLI always wins over the JSON file.  Only fields that were explicitly
    supplied on the command line are touched; everything else is left as
    loaded from the config file.

    ``--source`` is treated as a startup-time override only.  It does not
    enable live source switching mid-run.

    Args:
        config: ``FlightTrackerConfig`` returned by ``load_config()``.
        args:   ``argparse.Namespace`` from the entry-point parser.

    Returns:
        The same ``config`` object with ``config.settings`` mutated in place.
    """
    s = config.settings

    # Restart-required (applied at startup only, never hot-reloaded)
    if args.source is not None:
        s.source = args.source

    # radius_miles: stored in settings as an override sentinel.
    # The controller reads ``settings.radius_miles is not None`` and applies
    # it at FlightRadarScreen construction time.
    if args.radius_miles is not None:
        s.radius_miles = args.radius_miles

    # Hot-reloadable fields — straightforward overrides
    if args.ghost_holdover_seconds is not None:
        s.ghost_holdover_seconds = args.ghost_holdover_seconds
    if args.trail_length is not None:
        s.trail_length = args.trail_length
    if args.refresh_interval_seconds is not None:
        s.refresh_interval_seconds = args.refresh_interval_seconds
    if args.brightness is not None:
        s.brightness = args.brightness
    if args.web_mirror_jpeg_quality is not None:
        s.web_mirror_jpeg_quality = args.web_mirror_jpeg_quality

    # Boolean flags: store_true means the flag is only set when explicitly
    # passed, so we never accidentally disable a feature that was enabled in
    # the JSON file.
    if args.no_trails:
        s.trail_enabled = False
    if args.no_ghosts:
        s.ghost_enabled = False

    if args.callsign_rule is not None:
        s.callsign_rule = args.callsign_rule

    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Flight tracking display for Raspberry Pi with WhisPlay HAT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "CLI flags override the corresponding values in flight_locations.json\n"
            "at startup only.  They do not modify the JSON file.\n\n"
            "Restart-required flags: --source\n"
            "Hot-reloadable flags:   all others"
        ),
    )

    # ── Config & logging ─────────────────────────────────────────────────────
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to flight_locations.json (default: config/flight_locations.json)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    # ── Restart-required overrides ────────────────────────────────────────────
    parser.add_argument(
        "--source",
        choices=["local", "api"],
        default=None,
        help="Data source: 'local' (RTL-SDR/readsb) or 'api' (airplanes.live). "
             "Restart required to change mid-run.",
    )

    # ── Hot-reloadable overrides ──────────────────────────────────────────────
    parser.add_argument(
        "--radius-miles",
        type=int,
        dest="radius_miles",
        default=None,
        metavar="MILES",
        help="Tracking radius in miles (10–500). Applied to all locations.",
    )
    parser.add_argument(
        "--ghost-holdover-seconds",
        type=int,
        dest="ghost_holdover_seconds",
        default=None,
        metavar="SECS",
        help="How long to project ghost positions after signal loss (10–300 s).",
    )
    parser.add_argument(
        "--trail-length",
        type=int,
        dest="trail_length",
        default=None,
        metavar="N",
        help="Number of historical positions to keep per aircraft (0–20).",
    )
    parser.add_argument(
        "--refresh-interval",
        type=int,
        dest="refresh_interval_seconds",
        default=None,
        metavar="SECS",
        help="Flight data fetch interval in seconds (2–60).",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=None,
        metavar="PCT",
        help="Display backlight brightness, 0–100.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        dest="web_mirror_jpeg_quality",
        default=None,
        metavar="Q",
        help="Web mirror JPEG quality (30–95). Lower = smaller, faster.",
    )
    parser.add_argument(
        "--no-trails",
        action="store_true",
        help="Disable aircraft trail rendering.",
    )
    parser.add_argument(
        "--no-ghosts",
        action="store_true",
        help="Disable ghost/projected position rendering.",
    )
    parser.add_argument(
        "--callsign-rule",
        dest="callsign_rule",
        choices=["nearest", "highest", "busiest"],
        default=None,
        help="Which aircraft get callsign labels: nearest (default), "
             "highest (altitude), or busiest (most ADS-B messages).",
    )

    args = parser.parse_args()

    # ── Logging ───────────────────────────────────────────────────────────────
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    # ── Load → override → run ─────────────────────────────────────────────────
    # Import here so the sys.path insertion above is in effect.
    from flight.config import load_config
    from flight.controller import main

    config = load_config(args.config)
    config = apply_cli_overrides(config, args)

    # Pass both the cooked config and the original config_path so the
    # controller can use the path for hot-reload polling (Phase 4).
    main(config_path=args.config, config=config)
