import logging
import os
import re
import time

logging.basicConfig(level=logging.INFO)

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, redirect, request, render_template

from services.opensky import get_nearby_aircraft, get_flight_details as opensky_flight_details
from services.distance import find_overhead
from services.airlines import get_airline
from services.flightaware import get_flight_details as fa_flight_details, AEROAPI_KEY, is_budget_exceeded

app = Flask(__name__)

# Server-side cache for /api/overhead
_overhead_cache = {}  # key → {"data": ..., "timestamp": ...}
_OVERHEAD_CACHE_TTL = 15  # seconds
_CACHE_MAX_SIZE = 100


def _evict_cache(cache, max_size):
    """Remove oldest entries if cache exceeds max_size."""
    if len(cache) <= max_size:
        return
    sorted_keys = sorted(cache, key=lambda k: cache[k]["timestamp"])
    for key in sorted_keys[:len(cache) - max_size]:
        del cache[key]


@app.before_request
def https_redirect():
    if request.headers.get("X-Forwarded-Proto") == "http":
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def _cache_key(lat, lon, radius):
    return f"{round(lat, 2)},{round(lon, 2)},{round(radius, 1)}"


# Per-IP rate limiting for expensive endpoints
_rate_limit_store = {}  # ip → [timestamp, ...]
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 60  # seconds


def _is_rate_limited(ip):
    """Return True if ip has exceeded _RATE_LIMIT_MAX requests in the last _RATE_LIMIT_WINDOW seconds."""
    now = time.time()
    timestamps = _rate_limit_store.get(ip, [])
    # Prune entries outside the window
    timestamps = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
    _rate_limit_store[ip] = timestamps
    if len(timestamps) >= _RATE_LIMIT_MAX:
        return True
    timestamps.append(now)
    return False


def enrich_aircraft(ac):
    """Add airline and OpenSky route data (free) to an aircraft dict."""
    ac["airline"] = get_airline(ac.get("callsign"))

    details = opensky_flight_details(ac["icao24"])
    if details:
        ac["departure_airport"] = details["departure_airport"]
        ac["arrival_airport"] = details["arrival_airport"]
        if details["first_seen"]:
            ac["time_in_air_min"] = round((time.time() - details["first_seen"]) / 60)
        else:
            ac["time_in_air_min"] = None
    else:
        ac["departure_airport"] = None
        ac["arrival_airport"] = None
        ac["time_in_air_min"] = None

    return ac


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/overhead")
def overhead():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon query parameters are required"}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except ValueError:
        return jsonify({"error": "lat and lon must be numbers"}), 400

    radius_km = float(request.args.get("radius", 10))

    key = _cache_key(lat, lon, radius_km)
    cached = _overhead_cache.get(key)
    if cached and (time.time() - cached["timestamp"]) < _OVERHEAD_CACHE_TTL:
        return jsonify(cached["data"])

    aircraft = get_nearby_aircraft(lat, lon, radius_km)
    closest = find_overhead(aircraft, lat, lon)

    # Basic enrichment only (free): airline name from CSV + OpenSky route data
    for ac in closest:
        enrich_aircraft(ac)

    fa_available = bool(AEROAPI_KEY) and not is_budget_exceeded()

    response_data = {
        "count": len(closest),
        "aircraft": closest,
        "has_flightaware": fa_available,
    }
    _overhead_cache[key] = {"data": response_data, "timestamp": time.time()}
    _evict_cache(_overhead_cache, _CACHE_MAX_SIZE)

    return jsonify(response_data)


@app.route("/api/flight-details")
def flight_details():
    """On-demand FlightAware enrichment for a single aircraft."""
    if _is_rate_limited(request.remote_addr):
        return jsonify({"error": "Rate limit exceeded. Try again later."}), 429

    if not AEROAPI_KEY or is_budget_exceeded():
        return jsonify({"error": "FlightAware API key not configured"}), 503

    callsign = request.args.get("callsign")
    if not callsign:
        return jsonify({"error": "callsign parameter is required"}), 400
    if not re.match(r'^[A-Za-z0-9]+$', callsign):
        return jsonify({"error": "Invalid callsign"}), 400

    details = fa_flight_details(callsign)
    if details:
        return jsonify(details)
    else:
        return jsonify({"error": "No flight details found"}), 404
