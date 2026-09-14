"""Map-first GUI for spoofing an iPhone's GPS location over USB.

A single pywebview window (Leaflet map + a floating control panel) replaces
the old Tkinter forms + separate map-picker subprocess. JS calls into the
`Api` methods below via pywebview's js_api bridge; each call runs on its own
background thread (pywebview's doing, not ours), so the network calls here
don't freeze the map.
"""
from __future__ import annotations

import threading

import webview

from geo_spoofer import core

_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>geo-spoofer</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap">
<style>
  :root {
    --color-primary: #1E293B;
    --color-on-primary: #F8FAFC;
    --color-accent: #22C55E;
    --color-on-accent: #0F172A;
    --color-background: #0F172A;
    --color-muted: #272F42;
    --color-border: #475569;
    --color-subtle: #94A3B8;
    --color-destructive: #EF4444;
  }
  html, body, #map { height: 100%; margin: 0; }
  body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--color-background); }

  .pin {
    width: 18px; height: 18px; border-radius: 50%;
    border: 2px solid var(--color-on-accent);
    transform: scale(0.6);
    transition: transform 200ms ease-out;
  }
  .pin.dropped { transform: scale(1); }
  .pin.current { background: var(--color-subtle); box-shadow: 0 0 12px 2px rgba(148, 163, 184, 0.7); }
  .pin.spoofed { background: var(--color-accent); box-shadow: 0 0 12px 2px rgba(34, 197, 94, 0.8); }
  .pin.preview { background: var(--color-accent); opacity: 0.55; }
  @media (prefers-reduced-motion: reduce) {
    .pin { transition: none; }
  }

  .panel {
    position: fixed;
    top: 16px;
    left: 16px;
    width: 320px;
    background: var(--color-primary);
    color: var(--color-on-primary);
    border: 1px solid var(--color-border);
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 1000;
    font-size: 13px;
  }
  .panel h1 { font-size: 15px; font-weight: 600; margin: 0 0 12px; }
  .section { margin-bottom: 14px; }
  .section label { display: block; color: var(--color-subtle); font-size: 12px; margin-bottom: 6px; }
  .row { display: flex; gap: 6px; margin-bottom: 6px; }

  input {
    font-family: inherit;
    font-size: 13px;
    background: var(--color-muted);
    color: var(--color-on-primary);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 7px 10px;
    min-width: 0;
    flex: 1;
  }
  input:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 1px; }
  input.speed { flex: none; width: 52px; }
  .unit { align-self: center; color: var(--color-subtle); font-size: 12px; }

  button {
    font-family: inherit;
    font-size: 13px;
    font-weight: 500;
    border-radius: 8px;
    padding: 7px 14px;
    border: 1px solid transparent;
    cursor: pointer;
    transition: background-color 150ms ease, opacity 150ms ease;
  }
  button:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
  button:disabled { opacity: 0.5; cursor: default; }

  .btn-confirm { background: var(--color-accent); color: var(--color-on-accent); flex: none; }
  .btn-confirm:hover:not(:disabled) { background: #16A34A; }

  .btn-cancel {
    background: transparent; color: var(--color-on-primary); border-color: var(--color-border);
    width: 100%; margin-top: 4px;
  }
  .btn-cancel:hover:not(:disabled) { background: var(--color-muted); }

  .status { margin-top: 12px; color: var(--color-subtle); font-size: 12px; line-height: 1.4; }

  .legend { display: flex; gap: 14px; margin-top: 10px; font-size: 11px; color: var(--color-subtle); }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .legend .dot { width: 9px; height: 9px; border-radius: 50%; }
  .legend .dot.current { background: var(--color-subtle); }
  .legend .dot.spoofed { background: var(--color-accent); }

  .top-hint {
    position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
    background: var(--color-primary); color: var(--color-subtle);
    border: 1px solid var(--color-border); border-radius: 8px;
    padding: 6px 14px; font-size: 12px; z-index: 1000;
  }
</style>
</head>
<body>
  <div id="map"></div>
  <div class="top-hint">Click the map to fill the last-focused field</div>

  <div class="panel">
    <h1>geo-spoofer</h1>

    <div class="section">
      <label>Teleport to</label>
      <div class="row">
        <input id="teleportInput" placeholder="Place name, lat,lon, or click the map">
        <button id="teleportBtn" class="btn-confirm">Set</button>
      </div>
    </div>

    <div class="section">
      <label>Drive a route</label>
      <div class="row">
        <input id="fromInput" placeholder="From (blank = current location)">
      </div>
      <div class="row">
        <input id="toInput" placeholder="To">
        <input id="speedInput" class="speed" type="number" value="40" min="1">
        <span class="unit">km/h</span>
      </div>
      <button id="driveBtn" class="btn-confirm" style="width: 100%;">Drive</button>
    </div>

    <button id="stopBtn" class="btn-cancel">Stop / Restore real GPS</button>

    <div class="status" id="status">Idle. Plug in your iPhone over USB to begin.</div>

    <div class="legend">
      <span><span class="dot current"></span> You (approx.)</span>
      <span><span class="dot spoofed"></span> Spoofed to</span>
    </div>
  </div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map', { worldCopyJump: true }).setView([20, 0], 2);
  // CARTO's free dark tiles now require signing up for an API key (as of
  // 2026); Esri's dark-gray canvas is still free and keyless, so we stack
  // its base + label layers instead.
  const attribution = '&copy; OpenStreetMap contributors &copy; Esri';
  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    { attribution, maxZoom: 16 }
  ).addTo(map);
  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 16 }
  ).addTo(map);

  function pinIcon(cls) {
    return L.divIcon({ className: '', html: `<div class="pin ${cls} dropped"></div>`, iconSize: [18, 18] });
  }

  let currentMarker = null, currentLoc = null;
  let spoofedMarker = null, routeLine = null;

  const status = document.getElementById('status');
  function setStatus(text) { status.textContent = text; }

  function setSpoofedMarker(lat, lon) {
    if (spoofedMarker) spoofedMarker.setLatLng([lat, lon]);
    else spoofedMarker = L.marker([lat, lon], { icon: pinIcon('spoofed') }).addTo(map);
  }

  function clearRoute() {
    if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
  }

  // Fill whichever text field was last focused -- lets map clicks feed
  // "Teleport to", "From", or "To" depending on what you're editing.
  let lastFocused = 'teleportInput';
  for (const id of ['teleportInput', 'fromInput', 'toInput']) {
    document.getElementById(id).addEventListener('focus', () => { lastFocused = id; });
  }

  map.on('click', (e) => {
    const { lat, lng } = e.latlng;
    document.getElementById(lastFocused).value = `${lat.toFixed(6)},${lng.toFixed(6)}`;
  });

  function whenApiReady(fn) {
    if (window.pywebview && window.pywebview.api) fn();
    else window.addEventListener('pywebviewready', fn, { once: true });
  }

  function withButton(btn, label, fn) {
    btn.disabled = true;
    setStatus(label);
    fn().finally(() => { btn.disabled = false; });
  }

  document.getElementById('teleportBtn').addEventListener('click', () => {
    const text = document.getElementById('teleportInput').value.trim();
    if (!text) return;
    const btn = document.getElementById('teleportBtn');
    withButton(btn, `Setting location to ${text}...`, () =>
      pywebview.api.teleport(text)
        .then(({ lat, lon }) => {
          setSpoofedMarker(lat, lon);
          clearRoute();
          map.setView([lat, lon], 13);
          setStatus(`Location fixed at (${lat.toFixed(5)}, ${lon.toFixed(5)}).`);
        })
        .catch((err) => setStatus(`Error: ${err.message}`))
    );
  });

  document.getElementById('driveBtn').addEventListener('click', () => {
    const from = document.getElementById('fromInput').value.trim()
      || (currentLoc ? `${currentLoc[0]},${currentLoc[1]}` : '');
    const to = document.getElementById('toInput').value.trim();
    const speed = document.getElementById('speedInput').value.trim();
    if (!from || !to) { setStatus('Enter a "To" destination (and a "From", unless your current location was found).'); return; }
    const btn = document.getElementById('driveBtn');
    withButton(btn, `Routing ${from} -> ${to}...`, () =>
      pywebview.api.drive(from, to, speed)
        .then(({ points }) => {
          clearRoute();
          routeLine = L.polyline(points, { color: '#22C55E', weight: 4, opacity: 0.85 }).addTo(map);
          const [endLat, endLon] = points[points.length - 1];
          setSpoofedMarker(endLat, endLon);
          map.fitBounds(routeLine.getBounds(), { padding: [40, 40] });
          setStatus(`Driving from ${from} to ${to} at ${speed} km/h.`);
        })
        .catch((err) => setStatus(`Error: ${err.message}`))
    );
  });

  document.getElementById('stopBtn').addEventListener('click', () => {
    const btn = document.getElementById('stopBtn');
    withButton(btn, 'Stopping...', () =>
      pywebview.api.stop()
        .then(() => {
          if (spoofedMarker) { map.removeLayer(spoofedMarker); spoofedMarker = null; }
          clearRoute();
          setStatus('Stopped. Real GPS restored.');
        })
        .catch((err) => setStatus(`Error: ${err.message}`))
    );
  });

  whenApiReady(() => {
    setStatus('Locating you (approx., via IP)...');
    pywebview.api.get_current_location().then((loc) => {
      if (!loc) { setStatus('Idle. Plug in your iPhone over USB to begin.'); return; }
      currentLoc = [loc.lat, loc.lon];
      currentMarker = L.marker(currentLoc, { icon: pinIcon('current') }).addTo(map);
      map.setView(currentLoc, 11);
      setStatus('Idle. Plug in your iPhone over USB to begin.');
    });
  });
</script>
</body>
</html>
"""


class Api:
    def __init__(self) -> None:
        self.active_proc = None
        self._lock = threading.Lock()

    def _replace_active_proc(self, proc) -> None:
        with self._lock:
            if self.active_proc is not None:
                self.active_proc.terminate()
                self.active_proc.wait()
            self.active_proc = proc

    def get_current_location(self) -> dict | None:
        point = core.current_location()
        if point is None:
            return None
        lat, lon = point
        return {"lat": lat, "lon": lon}

    def teleport(self, text: str) -> dict:
        text = text.strip()
        if not text:
            raise core.GeoSpooferError("enter a place name, coordinates, or click the map")
        lat, lon = core.resolve_point(text)
        self._replace_active_proc(core.start_location(lat, lon))
        return {"lat": lat, "lon": lon}

    def drive(self, start_text: str, end_text: str, speed: str) -> dict:
        start_text, end_text = start_text.strip(), end_text.strip()
        if not start_text or not end_text:
            raise core.GeoSpooferError("enter both a start and an end")
        try:
            speed_kmh = float(speed)
        except ValueError:
            raise core.GeoSpooferError("enter a numeric speed")
        proc, points = core.start_drive(start_text, end_text, speed_kmh)
        self._replace_active_proc(proc)
        return {"points": [[lat, lon] for lat, lon in points]}

    def stop(self) -> dict:
        with self._lock:
            if self.active_proc is not None:
                self.active_proc.terminate()
                self.active_proc.wait()
                self.active_proc = None
        core.clear_location()
        return {}


def main() -> None:
    webview.create_window(
        "geo-spoofer", html=_HTML, js_api=Api(), width=1100, height=750, min_size=(700, 500)
    )
    webview.start()


if __name__ == "__main__":
    main()
