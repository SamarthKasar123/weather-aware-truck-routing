/** Shapes returned by the Django API (see backend/trips/services/planner.py). */

export type LatLng = [number, number];

/** 0 Low · 1 Moderate · 2 High · 3 Severe · 4 No Travel */
export type RiskLevel = 0 | 1 | 2 | 3 | 4;

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface Checkpoint {
  index: number;
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  eta_offset_s: number;
  weather: {
    temp_f: number;
    wind_mph: number;
    gust_mph: number;
    rain_in_hr: number;
    snow_in_hr: number;
    weather_code: number;
  };
  risk: { level: RiskLevel; wind: RiskLevel; rain: RiskLevel; snow: RiskLevel };
  reasons: string[];
}

export interface RouteOption {
  id: string;
  summary: string;
  distance_mi: number;
  duration_s: number;
  arrival: string;
  rank: number;
  recommended: boolean;
  why_not: string | null;
  score: {
    miles_by_level: Record<RiskLevel, number>;
    average_risk: number;
    max_level: RiskLevel;
  };
  geometry: LatLng[];
  vertex_times_s: number[];
  risk_segments: { level: RiskLevel; coords: LatLng[] }[];
  checkpoints: Checkpoint[];
}

export interface Plan {
  origin: Place;
  destination: Place;
  departure: string;
  load_lb: number;
  interval_mi: number;
  routes: RouteOption[];
  recommendation: { route_id: string; reason: string; ranking: string[] };
  corridor: LatLng[][];
  warnings: string[];
}

export type HeatmapMetric = "risk" | "wind" | "rain" | "snow";

export interface Heatmap {
  start: string;
  hours: number;
  bounds: [LatLng, LatLng];
  rows: number;
  cols: number;
  /** Row-major indices (north row first) of populated grid cells. */
  cells: number[];
  /** frames[metric][hour][i] is the value for cells[i]. */
  frames: Record<HeatmapMetric, number[][]>;
}

export interface PlanRequest {
  origin: Place | string;
  destination: Place | string;
  departure_time: string;
  load_weight_lb: number;
  interval_mi: 10 | 25 | 50;
}
