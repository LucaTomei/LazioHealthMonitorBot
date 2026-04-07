import json
import os
import logging
import requests

from modules.database import get_connection, _lock

logger = logging.getLogger("LocationsDB")


def _geoapify_key():
    return os.getenv("GEOAPIFY_API_KEY")


def geocode_query(query):
    """
    Geocodifica una query usando Geoapify.
    Restituisce (lat, lon) oppure (None, None).
    """
    api_key = _geoapify_key()
    if not api_key:
        logger.warning("GEOAPIFY_API_KEY non configurata, geocoding saltato")
        return None, None

    try:
        response = requests.get(
            "https://api.geoapify.com/v1/geocode/search",
            params={"text": query, "lang": "it", "limit": 1, "apiKey": api_key},
            timeout=5
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        if features:
            coords = features[0]["geometry"]["coordinates"]
            return coords[1], coords[0]  # lat, lon
    except Exception as e:
        logger.warning(f"Errore nel geocoding per '{query}': {e}")
    return None, None


def load_locations_db():
    """Carica il database delle location dalla tabella locations."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT key, hospital, address, latitude, longitude FROM locations"
            ).fetchall()
        return {
            row["key"]: {
                "hospital": row["hospital"],
                "address": row["address"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
            }
            for row in rows
        }
    except Exception as e:
        logger.warning(f"Errore nel caricamento delle location dal DB: {e}")
        return {}


def save_locations_db(locations):
    """Salva il database delle location nella tabella locations (DELETE + INSERT)."""
    try:
        with _lock:
            with get_connection() as conn:
                conn.execute("DELETE FROM locations")
                for key, loc in locations.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO locations (key, hospital, address, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
                        (key, loc.get("hospital"), loc.get("address"), loc.get("latitude"), loc.get("longitude"))
                    )
        logger.info("Database delle location salvato con successo")
    except Exception as e:
        logger.error(f"Errore nel salvataggio del database delle location: {e}")


def update_location_db(hospital_name, address, location_db):
    """
    Aggiorna il dizionario delle location.
    Geocodifica solo se le coordinate non sono già presenti.
    """
    key = f"{hospital_name} - {address}"
    if key not in location_db:
        location_db[key] = {
            "hospital": hospital_name,
            "address": address,
            "latitude": None,
            "longitude": None
        }

    if location_db[key]["latitude"] is not None and location_db[key]["longitude"] is not None:
        return

    lat, lon = geocode_query(address)
    if lat is None or lon is None:
        lat, lon = geocode_query(f"{hospital_name}, Italia")

    if lat is not None and lon is not None:
        location_db[key]["latitude"] = lat
        location_db[key]["longitude"] = lon
        logger.info(f"Coordinate trovate per {key}: {lat}, {lon}")
    else:
        logger.debug(f"Coordinate non trovate per {key}")
