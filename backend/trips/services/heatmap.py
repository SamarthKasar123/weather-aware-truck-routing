"""Weather heatmap frames (0-48 h) on a grid covering the trip corridor.

Grid rows are spaced evenly in Web-Mercator Y (not latitude) so the frontend
can stretch the grid as a single image over the map without distortion.
Only cells within `buffer` miles of a route are populated; the rest are
transparent, which keeps the request size small and the overlay on-corridor.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from . import geo, risk, weather
from .geo import LatLon

HOURS = 48
MAX_GRID_SIDE = 48  # cells along the longest bbox side
MIN_CELL_DEG = 0.1  # don't go finer than the forecast models resolve
MAX_ACTIVE_CELLS = 280  # each cell is one Open-Meteo "call" on the free tier
MIN_BUFFER_MI = 30.0


def _grid(lines: list[list[LatLon]], cell_deg: float) -> dict:
    pts = [p for line in lines for p in line]
    mid_lat = sum(p[0] for p in pts) / len(pts)
    cell_mi_mid = cell_deg * 69.0 * math.cos(math.radians(mid_lat))
    buffer_mi = max(MIN_BUFFER_MI, cell_mi_mid)
    pad_deg = buffer_mi / 69.0 + cell_deg

    west = min(p[1] for p in pts) - pad_deg / math.cos(math.radians(mid_lat))
    east = max(p[1] for p in pts) + pad_deg / math.cos(math.radians(mid_lat))
    south = min(p[0] for p in pts) - pad_deg
    north = max(p[0] for p in pts) + pad_deg

    cols = max(2, math.ceil((east - west) / cell_deg))
    east = west + cols * cell_deg
    y_n, y_s = geo.mercator_y(north), geo.mercator_y(south)
    cell_y = math.radians(cell_deg)  # Mercator Y uses radians, so cells are ~square on screen
    rows = max(2, math.ceil((y_n - y_s) / cell_y))
    y_s = y_n - rows * cell_y
    south = geo.inverse_mercator_y(y_s)

    def center(r: int, c: int) -> LatLon:
        return geo.inverse_mercator_y(y_n - (r + 0.5) * cell_y), west + (c + 0.5) * cell_deg

    # Mark cells within buffer of any route point. Lines are densified to half a
    # cell so no cell along the path is skipped.
    active: set[int] = set()
    for line in lines:
        for lat, lon in geo.resample(line, max(1.0, cell_mi_mid / 2)):
            r0 = int((y_n - geo.mercator_y(lat)) / cell_y)
            c0 = int((lon - west) / cell_deg)
            cell_mi = max(1e-6, cell_deg * 69.0 * math.cos(math.radians(lat)))
            k = math.ceil(buffer_mi / cell_mi) + 1
            for r in range(max(0, r0 - k), min(rows, r0 + k + 1)):
                for c in range(max(0, c0 - k), min(cols, c0 + k + 1)):
                    idx = r * cols + c
                    if idx not in active and geo.haversine_mi((lat, lon), center(r, c)) <= buffer_mi:
                        active.add(idx)

    cells = sorted(active)
    return {
        "bounds": [[south, west], [north, east]],
        "rows": rows,
        "cols": cols,
        "cells": cells,
        "centers": [center(i // cols, i % cols) for i in cells],
    }


def build_heatmap(lines: list[list[LatLon]], start: datetime, load_lb: float) -> dict:
    pts = [p for line in lines for p in line]
    lat_span = max(p[0] for p in pts) - min(p[0] for p in pts)
    lon_span = max(p[1] for p in pts) - min(p[1] for p in pts)
    cell_deg = max(MIN_CELL_DEG, max(lat_span, lon_span) / MAX_GRID_SIDE)
    grid = _grid(lines, cell_deg)
    while len(grid["cells"]) > MAX_ACTIVE_CELLS:
        cell_deg *= 1.2
        grid = _grid(lines, cell_deg)

    times = [start + timedelta(hours=h) for h in range(HOURS + 1)]
    series, _ = weather.fetch_hourly(grid["centers"], times[0], times[-1], max_points=MAX_ACTIVE_CELLS)

    frames: dict[str, list[list[float]]] = {"risk": [], "wind": [], "rain": [], "snow": []}
    for t in times:
        risk_f, wind_f, rain_f, snow_f = [], [], [], []
        for s in series:
            smp = weather.sample(s, t)
            level = risk.assess(smp.wind_mph, smp.rain_in_hr, smp.snow_in_hr, load_lb).level
            risk_f.append(int(level))
            wind_f.append(round(smp.wind_mph, 1))
            rain_f.append(round(smp.rain_in_hr, 3))
            snow_f.append(round(smp.snow_in_hr, 3))
        frames["risk"].append(risk_f)
        frames["wind"].append(wind_f)
        frames["rain"].append(rain_f)
        frames["snow"].append(snow_f)

    (south, west), (north, east) = grid["bounds"]
    return {
        "start": start.isoformat(),
        "hours": HOURS,
        "bounds": [[round(south, 5), round(west, 5)], [round(north, 5), round(east, 5)]],
        "rows": grid["rows"],
        "cols": grid["cols"],
        "cells": grid["cells"],
        "frames": frames,
    }
