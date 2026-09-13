"""Minimal Tkinter window for spoofing an iPhone's GPS location over USB.

Network/geocoding calls run synchronously on the UI thread -- they take
under a couple seconds and this is a single-user personal tool, so the
brief freeze isn't worth adding threading for.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from geo_spoofer import core


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("geo-spoofer")
        self.active_proc = None

        pad = {"padx": 8, "pady": 4}

        city_frame = ttk.LabelFrame(root, text="Set by city")
        city_frame.pack(fill="x", **pad)
        self.city_entry = ttk.Entry(city_frame, width=30)
        self.city_entry.pack(side="left", padx=6, pady=6)
        ttk.Button(city_frame, text="Set", command=self.on_set_city).pack(side="left", padx=6)

        coords_frame = ttk.LabelFrame(root, text="Set by coordinates")
        coords_frame.pack(fill="x", **pad)
        self.lat_entry = ttk.Entry(coords_frame, width=12)
        self.lat_entry.pack(side="left", padx=6, pady=6)
        self.lon_entry = ttk.Entry(coords_frame, width=12)
        self.lon_entry.pack(side="left", padx=6)
        ttk.Button(coords_frame, text="Set", command=self.on_set_coords).pack(side="left", padx=6)

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
        ttk.Button(row2, text="Drive", command=self.on_drive).pack(side="left", padx=6)

        ttk.Button(root, text="Stop / Restore real GPS", command=self.on_stop).pack(fill="x", **pad)

        self.status = tk.StringVar(value="Idle. Plug in your iPhone over USB to begin.")
        ttk.Label(root, textvariable=self.status, wraplength=380, foreground="gray20").pack(
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
