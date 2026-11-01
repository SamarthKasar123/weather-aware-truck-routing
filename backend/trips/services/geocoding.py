"""Geocoding via Photon (OpenStreetMap data, free, no key)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache

from .http import InputError, get_json

_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def to_dict(self) -> dict:
        return asdict(self)


def _label(props: dict) -> str:
    primary = props.get("name") or " ".join(
        p for p in (props.get("housenumber"), props.get("street")) if p
    )
    country = "USA" if props.get("countrycode") == "US" else props.get("country")
    parts: list[str] = []
    for p in (primary, props.get("city"), props.get("state"), country):
        if p and p not in parts:
            parts.append(p)
    return ", ".join(parts) or "Unnamed place"


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


def _photon(query: str, limit: int) -> list[tuple[Place, dict]]:
    _, data = get_json(
        f"{settings.PHOTON_BASE_URL}/api/",
        {"q": query, "limit": limit, "lang": "en"},
        provider="Geocoder",
    )
    out = []
    for f in data.get("features", []):
        lon, lat = f["geometry"]["coordinates"][:2]
        props = f.get("properties", {})
        out.append((Place(_label(props), float(lat), float(lon)), props))
    return out


def _region_text(props: dict) -> str:
    return " ".join(
        str(props.get(k) or "") for k in ("city", "county", "state", "country", "countrycode")
    ).lower()


def search(query: str, limit: int = 5) -> list[Place]:
    """Place search with a fix for "City, Region" queries.

    Photon matches every word against names, so "New York, USA" ranks a company
    called "CAF USA" above the city. When a comma query's top hit isn't a real
    place, search the part before the comma and keep the places whose
    state/country matches the rest.
    """
    query = query.strip()
    if len(query) < 2:
        return []
    key = f"geo:{limit}:{hashlib.sha1(query.lower().encode()).hexdigest()}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = _photon(query, limit)
    head, _, tail = query.partition(",")
    qualifiers = [_ALIASES.get(t.strip().lower(), t.strip().lower()) for t in tail.split(",") if t.strip()]
    if qualifiers and head.strip() and (not results or results[0][1].get("osm_key") not in _PLACE_KEYS):
        matched = [
            (p, props)
            for p, props in _photon(head.strip(), 10)
            if props.get("osm_key") in _PLACE_KEYS and all(q in _region_text(props) for q in qualifiers)
        ]
        results = matched + results

    places: list[Place] = []
    for p, _ in results:
        if p.label not in {x.label for x in places}:
            places.append(p)
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
