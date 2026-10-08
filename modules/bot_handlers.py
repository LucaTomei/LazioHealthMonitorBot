import re
import asyncio
import traceback
from datetime import datetime
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest, Conflict, NetworkError, TimedOut
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

from config import (
    logger, user_data, authorized_users, MAIN_KEYBOARD, ADMIN_KEYBOARD, is_admin,
    WAITING_FOR_FISCAL_CODE, WAITING_FOR_NRE, CONFIRM_ADD,
    WAITING_FOR_PRESCRIPTION_TO_DELETE, WAITING_FOR_PRESCRIPTION_TO_TOGGLE,
    WAITING_FOR_DATE_FILTER, WAITING_FOR_MONTHS_LIMIT, CONFIRM_DATE_FILTER,
    WAITING_FOR_BOOKING_CHOICE, WAITING_FOR_BOOKING_CONFIRMATION, WAITING_FOR_PHONE,
    WAITING_FOR_EMAIL, WAITING_FOR_SLOT_CHOICE, WAITING_FOR_BOOKING_TO_CANCEL,
    WAITING_FOR_AUTO_BOOK_CHOICE, AUTHORIZING,
    WAITING_FOR_PRESCRIPTION_BLACKLIST, WAITING_FOR_HOSPITAL_SELECTION,
    WAITING_FOR_BROADCAST_MESSAGE, WAITING_FOR_BROADCAST_CONFIRMATION,
    WAITING_FOR_FISCAL_CODE_REPORT, WAITING_FOR_PASSWORD_REPORT,
    WAITING_FOR_IMPORT_SOURCE
)
from modules.booking_client import booking_workflow, cancel_booking, get_user_bookings
from modules.data_utils import (
    save_authorized_users, count_authorized_users_in_db,
    load_input_data, get_prescription, add_prescription as db_add_prescription,
    update_prescription, delete_prescription,
    load_previous_data, save_previous_data,
    fmt_datetime
)
from modules.locations_db import load_locations_db
from modules.prescription_processor import process_prescription
from modules.reports_client import download_reports, download_report_document
from modules.reports_monitor import (
    load_reports_monitoring, get_report_monitoring, add_report_monitoring,
    remove_report_monitoring, toggle_report_monitoring, mark_reports_known,
    check_new_reports
)
from modules.telegram_utils import esc, split_message

# Numero massimo di slot mostrati in un messaggio (limite di 4096 caratteri di Telegram)
MAX_SLOTS_SHOWN = 20
HOSPITALS_PER_PAGE = 10

CANCEL_KEYBOARD = ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True)

MENU_BUTTONS = [
    "➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione",
    "📋 Lista Prescrizioni", "🔄 Verifica Disponibilità",
    "🔔 Gestisci Notifiche", "⏱ Imposta Filtro Date",
    "🏥 Prenota", "🤖 Prenota Automaticamente",
    "🚫 Blacklist Ospedali", "📝 Le mie Prenotazioni",
    "📊 Configura Monitoraggio Referti", "📋 Gestisci Monitoraggi Referti",
    "ℹ️ Informazioni", "🔑 Autorizza Utente", "📣 Messaggio Broadcast",
]
MENU_REGEX = "^(" + "|".join(re.escape(b) for b in MENU_BUTTONS) + ")$"

EMAIL_REGEX = re.compile(r"[^\s@<>&]+@[^\s@<>&]+\.[^\s@<>&]+")
PHONE_REGEX = re.compile(r"^[0-9+]{8,15}$")

# Sessioni dei flussi fuori dalle conversazioni (non devono sovrascrivere user_data)
quickbook_sessions = {}
report_sessions = {}


# =============================================================================
# UTILITY
# =============================================================================

def is_authorized(user_id):
    return str(user_id) in authorized_users


def _is_admin(user_id):
    return is_admin(user_id, authorized_users)


def _main_keyboard(user_id):
    return ADMIN_KEYBOARD if _is_admin(user_id) else MAIN_KEYBOARD


def _owns(item, user_id):
    return str(item.get("telegram_chat_id")) == str(user_id)


def _user_prescriptions(user_id):
    """Le prescrizioni visibili all'utente (tutte per l'admin)."""
    prescriptions = load_input_data()
    if _is_admin(user_id):
        return prescriptions
    return [p for p in prescriptions if _owns(p, user_id)]


def _description(prescription, default="Prescrizione"):
    return prescription.get("description") or default


def _session(user_id, *keys):
    """Ritorna la sessione dell'utente se contiene tutte le chiavi richieste, altrimenti None."""
    session = user_data.get(user_id)
    if session is None or any(key not in session for key in keys):
        return None
    return session


async def _session_expired(update: Update):
    """Risponde a un'interazione su una sessione non più valida e chiude la conversazione."""
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    text = "⚠️ Sessione scaduta. Ripeti l'operazione dal menu."
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text)
        except BadRequest:
            pass
    elif update.message:
        await update.message.reply_text(text, reply_markup=_main_keyboard(user_id))
    return ConversationHandler.END


async def run_blocking(func, *args, **kwargs):
    """Esegue una funzione bloccante (chiamate HTTP/DB) fuori dall'event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def _reply_long(message, text, reply_markup=None, parse_mode="HTML"):
    """Invia un testo lungo diviso in più messaggi; la tastiera va sull'ultimo."""
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        await message.reply_text(
            chunk,
            parse_mode=parse_mode,
            reply_markup=reply_markup if i == len(chunks) - 1 else None
        )


def _parse_index(callback_data, position=-1):
    try:
        return int(callback_data.split("_")[position])
    except (ValueError, IndexError):
        return None


def _format_slots(service, slots, intro):
    """Messaggio e tastiera per la scelta degli slot (al massimo MAX_SLOTS_SHOWN)."""
    shown = slots[:MAX_SLOTS_SHOWN]
    text = f"📋 <b>Disponibilità per {esc(service)}</b>\n\n{intro}\n\n"
    for i, slot in enumerate(shown):
        text += f"{i+1}. <b>{esc(fmt_datetime(slot['date']))}</b>\n"
        text += f"   🏥 {esc(slot['hospital'])}\n"
        text += f"   📍 {esc(slot['address'])}\n"
        text += f"   💰 {esc(slot['price'])}€\n\n"
    if len(slots) > len(shown):
        text += (f"…e altre {len(slots) - len(shown)} disponibilità più avanti nel tempo. "
                 "Usa il filtro date o la blacklist per restringere la ricerca.\n")
    return text, shown


def _slot_keyboard(count, prefix, cancel_data):
    keyboard, row = [], []
    for i in range(count):
        row.append(InlineKeyboardButton(f"{i+1}", callback_data=f"{prefix}{i}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data=cancel_data)])
    return InlineKeyboardMarkup(keyboard)


def _slot_confirmation_text(service, slot):
    return (
        "📅 <b>Conferma Prenotazione</b>\n\n"
        "Stai per prenotare:\n"
        f"<b>Servizio:</b> {esc(service)}\n"
        f"<b>Data:</b> {esc(fmt_datetime(slot['date']))}\n"
        f"<b>Ospedale:</b> {esc(slot['hospital'])}\n"
        f"<b>Indirizzo:</b> {esc(slot['address'])}\n"
        f"<b>Prezzo:</b> {esc(slot['price'])}€\n\n"
        "Confermi la prenotazione?"
    )


async def _complete_booking(context, query, user_id, prescription, result):
    """
    Gestisce l'esito positivo di una prenotazione: salva SUBITO la prenotazione
    (così il monitoraggio non prenota di nuovo) e poi avvisa l'utente.
    """
    booking_record = {
        "booking_id": result.get("booking_id"),
        "date": result["appointment_date"],
        "hospital": result["hospital"],
        "address": result["address"],
        "service": result["service"]
    }

    def add_booking(p):
        p.setdefault("bookings", []).append(booking_record)
        p["auto_book_enabled"] = False

    try:
        await run_blocking(update_prescription, prescription["fiscal_code"], prescription["nre"], add_booking)
    except Exception as e:
        logger.error(f"Prenotazione {result.get('booking_id')} effettuata ma non salvata: {str(e)}")

    formatted_date = fmt_datetime(result["appointment_date"])
    text = (
        "✅ <b>Prenotazione effettuata con successo!</b>\n\n"
        f"<b>Servizio:</b> {esc(result['service'])}\n"
        f"<b>Data:</b> {esc(formatted_date)}\n"
        f"<b>Ospedale:</b> {esc(result['hospital'])}\n"
        f"<b>Indirizzo:</b> {esc(result['address'])}\n"
        f"<b>ID Prenotazione:</b> {esc(result.get('booking_id') or 'non disponibile')}\n\n"
    )
    if result.get("pdf_content"):
        text += "Ti invio il documento di prenotazione."
    else:
        text += "⚠️ Il documento di prenotazione non è al momento scaricabile: lo trovi nell'app Salute Lazio."

    try:
        await query.edit_message_text(text, parse_mode="HTML")
    except BadRequest:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")

    if result.get("pdf_content"):
        try:
            await context.bot.send_document(
                chat_id=user_id,
                document=BytesIO(result["pdf_content"]),
                filename=f"prenotazione_{result.get('booking_id') or prescription['nre']}.pdf",
                caption=f"Documento di prenotazione per {result['service']} del {formatted_date}"[:1024]
            )
        except Exception as e:
            logger.error(f"Errore nell'invio del documento di prenotazione: {str(e)}")


# =============================================================================
# START E ANNULLA
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestore del comando /start."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text(
            "🔒 Non sei autorizzato ad utilizzare questo bot. Contatta l'amministratore per ottenere l'accesso."
        )
        logger.warning(f"Tentativo di accesso non autorizzato da {user_id}")
        return

    await update.message.reply_text(
        f"👋 Benvenuto, {update.effective_user.first_name}!\n\n"
        "Questo bot ti aiuterà a monitorare le disponibilità del Servizio Sanitario Nazionale.\n\n"
        "Utilizza i pulsanti sotto per gestire le prescrizioni da monitorare o per scaricare i tuoi referti.",
        reply_markup=_main_keyboard(user_id)
    )


async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulla l'operazione corrente e torna al menu principale."""
    user_id = update.effective_user.id if update.effective_user else None
    try:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("❌ Operazione annullata.")
        elif update.message:
            await update.message.reply_text(
                "❌ Operazione annullata. Cosa vuoi fare?",
                reply_markup=_main_keyboard(user_id)
            )
    except BadRequest as e:
        logger.debug(f"cancel_operation: {e}")
    finally:
        if user_id is not None:
            user_data.pop(user_id, None)
    return ConversationHandler.END


async def menu_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Un pulsante del menu premuto durante un'operazione la annulla e avvia quella scelta."""
    user_data.pop(update.effective_user.id, None)
    next_state = await handle_text(update, context)
    return next_state if next_state is not None else ConversationHandler.END


async def error_recovery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Messaggio inatteso durante una conversazione che si aspetta un pulsante."""
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    await update.message.reply_text(
        "⚠️ Operazione interrotta: era atteso uno dei pulsanti del messaggio precedente. "
        "Seleziona un'operazione dal menu.",
        reply_markup=_main_keyboard(user_id)
    )
    return ConversationHandler.END


async def stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pulsanti di messaggi vecchi che non appartengono più a nessuna operazione attiva."""
    try:
        await update.callback_query.answer(
            "Questo pulsante non è più valido. Ripeti l'operazione dal menu.", show_alert=True
        )
    except BadRequest:
        pass


# =============================================================================
# PRESCRIZIONI: AGGIUNTA
# =============================================================================

async def add_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'aggiunta di una nuova prescrizione."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    await update.message.reply_text(
        "Per aggiungere una nuova prescrizione da monitorare, ho bisogno di alcune informazioni.\n\n"
        "Per prima cosa, inserisci il codice fiscale del paziente:",
        reply_markup=CANCEL_KEYBOARD
    )

    user_data[user_id] = {"action": "add_prescription"}
    return WAITING_FOR_FISCAL_CODE


async def handle_fiscal_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del codice fiscale."""
    user_id = update.effective_user.id
    session = _session(user_id)
    if session is None:
        return await _session_expired(update)

    fiscal_code = update.message.text.strip().upper()

    if not re.match("^[A-Z0-9]{16}$", fiscal_code):
        await update.message.reply_text(
            "⚠️ Il codice fiscale inserito non sembra valido. Deve essere composto da 16 caratteri alfanumerici.\n\n"
            "Per favore, riprova o scrivi ❌ Annulla per tornare al menu principale:"
        )
        return WAITING_FOR_FISCAL_CODE

    session["fiscal_code"] = fiscal_code

    await update.message.reply_text(
        f"Codice fiscale: {fiscal_code}\n\n"
        "Ora inserisci il codice NRE della prescrizione (numero di ricetta elettronica):",
        reply_markup=CANCEL_KEYBOARD
    )
    return WAITING_FOR_NRE


async def handle_nre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del codice NRE."""
    user_id = update.effective_user.id
    session = _session(user_id, "fiscal_code")
    if session is None:
        return await _session_expired(update)

    nre = update.message.text.strip().upper()

    if not re.match("^[A-Z0-9]{15}$", nre):
        await update.message.reply_text(
            "⚠️ Il codice NRE inserito non sembra valido. Deve essere composto da 15 caratteri alfanumerici.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_NRE

    if await run_blocking(get_prescription, session["fiscal_code"], nre):
        await update.message.reply_text(
            "⚠️ Questa prescrizione è già presente nel sistema. Non è possibile aggiungerla di nuovo.",
            reply_markup=_main_keyboard(user_id)
        )
        user_data.pop(user_id, None)
        return ConversationHandler.END

    session["nre"] = nre

    await update.message.reply_text(
        f"Codice NRE: {nre}\n\n"
        "Ora inserisci il tuo numero di telefono per eventuali prenotazioni automatiche:",
        reply_markup=CANCEL_KEYBOARD
    )
    return WAITING_FOR_PHONE


async def handle_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del numero di telefono (aggiunta prescrizione o prenotazione)."""
    user_id = update.effective_user.id
    session = _session(user_id)
    if session is None:
        return await _session_expired(update)

    phone = update.message.text.strip().replace(" ", "")

    if not PHONE_REGEX.match(phone):
        await update.message.reply_text(
            "⚠️ Il numero di telefono inserito non sembra valido. Deve contenere almeno 8 cifre.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_PHONE

    session["phone"] = phone

    if session.get("action") == "add_prescription":
        prompt = "Ora inserisci la tua email per eventuali prenotazioni automatiche:"
    else:
        prompt = "Ora inserisci la tua email:"

    await update.message.reply_text(
        f"Numero di telefono: {phone}\n\n{prompt}",
        reply_markup=CANCEL_KEYBOARD
    )
    return WAITING_FOR_EMAIL


async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Smista l'email al flusso corretto (aggiunta prescrizione o prenotazione)."""
    session = _session(update.effective_user.id)
    if session is None:
        return await _session_expired(update)
    if session.get("action") == "add_prescription":
        return await handle_add_email(update, context)
    return await handle_email(update, context)


async def handle_add_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input dell'email durante l'aggiunta di prescrizione."""
    user_id = update.effective_user.id
    session = _session(user_id, "fiscal_code", "nre", "phone")
    if session is None:
        return await _session_expired(update)

    email = update.message.text.strip()

    if not EMAIL_REGEX.fullmatch(email):
        await update.message.reply_text(
            "⚠️ L'email inserita non sembra valida.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_EMAIL

    session["email"] = email

    await update.message.reply_text(
        "Stai per aggiungere una nuova prescrizione con i seguenti dati:\n\n"
        f"Codice Fiscale: {session['fiscal_code']}\n"
        f"NRE: {session['nre']}\n"
        f"Telefono: {session['phone']}\n"
        f"Email: {email}\n\n"
        "Confermi?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sì, aggiungi", callback_data="confirm_add"),
            InlineKeyboardButton("❌ No, annulla", callback_data="cancel_add")
        ]])
    )
    return CONFIRM_ADD


async def confirm_add_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma dell'aggiunta di una prescrizione."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_add":
        await query.edit_message_text("❌ Operazione annullata.")
        user_data.pop(user_id, None)
        await context.bot.send_message(chat_id=user_id, text="Cosa vuoi fare?", reply_markup=_main_keyboard(user_id))
        return ConversationHandler.END

    session = _session(user_id, "fiscal_code", "nre", "phone", "email")
    if session is None:
        return await _session_expired(update)
    user_data.pop(user_id, None)

    fiscal_code = session["fiscal_code"]
    nre = session["nre"]

    new_prescription = {
        "fiscal_code": fiscal_code,
        "nre": nre,
        "telegram_chat_id": user_id,
        "notifications_enabled": True,
        "auto_book_enabled": False,
        "phone": session["phone"],
        "email": session["email"],
        "config": {
            "only_new_dates": True,
            "notify_removed": False,
            "min_changes_to_notify": 1,
            "time_threshold_minutes": 60,
            "show_all_current": True,
            "months_limit": None
        }
    }

    # La prescrizione viene sempre salvata: se ora non è prenotabile o non ci sono
    # disponibilità, il monitoraggio continuerà a controllarla
    if not await run_blocking(db_add_prescription, new_prescription):
        await query.edit_message_text("⚠️ Questa prescrizione è già presente nel sistema.")
        await context.bot.send_message(chat_id=user_id, text="Cosa vuoi fare?", reply_markup=_main_keyboard(user_id))
        return ConversationHandler.END

    await query.edit_message_text("⏳ Prescrizione salvata. Verifica delle disponibilità in corso, attendere...")

    prescription_key = f"{fiscal_code}_{nre}"
    previous_data = {}
    try:
        success, message = await run_blocking(process_prescription, new_prescription, previous_data, user_id)
    except Exception as e:
        logger.error(f"Errore nella verifica iniziale della prescrizione: {str(e)}")
        success, message = False, "verifica temporaneamente non riuscita"

    if prescription_key in previous_data:
        try:
            await run_blocking(save_previous_data, {prescription_key: previous_data[prescription_key]})
        except Exception as e:
            logger.error(f"Errore nel salvare le disponibilità iniziali: {str(e)}")

    if success:
        status = "Riceverai notifiche quando saranno disponibili nuovi appuntamenti."
    else:
        status = (f"ℹ️ Al momento: {message}.\n"
                  "Il bot continuerà comunque a controllarla periodicamente e ti avviserà "
                  "appena trova disponibilità.\n\n"
                  "Se il codice fiscale o l'NRE fossero errati, rimuovila da '➖ Rimuovi Prescrizione' "
                  "e aggiungila di nuovo.")

    await query.edit_message_text(
        "✅ Prescrizione aggiunta con successo!\n\n"
        f"Descrizione: {new_prescription.get('description', 'Non ancora disponibile')}\n"
        f"Codice Fiscale: {fiscal_code}\n"
        f"NRE: {nre}\n\n"
        f"{status}"
    )

    await context.bot.send_message(
        chat_id=user_id,
        text="💡 Suggerimento: puoi attivare la prenotazione automatica usando la funzione '🤖 Prenota Automaticamente' "
             "per prenotare automaticamente il primo slot disponibile.",
        reply_markup=_main_keyboard(user_id)
    )
    return ConversationHandler.END


# =============================================================================
# PRESCRIZIONI: RIMOZIONE
# =============================================================================

async def remove_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la rimozione di una prescrizione."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    user_prescriptions = await run_blocking(_user_prescriptions, user_id)
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da rimuovere.")
        return ConversationHandler.END

    keyboard = []
    for idx, prescription in enumerate(user_prescriptions):
        desc = _description(prescription)
        keyboard.append([InlineKeyboardButton(
            f"{idx+1}. {desc[:30]}... ({prescription['fiscal_code'][-4:]})",
            callback_data=f"remove_{idx}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_remove")])

    user_data[user_id] = {"action": "remove_prescription", "prescriptions": user_prescriptions}

    await update.message.reply_text(
        "Seleziona la prescrizione da rimuovere:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_PRESCRIPTION_TO_DELETE


async def handle_prescription_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prescrizione da rimuovere."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_remove":
        return await cancel_operation(update, context)

    session = _session(user_id, "prescriptions")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["prescriptions"]):
        return await _session_expired(update)

    prescription = session["prescriptions"][idx]
    user_data.pop(user_id, None)

    removed = await run_blocking(delete_prescription, prescription["fiscal_code"], prescription["nre"])
    if removed:
        await query.edit_message_text(
            "✅ Prescrizione rimossa con successo!\n\n"
            f"Descrizione: {prescription.get('description', 'Non disponibile')}\n"
            f"Codice Fiscale: {prescription['fiscal_code']}\n"
            f"NRE: {prescription['nre']}"
        )
    else:
        await query.edit_message_text("⚠️ La prescrizione non è più presente.")
    return ConversationHandler.END


# =============================================================================
# PRESCRIZIONI: LISTA E VERIFICA
# =============================================================================

async def list_prescriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra la lista delle prescrizioni monitorate."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    admin = _is_admin(user_id)
    prescriptions = await run_blocking(_user_prescriptions, user_id)

    if not prescriptions:
        await update.message.reply_text(
            "Non ci sono prescrizioni in monitoraggio." if admin else "Non hai prescrizioni in monitoraggio."
        )
        return

    message = ("📋 <b>Tutte le prescrizioni monitorate:</b>\n\n" if admin
               else "📋 <b>Le tue prescrizioni monitorate:</b>\n\n")

    for idx, prescription in enumerate(prescriptions):
        config = prescription.get("config") or {}
        has_booking = bool(prescription.get("bookings"))
        months_limit = config.get("months_limit")
        hospitals_blacklist = config.get("hospitals_blacklist", [])
        team_card_code = ((prescription.get("patient_info") or {}).get("teamCard") or {}).get("code", "")

        user_info = ""
        if admin and "telegram_chat_id" in prescription:
            user_info = f" (User ID: {esc(prescription['telegram_chat_id'])})"

        message += f"{idx+1}. <b>{esc(_description(prescription, 'Prescrizione sconosciuta'))}</b>{user_info}\n"
        message += f"   Stato: {'📑 Prenotata' if has_booking else '🔍 In monitoraggio'}\n"
        message += f"   Codice Fiscale: <code>{esc(prescription['fiscal_code'])}</code>\n"
        message += f"   NRE: <code>{esc(prescription['nre'])}</code>\n"
        if team_card_code and team_card_code != "N/A":
            message += f"   Tessera Sanitaria: <code>{esc(team_card_code)}</code>\n"
        if prescription.get("phone") and prescription.get("email"):
            message += f"   📞 Telefono: {esc(prescription['phone'])}\n"
            message += f"   📧 Email: {esc(prescription['email'])}\n"
        message += (f"   🚫 {len(hospitals_blacklist)} ospedali esclusi\n" if hospitals_blacklist
                    else "   🚫 nessun ospedale escluso\n")

        if not has_booking:
            notification_status = "🔔 attive" if prescription.get("notifications_enabled", True) else "🔕 disattivate"
            date_filter = f"⏱ entro {months_limit} mesi" if months_limit else "⏱ nessun filtro date"
            auto_book_status = "🤖 attiva" if prescription.get("auto_book_enabled", False) else "🤖 disattivata"
            message += f"   Notifiche: {notification_status} | {date_filter}\n"
            message += f"   Prenotazione automatica: {auto_book_status}\n"
        else:
            for booking in prescription.get("bookings", []):
                message += (f"   🏥 Prenotato per: {esc(fmt_datetime(booking.get('date', '')))} "
                            f"presso {esc(booking.get('hospital', 'N/D'))}\n")
                message += f"   🆔 ID Prenotazione: {esc(booking.get('booking_id') or 'non disponibile')}\n"
        message += "\n"

    await _reply_long(update.message, message)


async def check_availability(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica immediatamente la disponibilità delle prescrizioni."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    admin = _is_admin(user_id)
    prescriptions = await run_blocking(_user_prescriptions, user_id)
    if not prescriptions:
        await update.message.reply_text(
            "Non ci sono prescrizioni da verificare." if admin else "Non hai prescrizioni da verificare."
        )
        return

    await update.message.reply_text("🔍 Sto verificando le disponibilità... Potrebbe richiedere alcuni minuti.")

    previous_data = await run_blocking(load_previous_data)
    num_processed = 0

    for prescription in prescriptions:
        prescription_key = f"{prescription['fiscal_code']}_{prescription['nre']}"
        # Forziamo l'invio del riepilogo anche senza cambiamenti
        config = dict(prescription.get("config") or {})
        config["min_changes_to_notify"] = 0
        prescription["config"] = config

        try:
            success, _ = await run_blocking(process_prescription, prescription, previous_data, user_id)
            if success:
                num_processed += 1
        except Exception as e:
            logger.error(f"Errore nella verifica della prescrizione NRE {prescription['nre']}: {str(e)}")

        if prescription_key in previous_data:
            try:
                await run_blocking(save_previous_data, {prescription_key: previous_data[prescription_key]})
            except Exception as e:
                logger.error(f"Errore nel salvare le disponibilità: {str(e)}")

        await asyncio.sleep(1)

    await update.message.reply_text(
        f"✅ Verifica completata! {num_processed}/{len(prescriptions)} prescrizioni processate.\n\n"
        "Se sono state trovate disponibilità, riceverai dei messaggi separati con i dettagli."
    )


# =============================================================================
# NOTIFICHE
# =============================================================================

async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abilita o disabilita le notifiche per una prescrizione."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    user_prescriptions = await run_blocking(_user_prescriptions, user_id)
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END

    keyboard = []
    for idx, prescription in enumerate(user_prescriptions):
        status = "🔔 ON" if prescription.get("notifications_enabled", True) else "🔕 OFF"
        keyboard.append([InlineKeyboardButton(
            f"{idx+1}. {_description(prescription)[:25]}... ({status})",
            callback_data=f"toggle_{idx}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_toggle")])

    user_data[user_id] = {"action": "toggle_notifications", "prescriptions": user_prescriptions}

    await update.message.reply_text(
        "Seleziona la prescrizione per cui vuoi attivare/disattivare le notifiche:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_PRESCRIPTION_TO_TOGGLE


async def handle_prescription_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prescrizione per cui attivare/disattivare le notifiche."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_toggle":
        return await cancel_operation(update, context)

    session = _session(user_id, "prescriptions")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["prescriptions"]):
        return await _session_expired(update)

    selected = session["prescriptions"][idx]
    user_data.pop(user_id, None)

    def toggle(p):
        p["notifications_enabled"] = not p.get("notifications_enabled", True)

    updated = await run_blocking(update_prescription, selected["fiscal_code"], selected["nre"], toggle)
    if updated is None:
        await query.edit_message_text("⚠️ La prescrizione non è più presente.")
        return ConversationHandler.END

    status_text = "attivate ✅" if updated["notifications_enabled"] else "disattivate ❌"
    await query.edit_message_text(
        f"✅ Notifiche {status_text} per:\n\n"
        f"Descrizione: {selected.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {selected['fiscal_code']}\n"
        f"NRE: {selected['nre']}"
    )
    return ConversationHandler.END


# =============================================================================
# PRENOTAZIONI
# =============================================================================

async def book_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la prenotazione di una prescrizione."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    user_prescriptions = await run_blocking(_user_prescriptions, user_id)
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da prenotare.")
        return ConversationHandler.END

    message = "🏥 <b>Prenotazione</b>\n\nSeleziona la prescrizione da prenotare:\n\n"
    for idx, prescription in enumerate(user_prescriptions):
        message += f"{idx+1}. <b>{esc(_description(prescription))}</b>\n"
        message += (f"   CF: <code>{esc(prescription['fiscal_code'])}</code> • "
                    f"NRE: <code>{esc(prescription['nre'])}</code>\n\n")

    keyboard = [[InlineKeyboardButton(f"{idx+1}", callback_data=f"book_{idx}")]
                for idx in range(len(user_prescriptions))]
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_booking")])

    user_data[user_id] = {"action": "book_prescription", "prescriptions": user_prescriptions}

    chunks = split_message(message)
    for i, chunk in enumerate(chunks):
        await update.message.reply_text(
            chunk,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard) if i == len(chunks) - 1 else None
        )
    return WAITING_FOR_BOOKING_CHOICE


async def _show_slots(user_id, session, edit, send_new):
    """Cerca le disponibilità per la prescrizione selezionata e mostra gli slot."""
    prescription = session["selected_prescription"]
    result = await run_blocking(
        booking_workflow,
        fiscal_code=prescription["fiscal_code"],
        nre=prescription["nre"],
        phone_number=session["phone"],
        email=session["email"],
        slot_choice=-1
    )

    if not (result.get("success") and result.get("action") == "list_slots") or not result.get("slots"):
        msg = result.get("message") or "Nessuna disponibilità trovata per questa prescrizione."
        if "filtri" in msg or "blacklist" in msg or "Nessuna disponibilità" in msg:
            text = f"ℹ️ {esc(msg)}\n\nProva a modificare la blacklist o il filtro date per questa prescrizione."
        else:
            text = f"⚠️ {esc(msg)}"
        await edit(text)
        user_data.pop(user_id, None)
        await send_new("Cosa vuoi fare?", _main_keyboard(user_id))
        return ConversationHandler.END

    text, shown = _format_slots(
        result.get("service", "Prestazione"), result["slots"],
        "Seleziona un numero per prenotare lo slot corrispondente:"
    )
    result["slots"] = shown
    session["booking_details"] = result
    await edit(text, _slot_keyboard(len(shown), "slot_", "cancel_slot"))
    return WAITING_FOR_SLOT_CHOICE


async def handle_booking_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session = _session(user_id, "prescriptions")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["prescriptions"]):
        return await _session_expired(update)

    prescription = session["prescriptions"][idx]
    session["selected_prescription"] = prescription

    if not (prescription.get("phone") and prescription.get("email")):
        await query.edit_message_text(f"Hai selezionato: {_description(prescription, 'N/D')}")
        await context.bot.send_message(
            chat_id=user_id, text="Inserisci il tuo numero di telefono:", reply_markup=CANCEL_KEYBOARD
        )
        return WAITING_FOR_PHONE

    session["phone"] = prescription["phone"]
    session["email"] = prescription["email"]

    await query.edit_message_text("🔍 Sto cercando le disponibilità...")

    async def edit(text, markup=None):
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

    async def send_new(text, markup):
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)

    return await _show_slots(user_id, session, edit, send_new)


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input dell'email nel flusso di prenotazione."""
    user_id = update.effective_user.id
    session = _session(user_id, "selected_prescription", "phone")
    if session is None:
        return await _session_expired(update)

    email = update.message.text.strip()
    if not EMAIL_REGEX.fullmatch(email):
        await update.message.reply_text("⚠️ L'email inserita non sembra valida.\n\nPer favore, riprova:")
        return WAITING_FOR_EMAIL

    session["email"] = email
    prescription = session["selected_prescription"]

    # Salviamo i contatti nella prescrizione: servono anche per la prenotazione automatica
    def set_contacts(p):
        p["phone"] = session["phone"]
        p["email"] = email

    try:
        await run_blocking(update_prescription, prescription["fiscal_code"], prescription["nre"], set_contacts)
    except Exception as e:
        logger.error(f"Errore nel salvare i contatti della prescrizione: {str(e)}")

    # Ripristiniamo la tastiera principale al posto di quella "❌ Annulla"
    await update.message.reply_text(
        "🔍 Sto cercando le disponibilità... Attendi un momento.",
        reply_markup=_main_keyboard(user_id)
    )

    async def edit(text, markup=None):
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")

    async def send_new(text, markup):
        pass  # la tastiera principale è già stata ripristinata

    return await _show_slots(user_id, session, edit, send_new)


async def handle_slot_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della disponibilità."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_slot":
        return await cancel_operation(update, context)

    session = _session(user_id, "booking_details", "selected_prescription")
    slot_idx = _parse_index(query.data)
    if session is None or slot_idx is None or not 0 <= slot_idx < len(session["booking_details"]["slots"]):
        return await _session_expired(update)

    booking_details = session["booking_details"]
    selected_slot = booking_details["slots"][slot_idx]

    await query.edit_message_text(
        _slot_confirmation_text(booking_details["service"], selected_slot),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sì, prenota", callback_data=f"confirm_slot_{slot_idx}"),
            InlineKeyboardButton("❌ No, annulla", callback_data="cancel_slot")
        ]]),
        parse_mode="HTML"
    )
    return WAITING_FOR_BOOKING_CONFIRMATION


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma della prenotazione."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_slot":
        return await cancel_operation(update, context)

    session = _session(user_id, "booking_details", "selected_prescription", "phone", "email")
    slot_idx = _parse_index(query.data)
    if session is None or slot_idx is None or not 0 <= slot_idx < len(session["booking_details"]["slots"]):
        return await _session_expired(update)

    # La sessione viene chiusa subito: un doppio click non può prenotare due volte
    user_data.pop(user_id, None)
    booking_details = session["booking_details"]
    prescription = session["selected_prescription"]
    slot = booking_details["slots"][slot_idx]

    await query.edit_message_text("🔄 Sto effettuando la prenotazione... Attendi un momento.")

    result = await run_blocking(
        booking_workflow,
        fiscal_code=prescription["fiscal_code"],
        nre=prescription["nre"],
        phone_number=session["phone"],
        email=session["email"],
        patient_id=booking_details.get("patient_id"),
        process_id=booking_details.get("process_id"),
        slot_date=slot["date"],
        diary_id=slot.get("diary_id")
    )

    if not (result.get("success") and result.get("action") == "booked"):
        await query.edit_message_text(f"❌ Errore nella prenotazione: {result.get('message', 'Errore sconosciuto')}")
        return ConversationHandler.END

    await _complete_booking(context, query, user_id, prescription, result)
    return ConversationHandler.END


def _api_booking_info(booking, prescription):
    services = booking.get("services") or [{}]
    return {
        "booking_id": booking.get("id"),
        "date": booking.get("startTime") or "",
        "hospital": (booking.get("hospital") or {}).get("name") or "Ospedale non disponibile",
        "address": (booking.get("site") or {}).get("address") or "Indirizzo non disponibile",
        "service": (services[0] or {}).get("description") or "Servizio non disponibile",
        "prescription": prescription,
        "from_api": True
    }


def _collect_bookings(user_id):
    """Prenotazioni salvate dal bot più quelle presenti su RecUP per i codici fiscali dell'utente."""
    user_prescriptions = _user_prescriptions(user_id)
    all_bookings = []
    known_ids = set()

    for prescription in user_prescriptions:
        for booking in prescription.get("bookings") or []:
            all_bookings.append({
                "booking_id": booking.get("booking_id"),
                "date": booking.get("date") or "",
                "hospital": booking.get("hospital", "N/D"),
                "address": booking.get("address", "Indirizzo non disponibile"),
                "service": booking.get("service", "N/D"),
                "prescription": prescription
            })
            if booking.get("booking_id"):
                known_ids.add(str(booking["booking_id"]))

    seen_fiscal_codes = set()
    for prescription in user_prescriptions:
        fiscal_code = prescription["fiscal_code"]
        if fiscal_code in seen_fiscal_codes:
            continue
        seen_fiscal_codes.add(fiscal_code)
        result = get_user_bookings(fiscal_code)
        if not result.get("success"):
            continue
        for booking in result.get("bookings") or []:
            if booking.get("id") and str(booking["id"]) not in known_ids:
                known_ids.add(str(booking["id"]))
                all_bookings.append(_api_booking_info(booking, prescription))

    all_bookings.sort(key=lambda b: b["date"] or "")
    return all_bookings


async def list_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra le prenotazioni attive dell'utente."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    loading_message = await update.message.reply_text("🔍 Sto cercando le prenotazioni... Attendi un momento.")
    all_bookings = await run_blocking(_collect_bookings, user_id)
    await loading_message.delete()

    if not all_bookings:
        await update.message.reply_text("📝 Non ci sono prenotazioni attive.")
        return

    message = "📝 <b>Le tue prenotazioni attive:</b>\n\n"
    for idx, booking in enumerate(all_bookings):
        message += f"{idx+1}. <b>{esc(booking['service'])}</b>\n"
        message += f"   📅 Data: {esc(fmt_datetime(booking['date']))}\n"
        message += f"   🏥 Ospedale: {esc(booking['hospital'])}\n"
        message += f"   📍 Indirizzo: {esc(booking['address'])}\n"
        message += f"   🆔 ID: {esc(booking['booking_id'] or 'non disponibile')}\n\n"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Disdici una prenotazione", callback_data="cancel_appointment")]])
    await _reply_long(update.message, message, reply_markup=keyboard)


async def start_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia il processo di cancellazione di una prenotazione."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_authorized(user_id):
        await query.edit_message_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return ConversationHandler.END

    await query.edit_message_reply_markup(reply_markup=None)
    status_message = await context.bot.send_message(chat_id=user_id, text="🔍 Sto cercando le prenotazioni... Attendi un momento.")

    all_bookings = [b for b in await run_blocking(_collect_bookings, user_id) if b.get("booking_id")]
    if not all_bookings:
        await status_message.edit_text("📝 Non ci sono prenotazioni attive da disdire.")
        return ConversationHandler.END

    user_data[user_id] = {"action": "cancel_booking", "bookings": all_bookings}

    keyboard = [
        [InlineKeyboardButton(
            f"{idx+1}. {booking['service'][:30]} - {fmt_datetime(booking['date'])}",
            callback_data=f"cancel_book_{idx}"
        )]
        for idx, booking in enumerate(all_bookings[:30])
    ]
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_cancel_book")])

    await status_message.edit_text(
        "Seleziona la prenotazione da disdire:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_BOOKING_TO_CANCEL


async def handle_booking_to_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prenotazione da disdire."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session = _session(user_id, "bookings")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["bookings"]):
        return await _session_expired(update)

    booking = session["bookings"][idx]
    await query.edit_message_text(
        "⚠️ <b>Sei sicuro di voler disdire questa prenotazione?</b>\n\n"
        f"<b>Servizio:</b> {esc(booking['service'])}\n"
        f"<b>Data:</b> {esc(fmt_datetime(booking['date']))}\n"
        f"<b>Ospedale:</b> {esc(booking['hospital'])}\n"
        f"<b>ID Prenotazione:</b> {esc(booking['booking_id'])}\n\n"
        "Questa operazione è <b>irreversibile</b>!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sì, disdici", callback_data=f"confirm_cancel_{idx}"),
            InlineKeyboardButton("❌ No, annulla", callback_data="cancel_cancel_book")
        ]]),
        parse_mode="HTML"
    )
    return WAITING_FOR_BOOKING_TO_CANCEL


async def confirm_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma della disdetta della prenotazione."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session = _session(user_id, "bookings")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["bookings"]):
        return await _session_expired(update)

    user_data.pop(user_id, None)
    booking = session["bookings"][idx]
    booking_id = booking["booking_id"]

    await query.edit_message_text("🔄 Sto disdendo la prenotazione... Attendi un momento.")

    try:
        await run_blocking(cancel_booking, booking_id)
    except Exception as e:
        logger.error(f"Errore nella cancellazione della prenotazione: {str(e)}")
        await query.edit_message_text(f"❌ Errore nella disdetta della prenotazione: {esc(str(e))}")
        return ConversationHandler.END

    def remove_booking(p):
        p["bookings"] = [b for b in p.get("bookings") or [] if str(b.get("booking_id")) != str(booking_id)]

    try:
        for prescription in await run_blocking(_user_prescriptions, user_id):
            if any(str(b.get("booking_id")) == str(booking_id) for b in prescription.get("bookings") or []):
                await run_blocking(update_prescription, prescription["fiscal_code"], prescription["nre"], remove_booking)
    except Exception as e:
        logger.error(f"Prenotazione disdetta ma non rimossa dai dati locali: {str(e)}")

    await query.edit_message_text(
        "✅ <b>Prenotazione disdetta con successo!</b>\n\n"
        f"La prenotazione per {esc(booking['service'])} è stata disdetta.",
        parse_mode="HTML"
    )
    return ConversationHandler.END


# =============================================================================
# PRENOTAZIONE RAPIDA DALLE NOTIFICHE
# =============================================================================

async def handle_quickbook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il pulsante 'Prenota subito' nelle notifiche di monitoraggio."""
    query = update.callback_query
    user_id = query.from_user.id

    if not is_authorized(user_id):
        await query.answer("🔒 Non sei autorizzato ad utilizzare questa funzione.", show_alert=True)
        return
    await query.answer()

    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await context.bot.send_message(chat_id=user_id, text="⚠️ Dati prenotazione non validi.")
        return
    fiscal_code, nre = parts[1], parts[2]

    prescription = await run_blocking(get_prescription, fiscal_code, nre)
    if not prescription or not (_owns(prescription, user_id) or _is_admin(user_id)):
        await context.bot.send_message(chat_id=user_id, text="⚠️ Prescrizione non trovata.")
        return

    if not prescription.get("phone") or not prescription.get("email"):
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Per prenotare serve telefono ed email. Aggiungili dalla sezione '🏥 Prenota'."
        )
        return

    loading = await context.bot.send_message(chat_id=user_id, text="🔍 Ricerca disponibilità in corso...")

    result = await run_blocking(
        booking_workflow,
        fiscal_code=fiscal_code,
        nre=nre,
        phone_number=prescription["phone"],
        email=prescription["email"],
        slot_choice=-1
    )

    if not (result.get("success") and result.get("action") == "list_slots") or not result.get("slots"):
        msg = result.get("message") or "Nessuna disponibilità trovata per questa prescrizione."
        prefix = "ℹ️" if ("filtri" in msg or "blacklist" in msg or "Nessuna" in msg) else "⚠️"
        await loading.edit_text(f"{prefix} {msg}")
        return

    text, shown = _format_slots(result.get("service", "Prestazione"), result["slots"], "Seleziona un numero per prenotare:")
    result["slots"] = shown
    quickbook_sessions[user_id] = {"prescription": prescription, "booking_details": result}

    await loading.edit_text(text, reply_markup=_slot_keyboard(len(shown), "qslot_", "cancel_qslot"), parse_mode="HTML")


async def handle_quickslot_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione dello slot dal flusso quickbook (fuori dal ConversationHandler)."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_qslot":
        quickbook_sessions.pop(user_id, None)
        await query.edit_message_text("❌ Operazione annullata.")
        return

    session = quickbook_sessions.get(user_id)
    slot_idx = _parse_index(query.data)
    if not session or slot_idx is None or not 0 <= slot_idx < len(session["booking_details"]["slots"]):
        await query.edit_message_text("⚠️ Sessione scaduta. Riprova.")
        return

    booking_details = session["booking_details"]
    await query.edit_message_text(
        _slot_confirmation_text(booking_details["service"], booking_details["slots"][slot_idx]),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sì, prenota", callback_data=f"confirm_qslot_{slot_idx}"),
            InlineKeyboardButton("❌ No, annulla", callback_data="cancel_qslot")
        ]]),
        parse_mode="HTML"
    )


async def handle_quickbook_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma ed esegue la prenotazione dal flusso quickbook."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session = quickbook_sessions.pop(user_id, None)
    slot_idx = _parse_index(query.data)
    if not session or not is_authorized(user_id) or slot_idx is None \
            or not 0 <= slot_idx < len(session["booking_details"]["slots"]):
        await query.edit_message_text("⚠️ Sessione scaduta. Riprova.")
        return

    prescription = session["prescription"]
    booking_details = session["booking_details"]
    slot = booking_details["slots"][slot_idx]

    await query.edit_message_text("🔄 Sto effettuando la prenotazione... Attendi un momento.")

    result = await run_blocking(
        booking_workflow,
        fiscal_code=prescription["fiscal_code"],
        nre=prescription["nre"],
        phone_number=prescription["phone"],
        email=prescription["email"],
        patient_id=booking_details.get("patient_id"),
        process_id=booking_details.get("process_id"),
        slot_date=slot["date"],
        diary_id=slot.get("diary_id")
    )

    if not (result.get("success") and result.get("action") == "booked"):
        await query.edit_message_text(f"❌ Errore nella prenotazione: {result.get('message', 'Errore sconosciuto')}")
        return

    await _complete_booking(context, query, user_id, prescription, result)


# =============================================================================
# PRENOTAZIONE AUTOMATICA
# =============================================================================

async def toggle_auto_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abilita o disabilita la prenotazione automatica per una prescrizione."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    user_prescriptions = await run_blocking(_user_prescriptions, user_id)
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END

    valid_prescriptions = [p for p in user_prescriptions if p.get("phone") and p.get("email")]
    if not valid_prescriptions:
        await update.message.reply_text(
            "⚠️ Non hai prescrizioni con dati di contatto completi. "
            "Usa '🏥 Prenota' su una prescrizione per inserire telefono ed email."
        )
        return ConversationHandler.END

    keyboard = []
    for idx, prescription in enumerate(valid_prescriptions):
        status = "🤖 ON" if prescription.get("auto_book_enabled", False) else "🤖 OFF"
        keyboard.append([InlineKeyboardButton(
            f"{idx+1}. {_description(prescription)[:25]}... ({status})",
            callback_data=f"auto_book_{idx}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_auto_book")])

    user_data[user_id] = {"action": "toggle_auto_booking", "prescriptions": valid_prescriptions}

    await update.message.reply_text(
        "Seleziona la prescrizione per cui vuoi attivare/disattivare la prenotazione automatica:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_AUTO_BOOK_CHOICE


async def handle_auto_book_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prescrizione per cui attivare/disattivare la prenotazione automatica."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_auto_book":
        return await cancel_operation(update, context)

    session = _session(user_id, "prescriptions")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["prescriptions"]):
        return await _session_expired(update)

    selected = session["prescriptions"][idx]
    user_data.pop(user_id, None)

    def toggle(p):
        p["auto_book_enabled"] = not p.get("auto_book_enabled", False)

    updated = await run_blocking(update_prescription, selected["fiscal_code"], selected["nre"], toggle)
    if updated is None:
        await query.edit_message_text("⚠️ La prescrizione non è più presente.")
        return ConversationHandler.END

    status_text = "attivata ✅" if updated["auto_book_enabled"] else "disattivata ❌"
    info_text = ""
    if updated["auto_book_enabled"]:
        info_text = (
            "\n\nIl bot controllerà automaticamente le disponibilità a ogni ciclo di monitoraggio e "
            "prenoterà il primo slot disponibile negli ospedali non in blacklist e nel filtro date, "
            "senza richiedere conferma. Riceverai il documento di prenotazione qui in chat."
        )
        if updated.get("bookings"):
            info_text += "\n\n⚠️ Questa prescrizione risulta già prenotata: la prenotazione automatica non verrà eseguita."

    await query.edit_message_text(
        f"✅ Prenotazione automatica {status_text} per:\n\n"
        f"Descrizione: {selected.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {selected['fiscal_code']}\n"
        f"NRE: {selected['nre']}"
        f"{info_text}"
    )
    return ConversationHandler.END


# =============================================================================
# FILTRO DATE
# =============================================================================

async def set_date_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Imposta un filtro per le date delle disponibilità."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    user_prescriptions = await run_blocking(_user_prescriptions, user_id)
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END

    keyboard = []
    for idx, prescription in enumerate(user_prescriptions):
        months_limit = (prescription.get("config") or {}).get("months_limit")
        filter_status = f"⏱ {months_limit} mesi" if months_limit else "⏱ nessun filtro"
        keyboard.append([InlineKeyboardButton(
            f"{idx+1}. {_description(prescription)[:25]}... ({filter_status})",
            callback_data=f"date_filter_{idx}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_date_filter")])

    user_data[user_id] = {"action": "set_date_filter", "prescriptions": user_prescriptions}

    await update.message.reply_text(
        "Seleziona la prescrizione per cui vuoi impostare un filtro sulle date:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_DATE_FILTER


async def handle_prescription_date_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prescrizione per il filtro date."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_date_filter":
        return await cancel_operation(update, context)

    session = _session(user_id, "prescriptions")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["prescriptions"]):
        return await _session_expired(update)

    prescription = session["prescriptions"][idx]
    session["selected_prescription"] = prescription

    months_limit = (prescription.get("config") or {}).get("months_limit")
    current_filter = f"{months_limit} mesi" if months_limit else "nessun filtro"

    keyboard = [
        [
            InlineKeyboardButton("1 mese", callback_data="months_1"),
            InlineKeyboardButton("2 mesi", callback_data="months_2"),
            InlineKeyboardButton("3 mesi", callback_data="months_3")
        ],
        [
            InlineKeyboardButton("6 mesi", callback_data="months_6"),
            InlineKeyboardButton("12 mesi", callback_data="months_12"),
            InlineKeyboardButton("Nessun limite", callback_data="months_0")
        ],
        [InlineKeyboardButton("Personalizzato...", callback_data="months_custom")],
        [InlineKeyboardButton("❌ Annulla", callback_data="cancel_months")]
    ]

    await query.edit_message_text(
        f"Prescrizione: {prescription.get('description', 'Non disponibile')}\n"
        f"Filtro attuale: {current_filter}\n\n"
        "Seleziona il periodo massimo entro cui ricevere notifiche di disponibilità:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_MONTHS_LIMIT


def _date_filter_confirmation(prescription, filter_text):
    text = (
        f"Stai per impostare un filtro di {filter_text} per:\n\n"
        f"Prescrizione: {prescription.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {prescription['fiscal_code']}\n"
        f"NRE: {prescription['nre']}\n\n"
        "Confermi?"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Sì, imposta", callback_data="confirm_date_filter"),
        InlineKeyboardButton("❌ No, annulla", callback_data="cancel_date_filter_confirm")
    ]])
    return text, markup


async def handle_months_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione del limite di mesi per il filtro date."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_months":
        return await cancel_operation(update, context)

    session = _session(user_id, "selected_prescription")
    if session is None:
        return await _session_expired(update)

    if query.data == "months_custom":
        await query.edit_message_text("Inserisci il numero di mesi entro cui vuoi ricevere notifiche (1-24):")
        return WAITING_FOR_MONTHS_LIMIT

    months = _parse_index(query.data)
    if months is None:
        return await _session_expired(update)

    session["months_limit"] = months if months > 0 else None
    text, markup = _date_filter_confirmation(
        session["selected_prescription"], f"{months} mesi" if months > 0 else "nessun limite"
    )
    await query.edit_message_text(text, reply_markup=markup)
    return CONFIRM_DATE_FILTER


async def handle_custom_months_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input personalizzato per il limite di mesi."""
    user_id = update.effective_user.id
    session = _session(user_id, "selected_prescription")
    if session is None:
        return await _session_expired(update)

    try:
        months = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Devi inserire un numero intero. Riprova:")
        return WAITING_FOR_MONTHS_LIMIT

    if months < 1 or months > 24:
        await update.message.reply_text("⚠️ Il valore deve essere compreso tra 1 e 24 mesi. Riprova:")
        return WAITING_FOR_MONTHS_LIMIT

    session["months_limit"] = months
    text, markup = _date_filter_confirmation(session["selected_prescription"], f"{months} mesi")
    await update.message.reply_text(text, reply_markup=markup)
    return CONFIRM_DATE_FILTER


async def confirm_date_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma l'impostazione del filtro date."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_date_filter_confirm":
        return await cancel_operation(update, context)

    session = _session(user_id, "selected_prescription", "months_limit")
    if session is None:
        return await _session_expired(update)
    user_data.pop(user_id, None)

    prescription = session["selected_prescription"]
    months_limit = session["months_limit"]

    def set_limit(p):
        p.setdefault("config", {})["months_limit"] = months_limit

    updated = await run_blocking(update_prescription, prescription["fiscal_code"], prescription["nre"], set_limit)
    if updated is None:
        await query.edit_message_text("⚠️ La prescrizione non è più presente.")
        return ConversationHandler.END

    filter_text = f"{months_limit} mesi" if months_limit is not None else "nessun limite"
    await query.edit_message_text(
        f"✅ Filtro date impostato a {filter_text} per:\n\n"
        f"Descrizione: {prescription.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {prescription['fiscal_code']}\n"
        f"NRE: {prescription['nre']}\n\n"
        "Ora riceverai notifiche solo per disponibilità entro il periodo specificato."
    )
    return ConversationHandler.END


# =============================================================================
# BLACKLIST OSPEDALI
# =============================================================================

async def manage_hospital_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la blacklist degli ospedali per una prescrizione."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    user_prescriptions = await run_blocking(_user_prescriptions, user_id)
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END

    message = "🚫 <b>Blacklist Ospedali</b>\n\nSeleziona la prescrizione:\n\n"
    for idx, prescription in enumerate(user_prescriptions):
        blacklist_count = len((prescription.get("config") or {}).get("hospitals_blacklist", []))
        blacklist_status = f"{blacklist_count} ospedali esclusi" if blacklist_count else "nessun ospedale escluso"
        message += f"{idx+1}. <b>{esc(_description(prescription))}</b>\n"
        message += f"   CF: {esc(prescription['fiscal_code'])} • {blacklist_status}\n\n"

    keyboard, row = [], []
    for idx in range(len(user_prescriptions)):
        row.append(InlineKeyboardButton(f"{idx+1}", callback_data=f"blacklist_{idx}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_blacklist")])

    user_data[user_id] = {"action": "manage_hospital_blacklist", "prescriptions": user_prescriptions}

    chunks = split_message(message)
    for i, chunk in enumerate(chunks):
        await update.message.reply_text(
            chunk, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard) if i == len(chunks) - 1 else None
        )
    return WAITING_FOR_PRESCRIPTION_BLACKLIST


async def handle_prescription_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prescrizione per modificare la blacklist."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_blacklist":
        return await cancel_operation(update, context)

    session = _session(user_id, "prescriptions")
    idx = _parse_index(query.data)
    if session is None or idx is None or not 0 <= idx < len(session["prescriptions"]):
        return await _session_expired(update)

    prescription = session["prescriptions"][idx]
    session["selected_prescription"] = prescription

    location_db = await run_blocking(load_locations_db)
    hospitals = sorted({loc.get("hospital") for loc in location_db.values() if loc.get("hospital")})

    if not hospitals:
        await query.edit_message_text(
            "⚠️ Nessun ospedale trovato nel database.\n\n"
            "Usa la funzione '🔄 Verifica Disponibilità' per popolare l'elenco degli ospedali."
        )
        user_data.pop(user_id, None)
        return ConversationHandler.END

    session["hospitals"] = hospitals
    session["current_blacklist"] = list((prescription.get("config") or {}).get("hospitals_blacklist", []))
    session["page"] = 0
    return await show_hospitals_page(query, user_id)


async def show_hospitals_page(query, user_id):
    """Mostra una pagina di ospedali."""
    session = _session(user_id, "hospitals", "current_blacklist", "selected_prescription")
    if session is None:
        try:
            await query.edit_message_text("⚠️ Sessione scaduta. Ripeti l'operazione dal menu.")
        except BadRequest:
            pass
        user_data.pop(user_id, None)
        return ConversationHandler.END

    hospitals = session["hospitals"]
    current_blacklist = session["current_blacklist"]
    prescription = session["selected_prescription"]
    total_pages = max(1, (len(hospitals) + HOSPITALS_PER_PAGE - 1) // HOSPITALS_PER_PAGE)
    page = min(max(session.get("page", 0), 0), total_pages - 1)
    session["page"] = page

    start_idx = page * HOSPITALS_PER_PAGE
    end_idx = min(start_idx + HOSPITALS_PER_PAGE, len(hospitals))

    message_text = (
        "🚫 <b>Blacklist Ospedali</b>\n\n"
        f"Prescrizione: <b>{esc(prescription.get('description', 'N/D'))}</b>\n\n"
        "<b>Seleziona gli ospedali da escludere:</b>\n"
        "❌ = Escluso | ✅ = Incluso\n\n"
    )

    keyboard, row = [], []
    for i, idx in enumerate(range(start_idx, end_idx)):
        hospital = hospitals[idx]
        is_blacklisted = hospital in current_blacklist
        status = "❌" if is_blacklisted else "✅"
        message_text += f"{i+1}. {status} {esc(hospital)}\n"
        row.append(InlineKeyboardButton(f"{status}{i+1}", callback_data=f"toggle_hospital_{idx}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    message_text += f"\nPagina {page+1}/{total_pages} • Ospedali esclusi: {len(current_blacklist)}/{len(hospitals)}"

    keyboard.append([
        InlineKeyboardButton("⬛ Blacklista tutti", callback_data="blacklist_all"),
        InlineKeyboardButton("⬜ Whitelist tutti", callback_data="whitelist_all")
    ])
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️", callback_data="page_prev"))
    navigation.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="page_noop"))
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("➡️", callback_data="page_next"))
    keyboard.append(navigation)
    keyboard.append([InlineKeyboardButton("📋 Importa da altra prescrizione", callback_data="import_blacklist")])
    keyboard.append([
        InlineKeyboardButton("✅ Conferma", callback_data="confirm_blacklist"),
        InlineKeyboardButton("❌ Annulla", callback_data="cancel_blacklist")
    ])

    try:
        await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise
    return WAITING_FOR_HOSPITAL_SELECTION


async def handle_hospital_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione di un ospedale per aggiungerlo/rimuoverlo dalla blacklist."""
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    session = _session(user_id, "hospitals", "current_blacklist")
    if session is None:
        await query.answer()
        return await _session_expired(update)

    hospitals = session["hospitals"]

    if callback_data == "page_noop":
        await query.answer()
        return WAITING_FOR_HOSPITAL_SELECTION

    if callback_data == "page_prev":
        await query.answer()
        session["page"] = session.get("page", 0) - 1
        return await show_hospitals_page(query, user_id)

    if callback_data == "page_next":
        await query.answer()
        session["page"] = session.get("page", 0) + 1
        return await show_hospitals_page(query, user_id)

    if callback_data == "blacklist_all":
        session["current_blacklist"] = list(hospitals)
        await query.answer("Tutti gli ospedali sono stati aggiunti alla blacklist")
        return await show_hospitals_page(query, user_id)

    if callback_data == "whitelist_all":
        session["current_blacklist"] = []
        await query.answer("Tutti gli ospedali sono stati rimossi dalla blacklist")
        return await show_hospitals_page(query, user_id)

    if callback_data.startswith("toggle_hospital_"):
        await query.answer()
        hospital_idx = _parse_index(callback_data, 2)
        if hospital_idx is None or not 0 <= hospital_idx < len(hospitals):
            return WAITING_FOR_HOSPITAL_SELECTION
        hospital_name = hospitals[hospital_idx]
        # Lo stato viene letto dalla sessione, non dal pulsante (che può essere vecchio)
        if hospital_name in session["current_blacklist"]:
            session["current_blacklist"].remove(hospital_name)
        else:
            session["current_blacklist"].append(hospital_name)
        return await show_hospitals_page(query, user_id)

    await query.answer()
    return WAITING_FOR_HOSPITAL_SELECTION


async def confirm_hospital_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma e salva la blacklist degli ospedali."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session = _session(user_id, "selected_prescription", "current_blacklist")
    if session is None:
        return await _session_expired(update)
    user_data.pop(user_id, None)

    prescription = session["selected_prescription"]
    current_blacklist = session["current_blacklist"]

    def set_blacklist(p):
        p.setdefault("config", {})["hospitals_blacklist"] = current_blacklist

    updated = await run_blocking(update_prescription, prescription["fiscal_code"], prescription["nre"], set_blacklist)
    if updated is None:
        await query.edit_message_text("⚠️ Impossibile aggiornare la blacklist: la prescrizione non è più presente.")
        return ConversationHandler.END

    await query.edit_message_text(
        "✅ Blacklist aggiornata per:\n\n"
        f"Descrizione: {prescription.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {prescription['fiscal_code']}\n"
        f"NRE: {prescription['nre']}\n\n"
        f"Ospedali esclusi: {len(current_blacklist)}\n"
        "Ora riceverai notifiche solo per ospedali non presenti nella blacklist."
    )
    return ConversationHandler.END


async def handle_import_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra la lista delle altre prescrizioni da cui importare la blacklist."""
    query = update.callback_query
    user_id = query.from_user.id

    session = _session(user_id, "selected_prescription")
    if session is None:
        await query.answer()
        return await _session_expired(update)

    current = session["selected_prescription"]
    others = [
        p for p in await run_blocking(_user_prescriptions, user_id)
        if not (p["fiscal_code"] == current["fiscal_code"] and p["nre"] == current["nre"])
    ]

    if not others:
        await query.answer("Nessun'altra prescrizione disponibile.", show_alert=True)
        return WAITING_FOR_HOSPITAL_SELECTION
    await query.answer()

    session["import_sources"] = others
    keyboard = []
    for i, p in enumerate(others):
        blacklist = (p.get("config") or {}).get("hospitals_blacklist", [])
        label = f"{p.get('description') or p['nre']} ({len(blacklist)} esclusi)"
        keyboard.append([InlineKeyboardButton(label[:60], callback_data=f"import_from_{i}")])
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_import")])

    await query.edit_message_text(
        "📋 <b>Seleziona la prescrizione da cui importare la blacklist:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return WAITING_FOR_IMPORT_SOURCE


async def handle_import_source_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Importa la blacklist dalla prescrizione selezionata."""
    query = update.callback_query
    user_id = query.from_user.id

    session = _session(user_id, "hospitals", "current_blacklist")
    if session is None:
        await query.answer()
        return await _session_expired(update)

    if query.data == "cancel_import":
        await query.answer()
        return await show_hospitals_page(query, user_id)

    sources = session.get("import_sources") or []
    idx = _parse_index(query.data)
    if idx is None or not 0 <= idx < len(sources):
        await query.answer()
        return await show_hospitals_page(query, user_id)

    imported = list((sources[idx].get("config") or {}).get("hospitals_blacklist", []))
    session["current_blacklist"] = imported
    await query.answer(f"Importati {len(imported)} ospedali esclusi.")
    return await show_hospitals_page(query, user_id)


# =============================================================================
# REFERTI: CONFIGURAZIONE MONITORAGGIO
# =============================================================================

async def download_medical_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia il processo di configurazione del monitoraggio dei referti medici."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    await update.message.reply_text(
        "📋 <b>Monitoraggio Referti Medici</b>\n\n"
        "Questo servizio controllerà periodicamente la disponibilità di nuovi referti "
        "e ti invierà una notifica quando saranno disponibili.\n\n"
        "Per configurare il monitoraggio, ho bisogno di alcune informazioni.\n\n"
        "Per prima cosa, inserisci il tuo <b>codice fiscale</b>:",
        reply_markup=CANCEL_KEYBOARD,
        parse_mode="HTML"
    )

    user_data[user_id] = {"action": "monitor_reports"}
    return WAITING_FOR_FISCAL_CODE_REPORT


async def handle_fiscal_code_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del codice fiscale per il monitoraggio dei referti."""
    user_id = update.effective_user.id
    session = _session(user_id)
    if session is None:
        return await _session_expired(update)

    fiscal_code = update.message.text.strip().upper()
    if not re.match("^[A-Z0-9]{16}$", fiscal_code):
        await update.message.reply_text(
            "⚠️ Il codice fiscale inserito non sembra valido. Deve essere composto da 16 caratteri alfanumerici.\n\n"
            "Per favore, riprova o scrivi ❌ Annulla per tornare al menu principale:"
        )
        return WAITING_FOR_FISCAL_CODE_REPORT

    session["fiscal_code"] = fiscal_code

    # Il codice della tessera sanitaria viene preso dalle prescrizioni monitorate, se presente
    tscns_code = "8038000"
    for prescription in await run_blocking(load_input_data):
        if prescription["fiscal_code"] == fiscal_code:
            code = ((prescription.get("patient_info") or {}).get("teamCard") or {}).get("code", "")
            if code and code != "N/A":
                tscns_code = code
                break

    session["tscns"] = tscns_code
    origin = "estratto automaticamente" if tscns_code != "8038000" else "valore predefinito"

    await update.message.reply_text(
        f"Codice fiscale: {esc(fiscal_code)}\n"
        f"Codice tessera sanitaria: <code>{esc(tscns_code)}</code> ({origin})\n\n"
        "Ora inserisci la <b>password</b> che hai ricevuto via SMS dalla Regione Lazio.\n\n"
        "<i>Nota: questa è la password che ricevi via SMS con testo simile a: "
        "'Regione Lazio su https://www.salutelazio.it/scarica-il-tuo-referto sara' possibile recuperare "
        "l'esito dell'esame effettuato. La password e' XXXXXXXXXX'</i>",
        reply_markup=CANCEL_KEYBOARD,
        parse_mode="HTML"
    )
    return WAITING_FOR_PASSWORD_REPORT


async def handle_password_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input della password per il monitoraggio dei referti."""
    user_id = update.effective_user.id
    session = _session(user_id, "fiscal_code", "tscns")
    if session is None:
        return await _session_expired(update)

    password = update.message.text.strip().upper()
    if not re.match("^[A-Z0-9]{10}$", password):
        await update.message.reply_text(
            "⚠️ La password inserita non sembra valida. Deve essere composta da 10 caratteri alfanumerici, "
            "come quella ricevuta via SMS.\n\n"
            "Per favore, riprova o scrivi ❌ Annulla per tornare al menu principale:"
        )
        return WAITING_FOR_PASSWORD_REPORT

    fiscal_code = session["fiscal_code"]
    tscns = session["tscns"]

    waiting_msg = await update.message.reply_text("🔍 Sto verificando le credenziali... Potrebbe richiedere alcuni secondi.")
    reports = await run_blocking(download_reports, fiscal_code, password, tscns)
    await waiting_msg.delete()

    if reports is None:
        await update.message.reply_text(
            "❌ Non è stato possibile verificare le credenziali: la password potrebbe essere errata "
            "oppure il servizio della Regione è temporaneamente non disponibile.\n\n"
            "Inserisci di nuovo la password oppure scrivi ❌ Annulla:"
        )
        return WAITING_FOR_PASSWORD_REPORT

    known_ids = [r.get("document_id") for r in reports if r.get("document_id")]
    await run_blocking(add_report_monitoring, fiscal_code, password, tscns, user_id, known_ids)
    user_data.pop(user_id, None)

    if known_ids:
        message = (
            "✅ <b>Monitoraggio referti attivato con successo!</b>\n\n"
            "Il sistema verificherà periodicamente la disponibilità di nuovi referti per:\n"
            f"<b>Codice Fiscale:</b> <code>{esc(fiscal_code)}</code>\n\n"
            f"Attualmente sono disponibili {len(known_ids)} referti.\n\n"
            "Per scaricarli usa '📋 Gestisci Monitoraggi Referti'. "
            "Riceverai una notifica per ogni nuovo referto."
        )
    else:
        message = (
            "✅ <b>Monitoraggio referti attivato con successo!</b>\n\n"
            "Il sistema verificherà periodicamente la disponibilità di nuovi referti per:\n"
            f"<b>Codice Fiscale:</b> <code>{esc(fiscal_code)}</code>\n\n"
            "Attualmente non sono disponibili referti. Riceverai una notifica "
            "non appena un referto sarà disponibile."
        )

    await update.message.reply_text(message, reply_markup=_main_keyboard(user_id), parse_mode="HTML")
    return ConversationHandler.END


# =============================================================================
# REFERTI: GESTIONE MONITORAGGI E DOWNLOAD
# =============================================================================

def _visible_monitorings(user_id):
    monitoring_data = load_reports_monitoring()
    if _is_admin(user_id):
        return monitoring_data
    return [m for m in monitoring_data if _owns(m, user_id)]


def _can_manage(item, user_id):
    return item is not None and (_is_admin(user_id) or _owns(item, user_id))


def _format_check_time(last_check):
    if not last_check:
        return "Mai controllato"
    try:
        return datetime.fromisoformat(last_check).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return last_check


async def list_report_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra la lista dei monitoraggi referti con le azioni disponibili."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    monitorings = await run_blocking(_visible_monitorings, user_id)
    if not monitorings:
        await update.message.reply_text("📋 Non hai monitoraggi referti attivi.")
        return

    message = "📋 <b>Monitoraggi Referti:</b>\n\n"
    keyboard = []
    for idx, monitoring in enumerate(monitorings):
        fiscal_code = monitoring["fiscal_code"]
        enabled = monitoring.get("enabled", True)
        message += f"{idx+1}. <b>Codice Fiscale:</b> <code>{esc(fiscal_code)}</code>\n"
        message += f"   Stato: {'✅ attivo' if enabled else '❌ disattivato'}\n"
        message += f"   Ultimo controllo: {esc(_format_check_time(monitoring.get('last_check')))}\n"
        message += f"   Referti noti: {len(monitoring.get('known_reports', []))}\n\n"

        item_id = monitoring["id"]
        keyboard.append([
            InlineKeyboardButton(f"{idx+1}. {'❌ Disattiva' if enabled else '✅ Attiva'}", callback_data=f"toggle_monitor_{item_id}"),
            InlineKeyboardButton("📥 Scarica", callback_data=f"download_reports_{item_id}"),
            InlineKeyboardButton("🗑️ Rimuovi", callback_data=f"remove_monitor_{item_id}"),
        ])

    keyboard.append([InlineKeyboardButton("🔄 Verifica Ora", callback_data="check_reports_now")])
    await _reply_long(update.message, message, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_report_monitoring_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce le azioni sui monitoraggi referti (attiva/disattiva, rimuovi, verifica)."""
    query = update.callback_query
    user_id = query.from_user.id

    if not is_authorized(user_id):
        await query.answer("🔒 Non sei autorizzato ad utilizzare questa funzione.", show_alert=True)
        return
    await query.answer()

    callback_data = query.data

    if callback_data == "check_reports_now":
        await query.edit_message_text("🔍 Verifica in corso... Attendere prego.")
        try:
            chat_filter = None if _is_admin(user_id) else user_id
            total_checked, total_notifications, errors = await run_blocking(check_new_reports, chat_filter)
            result_message = (
                "✅ Verifica completata!\n\n"
                f"Monitoraggi controllati: {total_checked}\n"
                f"Notifiche inviate: {total_notifications}\n"
            )
            if errors > 0:
                result_message += f"⚠️ Errori riscontrati: {errors}\n"
            result_message += "\nSe sono stati trovati nuovi referti, riceverai notifiche separate."
            await query.edit_message_text(result_message)
        except Exception as e:
            logger.error(f"Errore durante la verifica dei referti: {str(e)}")
            await query.edit_message_text("⚠️ Si è verificato un errore durante la verifica. Riprova più tardi.")
        return

    action, _, item_id = callback_data.rpartition("_")
    item = await run_blocking(get_report_monitoring, item_id)
    if not _can_manage(item, user_id):
        await query.edit_message_text("⚠️ Monitoraggio non trovato. Riapri '📋 Gestisci Monitoraggi Referti'.")
        return

    if action == "toggle_monitor":
        found, new_state = await run_blocking(toggle_report_monitoring, item_id)
        if not found:
            await query.edit_message_text("⚠️ Errore nella modifica dello stato del monitoraggio.")
            return
        await query.edit_message_text(
            f"{'✅' if new_state else '❌'} Monitoraggio referti {'attivato' if new_state else 'disattivato'} "
            f"per il codice fiscale: <code>{esc(item['fiscal_code'])}</code>",
            parse_mode="HTML"
        )
    elif action == "remove_monitor":
        if await run_blocking(remove_report_monitoring, item_id):
            await query.edit_message_text(
                f"✅ Monitoraggio referti rimosso per il codice fiscale: <code>{esc(item['fiscal_code'])}</code>",
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text("⚠️ Errore nella rimozione del monitoraggio.")


def _report_label(report):
    doc_date = report.get("document_date", "Data sconosciuta")
    try:
        doc_date = datetime.strptime(doc_date, "%Y%m%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        pass
    return (report.get("document_type") or "Referto", report.get("provider") or "Struttura sconosciuta", doc_date)


def _report_filename(report):
    doc_type, provider, _ = _report_label(report)
    filename = f"{report.get('document_date', '')}_{doc_type}_{provider}_{report.get('document_id')}"
    return "".join(c if c.isalnum() or c == "_" else "_" for c in filename)[:120] + ".pdf"


async def handle_download_reports_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recupera i referti disponibili per un monitoraggio e mostra l'elenco da scaricare."""
    query = update.callback_query
    user_id = query.from_user.id

    if not is_authorized(user_id):
        await query.answer("🔒 Non sei autorizzato ad utilizzare questa funzione.", show_alert=True)
        return
    await query.answer()

    item_id = query.data[len("download_reports_"):]
    item = await run_blocking(get_report_monitoring, item_id)
    if not _can_manage(item, user_id):
        await query.edit_message_text("⚠️ Monitoraggio non trovato. Riapri '📋 Gestisci Monitoraggi Referti'.")
        return

    await query.edit_message_text("🔍 Recupero dei referti in corso... Attendere prego.")
    reports = await run_blocking(download_reports, item["fiscal_code"], item["password"], item["tscns"])

    if reports is None:
        await query.edit_message_text(
            "⚠️ Impossibile recuperare i referti: password non più valida o servizio non disponibile."
        )
        return
    reports = [r for r in reports if r.get("document_id")]
    if not reports:
        await query.edit_message_text("ℹ️ Non ci sono referti disponibili per questo monitoraggio.")
        return

    # Tutti i referti restano in sessione ("Scarica tutti"); i pulsanti singoli sono al massimo 40
    report_sessions[user_id] = {"item_id": item_id, "reports": reports}

    keyboard = []
    for idx, report in enumerate(reports[:40]):
        doc_type, provider, doc_date = _report_label(report)
        keyboard.append([InlineKeyboardButton(f"{idx+1}. {doc_type} - {provider} ({doc_date})"[:60], callback_data=f"report_{idx}")])
    keyboard.append([InlineKeyboardButton("📥 Scarica tutti", callback_data="report_all")])
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_report")])

    await query.edit_message_text(
        f"📋 <b>Referti disponibili ({len(reports)}):</b>\n\nSeleziona un referto da scaricare:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def _send_report(context, user_id, item, report):
    content = await run_blocking(
        download_report_document, report["document_id"], item["fiscal_code"], item["password"], item["tscns"]
    )
    if not content:
        return False
    doc_type, provider, doc_date = _report_label(report)
    await context.bot.send_document(
        chat_id=user_id,
        document=BytesIO(content),
        filename=_report_filename(report),
        caption=f"📋 {doc_type}\n📅 {doc_date}\n🏥 {provider}"[:1024]
    )
    return True


async def handle_report_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scarica il referto selezionato (o tutti) e lo invia in chat."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_report":
        report_sessions.pop(user_id, None)
        await query.edit_message_text("❌ Operazione annullata.")
        return

    session = report_sessions.get(user_id)
    item = await run_blocking(get_report_monitoring, session["item_id"]) if session else None
    if not session or not _can_manage(item, user_id):
        report_sessions.pop(user_id, None)
        await query.edit_message_text("⚠️ Sessione scaduta. Riapri '📋 Gestisci Monitoraggi Referti'.")
        return

    reports = session["reports"]
    if query.data == "report_all":
        selected = reports
    else:
        idx = _parse_index(query.data)
        if idx is None or not 0 <= idx < len(reports):
            await query.edit_message_text("⚠️ Referto non valido.")
            return
        selected = [reports[idx]]

    report_sessions.pop(user_id, None)
    await query.edit_message_text("📥 Download in corso... Attendere prego.")

    success_ids, error_count = [], 0
    for report in selected:
        try:
            if await _send_report(context, user_id, item, report):
                success_ids.append(report["document_id"])
            else:
                error_count += 1
        except Exception as e:
            logger.error(f"Errore nell'invio del referto: {str(e)}")
            error_count += 1

    downloaded_everything = bool(success_ids) and error_count == 0 and len(selected) == len(reports)
    if downloaded_everything:
        # Come in origine: scaricati tutti i referti, il monitoraggio viene rimosso
        await run_blocking(remove_report_monitoring, item["id"])
        footer = "\n\nIl monitoraggio referti per questo codice fiscale è stato rimosso."
    else:
        if success_ids:
            await run_blocking(mark_reports_known, item["id"], success_ids)
        footer = ("\n\nCi sono ancora altri referti disponibili. Il monitoraggio continuerà per gli altri."
                  if len(selected) < len(reports) else "")

    if len(selected) == 1 and not error_count:
        text = "✅ Referto scaricato con successo!" + footer
    else:
        text = (f"✅ Download completato!\n\nReferti scaricati con successo: {len(success_ids)}\n"
                f"Errori: {error_count}" + footer)
    await context.bot.send_message(chat_id=user_id, text=text)


# =============================================================================
# INFO, BROADCAST E UTENTI
# =============================================================================

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra informazioni sul bot."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return

    await update.message.reply_text(
        "ℹ️ <b>Informazioni sul Bot</b>\n\n"
        "Questo bot monitora le disponibilità del Servizio Sanitario Nazionale (SSN) per le prescrizioni mediche e ti notifica quando ci sono nuove disponibilità. Monitora anche i tuoi referti medici e ti avvisa quando sono disponibili.\n\n"
        "<b>Comandi principali:</b>\n"
        "➕ <b>Aggiungi Prescrizione</b> - Monitora una nuova prescrizione\n"
        "➖ <b>Rimuovi Prescrizione</b> - Smetti di monitorare una prescrizione\n"
        "📋 <b>Lista Prescrizioni</b> - Visualizza le prescrizioni monitorate\n"
        "🔄 <b>Verifica Disponibilità</b> - Controlla subito le disponibilità\n"
        "🔔 <b>Gestisci Notifiche</b> - Attiva/disattiva notifiche per una prescrizione\n"
        "⏱ <b>Imposta Filtro Date</b> - Filtra le notifiche entro un periodo di mesi\n"
        "🚫 <b>Blacklist Ospedali</b> - Escludi ospedali specifici dalle notifiche\n"
        "🏥 <b>Prenota</b> - Prenota un appuntamento per una prescrizione\n"
        "🤖 <b>Prenota Automaticamente</b> - Attiva/disattiva la prenotazione automatica\n"
        "📝 <b>Le mie Prenotazioni</b> - Visualizza e gestisci le prenotazioni attive\n"
        "📊 <b>Configura Monitoraggio Referti</b> - Configura il monitoraggio automatico dei referti\n"
        "📋 <b>Gestisci Monitoraggi Referti</b> - Visualizza, scarica o disattiva monitoraggi referti\n\n"
        "<b>Monitoraggio Referti:</b>\n"
        "Il sistema verifica periodicamente se sono disponibili nuovi referti medici per il tuo codice fiscale. Quando un nuovo referto diventa disponibile, riceverai una notifica e potrai scaricarlo da '📋 Gestisci Monitoraggi Referti'. Una volta scaricati tutti i referti, il monitoraggio verrà automaticamente rimosso. "
        "Se nelle tue prescrizioni monitorate è presente il codice della tessera sanitaria, verrà utilizzato automaticamente.\n\n"
        "<b>Prenotazione Automatica:</b>\n"
        "Quando attivi la prenotazione automatica per una prescrizione, il bot prenota automaticamente il primo slot disponibile utilizzando i dati di contatto salvati, senza richiedere ulteriori conferme.\n\n"
        "<b>Blacklist Ospedali:</b>\n"
        "Puoi escludere specifici ospedali dalle notifiche per ogni prescrizione, ricevendo avvisi solo per le strutture che ti interessano.\n\n"
        "<b>Note:</b>\n"
        "• Il bot notifica solo quando ci sono cambiamenti significativi\n"
        "• Le disponibilità possono variare rapidamente, è consigliabile prenotare il prima possibile\n"
        "• Per problemi o assistenza, contatta l'amministratore",
        parse_mode="HTML"
    )


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'invio di un messaggio a tutti gli utenti autorizzati (solo admin)."""
    user_id = update.effective_user.id

    if not _is_admin(user_id):
        await update.message.reply_text("🔒 Solo l'amministratore può inviare messaggi broadcast.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📣 <b>Broadcast Message</b>\n\n"
        "Scrivi il messaggio che vuoi inviare a tutti gli utenti autorizzati.\n"
        "Il messaggio supporta la formattazione HTML.\n\n"
        "Esempi di formattazione:\n"
        "- Per il <b>grassetto</b> usa: &lt;b&gt;grassetto&lt;/b&gt;\n"
        "- Per il <i>corsivo</i> usa: &lt;i&gt;corsivo&lt;/i&gt;\n"
        "- Per il <u>sottolineato</u> usa: &lt;u&gt;sottolineato&lt;/u&gt;\n"
        "- Per il <code>codice</code> usa: &lt;code&gt;codice&lt;/code&gt;\n\n"
        "Scrivi il tuo messaggio o premi ❌ Annulla per tornare al menu principale:",
        reply_markup=CANCEL_KEYBOARD,
        parse_mode="HTML"
    )

    user_data[user_id] = {"action": "broadcast_message"}
    return WAITING_FOR_BROADCAST_MESSAGE


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il messaggio broadcast da inviare."""
    user_id = update.effective_user.id
    session = _session(user_id)
    if session is None or not _is_admin(user_id):
        return await _session_expired(update)

    message_text = update.message.text
    session["broadcast_message"] = message_text

    try:
        await update.message.reply_text(
            "📋 <b>Anteprima del messaggio:</b>\n\n" + message_text + "\n\n"
            f"👥 Questo messaggio verrà inviato a {len(authorized_users)} utenti autorizzati.\n\n"
            "Confermi l'invio?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Sì, invia a tutti", callback_data="confirm_broadcast"),
                InlineKeyboardButton("❌ No, annulla", callback_data="cancel_broadcast")
            ]]),
            parse_mode="HTML"
        )
    except BadRequest as e:
        await update.message.reply_text(
            f"⚠️ Il messaggio contiene HTML non valido ({esc(str(e))}).\n\nCorreggilo e invialo di nuovo:",
        )
        return WAITING_FOR_BROADCAST_MESSAGE

    return WAITING_FOR_BROADCAST_CONFIRMATION


async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma dell'invio del messaggio broadcast."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "cancel_broadcast":
        await cancel_operation(update, context)
        await context.bot.send_message(chat_id=user_id, text="Cosa vuoi fare?", reply_markup=_main_keyboard(user_id))
        return ConversationHandler.END

    session = _session(user_id, "broadcast_message")
    if session is None or not _is_admin(user_id):
        return await _session_expired(update)
    user_data.pop(user_id, None)

    await query.edit_message_text("📣 Invio del messaggio broadcast in corso...")

    success_count, error_details = 0, []
    for recipient_id in list(authorized_users):
        try:
            await context.bot.send_message(
                chat_id=int(recipient_id),
                text="📣 <b>Messaggio dall'amministratore:</b>\n\n" + session["broadcast_message"],
                parse_mode="HTML"
            )
            success_count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            error_details.append(f"ID {recipient_id}: {str(e)}")
            logger.error(f"Errore nell'invio del messaggio broadcast a {recipient_id}: {str(e)}")

    result_message = f"✅ Messaggio inviato con successo a {success_count} utenti."
    if error_details:
        result_message += f"\n\n❌ Errori nell'invio a {len(error_details)} utenti.\n\nDettagli degli errori:"
        for detail in error_details[:5]:
            result_message += f"\n- {detail}"
        if len(error_details) > 5:
            result_message += f"\n...e altri {len(error_details) - 5} errori."

    await context.bot.send_message(chat_id=user_id, text=result_message, reply_markup=_main_keyboard(user_id))
    return ConversationHandler.END


async def authorize_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'autorizzazione di nuovi utenti (solo admin)."""
    user_id = update.effective_user.id

    if not _is_admin(user_id):
        await update.message.reply_text("🔒 Solo l'amministratore può autorizzare nuovi utenti.")
        return

    user_data[user_id] = {"action": "authorizing_user"}
    await update.message.reply_text(
        "Per autorizzare un nuovo utente, invia il suo ID Telegram.\n\n"
        "L'utente può ottenere il proprio ID usando @userinfobot o altri bot simili.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annulla", callback_data="cancel_auth")]])
    )
    return AUTHORIZING


async def handle_cancel_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la pressione del pulsante '❌ Annulla' durante l'autorizzazione."""
    return await cancel_operation(update, context)


async def handle_auth_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'inserimento dell'ID utente da autorizzare."""
    user_id = update.effective_user.id
    if _session(user_id) is None or not _is_admin(user_id):
        return await _session_expired(update)

    new_user_id = update.message.text.strip()
    if not new_user_id.isdigit():
        await update.message.reply_text("⚠️ L'ID utente deve essere un numero. Riprova oppure digita /cancel per annullare:")
        return AUTHORIZING

    user_data.pop(user_id, None)
    if new_user_id in authorized_users:
        await update.message.reply_text(f"⚠️ L'utente {new_user_id} è già autorizzato.", reply_markup=_main_keyboard(user_id))
        return ConversationHandler.END

    authorized_users.append(new_user_id)
    await run_blocking(save_authorized_users)
    await update.message.reply_text(f"✅ Utente {new_user_id} autorizzato con successo!", reply_markup=_main_keyboard(user_id))
    return ConversationHandler.END


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i messaggi di testo e i comandi dai pulsanti del menu."""
    user_id = update.effective_user.id
    text = update.message.text

    if not is_authorized(user_id):
        # Primo avvio: il primo utente diventa amministratore, solo se il DB è
        # leggibile e non contiene davvero nessun utente
        try:
            no_users = not authorized_users and await run_blocking(count_authorized_users_in_db) == 0
        except Exception as e:
            logger.error(f"Impossibile verificare gli utenti autorizzati: {str(e)}")
            no_users = False

        if no_users:
            authorized_users.append(str(user_id))
            await run_blocking(save_authorized_users)
            logger.info(f"Primo utente {user_id} aggiunto come amministratore")
            await update.message.reply_text(
                f"👑 Benvenuto, {update.effective_user.first_name}!\n\n"
                "Sei stato impostato come amministratore del bot.\n\n"
                "Questo bot ti aiuterà a monitorare le disponibilità del Servizio Sanitario Nazionale.",
                reply_markup=_main_keyboard(user_id)
            )
        else:
            await update.message.reply_text(
                "🔒 Non sei autorizzato ad utilizzare questo bot. Contatta l'amministratore per ottenere l'accesso."
            )
        return

    routes = {
        "➕ Aggiungi Prescrizione": add_prescription,
        "➖ Rimuovi Prescrizione": remove_prescription,
        "📋 Lista Prescrizioni": list_prescriptions,
        "🔄 Verifica Disponibilità": check_availability,
        "🔔 Gestisci Notifiche": toggle_notifications,
        "⏱ Imposta Filtro Date": set_date_filter,
        "🏥 Prenota": book_prescription,
        "🤖 Prenota Automaticamente": toggle_auto_booking,
        "📝 Le mie Prenotazioni": list_bookings,
        "ℹ️ Informazioni": show_info,
        "🚫 Blacklist Ospedali": manage_hospital_blacklist,
        "📣 Messaggio Broadcast": broadcast_message,
        "🔑 Autorizza Utente": authorize_user,
        "📊 Configura Monitoraggio Referti": download_medical_reports,
        "📋 Gestisci Monitoraggi Referti": list_report_monitoring,
    }
    handler = routes.get(text)
    if handler:
        return await handler(update, context)

    await update.message.reply_text("Usa i pulsanti sotto per interagire con il bot.", reply_markup=_main_keyboard(user_id))


async def error_handler(update, context):
    """Gestisce gli errori del bot."""
    error = context.error

    if isinstance(error, BadRequest) and "message is not modified" in str(error).lower():
        return
    if not isinstance(update, Update):
        # Errori di rete/polling non legati a un messaggio dell'utente
        if isinstance(error, (Conflict, NetworkError, TimedOut)):
            logger.warning(f"Errore di rete Telegram: {error}")
        else:
            logger.error("Errore non gestito", exc_info=error)
        return

    logger.error(
        f"Errore nell'update {update.update_id}: {error}\n"
        + "".join(traceback.format_exception(type(error), error, error.__traceback__))
    )

    user_id = update.effective_user.id if update.effective_user else None
    if user_id is not None:
        user_data.pop(user_id, None)
        quickbook_sessions.pop(user_id, None)
        report_sessions.pop(user_id, None)

    if update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Si è verificato un errore durante l'elaborazione della tua richiesta. "
                     "Per favore, riprova o contatta l'amministratore se il problema persiste.",
                reply_markup=_main_keyboard(user_id) if user_id and is_authorized(user_id) else None
            )
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio di errore: {e}")


# =============================================================================
# SETUP HANDLERS
# =============================================================================

def setup_handlers(application):
    """Configura i gestori delle conversazioni per il bot."""

    menu = MessageHandler(filters.Regex(MENU_REGEX), menu_switch)
    cancel_text = MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation)
    cancel_cmd = CommandHandler("cancel", cancel_operation)
    text_input = filters.TEXT & ~filters.COMMAND

    def text_state(callback):
        return [cancel_text, cancel_cmd, menu, MessageHandler(text_input, callback)]

    def buttons(*handlers):
        # Durante un'operazione basata su pulsanti, il menu resta utilizzabile
        return [menu, *handlers]

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(text_input, handle_text)
        ],
        states={
            WAITING_FOR_FISCAL_CODE: text_state(handle_fiscal_code),
            WAITING_FOR_NRE: text_state(handle_nre),
            WAITING_FOR_PHONE: text_state(handle_add_phone),
            WAITING_FOR_EMAIL: text_state(handle_email_input),
            AUTHORIZING: [
                CallbackQueryHandler(handle_cancel_auth, pattern="^cancel_auth$"),
                *text_state(handle_auth_user_id)
            ],
            CONFIRM_ADD: buttons(
                CallbackQueryHandler(confirm_add_prescription, pattern="^(confirm_add|cancel_add)$")
            ),
            WAITING_FOR_PRESCRIPTION_TO_DELETE: buttons(
                CallbackQueryHandler(handle_prescription_to_delete, pattern=r"^(remove_\d+|cancel_remove)$")
            ),
            WAITING_FOR_PRESCRIPTION_TO_TOGGLE: buttons(
                CallbackQueryHandler(handle_prescription_toggle, pattern=r"^(toggle_\d+|cancel_toggle)$")
            ),
            WAITING_FOR_DATE_FILTER: buttons(
                CallbackQueryHandler(handle_prescription_date_filter, pattern=r"^(date_filter_\d+|cancel_date_filter)$")
            ),
            WAITING_FOR_MONTHS_LIMIT: [
                CallbackQueryHandler(handle_months_limit, pattern=r"^(months_\d+|months_custom|cancel_months)$"),
                *text_state(handle_custom_months_limit)
            ],
            CONFIRM_DATE_FILTER: buttons(
                CallbackQueryHandler(confirm_date_filter, pattern="^(confirm_date_filter|cancel_date_filter_confirm)$")
            ),
            WAITING_FOR_BOOKING_CHOICE: buttons(
                CallbackQueryHandler(handle_booking_choice, pattern=r"^book_\d+$"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_booking$")
            ),
            WAITING_FOR_SLOT_CHOICE: buttons(
                CallbackQueryHandler(handle_slot_choice, pattern=r"^(slot_\d+|cancel_slot)$")
            ),
            WAITING_FOR_BOOKING_CONFIRMATION: buttons(
                CallbackQueryHandler(confirm_booking, pattern=r"^(confirm_slot_\d+|cancel_slot)$")
            ),
            WAITING_FOR_AUTO_BOOK_CHOICE: buttons(
                CallbackQueryHandler(handle_auto_book_toggle, pattern=r"^(auto_book_\d+|cancel_auto_book)$")
            ),
            WAITING_FOR_PRESCRIPTION_BLACKLIST: buttons(
                CallbackQueryHandler(handle_prescription_blacklist, pattern=r"^(blacklist_\d+|cancel_blacklist)$")
            ),
            WAITING_FOR_HOSPITAL_SELECTION: buttons(
                CallbackQueryHandler(
                    handle_hospital_selection,
                    pattern=r"^(toggle_hospital_\d+(_(True|False))?|page_prev|page_next|page_noop|dummy|blacklist_all|whitelist_all)$"
                ),
                CallbackQueryHandler(confirm_hospital_blacklist, pattern="^confirm_blacklist$"),
                CallbackQueryHandler(handle_import_blacklist, pattern="^import_blacklist$"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_blacklist$")
            ),
            WAITING_FOR_IMPORT_SOURCE: buttons(
                CallbackQueryHandler(handle_import_source_selection, pattern=r"^(import_from_\d+|cancel_import)$")
            ),
            WAITING_FOR_BROADCAST_MESSAGE: text_state(handle_broadcast_message),
            WAITING_FOR_BROADCAST_CONFIRMATION: buttons(
                CallbackQueryHandler(confirm_broadcast, pattern="^(confirm_broadcast|cancel_broadcast)$")
            ),
            WAITING_FOR_FISCAL_CODE_REPORT: text_state(handle_fiscal_code_report),
            WAITING_FOR_PASSWORD_REPORT: text_state(handle_password_report),
        },
        fallbacks=[
            cancel_cmd,
            cancel_text,
            menu,
            MessageHandler(filters.ALL, error_recovery)
        ]
    )

    # La conversazione ha la precedenza: un /cancel durante un'operazione deve anche chiuderla
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("cancel", cancel_operation))

    booking_cancel_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_cancel_booking, pattern="^cancel_appointment$")
        ],
        states={
            WAITING_FOR_BOOKING_TO_CANCEL: [
                CallbackQueryHandler(handle_booking_to_cancel, pattern=r"^cancel_book_\d+$"),
                CallbackQueryHandler(confirm_cancel_booking, pattern=r"^confirm_cancel_\d+$"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_cancel_book$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_operation, pattern="^cancel_cancel_book$")
        ],
        # Il pulsante "Disdici" deve funzionare anche se un flusso precedente è rimasto aperto
        allow_reentry=True,
        name="booking_cancellation"
    )
    application.add_handler(booking_cancel_handler)

    # Monitoraggio e download referti
    application.add_handler(CallbackQueryHandler(
        handle_report_monitoring_action,
        pattern="^(toggle_monitor_|remove_monitor_|check_reports_now$)"
    ))
    application.add_handler(CallbackQueryHandler(handle_download_reports_selection, pattern="^download_reports_"))
    application.add_handler(CallbackQueryHandler(handle_report_choice, pattern=r"^(report_\d+|report_all|cancel_report)$"))

    # Prenotazione rapida dalle notifiche di monitoraggio
    application.add_handler(CallbackQueryHandler(handle_quickbook, pattern="^quickbook_"))
    application.add_handler(CallbackQueryHandler(handle_quickslot_choice, pattern=r"^(qslot_\d+|cancel_qslot)$"))
    application.add_handler(CallbackQueryHandler(handle_quickbook_confirm, pattern=r"^confirm_qslot_\d+$"))

    # Pulsanti di messaggi vecchi: rispondiamo sempre, così non resta la rotellina
    application.add_handler(CallbackQueryHandler(stale_button))

    application.add_error_handler(error_handler)
