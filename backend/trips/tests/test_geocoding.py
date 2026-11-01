from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from trips.services import geocoding
from trips.services.http import ProviderError


def _feature(name, lat, lon, osm_key, state="", country="", countrycode=""):
    return {
        "geometry": {"coordinates": [lon, lat]},
        "properties": {"name": name, "osm_key": osm_key, "state": state, "country": country,
                       "countrycode": countrycode},
    }


class SearchTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_city_region_query_prefers_matching_place(self):
        business = _feature("CAF USA, Incorporated", 42.1, -76.8, "landuse", "New York", "United States", "US")
        city_us = _feature("New York", 40.71, -74.0, "place", "New York", "United States", "US")
        city_uk = _feature("New York", 53.07, -0.14, "place", "England", "United Kingdom", "GB")

        def fake_get(url, params, provider):
            if params["q"] == "New York, USA":
                return 200, {"features": [business]}
            return 200, {"features": [city_uk, city_us]}

        with mock.patch.object(geocoding, "get_json", side_effect=fake_get):
            places = geocoding.search("New York, USA")
        self.assertEqual((places[0].lat, places[0].lon), (40.71, -74.0))
        self.assertEqual(places[1].label, "CAF USA, Incorporated, New York, USA")  # original hit kept as fallback

    def test_plain_query_uses_photon_order(self):
        denver = _feature("Denver", 39.74, -104.99, "place", "Colorado", "United States", "US")
        with mock.patch.object(geocoding, "get_json", return_value=(200, {"features": [denver]})) as m:
            places = geocoding.search("Denver")
        self.assertEqual(places[0].label, "Denver, Colorado, USA")
        self.assertEqual(m.call_count, 1)

    def test_resolve_accepts_lat_lon_text(self):
        p = geocoding.resolve("19.9975, 73.7898", "origin")
        self.assertEqual((p.lat, p.lon), (19.9975, 73.7898))


def _om_result(name, admin1, country, cc, lat, lon):
    return {"name": name, "admin1": admin1, "country": country, "country_code": cc,
            "latitude": lat, "longitude": lon}


class OpenMeteoFallbackTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _fake(self, url, params, provider):
        if "photon" in url:
            raise ProviderError("Geocoder is unreachable: ConnectionError")
        self.assertEqual(params["name"], "Salina")  # only the part before the comma
        return 200, {"results": [
            _om_result("Salinas", "California", "United States", "US", 36.68, -121.66),
            _om_result("Salina", "Kansas", "United States", "US", 38.84, -97.61),
        ]}

    def test_falls_back_and_matches_us_state_code(self):
        with mock.patch.object(geocoding, "get_json", side_effect=self._fake):
            places = geocoding.search("Salina, KS")
        self.assertEqual(places[0].label, "Salina, Kansas, USA")
        self.assertTrue(cache.get(geocoding.PHOTON_DOWN_KEY))

    def test_skips_photon_while_marked_down(self):
        cache.set(geocoding.PHOTON_DOWN_KEY, True)
        with mock.patch.object(geocoding, "get_json", side_effect=self._fake) as m:
            geocoding.search("Salina")
        self.assertEqual(m.call_count, 1)  # straight to Open-Meteo
