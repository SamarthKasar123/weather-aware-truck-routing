"""Planner integration test with routing and weather providers stubbed out."""
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from trips.services import geo, planner, weather
from trips.services.geocoding import Place
from trips.services.routing import RawRoute

DEPARTURE = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _straight_route(lat: float, n: int = 101, mph: float = 50.0) -> RawRoute:
    coords = [(lat, -100.0 + i * 0.02) for i in range(n)]
    cum = geo.cumulative_miles(coords)
    seg = [(cum[i + 1] - cum[i]) / mph * 3600 for i in range(n - 1)]
    return RawRoute(coords, seg, cum[-1] * geo.METERS_PER_MILE, sum(seg), f"Road {lat}")


def _series(wind: float) -> weather.HourlySeries:
    start = int(DEPARTURE.timestamp())
    times = [start + h * 3600 for h in range(72)]
    n = len(times)
    return weather.HourlySeries(times, [50.0] * n, [wind] * n, [wind] * n, [0.0] * n, [0.0] * n, [0] * n)


class PlannerTests(SimpleTestCase):
    def setUp(self):
        self.routes = [_straight_route(40.0), _straight_route(41.0), _straight_route(42.0)]
        self.req = planner.TripRequest(
            Place("A", 40, -100), Place("B", 40, -98), DEPARTURE, load_lb=45_000, interval_mi=25
        )

    def _fake_fetch(self, points, start, end):
        # Route at lat 40 (the fastest-listed) is windy: 40 mph with 45k lb -> Severe.
        return [_series(40.0 if abs(p[0] - 40.0) < 0.1 else 10.0) for p in points], 0.05

    def test_plan_recommends_route_without_severe_miles(self):
        with mock.patch.object(planner.routing, "route_options", return_value=self.routes), \
             mock.patch.object(planner.weather, "fetch_hourly", side_effect=self._fake_fetch):
            out = planner.plan_trip(self.req)

        self.assertEqual(len(out["routes"]), 3)
        windy = out["routes"][0]
        self.assertGreater(windy["score"]["miles_by_level"][3], 0)
        self.assertNotEqual(out["recommendation"]["route_id"], windy["id"])
        self.assertIn("Severe", windy["why_not"])

    def test_checkpoints_follow_interval_and_eta(self):
        with mock.patch.object(planner.routing, "route_options", return_value=self.routes), \
             mock.patch.object(planner.weather, "fetch_hourly", side_effect=self._fake_fetch):
            out = planner.plan_trip(self.req)

        route = out["routes"][0]
        miles = [c["mile"] for c in route["checkpoints"]]
        self.assertEqual(miles[:4], [0, 25, 50, 75])
        self.assertAlmostEqual(miles[-1], route["distance_mi"], places=1)
        # Constant 50 mph -> mile 25 is reached 30 minutes after departure.
        eta = datetime.fromisoformat(route["checkpoints"][1]["eta"])
        self.assertAlmostEqual((eta - DEPARTURE).total_seconds(), 1800, delta=5)
        # Risk segments cover the whole route.
        self.assertTrue(route["risk_segments"])


class WeatherSampleTests(SimpleTestCase):
    def test_wind_interpolates_and_precip_uses_containing_hour(self):
        t0 = int(DEPARTURE.timestamp())
        s = weather.HourlySeries(
            times=[t0, t0 + 3600],
            temp_f=[40, 50], wind_mph=[10, 20], gust_mph=[15, 25],
            rain_in=[0.0, 0.3], snow_in=[0.0, 0.0], code=[0, 61],
        )
        smp = weather.sample(s, DEPARTURE + timedelta(minutes=30))
        self.assertAlmostEqual(smp.wind_mph, 15)
        self.assertAlmostEqual(smp.rain_in_hr, 0.3)  # value stamped at the end of that hour
        self.assertEqual(smp.weather_code, 61)


class WeatherGridTests(SimpleTestCase):
    def test_grid_coarsens_to_fit_budget(self):
        points = [(40.0, -100.0 + i * 0.05) for i in range(400)]  # 400 distinct points ~3 mi apart
        snapped, grid = weather._snap_all(points, max_points=150)
        self.assertLessEqual(len(set(snapped)), 150)
        self.assertGreater(grid, 0.05)

    def test_small_trips_keep_finest_grid(self):
        _, grid = weather._snap_all([(40.0, -100.0), (40.5, -100.5)], max_points=150)
        self.assertEqual(grid, 0.05)
