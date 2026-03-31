import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

from services.airlines import AIRLINES

AEROAPI_BASE = "https://aeroapi.flightaware.com/aeroapi"
AEROAPI_KEY = os.environ.get("AEROAPI_KEY", "")
BUDGET_LIMIT = 4.90  # Stop using API at this dollar amount

# In-memory cache: callsign → {data, timestamp}
_cache = {}
CACHE_TTL = 7200  # 2 hours — flight route doesn't change mid-flight
_CACHE_MAX_SIZE = 200

# Usage cache
_usage_cache = {"cost": 0.0, "timestamp": 0}
_USAGE_CACHE_TTL = 120  # Check usage every 2 minutes


def _get_headers():
    return {"x-apikey": AEROAPI_KEY}


def check_usage():
    """Check current billing period usage (free endpoint). Returns total cost in dollars."""
    now = time.time()
    if (now - _usage_cache["timestamp"]) < _USAGE_CACHE_TTL:
        return _usage_cache["cost"]

    try:
        resp = requests.get(
            f"{AEROAPI_BASE}/account/usage",
            headers=_get_headers(),
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()

        total = data.get("total_cost", 0.0)

        _usage_cache["cost"] = total
        _usage_cache["timestamp"] = now
        logger.info("Usage: $%.2f / $%.2f limit", total, BUDGET_LIMIT)
        return total

    except Exception as e:
        logger.warning("Usage check failed: %s", e)
        return _usage_cache["cost"]


def is_budget_exceeded():
    """Check if we've hit the budget limit."""
    if not AEROAPI_KEY:
        return True
    return check_usage() >= BUDGET_LIMIT


def get_flight_details(callsign):
    """Fetch flight details from FlightAware AeroAPI, with caching and budget guard."""
    if not AEROAPI_KEY:
        return None

    if not callsign:
        return None

    # Check cache first (free, no budget impact)
    cached = _cache.get(callsign)
    if cached and (time.time() - cached["timestamp"]) < CACHE_TTL:
        return cached["data"]

    # Budget check before making a paid API call
    if is_budget_exceeded():
        logger.info("Budget exceeded, skipping API call for %s", callsign)
        return None

    try:
        resp = requests.get(
            f"{AEROAPI_BASE}/flights/{callsign}",
            headers=_get_headers(),
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()

        flights = data.get("flights", [])
        if not flights:
            result = None
        else:
            # Find the in-progress flight (has progress, hasn't landed)
            flight = None
            for f in flights:
                status = f.get("status", "")
                progress = f.get("progress_percent", 0)
                if progress and progress > 0 and "arrived" not in status.lower():
                    flight = f
                    break
                if f.get("actual_off") and not f.get("actual_on"):
                    flight = f
                    break
            if not flight:
                flight = flights[0]

            origin = flight.get("origin", {})
            destination = flight.get("destination", {})
            departure_time = (
                flight.get("actual_off")
                or flight.get("actual_out")
                or flight.get("estimated_off")
                or flight.get("estimated_out")
                or flight.get("scheduled_off")
                or flight.get("scheduled_out")
            )

            time_in_air_min = None
            if departure_time:
                from datetime import datetime, timezone

                try:
                    dep_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    time_in_air_min = round((now - dep_dt).total_seconds() / 60)
                    if time_in_air_min < 0:
                        time_in_air_min = None
                except (ValueError, TypeError):
                    time_in_air_min = None

            result = {
                "airline": AIRLINES.get(flight.get("operator_icao", "")) or flight.get("operator"),
                "departure_airport": origin.get("code", None),
                "departure_airport_name": origin.get("name", None),
                "arrival_airport": destination.get("code", None),
                "arrival_airport_name": destination.get("name", None),
                "aircraft_type": flight.get("aircraft_type", None),
                "time_in_air_min": time_in_air_min,
            }

        _cache[callsign] = {"data": result, "timestamp": time.time()}
        if len(_cache) > _CACHE_MAX_SIZE:
            oldest = min(_cache, key=lambda k: _cache[k]["timestamp"])
            del _cache[oldest]
        return result

    except Exception:
        logger.exception("FlightAware API call failed for %s", callsign)
        return None
