"""Pure geometry helpers. Coordinates are (lat, lon) tuples in degrees."""
from __future__ import annotations

import math
from bisect import bisect_left
from typing import Sequence

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def cumulative_miles(coords: Sequence[LatLon]) -> list[float]:
    out = [0.0]
    for i in range(1, len(coords)):
        out.append(out[-1] + haversine_mi(coords[i - 1], coords[i]))
    return out


def interpolate_along(
    coords: Sequence[LatLon], cum: Sequence[float], target: float
) -> tuple[LatLon, int, float]:
    """Point at distance `target` along the line.

    Returns (point, segment_index, fraction_within_segment).
    """
    if target <= 0:
        return coords[0], 0, 0.0
    if target >= cum[-1]:
        return coords[-1], len(coords) - 2, 1.0
    i = max(1, bisect_left(cum, target))
    seg_len = cum[i] - cum[i - 1]
    f = 0.0 if seg_len == 0 else (target - cum[i - 1]) / seg_len
    a, b = coords[i - 1], coords[i]
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), i - 1, f


def slice_line(
    coords: Sequence[LatLon], cum: Sequence[float], start: float, end: float
) -> list[LatLon]:
    """Sub-line between two distances along the line (inclusive endpoints)."""
    p0, i0, _ = interpolate_along(coords, cum, start)
    p1, i1, _ = interpolate_along(coords, cum, end)
    return [p0, *coords[i0 + 1 : i1 + 1], p1]


def simplify_indices(coords: Sequence[LatLon], tolerance_deg: float) -> list[int]:
    """Iterative Ramer-Douglas-Peucker (planar, in degrees).

    Returns indices of the vertices to keep (always including both endpoints),
    so callers can carry per-vertex attributes such as timestamps along.
    """
    n = len(coords)
    if n < 3:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_deg * tolerance_deg
    while stack:
        s, e = stack.pop()
        ax, ay = coords[s][1], coords[s][0]
        bx, by = coords[e][1], coords[e][0]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best_i, best_d = -1, tol2
        for i in range(s + 1, e):
            px, py = coords[i][1], coords[i][0]
            if seg2 == 0:
                d = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > best_d:
                best_i, best_d = i, d
        if best_i != -1:
            keep[best_i] = True
            stack.append((s, best_i))
            stack.append((best_i, e))
    return [i for i, k in enumerate(keep) if k]


def resample(coords: Sequence[LatLon], step_mi: float) -> list[LatLon]:
    """Points evenly spaced every `step_mi` along the line (plus the end point)."""
    cum = cumulative_miles(coords)
    total = cum[-1]
    out = []
    d = 0.0
    while d < total:
        out.append(interpolate_along(coords, cum, d)[0])
        d += step_mi
    out.append(coords[-1])
    return out


def overlap_ratio(a: Sequence[LatLon], b: Sequence[LatLon], cell_deg: float = 0.01) -> float:
    """Fraction of line `b`'s length that runs along line `a` (~1 km tolerance)."""
    occupied: set[tuple[int, int]] = set()
    for lat, lon in resample(a, 0.3):
        ci, cj = int(math.floor(lat / cell_deg)), int(math.floor(lon / cell_deg))
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                occupied.add((ci + di, cj + dj))
    samples = resample(b, 0.5)
    hits = sum(
        1
        for lat, lon in samples
        if (int(math.floor(lat / cell_deg)), int(math.floor(lon / cell_deg))) in occupied
    )
    return hits / len(samples)


def offset_point(origin: LatLon, dest: LatLon, along: float, perpendicular_mi: float) -> LatLon:
    """Point at fraction `along` of the straight origin->dest line, shifted sideways.

    Uses a local equirectangular approximation, adequate for picking a via point.
    """
    lat0 = math.radians((origin[0] + dest[0]) / 2)
    mi_per_deg_lat = 69.0
    mi_per_deg_lon = 69.0 * math.cos(lat0)
    dx = (dest[1] - origin[1]) * mi_per_deg_lon
    dy = (dest[0] - origin[0]) * mi_per_deg_lat
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length  # unit normal (left of travel direction)
    x = origin[1] * mi_per_deg_lon + dx * along + px * perpendicular_mi
    y = origin[0] * mi_per_deg_lat + dy * along + py * perpendicular_mi
    return (y / mi_per_deg_lat, x / mi_per_deg_lon)


def mercator_y(lat: float) -> float:
    lat = max(-85.0, min(85.0, lat))
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def inverse_mercator_y(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)
