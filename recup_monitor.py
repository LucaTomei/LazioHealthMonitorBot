import requests
import base64
import json
import time
import os
import logging
from logging.handlers import RotatingFileHandler

from datetime import datetime

# Configurazione del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # File handler con rotazione: max 1MB per file, massimo 5 file
        RotatingFileHandler(
            "recup_monitor.log", 
            maxBytes=1024*1024,  # 1MB
            backupCount=5        # Mantiene 5 file di backup
        ),
        logging.StreamHandler()  # Stampa anche sulla console
    ]
)
logger = logging.getLogger("RecupMonitor")

# Base configuration
BASE_URL = "https://recup-webapi-appmobile.regione.lazio.it"
AUTH_HEADER = "Basic QVBQTU9CSUxFX1NQRUNJQUw6UGs3alVTcDgzbUh4VDU4NA=="

# Configurazione Telegram
TELEGRAM_TOKEN = "7616599944:sadsdasda-2Jy-GrWnFWJ8"  # Inserisci il tuo token del bot Telegram

# Percorso del file di input e dati precedenti
INPUT_FILE = "input_prescriptions.json"
PREVIOUS_DATA_FILE = "previous_data.json"

def format_date(date_string):
    """Formatta la data ISO in un formato più leggibile."""
    try:
        # Parse della data ISO
        dt = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%SZ")
        # Formatta la data in italiano
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

def get_access_token():
    """Obtain access token from the authentication endpoint."""
    token_url = "https://gwapi-az.servicelazio.it/token"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Authorization": "Basic aFJaMkYxNkthcWQ5dzZxRldEVEhJbHg3UnVRYTpnaUVHbEp4a0Iza1VBdWRLdXZNdFBJaTVRc2th",
        "Accept-Language": "it-IT;q=1.0",
        "User-Agent": "RLGEOAPP/2.2.0 (it.laziocrea.rlgeoapp; build:2.2.0; iOS 18.3.1) Alamofire/5.10.2"
    }
    
    data = {
        "grant_type": "client_credentials"
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception as e:
        logger.error(f"Errore nell'ottenere il token di accesso: {str(e)}")
        return None

def update_device_token(access_token):
    """Update device token."""
    url = f"{BASE_URL}/salute/1.0/notifiche/dispositivo/ct6U4eGiTUfJlh-8la_XTW%3AAPA91bGpiDbgIPrQ4HRF6xB2TembPIAtwywCde0hsMEplYm9DLxaws-bUokiv3bwcLyMrYI3ZyKEj6_Gi8FT4jY2w-8-ajUJeH-qdVRFHWdUgLZvYg-ZxVk"
    
    headers = {
        "Accept-Encoding": "application/json; charset=utf-8",
        "Accept-Language": "it-IT;q=1.0",
        "User-Agent": "RLGEOAPP/2.2.0 (it.laziocrea.rlgeoapp; build:2.2.0; iOS 18.3.1) Alamofire/5.10.2",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "token_new": "ct6U4eGiTUfJlh-8la_XTW:APA91bGpiDbgIPrQ4HRF6xB2TembPIAtwywCde0hsMEplYm9DLxaws-bUokiv3bwcLyMrYI3ZyKEj6_Gi8FT4jY2w-8-ajUJeH-qdVRFHWdUgLZvYg-ZxVk"
    }
    
    try:
        response = requests.put(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'aggiornare il token del dispositivo: {str(e)}")
        return None

def get_patient_info(fiscal_code):
    """Retrieve patient information."""
    url = f"{BASE_URL}/api/v3/system-apis/patients"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "fiscalCode": fiscal_code
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere informazioni sul paziente {fiscal_code}: {str(e)}")
        return None

def get_doctor_info(fiscal_code):
    """Get doctor information."""
    url = f"{BASE_URL}/api/v4/experience-apis/doctors/bpx"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0",
        "Content-Type": "application/json"
    }
    
    data = {
        "personIdentifier": fiscal_code
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere le informazioni del medico per {fiscal_code}: {str(e)}")
        return None

def check_prescription(patient_id, nre):
    """Check prescription details."""
    url = f"{BASE_URL}/api/v3/experience-apis/citizens/prescriptions/check-prescription"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "patientId": patient_id,
        "nre": nre
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nel controllare la prescrizione {nre}: {str(e)}")
        return None

def get_prescription_details(patient_id, nre):
    """Get full prescription details."""
    url = f"{BASE_URL}/api/v3/system-apis/prescriptions/{nre}"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "patientId": patient_id
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere i dettagli della prescrizione {nre}: {str(e)}")
        return None

def get_availabilities(patient_id, process_id, nre, order_ids):
    """Get medical service availabilities."""
    url = f"{BASE_URL}/api/v3/experience-apis/citizens/availabilities"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "personId": patient_id,
        "processId": process_id,
        "nre": nre,
        "orderIds": order_ids,
        "prescriptionPriority": "P",
        "firstBy": "hospital-best-10"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere le disponibilità per {nre}: {str(e)}")
        return None

def send_telegram_message(message, chat_id=None):
    """Send a message to Telegram with comprehensive error handling and debugging."""
    # Default chat ID if not provided
    DEFAULT_CHAT_ID = "YOUR_DEFAULT_CHAT_ID"
    target_chat_id = chat_id or DEFAULT_CHAT_ID
    
    # Validate message and chat_id
    if not message:
        logger.error("Empty message. Cannot send Telegram notification")
        return False
    
    if not target_chat_id:
        logger.error("No chat ID provided for Telegram notification")
        return False
    
    # Clean up the message
    try:
        # Remove invalid XML characters
        def remove_invalid_xml_chars(text):
            # Remove control characters except newline and tab
            return ''.join(char for char in text if char.isprintable() or char in '\n\t')
        
        message = remove_invalid_xml_chars(message)
        
        # Truncate very long messages to prevent Telegram API errors
        MAX_MESSAGE_LENGTH = 4096
        if len(message) > MAX_MESSAGE_LENGTH:
            logger.warning(f"Message too long. Truncating from {len(message)} to {MAX_MESSAGE_LENGTH} characters")
            message = message[:MAX_MESSAGE_LENGTH] + "... [Message truncated]"
    except Exception as clean_error:
        logger.error(f"Error cleaning message: {clean_error}")
        return False
    
    # Prepare Telegram API request
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": target_chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        # Send the message with a timeout
        response = requests.post(url, data=data, timeout=10)
        
        # Detailed error handling for various scenarios
        if response.status_code == 400:
            error_details = response.json().get('description', 'Unknown error')
            logger.error(f"Telegram API Bad Request: {error_details}")
            
            # Specific error handling
            if "message is too long" in error_details.lower():
                logger.warning("Message exceeds Telegram's length limit")
                data['text'] = message[:3900] + "... [Message truncated due to length]"
                response = requests.post(url, data=data, timeout=10)
            
            # Invalid HTML parsing
            elif "can't parse entities" in error_details.lower():
                logger.warning("HTML parsing error. Removing HTML formatting.")
                data['parse_mode'] = None
                response = requests.post(url, data=data, timeout=10)
        
        # Raise an exception for non-200 status codes
        response.raise_for_status()
        
        logger.info(f"Telegram message sent successfully to {target_chat_id}")
        return True
    
    except requests.exceptions.Timeout:
        logger.error(f"Telegram message send timed out for chat {target_chat_id}")
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error sending Telegram message: {http_err}")
        # Log full response for debugging
        try:
            logger.error(f"Response content: {http_err.response.text}")
        except:
            pass
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Error sending Telegram message to {target_chat_id}: {req_err}")
    except Exception as e:
        logger.error(f"Unexpected error in Telegram message sending: {e}")
    
    return False

def load_input_data():
    """Load prescription data from input file."""
    try:
            
        with open(INPUT_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Errore nel caricare i dati di input: {str(e)}")
        return []

def load_previous_data():
    """Load previous availability data."""
    try:
        if os.path.exists(PREVIOUS_DATA_FILE):
            with open(PREVIOUS_DATA_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Errore nel caricare i dati precedenti: {str(e)}")
        return {}

def save_previous_data(data):
    """Save current availability data for future comparison."""
    try:
        with open(PREVIOUS_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info("Dati precedenti salvati con successo")
    except Exception as e:
        logger.error(f"Errore nel salvare i dati precedenti: {str(e)}")
        
def is_similar_datetime(date1_str, date2_str, minutes_threshold=30):
    """Controlla se due date sono simili entro un certo numero di minuti."""
    try:
        dt1 = datetime.strptime(date1_str, "%Y-%m-%dT%H:%M:%SZ")
        dt2 = datetime.strptime(date2_str, "%Y-%m-%dT%H:%M:%SZ")
        
        # Calcoliamo la differenza in minuti
        diff_minutes = abs((dt2 - dt1).total_seconds() / 60)
        
        # Stessa data (giorno, mese, anno)?
        same_day = (dt1.year == dt2.year and dt1.month == dt2.month and dt1.day == dt2.day)
        
        # Se è lo stesso giorno e la differenza è entro la soglia
        return same_day and diff_minutes <= minutes_threshold
    except Exception:
        return False

def compare_availabilities(previous, current, fiscal_code, nre, prescription_name="", config=None):
    """Compare previous and current availabilities with configuration per prescrizione."""
    # Configurazione predefinita se non specificata
    default_config = {
        "only_new_dates": True,
        "notify_removed": False,
        "min_changes_to_notify": 2,
        "time_threshold_minutes": 60,
        "show_all_current": True  # Nuovo parametro per mostrare tutte le disponibilità attuali
    }
    
    # Usa la configurazione fornita o quella predefinita
    if config is None:
        config = default_config
    else:
        # Assicuriamoci che show_all_current sia impostato (default a True se non specificato)
        if "show_all_current" not in config:
            config["show_all_current"] = True
    
    # Se è la prima volta che controlliamo questa prescrizione
    if not previous or not current:
        # Se non c'erano dati precedenti, consideriamo tutto come nuovo ma non spammiamo
        if not previous and len(current) > 0:
            # Creiamo un messaggio iniziale con un riassunto
            message = f"<code>{fiscal_code}</code> - <code> {nre}</code>\n"
            if prescription_name:
                message += f"<code>{prescription_name}</code>\n\n"
            else:
                message += "\n"
            
            message += f"🔔 <b>Prima scansione completata</b>\n\n"
            message += f"<b>Trovate {len(current)} disponibilità</b>\n\n"
            
            # Mostriamo tutte le disponibilità ordinate per data
            sorted_availabilities = sorted(current, key=lambda x: x['date'])
            
            # Raggruppiamo per ospedale
            hospitals = {}
            for avail in sorted_availabilities:
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals:
                    hospitals[hospital_name] = []
                hospitals[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals.items():
                message += f"• <b>{hospital_name}</b>\n"
                message += f"  📍 {availabilities[0]['site']['address']}\n"
                
                for avail in availabilities:
                    message += f"  📅 {format_date(avail['date'])} - {avail['price']} €\n"
                
                message += "\n"
            
            return message
        return None

    # Otteniamo i valori di configurazione
    only_new_dates = config.get("only_new_dates", True)
    notify_removed = config.get("notify_removed", False)
    min_changes = config.get("min_changes_to_notify", 2)
    time_threshold = config.get("time_threshold_minutes", 60)
    show_all_current = config.get("show_all_current", True)
    
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
    for a in previous:
        hospital_id = a['hospital'].get('id', 'unknown')
        if hospital_id not in prev_by_hospital:
            prev_by_hospital[hospital_id] = []
        prev_by_hospital[hospital_id].append(a)
    
    for a in current:
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
        # Prima riga: codici e nome prescrizione in formato copiabile senza altre formattazioni
        message = f"<code>{fiscal_code}</code> - </code>{nre}</code>\n"
        if prescription_name:
            message += f"<code>{prescription_name}</code>\n\n"
        else:
            message += "\n"
        
        # Intestazione del messaggio
        if only_new_dates:
            message += f"🔔 <b>Nuove disponibilità ({len(changes['new'])})</b>\n\n"
        else:
            message += f"🔔 <b>Aggiornamento disponibilità ({total_changes} cambiamenti)</b>\n\n"
        
        # Mostriamo solo le nuove disponibilità se only_new_dates è True
        if changes["new"]:
            if not only_new_dates:
                message += f"<b>✅ {len(changes['new'])} Nuove disponibilità:</b>\n"
            
            # Raggruppiamo per ospedale
            hospitals_new = {}
            for avail in changes["new"]:
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals_new:
                    hospitals_new[hospital_name] = []
                hospitals_new[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals_new.items():
                message += f"\n• <b>{hospital_name}</b>\n"
                message += f"  📍 {availabilities[0]['site']['address']}\n"
                
                # Ordiniamo le date
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                # Mostriamo tutte le date
                for avail in sorted_availabilities:
                    message += f"  📅 {format_date(avail['date'])} - {avail['price']} €\n"
                
                message += "\n"
        
        # Mostriamo le disponibilità rimosse solo se notify_removed è True
        if notify_removed and changes["removed"]:
            message += f"<b>❌ {len(changes['removed'])} Disponibilità rimosse:</b>\n"
            # Raggruppiamo per ospedale
            hospitals_removed = {}
            for avail in changes["removed"]:
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals_removed:
                    hospitals_removed[hospital_name] = []
                hospitals_removed[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals_removed.items():
                message += f"\n• <b>{hospital_name}</b>\n"
                message += f"  📍 {availabilities[0]['site']['address']}\n"
                
                # Ordiniamo le date
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                # Mostriamo tutte le date
                for avail in sorted_availabilities:
                    message += f"  📅 {format_date(avail['date'])}\n"
                
                message += "\n"
        
        # Mostriamo i cambiamenti di prezzo solo se only_new_dates è False
        if not only_new_dates and changes["changed"]:
            message += f"<b>🔄 {len(changes['changed'])} Disponibilità con prezzi modificati:</b>\n"
            # Raggruppiamo per ospedale
            hospitals_changed = {}
            for change in changes["changed"]:
                hospital_name = change['current']['hospital']['name']
                if hospital_name not in hospitals_changed:
                    hospitals_changed[hospital_name] = []
                hospitals_changed[hospital_name].append(change)
            
            # Mostriamo per ospedale
            for hospital_name, changes_list in hospitals_changed.items():
                message += f"\n• <b>{hospital_name}</b>\n"
                message += f"  📍 {changes_list[0]['current']['site']['address']}\n"
                
                # Ordiniamo le date
                sorted_changes = sorted(changes_list, key=lambda x: x['current']['date'])
                
                # Mostriamo tutte le date
                for change in sorted_changes:
                    message += f"  📅 {format_date(change['current']['date'])}: {change['previous']['price']} € → {change['current']['price']} €\n"
                
                message += "\n"
        
        # Aggiungiamo tutte le disponibilità attuali se show_all_current è True
        if show_all_current and current:
            message += f"\n<b>📋 Tutte le disponibilità attuali ({len(current)}):</b>\n\n"
            
            # Raggruppiamo per ospedale
            hospitals = {}
            for avail in current:
                hospital_name = avail['hospital']['name']
                if hospital_name not in hospitals:
                    hospitals[hospital_name] = []
                hospitals[hospital_name].append(avail)
            
            # Mostriamo per ospedale
            for hospital_name, availabilities in hospitals.items():
                message += f"• <b>{hospital_name}</b>\n"
                message += f"  📍 {availabilities[0]['site']['address']}\n"
                
                # Ordiniamo le date
                sorted_availabilities = sorted(availabilities, key=lambda x: x['date'])
                
                # Mostriamo tutte le date
                for avail in sorted_availabilities:
                    message += f"  📅 {format_date(avail['date'])} - {avail['price']} €\n"
                
                message += "\n"
        
        return message
    
    return None

def process_data_and_notify(fiscal_code, nre, previous_data, current_data, prescription_name):
    """Processa i dati e notifica solo se ci sono cambiamenti significativi."""
    changes_message = compare_availabilities(
        previous_data, 
        current_data,
        fiscal_code,
        nre,
        prescription_name
    )
    
    if changes_message:
        logger.info(f"Rilevati cambiamenti significativi per {fiscal_code}_{nre}")
        send_telegram_message(changes_message)
    else:
        logger.info(f"Nessun cambiamento significativo rilevato per {fiscal_code}_{nre}")

def process_prescription(prescription, previous_data):
    """Process a single prescription and check for availability changes."""
    fiscal_code = prescription["fiscal_code"]
    nre = prescription["nre"]
    prescription_key = f"{fiscal_code}_{nre}"
    
    # Otteniamo la configurazione specifica per questa prescrizione
    config = prescription.get("config", {})
    
    # Otteniamo l'ID chat Telegram specifico per questa prescrizione, se presente
    telegram_chat_id = prescription.get("telegram_chat_id")
    
    logger.info(f"Elaborazione prescrizione {prescription_key}")
    
    # Step 1: Get access token
    access_token = get_access_token()
    if not access_token:
        return
    
    # Step 2: Update device token
    update_device_token(access_token)
    
    # Step 3: Get patient information
    patient_info = get_patient_info(fiscal_code)
    if not patient_info or 'content' not in patient_info or not patient_info['content']:
        logger.error(f"Impossibile trovare informazioni per il paziente {fiscal_code}")
        return
    
    patient_id = patient_info['content'][0]['id']
    
    # Step 4: Get doctor information
    doctor_info = get_doctor_info(fiscal_code)
    if not doctor_info or 'id' not in doctor_info:
        logger.error(f"Impossibile trovare informazioni per il medico del paziente {fiscal_code}")
        return
    
    process_id = doctor_info['id']
    
    # Step 5: Check prescription
    check_prescription_result = check_prescription(patient_id, nre)
    if not check_prescription_result:
        logger.error(f"Impossibile verificare la prescrizione {nre}")
        return
    
    # Step 6: Get prescription details
    prescription_details = get_prescription_details(patient_id, nre)
    if not prescription_details or 'details' not in prescription_details or not prescription_details['details']:
        logger.error(f"Impossibile ottenere i dettagli della prescrizione {nre}")
        return
    
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
    
    # Step 7: Get availabilities
    availabilities = get_availabilities(patient_id, process_id, nre, order_ids)
    if not availabilities or 'content' not in availabilities:
        logger.error(f"Impossibile ottenere le disponibilità per {nre}")
        return
    
    current_availabilities = availabilities['content']
    
    # Compare with previous data to detect changes
    previous_availabilities = previous_data.get(prescription_key, [])
    
    # Confronta e genera un messaggio se ci sono cambiamenti significativi
    changes_message = compare_availabilities(
        previous_availabilities, 
        current_availabilities,
        fiscal_code,
        nre,
        prescription_name,
        config
    )
    
    # Se ci sono cambiamenti, invia una notifica
    if changes_message:
        logger.info(f"Rilevati cambiamenti significativi per {prescription_key}")
        
        # Invia al chat ID specifico se presente, altrimenti usa quello predefinito
        send_telegram_message(changes_message, telegram_chat_id)
        
        # Log se è stato utilizzato un chat ID specifico
        if telegram_chat_id:
            logger.info(f"Notifica inviata al chat ID specifico: {telegram_chat_id}")
    else:
        logger.info(f"Nessun cambiamento significativo rilevato per {prescription_key}")
    
    # Update previous data for next comparison
    previous_data[prescription_key] = current_availabilities

def monitor_service():
    """Main monitoring service function."""
    logger.info("Avvio del servizio di monitoraggio")
    
    # Load previous data
    previous_data = load_previous_data()
    
    try:
        while True:
            start_time = time.time()
            logger.info(f"Inizio ciclo di monitoraggio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Load input data
            prescriptions = load_input_data()
            
            # Process each prescription
            for prescription in prescriptions:
                process_prescription(prescription, previous_data)
                # Small delay between processing different prescriptions
                time.sleep(1)
            
            # Save updated previous data
            save_previous_data(previous_data)
            
            # Calculate time to sleep to maintain 5-minute cycles
            elapsed = time.time() - start_time
            sleep_time = max(300 - elapsed, 1)  # 300 seconds = 5 minutes
            
            logger.info(f"Ciclo completato in {elapsed:.2f} secondi. In attesa del prossimo ciclo tra {sleep_time:.2f} secondi.")
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        logger.info("Servizio interrotto dall'utente")
    except Exception as e:
        logger.error(f"Errore nel servizio di monitoraggio: {str(e)}")
        # In caso di errore, aspetta 1 minuto e riprova
        time.sleep(60)
        monitor_service()  # Riavvia il servizio

if __name__ == "__main__":
    monitor_service()
