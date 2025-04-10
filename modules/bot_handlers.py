import re, os, json
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

from modules.booking_client import (
    booking_workflow, cancel_booking, get_booking_document, 
    get_user_bookings
)
from datetime import datetime
from io import BytesIO

# Importiamo le variabili globali dal modulo principale
from config import (
    logger, user_data, authorized_users, MAIN_KEYBOARD, ADMIN_KEYBOARD, is_admin, PDF_FOLDER,
    WAITING_FOR_FISCAL_CODE, WAITING_FOR_NRE, CONFIRM_ADD,
    WAITING_FOR_PRESCRIPTION_TO_DELETE, WAITING_FOR_PRESCRIPTION_TO_TOGGLE,
    WAITING_FOR_DATE_FILTER, WAITING_FOR_MONTHS_LIMIT, CONFIRM_DATE_FILTER,
    WAITING_FOR_BOOKING_CHOICE, WAITING_FOR_BOOKING_CONFIRMATION, WAITING_FOR_PHONE,
    WAITING_FOR_EMAIL, WAITING_FOR_SLOT_CHOICE, WAITING_FOR_BOOKING_TO_CANCEL, WAITING_FOR_AUTO_BOOK_CHOICE, AUTHORIZING,
    WAITING_FOR_PRESCRIPTION_BLACKLIST, WAITING_FOR_HOSPITAL_SELECTION,
    WAITING_FOR_BROADCAST_MESSAGE, WAITING_FOR_BROADCAST_CONFIRMATION,
    WAITING_FOR_FISCAL_CODE_REPORT, WAITING_FOR_PASSWORD_REPORT, WAITING_FOR_REPORT_CHOICE, WAITING_FOR_REPORTS_MONITORING_ACTION
)


# Importiamo le funzioni da altri moduli
from modules.data_utils import (
    load_authorized_users, save_authorized_users, 
    load_input_data, save_input_data,
    load_previous_data, save_previous_data
)
from modules.prescription_processor import process_prescription

from modules.locations_db import load_locations_db

from modules.reports_client import (
    download_reports, download_report_document, 
    download_all_report_documents
)

from io import BytesIO

# =============================================================================
# FUNZIONI DI UTILITY PER IL BOT
# =============================================================================

async def send_telegram_message(chat_id, text, parse_mode="HTML"):
    """Invia un messaggio Telegram."""
    try:
        import requests
        
        from recup_monitor import TELEGRAM_TOKEN
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        
        return True
    except Exception as e:
        logger.error(f"Errore nell'inviare messaggio Telegram: {str(e)}")
        return False

# =============================================================================
# GESTORI DOWNLOAD REFERTI BOT
# =============================================================================
async def download_medical_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia il processo di monitoraggio dei referti medici."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Tastiera con pulsante Annulla
    cancel_keyboard = ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True)
    
    await update.message.reply_text(
        "📋 <b>Monitoraggio Referti Medici</b>\n\n"
        "Questo servizio controllerà periodicamente la disponibilità di nuovi referti "
        "e ti invierà una notifica quando saranno disponibili.\n\n"
        "Per configurare il monitoraggio, ho bisogno di alcune informazioni.\n\n"
        "Per prima cosa, inserisci il tuo <b>codice fiscale</b>:",
        reply_markup=cancel_keyboard,
        parse_mode="HTML"
    )
    
    # Inizializziamo i dati dell'utente
    user_data[user_id] = {"action": "monitor_reports"}
    
    return WAITING_FOR_FISCAL_CODE_REPORT

async def handle_fiscal_code_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del codice fiscale per il monitoraggio dei referti."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Controlliamo se l'utente vuole annullare
    if text == "❌ Annulla" or text.lower() == "/cancel":
        return await cancel_operation(update, context)
    
    fiscal_code = text.upper()
    
    # Validazione base del codice fiscale (16 caratteri alfanumerici)
    if not re.match("^[A-Z0-9]{16}$", fiscal_code):
        await update.message.reply_text(
            "⚠️ Il codice fiscale inserito non sembra valido. Deve essere composto da 16 caratteri alfanumerici.\n\n"
            "Per favore, riprova o scrivi ❌ Annulla per tornare al menu principale:"
        )
        return WAITING_FOR_FISCAL_CODE_REPORT
    
    # Salviamo il codice fiscale
    user_data[user_id]["fiscal_code"] = fiscal_code
    
    # Cerchiamo se il codice fiscale è presente nelle prescrizioni monitorate
    # per estrarre automaticamente il codice TSCNS
    tscns_code = "8038000"  # Valore predefinito
    prescriptions = load_input_data()
    
    for prescription in prescriptions:
        if prescription["fiscal_code"] == fiscal_code:
            # Controlliamo se ci sono informazioni del paziente con il codice della tessera sanitaria
            if "patient_info" in prescription and "teamCard" in prescription["patient_info"]:
                team_card_code = prescription["patient_info"]["teamCard"].get("code", "")
                if team_card_code:
                    # Usiamo il codice completo della tessera sanitaria
                    tscns_code = team_card_code
                    logger.info(f"Trovato codice tessera sanitaria {tscns_code} per il CF {fiscal_code} nelle prescrizioni")
                    break
    
    # Salviamo il codice TSCNS (sia quello trovato che quello predefinito)
    user_data[user_id]["tscns"] = tscns_code
    
    # Aggiungiamo un messaggio che mostra il codice tessera sanitaria usato
    tscns_info = ""
    if tscns_code != "8038000":
        tscns_info = f"\nCodice tessera sanitaria: <code>{tscns_code}</code> (estratto automaticamente)"
    else:
        tscns_info = f"\nCodice tessera sanitaria: <code>{tscns_code}</code> (valore predefinito)"
    
    await update.message.reply_text(
        f"Codice fiscale: {fiscal_code}{tscns_info}\n\n"
        "Ora inserisci la <b>password</b> che hai ricevuto via SMS dalla Regione Lazio.\n\n"
        "<i>Nota: questa è la password che ricevi via SMS con testo simile a: "
        "'Regione Lazio su https://www.salutelazio.it/scarica-il-tuo-referto sara' possibile recuperare l'esito dell'esame effettuato. La password e' XXXXXXXXXX'</i>",
        reply_markup=ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True),
        parse_mode="HTML"
    )
    
    return WAITING_FOR_PASSWORD_REPORT
 
async def handle_password_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input della password per il monitoraggio dei referti."""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    # Controlliamo se l'utente vuole annullare
    if password == "❌ Annulla" or password.lower() == "/cancel":
        return await cancel_operation(update, context)
    
    # Validazione base della password (10 caratteri alfanumerici, come nell'esempio SMS)
    if not re.match("^[A-Z0-9]{10}$", password.upper()):
        await update.message.reply_text(
            "⚠️ La password inserita non sembra valida. Deve essere composta da 10 caratteri alfanumerici, "
            "come quella ricevuta via SMS.\n\n"
            "Per favore, riprova o scrivi ❌ Annulla per tornare al menu principale:",
            parse_mode="HTML"
        )
        return WAITING_FOR_PASSWORD_REPORT
    
    # Salviamo la password
    user_data[user_id]["password"] = password.upper()
    
    # Otteniamo i dati necessari
    fiscal_code = user_data[user_id]["fiscal_code"]
    tscns = user_data[user_id]["tscns"]
    
    # Verifichiamo che i dati siano validi facendo un test
    waiting_msg = await update.message.reply_text(
        f"🔍 Sto verificando le credenziali... Potrebbe richiedere alcuni secondi."
    )
    
    # Importa la nuova funzione per aggiungere il monitoraggio
    from modules.reports_monitor import add_report_monitoring
    
    # Proviamo a fare una richiesta di test
    from modules.reports_client import download_reports
    test_reports = download_reports(fiscal_code, password.upper(), tscns)
    
    # Configuriamo il monitoraggio anche se non ci sono referti
    # Questo è il cambiamento principale: non usiamo la mancanza di referti come errore
    success = add_report_monitoring(
        fiscal_code=fiscal_code,
        password=password.upper(),
        tscns=tscns,
        telegram_chat_id=user_id
    )
    
    if success:
        await waiting_msg.delete()
        
        # Ripristina la tastiera principale
        keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD
        
        # Modifichiamo il messaggio in base alla presenza o meno di referti
        if test_reports and len(test_reports) > 0:
            num_reports = len(test_reports)
            message = (
                f"✅ <b>Monitoraggio referti attivato con successo!</b>\n\n"
                f"Il sistema verificherà periodicamente la disponibilità di nuovi referti per:\n"
                f"<b>Codice Fiscale:</b> <code>{fiscal_code}</code>\n\n"
                f"Attualmente sono disponibili {num_reports} referti.\n\n"
                f"Se vuoi scaricare i referti esistenti, usa il comando '📋 Gestisci Monitoraggi Referti'."
            )
        else:
            message = (
                f"✅ <b>Monitoraggio referti attivato con successo!</b>\n\n"
                f"Il sistema verificherà periodicamente la disponibilità di nuovi referti per:\n"
                f"<b>Codice Fiscale:</b> <code>{fiscal_code}</code>\n\n"
                f"Attualmente non sono disponibili referti. Riceverai una notifica "
                f"non appena un referto sarà disponibile.\n\n"
                f"Il sistema verificherà ogni 5 minuti. Le credenziali sono state salvate correttamente."
            )
        
        await update.message.reply_text(
            message,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        await waiting_msg.delete()
        await update.message.reply_text(
            "❌ Si è verificato un errore nell'attivazione del monitoraggio. Riprova più tardi."
        )
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END
    

async def list_report_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra la lista dei monitoraggi referti attivi."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Importa la funzione necessaria
    from modules.reports_monitor import load_reports_monitoring
    
    # Carica i dati di monitoraggio
    monitoring_data = load_reports_monitoring()
    
    # Filtra i monitoraggi dell'utente (o tutti se è admin)
    is_admin_user = is_admin(user_id, authorized_users)
    
    if is_admin_user:
        # L'admin vede tutti i monitoraggi
        user_monitoring = monitoring_data
    else:
        # Gli utenti normali vedono solo i propri
        user_monitoring = [m for m in monitoring_data if m.get("telegram_chat_id") == user_id]
    
    if not user_monitoring:
        await update.message.reply_text("📋 Non hai monitoraggi referti attivi.")
        return
    
    # Costruisci il messaggio
    message = "📋 <b>Monitoraggi Referti Attivi:</b>\n\n"
    
    for idx, monitoring in enumerate(user_monitoring):
        fiscal_code = monitoring["fiscal_code"]
        enabled = monitoring.get("enabled", True)
        last_check = monitoring.get("last_check", "Mai")
        known_reports = monitoring.get("known_reports", [])
        
        # Formatta l'ultimo controllo
        if last_check and last_check != "Mai":
            try:
                check_date = datetime.fromisoformat(last_check)
                formatted_check = check_date.strftime("%d/%m/%Y %H:%M:%S")
            except:
                formatted_check = last_check
        else:
            formatted_check = "Mai controllato"
        
        # Verifica se è attivo
        status = "✅ attivo" if enabled else "❌ disattivato"
        
        message += f"{idx+1}. <b>Codice Fiscale:</b> <code>{fiscal_code}</code>\n"
        message += f"   Stato: {status}\n"
        message += f"   Ultimo controllo: {formatted_check}\n"
        message += f"   Referti noti: {len(known_reports)}\n\n"
    
    # Crea la tastiera inline
    keyboard = []
    
    # Pulsanti per disattivare/attivare
    for idx, monitoring in enumerate(user_monitoring):
        fiscal_code = monitoring["fiscal_code"]
        enabled = monitoring.get("enabled", True)
        
        action = "disattiva" if enabled else "attiva"
        keyboard.append([
            InlineKeyboardButton(f"{'❌' if enabled else '✅'} {action.capitalize()} {fiscal_code}", 
                               callback_data=f"toggle_monitor_{idx}")
        ])
    
    # Pulsante per rimuovere
    for idx, monitoring in enumerate(user_monitoring):
        fiscal_code = monitoring["fiscal_code"]
        keyboard.append([
            InlineKeyboardButton(f"🗑️ Rimuovi {fiscal_code}", 
                               callback_data=f"remove_monitor_{idx}")
        ])
    
    # Pulsante per verificare subito tutti i monitoraggi
    keyboard.append([
        InlineKeyboardButton("🔄 Verifica Ora", callback_data="check_reports_now")
    ])
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_report_monitoring_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce le azioni sui monitoraggi referti (toggle, remove, check)."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data  # Estrai il valore PRIMA di usarlo
    
    logger.info(f"Ricevuta callback per monitoraggio: {callback_data}")
    
    # Importa le funzioni necessarie
    from modules.reports_monitor import (
        load_reports_monitoring, save_reports_monitoring, 
        toggle_report_monitoring, remove_report_monitoring,
        check_new_reports
    )
    
    # Carica i dati di monitoraggio
    monitoring_data = load_reports_monitoring()
    
    # Filtra i monitoraggi dell'utente (o tutti se è admin)
    is_admin_user = is_admin(user_id, authorized_users)
    
    if is_admin_user:
        # L'admin vede tutti i monitoraggi
        user_monitoring = monitoring_data
    else:
        # Gli utenti normali vedono solo i propri
        user_monitoring = [m for m in monitoring_data if m.get("telegram_chat_id") == user_id]
    
    if callback_data.startswith("toggle_monitor_"):
        # Toggle del monitoraggio
        idx = int(callback_data.split("_")[-1])
        
        if idx < 0 or idx >= len(user_monitoring):
            await query.edit_message_text("⚠️ Indice non valido.")
            return ConversationHandler.END
        
        fiscal_code = user_monitoring[idx]["fiscal_code"]
        
        # Inverti lo stato
        success, new_state = toggle_report_monitoring(fiscal_code)
        
        if success:
            state_text = "attivato" if new_state else "disattivato"
            status_emoji = "✅" if new_state else "❌"
            
            # Ricarica i dati per avere l'ultimo stato
            updated_monitoring = load_reports_monitoring()
            
            # Ricostruisci la lista dei monitoraggi
            keyboard = []
            current_row = []
            
            for midx, monitoring in enumerate(updated_monitoring):
                # Solo i monitoraggi dell'utente corrente
                if (is_admin_user or 
                    str(monitoring.get("telegram_chat_id")) == str(user_id)):
                    fc = monitoring["fiscal_code"]
                    pw = monitoring["password"]
                    enabled = monitoring.get("enabled", True)
                    
                    status = "✅" if enabled else "❌"
                    current_row.append(
                        InlineKeyboardButton(
                            f"{status} {fc}:{pw}", 
                            callback_data=f"toggle_monitor_{midx}"
                        )
                    )
                    
                    # 3 pulsanti per riga
                    if len(current_row) == 3:
                        keyboard.append(current_row)
                        current_row = []
            
            # Aggiungi ultima riga incompleta
            if current_row:
                keyboard.append(current_row)
            
            # Aggiungi pulsanti di rimozione
            remove_row = []
            for midx, monitoring in enumerate(updated_monitoring):
                if (is_admin_user or 
                    str(monitoring.get("telegram_chat_id")) == str(user_id)):
                    fc = monitoring["fiscal_code"]
                    pw = monitoring["password"]
                    remove_row.append(
                        InlineKeyboardButton(
                            f"🗑️ {fc}:{pw}", 
                            callback_data=f"remove_monitor_{midx}"
                        )
                    )
                    
                    # 3 pulsanti per riga
                    if len(remove_row) == 3:
                        keyboard.append(remove_row)
                        remove_row = []
            
            # Aggiungi ultima riga incompleta di rimozione
            if remove_row:
                keyboard.append(remove_row)
            
            # Aggiungi pulsante di verifica
            keyboard.append([
                InlineKeyboardButton("🔄 Verifica Ora", callback_data="check_reports_now")
            ])
            
            await query.edit_message_text(
                f"{status_emoji} Monitoraggio referti {state_text} per il codice fiscale: <code>{fiscal_code}</code>\n\n",
                #reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text("⚠️ Errore nella modifica dello stato del monitoraggio.")
        
        return ConversationHandler.END
    
    elif callback_data.startswith("remove_monitor_"):
        # Rimozione del monitoraggio
        idx = int(callback_data.split("_")[-1])
        
        if idx < 0 or idx >= len(user_monitoring):
            await query.edit_message_text("⚠️ Indice non valido.")
            return ConversationHandler.END
        
        fiscal_code = user_monitoring[idx]["fiscal_code"]
        
        # Rimuovi il monitoraggio
        success = remove_report_monitoring(fiscal_code)
        
        if success:
            # Ricarica i dati per aggiornare la vista
            updated_monitoring = load_reports_monitoring()
            
            # Ricostruisci la lista dei monitoraggi
            keyboard = []
            current_row = []
            
            for midx, monitoring in enumerate(updated_monitoring):
                # Solo i monitoraggi dell'utente corrente
                if (is_admin_user or 
                    str(monitoring.get("telegram_chat_id")) == str(user_id)):
                    fc = monitoring["fiscal_code"]
                    enabled = monitoring.get("enabled", True)
                    
                    status = "✅" if enabled else "❌"
                    current_row.append(
                        InlineKeyboardButton(
                            f"{status} {fc[-4:]}", 
                            callback_data=f"toggle_monitor_{midx}"
                        )
                    )
                    
                    # 3 pulsanti per riga
                    if len(current_row) == 3:
                        keyboard.append(current_row)
                        current_row = []
            
            # Aggiungi ultima riga incompleta
            if current_row:
                keyboard.append(current_row)
            
            # Aggiungi pulsanti di rimozione
            remove_row = []
            for midx, monitoring in enumerate(updated_monitoring):
                if (is_admin_user or 
                    str(monitoring.get("telegram_chat_id")) == str(user_id)):
                    fc = monitoring["fiscal_code"]
                    remove_row.append(
                        InlineKeyboardButton(
                            f"🗑️ {fc[-4:]}", 
                            callback_data=f"remove_monitor_{midx}"
                        )
                    )
                    
                    # 3 pulsanti per riga
                    if len(remove_row) == 3:
                        keyboard.append(remove_row)
                        remove_row = []
            
            # Aggiungi ultima riga incompleta di rimozione
            if remove_row:
                keyboard.append(remove_row)
            
            # Aggiungi pulsante di verifica
            keyboard.append([
                InlineKeyboardButton("🔄 Verifica Ora", callback_data="check_reports_now")
            ])
            
            await query.edit_message_text(
                f"✅ Monitoraggio referti rimosso per il codice fiscale: <code>{fiscal_code}</code>\n\n"
                f"Seleziona un'azione:",
                #reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text("⚠️ Errore nella rimozione del monitoraggio.")
        
        return ConversationHandler.END
    
    elif callback_data == "check_reports_now":
        # Verifica immediata dei referti
        await query.edit_message_text("🔍 Verifica in corso... Attendere prego.")
        
        try:
            # Esegui il controllo
            total_checked, total_notifications, errors = check_new_reports()
            
            # Mostra il risultato
            result_message = (
                f"✅ Verifica completata!\n\n"
                f"Monitoraggi controllati: {total_checked}\n"
                f"Notifiche inviate: {total_notifications}\n"
            )
            
            if errors > 0:
                result_message += f"⚠️ Errori riscontrati: {errors}\n"
            
            result_message += "\nSe sono stati trovati nuovi referti, riceverai notifiche separate."
            
            # Ricostruisci la lista dei monitoraggi
            updated_monitoring = load_reports_monitoring()
            
            keyboard = []
            current_row = []
            
            for midx, monitoring in enumerate(updated_monitoring):
                # Solo i monitoraggi dell'utente corrente
                if (is_admin_user or 
                    str(monitoring.get("telegram_chat_id")) == str(user_id)):
                    fc = monitoring["fiscal_code"]
                    enabled = monitoring.get("enabled", True)
                    
                    status = "✅" if enabled else "❌"
                    current_row.append(
                        InlineKeyboardButton(
                            f"{status} {fc[-4:]}", 
                            callback_data=f"toggle_monitor_{midx}"
                        )
                    )
                    
                    # 3 pulsanti per riga
                    if len(current_row) == 3:
                        keyboard.append(current_row)
                        current_row = []
            
            # Aggiungi ultima riga incompleta
            if current_row:
                keyboard.append(current_row)
            
            # Aggiungi pulsanti di rimozione
            remove_row = []
            for midx, monitoring in enumerate(updated_monitoring):
                if (is_admin_user or 
                    str(monitoring.get("telegram_chat_id")) == str(user_id)):
                    fc = monitoring["fiscal_code"]
                    remove_row.append(
                        InlineKeyboardButton(
                            f"🗑️ {fc[-4:]}", 
                            callback_data=f"remove_monitor_{midx}"
                        )
                    )
                    
                    # 3 pulsanti per riga
                    if len(remove_row) == 3:
                        keyboard.append(remove_row)
                        remove_row = []
            
            # Aggiungi ultima riga incompleta di rimozione
            if remove_row:
                keyboard.append(remove_row)
            
            # Aggiungi pulsante di verifica
            keyboard.append([
                InlineKeyboardButton("🔄 Verifica Ora", callback_data="check_reports_now")
            ])
            
            await query.edit_message_text(
                result_message,
                #reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Errore durante la verifica dei referti: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text("⚠️ Si è verificato un errore durante la verifica. Riprova più tardi.")
        
        return ConversationHandler.END
    else:
        # Callback non riconosciuta, log e ignora
        logger.warning(f"Ricevuta callback non riconosciuta: {callback_data}")
        return ConversationHandler.END
            
# Aggiungere una funzione alternativa per scaricare referti esistenti
async def download_existing_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia il processo di download dei referti già monitorati."""
    # Questa funzione mantiene la vecchia logica di download immediato
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Importa le funzioni necessarie
    from modules.reports_monitor import load_reports_monitoring
    
    # Carica i dati di monitoraggio
    monitoring_data = load_reports_monitoring()
    
    # Filtra i monitoraggi dell'utente (o tutti se è admin)
    is_admin_user = is_admin(user_id, authorized_users)
    
    if is_admin_user:
        # L'admin vede tutti i monitoraggi
        user_monitoring = monitoring_data
    else:
        # Gli utenti normali vedono solo i propri
        user_monitoring = [m for m in monitoring_data if m.get("telegram_chat_id") == user_id]
    
    if not user_monitoring:
        # Se non ci sono monitoraggi, mostra un messaggio
        await update.message.reply_text(
            "⚠️ Non hai monitoraggi referti configurati.\n\n"
            "Usa prima '📊 Configura Monitoraggio Referti' per configurare l'accesso."
        )
        return
    
    # Crea una tastiera con le opzioni di monitoraggio
    keyboard = []
    for idx, monitoring in enumerate(user_monitoring):
        fiscal_code = monitoring["fiscal_code"]
        keyboard.append([
            InlineKeyboardButton(f"📊 {fiscal_code}", callback_data=f"download_reports_{idx}")
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_download_reports")])
    
    await update.message.reply_text(
        "Seleziona il monitoraggio per cui vuoi scaricare i referti:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_FOR_REPORT_CHOICE

async def handle_report_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione del referto da scaricare."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel_report":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo le informazioni necessarie
    fiscal_code = user_data[user_id]["fiscal_code"]
    password = user_data[user_id]["password"]
    tscns = user_data[user_id]["tscns"]
    reports = user_data[user_id]["reports"]
    
    # Inviamo un messaggio di attesa
    await query.edit_message_text("📥 Download in corso... Attendere prego.")
    
    # Importa le funzioni per il monitoraggio
    from modules.reports_monitor import load_reports_monitoring, save_reports_monitoring
    
    # Carica i dati di monitoraggio
    monitoring_data = load_reports_monitoring()
    
    # Trova il monitoraggio corrispondente
    monitoring_item = None
    monitoring_index = -1
    for i, item in enumerate(monitoring_data):
        if item["fiscal_code"] == fiscal_code:
            monitoring_item = item
            monitoring_index = i
            break
    
    if callback_data == "report_all":
        # Scarica tutti i referti
        await query.edit_message_text("📥 Download in corso di tutti i referti... Attendere prego.")
        
        # Import necessari
        from modules.reports_client import download_report_document
        from io import BytesIO
        
        # Contatori per il risultato
        success_count = 0
        error_count = 0
        
        # Lista di ID scaricati con successo
        downloaded_ids = []
        
        # Inviamo i file all'utente
        for report in reports:
            try:
                document_id = report.get("document_id")
                if not document_id:
                    continue
                    
                # Scarica il documento
                document_content = download_report_document(document_id, fiscal_code, password, tscns)
                
                if not document_content:
                    error_count += 1
                    continue
                
                # Estrai informazioni
                provider = report.get("provider", "Struttura sconosciuta")
                doc_type = report.get("document_type", "Referto")
                doc_date = report.get("document_date", "Data sconosciuta")
                
                # Formattare la data se possibile
                try:
                    date_obj = datetime.strptime(doc_date, "%Y%m%d")
                    formatted_date = date_obj.strftime("%d/%m/%Y")
                except:
                    formatted_date = doc_date
                
                # Crea un nome file
                filename = f"{doc_date}_{doc_type}_{provider}_{document_id}.pdf"
                filename = ''.join(c if c.isalnum() or c == '.' or c == '_' else '_' for c in filename)
                
                # Inviamo il file
                await context.bot.send_document(
                    chat_id=user_id,
                    document=BytesIO(document_content),
                    filename=filename,
                    caption=f"📋 {doc_type}\n📅 {formatted_date}\n🏥 {provider}"
                )
                
                success_count += 1
                downloaded_ids.append(document_id)
            except Exception as e:
                logger.error(f"Errore nell'invio del documento Telegram: {str(e)}")
                error_count += 1
        
        # Se abbiamo trovato il monitoraggio, disattiviamolo o aggiorniamo la lista dei referti noti
        if monitoring_item:
            # Rimuoviamo il monitoraggio
            monitoring_data.pop(monitoring_index)
            save_reports_monitoring(monitoring_data)
            
            await query.message.reply_text(
                f"✅ Download completato!\n\n"
                f"Referti scaricati con successo: {success_count}\n"
                f"Errori: {error_count}\n\n"
                f"Il monitoraggio referti per questo codice fiscale è stato rimosso."
            )
        else:
            await query.message.reply_text(
                f"✅ Download completato!\n\n"
                f"Referti scaricati con successo: {success_count}\n"
                f"Errori: {error_count}"
            )
        
    else:
        # Scarica un singolo referto
        idx = int(callback_data.split("_")[1])
        
        # Import necessari
        from modules.reports_client import download_report_document
        from io import BytesIO
        
        # Controlliamo che l'indice sia valido
        if idx < 0 or idx >= len(reports):
            await query.edit_message_text("⚠️ Referto non valido.")
            user_data.pop(user_id, None)
            return ConversationHandler.END
        
        # Otteniamo il referto
        report = reports[idx]
        document_id = report.get("document_id")
        
        if not document_id:
            await query.edit_message_text("⚠️ ID documento non valido.")
            user_data.pop(user_id, None)
            return ConversationHandler.END
        
        # Scarica il documento
        document_content = download_report_document(document_id, fiscal_code, password, tscns)
        
        if not document_content:
            await query.edit_message_text("❌ Errore nel download del referto.")
            # Puliamo i dati dell'utente
            user_data.pop(user_id, None)
            return ConversationHandler.END
        
        # Estrai informazioni
        provider = report.get("provider", "Struttura sconosciuta")
        doc_type = report.get("document_type", "Referto")
        doc_date = report.get("document_date", "Data sconosciuta")
        
        # Formattare la data se possibile
        try:
            date_obj = datetime.strptime(doc_date, "%Y%m%d")
            formatted_date = date_obj.strftime("%d/%m/%Y")
        except:
            formatted_date = doc_date
        
        # Crea un nome file
        filename = f"{doc_date}_{doc_type}_{provider}_{document_id}.pdf"
        filename = ''.join(c if c.isalnum() or c == '.' or c == '_' else '_' for c in filename)
        
        # Inviamo il file
        await query.message.reply_document(
            document=BytesIO(document_content),
            filename=filename,
            caption=f"📋 {doc_type}\n📅 {formatted_date}\n🏥 {provider}"
        )
        
        # Se abbiamo trovato il monitoraggio, rimuoviamolo
        if monitoring_item:
            # Rimuoviamo il monitoraggio se c'è solo questo referto
            if len(reports) == 1:
                monitoring_data.pop(monitoring_index)
                save_reports_monitoring(monitoring_data)
                await query.message.reply_text(
                    "✅ Referto scaricato con successo!\n"
                    "Il monitoraggio referti per questo codice fiscale è stato rimosso."
                )
            else:
                # Se ci sono più referti, rimuoviamo solo questo dalla lista dei monitorati
                await query.message.reply_text(
                    "✅ Referto scaricato con successo!\n"
                    "Ci sono ancora altri referti disponibili. Il monitoraggio continuerà per gli altri."
                )
        else:
            await query.message.reply_text("✅ Referto scaricato con successo!")
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END

async def handle_download_reports_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione del monitoraggio per cui scaricare i referti."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel_download_reports":
        await query.edit_message_text("❌ Operazione annullata.")
        return ConversationHandler.END
    
    # Importa le funzioni necessarie
    from modules.reports_monitor import load_reports_monitoring
    from modules.reports_client import download_reports
    
    # Carica i dati di monitoraggio
    monitoring_data = load_reports_monitoring()
    
    # Filtra i monitoraggi dell'utente (o tutti se è admin)
    is_admin_user = is_admin(user_id, authorized_users)
    
    if is_admin_user:
        # L'admin vede tutti i monitoraggi
        user_monitoring = monitoring_data
    else:
        # Gli utenti normali vedono solo i propri
        user_monitoring = [m for m in monitoring_data if m.get("telegram_chat_id") == user_id]
    
    # Estrai l'indice
    idx = int(callback_data.split("_")[-1])
    
    if idx < 0 or idx >= len(user_monitoring):
        await query.edit_message_text("⚠️ Selezione non valida.")
        return ConversationHandler.END
    
    # Ottieni le informazioni del monitoraggio
    monitoring = user_monitoring[idx]
    fiscal_code = monitoring["fiscal_code"]
    password = monitoring["password"]
    tscns = monitoring["tscns"]
    
    # Invia un messaggio di attesa
    await query.edit_message_text("🔍 Recupero dei referti in corso... Attendere prego.")
    
    # Scarica i referti
    reports = download_reports(fiscal_code, password, tscns)
    
    if not reports or len(reports) == 0:
        await query.edit_message_text(
            "ℹ️ Non ci sono referti disponibili per questo monitoraggio."
        )
        return ConversationHandler.END
    
    # Salva i referti nell'utente per il download successivo
    user_data[user_id] = {
        "action": "download_reports",
        "fiscal_code": fiscal_code,
        "password": password,
        "tscns": tscns,
        "reports": reports
    }
    
    # Creiamo i pulsanti per i referti
    keyboard = []
    
    for idx, report in enumerate(reports):
        # Estrai informazioni
        provider = report.get("provider", "Struttura sconosciuta")
        doc_type = report.get("document_type", "Referto")
        doc_date = report.get("document_date", "Data sconosciuta")
        
        # Crea una descrizione breve ma informativa
        short_desc = f"{doc_type} - {provider} ({doc_date})"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. {short_desc[:50]}...",
                callback_data=f"report_{idx}"
            )
        ])
    
    # Aggiungiamo un pulsante per scaricare tutti i referti
    keyboard.append([InlineKeyboardButton("📥 Scarica tutti", callback_data="report_all")])
    
    # Aggiungiamo un pulsante per annullare
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_report")])
    
    # Aggiorniamo il messaggio con la lista dei referti
    await query.edit_message_text(
        f"📋 <b>Referti disponibili ({len(reports)}):</b>\n\n"
        "Seleziona un referto da scaricare:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return WAITING_FOR_REPORT_CHOICE
    
# =============================================================================
# GESTORI COMANDI BOT
# =============================================================================
def get_safe_description(prescription):
    """
    Ottiene una descrizione sicura dalla prescrizione.
    
    Args:
        prescription (dict): La prescrizione da cui ottenere la descrizione
        
    Returns:
        str: Una descrizione sicura
    """
    description = prescription.get('description', '')
    if not description:
        # Se la descrizione non è disponibile, usiamo l'NRE
        description = f"Prescrizione {prescription.get('nre', 'sconosciuta')}"
    return description
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestore del comando /start."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text(
            "🔒 Non sei autorizzato ad utilizzare questo bot. Contatta l'amministratore per ottenere l'accesso."
        )
        logger.warning(f"Tentativo di accesso non autorizzato da {user_id}")
        return
    
    # Verifichiamo se l'utente è admin
    keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD

    
    await update.message.reply_text(
        f"👋 Benvenuto, {update.effective_user.first_name}!\n\n"
        "Questo bot ti aiuterà a monitorare le disponibilità del Servizio Sanitario Nazionale.\n\n"
        "Utilizza i pulsanti sotto per gestire le prescrizioni da monitorare o per scaricare i tuoi referti.",
        reply_markup=keyboard
    )
    
# =============================================================================
# GESTORI PRESCRIZIONI: AGGIUNTA
# =============================================================================

async def manage_hospital_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la blacklist degli ospedali per una prescrizione."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        user_prescriptions = prescriptions
    else:
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END
    
    # Costruiamo il corpo del messaggio con le informazioni dettagliate
    message = "🚫 <b>Blacklist Ospedali</b>\n\nSeleziona la prescrizione:\n\n"
    
    for idx, prescription in enumerate(user_prescriptions):
        desc = prescription.get("description", "Prescrizione")
        fiscal_code = prescription["fiscal_code"]
        
        # Mostriamo il numero di ospedali in blacklist
        blacklist_count = len(prescription.get("config", {}).get("hospitals_blacklist", []))
        blacklist_status = f"{blacklist_count} ospedali esclusi" if blacklist_count else "nessun ospedale escluso"
        
        message += f"{idx+1}. <b>{desc}</b>\n"
        message += f"   CF: {fiscal_code} • {blacklist_status}\n\n"
    
    # Creiamo pulsanti più compatti, 3 per riga
    keyboard = []
    current_row = []
    
    for idx, _ in enumerate(user_prescriptions):
        current_row.append(
            InlineKeyboardButton(
                f"{idx+1}",  # Solo il numero
                callback_data=f"blacklist_{idx}"
            )
        )
        
        # Quando abbiamo 4 pulsanti nella riga corrente, la aggiungiamo alla tastiera
        if len(current_row) == 4 or idx == len(user_prescriptions) - 1:
            keyboard.append(current_row)
            current_row = []
    
    # Aggiungiamo il pulsante Annulla
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_blacklist")])
    
    # Salviamo le prescrizioni nei dati dell'utente
    user_data[user_id] = {
        "action": "manage_hospital_blacklist",
        "prescriptions": user_prescriptions
    }
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return WAITING_FOR_PRESCRIPTION_BLACKLIST
    
async def handle_prescription_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prescrizione per modificare la blacklist."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    logger.info(f"Gestione blacklist: callback_data={callback_data}")
    
    if callback_data == "cancel_blacklist":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Estraiamo l'indice della prescrizione
    idx = int(callback_data.split("_")[1])
    user_prescriptions = user_data[user_id]["prescriptions"]
    
    # Controlliamo che l'indice sia valido
    if idx < 0 or idx >= len(user_prescriptions):
        await query.edit_message_text("⚠️ Prescrizione non valida.")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo la prescrizione
    prescription = user_prescriptions[idx]
    user_data[user_id]["selected_prescription"] = prescription
    
    # Carichiamo il database delle location
    location_db = {}
    try:
        location_db = load_locations_db()
        logger.info(f"File locations caricato con successo. Trovate {len(location_db)} location.")
    except Exception as e:
        logger.error(f"Errore nel caricare il database delle location: {str(e)}")
    
    # Estraiamo i nomi degli ospedali dal database delle location
    # MODIFICA: Adattata alla struttura del tuo file locations.json
    hospitals = []
    
    for key, location in location_db.items():
        # In questo caso, usiamo il campo "hospital" nella struttura nidificata
        hospital_name = location.get("hospital", "")
        if hospital_name and hospital_name not in hospitals:
            hospitals.append(hospital_name)
    
    logger.info(f"Estratti {len(hospitals)} ospedali unici dal database.")
    
    # Se non ci sono ospedali, mostriamo un messaggio
    if not hospitals:
        # Per debug, mostriamo le chiavi del primo elemento del database
        debug_info = ""
        if location_db:
            first_key = next(iter(location_db))
            first_item = location_db[first_key]
            debug_info = f"\n\nStruttura del primo elemento:\n{first_key}: {first_item}"
        
        await query.edit_message_text(
            f"⚠️ Nessun ospedale trovato nel database.{debug_info}\n\n"
            f"Controlla la struttura del file locations.json o\n"
            f"usa la funzione 'Verifica Disponibilità' per popolare il database."
        )
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Ordiniamo gli ospedali alfabeticamente
    hospitals.sort()
    
    # Otteniamo la blacklist attuale
    current_blacklist = prescription.get("config", {}).get("hospitals_blacklist", [])
    logger.info(f"Blacklist attuale: {current_blacklist}")
    
    # Implementiamo una paginazione semplice
    hospitals_per_page = 10
    total_pages = (len(hospitals) + hospitals_per_page - 1) // hospitals_per_page
    
    # Salviamo i dati temporanei
    user_data[user_id]["hospitals"] = hospitals
    user_data[user_id]["current_blacklist"] = current_blacklist.copy()
    user_data[user_id]["page"] = 0
    
    # Mostriamo la prima pagina
    return await show_hospitals_page(query, user_id)

async def show_hospitals_page(query, user_id):
    """Mostra una pagina di ospedali."""
    hospitals = user_data[user_id]["hospitals"]
    current_blacklist = user_data[user_id]["current_blacklist"]
    page = user_data[user_id].get("page", 0)  # Default alla prima pagina
    prescription = user_data[user_id]["selected_prescription"]
    
    # Numero di ospedali per pagina
    hospitals_per_page = 10
    total_pages = (len(hospitals) + hospitals_per_page - 1) // hospitals_per_page
    
    # Calcola gli indici per la pagina corrente
    start_idx = page * hospitals_per_page
    end_idx = min(start_idx + hospitals_per_page, len(hospitals))
    
    # Costruisci il messaggio con la lista numerata degli ospedali
    message_text = (
        f"🚫 <b>Blacklist Ospedali</b>\n\n"
        f"Prescrizione: <b>{prescription.get('description', 'N/D')}</b>\n\n"
        f"<b>Seleziona gli ospedali da escludere:</b>\n"
        f"❌ = Escluso | ✅ = Incluso\n\n"
    )
    
    # Aggiungi gli ospedali al messaggio
    for i, idx in enumerate(range(start_idx, end_idx)):
        hospital = hospitals[idx]
        is_blacklisted = hospital in current_blacklist
        status = "❌" if is_blacklisted else "✅"
        message_text += f"{i+1}. {status} {hospital}\n"
    
    message_text += f"\nPagina {page+1}/{total_pages} • Ospedali esclusi: {len(current_blacklist)}/{len(hospitals)}"
    
    # Crea i pulsanti compatti (solo numeri)
    keyboard = []
    current_row = []
    
    for i, idx in enumerate(range(start_idx, end_idx)):
        hospital = hospitals[idx]
        is_blacklisted = hospital in current_blacklist
        button_text = f"{i+1}"  # Solo il numero
        
        # Aggiungi un indicatore visivo allo stato
        if is_blacklisted:
            button_text = f"❌{i+1}"
        else:
            button_text = f"✅{i+1}"
        
        current_row.append(InlineKeyboardButton(
            button_text,
            callback_data=f"toggle_hospital_{idx}_{is_blacklisted}"
        ))
        
        # 5 pulsanti per riga
        if len(current_row) == 5:
            keyboard.append(current_row)
            current_row = []
    
    # Aggiungi l'ultima riga se c'è
    if current_row:
        keyboard.append(current_row)
    
    # Pulsanti per blacklistare/whitelistare tutti
    blacklist_all_row = [
        InlineKeyboardButton("⬛ Blacklista tutti", callback_data="blacklist_all"),
        InlineKeyboardButton("⬜ Whitelist tutti", callback_data="whitelist_all")
    ]
    keyboard.append(blacklist_all_row)
    
    # Pulsanti di navigazione
    navigation = []
    
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️", callback_data="page_prev"))
    
    navigation.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="dummy"))
    
    if page < total_pages - 1:
        navigation.append(InlineKeyboardButton("➡️", callback_data="page_next"))
    
    keyboard.append(navigation)
    
    # Pulsanti per conferma/annulla
    keyboard.append([
        InlineKeyboardButton("✅ Conferma", callback_data="confirm_blacklist"),
        InlineKeyboardButton("❌ Annulla", callback_data="cancel_blacklist")
    ])
    
    try:
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Errore nell'aggiornare il messaggio: {str(e)}")
        try:
            # Potrebbe esserci un problema se il messaggio non è cambiato
            message_text += "\u200B"  # Carattere zero-width space
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except Exception as e2:
            logger.error(f"Secondo errore nell'aggiornare il messaggio: {str(e2)}")
    
    return WAITING_FOR_HOSPITAL_SELECTION

async def handle_hospital_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione di un ospedale per aggiungerlo/rimuoverlo dalla blacklist."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    logger.info(f"Hospital selection callback: {callback_data}")
    
    if callback_data == "cancel_blacklist":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    if callback_data == "confirm_blacklist":
        # Aggiorniamo la blacklist nella prescrizione
        return await confirm_hospital_blacklist(update, context)
    
    # Gestione delle pagine
    if callback_data == "page_prev":
        if "page" in user_data[user_id]:
            user_data[user_id]["page"] = max(0, user_data[user_id]["page"] - 1)
        else:
            user_data[user_id]["page"] = 0
        return await show_hospitals_page(query, user_id)
    
    if callback_data == "page_next":
        if "page" not in user_data[user_id]:
            user_data[user_id]["page"] = 0
        
        hospitals = user_data[user_id]["hospitals"]
        hospitals_per_page = 10
        total_pages = (len(hospitals) + hospitals_per_page - 1) // hospitals_per_page
        
        user_data[user_id]["page"] = min(user_data[user_id]["page"] + 1, total_pages - 1)
        return await show_hospitals_page(query, user_id)
    
    # Gestione blacklist/whitelist all
    if callback_data == "blacklist_all":
        # Blacklista tutti gli ospedali
        hospitals = user_data[user_id]["hospitals"]
        user_data[user_id]["current_blacklist"] = hospitals.copy()
        await query.answer("Tutti gli ospedali sono stati aggiunti alla blacklist")
        return await show_hospitals_page(query, user_id)  # Aggiornamento della pagina
    
    if callback_data == "whitelist_all":
        # Svuota la blacklist (whitelist tutti)
        user_data[user_id]["current_blacklist"] = []
        await query.answer("Tutti gli ospedali sono stati rimossi dalla blacklist")
        return await show_hospitals_page(query, user_id)  # Aggiornamento della pagina
    
    # Estraiamo i dati dalla callback per toggle hospital
    if callback_data.startswith("toggle_hospital_"):
        parts = callback_data.split("_")
        hospital_idx = int(parts[2])
        is_blacklisted = parts[3] == "True"
        
        # Otteniamo i dati necessari
        hospitals = user_data[user_id]["hospitals"]
        current_blacklist = user_data[user_id]["current_blacklist"]
        
        # Controlliamo che l'indice sia valido
        if hospital_idx < 0 or hospital_idx >= len(hospitals):
            await query.edit_message_text("⚠️ Ospedale non valido.")
            return WAITING_FOR_HOSPITAL_SELECTION
        
        # Otteniamo il nome dell'ospedale
        hospital_name = hospitals[hospital_idx]
        
        # Aggiorniamo la blacklist
        if is_blacklisted:
            # Rimuoviamo dalla blacklist
            if hospital_name in current_blacklist:
                current_blacklist.remove(hospital_name)
        else:
            # Aggiungiamo alla blacklist
            if hospital_name not in current_blacklist:
                current_blacklist.append(hospital_name)
        
        # Aggiorniamo i dati dell'utente
        user_data[user_id]["current_blacklist"] = current_blacklist
        
        # Mostriamo la pagina aggiornata
        return await show_hospitals_page(query, user_id)
    
    # Se arriviamo qui, è una callback non gestita
    logger.warning(f"Callback non gestita: {callback_data}")
    return WAITING_FOR_HOSPITAL_SELECTION  

async def confirm_hospital_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma e salva la blacklist degli ospedali."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Otteniamo i dati necessari
    prescription = user_data[user_id]["selected_prescription"]
    current_blacklist = user_data[user_id]["current_blacklist"]
    
    # Carichiamo tutte le prescrizioni
    all_prescriptions = load_input_data()
    
    # Cerchiamo la prescrizione nel dataset completo
    updated = False
    for p in all_prescriptions:
        if (p["fiscal_code"] == prescription["fiscal_code"] and 
            p["nre"] == prescription["nre"]):
            
            # Assicuriamo che esista la configurazione
            if "config" not in p:
                p["config"] = {}
            
            # Aggiorniamo la blacklist
            p["config"]["hospitals_blacklist"] = current_blacklist
            
            updated = True
            break
    
    if updated:
        # Salviamo le prescrizioni aggiornate
        save_input_data(all_prescriptions)
        
        # Aggiorniamo il messaggio
        await query.edit_message_text(
            f"✅ Blacklist aggiornata per:\n\n"
            f"Descrizione: {prescription.get('description', 'Non disponibile')}\n"
            f"Codice Fiscale: {prescription['fiscal_code']}\n"
            f"NRE: {prescription['nre']}\n\n"
            f"Ospedali esclusi: {len(current_blacklist)}\n"
            f"Ora riceverai notifiche solo per ospedali non presenti nella blacklist."
        )
    else:
        await query.edit_message_text("⚠️ Impossibile aggiornare la blacklist.")
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END

async def add_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'aggiunta di una nuova prescrizione."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Tastiera con pulsante Annulla
    cancel_keyboard = ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True)
    
    await update.message.reply_text(
        "Per aggiungere una nuova prescrizione da monitorare, ho bisogno di alcune informazioni.\n\n"
        "Per prima cosa, inserisci il codice fiscale del paziente:",
        reply_markup=cancel_keyboard
    )
    
    # Inizializziamo i dati dell'utente
    user_data[user_id] = {"action": "add_prescription"}
    
    return WAITING_FOR_FISCAL_CODE

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulla l'operazione corrente e torna al menu principale."""
    try:
        user_id = None
        
        # Gestione diversa se la cancellazione viene da un callback o da un messaggio
        if update.callback_query:
            # Cancellazione da una callback query
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            await query.edit_message_text("❌ Operazione annullata.")
        elif update.message:
            # Cancellazione da un messaggio di testo
            user_id = update.effective_user.id
            # Ripristiniamo la tastiera principale
            keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD

            await update.message.reply_text(
                "❌ Operazione annullata. Cosa vuoi fare?",
                reply_markup=keyboard
            )
        
        # Puliamo i dati dell'utente solo se abbiamo l'ID utente
        if user_id and user_id in user_data:
            user_data.pop(user_id, None)
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Errore in cancel_operation: {str(e)}")
        # In caso di errore, cerchiamo di ripulire i dati
        try:
            if update.effective_user and update.effective_user.id in user_data:
                user_data.pop(update.effective_user.id, None)
            elif update.callback_query and update.callback_query.from_user.id in user_data:
                user_data.pop(update.callback_query.from_user.id, None)
        except:
            pass
        return ConversationHandler.END
        
async def handle_fiscal_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del codice fiscale."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Controlliamo se l'utente vuole annullare
    if text == "❌ Annulla" or text.lower() == "/cancel":
        return await cancel_operation(update, context)
    
    fiscal_code = text.upper()
    
    # Validazione base del codice fiscale (16 caratteri alfanumerici)
    if not re.match("^[A-Z0-9]{16}$", fiscal_code):
        await update.message.reply_text(
            "⚠️ Il codice fiscale inserito non sembra valido. Deve essere composto da 16 caratteri alfanumerici.\n\n"
            "Per favore, riprova o scrivi ❌ Annulla per tornare al menu principale:"
        )
        return WAITING_FOR_FISCAL_CODE
    
    # Salviamo il codice fiscale
    user_data[user_id]["fiscal_code"] = fiscal_code
    
    await update.message.reply_text(
        f"Codice fiscale: {fiscal_code}\n\n"
        "Ora inserisci il codice NRE della prescrizione (numero di ricetta elettronica):",
        reply_markup=ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True)
    )
    
    return WAITING_FOR_NRE

async def handle_nre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del codice NRE."""
    user_id = update.effective_user.id
    nre = update.message.text.strip().upper()
    
    # Controlliamo se l'utente vuole annullare
    if nre == "❌ ANNULLA" or nre.lower() == "/cancel":
        return await cancel_operation(update, context)
    
    # Validazione base del codice NRE (15 caratteri alfanumerici)
    if not re.match("^[A-Z0-9]{15}$", nre):
        await update.message.reply_text(
            "⚠️ Il codice NRE inserito non sembra valido. Deve essere composto da 15 caratteri alfanumerici.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_NRE
    
    # Salviamo il codice NRE
    user_data[user_id]["nre"] = nre
    
    # Carichiamo le prescrizioni esistenti per verificare se è già presente
    prescriptions = load_input_data()
    
    # Controlliamo se la prescrizione esiste già
    fiscal_code = user_data[user_id]["fiscal_code"]
    for prescription in prescriptions:
        if prescription["fiscal_code"] == fiscal_code and prescription["nre"] == nre:
            await update.message.reply_text(
                "⚠️ Questa prescrizione è già presente nel sistema. Non è possibile aggiungerla di nuovo."
            )
            # Puliamo i dati dell'utente
            user_data.pop(user_id, None)
            return ConversationHandler.END
    
    # Chiediamo all'utente il numero di telefono
    await update.message.reply_text(
        f"Codice NRE: {nre}\n\n"
        f"Ora inserisci il tuo numero di telefono per eventuali prenotazioni automatiche:",
        reply_markup=ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True)
    )
    
    return WAITING_FOR_PHONE

async def handle_add_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del numero di telefono durante l'aggiunta di prescrizione."""
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    # Controlliamo se l'utente vuole annullare
    if phone == "❌ Annulla" or phone.lower() == "/cancel":
        return await cancel_operation(update, context)
    
    # Validazione base del numero di telefono (almeno 8 cifre)
    if not re.match("^[0-9+]{8,15}$", phone):
        await update.message.reply_text(
            "⚠️ Il numero di telefono inserito non sembra valido. Deve contenere almeno 8 cifre.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_PHONE
    
    # Salviamo il numero di telefono
    user_data[user_id]["phone"] = phone
    
    # Chiediamo l'email
    await update.message.reply_text(
        f"Numero di telefono: {phone}\n\n"
        f"Ora inserisci la tua email per eventuali prenotazioni automatiche:",
        reply_markup=ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True)
    )
    
    return WAITING_FOR_EMAIL

async def handle_add_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input dell'email durante l'aggiunta di prescrizione."""
    user_id = update.effective_user.id
    email = update.message.text.strip()
    
    # Controlliamo se l'utente vuole annullare
    if email == "❌ Annulla" or email.lower() == "/cancel":
        return await cancel_operation(update, context)
    
    # Verifica che i dati dell'utente siano corretti
    if user_id not in user_data:
        await update.message.reply_text(
            "⚠️ Si è verificato un errore nella sessione. Per favore, ricomincia l'operazione o premi /cancel."
        )
        return ConversationHandler.END
    
    # Verifica che sia l'azione corretta
    if user_data[user_id].get("action") != "add_prescription":
        await update.message.reply_text(
            "⚠️ Azione non corretta. Per favore, ricomincia l'operazione o premi /cancel."
        )
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Verifica che ci siano i dati necessari
    if "fiscal_code" not in user_data[user_id] or "nre" not in user_data[user_id] or "phone" not in user_data[user_id]:
        await update.message.reply_text(
            "⚠️ Dati incompleti. Per favore, ricomincia l'operazione."
        )
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Validazione base dell'email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text(
            "⚠️ L'email inserita non sembra valida.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_EMAIL
    
    # Salviamo l'email
    user_data[user_id]["email"] = email
    
    # Otteniamo i dati necessari
    fiscal_code = user_data[user_id]["fiscal_code"]
    nre = user_data[user_id]["nre"]
    phone = user_data[user_id]["phone"]
    
    await update.message.reply_text(
        f"Stai per aggiungere una nuova prescrizione con i seguenti dati:\n\n"
        f"Codice Fiscale: {fiscal_code}\n"
        f"NRE: {nre}\n"
        f"Telefono: {phone}\n"
        f"Email: {email}\n\n"
        f"Confermi?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sì, aggiungi", callback_data="confirm_add"),
                InlineKeyboardButton("❌ No, annulla", callback_data="cancel_add")
            ]
        ])
    )
    
    return CONFIRM_ADD

async def confirm_add_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma dell'aggiunta di una prescrizione."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "cancel_add":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Altrimenti, procediamo con l'aggiunta
    fiscal_code = user_data[user_id]["fiscal_code"]
    nre = user_data[user_id]["nre"]
    
    # Otteniamo i dati di contatto
    phone = user_data[user_id]["phone"]
    email = user_data[user_id]["email"]
    
    # Carichiamo le prescrizioni esistenti
    prescriptions = load_input_data()
    
    # Creiamo la nuova prescrizione con notifiche abilitate e configurazione di base
    new_prescription = {
        "fiscal_code": fiscal_code,
        "nre": nre,
        "telegram_chat_id": user_id,
        "notifications_enabled": True,  # Inizializziamo le notifiche come abilitate
        "auto_book_enabled": False,     # Prenotazione automatica disabilitata di default
        "phone": phone,                 # Aggiungiamo il telefono
        "email": email,                 # Aggiungiamo l'email
        "config": {
            "only_new_dates": True,
            "notify_removed": False,
            "min_changes_to_notify": 1,
            "time_threshold_minutes": 60,
            "show_all_current": True,
            "months_limit": None  # Nessun limite di mesi predefinito
        }
    }
    
    # Verifichiamo che la prescrizione sia valida
    previous_data = load_previous_data()
    success, message = process_prescription(new_prescription, previous_data, user_id)
    
    if not success:
        await query.edit_message_text(f"⚠️ Impossibile aggiungere la prescrizione: {message}")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Aggiungiamo la prescrizione
    prescriptions.append(new_prescription)
    logger.info(f"Prescrizione aggiunta: {new_prescription.get('description', 'Non disponibile')} per {fiscal_code}")
    logger.info(f"Totale prescrizioni: {len(prescriptions)}")
    
    save_input_data(prescriptions)
    save_previous_data(previous_data)
    
    # Aggiorniamo il messaggio
    await query.edit_message_text(
        f"✅ Prescrizione aggiunta con successo!\n\n"
        f"Descrizione: {new_prescription.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {fiscal_code}\n"
        f"NRE: {nre}\n\n"
        f"Riceverai notifiche quando saranno disponibili nuovi appuntamenti."
    )
    
    keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD

    await context.bot.send_message(
        chat_id=user_id,
        text="💡 Suggerimento: puoi attivare la prenotazione automatica usando la funzione '🤖 Prenota Automaticamente' "
             "per prenotare automaticamente il primo slot disponibile.",
        reply_markup=keyboard
    )
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END
    
# =============================================================================
# GESTORI PRESCRIZIONI: RIMOZIONE
# =============================================================================

async def remove_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la rimozione di una prescrizione."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da rimuovere.")
        return ConversationHandler.END
    
    # Creiamo i pulsanti per le prescrizioni
    keyboard = []
    
    for idx, prescription in enumerate(user_prescriptions):
        desc = prescription.get("description", "Prescrizione")
        fiscal_code = prescription["fiscal_code"]
        nre = prescription["nre"]
        
        # Creiamo un pulsante con identificativo della prescrizione
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. {desc[:30]}... ({fiscal_code[-4:]})",
                callback_data=f"remove_{idx}"
            )
        ])
    
    # Aggiungiamo un pulsante per annullare
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_remove")])
    
    # Salviamo le prescrizioni nei dati dell'utente
    user_data[user_id] = {
        "action": "remove_prescription",
        "prescriptions": user_prescriptions
    }
    
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
    callback_data = query.data
    
    if callback_data == "cancel_remove":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Estraiamo l'indice della prescrizione
    idx = int(callback_data.split("_")[1])
    user_prescriptions = user_data[user_id]["prescriptions"]
    
    # Controlliamo che l'indice sia valido
    if idx < 0 or idx >= len(user_prescriptions):
        await query.edit_message_text("⚠️ Prescrizione non valida.")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo la prescrizione
    prescription_to_remove = user_prescriptions[idx]
    
    # Carichiamo tutte le prescrizioni
    all_prescriptions = load_input_data()
    
    # Rimuoviamo la prescrizione
    new_prescriptions = []
    removed = False
    
    for prescription in all_prescriptions:
        if (prescription["fiscal_code"] == prescription_to_remove["fiscal_code"] and 
            prescription["nre"] == prescription_to_remove["nre"]):
            removed = True
        else:
            new_prescriptions.append(prescription)
    
    if removed:
        # Salviamo le prescrizioni aggiornate
        save_input_data(new_prescriptions)
        
        # Aggiorniamo il messaggio
        await query.edit_message_text(
            f"✅ Prescrizione rimossa con successo!\n\n"
            f"Descrizione: {prescription_to_remove.get('description', 'Non disponibile')}\n"
            f"Codice Fiscale: {prescription_to_remove['fiscal_code']}\n"
            f"NRE: {prescription_to_remove['nre']}"
        )
    else:
        await query.edit_message_text("⚠️ Impossibile rimuovere la prescrizione.")
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END

# =============================================================================
# GESTORI PRESCRIZIONI: LISTA E VERIFICA
# =============================================================================

async def list_prescriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra la lista delle prescrizioni monitorate."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        message = "📋 <b>Tutte le prescrizioni monitorate:</b>\n\n"
    else:
        # Gli utenti normali vedono solo le proprie
        prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
        message = "📋 <b>Le tue prescrizioni monitorate:</b>\n\n"
    
    if not prescriptions:
        await update.message.reply_text(
            "Non ci sono prescrizioni in monitoraggio." if is_admin else "Non hai prescrizioni in monitoraggio."
        )
        return
    
    # Costruiamo il messaggio
    for idx, prescription in enumerate(prescriptions):
        desc = prescription.get("description", "Prescrizione sconosciuta")
        fiscal_code = prescription["fiscal_code"]
        nre = prescription["nre"]
        
        # Verifica se la prescrizione ha prenotazioni
        has_booking = bool(prescription.get("bookings"))
        booking_status = "📑 Prenotata" if has_booking else "🔍 In monitoraggio"
        
        # Mostriamo lo stato delle notifiche
        notifications_enabled = prescription.get("notifications_enabled", True)
        notification_status = "🔔 attive" if notifications_enabled else "🔕 disattivate"
        
        # Mostriamo lo stato della prenotazione automatica
        auto_book_enabled = prescription.get("auto_book_enabled", False)
        auto_book_status = "🤖 attiva" if auto_book_enabled else "🤖 disattivata"
        
        # Mostriamo il limite di mesi se impostato
        months_limit = prescription.get("config", {}).get("months_limit")
        date_filter = f"⏱ entro {months_limit} mesi" if months_limit else "⏱ nessun filtro date"
        
        # Mostriamo il numero di ospedali in blacklist
        hospitals_blacklist = prescription.get("config", {}).get("hospitals_blacklist", [])
        blacklist_status = f"🚫 {len(hospitals_blacklist)} ospedali esclusi" if hospitals_blacklist else "🚫 nessun ospedale escluso"
        
        # Otteniamo il codice della tessera sanitaria se disponibile
        team_card_code = ""
        if "patient_info" in prescription and "teamCard" in prescription["patient_info"]:
            team_card_code = prescription["patient_info"]["teamCard"].get("code", "")
        
        # Mostriamo i dati di contatto se presenti
        contact_info = ""
        if "phone" in prescription and "email" in prescription:
            contact_info = f"   📞 Telefono: {prescription['phone']}\n"
            contact_info += f"   📧 Email: {prescription['email']}\n"
        
        # Aggiungiamo informazioni sull'utente se l'admin sta visualizzando
        user_info = ""
        if is_admin and "telegram_chat_id" in prescription:
            user_info = f" (User ID: {prescription['telegram_chat_id']})"
        
        message += f"{idx+1}. <b>{desc}</b>{user_info}\n"
        message += f"   Stato: {booking_status}\n"
        message += f"   Codice Fiscale: <code>{fiscal_code}</code>\n"
        message += f"   NRE: <code>{nre}</code>\n"
        
        # Aggiungiamo il codice della tessera sanitaria se disponibile
        if team_card_code:
            message += f"   Tessera Sanitaria: <code>{team_card_code}</code>\n"
            
        message += contact_info
        
        # Mostra informazioni sulla blacklist
        message += f"   {blacklist_status}\n"
        
        # Mostra altre informazioni solo se non è prenotata
        if not has_booking:
            message += f"   Notifiche: {notification_status} | {date_filter}\n"
            message += f"   Prenotazione automatica: {auto_book_status}\n"
        
        # Se ha prenotazioni, mostriamole
        if has_booking:
            for booking in prescription.get("bookings", []):
                try:
                    date_obj = datetime.strptime(booking["date"], "%Y-%m-%dT%H:%M:%SZ")
                    formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = booking["date"]
                
                message += f"   🏥 Prenotato per: {formatted_date} presso {booking['hospital']}\n"
                message += f"   🆔 ID Prenotazione: {booking['booking_id']}\n"
        
        message += "\n"
    
    await update.message.reply_text(message, parse_mode="HTML")
    
async def check_availability(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica immediatamente la disponibilità delle prescrizioni."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Notifichiamo all'utente che stiamo iniziando la verifica
    await update.message.reply_text("🔍 Sto verificando le disponibilità... Potrebbe richiedere alcuni minuti.")
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    
    if not is_admin:
        # Gli utenti normali verificano solo le proprie prescrizioni
        prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not prescriptions:
        await update.message.reply_text(
            "Non ci sono prescrizioni da verificare." if is_admin else "Non hai prescrizioni da verificare."
        )
        return
    
    # Carichiamo i dati precedenti
    previous_data = load_previous_data()
    
    # Processiamo ogni prescrizione
    num_processed = 0
    for prescription in prescriptions:
        # Forziamo l'aggiornamento per inviare anche se non ci sono cambiamenti
        old_config = prescription.get("config", {}).copy()
        
        # Modifichiamo temporaneamente la configurazione per forzare la notifica
        temp_config = old_config.copy()
        temp_config["min_changes_to_notify"] = 0
        prescription["config"] = temp_config
        
        # Processiamo la prescrizione
        success, _ = process_prescription(prescription, previous_data, user_id)
        
        # Ripristiniamo la configurazione originale
        prescription["config"] = old_config
        
        if success:
            num_processed += 1
        
        # Piccolo ritardo tra le richieste
        await asyncio.sleep(1)
    
    # Salviamo i dati aggiornati
    save_previous_data(previous_data)
    
    # Notifichiamo il completamento
    await update.message.reply_text(
        f"✅ Verifica completata! {num_processed}/{len(prescriptions)} prescrizioni processate.\n\n"
        "Se sono state trovate disponibilità, riceverai dei messaggi separati con i dettagli."
    )

# =============================================================================
# GESTORI NOTIFICHE
# =============================================================================

async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abilita o disabilita le notifiche per una prescrizione."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END
    
    # Creiamo i pulsanti per le prescrizioni
    keyboard = []
    
    for idx, prescription in enumerate(user_prescriptions):
        desc = prescription.get("description", "Prescrizione")
        fiscal_code = prescription["fiscal_code"]
        nre = prescription["nre"]
        
        # Controlliamo lo stato attuale delle notifiche
        notifications_enabled = prescription.get("notifications_enabled", True)
        status = "🔔 ON" if notifications_enabled else "🔕 OFF"
        
        # Creiamo un pulsante con identificativo della prescrizione
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. {desc[:25]}... ({status})",
                callback_data=f"toggle_{idx}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_toggle")])
    
    # Salviamo le prescrizioni nei dati dell'utente
    user_data[user_id] = {
        "action": "toggle_notifications",
        "prescriptions": user_prescriptions
    }
    
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
    callback_data = query.data
    
    if callback_data == "cancel_toggle":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Estraiamo l'indice della prescrizione
    idx = int(callback_data.split("_")[1])
    user_prescriptions = user_data[user_id]["prescriptions"]
    
    # Controlliamo che l'indice sia valido
    if idx < 0 or idx >= len(user_prescriptions):
        await query.edit_message_text("⚠️ Prescrizione non valida.")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo la prescrizione
    prescription_to_toggle = user_prescriptions[idx]
    
    # Carichiamo tutte le prescrizioni
    all_prescriptions = load_input_data()
    
    # Cerchiamo la prescrizione nel dataset completo
    toggled = False
    for prescription in all_prescriptions:
        if (prescription["fiscal_code"] == prescription_to_toggle["fiscal_code"] and 
            prescription["nre"] == prescription_to_toggle["nre"]):
            
            # Otteniamo lo stato attuale e lo invertiamo
            current_state = prescription.get("notifications_enabled", True)
            prescription["notifications_enabled"] = not current_state
            
            toggled = True
            new_state = prescription["notifications_enabled"]
            break
    
    if toggled:
        # Salviamo le prescrizioni aggiornate
        save_input_data(all_prescriptions)
        
        # Stato da visualizzare nel messaggio
        status_text = "attivate ✅" if new_state else "disattivate ❌"
        
        # Aggiorniamo il messaggio
        await query.edit_message_text(
            f"✅ Notifiche {status_text} per:\n\n"
            f"Descrizione: {prescription_to_toggle.get('description', 'Non disponibile')}\n"
            f"Codice Fiscale: {prescription_to_toggle['fiscal_code']}\n"
            f"NRE: {prescription_to_toggle['nre']}"
        )
    else:
        await query.edit_message_text("⚠️ Impossibile modificare lo stato delle notifiche.")
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END


# =============================================================================
# GESTORI PRENOTAZIONI
# =============================================================================

async def book_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la prenotazione di una prescrizione."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da prenotare.")
        return ConversationHandler.END
    
    # Costruiamo il corpo del messaggio con le informazioni dettagliate
    message = "🏥 <b>Prenotazione</b>\n\nSeleziona la prescrizione da prenotare:\n\n"
    
    for idx, prescription in enumerate(user_prescriptions):
        desc = prescription.get("description", "Prescrizione")
        fiscal_code = prescription["fiscal_code"]
        nre = prescription["nre"]
        
        message += f"{idx+1}. <b>{desc}</b>\n"
        message += f"   CF: <code>{fiscal_code}</code> • NRE: <code>{nre}</code>\n\n"
    
    # Creiamo pulsanti più semplici e compatti
    keyboard = []
    
    for idx, _ in enumerate(user_prescriptions):
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}",  # Solo il numero
                callback_data=f"book_{idx}"
            )
        ])
    
    # Aggiungiamo un pulsante per annullare
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_booking")])
    
    # Salviamo le prescrizioni nei dati dell'utente
    user_data[user_id] = {
        "action": "book_prescription",
        "prescriptions": user_prescriptions
    }
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return WAITING_FOR_BOOKING_CHOICE
    
async def handle_booking_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    try:
        idx = int(query.data.split("_")[1])
    except Exception as e:
        await query.edit_message_text("⚠️ Errore nella selezione della prescrizione.")
        return ConversationHandler.END

    user_prescriptions = user_data.get(user_id, {}).get("prescriptions", [])
    if idx < 0 or idx >= len(user_prescriptions):
        await query.edit_message_text("⚠️ Prescrizione non valida.")
        user_data.pop(user_id, None)
        return ConversationHandler.END

    prescription = user_prescriptions[idx]
    user_data[user_id]["selected_prescription"] = prescription

    # Se la prescrizione contiene già i dati di contatto, li usiamo
    if prescription.get("phone") and prescription.get("email"):
        user_data[user_id]["phone"] = prescription["phone"]
        user_data[user_id]["email"] = prescription["email"]
    else:
        await query.edit_message_text(
            f"Hai selezionato: {prescription.get('description', 'N/D')}\n\n"
            "Inserisci il tuo numero di telefono:"
        )
        return WAITING_FOR_PHONE

    # Invia subito un messaggio di attesa
    waiting_message = await query.edit_message_text("🔍 Sto cercando le disponibilità...")

    # Avvia il booking workflow per ottenere le disponibilità (slot_choice = -1 indica "mostra lista")
    result = booking_workflow(
        fiscal_code=prescription["fiscal_code"],
        nre=prescription["nre"],
        phone_number=user_data[user_id]["phone"],
        email=user_data[user_id]["email"],
        patient_id=None,
        process_id=None,
        slot_choice=-1  # Indica: "ritorna la lista degli slot"
    )
    
    if result.get("success") and result.get("action") == "list_slots":
        user_data[user_id]["booking_details"] = result
        slots = result.get("slots", [])
        if not slots:
            await waiting_message.edit_text("⚠️ Nessuna disponibilità trovata per questa prescrizione.")
            return ConversationHandler.END

        # Costruiamo un messaggio dettagliato con le informazioni complete
        message_text = f"📋 <b>Disponibilità per {result.get('service', 'Prestazione')}</b>\n\n"
        message_text += "Seleziona un numero per prenotare lo slot corrispondente:\n\n"
        
        # Aggiungiamo le disponibilità al messaggio
        for i, slot in enumerate(slots):
            try:
                date_obj = datetime.strptime(slot["date"], "%Y-%m-%dT%H:%M:%SZ")
                formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
            except Exception:
                formatted_date = slot["date"]
                
            message_text += f"{i+1}. <b>{formatted_date}</b>\n"
            message_text += f"   🏥 {slot['hospital']}\n"
            message_text += f"   📍 {slot['address']}\n"
            message_text += f"   💰 {slot['price']}€\n\n"
        
        # Costruiamo i pulsanti compatti (solo numeri)
        keyboard = []
        current_row = []
        
        for i in range(len(slots)):
            current_row.append(InlineKeyboardButton(
                f"{i+1}",  # Solo il numero
                callback_data=f"slot_{i}"
            ))
            
            # 5 pulsanti per riga
            if len(current_row) == 5:
                keyboard.append(current_row)
                current_row = []
        
        # Aggiungiamo l'ultima riga se c'è
        if current_row:
            keyboard.append(current_row)
        
        # Pulsante per annullare
        keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_slot")])
        
        await waiting_message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return WAITING_FOR_SLOT_CHOICE
    else:
        await waiting_message.edit_text("⚠️ Errore nella ricerca delle disponibilità. Riprova.")
        return ConversationHandler.END
       
async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input del numero di telefono."""
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    
    # Validazione base del numero di telefono (almeno 8 cifre)
    if not re.match("^[0-9+]{8,15}$", phone):
        await update.message.reply_text(
            "⚠️ Il numero di telefono inserito non sembra valido. Deve contenere almeno 8 cifre.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_PHONE
    
    # Salviamo il numero di telefono
    user_data[user_id]["phone"] = phone
    
    # Chiediamo l'email
    await update.message.reply_text(
        f"Numero di telefono: {phone}\n\n"
        f"Ora inserisci la tua email:"
    )
    
    return WAITING_FOR_EMAIL

async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input dell'email."""
    user_id = update.effective_user.id
    email = update.message.text.strip()
    
    # Validazione base dell'email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text(
            "⚠️ L'email inserita non sembra valida.\n\n"
            "Per favore, riprova:"
        )
        return WAITING_FOR_EMAIL
    
    # Salviamo l'email
    user_data[user_id]["email"] = email
    
    # Otteniamo la prescrizione
    prescription = user_data[user_id]["selected_prescription"]
    fiscal_code = prescription["fiscal_code"]
    nre = prescription["nre"]
    
    # Inviamo un messaggio di attesa
    loading_message = await update.message.reply_text(
        "🔍 Sto cercando le disponibilità... Attendi un momento."
    )
    
    # Avviamo il processo di ricerca delle disponibilità
    result = booking_workflow(
        fiscal_code=fiscal_code,
        nre=nre,
        phone_number=user_data[user_id]["phone"],
        email=email,
        slot_choice=-1  # Chiediamo la lista delle disponibilità
    )
    
    if not result["success"]:
        await loading_message.delete()
        await update.message.reply_text(
            f"⚠️ Errore nella ricerca delle disponibilità: {result.get('message', 'Errore sconosciuto')}"
        )
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Se abbiamo le disponibilità, le mostriamo all'utente
    if result["action"] == "list_slots":
        user_data[user_id]["booking_details"] = result
        
        # Creiamo una lista delle disponibilità
        slots = result["slots"]
        service_name = result["service"]
        
        if not slots:
            await loading_message.delete()
            await update.message.reply_text(
                "⚠️ Non ci sono disponibilità per questa prescrizione."
            )
            # Puliamo i dati dell'utente
            user_data.pop(user_id, None)
            return ConversationHandler.END
        
        # Costruiamo un messaggio dettagliato con le informazioni complete
        message_text = f"📋 <b>Disponibilità per {service_name}</b>\n\n"
        message_text += "Seleziona un numero per prenotare lo slot corrispondente:\n\n"
        
        # Aggiungiamo le disponibilità al messaggio
        for i, slot in enumerate(slots):
            try:
                date_obj = datetime.strptime(slot["date"], "%Y-%m-%dT%H:%M:%SZ")
                formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
            except Exception:
                formatted_date = slot["date"]
                
            message_text += f"{i+1}. <b>{formatted_date}</b>\n"
            message_text += f"   🏥 {slot['hospital']}\n"
            message_text += f"   📍 {slot['address']}\n"
            message_text += f"   💰 {slot['price']}€\n\n"
        
        # Costruiamo i pulsanti compatti (solo numeri)
        keyboard = []
        current_row = []
        
        for i in range(len(slots)):
            current_row.append(InlineKeyboardButton(
                f"{i+1}",  # Solo il numero
                callback_data=f"slot_{i}"
            ))
            
            # 5 pulsanti per riga
            if len(current_row) == 5:
                keyboard.append(current_row)
                current_row = []
        
        # Aggiungiamo l'ultima riga se c'è
        if current_row:
            keyboard.append(current_row)
        
        # Pulsante per annullare
        keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_slot")])
        
        # Eliminiamo il messaggio di caricamento
        await loading_message.delete()
        
        # Mostriamo le disponibilità
        await update.message.reply_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        return WAITING_FOR_SLOT_CHOICE
    
    # Se c'è stato un errore
    await loading_message.delete()
    await update.message.reply_text(
        f"⚠️ Errore imprevisto nella ricerca delle disponibilità."
    )
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    return ConversationHandler.END
    
async def handle_slot_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della disponibilità."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel_slot":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Estraiamo l'indice dello slot
    slot_idx = int(callback_data.split("_")[1])
    
    # Otteniamo i dettagli dello slot
    booking_details = user_data[user_id]["booking_details"]
    slots = booking_details["slots"]
    
    # Controlliamo che l'indice sia valido
    if slot_idx < 0 or slot_idx >= len(slots):
        await query.edit_message_text("⚠️ Disponibilità non valida.")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo lo slot selezionato
    selected_slot = slots[slot_idx]
    
    # Formattiamo la data
    try:
        date_obj = datetime.strptime(selected_slot["date"], "%Y-%m-%dT%H:%M:%SZ")
        formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
    except:
        formatted_date = selected_slot["date"]
    
    # Chiediamo conferma all'utente
    await query.edit_message_text(
        f"📅 <b>Conferma Prenotazione</b>\n\n"
        f"Stai per prenotare:\n"
        f"<b>Servizio:</b> {booking_details['service']}\n"
        f"<b>Data:</b> {formatted_date}\n"
        f"<b>Ospedale:</b> {selected_slot['hospital']}\n"
        f"<b>Indirizzo:</b> {selected_slot['address']}\n"
        f"<b>Prezzo:</b> {selected_slot['price']}€\n\n"
        f"Confermi la prenotazione?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sì, prenota", callback_data=f"confirm_slot_{slot_idx}"),
                InlineKeyboardButton("❌ No, annulla", callback_data="cancel_slot")
            ]
        ]),
        parse_mode="HTML"
    )
    
    return WAITING_FOR_BOOKING_CONFIRMATION

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma della prenotazione."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data.startswith("cancel_"):
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Estraiamo l'indice dello slot
    slot_idx = int(callback_data.split("_")[2])
    
    # Otteniamo i dettagli necessari
    booking_details = user_data[user_id]["booking_details"]
    prescription = user_data[user_id]["selected_prescription"]
    phone = user_data[user_id]["phone"]
    email = user_data[user_id]["email"]
    
    # Inviamo un messaggio di attesa
    await query.edit_message_text("🔄 Sto effettuando la prenotazione... Attendi un momento.")
    
    # Avviamo il processo di prenotazione
    result = booking_workflow(
        fiscal_code=prescription["fiscal_code"],
        nre=prescription["nre"],
        phone_number=phone,
        email=email,
        patient_id=booking_details.get("patient_id"),
        process_id=booking_details.get("process_id"),
        slot_choice=slot_idx
    )
    
    if not result["success"]:
        await query.edit_message_text(
            f"❌ Errore nella prenotazione: {result.get('message', 'Errore sconosciuto')}"
        )
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Se la prenotazione è andata a buon fine
    if result["action"] == "booked":
        # Formattiamo la data
        try:
            date_obj = datetime.strptime(result["appointment_date"], "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
        except:
            formatted_date = result["appointment_date"]
        
        # Inviamo il messaggio di conferma
        await query.edit_message_text(
            f"✅ <b>Prenotazione effettuata con successo!</b>\n\n"
            f"<b>Servizio:</b> {result['service']}\n"
            f"<b>Data:</b> {formatted_date}\n"
            f"<b>Ospedale:</b> {result['hospital']}\n"
            f"<b>Indirizzo:</b> {result['address']}\n"
            f"<b>ID Prenotazione:</b> {result['booking_id']}\n\n"
            f"Ti invio il documento di prenotazione.",
            parse_mode="HTML"
        )
        
        # Inviamo il PDF
        pdf_path = result["pdf_path"]
        pdf_content = result["pdf_content"]
        
        # Inviamo il documento come file
        await context.bot.send_document(
            chat_id=user_id,
            document=BytesIO(pdf_content),
            filename=f"prenotazione_{result['booking_id']}.pdf",
            caption=f"Documento di prenotazione per {result['service']} del {formatted_date}"
        )
        
        # Salvare la prenotazione nei dati della prescrizione
        prescriptions = load_input_data()
        for p in prescriptions:
            if p["fiscal_code"] == prescription["fiscal_code"] and p["nre"] == prescription["nre"]:
                if "bookings" not in p:
                    p["bookings"] = []
                p["bookings"].append({
                    "booking_id": result["booking_id"],
                    "date": result["appointment_date"],
                    "hospital": result["hospital"],
                    "address": result["address"],
                    "service": result["service"]
                })
                break
        save_input_data(prescriptions)
    else:
        await query.edit_message_text(
            f"⚠️ Errore imprevisto nella prenotazione."
        )
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    return ConversationHandler.END

async def list_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra le prenotazioni attive dell'utente."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    # Raccogliamo le prenotazioni da tutte le prescrizioni
    all_bookings = []
    
    for prescription in user_prescriptions:
        # Se la prescrizione ha prenotazioni salvate
        if "bookings" in prescription and prescription["bookings"]:
            for booking in prescription["bookings"]:
                booking_info = {
                    "booking_id": booking["booking_id"],
                    "date": booking["date"],
                    "hospital": booking["hospital"],
                    "address": booking.get("address", "Indirizzo non disponibile"),
                    "service": booking["service"],
                    "prescription": prescription
                }
                all_bookings.append(booking_info)
    
    # Se non ci sono prenotazioni, verifichiamo con l'API
    if not all_bookings:
        for prescription in user_prescriptions:
            fiscal_code = prescription["fiscal_code"]
            
            # Inviamo un messaggio di attesa
            loading_message = await update.message.reply_text(
                f"🔍 Sto cercando le prenotazioni per {fiscal_code}... Attendi un momento."
            )
            
            # Otteniamo le prenotazioni dall'API
            result = get_user_bookings(fiscal_code)
            
            # Eliminiamo il messaggio di caricamento
            await loading_message.delete()
            
            if result["success"] and result["bookings"]:
                for booking in result["bookings"]:
                    booking_info = {
                        "booking_id": booking["id"],
                        "date": booking.get("startTime", "Data non disponibile"),
                        "hospital": booking.get("hospital", {}).get("name", "Ospedale non disponibile"),
                        "address": booking.get("site", {}).get("address", "Indirizzo non disponibile"),
                        "service": booking.get("services", [{}])[0].get("description", "Servizio non disponibile"),
                        "prescription": prescription,
                        "from_api": True
                    }
                    all_bookings.append(booking_info)
    
    # Se non ci sono prenotazioni
    if not all_bookings:
        await update.message.reply_text("📝 Non ci sono prenotazioni attive.")
        return
    
    # Ordiniamo le prenotazioni per data
    all_bookings.sort(key=lambda x: x["date"])
    
    # Creiamo il messaggio con le prenotazioni
    message = "📝 <b>Le tue prenotazioni attive:</b>\n\n"
    
    for idx, booking in enumerate(all_bookings):
        # Formattiamo la data
        try:
            date_obj = datetime.strptime(booking["date"], "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
        except:
            formatted_date = booking["date"]
        
        message += f"{idx+1}. <b>{booking['service']}</b>\n"
        message += f"   📅 Data: {formatted_date}\n"
        message += f"   🏥 Ospedale: {booking['hospital']}\n"
        message += f"   📍 Indirizzo: {booking['address']}\n"
        message += f"   🆔 ID: {booking['booking_id']}\n\n"
    
    # Aggiungiamo un pulsante per disdire una prenotazione
    keyboard = [[InlineKeyboardButton("❌ Disdici una prenotazione", callback_data="cancel_appointment")]]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def start_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia il processo di cancellazione di una prenotazione."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    # Raccogliamo le prenotazioni da tutte le prescrizioni
    all_bookings = []
    
    for prescription in user_prescriptions:
        # Se la prescrizione ha prenotazioni salvate
        if "bookings" in prescription and prescription["bookings"]:
            for booking in prescription["bookings"]:
                booking_info = {
                    "booking_id": booking["booking_id"],
                    "date": booking["date"],
                    "hospital": booking["hospital"],
                    "address": booking.get("address", "Indirizzo non disponibile"),
                    "service": booking["service"],
                    "prescription": prescription
                }
                all_bookings.append(booking_info)
    
    # Se non ci sono prenotazioni, verifichiamo con l'API
    if not all_bookings:
        for prescription in user_prescriptions:
            fiscal_code = prescription["fiscal_code"]
            
            # Inviamo un messaggio di attesa
            await query.edit_message_text(
                f"🔍 Sto cercando le prenotazioni per {fiscal_code}... Attendi un momento."
            )
            
            # Otteniamo le prenotazioni dall'API
            from modules.booking_client import get_user_bookings
            result = get_user_bookings(fiscal_code)
            
            if result["success"] and result["bookings"]:
                for booking in result["bookings"]:
                    booking_info = {
                        "booking_id": booking["id"],
                        "date": booking.get("startTime", "Data non disponibile"),
                        "hospital": booking.get("hospital", {}).get("name", "Ospedale non disponibile"),
                        "address": booking.get("site", {}).get("address", "Indirizzo non disponibile"),
                        "service": booking.get("services", [{}])[0].get("description", "Servizio non disponibile"),
                        "prescription": prescription,
                        "from_api": True
                    }
                    all_bookings.append(booking_info)
    
    # Se non ci sono prenotazioni
    if not all_bookings:
        await query.edit_message_text("📝 Non ci sono prenotazioni attive da disdire.")
        return ConversationHandler.END
    
    # Ordiniamo le prenotazioni per data
    all_bookings.sort(key=lambda x: x["date"])
    
    # Salviamo le prenotazioni nei dati dell'utente
    user_data[user_id] = {
        "action": "cancel_booking",
        "bookings": all_bookings  # Salviamo tutte le prenotazioni
    }
    
    logger.info(f"Trovate {len(all_bookings)} prenotazioni da mostrare per la cancellazione")
    
    # Creiamo i pulsanti per le prenotazioni
    keyboard = []
    
    for idx, booking in enumerate(all_bookings):
        # Formattiamo la data
        try:
            date_obj = datetime.strptime(booking["date"], "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
        except Exception as e:
            logger.error(f"Errore nella formattazione della data: {e}")
            formatted_date = booking["date"]
        
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. {booking['service']} - {formatted_date}",
                callback_data=f"cancel_book_{idx}"
            )
        ])
    
    # Aggiungiamo un pulsante per annullare
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_cancel_book")])
    
    await query.edit_message_text(
        "Seleziona la prenotazione da disdire:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_FOR_BOOKING_TO_CANCEL

async def handle_booking_to_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prenotazione da disdire."""
    logger.info("Entrato in handle_booking_to_cancel")
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Log per debug
    logger.info(f"Callback ricevuta: {callback_data}")
    
    if callback_data == "cancel_cancel_book":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    try:
        # Estraiamo l'indice della prenotazione
        idx = int(callback_data.split("_")[2])
        logger.info(f"Indice estratto: {idx}")
        
        if user_id not in user_data or "bookings" not in user_data[user_id]:
            await query.edit_message_text("⚠️ Dati di prenotazione non trovati. Riprova.")
            return ConversationHandler.END
            
        user_bookings = user_data[user_id]["bookings"]
        
        # Controlliamo che l'indice sia valido
        if idx < 0 or idx >= len(user_bookings):
            await query.edit_message_text("⚠️ Prenotazione non valida.")
            user_data.pop(user_id, None)
            return ConversationHandler.END
        
        # Otteniamo la prenotazione
        booking_to_cancel = user_bookings[idx]
        
        # Formattiamo la data
        try:
            date_obj = datetime.strptime(booking_to_cancel["date"], "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
        except:
            formatted_date = booking_to_cancel["date"]
        
        # Chiediamo conferma all'utente
        await query.edit_message_text(
            f"⚠️ <b>Sei sicuro di voler disdire questa prenotazione?</b>\n\n"
            f"<b>Servizio:</b> {booking_to_cancel['service']}\n"
            f"<b>Data:</b> {formatted_date}\n"
            f"<b>Ospedale:</b> {booking_to_cancel['hospital']}\n"
            f"<b>ID Prenotazione:</b> {booking_to_cancel['booking_id']}\n\n"
            f"Questa operazione è <b>irreversibile</b>!",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Sì, disdici", callback_data=f"confirm_cancel_{idx}"),
                    InlineKeyboardButton("❌ No, annulla", callback_data="cancel_cancel_book")
                ]
            ]),
            parse_mode="HTML"
        )
        
        return WAITING_FOR_BOOKING_TO_CANCEL
    
    except Exception as e:
        logger.error(f"Errore in handle_booking_to_cancel: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        await query.edit_message_text("⚠️ Si è verificato un errore nel processare la richiesta.")
        if user_id in user_data:
            user_data.pop(user_id, None)
        return ConversationHandler.END

async def confirm_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma della disdetta della prenotazione."""
    logger.info("Entrato in confirm_cancel_booking")
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Log per debug
    logger.info(f"Callback conferma cancellazione: {callback_data}")
    
    if callback_data.startswith("cancel_cancel"):
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    try:
        # Estraiamo l'indice della prenotazione
        idx = int(callback_data.split("_")[2])
        
        if user_id not in user_data or "bookings" not in user_data[user_id]:
            await query.edit_message_text("⚠️ Dati di prenotazione non trovati. Riprova.")
            return ConversationHandler.END
            
        user_bookings = user_data[user_id]["bookings"]
        
        # Otteniamo la prenotazione
        booking_to_cancel = user_bookings[idx]
        booking_id = booking_to_cancel["booking_id"]
        
        # Inviamo un messaggio di attesa
        await query.edit_message_text("🔄 Sto disdendo la prenotazione... Attendi un momento.")
        
        # Import qui per evitare import circolari
        from modules.booking_client import cancel_booking
        
        try:
            # Disdiciamo la prenotazione
            result = cancel_booking(booking_id)
            
            # Rimuoviamo la prenotazione dalle prescrizioni
            prescriptions = load_input_data()
            for p in prescriptions:
                if "bookings" in p:
                    p["bookings"] = [b for b in p["bookings"] if b["booking_id"] != booking_id]
            save_input_data(prescriptions)
            
            # Inviamo il messaggio di conferma
            await query.edit_message_text(
                f"✅ <b>Prenotazione disdetta con successo!</b>\n\n"
                f"La prenotazione per {booking_to_cancel['service']} è stata disdetta.",
                parse_mode="HTML"
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Errore nella disdetta della prenotazione: {str(e)}"
            )
            logger.error(f"Errore nella cancellazione della prenotazione: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"Errore in confirm_cancel_booking: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        await query.edit_message_text("⚠️ Si è verificato un errore nel processare la richiesta.")
    
    # Puliamo i dati dell'utente
    if user_id in user_data:
        user_data.pop(user_id, None)
    
    return ConversationHandler.END

async def autobook_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la prenotazione automatica di una prescrizione (primo slot disponibile)."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da prenotare automaticamente.")
        return ConversationHandler.END
    
    # Creiamo i pulsanti per le prescrizioni
    keyboard = []
    
    for idx, prescription in enumerate(user_prescriptions):
        desc = prescription.get("description", "Prescrizione")
        fiscal_code = prescription["fiscal_code"]
        nre = prescription["nre"]
        
        # Creiamo un pulsante con identificativo della prescrizione
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. {desc[:30]}... ({fiscal_code[-4:]})",
                callback_data=f"autobook_{idx}"
            )
        ])
    
    # Aggiungiamo un pulsante per annullare
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_autobook")])
    
    # Salviamo le prescrizioni nei dati dell'utente
    user_data[user_id] = {
        "action": "autobook_prescription",
        "prescriptions": user_prescriptions
    }
    
    await update.message.reply_text(
        "🤖 <b>Prenotazione Automatica</b>\n\n"
        "Questa funzione prenota automaticamente il primo slot disponibile "
        "per la prescrizione selezionata, senza passaggi intermedi.\n\n"
        "Seleziona la prescrizione da prenotare automaticamente:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return WAITING_FOR_BOOKING_CHOICE

async def handle_autobook_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione della prescrizione da prenotare automaticamente."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel_autobook":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        if user_id in user_data:
            user_data.pop(user_id, None)
        return ConversationHandler.END
    
    try:
        # Estraiamo l'indice della prescrizione
        idx = int(callback_data.split("_")[1])
        user_prescriptions = user_data.get(user_id, {}).get("prescriptions", [])
        
        # Controlliamo che l'indice sia valido
        if idx < 0 or idx >= len(user_prescriptions):
            await query.edit_message_text("⚠️ Prescrizione non valida.")
            if user_id in user_data:
                user_data.pop(user_id, None)
            return ConversationHandler.END
        
        # Otteniamo la prescrizione
        prescription_to_book = user_prescriptions[idx]
        user_data[user_id]["selected_prescription"] = prescription_to_book
        
        # Utilizziamo la funzione di utilità per ottenere una descrizione sicura
        description = get_safe_description(prescription_to_book)
        
        # Chiediamo all'utente il numero di telefono
        await query.edit_message_text(
            f"Hai selezionato: {description}\n\n"
            f"Per completare la prenotazione automatica, ho bisogno di alcune informazioni di contatto.\n\n"
            f"Inserisci il tuo numero di telefono:"
        )
        
        return WAITING_FOR_PHONE
    except Exception as e:
        logger.error(f"Errore in handle_autobook_choice: {str(e)}")
        await query.edit_message_text("⚠️ Si è verificato un errore nella selezione della prescrizione.")
        if user_id in user_data:
            user_data.pop(user_id, None)
        return ConversationHandler.END
        
# =============================================================================
# GESTORI FILTRO DATE
# =============================================================================

async def set_date_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Imposta un filtro per le date delle disponibilità."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END
    
    # Creiamo i pulsanti per le prescrizioni
    keyboard = []
    
    for idx, prescription in enumerate(user_prescriptions):
        desc = prescription.get("description", "Prescrizione")
        fiscal_code = prescription["fiscal_code"]
        nre = prescription["nre"]
        
        # Otteniamo il filtro date attuale
        months_limit = prescription.get("config", {}).get("months_limit")
        filter_status = f"⏱ {months_limit} mesi" if months_limit else "⏱ nessun filtro"
        
        # Creiamo un pulsante con identificativo della prescrizione
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. {desc[:25]}... ({filter_status})",
                callback_data=f"date_filter_{idx}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_date_filter")])
    
    # Salviamo le prescrizioni nei dati dell'utente
    user_data[user_id] = {
        "action": "set_date_filter",
        "prescriptions": user_prescriptions
    }
    
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
    callback_data = query.data
    
    if callback_data == "cancel_date_filter":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Estraiamo l'indice della prescrizione
    idx = int(callback_data.split("_")[2])
    user_prescriptions = user_data[user_id]["prescriptions"]
    
    # Controlliamo che l'indice sia valido
    if idx < 0 or idx >= len(user_prescriptions):
        await query.edit_message_text("⚠️ Prescrizione non valida.")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo la prescrizione
    prescription = user_prescriptions[idx]
    user_data[user_id]["selected_prescription"] = prescription
    
    # Otteniamo il filtro date attuale
    months_limit = prescription.get("config", {}).get("months_limit")
    current_filter = f"{months_limit} mesi" if months_limit else "nessun filtro"
    
    # Creiamo pulsanti per scelte rapide + opzione personalizzata
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
        f"Seleziona il periodo massimo entro cui ricevere notifiche di disponibilità:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return WAITING_FOR_MONTHS_LIMIT

async def handle_months_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la selezione del limite di mesi per il filtro date."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel_months":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Se l'utente vuole inserire un valore personalizzato
    if callback_data == "months_custom":
        await query.edit_message_text(
            "Inserisci il numero di mesi entro cui vuoi ricevere notifiche (1-24):"
        )
        return WAITING_FOR_MONTHS_LIMIT
    
    # Altrimenti processiamo la scelta rapida
    months = int(callback_data.split("_")[1])
    
    # Salva la scelta nei dati dell'utente
    user_data[user_id]["months_limit"] = months if months > 0 else None
    
    # Prepara la conferma
    prescription = user_data[user_id]["selected_prescription"]
    filter_text = f"{months} mesi" if months > 0 else "nessun limite"
    
    await query.edit_message_text(
        f"Stai per impostare un filtro di {filter_text} per:\n\n"
        f"Prescrizione: {prescription.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {prescription['fiscal_code']}\n"
        f"NRE: {prescription['nre']}\n\n"
        f"Confermi?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sì, imposta", callback_data="confirm_date_filter"),
                InlineKeyboardButton("❌ No, annulla", callback_data="cancel_date_filter_confirm")
            ]
        ])
    )
    
    return CONFIRM_DATE_FILTER

async def toggle_auto_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abilita o disabilita la prenotazione automatica per una prescrizione."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    # Carichiamo le prescrizioni
    prescriptions = load_input_data()
    
    # Filtriamo solo le prescrizioni dell'utente o tutte se è admin
    is_admin = user_id == int(authorized_users[0]) if authorized_users else False
    user_prescriptions = []
    
    if is_admin:
        # L'admin vede tutte le prescrizioni
        user_prescriptions = prescriptions
    else:
        # Gli utenti normali vedono solo le proprie
        user_prescriptions = [p for p in prescriptions if p.get("telegram_chat_id") == user_id]
    
    if not user_prescriptions:
        await update.message.reply_text("⚠️ Non hai prescrizioni da gestire.")
        return ConversationHandler.END
    
    # Verifichiamo che le prescrizioni abbiano i dati necessari
    valid_prescriptions = []
    for p in user_prescriptions:
        if "phone" in p and "email" in p:
            valid_prescriptions.append(p)
    
    if not valid_prescriptions:
        await update.message.reply_text(
            "⚠️ Non hai prescrizioni con dati di contatto completi. "
            "Rimuovile e aggiungile nuovamente per inserire telefono ed email."
        )
        return ConversationHandler.END
    
    # Creiamo i pulsanti per le prescrizioni
    keyboard = []
    
    for idx, prescription in enumerate(valid_prescriptions):
        desc = prescription.get("description", "Prescrizione")
        fiscal_code = prescription["fiscal_code"]
        nre = prescription["nre"]
        
        # Controlliamo lo stato attuale della prenotazione automatica
        auto_book_enabled = prescription.get("auto_book_enabled", False)
        status = "🤖 ON" if auto_book_enabled else "🤖 OFF"
        
        # Creiamo un pulsante con identificativo della prescrizione
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. {desc[:25]}... ({status})",
                callback_data=f"auto_book_{idx}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="cancel_auto_book")])
    
    # Salviamo le prescrizioni nei dati dell'utente
    user_data[user_id] = {
        "action": "toggle_auto_booking",
        "prescriptions": valid_prescriptions
    }
    
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
    callback_data = query.data
    
    if callback_data == "cancel_auto_book":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Estraiamo l'indice della prescrizione
    idx = int(callback_data.split("_")[2])
    user_prescriptions = user_data[user_id]["prescriptions"]
    
    # Controlliamo che l'indice sia valido
    if idx < 0 or idx >= len(user_prescriptions):
        await query.edit_message_text("⚠️ Prescrizione non valida.")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo la prescrizione
    prescription_to_toggle = user_prescriptions[idx]
    
    # Carichiamo tutte le prescrizioni
    all_prescriptions = load_input_data()
    
    # Cerchiamo la prescrizione nel dataset completo
    toggled = False
    for prescription in all_prescriptions:
        if (prescription["fiscal_code"] == prescription_to_toggle["fiscal_code"] and 
            prescription["nre"] == prescription_to_toggle["nre"]):
            
            # Otteniamo lo stato attuale e lo invertiamo
            current_state = prescription.get("auto_book_enabled", False)
            prescription["auto_book_enabled"] = not current_state
            
            toggled = True
            new_state = prescription["auto_book_enabled"]
            break
    
    if toggled:
        # Salviamo le prescrizioni aggiornate
        save_input_data(all_prescriptions)
        
        # Stato da visualizzare nel messaggio
        status_text = "attivata ✅" if new_state else "disattivata ❌"
        
        # Testo aggiuntivo per spiegare la funzionalità
        info_text = (
            "Il bot controllerà automaticamente le disponibilità ogni 5 minuti e "
            f"prenoterà il primo slot disponibile negli ospedali non blacklistati senza richiedere conferma.\n\n"
            f"I documenti PDF delle prenotazioni saranno salvati nella cartella '{PDF_FOLDER}'."
        )
        
        # Aggiorniamo il messaggio
        await query.edit_message_text(
            f"✅ Prenotazione automatica {status_text} per:\n\n"
            f"Descrizione: {prescription_to_toggle.get('description', 'Non disponibile')}\n"
            f"Codice Fiscale: {prescription_to_toggle['fiscal_code']}\n"
            f"NRE: {prescription_to_toggle['nre']}\n\n"
            f"{info_text}"
        )
    else:
        await query.edit_message_text("⚠️ Impossibile modificare lo stato della prenotazione automatica.")
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END

async def handle_custom_months_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'input personalizzato per il limite di mesi."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Validazione: deve essere un numero tra 1 e 24
    try:
        months = int(text)
        if months < 1 or months > 24:
            await update.message.reply_text(
                "⚠️ Il valore deve essere compreso tra 1 e 24 mesi. Riprova:"
            )
            return WAITING_FOR_MONTHS_LIMIT
    except ValueError:
        await update.message.reply_text(
            "⚠️ Devi inserire un numero intero. Riprova:"
        )
        return WAITING_FOR_MONTHS_LIMIT
    
    # Salva la scelta nei dati dell'utente
    user_data[user_id]["months_limit"] = months
    
    # Prepara la conferma
    prescription = user_data[user_id]["selected_prescription"]
    
    await update.message.reply_text(
        f"Stai per impostare un filtro di {months} mesi per:\n\n"
        f"Prescrizione: {prescription.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {prescription['fiscal_code']}\n"
        f"NRE: {prescription['nre']}\n\n"
        f"Confermi?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Sì, imposta", callback_data="confirm_date_filter"),
                InlineKeyboardButton("❌ No, annulla", callback_data="cancel_date_filter_confirm")
            ]
        ])
    )
    
    return CONFIRM_DATE_FILTER

async def confirm_date_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conferma l'impostazione del filtro date."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel_date_filter_confirm":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Altrimenti procediamo con l'aggiornamento
    prescription = user_data[user_id]["selected_prescription"]
    months_limit = user_data[user_id]["months_limit"]
    
    # Carichiamo tutte le prescrizioni
    all_prescriptions = load_input_data()
    
    # Cerchiamo la prescrizione nel dataset completo
    updated = False
    for p in all_prescriptions:
        if (p["fiscal_code"] == prescription["fiscal_code"] and 
            p["nre"] == prescription["nre"]):
            
            # Assicuriamo che esista la configurazione
            if "config" not in p:
                p["config"] = {}
            
            # Aggiorniamo il filtro date
            p["config"]["months_limit"] = months_limit
            
            updated = True
            break
    
    if updated:
        # Salviamo le prescrizioni aggiornate
        save_input_data(all_prescriptions)
        
        # Testo da visualizzare nel messaggio
        filter_text = f"{months_limit} mesi" if months_limit is not None else "nessun limite"
        
        # Aggiorniamo il messaggio
        await query.edit_message_text(
            f"✅ Filtro date impostato a {filter_text} per:\n\n"
            f"Descrizione: {prescription.get('description', 'Non disponibile')}\n"
            f"Codice Fiscale: {prescription['fiscal_code']}\n"
            f"NRE: {prescription['nre']}\n\n"
            f"Ora riceverai notifiche solo per disponibilità entro il periodo specificato."
        )
    else:
        await query.edit_message_text("⚠️ Impossibile aggiornare il filtro date.")
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END

# =============================================================================
# GESTORI UTENTI
# =============================================================================

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra informazioni sul bot."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    await update.message.reply_text(
        "ℹ️ <b>Informazioni sul Bot</b>\n\n"
        "Questo bot monitora le disponibilità del Servizio Sanitario Nazionale (SSN) per le prescrizioni mediche e ti notifica quando ci sono nuove disponibilità. Inoltre, ora monitora anche i tuoi referti medici e ti avvisa quando sono disponibili.\n\n"
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
        "Il sistema verifica automaticamente ogni 5 minuti se sono disponibili nuovi referti medici per il tuo codice fiscale. Quando un referto diventa disponibile, riceverai immediatamente una notifica. Una volta scaricato il referto, il monitoraggio verrà automaticamente disattivato. "
        "Se nelle tue prescrizioni monitorate è presente il codice della tessera sanitaria, verrà utilizzato automaticamente.\n\n"
        "<b>Prenotazione Automatica:</b>\n"
        "Quando attivi la prenotazione automatica per una prescrizione, il bot prenota automaticamente il primo slot disponibile utilizzando i dati di contatto salvati, senza richiedere ulteriori conferme.\n\n"
        "<b>Blacklist Ospedali:</b>\n"
        "Puoi escludere specifici ospedali dalle notifiche per ogni prescrizione, ricevendo avvisi solo per le strutture che ti interessano.\n\n"
        "<b>Frequenza di controllo:</b> Ogni 5 minuti\n\n"
        "<b>Note:</b>\n"
        "• Il bot notifica solo quando ci sono cambiamenti significativi\n"
        "• Le disponibilità possono variare rapidamente, è consigliabile prenotare il prima possibile\n"
        "• Per problemi o assistenza, contatta l'amministratore",
        parse_mode="HTML"
    )
    
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'invio di un messaggio a tutti gli utenti autorizzati (solo admin)."""
    user_id = update.effective_user.id
    
    # Verifica che l'utente sia l'amministratore (primo utente nella lista)
    if not authorized_users or str(user_id) != authorized_users[0]:
        await update.message.reply_text("🔒 Solo l'amministratore può inviare messaggi broadcast.")
        return ConversationHandler.END
    
    # Tastiera con pulsante Annulla
    cancel_keyboard = ReplyKeyboardMarkup([["❌ Annulla"]], resize_keyboard=True)
    
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
        reply_markup=cancel_keyboard,
        parse_mode="HTML"
    )
    
    # Inizializziamo i dati dell'utente
    user_data[user_id] = {"action": "broadcast_message"}
    
    return WAITING_FOR_BROADCAST_MESSAGE

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il messaggio broadcast da inviare."""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Controlliamo se l'utente vuole annullare
    if message_text == "❌ Annulla" or message_text.lower() == "/cancel":
        return await cancel_operation(update, context)
    
    # Verifica che l'utente sia l'amministratore
    if not authorized_users or str(user_id) != authorized_users[0]:
        await update.message.reply_text("🔒 Solo l'amministratore può inviare messaggi broadcast.")
        if user_id in user_data:
            user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Chiedi conferma prima di inviare
    confirm_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sì, invia a tutti", callback_data="confirm_broadcast"),
            InlineKeyboardButton("❌ No, annulla", callback_data="cancel_broadcast")
        ]
    ])
    
    # Salviamo il messaggio
    user_data[user_id]["broadcast_message"] = message_text
    
    # Mostra anteprima
    await update.message.reply_text(
        "📋 <b>Anteprima del messaggio:</b>\n\n" + message_text + "\n\n"
        f"👥 Questo messaggio verrà inviato a {len(authorized_users)} utenti autorizzati.\n\n"
        "Confermi l'invio?",
        reply_markup=confirm_keyboard,
        parse_mode="HTML"
    )
    
    return WAITING_FOR_BROADCAST_CONFIRMATION

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la conferma dell'invio del messaggio broadcast."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel_broadcast":
        await query.edit_message_text("❌ Operazione annullata.")
        # Puliamo i dati dell'utente
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    # Otteniamo il messaggio
    broadcast_message = user_data[user_id]["broadcast_message"]
    
    # Inviamo un messaggio di attesa
    await query.edit_message_text("📣 Invio del messaggio broadcast in corso...")
    
    # Contatori per il feedback
    success_count = 0
    error_count = 0
    error_details = []
    
    # Inviamo il messaggio a tutti gli utenti autorizzati
    for recipient_id in authorized_users:
        try:
            # Skip dell'admin stesso se non vuole ricevere la copia
            if recipient_id == str(user_id) and user_data[user_id].get("skip_self", False):
                continue
                
            await context.bot.send_message(
                chat_id=int(recipient_id),
                text="📣 <b>Messaggio dall'amministratore:</b>\n\n" + broadcast_message,
                parse_mode="HTML"
            )
            success_count += 1
            
            # Breve pausa per evitare limiti di rate
            await asyncio.sleep(0.1)
        except Exception as e:
            error_count += 1
            error_details.append(f"ID {recipient_id}: {str(e)}")
            logger.error(f"Errore nell'invio del messaggio broadcast a {recipient_id}: {str(e)}")
    
    # Inviamo il feedback all'admin
    result_message = f"✅ Messaggio inviato con successo a {success_count} utenti."
    
    if error_count > 0:
        result_message += f"\n\n❌ Errori nell'invio a {error_count} utenti."
        if error_details:
            result_message += "\n\nDettagli degli errori:"
            for detail in error_details[:5]:  # Limita i dettagli per evitare messaggi troppo lunghi
                result_message += f"\n- {detail}"
            if len(error_details) > 5:
                result_message += f"\n...e altri {len(error_details) - 5} errori."
    
    # Ripristiniamo la tastiera principale
    keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD
    
    await context.bot.send_message(
        chat_id=user_id,
        text=result_message,
        reply_markup=keyboard
    )
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END

async def authorize_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'autorizzazione di nuovi utenti."""
    user_id = update.effective_user.id
    
    # Solo l'amministratore può autorizzare nuovi utenti
    # L'amministratore è il primo utente nella lista degli autorizzati
    if not authorized_users or str(user_id) != authorized_users[0]:
        await update.message.reply_text("🔒 Solo l'amministratore può autorizzare nuovi utenti.")
        return
    
    # Memorizziamo che l'utente sta cercando di autorizzare qualcuno
    user_data[user_id] = {"action": "authorizing_user"}
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Annulla", callback_data="cancel_auth")]
    ])
    
    # Chiediamo l'ID dell'utente da autorizzare
    await update.message.reply_text(
        "Per autorizzare un nuovo utente, invia il suo ID Telegram.\n\n"
        "L'utente può ottenere il proprio ID usando @userinfobot o altri bot simili.",
        reply_markup=keyboard
    )
    return AUTHORIZING


async def handle_cancel_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la pressione del pulsante '❌ Annulla' durante l'autorizzazione."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_data:
        user_data.pop(user_id, None)
    await query.edit_message_text("❌ Operazione annullata.")
    return ConversationHandler.END

async def handle_auth_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'inserimento dell'ID utente da autorizzare."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Se l'utente ha digitato un comando di annullamento, esegui il cancel
    if text.lower() in ["/cancel", "❌ annulla"]:
        return await cancel_operation(update, context)
    
    if not text.isdigit():
        await update.message.reply_text("⚠️ L'ID utente deve essere un numero. Riprova oppure digita /cancel per annullare:")
        return  # Resta nello stesso stato finché non riceve un input valido
    
    new_user_id = text
    if new_user_id in authorized_users:
        await update.message.reply_text(f"⚠️ L'utente {new_user_id} è già autorizzato.")
        user_data.pop(user_id, None)
        return ConversationHandler.END
    
    authorized_users.append(new_user_id)
    save_authorized_users()
    await update.message.reply_text(f"✅ Utente {new_user_id} autorizzato con successo!")
    user_data.pop(user_id, None)
    return ConversationHandler.END

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i messaggi di testo e i comandi dai pulsanti."""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Gestione degli input durante le conversazioni
    if user_id in user_data:
        # Se l'utente sta cercando di autorizzare qualcuno
        if user_data[user_id].get("action") == "authorizing_user":
            return await handle_auth_user_id(update, context)
        
        # Se l'utente sta inserendo un valore personalizzato per il filtro date
        if "selected_prescription" in user_data[user_id] and user_data[user_id].get("action") == "set_date_filter":
            return await handle_custom_months_limit(update, context)
        
        # Se l'utente sta inserendo dati per la prenotazione
        if user_data[user_id].get("action") in ["book_prescription", "autobook_prescription"]:
            if "phone" not in user_data[user_id]:
                return await handle_phone_number(update, context)
            elif "email" not in user_data[user_id]:
                return await handle_email(update, context)
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        # Se non ci sono utenti autorizzati, il primo utente diventa automaticamente amministratore
        if not authorized_users:
            authorized_users.append(str(user_id))
            save_authorized_users()
            logger.info(f"Primo utente {user_id} aggiunto come amministratore")
            
            # Inviamo un messaggio di benvenuto come amministratore
            keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD

            await update.message.reply_text(
                f"👑 Benvenuto, {update.effective_user.first_name}!\n\n"
                "Sei stato impostato come amministratore del bot.\n\n"
                "Questo bot ti aiuterà a monitorare le disponibilità del Servizio Sanitario Nazionale.",
                reply_markup=keyboard
            )
            return
        else:
            await update.message.reply_text(
                "🔒 Non sei autorizzato ad utilizzare questo bot. Contatta l'amministratore per ottenere l'accesso."
            )
            return
    
    # Gestiamo i comandi dai pulsanti
    if text == "➕ Aggiungi Prescrizione":
        return await add_prescription(update, context)
    elif text == "➖ Rimuovi Prescrizione":
        return await remove_prescription(update, context)
    elif text == "📋 Lista Prescrizioni":
        return await list_prescriptions(update, context)
    elif text == "🔄 Verifica Disponibilità":
        return await check_availability(update, context)
    elif text == "🔔 Gestisci Notifiche":
        return await toggle_notifications(update, context)
    elif text == "⏱ Imposta Filtro Date":
        return await set_date_filter(update, context)
    elif text == "🏥 Prenota":
        return await book_prescription(update, context)
    elif text == "🤖 Prenota Automaticamente":
        return await toggle_auto_booking(update, context)
    elif text == "📝 Le mie Prenotazioni":
        return await list_bookings(update, context)
    elif text == "ℹ️ Informazioni":
        return await show_info(update, context)
    elif text == "🚫 Blacklist Ospedali":
        return await manage_hospital_blacklist(update, context)
    elif text == "📣 Messaggio Broadcast":
        return await broadcast_message(update, context)
    elif text == "🔑 Autorizza Utente":
        return await authorize_user(update, context)
    elif text == "📊 Configura Monitoraggio Referti":
        return await download_medical_reports(update, context)
    elif text == "📋 Gestisci Monitoraggi Referti":
        return await list_report_monitoring(update, context)
    else:
        keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD

        # Messaggio di default con la tastiera aggiornata
        await update.message.reply_text(
            "Usa i pulsanti sotto per interagire con il bot.",
            reply_markup=keyboard
        )

async def error_handler(update, context):
    """Gestisce gli errori del bot."""
    # Otteniamo l'errore
    error = context.error
    
    # Logging avanzato con traccia di errore
    import traceback
    error_trace = traceback.format_exc()
    
    # Logghiamo l'errore dettagliato
    logger.error(f"Errore nell'update {update}: {error}")
    logger.error(f"Traccia dell'errore: {error_trace}")
    
    # Recuperiamo l'ID utente
    user_id = None
    if update.effective_user:
        user_id = update.effective_user.id
    
    # Puliamo i dati dell'utente se possibile
    if user_id and user_id in user_data:
        logger.info(f"Pulizia dati utente per {user_id} dopo errore")
        user_data.pop(user_id, None)
    
    # Informiamo l'utente dell'errore (se possibile)
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Si è verificato un errore durante l'elaborazione della tua richiesta. "
                 "Per favore, riprova o contatta l'amministratore se il problema persiste."
        )
    
    # Ripristina la tastiera principale se possibile
    if update and update.effective_chat and update.effective_user:
        keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD

        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🔄 Sessione ripristinata. Seleziona un'operazione:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Errore nel ripristino della tastiera: {e}")


# Funzione per recuperare da errori
async def error_recovery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il recupero da errori nella conversazione."""
    user_id = update.effective_user.id
    
    # Pulisci i dati dell'utente
    if user_id in user_data:
        user_data.pop(user_id, None)
    
    keyboard = ADMIN_KEYBOARD if is_admin(user_id, authorized_users) else MAIN_KEYBOARD

    await update.message.reply_text(
        "⚠️ Si è verificato un problema con l'operazione corrente. "
        "Per favore, ricomincia o premi /cancel.",
        reply_markup=keyboard
    )
    
    return ConversationHandler.END

# =============================================================================
# SETUP HANDLERS
# =============================================================================

def setup_handlers(application):
    """Configura i gestori delle conversazioni per il bot."""
    
    # Gestione dell'aggiunta di prescrizioni con ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
        ],
        states={
            WAITING_FOR_FISCAL_CODE: [
                MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
                CommandHandler("cancel", cancel_operation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fiscal_code)
            ],
            WAITING_FOR_NRE: [
                MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
                CommandHandler("cancel", cancel_operation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nre)
            ],
            WAITING_FOR_PHONE: [
                MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
                CommandHandler("cancel", cancel_operation),
                # Assicurati che vengano usate le funzioni corrette in base all'azione
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_phone)
            ],
            WAITING_FOR_EMAIL: [
                MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
                CommandHandler("cancel", cancel_operation),
                # Questa è la modifica chiave: usiamo un gestore condizionale per l'email
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: 
                               handle_add_email(update, context) 
                               if update.effective_user.id in user_data and user_data[update.effective_user.id].get("action") == "add_prescription"
                               else handle_email(update, context))
            ],
            AUTHORIZING: [
                CallbackQueryHandler(handle_cancel_auth, pattern="^cancel"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_auth_user_id)
            ],
            CONFIRM_ADD: [
                CallbackQueryHandler(confirm_add_prescription)
            ],
            WAITING_FOR_PRESCRIPTION_TO_DELETE: [
                CallbackQueryHandler(handle_prescription_to_delete)
            ],
            WAITING_FOR_PRESCRIPTION_TO_TOGGLE: [
                CallbackQueryHandler(handle_prescription_toggle)
            ],
            WAITING_FOR_DATE_FILTER: [
                CallbackQueryHandler(handle_prescription_date_filter)
            ],
            WAITING_FOR_MONTHS_LIMIT: [
                CallbackQueryHandler(handle_months_limit),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_months_limit)
            ],
            CONFIRM_DATE_FILTER: [
                CallbackQueryHandler(confirm_date_filter)
            ],
            # Stati per la prenotazione
            WAITING_FOR_BOOKING_CHOICE: [
                CallbackQueryHandler(handle_booking_choice, pattern="^book_"),
                CallbackQueryHandler(handle_autobook_choice, pattern="^autobook_"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_")
            ],
            WAITING_FOR_SLOT_CHOICE: [
                CallbackQueryHandler(handle_slot_choice)
            ],
            WAITING_FOR_BOOKING_CONFIRMATION: [
                CallbackQueryHandler(confirm_booking)
            ],
            WAITING_FOR_AUTO_BOOK_CHOICE: [
                CallbackQueryHandler(handle_auto_book_toggle)
            ],
            WAITING_FOR_BOOKING_TO_CANCEL: [
                CallbackQueryHandler(handle_booking_to_cancel, pattern="^cancel_book_"),
                CallbackQueryHandler(confirm_cancel_booking, pattern="^confirm_cancel_"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_cancel_book$")
            ],
            WAITING_FOR_PRESCRIPTION_BLACKLIST: [
                CallbackQueryHandler(handle_prescription_blacklist, pattern="^blacklist_"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_")
            ],
            WAITING_FOR_HOSPITAL_SELECTION: [
                CallbackQueryHandler(handle_hospital_selection, pattern="^toggle_hospital_"),
                CallbackQueryHandler(handle_hospital_selection, pattern="^page_"),
                CallbackQueryHandler(handle_hospital_selection, pattern="^blacklist_all$"), 
                CallbackQueryHandler(handle_hospital_selection, pattern="^whitelist_all$"), 
                CallbackQueryHandler(confirm_hospital_blacklist, pattern="^confirm_blacklist"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_")
            ],
            WAITING_FOR_BROADCAST_MESSAGE: [
                MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
                CommandHandler("cancel", cancel_operation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message)
            ],
            WAITING_FOR_BROADCAST_CONFIRMATION: [
                CallbackQueryHandler(confirm_broadcast)
            ],
            WAITING_FOR_FISCAL_CODE_REPORT: [
                MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
                CommandHandler("cancel", cancel_operation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fiscal_code_report)
            ],
            WAITING_FOR_PASSWORD_REPORT: [
                MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
                CommandHandler("cancel", cancel_operation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password_report)
            ],
            WAITING_FOR_REPORT_CHOICE: [
                CallbackQueryHandler(handle_report_choice, pattern="^report_"),
                CallbackQueryHandler(handle_download_reports_selection, pattern="^download_reports_"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_")
            ],
            
            # Nuovo stato per gestire le azioni sui monitoraggi:
            WAITING_FOR_REPORTS_MONITORING_ACTION: [
                CallbackQueryHandler(handle_report_monitoring_action, pattern="^toggle_monitor_"),
                CallbackQueryHandler(handle_report_monitoring_action, pattern="^remove_monitor_"),
                CallbackQueryHandler(handle_report_monitoring_action, pattern="^check_reports_now"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_operation),
            MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation),
            # Per recuperare da errori
            MessageHandler(filters.ALL, error_recovery)
        ]
    )
    
    application.add_handler(CommandHandler("cancel", cancel_operation)) # handler globale per il /cancel

    # Aggiungiamo i gestori
    application.add_handler(conv_handler)
    
    booking_cancel_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_cancel_booking, pattern="^cancel_appointment$")
        ],
        states={
            WAITING_FOR_BOOKING_TO_CANCEL: [
                CallbackQueryHandler(handle_booking_to_cancel, pattern="^cancel_book_"),
                CallbackQueryHandler(confirm_cancel_booking, pattern="^confirm_cancel_"),
                CallbackQueryHandler(cancel_operation, pattern="^cancel_cancel_book$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_operation, pattern="^cancel_")
        ],
        name="booking_cancellation"
    )
    
    application.add_handler(booking_cancel_handler)
    
    # CORREZIONE IMPORTANTE: Utilizzo di un pattern più preciso per evitare errori di regex
    reports_monitoring_handler = CallbackQueryHandler(
        handle_report_monitoring_action, 
        pattern="^(toggle_monitor_|remove_monitor_|check_reports_now)"
    )
    application.add_handler(reports_monitoring_handler)
    
    # Gestore errori
    application.add_error_handler(error_handler)
    