import json
import os

from config import logger, DEBUG_FOLDER

from modules.api_client import (
    get_access_token, update_device_token, get_patient_info,
    get_doctor_info, check_prescription, get_prescription_details,
    get_availabilities, api_message
)
from modules.data_utils import (
    update_prescription, is_date_within_range,
    is_similar_datetime, format_date, fmt_datetime
)
from modules.telegram_utils import esc, send_message_sync, send_document_sync

from modules.locations_db import update_location_db, load_locations_db, save_locations_db


def _hospital(avail):
    return (avail.get('hospital') or {}).get('name') or 'Struttura sconosciuta'


def _address(avail):
    return (avail.get('site') or {}).get('address') or 'Indirizzo non disponibile'


def _price(avail):
    price = avail.get('price')
    return esc(price) if price is not None else 'N/D'


def compare_availabilities(previous, current, fiscal_code, nre, prescription_name="", cf_code="", config=None):
    """Compare previous and current availabilities with configuration per prescrizione."""
    # Configurazione predefinita se non specificata
    default_config = {
        "only_new_dates": True,
        "notify_removed": False,
        "min_changes_to_notify": 2,
        "time_threshold_minutes": 60,
        "show_all_current": True,  # Mostra tutte le disponibilità attuali
        "months_limit": None,       # Nessun limite di mesi predefinito
        "hospitals_blacklist": []
    }
    
    # Merge con i valori predefiniti, senza modificare la configurazione della prescrizione
    config = {**default_config, **(config or {})}
    
    # Otteniamo la blacklist degli ospedali
    hospitals_blacklist = config.get("hospitals_blacklist", [])
    
    # Filtriamo le disponibilità (rimuovendo gli ospedali in blacklist)
    if hospitals_blacklist:
        filtered_current = []
        for avail in current:
            hospital_name = _hospital(avail)
            if hospital_name not in hospitals_blacklist:
                filtered_current.append(avail)
        current = filtered_current
    
    # Se è la prima volta che controlliamo questa prescrizione
    if not previous or not current:
        # Se non c'erano dati precedenti, consideriamo tutto come nuovo ma non spammiamo
        if not previous and len(current) > 0:
            # Filtriamo le disponibilità in base al limite di mesi
            months_limit = config.get("months_limit")
            if months_limit is not None:
                filtered_current = [
                    avail for avail in current 
                    if is_date_within_range(avail['date'], months_limit) and 
                       _hospital(avail) not in hospitals_blacklist
                ]
            else:
                filtered_current = [
                    avail for avail in current
                    if _hospital(avail) not in hospitals_blacklist
                ]
            
            # Se non ci sono disponibilità nel range, non mostriamo nulla
            if not filtered_current:
                return None
                
            # Preparazione del messaggio con formattazione HTML migliorata
            message = f"""
<b>🔍 Nuova Prescrizione</b>

<b>Codice Fiscale:</b> <code>{esc(fiscal_code)}</code>
<b>ID Tessera Sanitaria:</b> <code>{esc(cf_code)}</code>
<b>NRE:</b> <code>{esc(nre)}</code>
<b>Descrizione:</b> <code>{esc(prescription_name)}</code>
"""
            
            # Se c'è un limite di mesi, lo mostriamo
            if months_limit is not None:
                message += f"<b>Filtro:</b> Solo appuntamenti entro {months_limit} mesi\n"
            
            message += f"\n📋 <b>Disponibilità Trovate:</b> {len(filtered_current)}\n"
            
            # Raggruppiamo per ospedale
            hospitals = {}
            for avail in sorted(filtered_current, key=lambda x: x['date']):
                hospital_name = _hospital(avail)
                if hospital_name not in hospitals:
                    hospitals[hospital_name] = []
                hospitals[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals.items():
                message += f"\n<b>{esc(hospital_name)}</b>\n"
                message += f"📍 {esc(_address(availabilities[0]))}\n"
                
                for avail in sorted(availabilities, key=lambda x: x['date']):
                    message += f"📅 {format_date(avail['date'])} - {_price(avail)} €\n"
                
                message += "\n"  # Spazio tra gli ospedali
            
            return message
        return None

    # Otteniamo i valori di configurazione
    only_new_dates = config.get("only_new_dates", True)
    notify_removed = config.get("notify_removed", False)
    min_changes = config.get("min_changes_to_notify", 2)
    time_threshold = config.get("time_threshold_minutes", 60)
    show_all_current = config.get("show_all_current", True)
    months_limit = config.get("months_limit", None)
    
    # Filtriamo le disponibilità attuali in base al limite di mesi
    if months_limit is not None:
        filtered_current = [
            avail for avail in current 
            if is_date_within_range(avail['date'], months_limit)
        ]
    else:
        filtered_current = current
        
    # Filtriamo anche le disponibilità precedenti per avere un confronto corretto
    if months_limit is not None:
        filtered_previous = [
            avail for avail in previous 
            if is_date_within_range(avail['date'], months_limit)
        ]
    else:
        filtered_previous = previous
    
    # Prepara una struttura per i cambiamenti
    changes = {
        "new": [],
        "removed": [],
        "changed": []
    }
    
    # Crea dizionari per un confronto più semplice
    # Usiamo l'ID dell'ospedale come chiave principale per aggregare meglio
    prev_by_hospital = {}
    curr_by_hospital = {}
    
    # Organizziamo i dati per ospedale
    for a in filtered_previous:
        hospital_id = (a.get('hospital') or {}).get('id', 'unknown')
        if hospital_id not in prev_by_hospital:
            prev_by_hospital[hospital_id] = []
        prev_by_hospital[hospital_id].append(a)
    
    for a in filtered_current:
        hospital_id = (a.get('hospital') or {}).get('id', 'unknown')
        if hospital_id not in curr_by_hospital:
            curr_by_hospital[hospital_id] = []
        curr_by_hospital[hospital_id].append(a)
    
    # Lista degli ospedali
    all_hospitals = set(list(prev_by_hospital.keys()) + list(curr_by_hospital.keys()))
    
    # Esaminiamo i cambiamenti per ospedale
    for hospital_id in all_hospitals:
        prev_avails = prev_by_hospital.get(hospital_id, [])
        curr_avails = curr_by_hospital.get(hospital_id, [])
        
        # Costruiamo dizionari per date
        prev_dates = {a['date']: a for a in prev_avails}
        curr_dates = {a['date']: a for a in curr_avails}
        
        # Verifica nuove date
        for date, avail in curr_dates.items():
            if date not in prev_dates:
                # Verifichiamo se si tratta solo di un piccolo cambiamento di orario
                is_minor_change = False
                for prev_date in prev_dates.keys():
                    # Confrontiamo le date ignorando ore e minuti
                    if is_similar_datetime(prev_date, date, time_threshold):
                        # È probabilmente solo un aggiustamento di orario, non una nuova disponibilità
                        is_minor_change = True
                        break
                
                if not is_minor_change:
                    changes["new"].append(avail)
        
        # Verifica date rimosse (solo se notify_removed è True)
        if notify_removed:
            for date, avail in prev_dates.items():
                if date not in curr_dates:
                    # Verifichiamo se si tratta solo di un piccolo cambiamento di orario
                    is_minor_change = False
                    for curr_date in curr_dates.keys():
                        # Confrontiamo le date ignorando ore e minuti
                        if is_similar_datetime(date, curr_date, time_threshold):
                            # È probabilmente solo un aggiustamento di orario, non una rimozione
                            is_minor_change = True
                            break
                    
                    if not is_minor_change:
                        changes["removed"].append(avail)
        
        # Verifica cambiamenti di prezzo (solo se only_new_dates è False)
        if not only_new_dates:
            for date, curr_avail in curr_dates.items():
                if date in prev_dates:
                    prev_avail = prev_dates[date]
                    if prev_avail.get('price') != curr_avail.get('price'):
                        changes["changed"].append({
                            "previous": prev_avail,
                            "current": curr_avail
                        })
    
    # Calcoliamo il totale dei cambiamenti in base alla configurazione
    total_changes = len(changes["new"])
    if notify_removed:
        total_changes += len(changes["removed"])
    if not only_new_dates:
        total_changes += len(changes["changed"])
    
    # Se ci sono abbastanza cambiamenti, costruisci un messaggio
    if total_changes >= min_changes or (len(changes["new"]) > 0 and only_new_dates):
        # Preparazione del messaggio con formattazione HTML migliorata
        message = f"""
<b>🔍 Aggiornamento Prescrizione</b>

<b>Codice Fiscale:</b> <code>{esc(fiscal_code)}</code>
<b>ID Tessera Sanitaria:</b> <code>{esc(cf_code)}</code>
<b>NRE:</b> <code>{esc(nre)}</code>
<b>Descrizione:</b> <code>{esc(prescription_name)}</code>
"""
        
        # Se c'è un limite di mesi, lo mostriamo
        if months_limit is not None:
            message += f"<b>Filtro:</b> Solo appuntamenti entro {months_limit} mesi\n"
        
        # Intestazione del messaggio
        if only_new_dates:
            message += f"🆕 <b>Nuove Disponibilità:</b> {len(changes['new'])}\n"
        else:
            message += f"🔄 <b>Cambiamenti:</b> {total_changes}\n"
        
        # Nuove disponibilità
        if changes["new"]:
            message += "\n<b>🟢 Nuove Disponibilità:</b>\n"
            
            # Raggruppiamo per ospedale
            hospitals_new = {}
            for avail in changes["new"]:
                hospital_name = _hospital(avail)
                if hospital_name not in hospitals_new:
                    hospitals_new[hospital_name] = []
                hospitals_new[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals_new.items():
                message += f"\n<b>{esc(hospital_name)}</b>\n"
                message += f"📍 {esc(_address(availabilities[0]))}\n"
                
                # Ordiniamo le date
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                # Mostriamo tutte le date
                for avail in sorted_availabilities:
                    message += f"📅 {format_date(avail['date'])} - {_price(avail)} €\n"
        
        # Disponibilità rimosse (se configurato)
        if notify_removed and changes["removed"]:
            message += "\n<b>🔴 Disponibilità Rimosse:</b>\n"
            hospitals_removed = {}
            for avail in changes["removed"]:
                hospital_name = _hospital(avail)
                if hospital_name not in hospitals_removed:
                    hospitals_removed[hospital_name] = []
                hospitals_removed[hospital_name].append(avail)
            
            for hospital_name, availabilities in hospitals_removed.items():
                message += f"\n<b>{esc(hospital_name)}</b>\n"
                message += f"📍 {esc(_address(availabilities[0]))}\n"
                
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                for avail in sorted_availabilities:
                    message += f"📅 {format_date(avail['date'])}\n"
        
        # Tutte le disponibilità attuali
        if show_all_current and filtered_current:
            message += f"\n📋 <b>Tutte le Disponibilità:</b> {len(filtered_current)}\n"
            
            hospitals = {}
            for avail in filtered_current:
                hospital_name = _hospital(avail)
                if hospital_name not in hospitals:
                    hospitals[hospital_name] = []
                hospitals[hospital_name].append(avail)
            
            for hospital_name, availabilities in hospitals.items():
                message += f"\n<b>{esc(hospital_name)}</b>\n"
                message += f"📍 {esc(_address(availabilities[0]))}\n"
                
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                for avail in sorted_availabilities:
                    message += f"📅 {format_date(avail['date'])} - {_price(avail)} €\n"
        
        return message
    
    return None

def _save_debug(nre, kind, data):
    """Salva una volta sola la risposta grezza delle API per una ricetta (diagnostica)."""
    try:
        os.makedirs(DEBUG_FOLDER, exist_ok=True)
        path = os.path.join(DEBUG_FOLDER, f"{nre}_{kind}.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            logger.info(f"Risposta API salvata per diagnostica: {path}")
    except Exception as e:
        logger.warning(f"Impossibile salvare la risposta di diagnostica: {e}")


def _record_status(prescription, telegram_chat_id, reason, notify):
    """
    Memorizza il motivo per cui la Regione non permette di prenotare la ricetta
    (scaduta, già presa in carico, priorità non prenotabile online...) e avvisa
    l'utente una sola volta per ogni nuovo motivo. reason=None azzera lo stato.
    """
    fiscal_code, nre = prescription["fiscal_code"], prescription["nre"]
    previous = prescription.get("status_message")
    if previous == reason:
        return
    prescription["status_message"] = reason
    try:
        update_prescription(fiscal_code, nre, lambda p: p.__setitem__("status_message", reason))
    except Exception as e:
        logger.warning(f"Impossibile salvare lo stato della prescrizione: {e}")

    if reason and notify and prescription.get("notifications_enabled", True) and telegram_chat_id:
        description = prescription.get("description") or f"Prescrizione {nre}"
        send_message_sync(
            telegram_chat_id,
            f"ℹ️ <b>{esc(description)}</b>\n"
            f"NRE: <code>{esc(nre)}</code>\n\n"
            f"⚠️ Al momento non è prenotabile online.\nMotivo: {esc(reason)}.\n\n"
            "Il bot continuerà a controllarla e ti avviserà se diventa prenotabile."
        )


def _update_description(prescription, patient_id, nre):
    """Legge il nome della prestazione anche quando la ricetta non è prenotabile."""
    try:
        details = get_prescription_details(patient_id, nre)
        name = ((details or {}).get("details") or [{}])[0].get("service", {}).get("description")
        if name and prescription.get("description") != name:
            prescription["description"] = name
            update_prescription(prescription["fiscal_code"], nre, lambda p: p.__setitem__("description", name))
    except Exception as e:
        logger.warning(f"Impossibile leggere la descrizione della prescrizione: {e}")


def is_prescription_already_booked(prescription):
    """Verifica se una prescrizione ha già prenotazioni attive."""
    return bool(prescription.get("bookings"))


def _build_patient_info(patient_details):
    def place(key):
        info = patient_details.get(key) or {}
        return " ".join(filter(bool, [
            info.get('address', ''),
            info.get('streetNumber', ''),
            info.get('postalCode', ''),
            (info.get('town') or {}).get('name', ''),
            (info.get('province') or {}).get('id', '')
        ])).strip() or "N/A"

    team_card = patient_details.get("teamCard") or {}
    return {
        "firstName": patient_details.get("firstName", "N/A"),
        "lastName": patient_details.get("lastName", "N/A"),
        "birthDate": patient_details.get("birthDate", "N/A"),
        "teamCard": {
            "code": team_card.get("code", "N/A"),
            "validFrom": team_card.get("startDate", "N/A"),
            "validTo": team_card.get("endDate", "N/A")
        },
        "residence": place('residence'),
        "domicile": place('domicile'),
        "birthPlace": f"{(patient_details.get('birthPlace') or {}).get('name', 'N/A')}, "
                      f"{(patient_details.get('birthProvince') or {}).get('id', 'N/A')}",
        "citizenship": (patient_details.get('citizenship') or {}).get('name', 'N/A')
    }


def _notify_availability(prescription, telegram_chat_id, fiscal_code, nre, message):
    reply_markup = None
    # Pulsante "Prenota subito" se la prescrizione ha i contatti
    if prescription.get("phone") and prescription.get("email"):
        callback = f"quickbook_{fiscal_code}_{nre}"
        if len(callback.encode()) <= 64:
            reply_markup = {"inline_keyboard": [[{"text": "📅 Prenota subito", "callback_data": callback}]]}

    if send_message_sync(telegram_chat_id, message, reply_markup=reply_markup):
        logger.info(f"Notifica inviata al chat ID: {telegram_chat_id}")
    else:
        logger.error(f"Errore nell'inviare la notifica al chat ID: {telegram_chat_id}")


def _auto_book(prescription, telegram_chat_id, fiscal_code, nre, patient_id, process_id,
               prescription_name, current_availabilities, config):
    prescription_key = f"{fiscal_code}_{nre}"
    hospitals_blacklist = config.get("hospitals_blacklist", [])
    months_limit = config.get("months_limit")

    bookable = [
        avail for avail in current_availabilities
        if _hospital(avail) not in hospitals_blacklist
        and is_date_within_range(avail.get('date', ''), months_limit)
    ]
    if not bookable:
        logger.info(f"Nessuna disponibilità prenotabile dopo i filtri per {prescription_key}")
        return

    logger.info(f"Tentativo di prenotazione automatica per {prescription_key}")
    from modules.booking_client import booking_workflow

    # Il workflow ricalcola disponibilità e filtri e prenota il primo slot utile
    result = booking_workflow(
        fiscal_code=fiscal_code,
        nre=nre,
        phone_number=prescription["phone"],
        email=prescription["email"],
        patient_id=patient_id,
        process_id=process_id,
        slot_choice=0
    )

    if not (result.get("success") and result.get("action") == "booked"):
        logger.error(f"Errore nella prenotazione automatica per {prescription_key}: {result.get('message', 'Errore sconosciuto')}")
        return

    logger.info(f"Prenotazione automatica riuscita per {prescription_key}!")

    # Salviamo la prenotazione PRIMA di qualsiasi notifica: se l'invio fallisce,
    # il ciclo successivo non deve prenotare di nuovo
    booking_record = {
        "booking_id": result.get("booking_id"),
        "date": result["appointment_date"],
        "hospital": result["hospital"],
        "address": result["address"],
        "service": prescription_name
    }

    def mark_booked(p):
        p.setdefault("bookings", []).append(booking_record)
        p["auto_book_enabled"] = False

    try:
        update_prescription(fiscal_code, nre, mark_booked)
    except Exception as e:
        logger.error(f"Prenotazione {result.get('booking_id')} effettuata ma non salvata: {str(e)}")

    formatted_date = fmt_datetime(result["appointment_date"])
    booking_message = (
        "<b>✅ Prenotazione Automatica Completata!</b>\n\n"
        f"<b>Prescrizione:</b> {esc(prescription_name)}\n"
        f"<b>Data:</b> {esc(formatted_date)}\n"
        f"<b>Ospedale:</b> {esc(result['hospital'])}\n"
        f"<b>Indirizzo:</b> {esc(result['address'])}\n"
        f"<b>ID Prenotazione:</b> {esc(result.get('booking_id') or 'non disponibile')}\n\n"
        "La prenotazione è stata effettuata automaticamente. Controlla la tua email per conferma."
    )
    if not result.get("pdf_content"):
        booking_message += "\n\n⚠️ Il documento di prenotazione non è al momento scaricabile: lo trovi nell'app Salute Lazio."
    send_message_sync(telegram_chat_id, booking_message)

    if result.get("pdf_content"):
        send_document_sync(
            telegram_chat_id,
            result["pdf_content"],
            f"prenotazione_{result.get('booking_id') or nre}.pdf",
            caption=f"Documento di prenotazione per {prescription_name} del {formatted_date}"
        )


def process_prescription(prescription, previous_data, chat_id=None, notify_status=True):
    """Process a single prescription and check for availability changes."""
    fiscal_code = prescription["fiscal_code"]
    nre = prescription["nre"]
    prescription_key = f"{fiscal_code}_{nre}"

    # Otteniamo la configurazione specifica per questa prescrizione
    config = prescription.get("config", {})

    # Otteniamo l'ID chat Telegram specifico per questa prescrizione, se presente
    telegram_chat_id = prescription.get("telegram_chat_id", chat_id)

    logger.info(f"Elaborazione prescrizione NRE {nre}")

    # Verifica se la prescrizione è già prenotata, se sì, salta il monitoraggio
    if is_prescription_already_booked(prescription):
        logger.info(f"Prescrizione NRE {nre} già prenotata, monitoraggio saltato")
        return True, prescription.get("description", "Prescrizione prenotata")

    # Step 1: Get access token (opzionale, serve solo per notifiche push)
    access_token = get_access_token()
    if not access_token:
        logger.warning("Token gwapi-az non ottenuto, si continua senza aggiornare il device token")
    else:
        # Step 2: Update device token
        update_device_token(access_token)

    # Step 3: Get patient information
    patient_info = get_patient_info(fiscal_code)
    if not patient_info or 'content' not in patient_info or not patient_info['content']:
        error_msg = f"Impossibile trovare informazioni per il paziente {fiscal_code}"
        logger.error(f"Impossibile trovare informazioni per il paziente della prescrizione NRE {nre}")
        return False, error_msg

    patient_details = patient_info['content'][0]
    cf_code = (patient_details.get("teamCard") or {}).get("code", "")
    patient_info_dict = _build_patient_info(patient_details)

    # Una prescrizione appena inserita viene verificata prima di essere salvata:
    # in quel caso aggiorniamo solo l'oggetto in memoria
    prescription["patient_info"] = patient_info_dict
    try:
        update_prescription(fiscal_code, nre, lambda p: p.__setitem__("patient_info", patient_info_dict))
    except Exception as e:
        logger.error(f"Errore durante l'aggiornamento delle informazioni paziente: {str(e)}")

    patient_id = patient_details['id']

    # Step 4: Get doctor information
    doctor_info = get_doctor_info(fiscal_code)
    if not doctor_info or 'id' not in doctor_info:
        error_msg = f"Impossibile trovare informazioni per il medico del paziente {fiscal_code}"
        logger.error(f"Impossibile trovare informazioni sul medico per la prescrizione NRE {nre}")
        return False, error_msg

    process_id = doctor_info['id']

    # Step 5: Check prescription
    check_prescription_result = check_prescription(patient_id, nre)
    if not check_prescription_result:
        error_msg = f"Impossibile verificare la prescrizione {nre}"
        logger.error(error_msg)
        return False, error_msg
    if check_prescription_result.get("_not_found"):
        # 404: la Regione indica il motivo (es. ricetta scaduta), altrimenti può essere temporaneo
        reason = api_message(check_prescription_result)
        logger.warning(f"Prescrizione {nre} non disponibile (404) — skip ciclo")
        if reason:
            _record_status(prescription, telegram_chat_id, reason, notify_status)
            return False, reason
        return False, f"Prescrizione {nre} non disponibile al momento"

    # Se content è False, la prescrizione non è prenotabile dall'app
    if check_prescription_result.get('content') is False:
        _save_debug(nre, "check", check_prescription_result)
        _update_description(prescription, patient_id, nre)
        error_msg = api_message(check_prescription_result) or f"La prescrizione {nre} non è prenotabile online"
        logger.warning(f"Prescrizione non prenotabile online: {error_msg}")
        _record_status(prescription, telegram_chat_id, error_msg, notify_status)
        return False, error_msg

    # Step 6: Get prescription details
    prescription_details = get_prescription_details(patient_id, nre)
    if not prescription_details or not prescription_details.get('details'):
        error_msg = f"Impossibile ottenere i dettagli della prescrizione {nre}"
        logger.error(error_msg)
        return False, error_msg

    service = prescription_details['details'][0].get('service') or {}
    order_ids = service.get('id')
    prescription_name = service.get('description') or "Prescrizione sconosciuta"

    # Ricette con più prestazioni: le API dell'app ne gestiscono una per volta
    other_services = [
        (d.get('service') or {}).get('description') or 'Prestazione'
        for d in prescription_details['details'][1:]
    ]
    if other_services:
        _save_debug(nre, "details", prescription_details)

    # Aggiorniamo il nome della prescrizione nei dati
    if prescription.get("description") != prescription_name:
        prescription["description"] = prescription_name
        try:
            update_prescription(fiscal_code, nre, lambda p: p.__setitem__("description", prescription_name))
        except Exception as e:
            logger.warning(f"Impossibile salvare la descrizione della prescrizione: {str(e)}")

    # Step 7: Get availabilities
    availabilities = get_availabilities(patient_id, process_id, nre, order_ids)
    if not availabilities or 'content' not in availabilities:
        error_msg = f"Impossibile ottenere le disponibilità per {nre}, sei sicuro che non sia già prenotata?"
        logger.error(error_msg)
        return False, error_msg
    if availabilities.get("_already_booked"):
        logger.warning(f"Prescrizione NRE {nre} non più prenotabile (400), salto")
        reason = api_message(availabilities)
        if reason:
            _record_status(prescription, telegram_chat_id, reason, notify_status)
            return False, reason
        return True, prescription.get("description", "Prescrizione non più attiva")

    # La ricetta è di nuovo prenotabile: azzeriamo un eventuale stato precedente
    _record_status(prescription, telegram_chat_id, None, False)

    current_availabilities = availabilities['content'] or []

    # Aggiorniamo il database delle location
    try:
        locations_db = load_locations_db()
        for slot in current_availabilities:
            update_location_db(_hospital(slot), _address(slot), locations_db)
        save_locations_db(locations_db)
    except Exception as e:
        logger.error(f"Errore nell'aggiornare il database delle location: {str(e)}")

    # Confronta con i dati precedenti e genera un messaggio se ci sono cambiamenti significativi
    previous_availabilities = previous_data.get(prescription_key, [])
    changes_message = compare_availabilities(
        previous_availabilities,
        current_availabilities,
        fiscal_code,
        nre,
        prescription_name,
        cf_code,
        config
    )

    if changes_message and other_services:
        changes_message += (
            f"\n⚠️ <b>Questa ricetta contiene {len(other_services) + 1} prestazioni.</b> "
            "Il bot monitora e prenota solo la prima; per prenotarle tutte insieme usa "
            "Prenota Smart sul sito della Regione.\n"
            "Altre prestazioni: " + ", ".join(esc(s) for s in other_services) + "\n"
        )

    if changes_message:
        logger.info(f"Rilevati cambiamenti significativi per NRE {nre}")
        if prescription.get("notifications_enabled", True):
            _notify_availability(prescription, telegram_chat_id, fiscal_code, nre, changes_message)
        else:
            logger.info(f"Notifiche disabilitate per NRE {nre}, nessun messaggio inviato")
    else:
        logger.info(f"Nessun cambiamento significativo rilevato per NRE {nre}")

    # Update previous data for next comparison
    previous_data[prescription_key] = current_availabilities

    # Prenotazione automatica
    if prescription.get("auto_book_enabled", False) and current_availabilities:
        if prescription.get("phone") and prescription.get("email"):
            try:
                _auto_book(prescription, telegram_chat_id, fiscal_code, nre, patient_id, process_id,
                           prescription_name, current_availabilities, config)
            except Exception as e:
                logger.error(f"Errore durante la prenotazione automatica: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.warning(f"Prenotazione automatica attiva ma contatti mancanti per NRE {nre}")

    return True, prescription_name
