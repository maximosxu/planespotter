# Plane Spotter

A real-time aircraft tracking web app that shows nearby planes on an interactive map. Uses your browser's geolocation to find aircraft overhead, displaying their position, altitude, speed, route, and airline information.

## Architecture

```
Browser (Leaflet map + sidebar)
  |
  |  GET /api/overhead?lat=...&lon=...&radius=15
  v
Flask app (app.py)
  |
  |-- services/opensky.py    -> OpenSky Network API (aircraft positions + routes)
  |-- services/flightaware.py -> FlightAware AeroAPI (enriched flight details, optional)
  |-- services/airlines.py    -> Local CSV lookup (airline names from ICAO codes)
  |-- services/distance.py    -> Haversine distance calculation
  |
  v
Response: list of nearest 10 aircraft with metadata
```

## How It Works

1. The browser requests your location and sends it to `/api/overhead`
2. The backend queries **OpenSky Network** for all aircraft within a bounding box
3. Results are filtered (grounded aircraft removed), sorted by distance, and trimmed to the closest 10
4. Each aircraft is enriched with:
   - **Airline name** from a local CSV database (`data/airlines.csv`) using the callsign's ICAO prefix
   - **Route and departure time** from OpenSky's flight tracking endpoint
5. The frontend renders aircraft as cards in a sidebar and as rotated plane icons on a Leaflet map
6. Clicking "Details" on a card fetches additional data from **FlightAware** (aircraft type, full airport names) via `/api/flight-details`
7. The page auto-refreshes every 60 seconds

## Data Sources

| Source | What it provides | Cost |
|--------|-----------------|------|
| [OpenSky Network](https://opensky-network.org) | Live aircraft positions, routes, departure times | Free (requires account for higher rate limits) |
| [FlightAware AeroAPI](https://www.flightaware.com/aeroapi/) | Airline, aircraft type, full airport names | Paid (budget-guarded at $4.90/billing period) |
| [OpenFlights](https://github.com/jpatokal/openflights) | Airline name database | Free (bundled CSV) |

## Project Structure

```
plane-spotter/
  app.py                  # Flask app, API routes, caching, security middleware
  Procfile                # gunicorn entry point for deployment
  requirements.txt        # Python dependencies
  .env                    # Environment variables (not committed)
  data/
    airlines.csv          # OpenFlights airline database
  services/
    opensky.py            # OpenSky Network SDK client
    flightaware.py        # FlightAware AeroAPI client with budget guard
    airlines.py           # Airline name lookup from CSV
    distance.py           # Haversine formula, find closest aircraft
  templates/
    index.html            # Single-page frontend (dark theme, responsive)
  static/
    app.js                # Map initialization, API calls, UI rendering
```

## Key Files

### `app.py`
- **`/health`** — Health check endpoint for deployment platforms
- **`/api/overhead`** — Main endpoint: fetches nearby aircraft, enriches with airline/route data. Response cached server-side for 15 seconds.
- **`/api/flight-details`** — On-demand FlightAware lookup for a single callsign. Rate-limited (10 requests/IP/minute).
- HTTPS redirect via `X-Forwarded-Proto` header
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`

### `services/opensky.py`
- Uses the official OpenSky Python SDK (`opensky_api`)
- Authenticates via OAuth2 client credentials if `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET` are set
- Falls back to anonymous access (lower rate limits) if no credentials

### `services/flightaware.py`
- Queries FlightAware's AeroAPI for enriched flight data
- **Budget guard**: checks billing usage before every paid call, stops at $4.90
- In-memory cache with 2-hour TTL (flight routes don't change mid-flight)
- Cache capped at 200 entries to prevent unbounded memory growth

### `static/app.js`
- Initializes a Leaflet map (defaults to Seattle if geolocation is unavailable)
- Renders aircraft as rotated SVG plane icons on the map and as cards in the sidebar
- FlightAware details cached in `localStorage` (2-hour TTL, persists across page refreshes)
- All API-sourced strings are HTML-escaped to prevent XSS
- Mobile-responsive with map/list tab switching at 768px

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENSKY_CLIENT_ID` | No | OpenSky API client ID (improves rate limits) |
| `OPENSKY_CLIENT_SECRET` | No | OpenSky API client secret |
| `AEROAPI_KEY` | No | FlightAware AeroAPI key (enables "Details" button) |

Create a `.env` file in the project root for local development:

```
OPENSKY_CLIENT_ID=your-client-id
OPENSKY_CLIENT_SECRET=your-secret
AEROAPI_KEY=your-flightaware-key
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **Note**: The `opensky-api` package requires Python 3.10+.

## Running Locally

```bash
gunicorn app:app
```

The app will be available at `http://localhost:8000`.

## Deployment (Fly.io)

OpenSky blocks requests from major cloud providers (AWS, GCP). Fly.io works because it uses its own infrastructure.

```bash
brew install flyctl
fly auth login
fly launch
fly secrets set OPENSKY_CLIENT_ID='your-client-id'
fly secrets set OPENSKY_CLIENT_SECRET='your-secret'
fly secrets set AEROAPI_KEY='your-key'
fly deploy
fly open
```

Set the health check path to `/health` in your `fly.toml`.

## Caching

| Layer | What | TTL | Max size |
|-------|------|-----|----------|
| Server: `_overhead_cache` | `/api/overhead` responses | 15s | 100 entries |
| Server: `_cache` (FlightAware) | FlightAware API responses | 2h | 200 entries |
| Server: `_usage_cache` | FlightAware billing usage | 2min | 1 entry |
| Client: `localStorage` | FlightAware detail lookups | 2h | Browser limit (~5MB) |

## Security

- **Input validation**: Callsign parameter restricted to alphanumeric characters
- **XSS protection**: All API-sourced strings escaped before HTML insertion
- **HTTPS redirect**: HTTP requests redirected to HTTPS in production
- **Security headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`
- **Rate limiting**: `/api/flight-details` limited to 10 requests per IP per minute
- **Budget guard**: FlightAware API calls stop at $4.90 per billing period
- **Secrets**: API keys loaded from environment variables, `.env` excluded from git
