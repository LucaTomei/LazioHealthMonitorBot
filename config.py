import os
import logging
from logging.handlers import RotatingFileHandler
from telegram import ReplyKeyboardMarkup

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
TELEGRAM_TOKEN = ""

# Percorso del file di input e dati precedenti
INPUT_FILE = "input_prescriptions.json"
PREVIOUS_DATA_FILE = "previous_data.json"
USERS_FILE = "authorized_users.json"

# Stati per la conversazione
(WAITING_FOR_FISCAL_CODE, WAITING_FOR_NRE, CONFIRM_ADD, 
 WAITING_FOR_PRESCRIPTION_TO_DELETE, WAITING_FOR_PRESCRIPTION_TO_TOGGLE,
 WAITING_FOR_DATE_FILTER, WAITING_FOR_MONTHS_LIMIT, CONFIRM_DATE_FILTER,
 WAITING_FOR_BOOKING_CHOICE, WAITING_FOR_BOOKING_CONFIRMATION, WAITING_FOR_PHONE,
 WAITING_FOR_EMAIL, WAITING_FOR_SLOT_CHOICE, WAITING_FOR_BOOKING_TO_CANCEL,
 WAITING_FOR_AUTO_BOOK_CHOICE, AUTHORIZING) = range(16)  

# Lista di utenti autorizzati
authorized_users = []

# Dizionario per tenere traccia delle conversazioni in corso
user_data = {}

# Definizione della tastiera principale come variabile globale
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    ["➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione"],
    ["📋 Lista Prescrizioni", "🔄 Verifica Disponibilità"],
    ["🔔 Gestisci Notifiche", "⏱ Imposta Filtro Date"],
    ["🏥 Prenota", "🤖 Prenota Automaticamente"],
    ["🚫 Blacklist Ospedali", "📝 Le mie Prenotazioni"],
    ["ℹ️ Informazioni", "🔑 Autorizza Utente"]
], resize_keyboard=True)
