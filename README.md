# Weather-Aware Truck Routing

**Live demo:** https://weather-aware-truck-routing-omega.vercel.app · API: https://truck-routing-api-d071.onrender.com/api/health

> Hosted on free tiers. The API sleeps after 15 minutes idle, so the first search can take up to a minute while it wakes. After that it's fast.

A React + Django app that helps a truck driver pick the safest route. It weighs forecast weather at the truck's estimated arrival time at each point on the route, the load weight, and the travel time.

**Inputs:** origin, destination, departure date and time, load weight, and a sample interval of 10, 25 or 50 miles.

**Outputs:** 3 route options on a map, with:
- weather checkpoints colored by risk, each with its ETA and conditions
- risk-colored route segments
- a per-route summary (miles in each risk level)
- a recommended route and the reason it was chosen
- a corridor weather heatmap with a 0–48 h forecast slider

No API keys are needed. All providers are free:

| Concern | Provider |
|---|---|
| Routing (with alternatives) | [OSRM](https://project-osrm.org/) public server |
| Geocoding / autocomplete | [Photon](https://photon.komoot.io/) (OpenStreetMap data), falling back to [Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api) when Photon is unreachable (e.g. from Render) |
| Hourly forecasts | [Open-Meteo](https://open-meteo.com/) |
| Map tiles | CARTO Light (OpenStreetMap data) |

---

## Quick start

Requirements: Python 3.11 or newer, and Node 18 or newer.

```bash
# 1. Backend  (http://127.0.0.1:8000)
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver 8000

# 2. Frontend (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Click **Try Chicago → Denver**, then **Find safest route**.

Run the backend tests:

```bash
cd backend && .venv/bin/python manage.py test trips
```

Type-check and build the frontend:

```bash
cd frontend && npm run build
```

### Configuration (optional environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OSRM_BASE_URL` | `https://router.project-osrm.org` | Point at a self-hosted OSRM (e.g. with a truck profile) |
| `PHOTON_BASE_URL` | `https://photon.komoot.io` | Geocoder |
| `OPEN_METEO_BASE_URL` | `https://api.open-meteo.com` | Weather |
| `OPEN_METEO_API_KEY` | – | Commercial key (use with `OPEN_METEO_BASE_URL=https://customer-api.open-meteo.com`) |
| `TRUCK_MAX_SPEED_MPH` | `65` | Truck speed cap applied to router durations |
| `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` | dev values | Deployment |
| `VITE_API_BASE` (frontend) | `/api` | API base URL when the frontend isn't served behind the dev proxy |

---

## Deployment (free: Render + Vercel)

| Part | Host | Config |
|---|---|---|
| Django API | Render free web service | [`render.yaml`](render.yaml) (Blueprint) |
| React app | Vercel Hobby | [`frontend/vercel.json`](frontend/vercel.json), root directory `frontend` |

1. **Render:** New → Blueprint → select this repo → Apply. Wait for the deploy, then check that `https://<service>.onrender.com/api/health` returns `{"status":"ok"}`.
2. **Vercel:** Add New → Project → import this repo.
   - Set the project name to `weather-aware-truck-routing` and the root directory to `frontend`.
   - Add the environment variable `VITE_API_BASE` = `https://<service>.onrender.com/api`, then deploy.
3. **Allowed sites:** `render.yaml` already allows `https://weather-aware-truck-routing*.vercel.app`. If your Vercel URL is different, edit `CORS_ALLOWED_ORIGIN_REGEXES` or `CORS_ALLOWED_ORIGINS` on Render.

Render's free services sleep after 15 minutes idle, and the first request afterwards takes about 50 s. The frontend pings `/api/health` on page load to start waking the server, and tells the user if a request is slow because of this.

---

## How it works

```
React (Vite, TS, Leaflet)                      Django REST
──────────────────────────                     ─────────────────────────────────────────────
TripForm ── POST /api/plan ─────────────────►  geocoding.resolve()   Photon
                                               routing.route_options() OSRM ×(1..7)
                                               planner._build_route()  checkpoints + ETAs
                                               weather.fetch_hourly()  Open-Meteo (batched, cached)
                                               risk.assess / score_route / recommend
MapView, RouteCards, CheckpointTable  ◄─────── routes, checkpoints, segments, recommendation, corridor

HeatmapLayer ── POST /api/heatmap ──────────►  heatmap.build_heatmap()  grid over corridor × 49 hours
HeatmapControls (slider/play)  ◄────────────── frames[metric][hour][cell]
```

### 1. Routes (`backend/trips/services/routing.py`)
- The first OSRM request asks for up to 3 alternatives.
- OSRM often returns fewer than 3, because it only offers alternatives that differ meaningfully from the main route. When that happens, the backend requests routes forced through **via points** offset to either side of the straight origin–destination line.
- A candidate is kept only if it is **distinct** (it shares under 85% of its length with routes already found) and **reasonable** (no more than 1.6× the fastest duration).
- **Unreachable endpoints:** OSRM snaps each endpoint to the nearest road with no distance limit. A pair with no road connection, like New York → London, would otherwise "succeed" by snapping one end thousands of miles away, so any endpoint that snaps more than 25 km away returns *no drivable route*.
- **Truck speed:** the public OSRM server routes for cars. Any road segment faster than `TRUCK_MAX_SPEED_MPH` (65 mph by default) is slowed to that speed. For true heavy-vehicle routing, point `OSRM_BASE_URL` at an OSRM server built with a truck profile; nothing else changes.

**Geocoding:** Photon matches every word of a query against place names, so "New York, USA" can rank a business called "CAF USA" above the city. When a comma query's top result isn't a city, town or region, the backend searches again with the part before the comma and keeps the places whose state or country matches the rest. Aliases are handled, e.g. USA → United States. A trip whose origin and destination are the same place is rejected.

### 2. Checkpoints and ETAs (`planner.py`)
- Checkpoints are placed at mile 0, then every *N* miles (10, 25 or 50), plus one at the destination.
- OSRM returns a duration for every pair of consecutive points on the route. Summing these gives the time to reach each point. A checkpoint's ETA is interpolated within its segment, so it reflects real speeds, including slow urban stretches.
- **Weather is sampled at that ETA, not at the departure time.** A checkpoint 600 miles out gets the forecast for when the truck actually arrives there, about 9–10 hours later.

### 3. Weather (`weather.py`)
- Open-Meteo hourly forecast, in mph and inches: `wind_speed_10m`, `wind_gusts_10m`, `rain + showers`, `snowfall`, `temperature_2m` and `weather_code`.
- **Interpolation:** wind and temperature are interpolated linearly between hours. Rain and snow are amounts over the preceding hour, so the ETA uses the hourly bucket it falls in. That value is the in/hr rate.
- **Batching and caching:** up to 100 locations per request, run 4 requests in parallel. Results are cached for 30 minutes.
- **Adaptive lookup grid:** checkpoints snap to a lookup grid so nearby points share one forecast. The grid starts at 0.05° (about 3.5 mi). Open-Meteo's free tier counts each location as one call (about 600 per minute), so if a trip has more than 300 unique points, the grid is coarsened step by step until it fits. A typical trip keeps 0.05–0.15°. The extreme case, 3 cross-country routes at 10-mile spacing, ends up near 0.5°. **ETAs are never approximated.** The response reports the grid used as `weather_grid_deg`. With a commercial key (`OPEN_METEO_API_KEY`), these budgets can be raised.

### 4. Risk rules (`risk.py`, pure functions with tests)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

**Load rules** (these apply to wind only):
- ≥ 55 mph means No Travel for any load.
- 45–54 mph with a load over 30,000 lb means No Travel.
- 35–44 mph with a load over 40,000 lb means Severe.

**How the table is applied:**
- **Overall checkpoint risk** is the worst of the three conditions: wind (after the load rules), rain and snow.
- **Shared boundaries:** where two bands share an edge (e.g. rain 0.25), the value goes into the higher band, which is the safer choice. The exception is the rain and snow No Travel edges, which the table defines as strictly greater than (> 1.00, > 3.0).
- **Sustained wind** drives the classification. Gusts are shown for context.

### 5. Route scoring and recommendation
- **Assigning miles to checkpoints:** each checkpoint covers the stretch of road nearer to it than to its neighbors (midpoint to midpoint). Every mile is counted exactly once. The map colors each route segment the same way.
- **Average risk:** the mile-weighted mean of the risk levels, where 0 = Low and 4 = No Travel.

**Ranking.** Routes are compared on these criteria, in order. The first difference decides.
1. **No Travel miles.** A route that crosses a No Travel zone never beats one that doesn't. The brief doesn't list this criterion; it follows from No Travel being worse than Severe.
2. Fewest **Severe** miles
3. Fewest **High** miles
4. Lowest **average risk**
5. Shortest **travel time**

**Tie handling:** miles are rounded to 0.1 and average risk to 0.01 before comparing. That way floating-point noise can't settle a tie that should pass to the next criterion.

**What the user sees:**
- The UI states why the recommended route won, e.g. "Fewest Severe miles (0.0 mi vs 37.5 mi)".
- Each other route shows why it wasn't chosen.
- If even the best route has Severe or No Travel exposure, a warning suggests caution or a later departure.

### 6. Heatmap (`heatmap.py` + `frontend/src/lib/heatmapRender.ts`)

**Backend (grid):**
- Builds a grid over the bounding box of all routes, using cells of at least 0.1°, with at most 48 cells along the long side.
- Only cells within about 30 miles of a route are populated. The count is capped at 280: if a trip would need more, the cells get larger.
- Grid rows are spaced evenly in **Web-Mercator Y**, so the grid can be stretched over the map as one image without vertical distortion.
- For each cell and each hour from departure to departure + 48 h, it returns wind, rain, snow and the load-adjusted risk level. All of this is fetched once.

**Frontend (rendering), built for a smooth slider:**
- **Single canvas:** the overlay is one `<canvas>` placed by Leaflet's own `ImageOverlay` positioning and zoom animation. Moving the slider repaints that canvas in place, with no network requests, no image reloads and no flicker.
- **Smooth colors:** values, not colors, are interpolated bilinearly between cell centers at 6× resolution, then colored through a lookup table. The corridor edges fade out softly.
- **Fast repaints:** a frame takes about 2 ms, so dragging and the ▶ playback stay smooth.
- **Matching colors:** the wind, rain and snow color scales change at the same thresholds as the risk table, so a color always means the same risk level.
- **Hover readout:** shows the value under the cursor.
- **Truck markers:** show where each truck would be at the slider time. A tick on the slider marks the selected route's arrival.
- **Linked to checkpoints:** clicking a checkpoint jumps the slider to the hour the truck reaches it.

### Map performance notes
- Leaflet's **canvas renderer** draws every vector (routes and hundreds of checkpoints).
- Route geometry is simplified with Douglas-Peucker on the server (about 20 m tolerance). A 1,000-mile route goes from about 10k points to about 900.
- Static layers (`RoutesLayer`, `CheckpointsLayer`, `CheckpointTable`) are memoized, so moving the slider only re-renders the heatmap and the truck markers.
- The heatmap is a separate request. Routes appear as soon as they are ready, and the heatmap fills in about 1–2 s later.

---

## API

### `POST /api/plan`
```json
{
  "origin": "Chicago, IL",                      // or {"label","lat","lon"} or "41.88,-87.63"
  "destination": {"label": "Denver, CO", "lat": 39.74, "lon": -104.98},
  "departure_time": "2026-11-02T14:00:00Z",     // within the next 7 days
  "load_weight_lb": 42000,
  "interval_mi": 25                              // 10 | 25 | 50
}
```
Returns `routes[]`. Each route has:
- `id`, `summary`, `distance_mi`, `duration_s`, `arrival`
- `rank`, `recommended`, `why_not`
- `score.miles_by_level`, `score.average_risk`, `score.max_level`
- `geometry` and `vertex_times_s`
- `risk_segments`
- `checkpoints[]`, each with `mile`, `eta`, `weather` and `risk` (`level`, `wind`, `rain`, `snow`) plus `reasons`

The response also has `recommendation` (`route_id`, `reason`, `ranking`), `corridor` and `warnings`.

### `POST /api/heatmap`
`{"corridor": [[[lat,lon],...],...], "start_time": "...", "load_weight_lb": 42000}` returns `bounds`, `rows`, `cols`, `cells` and `frames.{risk,wind,rain,snow}[hour][i]`.

### `GET /api/geocode?q=...`
Place suggestions.

**Errors:**
- `400`: invalid input, or no route found. Body: `{detail}` or field errors.
- `502`: an upstream provider failed.

---

## Project layout

```
backend/
  config/                Django settings & root URLs
  trips/
    services/
      risk.py            risk table, load rules, scoring, recommendation (pure)
      geo.py             distances, interpolation, simplification, overlap (pure)
      routing.py         OSRM client + alternative-route generation
      weather.py         Open-Meteo client: batching, caching, ETA sampling
      planner.py         orchestration → API response
      heatmap.py         corridor grid + 49 hourly frames
      geocoding.py       Photon client
      http.py            shared session (retries/timeouts) + error types
    serializers.py       request validation
    views.py             endpoints
    tests/               risk rules, recommendation, geometry, planner (providers mocked)
frontend/src/
  App.tsx                state + layout
  components/            TripForm, PlaceInput, RouteCards, RiskBar, CheckpointTable,
                         MapView, RoutesLayer, CheckpointsLayer, HeatmapLayer, HeatmapControls
  lib/                   api client, risk colours/ramps, heatmap renderer, canvas overlay, formatting
```

## Assumptions and limitations
- **Driving time is continuous.** Hours-of-Service breaks and fuel stops aren't modeled, so ETAs on long trips are optimistic. Adding them would mean inserting rest time into the cumulative times before sampling weather.
- **Car routing.** The public OSRM server ignores truck restrictions such as height and weight limits and hazmat rules. See the routing notes above for how to swap in a truck profile.
- **Forecast range.** Departure must be within 7 days. Open-Meteo forecasts go 16 days out, but accuracy drops off quickly after the first few.
- **Time zones.** Times are entered and shown in the browser's time zone. The API uses UTC ISO-8601 throughout.
- **Rate limits.** The public OSRM, Photon and Open-Meteo services are rate-limited and meant for fair use. For production, self-host them or use paid tiers; the base URLs are configurable.
