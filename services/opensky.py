import logging
import time

import requests

logger = logging.getLogger(__name__)

OPENSKY_URL = "https://opensky-network.org/api/states/all"
OPENSKY_FLIGHTS_URL = "https://opensky-network.org/api/flights/aircraft"


def get_nearby_aircraft(lat, lon, radius_km):
    """Fetch aircraft within a bounding box from OpenSky Network."""
    delta = radius_km / 111  # ~111km per degree latitude
    try:
        resp = requests.get(
            OPENSKY_URL,
            params={
                "lamin": lat - delta,
                "lamax": lat + delta,
                "lomin": lon - delta,
                "lomax": lon + delta,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("OpenSky states API failed")
        return []

    if not data.get("states"):
        return []

    return [
        {
            "callsign": s[1].strip() if s[1] else None,
            "icao24": s[0],
            "origin_country": s[2],
            "latitude": s[6],
            "longitude": s[5],
            "altitude_m": s[7],
            "velocity_ms": s[9],
            "heading": s[10],
            "on_ground": s[8],
        }
        for s in data["states"]
        if not s[8]  # exclude grounded aircraft
    ]


def get_flight_details(icao24):
    """Fetch route and departure time for an aircraft by ICAO24 address."""
    now = int(time.time())
    try:
        resp = requests.get(
            OPENSKY_FLIGHTS_URL,
            params={
                "icao24": icao24,
                "begin": now - 7200,  # last 2 hours
                "end": now,
            },
            timeout=5,
        )
        resp.raise_for_status()
        flights = resp.json()
        if not flights:
            return None
        # Take the most recent flight
        flight = flights[-1]
        return {
            "departure_airport": flight.get("estDepartureAirport"),
            "arrival_airport": flight.get("estArrivalAirport"),
            "first_seen": flight.get("firstSeen"),
        }
    except Exception:
        logger.exception("OpenSky flight details failed for %s", icao24)
        return None
