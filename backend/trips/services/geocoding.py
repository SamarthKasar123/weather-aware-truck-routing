"""Geocoding: Photon (OpenStreetMap, free, no key) with Open-Meteo as fallback.

Photon's public server refuses connections from some cloud hosts (e.g. Render),
so when it is unreachable we fall back to Open-Meteo's geocoder, which covers
cities and towns worldwide (GeoNames) but not street addresses.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache

from .http import InputError, ProviderError, get_json

log = logging.getLogger(__name__)

_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
PHOTON_DOWN_KEY = "geo:photon-down"
PHOTON_DOWN_TTL_S = 10 * 60  # skip Photon for a while after it fails


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Hit:
    place: Place
    region: str  # lower-cased admin areas + country, for qualifier matching
    is_place: bool  # a city/town/region rather than a business or building


def _join_label(*parts: str | None) -> str:
    out: list[str] = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return ", ".join(out) or "Unnamed place"


_PLACE_KEYS = {"place", "boundary"}  # cities, towns, states... (vs. shops, offices)
_ALIASES = {
    "usa": "united states",
    "us": "united states",
    "u.s.": "united states",
    "u.s.a.": "united states",
    "america": "united states",
    "uk": "united kingdom",
    "uae": "united arab emirates",
}
_US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california",
    "co": "colorado", "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia",
    "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire",
    "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee",
    "tx": "texas", "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington",
    "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}


def _qualifiers(tail: str) -> list[str]:
    """"USA" -> "united states", "KS" -> "kansas", other text lower-cased."""
    out = []
    for t in tail.split(","):
        t = t.strip().lower()
        if t:
            out.append(_ALIASES.get(t) or _US_STATES.get(t) or t)
    return out


def _photon(query: str, limit: int) -> list[_Hit]:
    _, data = get_json(
        f"{settings.PHOTON_BASE_URL}/api/",
        {"q": query, "limit": limit, "lang": "en"},
        provider="Geocoder",
    )
    hits = []
    for f in data.get("features", []):
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f.get("properties", {})
        primary = p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
        country = "USA" if p.get("countrycode") == "US" else p.get("country")
        region = " ".join(str(p.get(k) or "") for k in ("city", "county", "state", "country", "countrycode"))
        hits.append(_Hit(
            Place(_join_label(primary, p.get("city"), p.get("state"), country), float(lat), float(lon)),
            region.lower(),
            p.get("osm_key") in _PLACE_KEYS,
        ))
    return hits


def _open_meteo(name: str, limit: int) -> list[_Hit]:
    _, data = get_json(
        settings.OPEN_METEO_GEOCODING_URL,
        {"name": name, "count": limit, "language": "en", "format": "json"},
        provider="Geocoder",
    )
    hits = []
    for r in data.get("results", []) or []:
        country = "USA" if r.get("country_code") == "US" else r.get("country")
        region = " ".join(str(r.get(k) or "") for k in ("admin1", "admin2", "country", "country_code"))
        hits.append(_Hit(
            Place(_join_label(r.get("name"), r.get("admin1"), country), float(r["latitude"]), float(r["longitude"])),
            region.lower(),
            True,
        ))
    return hits


def _search_photon(query: str, limit: int) -> list[_Hit]:
    """Photon matches every word against names, so "New York, USA" ranks a company
    called "CAF USA" above the city. When a comma query's top hit isn't a real
    place, search the part before the comma and keep the places whose
    state/country matches the rest."""
    hits = _photon(query, limit)
    head, _, tail = query.partition(",")
    quals = _qualifiers(tail)
    if quals and head.strip() and (not hits or not hits[0].is_place):
        matched = [h for h in _photon(head.strip(), 10) if h.is_place and all(q in h.region for q in quals)]
        hits = matched + hits
    return hits


def _search_open_meteo(query: str, limit: int) -> list[_Hit]:
    """Open-Meteo only matches bare place names: search the part before the first
    comma and prefer results whose region matches the rest."""
    head, _, tail = query.partition(",")
    hits = _open_meteo(head.strip(), max(limit, 10))
    quals = _qualifiers(tail)
    matched = [h for h in hits if all(q in h.region for q in quals)] if quals else hits
    return matched or hits


def search(query: str, limit: int = 5) -> list[Place]:
    query = query.strip()
    if len(query) < 2:
        return []
    key = f"geo:{limit}:{hashlib.sha1(query.lower().encode()).hexdigest()}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    hits: list[_Hit] | None = None
    if not cache.get(PHOTON_DOWN_KEY):
        try:
            hits = _search_photon(query, limit)
        except ProviderError as exc:
            log.warning("Photon unavailable, using Open-Meteo geocoding: %s", exc)
            cache.set(PHOTON_DOWN_KEY, True, PHOTON_DOWN_TTL_S)
    if hits is None:
        hits = _search_open_meteo(query, limit)

    places: list[Place] = []
    for h in hits:
        if h.place.label not in {x.label for x in places}:
            places.append(h.place)
    places = places[:limit]
    cache.set(key, places, 24 * 3600)
    return places


def resolve(value: str | dict, field: str) -> Place:
    """Turn user input (selected suggestion, "lat,lon", or free text) into a Place."""
    if isinstance(value, dict):
        return Place(str(value.get("label") or f"{value['lat']:.4f}, {value['lon']:.4f}"),
                     float(value["lat"]), float(value["lon"]))
    m = _LATLON_RE.match(value)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return Place(f"{lat:.4f}, {lon:.4f}", lat, lon)
    results = search(value, limit=1)
    if not results:
        raise InputError(f"Could not find a location for {field}: “{value}”.")
    return results[0]
