import logging
import os
import time

from opensky_api import OpenSkyApi

logger = logging.getLogger(__name__)

OPENSKY_CLIENT_ID = os.environ.get("OPENSKY_CLIENT_ID", "")
OPENSKY_CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET", "")

if OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET:
    _api = OpenSkyApi(client_id=OPENSKY_CLIENT_ID, client_secret=OPENSKY_CLIENT_SECRET)
    logger.info("OpenSky API initialized with credentials")
else:
    _api = OpenSkyApi()
    logger.info("OpenSky API initialized anonymously")


def get_nearby_aircraft(lat, lon, radius_km):
    """Fetch aircraft within a bounding box from OpenSky Network."""
    delta = radius_km / 111  # ~111km per degree latitude
    try:
        states = _api.get_states(bbox=(
            lat - delta,
            lat + delta,
            lon - delta,
            lon + delta,
        ))
    except Exception:
        logger.exception("OpenSky states API failed")
        return []

    if not states or not states.states:
        return []

    return [
        {
            "callsign": s.callsign.strip() if s.callsign else None,
            "icao24": s.icao24,
            "origin_country": s.origin_country,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "altitude_m": s.baro_altitude,
            "velocity_ms": s.velocity,
            "heading": s.true_track,
            "on_ground": s.on_ground,
        }
        for s in states.states
        if not s.on_ground
    ]


def get_flight_details(icao24):
    """Fetch route and departure time for an aircraft by ICAO24 address."""
    now = int(time.time())
    try:
        flights = _api.get_flights_by_aircraft(icao24, now - 7200, now)
        if not flights:
            return None
        flight = flights[-1]
        return {
            "departure_airport": flight.estDepartureAirport,
            "arrival_airport": flight.estArrivalAirport,
            "first_seen": flight.firstSeen,
        }
    except Exception:
        logger.exception("OpenSky flight details failed for %s", icao24)
        return None
