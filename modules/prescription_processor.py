import asyncio, logging, json, os

# Importiamo le variabili globali e funzioni da altri moduli
from recup_monitor import logger, TELEGRAM_TOKEN  # Importa il token Telegram

from modules.api_client import (
    get_access_token, update_device_token, get_patient_info, 
    get_doctor_info, check_prescription, get_prescription_details,
    get_availabilities
)
from modules.data_utils import (
    load_input_data, save_input_data, is_date_within_range,
    is_similar_datetime, format_date
)

from modules.locations_db import update_location_db


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
    
    # Usa la configurazione fornita o quella predefinita
    if config is None:
        config = default_config
    else:
        # Merge delle configurazioni, mantenendo i valori forniti
        for key, value in default_config.items():
            if key not in config:
                config[key] = value
    
    # Otteniamo la blacklist degli ospedali
    hospitals_blacklist = config.get("hospitals_blacklist", [])
    
    # Filtriamo le disponibilità (rimuovendo gli ospedali in blacklist)
    if hospitals_blacklist:
        filtered_current = []
        for avail in current:
            hospital_name = avail['hospital']['name']
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
                       avail['hospital']['name'] not in hospitals_blacklist
                ]
            else:
                filtered_current = [
                    avail for avail in current
                    if avail['hospital']['name'] not in hospitals_blacklist
                ]
            
            # Se non ci sono disponibilità nel range, non mostriamo nulla
            if not filtered_current:
                return None
                
            # Preparazione del messaggio con formattazione HTML migliorata
            message = f"""
<b>🔍 Nuova Prescrizione</b>

<b>Codice Fiscale:</b> <code>{fiscal_code}</code>
<b>ID Tessera Sanitaria:</b> <code>{cf_code}</code>
<b>NRE:</b> <code>{nre}</code>
<b>Descrizione:</b> <code>{prescription_name}</code>
"""
            
            # Se c'è un limite di mesi, lo mostriamo
            if months_limit is not None:
                message += f"<b>Filtro:</b> Solo appuntamenti entro {months_limit} mesi\n"
            
            message += f"\n📋 <b>Disponibilità Trovate:</b> {len(filtered_current)}\n"
            
            # Raggruppiamo per ospedale
            hospitals = {}
            for avail in sorted(filtered_current, key=lambda x: x['date']):
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals:
                    hospitals[hospital_name] = []
                hospitals[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals.items():
                message += f"\n<b>{hospital_name}</b>\n"
                message += f"📍 {availabilities[0]['site']['address']}\n"
                
                for avail in sorted(availabilities, key=lambda x: x['date']):
                    message += f"📅 {format_date(avail['date'])} - {avail['price']} €\n"
                
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
        hospital_id = a['hospital'].get('id', 'unknown')
        if hospital_id not in prev_by_hospital:
            prev_by_hospital[hospital_id] = []
        prev_by_hospital[hospital_id].append(a)
    
    for a in filtered_current:
        hospital_id = a['hospital'].get('id', 'unknown')
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
                    if prev_avail['price'] != curr_avail['price']:
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

<b>Codice Fiscale:</b> <code>{fiscal_code}</code>
<b>ID Tessera Sanitaria:</b> <code>{cf_code}</code>
<b>NRE:</b> <code>{nre}</code>
<b>Descrizione:</b> <code>{prescription_name}</code>
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
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals_new:
                    hospitals_new[hospital_name] = []
                hospitals_new[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals_new.items():
                message += f"\n<b>{hospital_name}</b>\n"
                message += f"📍 {availabilities[0]['site']['address']}\n"
                
                # Ordiniamo le date
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                # Mostriamo tutte le date
                for avail in sorted_availabilities:
                    message += f"📅 {format_date(avail['date'])} - {avail['price']} €\n"
        
        # Disponibilità rimosse (se configurato)
        if notify_removed and changes["removed"]:
            message += "\n<b>🔴 Disponibilità Rimosse:</b>\n"
            hospitals_removed = {}
            for avail in changes["removed"]:
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals_removed:
                    hospitals_removed[hospital_name] = []
                hospitals_removed[hospital_name].append(avail)
            
            for hospital_name, availabilities in hospitals_removed.items():
                message += f"\n<b>{hospital_name}</b>\n"
                message += f"📍 {availabilities[0]['site']['address']}\n"
                
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                for avail in sorted_availabilities:
                    message += f"📅 {format_date(avail['date'])}\n"
        
        # Tutte le disponibilità attuali
        if show_all_current and filtered_current:
            message += f"\n📋 <b>Tutte le Disponibilità:</b> {len(filtered_current)}\n"
            
            hospitals = {}
            for avail in filtered_current:
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals:
                    hospitals[hospital_name] = []
                hospitals[hospital_name].append(avail)
            
            for hospital_name, availabilities in hospitals.items():
                message += f"\n<b>{hospital_name}</b>\n"
                message += f"📍 {availabilities[0]['site']['address']}\n"
                
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                for avail in sorted_availabilities:
                    message += f"📅 {format_date(avail['date'])} - {avail['price']} €\n"
        
        return message
    
    return None

def process_prescription(prescription, previous_data, chat_id=None):
    """Process a single prescription and check for availability changes."""
    fiscal_code = prescription["fiscal_code"]
    nre = prescription["nre"]
    prescription_key = f"{fiscal_code}_{nre}"
    
    # Otteniamo la configurazione specifica per questa prescrizione
    config = prescription.get("config", {})
    
    # Otteniamo l'ID chat Telegram specifico per questa prescrizione, se presente
    telegram_chat_id = prescription.get("telegram_chat_id", chat_id)
    
    logger.info(f"Elaborazione prescrizione {prescription_key}")
    
    # Step 1: Get access token
    access_token = get_access_token()
    if not access_token:
        return False, "Impossibile ottenere il token di accesso"
    
    # Step 2: Update device token
    update_device_token(access_token)
    
    # Step 3: Get patient information
    patient_info = get_patient_info(fiscal_code)
    if not patient_info or 'content' not in patient_info or not patient_info['content']:
        error_msg = f"Impossibile trovare informazioni per il paziente {fiscal_code}"
        logger.error(error_msg)
        return False, error_msg
        
    # Carichiamo tutte le prescrizioni
    all_prescriptions = load_input_data()
    cf_code = ""
    
    try:
        # Flag per verificare se abbiamo trovato e aggiornato la prescrizione
        prescription_updated = False
        
        # Cerchiamo e aggiorniamo la prescrizione specifica
        for p in all_prescriptions:
            if (p["fiscal_code"] == fiscal_code and 
                p["nre"] == nre):
                
                # Verifichiamo che ci siano informazioni del paziente valide
                if patient_info and 'content' in patient_info and patient_info['content']:
                    patient_details = patient_info['content'][0]
                    
                    # Creiamo un dizionario dettagliato e pulito
                    patient_info_dict = {
                        "firstName": patient_details.get("firstName", "N/A"),
                        "lastName": patient_details.get("lastName", "N/A"),
                        "birthDate": patient_details.get("birthDate", "N/A"),
                        
                        # Codice della tessera sanitaria con gestione più robusta
                        "teamCard": {
                            "code": patient_details.get("teamCard", {}).get("code", "N/A"),
                            "validFrom": patient_details.get("teamCard", {}).get("startDate", "N/A"),
                            "validTo": patient_details.get("teamCard", {}).get("endDate", "N/A")
                        },
                        
                        # Residenza con gestione degli attributi mancanti
                        "residence": " ".join(filter(bool, [
                            patient_details.get('residence', {}).get('address', ''),
                            patient_details.get('residence', {}).get('streetNumber', ''),
                            patient_details.get('residence', {}).get('postalCode', ''),
                            patient_details.get('residence', {}).get('town', {}).get('name', ''),
                            patient_details.get('residence', {}).get('province', {}).get('id', '')
                        ])).strip() or "N/A",
                        
                        # Domicilio con gestione degli attributi mancanti
                        "domicile": " ".join(filter(bool, [
                            patient_details.get('domicile', {}).get('address', ''),
                            patient_details.get('domicile', {}).get('streetNumber', ''),
                            patient_details.get('domicile', {}).get('postalCode', ''),
                            patient_details.get('domicile', {}).get('town', {}).get('name', ''),
                            patient_details.get('domicile', {}).get('province', {}).get('id', '')
                        ])).strip() or "N/A",
                        
                        # Informazioni aggiuntive
                        "birthPlace": f"{patient_details.get('birthPlace', {}).get('name', 'N/A')}, "
                                      f"{patient_details.get('birthProvince', {}).get('id', 'N/A')}",
                        
                        "citizenship": patient_details.get('citizenship', {}).get('name', 'N/A')
                    }
                    
                    cf_code = patient_details.get("teamCard", {}).get("code", "")
                    
                    # Aggiungiamo le informazioni del paziente
                    p["patient_info"] = patient_info_dict
                    
                    # Logghiamo l'aggiornamento
                    logger.info(f"Aggiornate informazioni paziente per prescrizione NRE: {nre}")
                    
                    # Impostiamo il flag di aggiornamento
                    prescription_updated = True
                
                break  # Usciamo dal ciclo dopo aver trovato la prescrizione
        
        # Salviamo solo se abbiamo effettivamente aggiornato qualcosa
        if prescription_updated:
            save_input_data(all_prescriptions)
            logger.info(f"Salvate informazioni paziente per prescrizione NRE: {nre}")
        else:
            logger.warning(f"Nessuna prescrizione trovata per aggiornamento: {fiscal_code}, {nre}")
    
    except Exception as e:
        # Catturiamo e logghiamo eventuali errori durante l'aggiornamento
        logger.error(f"Errore durante l'aggiornamento delle informazioni paziente: {str(e)}")
    
    
    patient_id = patient_info['content'][0]['id']
    
    # Step 4: Get doctor information
    doctor_info = get_doctor_info(fiscal_code)
    if not doctor_info or 'id' not in doctor_info:
        error_msg = f"Impossibile trovare informazioni per il medico del paziente {fiscal_code}"
        logger.error(error_msg)
        return False, error_msg
    
    process_id = doctor_info['id']
    
    # Step 5: Check prescription
    check_prescription_result = check_prescription(patient_id, nre)
    if not check_prescription_result:
        error_msg = f"Impossibile verificare la prescrizione {nre}"
        logger.error(error_msg)
        return False, error_msg
    
    # Step 6: Get prescription details
    prescription_details = get_prescription_details(patient_id, nre)
    if not prescription_details or 'details' not in prescription_details or not prescription_details['details']:
        error_msg = f"Impossibile ottenere i dettagli della prescrizione {nre}"
        logger.error(error_msg)
        return False, error_msg
    
    order_ids = prescription_details['details'][0]['service']['id']
    
    # Ottieni il nome della prescrizione
    prescription_name = "Prescrizione sconosciuta"
    try:
        if 'details' in prescription_details and prescription_details['details']:
            service_description = prescription_details['details'][0]['service'].get('description', '')
            if service_description:
                prescription_name = service_description
    except Exception as e:
        logger.warning(f"Impossibile ottenere il nome della prescrizione: {str(e)}")
    
    # Aggiorniamo il nome della prescrizione nei dati
    prescription["description"] = prescription_name
    
    # Step 7: Get availabilities
    availabilities = get_availabilities(patient_id, process_id, nre, order_ids)
    if not availabilities or 'content' not in availabilities:
        error_msg = f"Impossibile ottenere le disponibilità per {nre}, sei sicuro che non sia già prenotata?"
        logger.error(error_msg)
        return False, error_msg
    
    current_availabilities = availabilities['content']
    
    # *** In questo punto aggiorniamo il database delle location ***
    if os.path.exists("../locations.json"):
        with open("../locations.json", "r") as f:
            locations_db = json.load(f)
    else:
        locations_db = {}
        
    for slot in current_availabilities:
        hospital_info = slot.get("hospital", {})
        site_info = slot.get("site", {})
        hospital_name = hospital_info.get("name", "Sconosciuto")
        address = site_info.get("address", "Indirizzo non disponibile")
        update_location_db(hospital_name, address, locations_db)
    
    # Salva le modifiche sul file JSON
    with open("../locations.json", "w") as f:
        json.dump(locations_db, f, indent=2)
    
    # Compare with previous data to detect changes
    previous_availabilities = previous_data.get(prescription_key, [])
    
    # Confronta e genera un messaggio se ci sono cambiamenti significativi
    changes_message = compare_availabilities(
        previous_availabilities, 
        current_availabilities,
        fiscal_code,
        nre,
        prescription_name,
        cf_code,
        config
    )
    
    # Se ci sono cambiamenti, invia una notifica
    if changes_message:
        logger.info(f"Rilevati cambiamenti significativi per {prescription_key}")
        
        # Controlliamo se le notifiche sono abilitate per questa prescrizione
        notifications_enabled = prescription.get("notifications_enabled", True)  # Default a True
        
        if notifications_enabled:
            try:
                # Utilizziamo il metodo normale invece di quello asincrono per evitare problemi
                import requests
                
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                data = {
                    "chat_id": telegram_chat_id,
                    "text": changes_message,
                    "parse_mode": "HTML"
                }
                
                response = requests.post(url, data=data, timeout=10)
                response.raise_for_status()
                
                logger.info(f"Notifica inviata al chat ID: {telegram_chat_id}")
            except Exception as e:
                logger.error(f"Errore nell'inviare notifica: {str(e)}")
        else:
            logger.info(f"Notifiche disabilitate per {prescription_key}, nessun messaggio inviato")
    else:
        logger.info(f"Nessun cambiamento significativo rilevato per {prescription_key}")
    
    # Update previous data for next comparison
    previous_data[prescription_key] = current_availabilities
    
    auto_book_enabled = prescription.get("auto_book_enabled", False)
    
    # Se ci sono disponibilità e la prenotazione automatica è abilitata
    if auto_book_enabled and current_availabilities:
        # Verifichiamo se la prescrizione ha i dati di contatto necessari
        if "phone" in prescription and "email" in prescription:
            try:
                # Verifichiamo che la prescrizione non sia già prenotata
                if not any(booking.get("booking_id") for booking in prescription.get("bookings", [])):
                    logger.info(f"Tentativo di prenotazione automatica per {prescription_key}")
                    
                    # Importiamo la funzione di prenotazione
                    from modules.booking_client import booking_workflow
                    
                    # Avviamo il processo di prenotazione automatica
                    result = booking_workflow(
                        fiscal_code=fiscal_code,
                        nre=nre,
                        phone_number=prescription["phone"],
                        email=prescription["email"],
                        patient_id=patient_id,
                        process_id=process_id,
                        slot_choice=0  # Il primo slot disponibile
                    )
                    
                    if result["success"] and result["action"] == "booked":
                        # La prenotazione è andata a buon fine!
                        logger.info(f"Prenotazione automatica riuscita per {prescription_key}!")
                        
                        # Formattare la data
                        try:
                            date_obj = datetime.strptime(result["appointment_date"], "%Y-%m-%dT%H:%M:%SZ")
                            formatted_date = date_obj.strftime("%d/%m/%Y %H:%M")
                        except:
                            formatted_date = result["appointment_date"]
                        
                        # Inviamo una notifica all'utente
                        booking_message = f"""
<b>✅ Prenotazione Automatica Completata!</b>

<b>Prescrizione:</b> {prescription_name}
<b>Data:</b> {formatted_date}
<b>Ospedale:</b> {result['hospital']}
<b>Indirizzo:</b> {result['address']}
<b>ID Prenotazione:</b> {result['booking_id']}

La prenotazione è stata effettuata automaticamente. Controlla la tua email per conferma.
"""
                        # Utilizziamo il metodo normale invece di quello asincrono per evitare problemi
                        import requests
                        
                        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                        data = {
                            "chat_id": telegram_chat_id,
                            "text": booking_message,
                            "parse_mode": "HTML"
                        }
                        
                        response = requests.post(url, data=data, timeout=10)
                        
                        # Invio del PDF come documento
                        url_document = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
                        
                        from io import BytesIO
                        
                        files = {
                            'document': ('prenotazione.pdf', BytesIO(result['pdf_content']), 'application/pdf')
                        }
                        
                        data_document = {
                            "chat_id": telegram_chat_id,
                            "caption": f"Documento di prenotazione per {prescription_name} del {formatted_date}"
                        }
                        
                        requests.post(url_document, data=data_document, files=files, timeout=30)
                        
                        # Aggiorniamo la prescrizione per includere la prenotazione
                        all_prescriptions = load_input_data()
                        for p in all_prescriptions:
                            if p["fiscal_code"] == fiscal_code and p["nre"] == nre:
                                if "bookings" not in p:
                                    p["bookings"] = []
                                p["bookings"].append({
                                    "booking_id": result["booking_id"],
                                    "date": result["appointment_date"],
                                    "hospital": result["hospital"],
                                    "address": result["address"],
                                    "service": prescription_name
                                })
                                
                                # Disabilitiamo la prenotazione automatica dopo il successo
                                p["auto_book_enabled"] = False
                                
                                break
                        
                        # Salviamo le modifiche
                        save_input_data(all_prescriptions)
                    elif result["success"] and result["action"] == "list_slots":
                        # Ci sono slot disponibili, ma non è stata completata la prenotazione
                        logger.info(f"Slot disponibili per {prescription_key}, prenotazione non completata")
                    else:
                        # Errore nella prenotazione
                        logger.error(f"Errore nella prenotazione automatica per {prescription_key}: {result.get('message', 'Errore sconosciuto')}")
            except Exception as e:
                logger.error(f"Errore durante la prenotazione automatica: {str(e)}")
    
    # Update previous data for next comparison
    previous_data[prescription_key] = current_availabilities
    
    return True, prescription_name
    