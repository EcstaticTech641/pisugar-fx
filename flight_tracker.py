#!/usr/bin/env python3
"""Flight tracker application entry point."""

import argparse
import sys
import os

# Add parent directory to path so we can import flight module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flight.controller import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Flight tracking display for Raspberry Pi with WhisPlay HAT"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to flight_locations.json config file (default: config/flight_locations.json)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    
    args = parser.parse_args()
    
    # Setup debug logging if requested
    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    main(config_path=args.config)
