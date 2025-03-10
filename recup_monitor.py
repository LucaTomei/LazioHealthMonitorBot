import multiprocessing
import logging
import os
import asyncio
import time
from datetime import datetime

# Importiamo le configurazioni dal modulo config
from config import logger, TELEGRAM_TOKEN, authorized_users

# Configurazione del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("RecupMultiprocess")

def run_telegram_bot():
    """Funzione che esegue il bot Telegram in un processo separato."""
    logger.info("Avvio del processo per il bot Telegram")
    try:
        from telegram.ext import Application
        from modules.bot_handlers import setup_handlers
        
        # Creiamo l'applicazione
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Setup dei gestori
        setup_handlers(application)
        
        # Avviamo il bot
        logger.info("Bot Telegram in avvio...")
        application.run_polling(allowed_updates=["message", "callback_query"])
    except Exception as e:
        logger.error(f"Errore nel processo del bot Telegram: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def run_monitoring():
    """Funzione che esegue il monitoraggio in un processo separato."""
    logger.info("Avvio del processo per il monitoraggio")
    try:
        import asyncio
        
        # Creiamo un nuovo loop per questo processo
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        from modules.monitoring import run_monitoring_loop
        
        # Avviamo il loop di monitoraggio
        logger.info("Monitoraggio prescrizioni in avvio...")
        loop.run_until_complete(run_monitoring_loop())
    except Exception as e:
        logger.error(f"Errore nel processo di monitoraggio: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    """Funzione principale che avvia i processi separati."""
    logger.info("Avvio del sistema multi-processo")
    
    # Caricamento configurazioni e dati comuni
    from modules.data_utils import load_authorized_users
    load_authorized_users()
    
    # Creiamo e avviamo il processo per il bot Telegram
    bot_process = multiprocessing.Process(target=run_telegram_bot)
    bot_process.start()
    
    # Creiamo e avviamo il processo per il monitoraggio
    monitoring_process = multiprocessing.Process(target=run_monitoring)
    monitoring_process.start()
    
    # Attendiamo che i processi terminino (non dovrebbe mai accadere a meno di errori)
    logger.info("Sistema multi-processo avviato. Processi in esecuzione.")
    
    try:
        bot_process.join()
        monitoring_process.join()
    except KeyboardInterrupt:
        logger.info("Interruzione richiesta dall'utente, terminazione dei processi...")
        bot_process.terminate()
        monitoring_process.terminate()
        bot_process.join()
        monitoring_process.join()
        logger.info("Processi terminati correttamente.")
    except Exception as e:
        logger.error(f"Errore nel sistema multi-processo: {str(e)}")
        bot_process.terminate()
        monitoring_process.terminate()
        bot_process.join()
        monitoring_process.join()

if __name__ == "__main__":
    main()