import json
import uuid
from datetime import datetime

from config import logger
from modules.reports_client import download_reports
from modules.database import get_connection, _lock
from modules.telegram_utils import esc, send_message_sync


# I monitoraggi sono salvati come lista JSON in un'unica riga di reports_monitoring.
# Ogni modifica rilegge la lista dentro una transazione (BEGIN IMMEDIATE), così bot
# e processo di monitoraggio non si sovrascrivono a vicenda.

def _read_items(conn):
    row = conn.execute(
        "SELECT data FROM reports_monitoring ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return json.loads(row["data"]) if row else []


def _ensure_ids(items):
    changed = False
    for item in items:
        if not item.get("id"):
            item["id"] = uuid.uuid4().hex[:10]
            changed = True
    return changed


def _write_items(conn, items):
    conn.execute("DELETE FROM reports_monitoring")
    conn.execute("INSERT INTO reports_monitoring (data) VALUES (?)", (json.dumps(items),))


def _mutate(fn):
    """Applica `fn(items)` alla lista aggiornata e la salva atomicamente. Ritorna il risultato di fn."""
    with _lock:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            items = _read_items(conn)
            _ensure_ids(items)
            result = fn(items)
            _write_items(conn, items)
    return result


def load_reports_monitoring():
    """Carica i monitoraggi referti (ogni elemento ha un `id` stabile)."""
    with get_connection() as conn:
        items = _read_items(conn)
    if any(not item.get("id") for item in items):
        # Dati salvati da versioni precedenti: assegniamo gli id una volta sola
        items = _mutate(lambda current: list(current))
    return items


def get_report_monitoring(item_id):
    """Ritorna il monitoraggio con l'id indicato, oppure None."""
    for item in load_reports_monitoring():
        if item.get("id") == item_id:
            return item
    return None


def add_report_monitoring(fiscal_code, password, tscns, telegram_chat_id, known_reports=None):
    """
    Aggiunge (o aggiorna) il monitoraggio referti per un codice fiscale di un utente.
    Ritorna l'id del monitoraggio.
    """
    def apply(items):
        for item in items:
            if item["fiscal_code"] == fiscal_code and str(item.get("telegram_chat_id")) == str(telegram_chat_id):
                item.update({
                    "password": password,
                    "tscns": tscns,
                    "enabled": True,
                    "known_reports": list(known_reports or []),
                    "seeded": True,
                })
                logger.info("Aggiornato monitoraggio referti esistente")
                return item["id"]

        new_item = {
            "id": uuid.uuid4().hex[:10],
            "fiscal_code": fiscal_code,
            "password": password,
            "tscns": tscns,
            "telegram_chat_id": telegram_chat_id,
            "enabled": True,
            "last_check": None,
            # Referti già presenti all'attivazione: non vanno notificati come nuovi
            "known_reports": list(known_reports or []),
            "seeded": True,
            "added_at": datetime.now().isoformat()
        }
        items.append(new_item)
        logger.info("Aggiunto nuovo monitoraggio referti")
        return new_item["id"]

    return _mutate(apply)


def remove_report_monitoring(item_id):
    """Rimuove un monitoraggio referti. Ritorna True se esisteva."""
    def apply(items):
        before = len(items)
        items[:] = [item for item in items if item.get("id") != item_id]
        return len(items) < before

    removed = _mutate(apply)
    if removed:
        logger.info(f"Rimosso monitoraggio referti {item_id}")
    return removed


def toggle_report_monitoring(item_id, enabled=None):
    """Attiva/disattiva un monitoraggio. Ritorna (trovato, nuovo_stato)."""
    def apply(items):
        for item in items:
            if item.get("id") == item_id:
                item["enabled"] = (not item.get("enabled", True)) if enabled is None else enabled
                return True, item["enabled"]
        return False, None

    found, state = _mutate(apply)
    if found:
        logger.info(f"Monitoraggio referti {item_id}: enabled={state}")
    return found, state


def mark_reports_known(item_id, report_ids):
    """Aggiunge gli id dei referti alla lista dei referti già noti."""
    def apply(items):
        for item in items:
            if item.get("id") == item_id:
                known = item.get("known_reports", [])
                item["known_reports"] = known + [r for r in report_ids if r not in known]
                return True
        return False

    return _mutate(apply)


def _format_report_date(doc_date):
    try:
        return datetime.strptime(doc_date, "%Y%m%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return doc_date


def check_new_reports(chat_id=None):
    """
    Verifica la disponibilità di nuovi referti per i monitoraggi attivi
    (tutti, oppure solo quelli dell'utente `chat_id`).
    Ritorna (monitoraggi_controllati, notifiche_inviate, errori).
    """
    logger.info("Avvio controllo disponibilità nuovi referti")

    monitoring_data = load_reports_monitoring()
    if chat_id is not None:
        monitoring_data = [m for m in monitoring_data if str(m.get("telegram_chat_id")) == str(chat_id)]

    if not monitoring_data:
        logger.info("Nessun monitoraggio referti configurato")
        return 0, 0, 0

    total_checked = 0
    total_notifications = 0
    errors = 0
    updates = {}

    for monitoring_item in monitoring_data:
        if not monitoring_item.get("enabled", True):
            continue

        item_id = monitoring_item["id"]
        fiscal_code = monitoring_item["fiscal_code"]
        known_reports = monitoring_item.get("known_reports", [])
        update = {"last_check": datetime.now().isoformat()}
        updates[item_id] = update

        try:
            reports = download_reports(fiscal_code, monitoring_item["password"], monitoring_item["tscns"])

            if reports is None:
                logger.warning("Impossibile recuperare i referti (credenziali o servizio non disponibile)")
                errors += 1
                continue

            total_checked += 1

            current_report_ids = [r.get("document_id") for r in reports if r.get("document_id")]

            if not monitoring_item.get("seeded"):
                # Monitoraggio creato da una versione precedente, senza elenco dei referti già
                # presenti: li registriamo senza notificare tutto lo storico come "nuovo"
                update["known_reports"] = current_report_ids
                update["seeded"] = True
                continue

            new_reports = [r for r in reports if r.get("document_id") and r.get("document_id") not in known_reports]

            if not new_reports:
                continue

            logger.info(f"Trovati {len(new_reports)} nuovi referti")

            message = (
                "<b>🔔 Nuovi Referti Disponibili!</b>\n\n"
                f"<b>Codice Fiscale:</b> <code>{esc(fiscal_code)}</code>\n"
                f"<b>Nuovi referti:</b> {len(new_reports)}\n\n"
                "<b>Elenco dei nuovi referti:</b>\n"
            )
            for i, report in enumerate(new_reports):
                provider = report.get("provider", "Struttura sconosciuta")
                doc_type = report.get("document_type", "Referto")
                formatted_date = _format_report_date(report.get("document_date", "Data sconosciuta"))
                message += f"{i+1}. <b>{esc(doc_type)}</b> - {esc(provider)} ({esc(formatted_date)})\n"
            message += "\nUsa <b>📋 Gestisci Monitoraggi Referti</b> per scaricare i nuovi referti."

            if send_message_sync(monitoring_item["telegram_chat_id"], message):
                update["known_reports"] = current_report_ids
                total_notifications += 1
            else:
                logger.error("Errore nell'invio della notifica referti")
                errors += 1

        except Exception as e:
            logger.error(f"Errore nel controllo referti: {str(e)}")
            errors += 1

    def apply(items):
        for item in items:
            update = updates.get(item.get("id"))
            if update:
                if "known_reports" in update:
                    known = item.get("known_reports", [])
                    update["known_reports"] = known + [r for r in update["known_reports"] if r not in known]
                item.update(update)

    if updates:
        _mutate(apply)

    logger.info(f"Controllo referti completato: {total_checked} controllati, {total_notifications} notifiche inviate, {errors} errori")
    return total_checked, total_notifications, errors
