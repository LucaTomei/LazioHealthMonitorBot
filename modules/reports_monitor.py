import json
import os
import logging
from datetime import datetime

from config import logger, REPORTS_MONITORING_FILE, authorized_users
from modules.reports_client import download_reports, download_report_document
from modules.bot_handlers import send_telegram_message

def load_reports_monitoring():
    """Carica i dati di monitoraggio dei referti dal file JSON."""
    try:
        if os.path.exists(REPORTS_MONITORING_FILE):
            with open(REPORTS_MONITORING_FILE, 'r') as f:
                return json.load(f)
        # Se il file non esiste, lo creiamo con un array vuoto
        with open(REPORTS_MONITORING_FILE, 'w') as f:
            json.dump([], f)
        logger.info("Creato nuovo file di monitoraggio referti")
        return []
    except Exception as e:
        logger.error(f"Errore nel caricare i dati di monitoraggio referti: {str(e)}")
        return []

def save_reports_monitoring(data):
    """Salva i dati di monitoraggio dei referti su file JSON."""
    try:
        file_path = os.path.abspath(REPORTS_MONITORING_FILE)
        logger.info(f"Tentativo di salvare i dati di monitoraggio referti in: {file_path}")
        
        # Verifica se la directory esiste
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Salva con indentazione per leggibilità
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Verifica che il file esista dopo il salvataggio
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"Dati di monitoraggio referti salvati con successo ({file_size} bytes)")
            
            # Leggi il file per verificare il contenuto
            with open(file_path, 'r') as f:
                content = json.load(f)
                logger.info(f"Verificato il contenuto: {len(content)} richieste di monitoraggio referti")
        else:
            logger.error(f"Il file {file_path} non esiste dopo il salvataggio")
    except Exception as e:
        logger.error(f"Errore nel salvare i dati di monitoraggio referti: {str(e)}")

def add_report_monitoring(fiscal_code, password, tscns, telegram_chat_id):
    """Aggiunge una nuova richiesta di monitoraggio referti."""
    # Carica i dati esistenti
    monitoring_data = load_reports_monitoring()
    
    # Verifica se esiste già un monitoraggio per questo codice fiscale
    existing_index = None
    for i, item in enumerate(monitoring_data):
        if item["fiscal_code"] == fiscal_code:
            existing_index = i
            break
    
    # Crea il nuovo elemento di monitoraggio
    new_monitoring = {
        "fiscal_code": fiscal_code,
        "password": password,
        "tscns": tscns,
        "telegram_chat_id": telegram_chat_id,
        "enabled": True,
        "last_check": None,
        "known_reports": [],  # Lista di ID referti già noti
        "added_at": datetime.now().isoformat()
    }
    
    # Aggiorna o aggiungi
    if existing_index is not None:
        monitoring_data[existing_index] = new_monitoring
        logger.info(f"Aggiornato monitoraggio referti per {fiscal_code}")
    else:
        monitoring_data.append(new_monitoring)
        logger.info(f"Aggiunto nuovo monitoraggio referti per {fiscal_code}")
    
    # Salva i dati aggiornati
    save_reports_monitoring(monitoring_data)
    return True

def remove_report_monitoring(fiscal_code):
    """Rimuove una richiesta di monitoraggio referti."""
    monitoring_data = load_reports_monitoring()
    
    # Filtra per rimuovere il monitoraggio specifico
    updated_data = [item for item in monitoring_data if item["fiscal_code"] != fiscal_code]
    
    # Se la lunghezza è cambiata, qualcosa è stato rimosso
    if len(updated_data) < len(monitoring_data):
        save_reports_monitoring(updated_data)
        logger.info(f"Rimosso monitoraggio referti per {fiscal_code}")
        return True
    else:
        logger.warning(f"Nessun monitoraggio referti trovato per {fiscal_code}")
        return False

def toggle_report_monitoring(fiscal_code, enabled=None):
    """Attiva o disattiva il monitoraggio per un codice fiscale specifico."""
    monitoring_data = load_reports_monitoring()
    
    # Cerca il monitoraggio specifico
    found = False
    for item in monitoring_data:
        if item["fiscal_code"] == fiscal_code:
            # Se enabled è None, inverte lo stato attuale
            if enabled is None:
                item["enabled"] = not item["enabled"]
            else:
                item["enabled"] = enabled
            found = True
            break
    
    if found:
        save_reports_monitoring(monitoring_data)
        logger.info(f"Aggiornato stato monitoraggio referti per {fiscal_code}: enabled={item['enabled']}")
        return True, item["enabled"]
    else:
        logger.warning(f"Nessun monitoraggio referti trovato per {fiscal_code}")
        return False, None

def check_new_reports():
    """
    Verifica la disponibilità di nuovi referti per tutti gli utenti monitorati.
    Questa funzione viene chiamata periodicamente dal processo di monitoraggio.
    """
    logger.info("Avvio controllo disponibilità nuovi referti")
    
    # Carica i dati di monitoraggio
    monitoring_data = load_reports_monitoring()
    
    if not monitoring_data:
        logger.info("Nessun monitoraggio referti configurato")
        return 0, 0, 0  # Ritorna i contatori anche quando non ci sono monitoraggi
    
    # Contatori per statistiche
    total_checked = 0
    total_notifications = 0
    errors = 0
    
    # Controlla ogni richiesta di monitoraggio
    for monitoring_item in monitoring_data:
        # Salta se disabilitato
        if not monitoring_item.get("enabled", True):
            continue
        
        fiscal_code = monitoring_item["fiscal_code"]
        password = monitoring_item["password"]
        tscns = monitoring_item["tscns"]
        chat_id = monitoring_item["telegram_chat_id"]
        known_reports = monitoring_item.get("known_reports", [])
        
        try:
            # Aggiorna il timestamp dell'ultimo controllo
            monitoring_item["last_check"] = datetime.now().isoformat()
            
            # Scarica la lista dei referti disponibili
            reports = download_reports(fiscal_code, password, tscns)
            
            if not reports:
                logger.warning(f"Nessun referto trovato per {fiscal_code} o errore nel download")
                errors += 1
                continue
            
            # Lista degli ID dei referti attuali
            current_report_ids = [report.get("document_id") for report in reports if report.get("document_id")]
            
            # Trova i nuovi referti (quelli che non sono nella lista known_reports)
            new_report_ids = [report_id for report_id in current_report_ids if report_id not in known_reports]
            
            # Se ci sono nuovi referti, invia una notifica
            if new_report_ids:
                logger.info(f"Trovati {len(new_report_ids)} nuovi referti per {fiscal_code}")
                
                # Filtra i report completi per i nuovi ID
                new_reports = [report for report in reports if report.get("document_id") in new_report_ids]
                
                # Costruisci il messaggio di notifica
                message = f"""
<b>🔔 Nuovi Referti Disponibili!</b>

<b>Codice Fiscale:</b> <code>{fiscal_code}</code>
<b>Nuovi referti:</b> {len(new_reports)}

<b>Elenco dei nuovi referti:</b>
"""
                
                for i, report in enumerate(new_reports):
                    provider = report.get("provider", "Struttura sconosciuta")
                    doc_type = report.get("document_type", "Referto")
                    doc_date = report.get("document_date", "Data sconosciuta")
                    
                    # Formattare la data se possibile
                    try:
                        date_obj = datetime.strptime(doc_date, "%Y%m%d")
                        formatted_date = date_obj.strftime("%d/%m/%Y")
                    except:
                        formatted_date = doc_date
                    
                    message += f"{i+1}. <b>{doc_type}</b> - {provider} ({formatted_date})\n"
                
                message += """
Usa il comando <b>📋 Gestisci Monitoraggi Referti</b> per scaricare i nuovi referti.
"""
                
                # Invia la notifica
                success = send_telegram_message(chat_id, message, "HTML")
                
                if success:
                    # Aggiorna la lista dei referti noti
                    monitoring_item["known_reports"] = current_report_ids
                    total_notifications += 1
                else:
                    logger.error(f"Errore nell'invio notifica per {fiscal_code}")
                    errors += 1
            
            total_checked += 1
            
        except Exception as e:
            logger.error(f"Errore nel controllo referti per {fiscal_code}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            errors += 1
    
    # Salva i dati aggiornati
    save_reports_monitoring(monitoring_data)
    
    logger.info(f"Controllo referti completato: {total_checked} controllati, {total_notifications} notifiche inviate, {errors} errori")
    return total_checked, total_notifications, errors