import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ROME = ZoneInfo("Europe/Rome")

from config import logger, authorized_users
from modules.database import get_connection, _lock


def load_authorized_users():
    """Carica gli utenti autorizzati dalla tabella users."""
    global authorized_users
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT user_id FROM users").fetchall()
        loaded_users = [row["user_id"] for row in rows]
        if loaded_users:
            authorized_users.clear()
            authorized_users.extend(loaded_users)
            logger.info(f"Caricati {len(authorized_users)} utenti autorizzati")
        else:
            logger.warning("Nessun utente autorizzato nel DB, mantengo utenti esistenti")
    except Exception as e:
        logger.error(f"Errore nel caricare gli utenti autorizzati: {str(e)}")


def save_authorized_users():
    """Salva gli utenti autorizzati nella tabella users (DELETE + INSERT)."""
    try:
        with _lock:
            with get_connection() as conn:
                conn.execute("DELETE FROM users")
                for user_id in authorized_users:
                    conn.execute(
                        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                        (str(user_id),)
                    )
        logger.info("Utenti autorizzati salvati con successo")
    except Exception as e:
        logger.error(f"Errore nel salvare gli utenti autorizzati: {str(e)}")


def load_authorized_users_with_lock():
    """Alias di load_authorized_users() — il lock è gestito in database.py."""
    load_authorized_users()


def save_authorized_users_with_lock():
    """Alias di save_authorized_users() — il lock è gestito in database.py."""
    save_authorized_users()


def load_input_data():
    """Carica le prescrizioni dalla tabella prescriptions."""
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT data FROM prescriptions").fetchall()
        return [json.loads(row["data"]) for row in rows]
    except Exception as e:
        logger.error(f"Errore nel caricare i dati di input: {str(e)}")
        return []


def save_input_data(data):
    """Salva la lista delle prescrizioni nella tabella prescriptions (DELETE + INSERT)."""
    try:
        with _lock:
            with get_connection() as conn:
                conn.execute("DELETE FROM prescriptions")
                for prescription in data:
                    conn.execute(
                        """INSERT OR REPLACE INTO prescriptions
                           (fiscal_code, nre, telegram_chat_id, notifications_enabled,
                            auto_book_enabled, phone, email, description, data, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                        (
                            prescription.get("fiscal_code", ""),
                            prescription.get("nre", ""),
                            prescription.get("telegram_chat_id"),
                            1 if prescription.get("notifications_enabled", True) else 0,
                            1 if prescription.get("auto_book_enabled", False) else 0,
                            prescription.get("phone"),
                            prescription.get("email"),
                            prescription.get("description"),
                            json.dumps(prescription),
                        )
                    )
        logger.info(f"Dati delle prescrizioni salvati con successo ({len(data)} prescrizioni)")
    except Exception as e:
        logger.error(f"Errore nel salvare i dati delle prescrizioni: {str(e)}")


def load_previous_data():
    """Carica i dati di disponibilità precedenti dalla tabella previous_availabilities."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT prescription_key, availabilities FROM previous_availabilities"
            ).fetchall()
        return {row["prescription_key"]: json.loads(row["availabilities"]) for row in rows}
    except Exception as e:
        logger.error(f"Errore nel caricare i dati precedenti: {str(e)}")
        return {}


def save_previous_data(data):
    """Salva i dati di disponibilità nella tabella previous_availabilities (DELETE + INSERT)."""
    try:
        with _lock:
            with get_connection() as conn:
                conn.execute("DELETE FROM previous_availabilities")
                for key, value in data.items():
                    conn.execute(
                        """INSERT OR REPLACE INTO previous_availabilities
                           (prescription_key, availabilities, updated_at)
                           VALUES (?, ?, datetime('now'))""",
                        (key, json.dumps(value))
                    )
        logger.info("Dati precedenti salvati con successo")
    except Exception as e:
        logger.error(f"Errore nel salvare i dati precedenti: {str(e)}")


def _parse_utc_to_rome(date_string):
    """Parsa una stringa UTC ISO e la converte al fuso orario di Roma (CET/CEST)."""
    dt = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%SZ")
    return dt.replace(tzinfo=timezone.utc).astimezone(_ROME)


def fmt_datetime(date_string):
    """Restituisce la data nel formato DD/MM/YYYY HH:MM in ora italiana."""
    try:
        return _parse_utc_to_rome(date_string).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return date_string


def format_date(date_string):
    """Formatta la data ISO in un formato più leggibile (ora italiana)."""
    try:
        dt = _parse_utc_to_rome(date_string)
        weekdays = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        months = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        weekday = weekdays[dt.weekday()]
        day = dt.day
        month = months[dt.month - 1]
        year = dt.year
        time = dt.strftime("%H:%M")
        return f"{weekday} {day} {month} {year}, ore {time}"
    except Exception as e:
        logger.warning(f"Errore nella formattazione della data {date_string}: {str(e)}")
        return date_string


def is_date_within_range(date_str, months_limit=None):
    """Verifica se una data è compresa nell'intervallo di oggi fino a X mesi."""
    if months_limit is None:
        return True
    try:
        date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        today = datetime.now()
        limit_date = today + timedelta(days=30 * months_limit)
        return today <= date <= limit_date
    except Exception as e:
        logger.warning(f"Errore nel verificare l'intervallo di date: {str(e)}")
        return True


def is_similar_datetime(date1_str, date2_str, minutes_threshold=30):
    """Controlla se due date sono simili entro un certo numero di minuti."""
    try:
        dt1 = datetime.strptime(date1_str, "%Y-%m-%dT%H:%M:%SZ")
        dt2 = datetime.strptime(date2_str, "%Y-%m-%dT%H:%M:%SZ")
        diff_minutes = abs((dt2 - dt1).total_seconds() / 60)
        same_day = (dt1.year == dt2.year and dt1.month == dt2.month and dt1.day == dt2.day)
        return same_day and diff_minutes <= minutes_threshold
    except Exception:
        return False
