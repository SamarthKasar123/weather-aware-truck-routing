from django.test import SimpleTestCase

from trips.services.risk import (
    Risk,
    RouteScore,
    assess,
    explain,
    rain_risk,
    recommend,
    score_route,
    snow_risk,
    wind_risk,
)


class WindRiskTests(SimpleTestCase):
    def test_bands_for_light_load(self):
        cases = [(0, Risk.LOW), (24.9, Risk.LOW), (25, Risk.MODERATE), (34.9, Risk.MODERATE),
                 (35, Risk.HIGH), (44.9, Risk.HIGH), (45, Risk.SEVERE), (54.9, Risk.SEVERE),
                 (55, Risk.NO_TRAVEL), (80, Risk.NO_TRAVEL)]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertEqual(wind_risk(mph, 10_000), expected)

    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(wind_risk(55, 0), Risk.NO_TRAVEL)

    def test_45_to_54_over_30k_lb_is_no_travel(self):
        self.assertEqual(wind_risk(45, 30_001), Risk.NO_TRAVEL)
        self.assertEqual(wind_risk(54, 50_000), Risk.NO_TRAVEL)
        self.assertEqual(wind_risk(50, 30_000), Risk.SEVERE)  # exactly 30,000 is not "> 30,000"

    def test_35_to_44_over_40k_lb_is_severe(self):
        self.assertEqual(wind_risk(35, 40_001), Risk.SEVERE)
        self.assertEqual(wind_risk(44, 40_000), Risk.HIGH)

    def test_load_rules_do_not_touch_lower_bands(self):
        self.assertEqual(wind_risk(30, 80_000), Risk.MODERATE)


class PrecipRiskTests(SimpleTestCase):
    def test_rain_bands(self):
        cases = [(0, Risk.LOW), (0.09, Risk.LOW), (0.10, Risk.MODERATE), (0.25, Risk.HIGH),
                 (0.50, Risk.SEVERE), (1.00, Risk.SEVERE), (1.01, Risk.NO_TRAVEL)]
        for v, expected in cases:
            with self.subTest(v=v):
                self.assertEqual(rain_risk(v), expected)

    def test_snow_bands(self):
        cases = [(0.4, Risk.LOW), (0.5, Risk.MODERATE), (1.0, Risk.HIGH), (2.0, Risk.SEVERE),
                 (3.0, Risk.SEVERE), (3.1, Risk.NO_TRAVEL)]
        for v, expected in cases:
            with self.subTest(v=v):
                self.assertEqual(snow_risk(v), expected)


class AssessTests(SimpleTestCase):
    def test_overall_is_worst_condition(self):
        a = assess(wind_mph=26, rain_in_hr=0.3, snow_in_hr=0, load_lb=10_000)
        self.assertEqual((a.level, a.wind, a.rain, a.snow), (Risk.HIGH, Risk.MODERATE, Risk.HIGH, Risk.LOW))

    def test_reason_mentions_load_rule(self):
        a = assess(wind_mph=47, rain_in_hr=0, snow_in_hr=0, load_lb=35_000)
        self.assertEqual(a.level, Risk.NO_TRAVEL)
        self.assertIn("load rule", a.reasons[0])

    def test_calm_weather_has_no_reasons(self):
        self.assertEqual(assess(5, 0, 0, 80_000).reasons, ())


class ScoreRouteTests(SimpleTestCase):
    def test_midpoint_attribution_counts_each_mile_once(self):
        # Checkpoints at 0, 25, 50, 60 (end). Spans: 12.5, 25, 17.5, 5
        s = score_route([0, 25, 50, 60], [Risk.LOW, Risk.SEVERE, Risk.HIGH, Risk.LOW], 60, 3600)
        self.assertAlmostEqual(s.miles_by_level[Risk.SEVERE], 25)
        self.assertAlmostEqual(s.miles_by_level[Risk.HIGH], 17.5)
        self.assertAlmostEqual(s.miles_by_level[Risk.LOW], 17.5)
        self.assertAlmostEqual(sum(s.miles_by_level.values()), 60)
        self.assertAlmostEqual(s.average_risk, (25 * 3 + 17.5 * 2) / 60)
        self.assertEqual(s.max_level, Risk.SEVERE)


def _score(no_travel=0.0, severe=0.0, high=0.0, avg=0.0, duration=3600.0):
    miles = {lvl: 0.0 for lvl in Risk}
    miles[Risk.NO_TRAVEL], miles[Risk.SEVERE], miles[Risk.HIGH] = no_travel, severe, high
    return RouteScore(miles, avg, Risk.LOW, duration)


class RecommendTests(SimpleTestCase):
    def test_fewest_severe_miles_wins_over_speed(self):
        best, _ = recommend([_score(severe=10, duration=100), _score(severe=0, high=90, duration=900)])
        self.assertEqual(best, 1)

    def test_high_miles_break_severe_tie(self):
        best, _ = recommend([_score(severe=5, high=30), _score(severe=5, high=10)])
        self.assertEqual(best, 1)

    def test_average_risk_breaks_high_tie(self):
        best, _ = recommend([_score(high=10, avg=0.9), _score(high=10, avg=0.4)])
        self.assertEqual(best, 1)

    def test_travel_time_is_last_tiebreaker(self):
        best, ranking = recommend([_score(duration=5000), _score(duration=4000), _score(duration=4500)])
        self.assertEqual((best, ranking), (1, [1, 2, 0]))

    def test_no_travel_is_worse_than_any_severe(self):
        best, _ = recommend([_score(no_travel=1, severe=0), _score(severe=200)])
        self.assertEqual(best, 1)

    def test_float_noise_does_not_decide_ties(self):
        best, _ = recommend([_score(severe=10.000001, duration=100), _score(severe=10.0, duration=200)])
        self.assertEqual(best, 0)

    def test_explain(self):
        self.assertIn("Fewest Severe miles", explain(_score(severe=0), _score(severe=12)))
        self.assertIn("fastest", explain(_score(duration=1000), _score(duration=4000)))
        self.assertEqual(explain(_score(), None), "Only one route available.")
