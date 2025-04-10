import asyncio
import time
import logging
from datetime import datetime

# Importiamo le variabili globali dal modulo principale
from recup_monitor import logger

# Importiamo le funzioni da altri moduli
from modules.data_utils import load_input_data, load_previous_data, save_previous_data
from modules.prescription_processor import process_prescription

def run_monitoring():
    """Funzione che esegue il monitoraggio in un processo separato."""
    logger.info("Avvio del processo per il monitoraggio")
    try:
        import asyncio
        import time
        from datetime import datetime
        
        # Creiamo un nuovo loop per questo processo
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Importa la funzione corretta
        from modules.monitoring import run_monitoring_loop
        
        # Funzione migliorata che si riavvia automaticamente in caso di errore
        loop.run_until_complete(run_monitoring_loop())
    
    except Exception as e:
        logger.error(f"Errore critico nel processo di monitoraggio: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

async def run_monitoring_loop():
    """Funzione dedicata al loop di monitoraggio da eseguire in un processo separato."""
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
                try:
                    process_prescription(prescription, previous_data)
                except Exception as e:
                    logger.error(f"Errore nel processare la prescrizione {prescription.get('nre', 'sconosciuta')}: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                
                # Small delay between processing different prescriptions
                await asyncio.sleep(1)
            
            # Verifica dei referti
            try:
                from modules.reports_monitor import check_new_reports
                logger.info("Avvio verifica nuovi referti")
                total_checked, total_notifications, errors = check_new_reports()
                logger.info(f"Verifica referti completata: {total_checked} controllati, {total_notifications} notifiche")
                if errors > 0:
                    logger.warning(f"Errori durante la verifica dei referti: {errors}")
            except Exception as e:
                logger.error(f"Errore nella verifica dei referti: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            # Save updated previous data
            save_previous_data(previous_data)
            
            # Calculate time to sleep to maintain 5-minute cycles
            elapsed = time.time() - start_time
            sleep_time = max(300 - elapsed, 1)  # 300 seconds = 5 minutes
            
            logger.info(f"Ciclo completato in {elapsed:.2f} secondi. In attesa del prossimo ciclo tra {sleep_time:.2f} secondi.")
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Errore nel servizio di monitoraggio: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # In caso di errore, aspetta 1 minuto e riprova
            await asyncio.sleep(60)

