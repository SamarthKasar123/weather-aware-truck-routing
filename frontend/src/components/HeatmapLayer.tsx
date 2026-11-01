import { useEffect, useMemo, useRef } from "react";
import { useMap, useMapEvents } from "react-leaflet";
import { canvasOverlay } from "../lib/canvasOverlay";
import { paintHeatmap, valueAt } from "../lib/heatmapRender";
import type { Heatmap, HeatmapMetric } from "../types";

const PANE = "heatmap";

interface Props {
  heatmap: Heatmap;
  metric: HeatmapMetric;
  hour: number;
  onHover: (value: number | null) => void;
}

/** Forecast heatmap: one canvas overlay, repainted in place when hour/metric change. */
export default function HeatmapLayer({ heatmap, metric, hour, onHover }: Props) {
  const map = useMap();
  const canvas = useMemo(() => document.createElement("canvas"), []);

  useEffect(() => {
    if (!map.getPane(PANE)) {
      const pane = map.createPane(PANE);
      pane.style.zIndex = "350"; // above tiles (200), below routes (400)
      pane.style.pointerEvents = "none";
    }
    const layer = canvasOverlay(canvas, heatmap.bounds, { pane: PANE, interactive: false });
    layer.addTo(map);
    return () => {
      layer.remove();
    };
  }, [map, canvas, heatmap]);

  useEffect(() => {
    paintHeatmap(canvas, heatmap, metric, hour);
  }, [canvas, heatmap, metric, hour]);

  // Mouse readout; refs keep the handler stable while hour/metric change.
  const latest = useRef({ heatmap, metric, hour });
  latest.current = { heatmap, metric, hour };
  useMapEvents({
    mousemove(e) {
      const { heatmap: hm, metric: m, hour: h } = latest.current;
      onHover(valueAt(hm, m, h, e.latlng.lat, e.latlng.lng));
    },
    mouseout() {
      onHover(null);
    },
  });

  return null;
}
