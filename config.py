import os
import logging
from logging.handlers import RotatingFileHandler
from telegram import ReplyKeyboardMarkup
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Configurazione del logging
log_folder = os.getenv("LOG_FOLDER", "logs")
os.makedirs(log_folder, exist_ok=True)

# Imposta il livello di logging dalla variabile d'ambiente
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

logging.basicConfig(
    level=log_level_map.get(log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # File handler con rotazione: max 1MB per file, massimo 5 file
        RotatingFileHandler(
            os.path.join(log_folder, "recup_monitor.log"), 
            maxBytes=1024*1024,  # 1MB
            backupCount=5        # Mantiene 5 file di backup
        ),
        logging.StreamHandler()  # Stampa anche sulla console
    ]
)
logger = logging.getLogger("RecupMonitor")

# Log info sul server (utile per multi-server setup)
SERVER_NAME = os.getenv("SERVER_NAME", "server1")
logger.info(f"Inizializzazione bot su server: {SERVER_NAME}")

# Base configuration - Usa variabili d'ambiente con fallback
BASE_URL = os.getenv("BASE_URL", "https://recup-webapi-appmobile.regione.lazio.it")
AUTH_HEADER = os.getenv("AUTH_HEADER", "Basic QVBQTU9CSUxFX1NQRUNJQUw6UGs3alVTcDgzbUh4VDU4NA==")

# Configurazione Telegram - CRITICO: deve essere in .env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_TOKEN:
    logger.error("ERRORE CRITICO: TELEGRAM_BOT_TOKEN non trovato nelle variabili d'ambiente!")
    logger.error("Crea un file .env con: TELEGRAM_BOT_TOKEN=your_token_here")
    raise ValueError("TELEGRAM_BOT_TOKEN non configurato! Controlla il file .env")

logger.info("Token Telegram caricato correttamente")

# Percorsi dei file - Configurabili via env
PDF_FOLDER = os.getenv("PDF_FOLDER", "prenotazioni_pdf")
REPORTS_FOLDER = os.getenv("REPORTS_FOLDER", "reports_pdf")
REPORTS_MONITORING_FILE = os.getenv("REPORTS_MONITORING_FILE", "reports_monitoring.json")
INPUT_FILE = os.getenv("INPUT_FILE", "input_prescriptions.json")
PREVIOUS_DATA_FILE = os.getenv("PREVIOUS_DATA_FILE", "previous_data.json")
USERS_FILE = os.getenv("USERS_FILE", "authorized_users.json")

# Crea le directory necessarie
os.makedirs(PDF_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)

# Impostazioni di monitoraggio
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # 5 minuti default
ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"

# Impostazioni avanzate
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

logger.info(f"Configurazione caricata:")
logger.info(f"  - Check interval: {CHECK_INTERVAL}s")
logger.info(f"  - Notifiche: {'Abilitate' if ENABLE_NOTIFICATIONS else 'Disabilitate'}")
logger.info(f"  - Debug mode: {'ON' if DEBUG_MODE else 'OFF'}")

# Stati per la conversazione
(WAITING_FOR_FISCAL_CODE, WAITING_FOR_NRE, CONFIRM_ADD, 
 WAITING_FOR_PRESCRIPTION_TO_DELETE, WAITING_FOR_PRESCRIPTION_TO_TOGGLE,
 WAITING_FOR_DATE_FILTER, WAITING_FOR_MONTHS_LIMIT, CONFIRM_DATE_FILTER,
 WAITING_FOR_BOOKING_CHOICE, WAITING_FOR_BOOKING_CONFIRMATION, WAITING_FOR_PHONE,
 WAITING_FOR_EMAIL, WAITING_FOR_SLOT_CHOICE, WAITING_FOR_BOOKING_TO_CANCEL,
 WAITING_FOR_AUTO_BOOK_CHOICE, AUTHORIZING, WAITING_FOR_PRESCRIPTION_BLACKLIST, 
 WAITING_FOR_HOSPITAL_SELECTION, WAITING_FOR_BROADCAST_MESSAGE,
 WAITING_FOR_BROADCAST_CONFIRMATION, WAITING_FOR_FISCAL_CODE_REPORT, 
 WAITING_FOR_PASSWORD_REPORT, WAITING_FOR_REPORT_CHOICE,
 WAITING_FOR_REPORTS_MONITORING_ACTION) = range(24)

# Lista di utenti autorizzati
authorized_users = []

# Dizionario per tenere traccia delle conversazioni in corso
user_data = {}

def is_admin(user_id: int, authorized_users: list) -> bool:
    """Verifica se l'utente è admin."""
    return bool(authorized_users) and user_id == int(authorized_users[0])

# Definizione della tastiera principale come variabile globale
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    ["➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione"],
    ["📋 Lista Prescrizioni", "🔄 Verifica Disponibilità"],
    ["🔔 Gestisci Notifiche", "⏱ Imposta Filtro Date"],
    ["🏥 Prenota", "🤖 Prenota Automaticamente"],
    ["🚫 Blacklist Ospedali", "📝 Le mie Prenotazioni"],
    ["📊 Configura Monitoraggio Referti", "📋 Gestisci Monitoraggi Referti"],
    ["ℹ️ Informazioni", "🔑 Autorizza Utente"]
], resize_keyboard=True)

ADMIN_KEYBOARD = ReplyKeyboardMarkup([
    ["➕ Aggiungi Prescrizione", "➖ Rimuovi Prescrizione"],
    ["📋 Lista Prescrizioni", "🔄 Verifica Disponibilità"],
    ["🔔 Gestisci Notifiche", "⏱ Imposta Filtro Date"],
    ["🚫 Blacklist Ospedali", "🏥 Prenota"],
    ["🤖 Prenota Automaticamente", "📝 Le mie Prenotazioni"],
    ["📊 Configura Monitoraggio Referti", "📋 Gestisci Monitoraggi Referti"],
    ["🔑 Autorizza Utente", "ℹ️ Informazioni"],
    ["📣 Messaggio Broadcast"]
], resize_keyboard=True)