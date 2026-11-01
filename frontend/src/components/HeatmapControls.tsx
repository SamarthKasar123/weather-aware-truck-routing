import { useEffect, useState } from "react";
import { formatTimeFull } from "../lib/format";
import { METRIC_LABELS, RAMPS, RISK_LEVELS, rampGradientCss, riskLabel } from "../lib/risk";
import type { Heatmap, HeatmapMetric, RiskLevel } from "../types";

interface Props {
  departure: string;
  heatmap: Heatmap | null;
  loading: boolean;
  error: string | null;
  hour: number;
  onHour: React.Dispatch<React.SetStateAction<number>>;
  metric: HeatmapMetric;
  onMetric: (m: HeatmapMetric) => void;
  show: boolean;
  onShow: (v: boolean) => void;
  hoverValue: number | null;
  arrivalHour: number;
}

const MAX_HOUR = 48;
const PLAY_STEP_MS = 450;
const METRICS: HeatmapMetric[] = ["risk", "wind", "rain", "snow"];

function formatValue(metric: HeatmapMetric, v: number): string {
  if (metric === "risk") return riskLabel(v as RiskLevel);
  if (metric === "wind") return `${v.toFixed(0)} mph`;
  return `${v.toFixed(2)} in/hr`;
}

export default function HeatmapControls(p: Props) {
  const [playing, setPlaying] = useState(false);
  const { onHour } = p;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => onHour((h) => (h >= MAX_HOUR ? 0 : h + 1)), PLAY_STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, onHour]);

  const time = new Date(new Date(p.departure).getTime() + p.hour * 3600_000);
  const ramp = RAMPS[p.metric];
  const disabled = !p.heatmap;

  return (
    <div className="heatmap-controls">
      <div className="hc-top">
        <label className="toggle">
          <input type="checkbox" checked={p.show} onChange={(e) => p.onShow(e.target.checked)} />
          Weather heatmap
        </label>
        <div className="segmented small" role="radiogroup" aria-label="Heatmap layer">
          {METRICS.map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={p.metric === m}
              className={p.metric === m ? "on" : ""}
              onClick={() => p.onMetric(m)}
            >
              {METRIC_LABELS[m]}
            </button>
          ))}
        </div>
        <div className="hc-status">
          {p.loading && <span className="spinner small" aria-label="Loading forecast" />}
          {p.error && <span className="hc-error">{p.error}</span>}
          {!p.loading && !p.error && p.hoverValue !== null && p.show && (
            <span className="hover-readout">
              {METRIC_LABELS[p.metric]}: <b>{formatValue(p.metric, p.hoverValue)}</b>
            </span>
          )}
        </div>
      </div>

      <div className="hc-slider">
        <button
          type="button"
          className="play"
          onClick={() => setPlaying((v) => !v)}
          disabled={disabled}
          aria-label={playing ? "Pause" : "Play forecast"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="slider-col">
          <div className="slider-time">
            <span>
              <b>+{p.hour}h</b> · {formatTimeFull(time)}
            </span>
            <span className="arrival-label">Arrives +{p.arrivalHour.toFixed(1)}h</span>
          </div>
          <div className="slider-track">
            <input
              type="range"
              min={0}
              max={MAX_HOUR}
              step={1}
              value={p.hour}
              onChange={(e) => {
                setPlaying(false);
                p.onHour(Number(e.target.value));
              }}
              aria-label="Forecast hour after departure"
            />
            {p.arrivalHour <= MAX_HOUR && (
              <span
                className="arrival-mark"
                style={{ left: `${(p.arrivalHour / MAX_HOUR) * 100}%` }}
                title="Selected route arrival"
              />
            )}
          </div>
          <div className="slider-ticks">
            {[0, 6, 12, 18, 24, 30, 36, 42, 48].map((h) => (
              <span key={h}>{h}h</span>
            ))}
          </div>
        </div>
      </div>

      <div className="hc-legend">
        {p.metric === "risk" ? (
          RISK_LEVELS.map((r) => (
            <span key={r.level} className="legend-chip">
              <i style={{ background: r.color }} />
              {r.label}
            </span>
          ))
        ) : (
          <div className="legend-ramp">
            <div className="ramp" style={{ background: rampGradientCss(p.metric) }} />
            <div className="ramp-ticks">
              {ramp.ticks.map((t) => {
                const min = ramp.stops[0].at;
                const max = ramp.stops[ramp.stops.length - 1].at;
                return (
                  <span key={t} style={{ left: `${((t - min) / (max - min)) * 100}%` }}>
                    {t}
                  </span>
                );
              })}
              <em>{ramp.unit}</em>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
