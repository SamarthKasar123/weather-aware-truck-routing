import type { LatLng, RouteOption } from "../types";

/** Truck position `offsetS` seconds after departure (clamped to the route ends). */
export function positionAt(route: RouteOption, offsetS: number): LatLng {
  const t = route.vertex_times_s;
  const g = route.geometry;
  if (offsetS <= 0) return g[0];
  if (offsetS >= t[t.length - 1]) return g[g.length - 1];
  let lo = 0;
  let hi = t.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (t[mid] <= offsetS) lo = mid;
    else hi = mid;
  }
  const f = t[hi] === t[lo] ? 0 : (offsetS - t[lo]) / (t[hi] - t[lo]);
  return [g[lo][0] + (g[hi][0] - g[lo][0]) * f, g[lo][1] + (g[hi][1] - g[lo][1]) * f];
}
