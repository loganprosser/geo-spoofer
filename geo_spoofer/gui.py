"""Minimal Tkinter window for spoofing an iPhone's GPS location over USB.

Network/geocoding calls run synchronously on the UI thread -- they take
under a couple seconds and this is a single-user personal tool, so the
brief freeze isn't worth adding threading for.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from geo_spoofer import core

_BG = "#0F172A"
_PANEL = "#1E293B"
_MUTED = "#272F42"
_FG = "#F8FAFC"
_SUBTLE_FG = "#94A3B8"
_BORDER = "#475569"
_ACCENT = "#22C55E"
_ACCENT_ACTIVE = "#16A34A"
_ACCENT_FG = "#0F172A"
_DANGER = "#EF4444"
_DANGER_ACTIVE = "#DC2626"
_FONT = ("SF Pro Text", 11)


def _apply_theme(root: tk.Tk) -> None:
    root.configure(bg=_BG)
    style = ttk.Style(root)
    style.theme_use("clam")  # macOS's native "aqua" theme ignores color overrides; clam respects them.

    style.configure(".", background=_BG, foreground=_FG, font=_FONT)
    style.configure("TFrame", background=_BG)
    style.configure("TLabelframe", background=_BG, foreground=_FG, bordercolor=_BORDER)
    style.configure("TLabelframe.Label", background=_BG, foreground=_FG, font=(_FONT[0], 11, "bold"))
    style.configure("TLabel", background=_BG, foreground=_FG)
    style.configure(
        "TEntry", fieldbackground=_MUTED, foreground=_FG, insertcolor=_FG, bordercolor=_BORDER,
        lightcolor=_BORDER, darkcolor=_BORDER,
    )
    style.configure("TButton", background=_PANEL, foreground=_FG, bordercolor=_BORDER, padding=6)
    style.map("TButton", background=[("active", _MUTED)])
    style.configure("Accent.TButton", background=_ACCENT, foreground=_ACCENT_FG, padding=6)
    style.map("Accent.TButton", background=[("active", _ACCENT_ACTIVE)])
    style.configure("Danger.TButton", background=_DANGER, foreground=_FG, padding=6)
    style.map("Danger.TButton", background=[("active", _DANGER_ACTIVE)])


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("geo-spoofer")
        _apply_theme(root)
        self.active_proc = None

        pad = {"padx": 8, "pady": 4}

        city_frame = ttk.LabelFrame(root, text="Set by city")
        city_frame.pack(fill="x", **pad)
        self.city_entry = ttk.Entry(city_frame, width=30)
        self.city_entry.pack(side="left", padx=6, pady=6)
        ttk.Button(city_frame, text="Set", style="Accent.TButton", command=self.on_set_city).pack(
            side="left", padx=6
        )

        coords_frame = ttk.LabelFrame(root, text="Set by coordinates")
        coords_frame.pack(fill="x", **pad)
        self.lat_entry = ttk.Entry(coords_frame, width=12)
        self.lat_entry.pack(side="left", padx=6, pady=6)
        self.lon_entry = ttk.Entry(coords_frame, width=12)
        self.lon_entry.pack(side="left", padx=6)
        ttk.Button(coords_frame, text="Pick on map...", command=self.on_pick_on_map).pack(
            side="left", padx=6
        )
        ttk.Button(coords_frame, text="Set", style="Accent.TButton", command=self.on_set_coords).pack(
            side="left", padx=6
        )

        drive_frame = ttk.LabelFrame(root, text="Drive a route (place name or lat,lon)")
        drive_frame.pack(fill="x", **pad)
        row1 = ttk.Frame(drive_frame)
        row1.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Label(row1, text="From").pack(side="left")
        self.from_entry = ttk.Entry(row1, width=26)
        self.from_entry.pack(side="left", padx=6)
        ttk.Label(row1, text="To").pack(side="left")
        self.to_entry = ttk.Entry(row1, width=26)
        self.to_entry.pack(side="left", padx=6)
        row2 = ttk.Frame(drive_frame)
        row2.pack(fill="x", padx=6, pady=6)
        ttk.Label(row2, text="Speed (km/h)").pack(side="left")
        self.speed_entry = ttk.Entry(row2, width=6)
        self.speed_entry.insert(0, "40")
        self.speed_entry.pack(side="left", padx=6)
        ttk.Button(row2, text="Drive", style="Accent.TButton", command=self.on_drive).pack(
            side="left", padx=6
        )

        ttk.Button(root, text="Stop / Restore real GPS", style="Danger.TButton", command=self.on_stop).pack(
            fill="x", **pad
        )

        self.status = tk.StringVar(value="Idle. Plug in your iPhone over USB to begin.")
        ttk.Label(root, textvariable=self.status, wraplength=380, foreground=_SUBTLE_FG).pack(
            fill="x", padx=8, pady=(0, 8)
        )

    def set_status(self, text: str) -> None:
        self.status.set(text)
        self.root.update_idletasks()

    def _replace_active_proc(self, proc) -> None:
        if self.active_proc is not None:
            self.active_proc.terminate()
            self.active_proc.wait()
        self.active_proc = proc

    def _run_action(self, description: str, action) -> None:
        self.set_status(f"{description}...")
        try:
            action()
        except core.GeoSpooferError as e:
            self.set_status(f"Error: {e}")

    def on_set_city(self) -> None:
        city = self.city_entry.get().strip()
        if not city:
            return

        def action():
            lat, lon = core.geocode(city)
            self._replace_active_proc(core.start_location(lat, lon))
            self.set_status(f"Location fixed at {city!r} ({lat:.5f}, {lon:.5f}).")

        self._run_action(f"Looking up {city!r}", action)

    def on_pick_on_map(self) -> None:
        self.set_status("Opening map picker...")
        point = core.pick_on_map()
        if point is None:
            self.set_status("Map picker cancelled.")
            return
        lat, lon = point
        self.lat_entry.delete(0, tk.END)
        self.lat_entry.insert(0, f"{lat:.6f}")
        self.lon_entry.delete(0, tk.END)
        self.lon_entry.insert(0, f"{lon:.6f}")
        self.set_status(f"Picked ({lat:.6f}, {lon:.6f}). Click Set to fix the location.")

    def on_set_coords(self) -> None:
        try:
            lat, lon = float(self.lat_entry.get()), float(self.lon_entry.get())
        except ValueError:
            self.set_status("Enter numeric latitude and longitude.")
            return

        def action():
            self._replace_active_proc(core.start_location(lat, lon))
            self.set_status(f"Location fixed at ({lat}, {lon}).")

        self._run_action("Setting location", action)

    def on_drive(self) -> None:
        start, end = self.from_entry.get().strip(), self.to_entry.get().strip()
        if not start or not end:
            return
        try:
            speed = float(self.speed_entry.get())
        except ValueError:
            self.set_status("Enter a numeric speed.")
            return

        def action():
            self._replace_active_proc(core.start_drive(start, end, speed))
            self.set_status(f"Driving from {start!r} to {end!r} at {speed} km/h.")

        self._run_action(f"Routing {start!r} -> {end!r}", action)

    def on_stop(self) -> None:
        def action():
            if self.active_proc is not None:
                self.active_proc.terminate()
                self.active_proc.wait()
                self.active_proc = None
            core.clear_location()
            self.set_status("Stopped. Real GPS restored.")

        self._run_action("Stopping", action)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
