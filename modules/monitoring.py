import asyncio
import os
import time
import traceback
from datetime import datetime

from config import logger, CHECK_INTERVAL, DB_FILE

from modules.data_utils import (
    load_input_data, load_previous_data, save_previous_data, prune_previous_data
)
from modules.prescription_processor import process_prescription

# File aggiornato a ogni ciclo completato, usato dall'HEALTHCHECK del container
HEARTBEAT_FILE = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)), "heartbeat")


def _touch_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(datetime.now().isoformat())
    except OSError as e:
        logger.warning(f"Impossibile aggiornare il file heartbeat: {e}")


def _check_reports():
    from modules.reports_monitor import check_new_reports
    logger.info("Avvio verifica nuovi referti")
    total_checked, total_notifications, errors = check_new_reports()
    logger.info(f"Verifica referti completata: {total_checked} controllati, {total_notifications} notifiche")
    if errors > 0:
        logger.warning(f"Errori durante la verifica dei referti: {errors}")


async def run_monitoring_loop():
    """Loop di monitoraggio (prescrizioni e referti) eseguito nel processo dedicato."""
    while True:
        start_time = time.time()
        try:
            logger.info(f"Inizio ciclo di monitoraggio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # Ricarichiamo a ogni ciclo: il bot può aver aggiunto prescrizioni o
            # aggiornato le disponibilità (verifica manuale) nel frattempo
            previous_data = load_previous_data()
            prescriptions = load_input_data()

            for prescription in prescriptions:
                prescription_key = f"{prescription.get('fiscal_code')}_{prescription.get('nre')}"
                try:
                    process_prescription(prescription, previous_data)
                except Exception as e:
                    logger.error(f"Errore nel processare la prescrizione {prescription.get('nre', 'sconosciuta')}: {str(e)}")
                    logger.error(traceback.format_exc())

                # Salviamo subito le disponibilità di questa prescrizione
                if prescription_key in previous_data:
                    try:
                        save_previous_data({prescription_key: previous_data[prescription_key]})
                    except Exception as e:
                        logger.error(f"Errore nel salvare le disponibilità: {str(e)}")

                await asyncio.sleep(1)

            prune_previous_data()

            try:
                _check_reports()
            except Exception as e:
                logger.error(f"Errore nella verifica dei referti: {str(e)}")
                logger.error(traceback.format_exc())

            _touch_heartbeat()

            elapsed = time.time() - start_time
            sleep_time = max(CHECK_INTERVAL - elapsed, 1)
            logger.info(f"Ciclo completato in {elapsed:.2f} secondi. In attesa del prossimo ciclo tra {sleep_time:.2f} secondi.")
            await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Errore nel servizio di monitoraggio: {str(e)}")
            logger.error(traceback.format_exc())
            # In caso di errore, aspetta 1 minuto e riprova
            await asyncio.sleep(60)
