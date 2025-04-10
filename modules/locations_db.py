import json
import os
import logging
import requests
import time

# Imposta il percorso del file JSON che fungerà da "database" delle location
LOCATIONS_DB_FILE = "locations.json"

logger = logging.getLogger("LocationsDB")

def geocode_query(query):
    """
    Effettua il geocoding di una query (indirizzo, nome, ecc.) usando Nominatim.
    Restituisce latitudine e longitudine oppure (None, None) in caso di fallimento.
    """
    base_url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "RecupMonitor/1.0 (tuo.email@dominio.com)"
    }
    
    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return lat, lon
    except Exception as e:
        print(f"Errore nel geocoding per la query '{query}': {e}")
    return None, None

def load_locations_db():
    """Carica il database delle location da file JSON."""
    if os.path.exists(LOCATIONS_DB_FILE):
        try:
            with open(LOCATIONS_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("File JSON delle location corrotto, restituisco dizionario vuoto")
            return {}
    return {}

def save_locations_db(locations):
    """Salva il database delle location su file JSON."""
    try:
        with open(LOCATIONS_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(locations, f, indent=4, ensure_ascii=False)
        logger.info("Database delle location salvato con successo")
    except Exception as e:
        logger.error(f"Errore nel salvataggio del database delle location: {e}")

def update_location_db(hospital_name, address, location_db):
    """
    Aggiorna il dizionario delle location.
    Se latitudine o longitudine sono None, prova a geocodificare usando prima l'indirizzo;
    se questo fallisce, prova con il nome dell'ospedale.
    """
    key = f"{hospital_name} - {address}"
    if key not in location_db:
        # Aggiunge la voce con coordinate vuote
        location_db[key] = {
            "hospital": hospital_name,
            "address": address,
            "latitude": None,
            "longitude": None
        }
    
    # Se le coordinate sono già presenti, non fare nulla
    if location_db[key]["latitude"] is not None and location_db[key]["longitude"] is not None:
        return

    # Prima prova a geocodificare l'indirizzo
    lat, lon = geocode_query(address)
    
    # Se non trova, prova a usare il nome dell'ospedale (magari con aggiunta di "Italia" per contestualizzare)
    if lat is None or lon is None:
        query = f"{hospital_name}, Italia"
        lat, lon = geocode_query(query)
    
    # Se sono state trovate coordinate, aggiornale
    if lat is not None and lon is not None:
        location_db[key]["latitude"] = lat
        location_db[key]["longitude"] = lon
        print(f"Coordinate trovate per {key}: {lat}, {lon}")
    else:
        print(f"Coordinate non trovate per {key}")

    # Per rispettare i limiti di Nominatim, attende 1 secondo tra le richieste
    time.sleep(.3)
