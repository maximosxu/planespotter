import csv
import os

# Load OpenFlights airlines database at import time.
# CSV columns: id, name, alias, IATA, ICAO, callsign, country, active
# Source: https://github.com/jpatokal/openflights/blob/master/data/airlines.dat

AIRLINES = {}

_data_path = os.path.join(os.path.dirname(__file__), "..", "data", "airlines.csv")
with open(_data_path, encoding="utf-8") as f:
    for row in csv.reader(f):
        icao = row[4].strip() if len(row) > 4 else ""
        name = row[1].strip() if len(row) > 1 else ""
        if icao and icao != "N/A" and icao != "\\N" and name:
            AIRLINES[icao] = name


def get_airline(callsign):
    """Extract airline name from callsign's ICAO prefix."""
    if not callsign:
        return None
    prefix = ""
    for ch in callsign:
        if ch.isalpha():
            prefix += ch
        else:
            break
    return AIRLINES.get(prefix)
