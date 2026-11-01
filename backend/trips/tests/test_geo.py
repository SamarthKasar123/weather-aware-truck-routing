from django.test import SimpleTestCase

from trips.services import geo


class GeoTests(SimpleTestCase):
    def test_haversine_known_distance(self):
        # Chicago -> Denver great-circle distance is ~920 miles.
        self.assertAlmostEqual(geo.haversine_mi((41.8781, -87.6298), (39.7392, -104.9903)), 920, delta=5)

    def test_interpolate_along_midpoint(self):
        line = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cum = geo.cumulative_miles(line)
        point, seg, frac = geo.interpolate_along(line, cum, cum[-1] * 0.75)
        self.assertAlmostEqual(point[1], 1.5, places=6)
        self.assertEqual(seg, 1)
        self.assertAlmostEqual(frac, 0.5, places=6)

    def test_interpolate_clamps(self):
        line = [(0.0, 0.0), (1.0, 1.0)]
        cum = geo.cumulative_miles(line)
        self.assertEqual(geo.interpolate_along(line, cum, -5)[0], line[0])
        self.assertEqual(geo.interpolate_along(line, cum, 1e9)[0], line[-1])

    def test_simplify_keeps_endpoints_and_corners(self):
        line = [(0.0, x / 10) for x in range(11)] + [(1.0, 1.0)]
        keep = geo.simplify_indices(line, 0.001)
        self.assertEqual(keep, [0, 10, 11])

    def test_slice_line(self):
        line = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cum = geo.cumulative_miles(line)
        part = geo.slice_line(line, cum, cum[-1] * 0.25, cum[-1] * 0.75)
        self.assertAlmostEqual(part[0][1], 0.5, places=6)
        self.assertEqual(part[1], (0.0, 1.0))
        self.assertAlmostEqual(part[-1][1], 1.5, places=6)

    def test_overlap_ratio(self):
        a = [(40.0, -100.0), (40.0, -99.0)]
        parallel_far = [(41.0, -100.0), (41.0, -99.0)]
        self.assertGreater(geo.overlap_ratio(a, a), 0.95)
        self.assertLess(geo.overlap_ratio(a, parallel_far), 0.05)

    def test_mercator_roundtrip(self):
        for lat in (-60, 0, 33.3, 70):
            self.assertAlmostEqual(geo.inverse_mercator_y(geo.mercator_y(lat)), lat, places=9)
