import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import HeatmapRequestSerializer, PlanRequestSerializer
from .services import geocoding, heatmap, planner
from .services.geo import haversine_mi
from .services.http import InputError, ProviderError

log = logging.getLogger(__name__)


def _guarded(fn):
    """Map service-layer exceptions to clean JSON errors."""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except InputError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ProviderError as exc:
            log.warning("Provider failure: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
@_guarded
def geocode(request):
    """Place autocomplete: GET /api/geocode?q=Denver"""
    places = geocoding.search(request.query_params.get("q", ""))
    return Response({"results": [p.to_dict() for p in places]})


@api_view(["POST"])
@_guarded
def plan(request):
    """Plan a trip: 3 routes, weather checkpoints, risk, recommendation."""
    s = PlanRequestSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    req = planner.TripRequest(
        origin=geocoding.resolve(d["origin"], "origin"),
        destination=geocoding.resolve(d["destination"], "destination"),
        departure=d["departure_time"],
        load_lb=d["load_weight_lb"],
        interval_mi=int(d["interval_mi"]),
    )
    if haversine_mi((req.origin.lat, req.origin.lon), (req.destination.lat, req.destination.lon)) < 0.5:
        raise InputError("Origin and destination are the same place.")
    return Response(planner.plan_trip(req))


@api_view(["POST"])
@_guarded
def heatmap_view(request):
    """Hourly weather/risk grid along the trip corridor for the next 48 h."""
    s = HeatmapRequestSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    lines = [[(p[0], p[1]) for p in line] for line in d["corridor"]]
    return Response(heatmap.build_heatmap(lines, d["start_time"], d["load_weight_lb"]))
