from unittest import mock

from django.test import SimpleTestCase

from trips.services import routing
from trips.services.http import InputError


def _osrm_response(snap_m):
    return 200, {
        "code": "Ok",
        "waypoints": [{"distance": snap_m}, {"distance": 3}],
        "routes": [{
            "geometry": {"coordinates": [[-9.5, 38.8], [-0.13, 51.5]]},
            "legs": [{"annotation": {"duration": [100.0]}, "summary": "A1"}],
            "distance": 2_000_000, "duration": 100.0,
        }],
    }


class OsrmTests(SimpleTestCase):
    def test_far_snapped_endpoint_is_no_route(self):
        with mock.patch.object(routing, "get_json", return_value=_osrm_response(5_534_802)):
            with self.assertRaisesRegex(InputError, "origin"):
                routing._osrm([(40.7, -74.0), (51.5, -0.13)])

    def test_normal_snap_is_accepted(self):
        with mock.patch.object(routing, "get_json", return_value=_osrm_response(40)):
            routes = routing._osrm([(38.8, -9.5), (51.5, -0.13)])
        self.assertEqual(routes[0].summary, "A1")
