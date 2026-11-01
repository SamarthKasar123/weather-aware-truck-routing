"""Trip planning: routes → checkpoints with ETAs → weather → risk → recommendation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import geo, risk, routing, weather
from .geo import LatLon
from .geocoding import Place
from .risk import Risk

DISPLAY_TOLERANCE_DEG = 0.0002  # ~20 m; keeps map geometry light without visible change
CORRIDOR_STEP_MI = 8.0


@dataclass
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime  # timezone-aware
    load_lb: float
    interval_mi: int


@dataclass
class Checkpoint:
    mile: float
    point: LatLon
    eta_offset_s: float
    eta: datetime
    sample: weather.Sample | None = None
    assessment: risk.Assessment | None = None


@dataclass
class BuiltRoute:
    raw: routing.RawRoute
    coords: list[LatLon]  # simplified display geometry
    miles: list[float]  # cumulative miles at each display vertex
    times_s: list[float]  # cumulative seconds from departure at each display vertex
    total_mi: float
    checkpoints: list[Checkpoint] = field(default_factory=list)


def _build_route(raw: routing.RawRoute, req: TripRequest) -> BuiltRoute:
    cum_mi = geo.cumulative_miles(raw.coords)
    # Scale geometric length to the router's reported distance so the final checkpoint
    # sits exactly at the reported trip length.
    total_mi = raw.distance_m / geo.METERS_PER_MILE
    scale = total_mi / cum_mi[-1] if cum_mi[-1] > 0 else 1.0
    cum_mi = [m * scale for m in cum_mi]
    cum_s = [0.0]
    for d in raw.segment_durations_s:
        cum_s.append(cum_s[-1] + d)

    checkpoint_miles = [float(m) for m in range(0, int(total_mi), req.interval_mi)]
    if not checkpoint_miles or total_mi - checkpoint_miles[-1] > 0.05:
        checkpoint_miles.append(total_mi)
    checkpoints = []
    for mile in checkpoint_miles:
        point, i, f = geo.interpolate_along(raw.coords, cum_mi, mile)
        offset = cum_s[i] + f * (cum_s[i + 1] - cum_s[i])
        checkpoints.append(Checkpoint(mile, point, offset, req.departure + timedelta(seconds=offset)))

    keep = geo.simplify_indices(raw.coords, DISPLAY_TOLERANCE_DEG)
    return BuiltRoute(
        raw=raw,
        coords=[raw.coords[i] for i in keep],
        miles=[cum_mi[i] for i in keep],
        times_s=[cum_s[i] for i in keep],
        total_mi=total_mi,
        checkpoints=checkpoints,
    )


def _risk_segments(route: BuiltRoute) -> list[dict]:
    """Split the display line into stretches coloured by their checkpoint's risk.

    Uses the same midpoint attribution as `risk.score_route`, and merges
    neighbouring stretches that share a level.
    """
    cps = route.checkpoints
    segments: list[dict] = []
    for i, cp in enumerate(cps):
        start = 0.0 if i == 0 else (cps[i - 1].mile + cp.mile) / 2
        end = route.total_mi if i == len(cps) - 1 else (cp.mile + cps[i + 1].mile) / 2
        level = int(cp.assessment.level)
        part = geo.slice_line(route.coords, route.miles, start, end)
        if segments and segments[-1]["level"] == level:
            segments[-1]["coords"].extend(part[1:])
        else:
            segments.append({"level": level, "coords": part})
    for s in segments:
        s["coords"] = [[round(lat, 5), round(lon, 5)] for lat, lon in s["coords"]]
    return segments


def _score_dict(score: risk.RouteScore) -> dict:
    return {
        "miles_by_level": {int(k): round(v, 1) for k, v in score.miles_by_level.items()},
        "average_risk": round(score.average_risk, 3),
        "max_level": int(score.max_level),
    }


def _checkpoint_dict(i: int, cp: Checkpoint) -> dict:
    a = cp.assessment
    return {
        "index": i,
        "mile": round(cp.mile, 1),
        "lat": round(cp.point[0], 5),
        "lon": round(cp.point[1], 5),
        "eta": cp.eta.isoformat(),
        "eta_offset_s": round(cp.eta_offset_s),
        "weather": cp.sample.to_dict(),
        "risk": {
            "level": int(a.level),
            "wind": int(a.wind),
            "rain": int(a.rain),
            "snow": int(a.snow),
        },
        "reasons": list(a.reasons),
    }


def plan_trip(req: TripRequest) -> dict:
    raws = routing.route_options((req.origin.lat, req.origin.lon), (req.destination.lat, req.destination.lon))
    routes = [_build_route(r, req) for r in raws]

    # One batched weather lookup for every checkpoint of every route.
    all_cps = [cp for r in routes for cp in r.checkpoints]
    latest_eta = max(cp.eta for cp in all_cps)
    series, weather_grid = weather.fetch_hourly([cp.point for cp in all_cps], req.departure, latest_eta)
    for cp, s in zip(all_cps, series):
        cp.sample = weather.sample(s, cp.eta)
        cp.assessment = risk.assess(
            cp.sample.wind_mph, cp.sample.rain_in_hr, cp.sample.snow_in_hr, req.load_lb
        )

    scores = [
        risk.score_route(
            [cp.mile for cp in r.checkpoints],
            [cp.assessment.level for cp in r.checkpoints],
            r.total_mi,
            r.raw.duration_s,
        )
        for r in routes
    ]
    best, ranking = risk.recommend(scores)
    runner_up = scores[ranking[1]] if len(ranking) > 1 else None
    ids = [chr(ord("A") + i) for i in range(len(routes))]  # routes arrive sorted fastest-first

    warnings = []
    if len(routes) < routing.TARGET_ROUTES:
        warnings.append(
            f"Only {len(routes)} distinct route(s) exist between these points; showing all of them."
        )
    best_miles = scores[best].miles_by_level
    if best_miles[Risk.NO_TRAVEL] > 0:
        warnings.append(
            "Every route crosses No Travel conditions at the planned time. "
            "Consider delaying departure."
        )
    elif best_miles[Risk.SEVERE] > 0:
        warnings.append("Even the recommended route has Severe weather exposure. Drive with caution.")

    out_routes = []
    for i, (r, score) in enumerate(zip(routes, scores)):
        arrival = req.departure + timedelta(seconds=r.raw.duration_s)
        out_routes.append(
            {
                "id": ids[i],
                "summary": r.raw.summary,
                "distance_mi": round(r.total_mi, 1),
                "duration_s": round(r.raw.duration_s),
                "arrival": arrival.isoformat(),
                "rank": ranking.index(i) + 1,
                "recommended": i == best,
                "why_not": None if i == best else risk.explain(scores[best], score),
                "score": _score_dict(score),
                "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in r.coords],
                "vertex_times_s": [round(t) for t in r.times_s],
                "risk_segments": _risk_segments(r),
                "checkpoints": [_checkpoint_dict(j, cp) for j, cp in enumerate(r.checkpoints)],
            }
        )

    return {
        "origin": req.origin.to_dict(),
        "destination": req.destination.to_dict(),
        "departure": req.departure.isoformat(),
        "load_lb": req.load_lb,
        "interval_mi": req.interval_mi,
        "routes": out_routes,
        "recommendation": {
            "route_id": ids[best],
            "reason": risk.explain(scores[best], runner_up),
            "ranking": [ids[i] for i in ranking],
        },
        "corridor": [
            [[round(lat, 3), round(lon, 3)] for lat, lon in geo.resample(r.coords, CORRIDOR_STEP_MI)]
            for r in routes
        ],
        "warnings": warnings,
        "weather_grid_deg": weather_grid,
    }
