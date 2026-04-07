import sqlite3
import threading
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger("Database")

DB_FILE = os.getenv("DB_FILE", "data/recup_monitor.db")

# Protegge scritture concorrenti all'interno dello stesso processo
# (cross-process è gestito da SQLite WAL + busy_timeout)
_lock = threading.Lock()


def _db_path():
    path = os.path.abspath(DB_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _new_conn():
    """Apre una connessione SQLite configurata."""
    conn = sqlite3.connect(
        _db_path(),
        check_same_thread=False,
        timeout=30  # attende fino a 30s se il DB è locked da un altro processo
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")  # 30s in ms per retrocompatibilità
    return conn


@contextmanager
def get_connection():
    """
    Context manager che apre, usa e chiude la connessione.
    Fa commit automatico su successo, rollback su eccezione.
    """
    conn = _new_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Crea lo schema del database e migra i dati da JSON se necessario."""
    path = _db_path()
    # Setta WAL mode una volta sola (persiste nel file)
    conn = _new_conn()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS prescriptions (
                fiscal_code TEXT NOT NULL,
                nre TEXT NOT NULL,
                telegram_chat_id INTEGER,
                notifications_enabled INTEGER DEFAULT 1,
                auto_book_enabled INTEGER DEFAULT 0,
                phone TEXT,
                email TEXT,
                description TEXT,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (fiscal_code, nre)
            );

            CREATE TABLE IF NOT EXISTS previous_availabilities (
                prescription_key TEXT PRIMARY KEY,
                availabilities TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS locations (
                key TEXT PRIMARY KEY,
                hospital TEXT,
                address TEXT,
                latitude REAL,
                longitude REAL
            );

            CREATE TABLE IF NOT EXISTS reports_monitoring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()

    logger.info("Schema database inizializzato")
    migrate_from_json()


def migrate_from_json():
    """Importa i dati dai file JSON esistenti se il DB è vuoto."""
    try:
        from config import (
            INPUT_FILE, PREVIOUS_DATA_FILE, USERS_FILE, REPORTS_MONITORING_FILE
        )
    except ImportError:
        INPUT_FILE = os.getenv("INPUT_FILE", "input_prescriptions.json")
        PREVIOUS_DATA_FILE = os.getenv("PREVIOUS_DATA_FILE", "previous_data.json")
        USERS_FILE = os.getenv("USERS_FILE", "authorized_users.json")
        REPORTS_MONITORING_FILE = os.getenv("REPORTS_MONITORING_FILE", "reports_monitoring.json")

    LOCATIONS_JSON = "locations.json"

    with _lock:
        conn = _new_conn()
        try:
            # users
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
                if os.path.exists(USERS_FILE):
                    try:
                        users = json.load(open(USERS_FILE))
                        for uid in users:
                            conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (str(uid),))
                        logger.info(f"Migrati {len(users)} utenti da {USERS_FILE}")
                    except Exception as e:
                        logger.error(f"Errore migrazione users: {e}")

            # prescriptions
            if conn.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0] == 0:
                if os.path.exists(INPUT_FILE):
                    try:
                        prescriptions = json.load(open(INPUT_FILE))
                        for p in prescriptions:
                            conn.execute(
                                """INSERT OR IGNORE INTO prescriptions
                                   (fiscal_code, nre, telegram_chat_id, notifications_enabled,
                                    auto_book_enabled, phone, email, description, data)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    p.get("fiscal_code", ""),
                                    p.get("nre", ""),
                                    p.get("telegram_chat_id"),
                                    1 if p.get("notifications_enabled", True) else 0,
                                    1 if p.get("auto_book_enabled", False) else 0,
                                    p.get("phone"),
                                    p.get("email"),
                                    p.get("description"),
                                    json.dumps(p),
                                )
                            )
                        logger.info(f"Migrate {len(prescriptions)} prescrizioni da {INPUT_FILE}")
                    except Exception as e:
                        logger.error(f"Errore migrazione prescriptions: {e}")

            # previous_availabilities
            if conn.execute("SELECT COUNT(*) FROM previous_availabilities").fetchone()[0] == 0:
                if os.path.exists(PREVIOUS_DATA_FILE):
                    try:
                        previous = json.load(open(PREVIOUS_DATA_FILE))
                        for key, value in previous.items():
                            conn.execute(
                                "INSERT OR IGNORE INTO previous_availabilities (prescription_key, availabilities) VALUES (?, ?)",
                                (key, json.dumps(value))
                            )
                        logger.info(f"Migrati {len(previous)} record disponibilità da {PREVIOUS_DATA_FILE}")
                    except Exception as e:
                        logger.error(f"Errore migrazione previous_availabilities: {e}")

            # locations
            if conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 0:
                if os.path.exists(LOCATIONS_JSON):
                    try:
                        locations = json.load(open(LOCATIONS_JSON, encoding="utf-8"))
                        for key, loc in locations.items():
                            conn.execute(
                                "INSERT OR IGNORE INTO locations (key, hospital, address, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
                                (key, loc.get("hospital"), loc.get("address"), loc.get("latitude"), loc.get("longitude"))
                            )
                        logger.info(f"Migrate {len(locations)} location da {LOCATIONS_JSON}")
                    except Exception as e:
                        logger.error(f"Errore migrazione locations: {e}")

            # reports_monitoring
            if conn.execute("SELECT COUNT(*) FROM reports_monitoring").fetchone()[0] == 0:
                if os.path.exists(REPORTS_MONITORING_FILE):
                    try:
                        reports = json.load(open(REPORTS_MONITORING_FILE))
                        if reports:
                            conn.execute("INSERT INTO reports_monitoring (data) VALUES (?)", (json.dumps(reports),))
                            logger.info(f"Migrati dati reports_monitoring da {REPORTS_MONITORING_FILE}")
                    except Exception as e:
                        logger.error(f"Errore migrazione reports_monitoring: {e}")

            conn.commit()
        finally:
            conn.close()

    logger.info("Migrazione da JSON completata")
