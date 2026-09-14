"""Spoofs an iPhone's GPS location over USB.

Wraps pymobiledevice3's DVT ``simulate-location`` service (the same mechanism
Xcode's "Debug > Simulate Location" uses), and adds city search + road
routing on top. Requires the phone plugged into this Mac over USB, in
Developer Mode, with "Trust This Computer" already accepted.

The simulated location only holds while a process keeps the DVT connection
open -- same as Xcode. That's why `set_location`/`start_drive` return the
running `Popen` instead of blocking: the caller decides how long to hold it
(foreground wait + Ctrl-C for the CLI, a Stop button for the GUI).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import gpxpy.gpx

USER_AGENT = "geo-spoofer/0.1 (personal use, USB-only)"
_EARTH_RADIUS_M = 6_371_000


class GeoSpooferError(RuntimeError):
    pass


def _pymobiledevice3_path() -> str:
    """Resolve the CLI next to the current interpreter first, so this works
    whether or not the venv is "activated" in the calling shell (e.g. when
    the GUI is launched by double-clicking rather than from a shell)."""
    sibling = Path(sys.executable).parent / "pymobiledevice3"
    if sibling.exists():
        return str(sibling)
    found = shutil.which("pymobiledevice3")
    if found:
        return found
    raise GeoSpooferError("pymobiledevice3 not found (expected it installed alongside this Python)")


def _cmd(*args: str) -> list[str]:
    return [_pymobiledevice3_path(), "developer", "dvt", "simulate-location", *args]


def _run(*args: str) -> None:
    result = subprocess.run(_cmd(*args), capture_output=True, text=True)
    if result.returncode != 0:
        raise GeoSpooferError(result.stderr.strip() or result.stdout.strip() or "pymobiledevice3 failed")


def start_location(lat: float, lon: float) -> subprocess.Popen:
    """Start simulating `lat, lon`. Keep the returned process alive for as
    long as the phone should report this location; terminate it to restore
    real GPS."""
    return subprocess.Popen(_cmd("set", "--", str(lat), str(lon)))


def clear_location() -> None:
    """Stop any simulation and restore the phone's real GPS."""
    _run("clear")


def current_location() -> tuple[float, float] | None:
    """Best-effort approximation of where you actually are, via free IP
    geolocation (no device GPS readback exists -- pymobiledevice3 can only
    set the simulated location, never read the real one back). City-level
    accuracy at best. Returns None if the lookup fails."""
    request = urllib.request.Request("https://ipapi.co/json/", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
        return float(data["latitude"]), float(data["longitude"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def geocode(place: str) -> tuple[float, float]:
    """Place name -> (lat, lon) via OpenStreetMap Nominatim."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": place, "format": "json", "limit": 1}
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        results = json.load(response)
    if not results:
        raise GeoSpooferError(f"couldn't find a location for {place!r}")
    return float(results[0]["lat"]), float(results[0]["lon"])


def resolve_point(text: str) -> tuple[float, float]:
    """Accepts either "lat,lon" or a place name to geocode."""
    text = text.strip()
    parts = text.split(",")
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return geocode(text)


def osrm_route(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    """Road-following point list between two (lat, lon) points, via the
    public OSRM routing server."""
    (lat1, lon1), (lat2, lon2) = start, end
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise GeoSpooferError(f"no road route found: {data.get('message', 'unknown error')}")
    return [(lat, lon) for lon, lat in data["routes"][0]["geometry"]["coordinates"]]


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = radians(a[0]), radians(a[1]), radians(b[0]), radians(b[1])
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * asin(sqrt(h))


def route_to_gpx(points: list[tuple[float, float]], speed_kmh: float) -> str:
    """Turns a point list into a timestamped GPX track XML string, paced at
    `speed_kmh`. pymobiledevice3's own player paces movement using the gap
    between consecutive timestamps, so that spacing is what controls
    playback speed."""
    if speed_kmh <= 0:
        raise GeoSpooferError("speed must be > 0 km/h")
    if len(points) < 2:
        raise GeoSpooferError("route needs at least two points")
    speed_m_s = speed_kmh * 1000 / 3600

    gpx = gpxpy.gpx.GPX()
    track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    t = datetime.now(timezone.utc)
    segment.points.append(gpxpy.gpx.GPXTrackPoint(points[0][0], points[0][1], time=t))
    for prev, cur in zip(points, points[1:]):
        t += timedelta(seconds=haversine_m(prev, cur) / speed_m_s)
        segment.points.append(gpxpy.gpx.GPXTrackPoint(cur[0], cur[1], time=t))

    return gpx.to_xml()


def start_drive(
    start_text: str, end_text: str, speed_kmh: float = 40.0
) -> tuple[subprocess.Popen, list[tuple[float, float]]]:
    """Looks up a road route between two places/coords and starts driving it.
    Keep the returned process alive for the drive; terminate it to stop
    early and restore real GPS. Also returns the route's points so callers
    (e.g. the map view) can draw it without re-fetching."""
    start, end = resolve_point(start_text), resolve_point(end_text)
    points = osrm_route(start, end)
    gpx_xml = route_to_gpx(points, speed_kmh)

    fd, path = tempfile.mkstemp(suffix=".gpx", prefix="geo-spoofer-")
    os.close(fd)
    Path(path).write_text(gpx_xml)
    return subprocess.Popen(_cmd("play", path)), points
