import { RISK_LEVELS } from "../lib/risk";
import type { RiskLevel } from "../types";

/** Stacked bar of route miles per risk level. */
export default function RiskBar({ miles }: { miles: Record<RiskLevel, number> }) {
  const total = RISK_LEVELS.reduce((s, r) => s + miles[r.level], 0) || 1;
  return (
    <div className="risk-bar-wrap">
      <div className="risk-bar" role="img" aria-label="Miles by risk level">
        {RISK_LEVELS.map(({ level, label, color }) =>
          miles[level] > 0 ? (
            <span
              key={level}
              style={{ width: `${(miles[level] / total) * 100}%`, background: color }}
              title={`${label}: ${miles[level].toFixed(1)} mi`}
            />
          ) : null,
        )}
      </div>
      <div className="risk-bar-legend">
        {RISK_LEVELS.filter(({ level }) => miles[level] > 0).map(({ level, label, color }) => (
          <span key={level}>
            <i style={{ background: color }} />
            {label} {Math.round(miles[level])} mi
          </span>
        ))}
      </div>
    </div>
  );
}
