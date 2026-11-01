import type { Heatmap, LatLng, Place, Plan, PlanRequest } from "../types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {}

/** Flatten DRF's error payloads ({detail} or {field: [msgs]}) into one message. */
function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const obj = body as Record<string, unknown>;
    if (typeof obj.detail === "string") return obj.detail;
    const parts = Object.entries(obj).map(([field, msgs]) => {
      const text = Array.isArray(msgs) ? msgs.join(" ") : String(msgs);
      return field === "non_field_errors" ? text : `${field.replace(/_/g, " ")}: ${text}`;
    });
    if (parts.length) return parts.join(" · ");
  }
  return `Request failed (HTTP ${status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Cannot reach the server. Is the backend running?");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(errorMessage(body, res.status));
  return body as T;
}

/** Fire-and-forget ping so a sleeping free-tier backend starts waking up on page load. */
export function wakeServer(): void {
  fetch(`${BASE}/health`).catch(() => undefined);
}

export function geocode(q: string, signal?: AbortSignal): Promise<Place[]> {
  return request<{ results: Place[] }>(`/geocode?q=${encodeURIComponent(q)}`, { signal }).then(
    (r) => r.results,
  );
}

export function planTrip(body: PlanRequest, signal?: AbortSignal): Promise<Plan> {
  return request<Plan>("/plan", { method: "POST", body: JSON.stringify(body), signal });
}

export function fetchHeatmap(
  corridor: LatLng[][],
  startTime: string,
  loadLb: number,
  signal?: AbortSignal,
): Promise<Heatmap> {
  return request<Heatmap>("/heatmap", {
    method: "POST",
    body: JSON.stringify({ corridor, start_time: startTime, load_weight_lb: loadLb }),
    signal,
  });
}
