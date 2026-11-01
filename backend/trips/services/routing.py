"""Route options via OSRM.

OSRM's `alternatives` frequently returns fewer than 3 routes (it only offers
alternatives that are meaningfully different and not much slower). When that
happens we ask for routes forced through via points offset to either side of
the straight line, and keep the ones that are genuinely different.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from . import geo
from .geo import LatLon
from .http import InputError, ProviderError, get_json

log = logging.getLogger(__name__)

TARGET_ROUTES = 3
MAX_OVERLAP = 0.85  # a candidate sharing more than this with an existing route is a duplicate
MAX_SLOWDOWN = 1.6  # ignore candidates much slower than the fastest route
MAX_SNAP_M = 25_000  # origin/destination farther than this from a usable road -> no route
# (fraction along the straight line, sideways offset as a fraction of its length)
VIA_OFFSETS = ((0.5, 0.12), (0.5, -0.12), (0.5, 0.25), (0.5, -0.25), (0.35, 0.18), (0.65, -0.18))


@dataclass
class RawRoute:
    coords: list[LatLon]
    segment_durations_s: list[float]  # one per consecutive coordinate pair
    distance_m: float
    duration_s: float
    summary: str


def _parse(route: dict) -> RawRoute:
    coords = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    seg = [d for leg in route["legs"] for d in leg.get("annotation", {}).get("duration", [])]
    if len(seg) != len(coords) - 1:
        # Annotation mismatch: spread total duration proportionally to distance instead.
        cum = geo.cumulative_miles(coords)
        total = cum[-1] or 1.0
        seg = [route["duration"] * (cum[i + 1] - cum[i]) / total for i in range(len(coords) - 1)]
    names: list[str] = []
    for leg in route["legs"]:
        for name in (leg.get("summary") or "").split(","):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    return RawRoute(coords, seg, route["distance"], route["duration"], ", ".join(names[:3]))


def _osrm(waypoints: list[LatLon], alternatives: int = 0) -> list[RawRoute]:
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    status, data = get_json(
        f"{settings.OSRM_BASE_URL}/route/v1/driving/{path}",
        {
            "alternatives": str(alternatives) if alternatives else "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "duration",
            "steps": "true",  # needed for leg summaries (road names)
        },
        provider="Routing service",
    )
    code = data.get("code")
    if code == "NoRoute":
        return []
    if status != 200 or code != "Ok":
        if code in ("NoSegment", "InvalidQuery", "InvalidValue"):
            raise InputError("One of the locations is not reachable by road.")
        raise ProviderError(f"Routing service error: {data.get('message') or code}")
    # OSRM snaps each endpoint to the nearest routable road with no distance limit, so
    # an unconnected pair (e.g. New York -> London) "succeeds" by snapping one end to
    # a road thousands of miles away. Treat a far snap as no route.
    wps = data.get("waypoints", [])
    for wp, name in ((wps[0], "origin"), (wps[-1], "destination")) if wps else ():
        if wp.get("distance", 0) > MAX_SNAP_M:
            raise InputError(f"No drivable route: the {name} isn't reachable by road from the other end.")
    return [_parse(r) for r in data["routes"]]


def _is_distinct(candidate: RawRoute, existing: list[RawRoute]) -> bool:
    return all(geo.overlap_ratio(r.coords, candidate.coords) < MAX_OVERLAP for r in existing)


def apply_truck_speed_cap(route: RawRoute) -> RawRoute:
    """Slow any segment faster than the truck max speed (OSRM uses a car profile)."""
    max_mps = settings.TRUCK_MAX_SPEED_MPH * geo.METERS_PER_MILE / 3600
    seg = []
    for i, d in enumerate(route.segment_durations_s):
        length_m = geo.haversine_mi(route.coords[i], route.coords[i + 1]) * geo.METERS_PER_MILE
        seg.append(max(d, length_m / max_mps))
    return RawRoute(route.coords, seg, route.distance_m, sum(seg), route.summary)


def route_options(origin: LatLon, destination: LatLon) -> list[RawRoute]:
    routes = _osrm([origin, destination], alternatives=TARGET_ROUTES)
    if not routes:
        raise InputError("No drivable route was found between these locations.")
    routes = [r for i, r in enumerate(routes) if _is_distinct(r, routes[:i])]

    fastest = min(r.duration_s for r in routes)
    straight_mi = geo.haversine_mi(origin, destination)
    for along, side in VIA_OFFSETS:
        if len(routes) >= TARGET_ROUTES:
            break
        via = geo.offset_point(origin, destination, along, side * straight_mi)
        try:
            candidates = _osrm([origin, via, destination])
        except (InputError, ProviderError) as exc:
            log.info("Via-point candidate skipped: %s", exc)
            continue
        for c in candidates:
            if c.duration_s <= fastest * MAX_SLOWDOWN and _is_distinct(c, routes):
                routes.append(c)

    routes = [apply_truck_speed_cap(r) for r in routes[:TARGET_ROUTES]]
    routes.sort(key=lambda r: r.duration_s)
    return routes
