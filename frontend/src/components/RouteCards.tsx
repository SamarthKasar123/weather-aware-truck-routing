import { formatDuration, formatMiles, formatTime } from "../lib/format";
import { riskColor, riskLabel } from "../lib/risk";
import type { Plan } from "../types";
import RiskBar from "./RiskBar";

interface Props {
  plan: Plan;
  selectedId: string;
  onSelect: (id: string) => void;
}

export default function RouteCards({ plan, selectedId, onSelect }: Props) {
  const ranked = [...plan.routes].sort((a, b) => a.rank - b.rank);
  return (
    <div className="route-cards">
      {ranked.map((r) => (
        <button
          key={r.id}
          type="button"
          className={`route-card${r.id === selectedId ? " selected" : ""}${r.recommended ? " recommended" : ""}`}
          onClick={() => onSelect(r.id)}
          aria-pressed={r.id === selectedId}
        >
          <div className="route-card-head">
            <span className="route-badge">{r.id}</span>
            <span className="route-name">{r.summary ? `via ${r.summary}` : `Route ${r.id}`}</span>
            {r.recommended ? <span className="tag rec">★ Recommended</span> : <span className="tag">#{r.rank}</span>}
          </div>
          <div className="route-stats">
            <div>
              <b>{formatDuration(r.duration_s)}</b>
              <small>drive time</small>
            </div>
            <div>
              <b>{formatMiles(r.distance_mi)}</b>
              <small>distance</small>
            </div>
            <div>
              <b>{formatTime(r.arrival)}</b>
              <small>arrival</small>
            </div>
            <div>
              <b style={{ color: riskColor(r.score.max_level) }}>{riskLabel(r.score.max_level)}</b>
              <small>worst · avg {r.score.average_risk.toFixed(2)}</small>
            </div>
          </div>
          <RiskBar miles={r.score.miles_by_level} />
          {r.why_not && <div className="why-not">Not chosen: {r.why_not}</div>}
        </button>
      ))}
    </div>
  );
}
