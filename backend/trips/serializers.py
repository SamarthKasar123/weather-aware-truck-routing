"""Request validation for the public API."""
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

MAX_DEPARTURE_AHEAD = timedelta(days=7)  # forecasts beyond this are too unreliable
MAX_DEPARTURE_BEHIND = timedelta(hours=1)
INTERVAL_CHOICES = (10, 25, 50)


class PlaceField(serializers.Field):
    """Either free text / "lat,lon", or a selected suggestion {label, lat, lon}."""

    default_error_messages = {"invalid": "Enter a location or pick a suggestion."}

    def to_internal_value(self, data):
        if isinstance(data, str) and data.strip():
            return data.strip()
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                self.fail("invalid")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                self.fail("invalid")
            return {"label": str(data.get("label", ""))[:200], "lat": lat, "lon": lon}
        self.fail("invalid")

    def to_representation(self, value):
        return value


def _validate_departure(value):
    now = timezone.now()
    if value < now - MAX_DEPARTURE_BEHIND:
        raise serializers.ValidationError("Departure time is in the past.")
    if value > now + MAX_DEPARTURE_AHEAD:
        raise serializers.ValidationError("Departure must be within the next 7 days (forecast range).")
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure_time = serializers.DateTimeField(validators=[_validate_departure])
    load_weight_lb = serializers.FloatField(min_value=0, max_value=200_000)
    interval_mi = serializers.ChoiceField(choices=INTERVAL_CHOICES, default=25)


class LatLonList(serializers.ListField):
    child = serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2)


class HeatmapRequestSerializer(serializers.Serializer):
    corridor = serializers.ListField(child=LatLonList(min_length=2, max_length=2000), min_length=1, max_length=5)
    start_time = serializers.DateTimeField(validators=[_validate_departure])
    load_weight_lb = serializers.FloatField(min_value=0, max_value=200_000)
