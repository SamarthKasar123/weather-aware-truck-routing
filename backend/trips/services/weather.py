"""Hourly forecasts from Open-Meteo (free, no key), batched and cached.

Units requested: wind in mph, precipitation and snowfall in inches. Open-Meteo
reports rain/showers/snowfall as the amount over the *preceding* hour, which is
exactly an in/hr rate for that hour.
"""
from __future__ import annotations

from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from .geo import LatLon
from .http import ProviderError, get_json

# Points are snapped to a lookup grid to share forecasts between nearby points.
# Open-Meteo's free tier counts every location as one call (~600/min), so when a
# trip has more unique points than `max_points` the grid is coarsened step by
# step. Short trips keep ~3.5 mi precision; a cross-country trip at 10 mi
# spacing ends up around 0.15-0.25° (~10-17 mi). ETAs are unaffected.
GRID_STEPS_DEG = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5)
DEFAULT_MAX_POINTS = 300
BATCH_SIZE = 100  # locations per Open-Meteo request
MAX_WORKERS = 4
CACHE_TTL_S = 30 * 60
HOURLY_VARS = (
    "temperature_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
    "weather_code",
)


@dataclass
class HourlySeries:
    times: list[int]  # unix seconds, hourly
    temp_f: list[float]
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in: list[float]  # liquid precip (rain + showers) during the preceding hour
    snow_in: list[float]  # snowfall during the preceding hour
    code: list[int]


@dataclass(frozen=True)
class Sample:
    temp_f: float
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    weather_code: int

    def to_dict(self) -> dict:
        return {
            "temp_f": round(self.temp_f, 1),
            "wind_mph": round(self.wind_mph, 1),
            "gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 3),
            "snow_in_hr": round(self.snow_in_hr, 3),
            "weather_code": self.weather_code,
        }


def _num(values: list, default: float = 0.0) -> list[float]:
    return [default if v is None else float(v) for v in values]


def _parse(loc: dict) -> HourlySeries:
    h = loc["hourly"]
    rain, showers = _num(h["rain"]), _num(h["showers"])
    return HourlySeries(
        times=[int(t) for t in h["time"]],
        temp_f=_num(h["temperature_2m"]),
        wind_mph=_num(h["wind_speed_10m"]),
        gust_mph=_num(h["wind_gusts_10m"]),
        rain_in=[r + s for r, s in zip(rain, showers)],
        snow_in=_num(h["snowfall"]),
        code=[int(c) for c in _num(h["weather_code"])],
    )


def _snap(p: LatLon, grid: float) -> LatLon:
    return (round(round(p[0] / grid) * grid, 4), round(round(p[1] / grid) * grid, 4))


def _snap_all(points: list[LatLon], max_points: int) -> tuple[list[LatLon], float]:
    for grid in GRID_STEPS_DEG:
        snapped = [_snap(p, grid) for p in points]
        if len(set(snapped)) <= max_points:
            break
    return snapped, grid


def _hour_floor(t: datetime) -> datetime:
    return t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _fetch_batch(points: list[LatLon], start: str, end: str) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": start,
        "end_hour": end,
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    status, data = get_json(f"{settings.OPEN_METEO_BASE_URL}/v1/forecast", params, provider="Weather service")
    if status != 200:
        reason = data.get("reason", "") if isinstance(data, dict) else ""
        raise ProviderError(f"Weather service rejected the request: {reason or status}")
    if isinstance(data, dict):  # a single location comes back as an object, not a list
        data = [data]
    return [_parse(loc) for loc in data]


def fetch_hourly(
    points: list[LatLon], start: datetime, end: datetime, max_points: int = DEFAULT_MAX_POINTS
) -> tuple[list[HourlySeries], float]:
    """Hourly series covering [start, end] for each point (same order as input).

    Also returns the lookup grid size (degrees) that was used.
    """
    start_h = _hour_floor(start)
    end_h = _hour_floor(end) + timedelta(hours=1)
    s, e = start_h.strftime("%Y-%m-%dT%H:%M"), end_h.strftime("%Y-%m-%dT%H:%M")

    snapped, grid = _snap_all(points, max_points)
    unique = list(dict.fromkeys(snapped))
    found: dict[LatLon, HourlySeries] = {}
    keys = {p: f"wx:{p[0]}:{p[1]}:{s}:{e}" for p in unique}
    cached = cache.get_many(list(keys.values()))
    missing = []
    for p in unique:
        if keys[p] in cached:
            found[p] = cached[keys[p]]
        else:
            missing.append(p)

    batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    if batches:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(batches))) as pool:
            results = list(pool.map(lambda b: _fetch_batch(b, s, e), batches))
        fresh = {}
        for batch, series_list in zip(batches, results):
            for p, series in zip(batch, series_list):
                found[p] = series
                fresh[keys[p]] = series
        cache.set_many(fresh, CACHE_TTL_S)

    return [found[p] for p in snapped], grid


def sample(series: HourlySeries, when: datetime) -> Sample:
    """Conditions at `when`.

    Instantaneous fields (wind, temperature) are linearly interpolated between
    the surrounding hours. Precipitation uses the hourly bucket that contains
    `when` (the value stamped at the next full hour).
    """
    t = when.timestamp()
    times = series.times
    i = bisect_left(times, t)  # first hour >= t  -> the bucket containing t
    hi = min(max(i, 0), len(times) - 1)
    lo = max(hi - 1, 0)
    if hi == lo or times[hi] == times[lo]:
        f = 0.0
    else:
        f = min(1.0, max(0.0, (t - times[lo]) / (times[hi] - times[lo])))

    def lerp(values: list[float]) -> float:
        return values[lo] + (values[hi] - values[lo]) * f

    return Sample(
        temp_f=lerp(series.temp_f),
        wind_mph=lerp(series.wind_mph),
        gust_mph=lerp(series.gust_mph),
        rain_in_hr=series.rain_in[hi],
        snow_in_hr=series.snow_in[hi],
        weather_code=series.code[hi],
    )
