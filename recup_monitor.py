import requests
import base64
import json
import time
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import threading
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

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
TELEGRAM_TOKEN = "761659safdssdfafdsafdawe-2Jy-GrWnFWJ8"

# Percorso del file di input e dati precedenti
INPUT_FILE = "input_prescriptions.json"
PREVIOUS_DATA_FILE = "previous_data.json"
USERS_FILE = "authorized_users.json"

# Stati per la conversazione
WAITING_FOR_FISCAL_CODE, WAITING_FOR_NRE, CONFIRM_ADD, WAITING_FOR_PRESCRIPTION_TO_DELETE = range(4)

# Dizionario per tenere traccia delle conversazioni in corso
user_data = {}

# Lista di utenti autorizzati
authorized_users = []

def load_authorized_users():
    """Carica gli utenti autorizzati dal file."""
    global authorized_users
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                authorized_users = json.load(f)
            logger.info(f"Caricati {len(authorized_users)} utenti autorizzati")
        else:
            # Se il file non esiste, lo creiamo con un array vuoto
            with open(USERS_FILE, 'w') as f:
                json.dump([], f)
            logger.info("Creato nuovo file di utenti autorizzati")
    except Exception as e:
        logger.error(f"Errore nel caricare gli utenti autorizzati: {str(e)}")
        authorized_users = []

def save_authorized_users():
    """Salva gli utenti autorizzati su file."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(authorized_users, f, indent=2)
        logger.info("Utenti autorizzati salvati con successo")
    except Exception as e:
        logger.error(f"Errore nel salvare gli utenti autorizzati: {str(e)}")

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
    # Questa funzione può fallire senza compromettere il funzionamento principale
    try:
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
        
        response = requests.put(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Avviso: impossibile aggiornare il token del dispositivo: {str(e)}")
        # Continuiamo comunque l'esecuzione
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

def load_input_data():
    """Load prescription data from input file."""
    try:
        if os.path.exists(INPUT_FILE):
            with open(INPUT_FILE, 'r') as f:
                return json.load(f)
        # Se il file non esiste, lo creiamo con un array vuoto
        with open(INPUT_FILE, 'w') as f:
            json.dump([], f)
        logger.info("Creato nuovo file di prescrizioni")
        return []
    except Exception as e:
        logger.error(f"Errore nel caricare i dati di input: {str(e)}")
        return []

def save_input_data(data):
    """Salva i dati delle prescrizioni su file con diagnostica migliorata."""
    try:
        file_path = os.path.abspath(INPUT_FILE)
        logger.info(f"Tentativo di salvare i dati delle prescrizioni in: {file_path}")
        
        # Verifica se la directory esiste
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Salva con indentazione per leggibilità
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Verifica che il file esista dopo il salvataggio
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"Dati delle prescrizioni salvati con successo ({file_size} bytes)")
            
            # Leggi il file per verificare il contenuto
            with open(file_path, 'r') as f:
                content = json.load(f)
                logger.info(f"Verificato il contenuto: {len(content)} prescrizioni")
        else:
            logger.error(f"Il file {file_path} non esiste dopo il salvataggio")
    except Exception as e:
        logger.error(f"Errore nel salvare i dati delle prescrizioni: {str(e)}")
        
        # Tentativo di recupero
        try:
            # Prova a salvare in una posizione alternativa
            alt_path = os.path.join(os.path.expanduser("~"), "recup_prescriptions.json")
            logger.info(f"Tentativo di salvare in posizione alternativa: {alt_path}")
            
            with open(alt_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            logger.info(f"Dati salvati nella posizione alternativa: {alt_path}")
            logger.info(f"Modifica la variabile INPUT_FILE nel codice: {alt_path}")
        except Exception as alt_e:
            logger.error(f"Anche il salvataggio alternativo è fallito: {str(alt_e)}")

def load_previous_data():
    """Load previous availability data."""
    try:
        if os.path.exists(PREVIOUS_DATA_FILE):
            with open(PREVIOUS_DATA_FILE, 'r') as f:
                return json.load(f)
        # Se il file non esiste, lo creiamo con un dizionario vuoto
        with open(PREVIOUS_DATA_FILE, 'w') as f:
            json.dump({}, f)
        logger.info("Creato nuovo file di dati precedenti")
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
            # Preparazione del messaggio con formattazione HTML migliorata
            message = f"""
<b>🔍 Nuova Prescrizione</b>

<b>Codice Fiscale:</b> <code>{fiscal_code}</code>
<b>NRE:</b> <code>{nre}</code>
<b>Descrizione:</b> <code>{prescription_name}</code>

📋 <b>Disponibilità Trovate:</b> {len(current)}
"""
            
            # Raggruppiamo per ospedale
            hospitals = {}
            for avail in sorted(current, key=lambda x: x['date']):
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
        # Preparazione del messaggio con formattazione HTML migliorata
        message = f"""
<b>🔍 Aggiornamento Prescrizione</b>

<b>Codice Fiscale:</b> <code>{fiscal_code}</code>
<b>NRE:</b> <code>{nre}</code>
<b>Descrizione:</b> <code>{prescription_name}</code>
"""
        
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
        if show_all_current and current:
            message += f"\n📋 <b>Tutte le Disponibilità:</b> {len(current)}\n"
            
            hospitals = {}
            for avail in current:
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
        error_msg = f"Impossibile ottenere le disponibilità per {nre}"
        logger.error(error_msg)
        return False, error_msg
    
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
        logger.info(f"Nessun cambiamento significativo rilevato per {prescription_key}")
    
    # Update previous data for next comparison
    previous_data[prescription_key] = current_availabilities
    
    return True, prescription_name

async def start_monitoring():
    """Avvia il thread di monitoraggio delle prescrizioni."""
    # Load previous data
    previous_data = load_previous_data()
    
    while True:
        try:
            start_time = time.time()
            logger.info(f"Inizio ciclo di monitoraggio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Load input data
            prescriptions = load_input_data()
            
            # Process each prescription
            for prescription in prescriptions:
                process_prescription(prescription, previous_data)
                # Small delay between processing different prescriptions
                await asyncio.sleep(1)
            
            # Save updated previous data
            save_previous_data(previous_data)
            
            # Calculate time to sleep to maintain 5-minute cycles
            elapsed = time.time() - start_time
            sleep_time = max(300 - elapsed, 1)  # 300 seconds = 5 minutes
            
            logger.info(f"Ciclo completato in {elapsed:.2f} secondi. In attesa del prossimo ciclo tra {sleep_time:.2f} secondi.")
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Errore nel servizio di monitoraggio: {str(e)}")
            # In caso di errore, aspetta 1 minuto e riprova
            await asyncio.sleep(60)

# Funzioni per il bot Telegram

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
    
    # Creiamo una tastiera personalizzata
    keyboard = [
        ["➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione"],
        ["📋 Lista Prescrizioni", "🔄 Verifica Disponibilità"],
        ["ℹ️ Informazioni", "🔑 Autorizza Utente"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"👋 Benvenuto, {update.effective_user.first_name}!\n\n"
        "Questo bot ti aiuterà a monitorare le disponibilità del Servizio Sanitario Nazionale.\n\n"
        "Utilizza i pulsanti sotto per gestire le prescrizioni da monitorare.",
        reply_markup=reply_markup
    )

# Nelle funzioni di conversazione, aggiungi una tastiera con il pulsante Annulla
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

# Funzione per gestire l'annullamento
async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulla l'operazione corrente e torna al menu principale."""
    user_id = update.effective_user.id
    
    # Puliamo i dati dell'utente
    if user_id in user_data:
        user_data.pop(user_id, None)
    
    # Ripristiniamo la tastiera principale
    main_keyboard = ReplyKeyboardMarkup([
        ["➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione"],
        ["📋 Lista Prescrizioni", "🔄 Verifica Disponibilità"],
        ["ℹ️ Informazioni", "🔑 Autorizza Utente"]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "❌ Operazione annullata. Cosa vuoi fare?",
        reply_markup=main_keyboard
    )
    
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
    
    # Prepariamo la conferma
    await update.message.reply_text(
        f"Stai per aggiungere una nuova prescrizione con i seguenti dati:\n\n"
        f"Codice Fiscale: {fiscal_code}\n"
        f"NRE: {nre}\n\n"
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
    
    # Carichiamo le prescrizioni esistenti
    prescriptions = load_input_data()
    
    # Creiamo la nuova prescrizione
    new_prescription = {
        "fiscal_code": fiscal_code,
        "nre": nre,
        "telegram_chat_id": user_id,
        "config": {
            "only_new_dates": True,
            "notify_removed": False,
            "min_changes_to_notify": 1,
            "time_threshold_minutes": 60,
            "show_all_current": True
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
    
    # Verifica subito che il salvataggio abbia funzionato
    try:
        test_prescriptions = load_input_data()
        logger.info(f"Verifica dopo il salvataggio: {len(test_prescriptions)} prescrizioni presenti")
    except Exception as e:
        logger.error(f"Errore nel verificare il salvataggio: {str(e)}")
    save_previous_data(previous_data)
    
    # Aggiorniamo il messaggio
    await query.edit_message_text(
        f"✅ Prescrizione aggiunta con successo!\n\n"
        f"Descrizione: {new_prescription.get('description', 'Non disponibile')}\n"
        f"Codice Fiscale: {fiscal_code}\n"
        f"NRE: {nre}\n\n"
        f"Riceverai notifiche quando saranno disponibili nuovi appuntamenti."
    )
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
    return ConversationHandler.END

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
        
        # Aggiungiamo informazioni sull'utente se l'admin sta visualizzando
        user_info = ""
        if is_admin and "telegram_chat_id" in prescription:
            user_info = f" (User ID: {prescription['telegram_chat_id']})"
        
        message += f"{idx+1}. <b>{desc}</b>{user_info}\n"
        message += f"   Codice Fiscale: <code>{fiscal_code}</code>\n"
        message += f"   NRE: <code>{nre}</code>\n\n"
    
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

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra informazioni sul bot."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        await update.message.reply_text("🔒 Non sei autorizzato ad utilizzare questa funzione.")
        return
    
    await update.message.reply_text(
        "ℹ️ <b>Informazioni sul Bot</b>\n\n"
        "Questo bot monitora le disponibilità del Servizio Sanitario Nazionale (SSN) per le prescrizioni mediche e ti notifica quando ci sono nuove disponibilità.\n\n"
        "<b>Comandi principali:</b>\n"
        "➕ <b>Aggiungi Prescrizione</b> - Monitora una nuova prescrizione\n"
        "➖ <b>Rimuovi Prescrizione</b> - Smetti di monitorare una prescrizione\n"
        "📋 <b>Lista Prescrizioni</b> - Visualizza le prescrizioni monitorate\n"
        "🔄 <b>Verifica Disponibilità</b> - Controlla subito le disponibilità\n\n"
        "<b>Frequenza di controllo:</b> Ogni 5 minuti\n\n"
        "<b>Note:</b>\n"
        "• Il bot notifica solo quando ci sono cambiamenti significativi\n"
        "• Le disponibilità possono variare rapidamente, è consigliabile prenotare il prima possibile\n"
        "• Per problemi o assistenza, contatta l'amministratore",
        parse_mode="HTML"
    )

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
    
    # Chiediamo l'ID dell'utente da autorizzare
    await update.message.reply_text(
        "Per autorizzare un nuovo utente, invia il suo ID Telegram.\n\n"
        "L'utente può ottenere il proprio ID usando @userinfobot o altri bot simili."
    )

async def handle_auth_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'inserimento dell'ID utente da autorizzare."""
    user_id = update.effective_user.id
    
    # Controlliamo se l'utente sta effettivamente autorizzando qualcuno
    if user_id not in user_data or user_data[user_id].get("action") != "authorizing_user":
        return
    
    # Otteniamo l'ID dell'utente da autorizzare
    new_user_id = update.message.text.strip()
    
    # Controlliamo se è un ID valido
    if not new_user_id.isdigit():
        await update.message.reply_text("⚠️ L'ID utente deve essere un numero.")
        return
    
    # Controlliamo se è già autorizzato
    if new_user_id in authorized_users:
        await update.message.reply_text(f"⚠️ L'utente {new_user_id} è già autorizzato.")
        user_data.pop(user_id, None)  # Puliamo i dati dell'utente
        return
    
    # Aggiungiamo l'utente alla lista degli autorizzati
    authorized_users.append(new_user_id)
    save_authorized_users()
    
    await update.message.reply_text(f"✅ Utente {new_user_id} autorizzato con successo!")
    
    # Puliamo i dati dell'utente
    user_data.pop(user_id, None)
    
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i messaggi di testo e i comandi dai pulsanti."""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Se l'utente sta cercando di autorizzare qualcuno, gestiamo questo caso speciale
    if user_id in user_data and user_data[user_id].get("action") == "authorizing_user":
        return await handle_auth_user_id(update, context)
    
    # Controlliamo se l'utente è autorizzato
    if str(user_id) not in authorized_users:
        # Se non ci sono utenti autorizzati, il primo utente diventa automaticamente amministratore
        if not authorized_users:
            authorized_users.append(str(user_id))
            save_authorized_users()
            logger.info(f"Primo utente {user_id} aggiunto come amministratore")
            
            # Inviamo un messaggio di benvenuto come amministratore
            keyboard = [
                ["➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione"],
                ["📋 Lista Prescrizioni", "🔄 Verifica Disponibilità"],
                ["ℹ️ Informazioni", "🔑 Autorizza Utente"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                f"👑 Benvenuto, {update.effective_user.first_name}!\n\n"
                "Sei stato impostato come amministratore del bot.\n\n"
                "Questo bot ti aiuterà a monitorare le disponibilità del Servizio Sanitario Nazionale.",
                reply_markup=reply_markup
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
    elif text == "ℹ️ Informazioni":
        return await show_info(update, context)
    elif text == "🔑 Autorizza Utente":
        return await authorize_user(update, context)
    else:
        # Messaggio di default
        await update.message.reply_text(
            "Usa i pulsanti sotto per interagire con il bot.",
            reply_markup=ReplyKeyboardMarkup([
                ["➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione"],
                ["📋 Lista Prescrizioni", "🔄 Verifica Disponibilità"],
                ["ℹ️ Informazioni", "🔑 Autorizza Utente"]
            ], resize_keyboard=True)
        )
async def error_handler(update, context):
    """Gestisce gli errori del bot."""
    logger.error(f"Errore nell'update {update}: {context.error}")
    
    # Informiamo l'utente dell'errore (se possibile)
    if update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Si è verificato un errore. Riprova più tardi o contatta l'amministratore."
        )

application = None  # Dichiarazione globale

# Modifica la funzione main()
def main():
    """Funzione principale che avvia il bot."""
    global application  # Importante! Usa la variabile globale
    
    # Carichiamo gli utenti autorizzati
    load_authorized_users()
    
    # Se non ci sono utenti autorizzati, aggiungiamo il primo utente che interagisce
    if not authorized_users:
        logger.warning("Nessun utente autorizzato trovato. Il primo utente a interagire diventerà amministratore.")
    
    # Creiamo l'applicazione
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
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
            CONFIRM_ADD: [
                CallbackQueryHandler(confirm_add_prescription)
            ],
            WAITING_FOR_PRESCRIPTION_TO_DELETE: [
                CallbackQueryHandler(handle_prescription_to_delete)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_operation),
            MessageHandler(filters.Regex("^❌ Annulla$"), cancel_operation)
        ]
    )
    
    # Aggiungiamo i gestori
    application.add_handler(conv_handler)
    
    # Gestore errori
    application.add_error_handler(error_handler)
    
    # Avviamo il thread di monitoraggio
    async def start_bot():
        # Avviamo il monitoraggio in background
        monitoring_task = asyncio.create_task(start_monitoring())
        
        # Avviamo il bot
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # Attendi che il monitoraggio termini (non dovrebbe mai succedere)
        await monitoring_task
    
    # Avviamo il bot
    try:
        # Verifichiamo se è già presente un ciclo di eventi
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        logger.info("Bot interrotto dall'utente")
    except Exception as e:
        logger.error(f"Errore nell'avvio del bot: {str(e)}")

if __name__ == "__main__":
    # Importazioni necessarie per asyncio
    import asyncio
    from telegram.ext import Application
    
    # Avviamo il bot
    main()