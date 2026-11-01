import L from "leaflet";
import { useEffect, useMemo } from "react";
import { CircleMarker, MapContainer, Marker, Pane, TileLayer, Tooltip, useMap } from "react-leaflet";
import { formatTime } from "../lib/format";
import { positionAt } from "../lib/route";
import type { Checkpoint, Heatmap, HeatmapMetric, Plan } from "../types";
import CheckpointsLayer from "./CheckpointsLayer";
import HeatmapLayer from "./HeatmapLayer";
import RoutesLayer from "./RoutesLayer";

interface Props {
  plan: Plan | null;
  heatmap: Heatmap | null;
  showHeatmap: boolean;
  metric: HeatmapMetric;
  hour: number;
  selectedId: string;
  focus: Checkpoint | null;
  onSelect: (id: string) => void;
  onCheckpointClick: (routeId: string, cp: Checkpoint) => void;
  onHeatmapHover: (v: number | null) => void;
}

const renderer = L.canvas({ tolerance: 6 });
const endpointIcon = (kind: "start" | "end") =>
  L.divIcon({ className: "endpoint-icon", iconSize: [0, 0], html: `<div class="endpoint ${kind}"></div>` });
const truckIcon = L.divIcon({ className: "truck-icon", iconSize: [0, 0], html: '<div class="truck">🚚</div>' });

function FitToPlan({ plan }: { plan: Plan | null }) {
  const map = useMap();
  useEffect(() => {
    if (!plan) return;
    const bounds = L.latLngBounds(plan.routes.flatMap((r) => r.geometry));
    map.fitBounds(bounds, { padding: [48, 48] });
  }, [map, plan]);
  return null;
}

function FocusCheckpoint({ focus }: { focus: Checkpoint | null }) {
  const map = useMap();
  useEffect(() => {
    if (focus) map.setView([focus.lat, focus.lon], Math.max(map.getZoom(), 8), { animate: true });
  }, [map, focus]);
  return null;
}

/** Where each truck would be at the slider time. */
function TruckPositions({ plan, hour, selectedId }: { plan: Plan; hour: number; selectedId: string }) {
  const offset = hour * 3600;
  const time = new Date(new Date(plan.departure).getTime() + offset * 1000);
  return (
    <>
      {plan.routes.map((r) => {
        const pos = positionAt(r, offset);
        const arrived = offset >= r.duration_s;
        const label = `Route ${r.id} at ${formatTime(time)}${arrived ? " (arrived)" : ""}`;
        return r.id === selectedId ? (
          <Marker key={r.id} position={pos} icon={truckIcon} zIndexOffset={2000}>
            <Tooltip direction="right" offset={[12, 0]}>
              {label}
            </Tooltip>
          </Marker>
        ) : (
          <CircleMarker
            key={`${r.id}-${selectedId}`}
            center={pos}
            radius={5}
            pathOptions={{ color: "#0f172a", weight: 2, fillColor: "#fff", fillOpacity: 1 }}
          >
            <Tooltip direction="right">{label}</Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

export default function MapView(props: Props) {
  const { plan, heatmap, showHeatmap, metric, hour, selectedId } = props;
  const endpoints = useMemo(
    () =>
      plan && {
        start: [plan.origin.lat, plan.origin.lon] as [number, number],
        end: [plan.destination.lat, plan.destination.lon] as [number, number],
      },
    [plan],
  );

  return (
    <MapContainer
      className="map"
      center={[39.5, -98.35]}
      zoom={4}
      minZoom={3}
      renderer={renderer}
      preferCanvas
      zoomSnap={0.5}
      worldCopyJump
    >
      <TileLayer
        attribution='Tiles &copy; <a href="https://www.esri.com">Esri</a>, HERE, Garmin, &copy; OpenStreetMap contributors · Weather: <a href="https://open-meteo.com">Open-Meteo</a>'
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        maxZoom={16}
      />
      {/* Place-name labels above the heatmap (350) but below routes (400). */}
      <Pane name="labels" style={{ zIndex: 360, pointerEvents: "none" }}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
        />
      </Pane>
      {heatmap && showHeatmap && (
        <HeatmapLayer heatmap={heatmap} metric={metric} hour={hour} onHover={props.onHeatmapHover} />
      )}
      {plan && (
        <>
          <RoutesLayer plan={plan} selectedId={selectedId} onSelect={props.onSelect} />
          <CheckpointsLayer plan={plan} selectedId={selectedId} onCheckpointClick={props.onCheckpointClick} />
          <TruckPositions plan={plan} hour={hour} selectedId={selectedId} />
        </>
      )}
      {plan && endpoints && (
        <>
          <Marker position={endpoints.start} icon={endpointIcon("start")}>
            <Tooltip direction="top">Origin: {plan.origin.label}</Tooltip>
          </Marker>
          <Marker position={endpoints.end} icon={endpointIcon("end")}>
            <Tooltip direction="top">Destination: {plan.destination.label}</Tooltip>
          </Marker>
        </>
      )}
      <FitToPlan plan={plan} />
      <FocusCheckpoint focus={props.focus} />
    </MapContainer>
  );
}
