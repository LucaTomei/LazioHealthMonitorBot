import os
import json
import logging
from datetime import datetime, timedelta
import fcntl

# Importa costanti e configurazioni dal modulo config
from config import (
    logger, INPUT_FILE, PREVIOUS_DATA_FILE, USERS_FILE,
    authorized_users
)

def load_authorized_users_with_lock():
    """Carica gli utenti autorizzati dal file con lock."""
    global authorized_users
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                # Acquisiamo un lock condiviso per la lettura
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    loaded_users = json.load(f)
                    if loaded_users:
                        authorized_users.clear()
                        authorized_users.extend(loaded_users)
                        logger.info(f"Caricati {len(authorized_users)} utenti autorizzati")
                finally:
                    # Rilasciamo il lock
                    fcntl.flock(f, fcntl.LOCK_UN)
        else:
            # Se il file non esiste, lo creiamo
            with open(USERS_FILE, 'w') as f:
                # Acquisiamo un lock esclusivo per la scrittura
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    json.dump(authorized_users, f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            logger.info("Creato nuovo file di utenti autorizzati")
    except Exception as e:
        logger.error(f"Errore nel caricare gli utenti autorizzati: {str(e)}")

def save_authorized_users_with_lock():
    """Salva gli utenti autorizzati su file con lock."""
    try:
        with open(USERS_FILE, 'w') as f:
            # Acquisiamo un lock esclusivo
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(authorized_users, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        logger.info("Utenti autorizzati salvati con successo")
    except Exception as e:
        logger.error(f"Errore nel salvare gli utenti autorizzati: {str(e)}")

def load_authorized_users():
    """Carica gli utenti autorizzati dal file."""
    global authorized_users
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                loaded_users = json.load(f)
                if loaded_users:  # Verifichiamo che il file contenga utenti
                    authorized_users.clear()  # Solo se abbiamo caricato utenti validi
                    authorized_users.extend(loaded_users)
                    logger.info(f"Caricati {len(authorized_users)} utenti autorizzati")
                else:
                    logger.warning("File utenti autorizzati vuoto, mantengo utenti esistenti")
        else:
            # Se il file non esiste, lo creiamo con gli utenti attuali (se presenti)
            with open(USERS_FILE, 'w') as f:
                json.dump(authorized_users, f)
            logger.info(f"Creato nuovo file con {len(authorized_users)} utenti autorizzati")
    except Exception as e:
        logger.error(f"Errore nel caricare gli utenti autorizzati: {str(e)}")

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

def is_date_within_range(date_str, months_limit=None):
    """
    Verifica se una data è compresa nell'intervallo di oggi fino a X mesi.
    
    Args:
        date_str: La data in formato ISO da verificare
        months_limit: Il numero di mesi limite. Se None, non c'è limite
    
    Returns:
        bool: True se la data è nell'intervallo, False altrimenti
    """
    if months_limit is None:
        return True  # Nessun limite impostato
    
    try:
        # Convertiamo la data da verificare
        date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        
        # Data di oggi e limite
        today = datetime.now()
        limit_date = today + timedelta(days=30 * months_limit)
        
        # Verifichiamo che la data sia successiva a oggi e entro il limite
        return today <= date <= limit_date
    except Exception as e:
        logger.warning(f"Errore nel verificare l'intervallo di date: {str(e)}")
        return True  # In caso di errore, non filtriamo la data

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