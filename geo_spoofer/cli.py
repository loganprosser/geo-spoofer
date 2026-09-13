"""CLI for spoofing an iPhone's GPS location over USB.

    geo-spoofer set-city "San Francisco"
    geo-spoofer set-coords 37.7749 -122.4194
    geo-spoofer drive --from "Golden Gate Bridge" --to "Fisherman's Wharf" --speed 30
    geo-spoofer clear
"""
from __future__ import annotations

import argparse
import sys

from geo_spoofer import core


def _hold_until_interrupted(proc, label: str) -> None:
    print(f"{label} Press Ctrl+C to stop and restore real GPS.")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        print("\nStopped, real GPS restored.")


def cmd_set_city(args: argparse.Namespace) -> None:
    lat, lon = core.geocode(args.city)
    proc = core.start_location(lat, lon)
    _hold_until_interrupted(proc, f"Location fixed at {args.city!r} ({lat:.5f}, {lon:.5f}).")


def cmd_set_coords(args: argparse.Namespace) -> None:
    proc = core.start_location(args.lat, args.lon)
    _hold_until_interrupted(proc, f"Location fixed at ({args.lat}, {args.lon}).")


def cmd_drive(args: argparse.Namespace) -> None:
    proc = core.start_drive(args.start, args.end, args.speed)
    _hold_until_interrupted(proc, f"Driving from {args.start!r} to {args.end!r} at {args.speed} km/h.")


def cmd_clear(args: argparse.Namespace) -> None:
    core.clear_location()
    print("Real GPS restored.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="geo-spoofer")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("set-city", help="Fix the phone's location to a named place")
    p.add_argument("city")
    p.set_defaults(func=cmd_set_city)

    p = sub.add_parser("set-coords", help="Fix the phone's location to lat/lon")
    p.add_argument("lat", type=float)
    p.add_argument("lon", type=float)
    p.set_defaults(func=cmd_set_coords)

    p = sub.add_parser("drive", help="Drive a road route between two places/coords")
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", required=True)
    p.add_argument("--speed", type=float, default=40.0, help="km/h, default 40")
    p.set_defaults(func=cmd_drive)

    p = sub.add_parser("clear", help="Restore the phone's real GPS")
    p.set_defaults(func=cmd_clear)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except core.GeoSpooferError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
