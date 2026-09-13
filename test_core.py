"""Self-check for the logic that doesn't need a phone or network: coordinate
parsing and GPX timing. Run with: .venv/bin/python3 test_core.py
"""
import gpxpy

from geo_spoofer import core


def test_resolve_point_parses_raw_coords():
    assert core.resolve_point("37.7749,-122.4194") == (37.7749, -122.4194)


def test_haversine_known_distance():
    # San Francisco -> Los Angeles is ~559 km as the crow flies.
    sf, la = (37.7749, -122.4194), (34.0522, -118.2437)
    km = core.haversine_m(sf, la) / 1000
    assert 545 < km < 575


def test_route_to_gpx_paces_by_speed():
    points = [(0.0, 0.0), (0.0, 0.1), (0.0, 0.2)]  # ~11.1 km between each, at the equator
    xml = core.route_to_gpx(points, speed_kmh=111.19)  # -> ~360s (6 min) per leg
    gpx = gpxpy.parse(xml)
    times = [pt.time for pt in gpx.tracks[0].segments[0].points]
    assert len(times) == 3
    leg_seconds = (times[1] - times[0]).total_seconds()
    assert 340 < leg_seconds < 380


def test_route_to_gpx_rejects_bad_input():
    for bad_args in [([(0, 0)], 40), ([(0, 0), (0, 1)], 0)]:
        try:
            core.route_to_gpx(*bad_args)
        except core.GeoSpooferError:
            continue
        raise AssertionError(f"expected GeoSpooferError for {bad_args}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
