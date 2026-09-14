# geo-spoofer

Spoof an iPhone's GPS location over USB, from a Mac. Uses the same
mechanism as Xcode's "Debug > Simulate Location" (a DVT service on the
phone), wrapped by [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) —
no Xcode project, no jailbreak.

The phone must stay plugged into this Mac over USB for the whole time you
want the fake location to hold — same as Xcode, disconnecting reverts to
real GPS.

## One-time setup on the phone

1. iOS 16+: enable **Developer Mode** — Settings > Privacy & Security >
   Developer Mode, then reboot when prompted.
2. Plug in over USB and tap **Trust This Computer** if asked.

Only tested against iOS 17+ (uses the DVT-based `simulate-location`
command). Older iOS uses a different pymobiledevice3 subcommand
(`developer simulate-location`, no `dvt`) — not wired up here.

## Setup

```
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## CLI

```
venv/bin/python3 -m geo_spoofer.cli set-city "San Francisco"
venv/bin/python3 -m geo_spoofer.cli set-coords 37.7749 -122.4194
venv/bin/python3 -m geo_spoofer.cli drive --from "Golden Gate Bridge" --to "Fisherman's Wharf" --speed 30
venv/bin/python3 -m geo_spoofer.cli clear
```

`set-city`, `set-coords`, and `drive` run in the foreground — Ctrl+C stops
and restores real GPS.

## GUI

```
venv/bin/python3 -m geo_spoofer.gui
```

A full-window map (dark, via free OSM/CARTO tiles). A floating panel lets
you teleport to a place name/coordinates, or drive a road route between a
"From" and "To" (free OSRM routing) — click the map to fill whichever field
you last focused, like dropping a pin. Your approximate real location (free
IP geolocation, city-level accuracy — there's no way to read the phone's
actual GPS back) shows as a gray pin alongside the green "spoofed to" pin,
so you can see the offset. "Stop / Restore real GPS" cancels whichever is
active.

No API keys, no billing accounts, no signup — every lookup (geocoding,
routing, map tiles, approximate current location) uses a free, keyless
service.

## Tests

```
venv/bin/python3 test_core.py
```

Covers the logic that doesn't need a phone (coordinate parsing, GPX
timing/pacing math). The actual USB/device calls need a real iPhone plugged
in to verify.

## License

MIT — see [LICENSE](LICENSE).
