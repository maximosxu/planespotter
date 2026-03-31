from math import radians, sin, cos, sqrt, atan2


def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two points in km."""
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def find_overhead(aircraft, lat, lon):
    """Sort aircraft by distance from a point, return closest 10."""
    for ac in aircraft:
        if ac["latitude"] is not None and ac["longitude"] is not None:
            ac["distance_km"] = round(
                haversine(lat, lon, ac["latitude"], ac["longitude"]), 2
            )

    ranked = sorted(
        [a for a in aircraft if "distance_km" in a],
        key=lambda a: a["distance_km"],
    )
    return ranked[:10]
