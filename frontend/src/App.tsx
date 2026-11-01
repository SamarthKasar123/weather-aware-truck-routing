import { useCallback, useRef, useState } from "react";
import CheckpointTable from "./components/CheckpointTable";
import HeatmapControls from "./components/HeatmapControls";
import MapView from "./components/MapView";
import RouteCards from "./components/RouteCards";
import TripForm from "./components/TripForm";
import { fetchHeatmap, planTrip } from "./lib/api";
import { formatTimeFull } from "./lib/format";
import type { Checkpoint, Heatmap, HeatmapMetric, Plan, PlanRequest } from "./types";

const MAX_HOUR = 48;

export default function App() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState("A");
  const [focus, setFocus] = useState<Checkpoint | null>(null);

  const [heatmap, setHeatmap] = useState<Heatmap | null>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [metric, setMetric] = useState<HeatmapMetric>("risk");
  const [hour, setHour] = useState(0);
  const [hoverValue, setHoverValue] = useState<number | null>(null);

  const inflight = useRef<AbortController | null>(null);

  const submit = useCallback(async (req: PlanRequest) => {
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    setLoading(true);
    setError(null);
    setHeatmap(null);
    setHeatmapError(null);
    try {
      const result = await planTrip(req, ctrl.signal);
      setPlan(result);
      setSelectedId(result.recommendation.route_id);
      setFocus(null);
      setHour(0);
      setLoading(false);

      // The heatmap loads second so routes appear as soon as they're ready.
      setHeatmapLoading(true);
      try {
        setHeatmap(await fetchHeatmap(result.corridor, result.departure, result.load_lb, ctrl.signal));
      } catch (err) {
        if ((err as Error).name !== "AbortError") setHeatmapError((err as Error).message);
      } finally {
        if (!ctrl.signal.aborted) setHeatmapLoading(false);
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError((err as Error).message);
      setLoading(false);
    }
  }, []);

  const selectRoute = useCallback((id: string) => {
    setSelectedId(id);
    setFocus(null);
  }, []);

  const focusCheckpoint = useCallback((routeId: string, cp: Checkpoint) => {
    setSelectedId(routeId);
    setFocus(cp);
    // Jump the forecast slider to when the truck reaches this checkpoint.
    setHour(Math.min(MAX_HOUR, Math.max(0, Math.round(cp.eta_offset_s / 3600))));
  }, []);

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? plan?.routes[0];
  const recommended = plan?.routes.find((r) => r.recommended);

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <span className="logo">🚚</span>
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p>Safest route by weather, load and time</p>
          </div>
        </header>

        <TripForm loading={loading} onSubmit={submit} />
        {error && <div className="alert error">{error}</div>}

        {plan && recommended && selected && (
          <section className="results">
            <div className="recommendation">
              <div className="rec-title">
                <span className="route-badge">{recommended.id}</span>
                Recommended: Route {recommended.id}
              </div>
              <p>{plan.recommendation.reason}</p>
              <small>
                Departing {formatTimeFull(plan.departure)} · {plan.load_lb.toLocaleString()} lb · weather every{" "}
                {plan.interval_mi} mi
              </small>
            </div>
            {plan.warnings.map((w) => (
              <div key={w} className="alert warn">
                {w}
              </div>
            ))}

            <h2>Route options</h2>
            <RouteCards plan={plan} selectedId={selected.id} onSelect={selectRoute} />

            <h2>
              Checkpoints · Route {selected.id} <small>({selected.checkpoints.length})</small>
            </h2>
            <CheckpointTable
              route={selected}
              focusIndex={focus && selected.checkpoints.includes(focus) ? focus.index : null}
              onFocus={(cp) => focusCheckpoint(selected.id, cp)}
            />
            <p className="footnote">
              Wind in mph (g = gusts). Rain and snow in in/hr. Times in your local time zone. Risk is the worst of
              wind (load-adjusted), rain and snow at the truck's ETA.
            </p>
          </section>
        )}
      </aside>

      <main className="map-wrap">
        <MapView
          plan={plan}
          heatmap={heatmap}
          showHeatmap={showHeatmap}
          metric={metric}
          hour={hour}
          selectedId={selected?.id ?? "A"}
          focus={focus}
          onSelect={selectRoute}
          onCheckpointClick={focusCheckpoint}
          onHeatmapHover={setHoverValue}
        />
        {plan && selected && (
          <HeatmapControls
            departure={plan.departure}
            heatmap={heatmap}
            loading={heatmapLoading}
            error={heatmapError}
            hour={hour}
            onHour={setHour}
            metric={metric}
            onMetric={setMetric}
            show={showHeatmap}
            onShow={setShowHeatmap}
            hoverValue={hoverValue}
            arrivalHour={selected.duration_s / 3600}
          />
        )}
        {!plan && !loading && (
          <div className="map-hint">
            <b>Plan a trip</b>
            <span>
              Enter an origin, destination, departure time and load. You'll get 3 routes scored by forecast weather
              at the truck's ETA at each checkpoint.
            </span>
          </div>
        )}
        {loading && (
          <div className="map-loading">
            <span className="spinner" />
            Finding routes and forecasts…
          </div>
        )}
      </main>
    </div>
  );
}
