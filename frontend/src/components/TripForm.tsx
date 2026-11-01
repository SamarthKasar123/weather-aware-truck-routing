import { useState } from "react";
import { toLocalInputValue } from "../lib/format";
import type { Place, PlanRequest } from "../types";
import PlaceInput from "./PlaceInput";

interface Props {
  loading: boolean;
  onSubmit: (req: PlanRequest) => void;
}

const INTERVALS = [10, 25, 50] as const;
const MAX_DAYS_AHEAD = 7;

function defaultDeparture(): string {
  const d = new Date();
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 15) * 15, 0, 0);
  return toLocalInputValue(d);
}

export default function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | string>("");
  const [destination, setDestination] = useState<Place | string>("");
  const [departure, setDeparture] = useState(defaultDeparture);
  const [load, setLoad] = useState("35000");
  const [interval, setInterval] = useState<(typeof INTERVALS)[number]>(25);
  const [error, setError] = useState<string | null>(null);

  const now = new Date();
  const maxDeparture = new Date(now.getTime() + MAX_DAYS_AHEAD * 86400_000);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const dep = new Date(departure);
    const loadLb = Number(load);
    if (Number.isNaN(dep.getTime())) return setError("Enter a valid departure date and time.");
    if (dep.getTime() < Date.now() - 3600_000) return setError("Departure time is in the past.");
    if (dep > maxDeparture) return setError(`Departure must be within ${MAX_DAYS_AHEAD} days (forecast range).`);
    if (!Number.isFinite(loadLb) || loadLb <= 0 || loadLb > 200_000)
      return setError("Load weight must be between 1 and 200,000 lb.");
    setError(null);
    onSubmit({
      origin,
      destination,
      departure_time: dep.toISOString(),
      load_weight_lb: loadLb,
      interval_mi: interval,
    });
  };

  const fillExample = () => {
    setOrigin({ label: "Chicago, Illinois, USA", lat: 41.8755616, lon: -87.6244212 });
    setDestination({ label: "Denver, Colorado, USA", lat: 39.7392364, lon: -104.984862 });
  };

  return (
    <form className="trip-form" onSubmit={submit} noValidate>
      <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="City, address, or lat,lon" />
      <button
        type="button"
        className="swap"
        title="Swap origin and destination"
        aria-label="Swap origin and destination"
        onClick={() => {
          setOrigin(destination);
          setDestination(origin);
        }}
      >
        ⇅
      </button>
      <PlaceInput
        label="Destination"
        value={destination}
        onChange={setDestination}
        placeholder="City, address, or lat,lon"
      />
      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={toLocalInputValue(new Date(now.getTime() - 3600_000))}
            max={toLocalInputValue(maxDeparture)}
            onChange={(e) => setDeparture(e.target.value)}
            required
          />
        </div>
        <div className="field load-field">
          <label htmlFor="load">Load weight</label>
          <div className="suffix-input">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              min={1}
              max={200000}
              step={500}
              value={load}
              onChange={(e) => setLoad(e.target.value)}
              required
            />
            <span>lb</span>
          </div>
        </div>
      </div>
      <div className="field">
        <span className="label">Weather sample interval</span>
        <div className="segmented" role="radiogroup" aria-label="Weather sample interval">
          {INTERVALS.map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={interval === v}
              className={interval === v ? "on" : ""}
              onClick={() => setInterval(v)}
            >
              {v} mi
            </button>
          ))}
        </div>
      </div>
      {error && <div className="form-error">{error}</div>}
      <div className="form-actions">
        <button type="submit" className="primary" disabled={loading || !origin || !destination}>
          {loading ? "Planning…" : "Find safest route"}
        </button>
        <button type="button" className="link" onClick={fillExample}>
          Try Chicago → Denver
        </button>
      </div>
    </form>
  );
}
