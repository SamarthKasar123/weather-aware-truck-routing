import type { HeatmapMetric, RiskLevel } from "../types";

export const RISK_LEVELS: { level: RiskLevel; label: string; color: string }[] = [
  { level: 0, label: "Low", color: "#16a34a" },
  { level: 1, label: "Moderate", color: "#eab308" },
  { level: 2, label: "High", color: "#f97316" },
  { level: 3, label: "Severe", color: "#dc2626" },
  { level: 4, label: "No Travel", color: "#7e22ce" },
];

export const riskLabel = (l: RiskLevel) => RISK_LEVELS[l].label;
export const riskColor = (l: RiskLevel) => RISK_LEVELS[l].color;

type RGBA = [number, number, number, number];
interface Stop {
  at: number;
  rgba: RGBA;
}

function hex(h: string, a: number): RGBA {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, a];
}

/**
 * Heatmap colour ramps. Stops for wind/rain/snow sit on the same thresholds as
 * the risk table, so a colour on the heatmap always means the same risk band.
 */
export const RAMPS: Record<HeatmapMetric, { stops: Stop[]; unit: string; ticks: number[] }> = {
  risk: {
    unit: "",
    ticks: [0, 1, 2, 3, 4],
    stops: RISK_LEVELS.map((r) => ({ at: r.level, rgba: hex(r.color, r.level === 0 ? 0.22 : 0.62) })),
  },
  wind: {
    unit: "mph",
    ticks: [0, 25, 35, 45, 55],
    stops: [
      { at: 0, rgba: hex("#38bdf8", 0.12) },
      { at: 15, rgba: hex("#22c55e", 0.3) },
      { at: 25, rgba: hex("#eab308", 0.55) },
      { at: 35, rgba: hex("#f97316", 0.62) },
      { at: 45, rgba: hex("#dc2626", 0.68) },
      { at: 55, rgba: hex("#7e22ce", 0.72) },
    ],
  },
  rain: {
    unit: "in/hr",
    ticks: [0, 0.1, 0.25, 0.5, 1],
    stops: [
      { at: 0, rgba: hex("#60a5fa", 0) },
      { at: 0.01, rgba: hex("#60a5fa", 0.25) },
      { at: 0.1, rgba: hex("#2563eb", 0.5) },
      { at: 0.25, rgba: hex("#f97316", 0.6) },
      { at: 0.5, rgba: hex("#dc2626", 0.68) },
      { at: 1.0, rgba: hex("#7e22ce", 0.72) },
    ],
  },
  snow: {
    unit: "in/hr",
    ticks: [0, 0.5, 1, 2, 3],
    stops: [
      { at: 0, rgba: hex("#a5f3fc", 0) },
      { at: 0.05, rgba: hex("#a5f3fc", 0.3) },
      { at: 0.5, rgba: hex("#22d3ee", 0.5) },
      { at: 1, rgba: hex("#f97316", 0.6) },
      { at: 2, rgba: hex("#dc2626", 0.68) },
      { at: 3, rgba: hex("#7e22ce", 0.72) },
    ],
  },
};

export const METRIC_LABELS: Record<HeatmapMetric, string> = {
  risk: "Risk",
  wind: "Wind",
  rain: "Rain",
  snow: "Snow",
};

/** Colour for a value on a ramp, alpha in 0-1. Linear between stops, clamped at ends. */
export function rampColor(stops: Stop[], v: number): RGBA {
  if (v <= stops[0].at) return stops[0].rgba;
  for (let i = 1; i < stops.length; i++) {
    const b = stops[i];
    if (v <= b.at) {
      const a = stops[i - 1];
      const t = (v - a.at) / (b.at - a.at);
      return [
        a.rgba[0] + (b.rgba[0] - a.rgba[0]) * t,
        a.rgba[1] + (b.rgba[1] - a.rgba[1]) * t,
        a.rgba[2] + (b.rgba[2] - a.rgba[2]) * t,
        a.rgba[3] + (b.rgba[3] - a.rgba[3]) * t,
      ];
    }
  }
  return stops[stops.length - 1].rgba;
}

export function rampGradientCss(metric: HeatmapMetric): string {
  const { stops } = RAMPS[metric];
  const min = stops[0].at;
  const max = stops[stops.length - 1].at;
  const parts = stops.map(({ at, rgba }) => {
    const pct = ((at - min) / (max - min)) * 100;
    return `rgba(${rgba[0]},${rgba[1]},${rgba[2]},${Math.max(rgba[3], 0.35)}) ${pct}%`;
  });
  return `linear-gradient(90deg, ${parts.join(", ")})`;
}
