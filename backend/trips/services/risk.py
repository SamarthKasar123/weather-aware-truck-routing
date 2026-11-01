"""Weather risk rules and route recommendation.

All thresholds come straight from the assignment's risk table and load rules.
This module is pure (no I/O) so it can be unit-tested exhaustively.

Band edges: the table lists shared boundaries (e.g. rain "0.10-0.25" and
"0.25-0.50"). We treat each lower bound as inclusive, so a value sitting on a
boundary falls into the *higher* (safer-to-assume) band, except at the
No Travel edge for rain/snow, which the table defines as strictly greater
than 1.00 / 3.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    Risk.LOW: "Low",
    Risk.MODERATE: "Moderate",
    Risk.HIGH: "High",
    Risk.SEVERE: "Severe",
    Risk.NO_TRAVEL: "No Travel",
}


def wind_risk(wind_mph: float, load_lb: float) -> Risk:
    """Wind band, escalated by the load rules."""
    if wind_mph >= 55:
        return Risk.NO_TRAVEL  # any load
    if wind_mph >= 45:
        return Risk.NO_TRAVEL if load_lb > 30_000 else Risk.SEVERE
    if wind_mph >= 35:
        return Risk.SEVERE if load_lb > 40_000 else Risk.HIGH
    if wind_mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def rain_risk(rain_in_hr: float) -> Risk:
    if rain_in_hr > 1.00:
        return Risk.NO_TRAVEL
    if rain_in_hr >= 0.50:
        return Risk.SEVERE
    if rain_in_hr >= 0.25:
        return Risk.HIGH
    if rain_in_hr >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def snow_risk(snow_in_hr: float) -> Risk:
    if snow_in_hr > 3.0:
        return Risk.NO_TRAVEL
    if snow_in_hr >= 2.0:
        return Risk.SEVERE
    if snow_in_hr >= 1.0:
        return Risk.HIGH
    if snow_in_hr >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    reasons: tuple[str, ...]


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall risk at a point = worst of the three conditions."""
    w, r, s = wind_risk(wind_mph, load_lb), rain_risk(rain_in_hr), snow_risk(snow_in_hr)
    level = max(w, r, s)
    reasons = []
    if w > Risk.LOW:
        base = wind_risk(wind_mph, 0)
        if w > base:
            reasons.append(
                f"Wind {wind_mph:.0f} mph with {load_lb:,.0f} lb load → {w.label} (load rule)"
            )
        else:
            reasons.append(f"Wind {wind_mph:.0f} mph → {w.label}")
    if r > Risk.LOW:
        reasons.append(f"Rain {rain_in_hr:.2f} in/hr → {r.label}")
    if s > Risk.LOW:
        reasons.append(f"Snow {snow_in_hr:.2f} in/hr → {s.label}")
    return Assessment(level, w, r, s, tuple(reasons))


# ---------------------------------------------------------------------------
# Route-level scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteScore:
    """Mileage exposure per risk level for one route."""

    miles_by_level: dict[Risk, float]
    average_risk: float  # mile-weighted mean of level values (0-4)
    max_level: Risk
    duration_s: float

    def sort_key(self) -> tuple:
        """Assignment priority: Severe miles, High miles, avg risk, travel time.

        No Travel is strictly worse than Severe, so it is compared first:
        a route that crosses a No Travel zone never beats one that doesn't.
        Miles are rounded to 0.1 and average risk to 0.01 so floating-point
        noise doesn't decide a tie that should fall through to the next rule.
        """
        m = self.miles_by_level
        return (
            round(m[Risk.NO_TRAVEL], 1),
            round(m[Risk.SEVERE], 1),
            round(m[Risk.HIGH], 1),
            round(self.average_risk, 2),
            self.duration_s,
        )


def score_route(
    checkpoint_miles: list[float], checkpoint_levels: list[Risk], total_miles: float, duration_s: float
) -> RouteScore:
    """Attribute route miles to checkpoints and total them per risk level.

    Each checkpoint represents the stretch of road closer to it than to its
    neighbours (from the midpoint with the previous checkpoint to the midpoint
    with the next), so every mile is counted exactly once.
    """
    miles_by_level = {lvl: 0.0 for lvl in Risk}
    weighted = 0.0
    n = len(checkpoint_miles)
    for i, (mile, level) in enumerate(zip(checkpoint_miles, checkpoint_levels)):
        start = 0.0 if i == 0 else (checkpoint_miles[i - 1] + mile) / 2
        end = total_miles if i == n - 1 else (mile + checkpoint_miles[i + 1]) / 2
        span = max(0.0, end - start)
        miles_by_level[level] += span
        weighted += span * int(level)
    return RouteScore(
        miles_by_level=miles_by_level,
        average_risk=weighted / total_miles if total_miles > 0 else 0.0,
        max_level=max(checkpoint_levels, default=Risk.LOW),
        duration_s=duration_s,
    )


def recommend(scores: list[RouteScore]) -> tuple[int, list[int]]:
    """Return (index of best route, all indices ranked best→worst)."""
    ranking = sorted(range(len(scores)), key=lambda i: scores[i].sort_key())
    return ranking[0], ranking


_MILE_CRITERIA = ("No Travel", "Severe", "High")  # sort_key positions 0-2


def explain(best: RouteScore, runner_up: RouteScore | None) -> str:
    """Human-readable reason the best route beat the runner-up."""
    if runner_up is None:
        return "Only one route available."
    bk, rk = best.sort_key(), runner_up.sort_key()
    for idx, name in enumerate(_MILE_CRITERIA):
        if bk[idx] < rk[idx]:
            return f"Fewest {name} miles ({bk[idx]:.1f} mi vs {rk[idx]:.1f} mi)."
    if bk[3] < rk[3]:
        return f"Lowest average risk ({bk[3]:.2f} vs {rk[3]:.2f}) with equal Severe/High exposure."
    saved_min = (runner_up.duration_s - best.duration_s) / 60
    if saved_min >= 1:
        return f"Equal weather exposure; fastest option (saves {saved_min:.0f} min)."
    return "Equal weather exposure and travel time."
