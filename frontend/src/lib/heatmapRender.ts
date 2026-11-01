import type { Heatmap, HeatmapMetric } from "../types";
import { RAMPS, rampColor } from "./risk";

/** Canvas pixels per grid cell. Values are interpolated (not colours), then coloured. */
const UPSCALE = 6;
const LUT_SIZE = 256;

const lutCache = new Map<HeatmapMetric, { lut: Uint8ClampedArray; min: number; max: number }>();

function getLut(metric: HeatmapMetric) {
  let entry = lutCache.get(metric);
  if (!entry) {
    const { stops } = RAMPS[metric];
    const min = stops[0].at;
    const max = stops[stops.length - 1].at;
    const lut = new Uint8ClampedArray(LUT_SIZE * 4);
    for (let i = 0; i < LUT_SIZE; i++) {
      const [r, g, b, a] = rampColor(stops, min + ((max - min) * i) / (LUT_SIZE - 1));
      lut.set([r, g, b, a * 255], i * 4);
    }
    entry = { lut, min, max };
    lutCache.set(metric, entry);
  }
  return entry;
}

/** Dense row-major grid for one frame; NaN where the cell is outside the corridor. */
function denseFrame(hm: Heatmap, metric: HeatmapMetric, hour: number): Float32Array {
  const grid = new Float32Array(hm.rows * hm.cols).fill(NaN);
  const values = hm.frames[metric][hour];
  for (let i = 0; i < hm.cells.length; i++) grid[hm.cells[i]] = values[i];
  return grid;
}

/**
 * Paint one forecast hour into `canvas`. Bilinear interpolation between cell
 * centres gives smooth gradients; partially-covered pixels at the corridor edge
 * fade out instead of ending in hard squares. ~40k pixels: well under 5 ms.
 */
export function paintHeatmap(
  canvas: HTMLCanvasElement,
  hm: Heatmap,
  metric: HeatmapMetric,
  hour: number,
): void {
  const { rows, cols } = hm;
  const W = cols * UPSCALE;
  const H = rows * UPSCALE;
  if (canvas.width !== W) canvas.width = W;
  if (canvas.height !== H) canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const grid = denseFrame(hm, metric, hour);
  const { lut, min, max } = getLut(metric);
  const scale = (LUT_SIZE - 1) / (max - min);
  const img = ctx.createImageData(W, H);
  const out = img.data;

  for (let y = 0; y < H; y++) {
    const gy = (y + 0.5) / UPSCALE - 0.5;
    const j = Math.floor(gy);
    const fy = gy - j;
    const r0 = Math.max(0, j) * cols;
    const r1 = Math.min(rows - 1, j + 1) * cols;
    for (let x = 0; x < W; x++) {
      const gx = (x + 0.5) / UPSCALE - 0.5;
      const i = Math.floor(gx);
      const fx = gx - i;
      const c0 = Math.max(0, i);
      const c1 = Math.min(cols - 1, i + 1);

      // Weighted mean of the valid (non-NaN; `v === v`) corners. Inlined: hot loop.
      const v00 = grid[r0 + c0];
      const v01 = grid[r0 + c1];
      const v10 = grid[r1 + c0];
      const v11 = grid[r1 + c1];
      const w00 = (1 - fx) * (1 - fy);
      const w01 = fx * (1 - fy);
      const w10 = (1 - fx) * fy;
      const w11 = fx * fy;
      let sum = 0;
      let wsum = 0;
      if (v00 === v00) { sum += v00 * w00; wsum += w00; }
      if (v01 === v01) { sum += v01 * w01; wsum += w01; }
      if (v10 === v10) { sum += v10 * w10; wsum += w10; }
      if (v11 === v11) { sum += v11 * w11; wsum += w11; }
      if (wsum < 1e-4) continue;

      const v = sum / wsum;
      const li = Math.max(0, Math.min(LUT_SIZE - 1, Math.round((v - min) * scale))) * 4;
      const coverage = Math.min(1, wsum / 0.5);
      const p = (y * W + x) * 4;
      out[p] = lut[li];
      out[p + 1] = lut[li + 1];
      out[p + 2] = lut[li + 2];
      out[p + 3] = lut[li + 3] * coverage;
    }
  }
  ctx.putImageData(img, 0, 0);
}

function mercY(lat: number): number {
  const r = (Math.max(-85, Math.min(85, lat)) * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + r / 2));
}

/** Raw value of the grid cell under a map position, or null outside the corridor. */
export function valueAt(
  hm: Heatmap,
  metric: HeatmapMetric,
  hour: number,
  lat: number,
  lng: number,
): number | null {
  const [[south, west], [north, east]] = hm.bounds;
  const col = Math.floor(((lng - west) / (east - west)) * hm.cols);
  const yN = mercY(north);
  const row = Math.floor(((yN - mercY(lat)) / (yN - mercY(south))) * hm.rows);
  if (col < 0 || col >= hm.cols || row < 0 || row >= hm.rows) return null;
  const i = hm.cells.indexOf(row * hm.cols + col);
  return i === -1 ? null : hm.frames[metric][hour][i];
}
