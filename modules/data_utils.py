import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ROME = ZoneInfo("Europe/Rome")

from config import logger, authorized_users
from modules.database import get_connection, _lock


def load_authorized_users():
    """Carica gli utenti autorizzati dalla tabella users."""
    try:
        with get_connection() as conn:
            # L'admin è il primo utente: l'ordine di inserimento va preservato
            rows = conn.execute("SELECT user_id FROM users ORDER BY rowid").fetchall()
        loaded_users = [row["user_id"] for row in rows]
        if loaded_users:
            authorized_users.clear()
            authorized_users.extend(loaded_users)
            logger.info(f"Caricati {len(authorized_users)} utenti autorizzati")
        else:
            logger.warning("Nessun utente autorizzato nel DB, mantengo utenti esistenti")
    except Exception as e:
        logger.error(f"Errore nel caricare gli utenti autorizzati: {str(e)}")


def count_authorized_users_in_db():
    """Numero di utenti autorizzati salvati nel DB (solleva eccezione se il DB non è leggibile)."""
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


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


# =============================================================================
# PRESCRIZIONI
# Bot e monitoraggio girano in processi separati: ogni scrittura agisce su una
# singola riga, così nessun processo può sovrascrivere o cancellare le
# prescrizioni modificate dall'altro con una copia non aggiornata.
# =============================================================================

def _prescription_params(prescription):
    return (
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


_UPSERT_PRESCRIPTION_SQL = """INSERT OR REPLACE INTO prescriptions
    (fiscal_code, nre, telegram_chat_id, notifications_enabled,
     auto_book_enabled, phone, email, description, data, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
            COALESCE((SELECT created_at FROM prescriptions WHERE fiscal_code = ? AND nre = ?), datetime('now')),
            datetime('now'))"""


def load_input_data():
    """
    Carica le prescrizioni dalla tabella prescriptions.
    Solleva eccezione se il DB non è leggibile: un errore non deve sembrare una lista vuota.
    """
    with get_connection() as conn:
        # Ordine stabile: gli aggiornamenti (INSERT OR REPLACE) non cambiano la posizione
        rows = conn.execute(
            "SELECT data FROM prescriptions ORDER BY created_at, fiscal_code, nre"
        ).fetchall()
    return [json.loads(row["data"]) for row in rows]


def get_prescription(fiscal_code, nre):
    """Ritorna la prescrizione aggiornata dal DB, oppure None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data FROM prescriptions WHERE fiscal_code = ? AND nre = ?",
            (fiscal_code, nre)
        ).fetchone()
    return json.loads(row["data"]) if row else None


def add_prescription(prescription):
    """Aggiunge una prescrizione. Ritorna False se esiste già (stesso codice fiscale e NRE)."""
    with _lock:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            exists = conn.execute(
                "SELECT 1 FROM prescriptions WHERE fiscal_code = ? AND nre = ?",
                (prescription.get("fiscal_code", ""), prescription.get("nre", ""))
            ).fetchone()
            if exists:
                return False
            conn.execute(
                _UPSERT_PRESCRIPTION_SQL,
                _prescription_params(prescription)
                + (prescription.get("fiscal_code", ""), prescription.get("nre", ""))
            )
    logger.info(f"Prescrizione aggiunta: NRE {prescription.get('nre')}")
    return True


def update_prescription(fiscal_code, nre, mutate):
    """
    Modifica atomicamente una prescrizione: la rilegge dal DB dentro una transazione
    che blocca le scritture degli altri processi, applica `mutate(prescription)` e la salva.
    Ritorna la prescrizione aggiornata, oppure None se non esiste più.
    """
    with _lock:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT data FROM prescriptions WHERE fiscal_code = ? AND nre = ?",
                (fiscal_code, nre)
            ).fetchone()
            if not row:
                return None
            prescription = json.loads(row["data"])
            mutate(prescription)
            # La chiave primaria non può cambiare
            prescription["fiscal_code"] = fiscal_code
            prescription["nre"] = nre
            conn.execute(
                _UPSERT_PRESCRIPTION_SQL,
                _prescription_params(prescription) + (fiscal_code, nre)
            )
    return prescription


def delete_prescription(fiscal_code, nre):
    """Rimuove una prescrizione e le relative disponibilità salvate. Ritorna True se esisteva."""
    with _lock:
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM prescriptions WHERE fiscal_code = ? AND nre = ?",
                (fiscal_code, nre)
            )
            conn.execute(
                "DELETE FROM previous_availabilities WHERE prescription_key = ?",
                (f"{fiscal_code}_{nre}",)
            )
            deleted = cursor.rowcount > 0
    if deleted:
        logger.info(f"Prescrizione rimossa: NRE {nre}")
    return deleted


def save_input_data(data):
    """
    Salva (upsert) le prescrizioni passate. Non cancella mai righe: per rimuovere
    una prescrizione usare delete_prescription(). Preferire update_prescription()
    per modificare una singola prescrizione.
    """
    with _lock:
        with get_connection() as conn:
            for prescription in data:
                conn.execute(
                    _UPSERT_PRESCRIPTION_SQL,
                    _prescription_params(prescription)
                    + (prescription.get("fiscal_code", ""), prescription.get("nre", ""))
                )
    logger.info(f"Dati delle prescrizioni salvati con successo ({len(data)} prescrizioni)")


# =============================================================================
# DISPONIBILITÀ PRECEDENTI
# =============================================================================

def load_previous_data():
    """Carica i dati di disponibilità precedenti dalla tabella previous_availabilities."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT prescription_key, availabilities FROM previous_availabilities"
        ).fetchall()
    return {row["prescription_key"]: json.loads(row["availabilities"]) for row in rows}


def save_previous_data(data):
    """Salva (upsert) le disponibilità per le chiavi passate, senza toccare le altre."""
    with _lock:
        with get_connection() as conn:
            for key, value in data.items():
                conn.execute(
                    """INSERT OR REPLACE INTO previous_availabilities
                       (prescription_key, availabilities, updated_at)
                       VALUES (?, ?, datetime('now'))""",
                    (key, json.dumps(value))
                )
    logger.info("Dati precedenti salvati con successo")


def prune_previous_data():
    """Rimuove le disponibilità salvate di prescrizioni che non esistono più."""
    with _lock:
        with get_connection() as conn:
            conn.execute(
                """DELETE FROM previous_availabilities
                   WHERE prescription_key NOT IN (
                       SELECT fiscal_code || '_' || nre FROM prescriptions
                   )"""
            )


# =============================================================================
# DATE
# Le date delle API RecUP sono in UTC ("2025-03-10T08:30:00Z").
# =============================================================================

def _parse_utc(date_string):
    """Parsa una data ISO delle API come datetime aware in UTC."""
    dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        # Senza fuso orario la data è già in ora italiana
        dt = dt.replace(tzinfo=_ROME)
    return dt.astimezone(timezone.utc)


def _parse_utc_to_rome(date_string):
    """Parsa una stringa UTC ISO e la converte al fuso orario di Roma (CET/CEST)."""
    return _parse_utc(date_string).astimezone(_ROME)


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
        date = _parse_utc(date_str)
        now = datetime.now(timezone.utc)
        limit_date = now + timedelta(days=30 * months_limit)
        return now <= date <= limit_date
    except Exception as e:
        logger.warning(f"Errore nel verificare l'intervallo di date: {str(e)}")
        return True


def is_similar_datetime(date1_str, date2_str, minutes_threshold=30):
    """Controlla se due date sono nello stesso giorno (ora italiana) ed entro un certo numero di minuti."""
    try:
        dt1 = _parse_utc_to_rome(date1_str)
        dt2 = _parse_utc_to_rome(date2_str)
        diff_minutes = abs((dt2 - dt1).total_seconds() / 60)
        return dt1.date() == dt2.date() and diff_minutes <= minutes_threshold
    except Exception:
        return False
