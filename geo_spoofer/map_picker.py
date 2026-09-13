"""Standalone interactive-map location picker.

Launched as a subprocess (`python3 -m geo_spoofer.map_picker`) rather than
imported directly: on macOS the native webview must own the process's main
thread, which the Tkinter GUI's mainloop already occupies. Prints
"lat,lon" to stdout and exits 0 if the user confirms a point, exits
nonzero if they cancel/close the window.
"""
from __future__ import annotations

import sys

import webview

_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pick a location</title>
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
    --color-destructive: #EF4444;
  }
  html, body, #map { height: 100%; margin: 0; }
  body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--color-background); }

  .pin {
    width: 18px; height: 18px; border-radius: 50%;
    background: var(--color-accent);
    border: 2px solid var(--color-on-accent);
    box-shadow: 0 0 12px 2px rgba(34, 197, 94, 0.8);
    transform: scale(0.6);
    transition: transform 200ms ease-out;
  }
  .pin.dropped { transform: scale(1); }
  @media (prefers-reduced-motion: reduce) {
    .pin { transition: none; }
  }

  .panel {
    position: fixed;
    left: 50%;
    bottom: 24px;
    transform: translateX(-50%);
    background: var(--color-primary);
    color: var(--color-on-primary);
    border: 1px solid var(--color-border);
    border-radius: 12px;
    padding: 14px 18px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    display: none;
    align-items: center;
    gap: 16px;
    z-index: 1000;
    font-size: 14px;
  }
  .panel.visible { display: flex; }
  .panel .coords { font-family: 'SF Mono', Menlo, monospace; color: var(--color-on-primary); min-width: 220px; }
  .panel .hint { color: #94A3B8; font-size: 12px; }

  button {
    font-family: inherit;
    font-size: 14px;
    font-weight: 500;
    border-radius: 8px;
    padding: 8px 16px;
    min-height: 36px;
    border: 1px solid transparent;
    cursor: pointer;
    transition: background-color 150ms ease, opacity 150ms ease;
  }
  button:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }

  .btn-confirm { background: var(--color-accent); color: var(--color-on-accent); }
  .btn-confirm:hover { background: #16A34A; }
  .btn-confirm:disabled { opacity: 0.4; cursor: default; }

  .btn-cancel { background: transparent; color: var(--color-on-primary); border-color: var(--color-border); }
  .btn-cancel:hover { background: var(--color-muted); }

  .top-hint {
    position: fixed; top: 16px; left: 50%; transform: translateX(-50%);
    background: var(--color-primary); color: #94A3B8;
    border: 1px solid var(--color-border); border-radius: 8px;
    padding: 6px 14px; font-size: 13px; z-index: 1000;
  }
</style>
</head>
<body>
  <div id="map"></div>
  <div class="top-hint">Click anywhere on the map to drop a pin</div>
  <div class="panel" id="panel">
    <div>
      <div class="coords" id="coords">--</div>
      <div class="hint">Confirm to use this point</div>
    </div>
    <button class="btn-cancel" id="cancelBtn">Cancel</button>
    <button class="btn-confirm" id="confirmBtn" disabled>Use this location</button>
  </div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map', { worldCopyJump: true }).setView([20, 0], 2);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);

  const pinIcon = L.divIcon({ className: '', html: '<div class="pin" id="pinEl"></div>', iconSize: [18, 18] });
  let marker = null;

  function showPanel(lat, lng) {
    document.getElementById('coords').textContent =
      `Lat ${lat.toFixed(6)}  Lon ${lng.toFixed(6)}`;
    document.getElementById('panel').classList.add('visible');
    document.getElementById('confirmBtn').disabled = false;
  }

  map.on('click', (e) => {
    const { lat, lng } = e.latlng;
    if (marker) {
      marker.setLatLng(e.latlng);
    } else {
      marker = L.marker(e.latlng, { icon: pinIcon }).addTo(map);
    }
    requestAnimationFrame(() => {
      const el = document.getElementById('pinEl');
      if (el) el.classList.add('dropped');
    });
    showPanel(lat, lng);
  });

  function whenApiReady(fn) {
    if (window.pywebview && window.pywebview.api) fn();
    else window.addEventListener('pywebviewready', fn, { once: true });
  }

  document.getElementById('confirmBtn').addEventListener('click', () => {
    if (!marker) return;
    const { lat, lng } = marker.getLatLng();
    whenApiReady(() => window.pywebview.api.confirm(lat, lng));
  });

  document.getElementById('cancelBtn').addEventListener('click', () => {
    whenApiReady(() => window.pywebview.api.cancel());
  });
</script>
</body>
</html>
"""


class _Api:
    def __init__(self) -> None:
        self.result: tuple[float, float] | None = None

    def confirm(self, lat: float, lon: float) -> None:
        self.result = (float(lat), float(lon))
        webview.windows[0].destroy()

    def cancel(self) -> None:
        webview.windows[0].destroy()


def main() -> int:
    api = _Api()
    webview.create_window(
        "Pick a location", html=_HTML, js_api=api, width=960, height=640, min_size=(600, 420)
    )
    webview.start()
    if api.result is None:
        return 1
    lat, lon = api.result
    print(f"{lat},{lon}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
