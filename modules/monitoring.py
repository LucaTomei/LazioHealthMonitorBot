import asyncio
import time
import logging
from datetime import datetime

# Importiamo le variabili globali dal modulo principale
from recup_monitor import logger

# Importiamo le funzioni da altri moduli
from modules.data_utils import load_input_data, load_previous_data, save_previous_data
from modules.prescription_processor import process_prescription

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