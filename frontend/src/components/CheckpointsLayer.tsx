import { memo } from "react";
import { CircleMarker, Tooltip } from "react-leaflet";
import { formatTime, weatherText } from "../lib/format";
import { riskColor, riskLabel } from "../lib/risk";
import type { Checkpoint, Plan } from "../types";

interface Props {
  plan: Plan;
  selectedId: string;
  onCheckpointClick: (routeId: string, cp: Checkpoint) => void;
}

function CheckpointTooltip({ routeId, cp }: { routeId: string; cp: Checkpoint }) {
  const w = cp.weather;
  return (
    <div className="cp-tooltip">
      <div className="cp-tooltip-head">
        <span>
          Route {routeId} · Mile {Math.round(cp.mile)}
        </span>
        <span className="risk-chip" style={{ background: riskColor(cp.risk.level) }}>
          {riskLabel(cp.risk.level)}
        </span>
      </div>
      <div>ETA {formatTime(cp.eta)}</div>
      <div>
        {weatherText(w.weather_code)}, {Math.round(w.temp_f)}°F
      </div>
      <div>
        Wind {w.wind_mph.toFixed(0)} mph (gust {w.gust_mph.toFixed(0)}) · Rain {w.rain_in_hr.toFixed(2)} ·
        Snow {w.snow_in_hr.toFixed(2)} in/hr
      </div>
      {cp.reasons.map((r) => (
        <div key={r} className="cp-reason">
          {r}
        </div>
      ))}
    </div>
  );
}

/** Weather checkpoints for every route; the selected route's are larger and on top. */
function CheckpointsLayer({ plan, selectedId, onCheckpointClick }: Props) {
  const ordered = [...plan.routes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId));
  return (
    <>
      {ordered.map((route) => {
        const selected = route.id === selectedId;
        return route.checkpoints.map((cp) => (
          <CircleMarker
            key={`${route.id}-${cp.index}-${selectedId}`}
            center={[cp.lat, cp.lon]}
            radius={selected ? 6 : 3.5}
            pathOptions={{
              color: selected ? "#fff" : "#334155",
              weight: selected ? 2 : 1,
              fillColor: riskColor(cp.risk.level),
              fillOpacity: selected ? 1 : 0.75,
            }}
            eventHandlers={{ click: () => onCheckpointClick(route.id, cp) }}
          >
            <Tooltip direction="top" offset={[0, -6]} opacity={1}>
              <CheckpointTooltip routeId={route.id} cp={cp} />
            </Tooltip>
          </CircleMarker>
        ));
      })}
    </>
  );
}

export default memo(CheckpointsLayer);
