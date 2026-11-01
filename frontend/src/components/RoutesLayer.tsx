import L from "leaflet";
import { memo, useMemo } from "react";
import { Marker, Polyline } from "react-leaflet";
import { formatDuration } from "../lib/format";
import { riskColor } from "../lib/risk";
import type { LatLng, Plan, RouteOption } from "../types";

interface Props {
  plan: Plan;
  selectedId: string;
  onSelect: (id: string) => void;
}

const LABEL_CANDIDATES = 40;
const SAMPLES_PER_ROUTE = 120;

function every<T>(arr: T[], n: number): T[] {
  const step = Math.max(1, Math.floor(arr.length / n));
  return arr.filter((_, i) => i % step === 0);
}

/** Squared equirectangular distance in degrees; enough for comparing nearness. */
function minDist2(p: LatLng, pts: LatLng[]): number {
  const k = Math.cos((p[0] * Math.PI) / 180);
  let best = Infinity;
  for (const q of pts) {
    const dy = p[0] - q[0];
    const dx = (p[1] - q[1]) * k;
    best = Math.min(best, dx * dx + dy * dy);
  }
  return best;
}

/**
 * Put each route's label where that route is farthest from the other routes
 * (and from labels already placed), so shared stretches don't stack labels.
 */
function placeLabels(routes: RouteOption[]): LatLng[] {
  const placed: LatLng[] = [];
  return routes.map((r) => {
    const others = routes.filter((o) => o !== r).flatMap((o) => every(o.geometry, SAMPLES_PER_ROUTE));
    let best = r.geometry[Math.floor(r.geometry.length / 2)];
    let bestScore = -1;
    for (let k = 0; k <= LABEL_CANDIDATES; k++) {
      const p = r.geometry[Math.floor((r.geometry.length - 1) * (0.2 + (0.6 * k) / LABEL_CANDIDATES))];
      const score = Math.min(minDist2(p, others), placed.length ? 2 * minDist2(p, placed) : Infinity);
      if (score > bestScore) {
        best = p;
        bestScore = score;
      }
    }
    placed.push(best);
    return best;
  });
}

function labelIcon(route: RouteOption, selected: boolean) {
  const cls = ["route-label", selected && "selected", route.recommended && "recommended"]
    .filter(Boolean)
    .join(" ");
  return L.divIcon({
    className: "route-label-icon",
    iconSize: [0, 0],
    html: `<div class="${cls}"><b>${route.id}</b><span>${formatDuration(route.duration_s)} · ${Math.round(
      route.distance_mi,
    )} mi</span>${route.recommended ? '<i title="Recommended">★</i>' : ""}</div>`,
  });
}

/** Unselected routes in grey; the selected route coloured by risk along its length. */
function RoutesLayer({ plan, selectedId, onSelect }: Props) {
  const selected = plan.routes.find((r) => r.id === selectedId) ?? plan.routes[0];
  const others = plan.routes.filter((r) => r !== selected);

  const labels = useMemo(() => {
    const positions = placeLabels(plan.routes);
    return plan.routes.map((route, i) => ({ route, at: positions[i] }));
  }, [plan]);

  // Canvas draws layers in insertion order, so keys include the selection: changing it
  // remounts everything in a fixed order and the selected route always ends up on top.
  return (
    <>
      {others.map((r) => (
        <Polyline
          key={`other-${r.id}-${selected.id}`}
          positions={r.geometry}
          pathOptions={{ color: "#475569", weight: 5, opacity: 0.5, lineCap: "round" }}
          eventHandlers={{ click: () => onSelect(r.id) }}
        />
      ))}
      <Polyline
        key={`casing-${selected.id}`}
        positions={selected.geometry}
        pathOptions={{ color: "#0f172a", weight: 9, opacity: 0.85, lineCap: "round" }}
        interactive={false}
      />
      {selected.risk_segments.map((seg, i) => (
        <Polyline
          key={`seg-${selected.id}-${i}`}
          positions={seg.coords}
          pathOptions={{ color: riskColor(seg.level), weight: 5, opacity: 1, lineCap: "round" }}
          interactive={false}
        />
      ))}
      {labels.map(({ route, at }) => (
        <Marker
          key={`label-${route.id}-${selected.id}`}
          position={at}
          icon={labelIcon(route, route.id === selected.id)}
          zIndexOffset={route.id === selected.id ? 1000 : 0}
          eventHandlers={{ click: () => onSelect(route.id) }}
        />
      ))}
    </>
  );
}

export default memo(RoutesLayer);
