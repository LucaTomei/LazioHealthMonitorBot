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

def run_telegram_bot(users_list=None):
    """Funzione che esegue il bot Telegram in un processo separato."""
    global authorized_users
    if users_list:
        authorized_users.clear()
        authorized_users.extend(users_list)
    logger.info("Avvio del processo per il bot Telegram")
    try:
        import asyncio
        from telegram.ext import Application
        from modules.bot_handlers import setup_handlers
        
        # Configuriamo un nuovo loop per il processo
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def run_bot():
            try:
                # Creiamo l'applicazione
                application = Application.builder().token(TELEGRAM_TOKEN).build()
                
                # Setup dei gestori
                setup_handlers(application)
                
                # Avviamo il bot
                logger.info("Bot Telegram in avvio...")
                await application.initialize()
                await application.start()
                await application.updater.start_polling(allowed_updates=["message", "callback_query"])
                
                # Manteniamo il bot in esecuzione
                while True:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Errore durante l'esecuzione del bot: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                
                # Riavviamo il bot dopo un errore
                logger.info("Tentativo di riavvio del bot tra 10 secondi...")
                await asyncio.sleep(10)
                return await run_bot()  # Riavvio ricorsivo
        
        # Eseguiamo il bot nel loop
        loop.run_until_complete(run_bot())
    
    except Exception as e:
        logger.error(f"Errore critico nel processo del bot Telegram: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
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
        
        # Funzione migliorata che si riavvia automaticamente in caso di errore
        async def robust_monitoring_loop():
            # Carica dati precedenti
            from modules.data_utils import load_previous_data, save_previous_data, load_input_data
            from modules.prescription_processor import process_prescription
            
            previous_data = load_previous_data()
            
            while True:
                try:
                    start_time = time.time()
                    logger.info(f"Inizio ciclo di monitoraggio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # Carichiamo i dati delle prescrizioni
                    prescriptions = load_input_data()
                    
                    # Process each prescription
                    for prescription in prescriptions:
                        try:
                            process_prescription(prescription, previous_data)
                        except Exception as e:
                            logger.error(f"Errore nel processare la prescrizione {prescription.get('nre', 'sconosciuta')}: {str(e)}")
                            import traceback
                            logger.error(traceback.format_exc())
                        
                        # Breve pausa tra una prescrizione e l'altra
                        await asyncio.sleep(1)
                    
                    # Salviamo i dati aggiornati
                    save_previous_data(previous_data)
                    
                    # Calcoliamo il tempo di attesa per mantenere cicli di 5 minuti
                    elapsed = time.time() - start_time
                    sleep_time = max(300 - elapsed, 1)  # 300 secondi = 5 minuti
                    
                    logger.info(f"Ciclo completato in {elapsed:.2f} secondi. In attesa del prossimo ciclo tra {sleep_time:.2f} secondi.")
                    await asyncio.sleep(sleep_time)
                    
                except Exception as e:
                    logger.error(f"Errore nel ciclo di monitoraggio: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
                    # In caso di errore, aspetta 60 secondi e riprova
                    logger.info("Riavvio del ciclo di monitoraggio tra 60 secondi...")
                    await asyncio.sleep(60)
        
        # Avvia il loop di monitoraggio
        loop.run_until_complete(robust_monitoring_loop())
    
    except Exception as e:
        logger.error(f"Errore critico nel processo di monitoraggio: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    """Funzione principale che avvia il sistema multi-processo."""
    logger.info("Avvio del sistema multi-processo")
    
    # Caricamento configurazioni e dati comuni
    from modules.data_utils import load_authorized_users
    load_authorized_users()
    
    users = list(authorized_users)
    
    if not authorized_users:
        logger.warning("Nessun utente autorizzato trovato! Il sistema aspetterà l'aggiunta manuale di un utente.")
    
    # Impostazioni avanzate per i processi separati
    # Questa modifica fa sì che i processi siano completamente indipendenti
    mp_context = multiprocessing.get_context('spawn')
    
    # Creiamo e avviamo il processo per il bot Telegram
    #bot_process = mp_context.Process(target=run_telegram_bot)
    bot_process = mp_context.Process(target=run_telegram_bot, args=(users,))

    bot_process.daemon = True  # Il processo terminerà quando il processo principale termina
    bot_process.start()
    
    # Creiamo e avviamo il processo per il monitoraggio
    monitoring_process = mp_context.Process(target=run_monitoring)
    monitoring_process.daemon = True
    monitoring_process.start()
    
    # Attendiamo che i processi terminino (non dovrebbe mai accadere a meno di errori)
    logger.info("Sistema multi-processo avviato. Processi in esecuzione.")
    
    try:
        # Invece di fare join direttamente, controlliamo periodicamente lo stato
        while bot_process.is_alive() and monitoring_process.is_alive():
            time.sleep(1)  # Controlliamo ogni secondo
            
        # Se siamo qui, uno dei processi è terminato inaspettatamente
        if not bot_process.is_alive():
            logger.error("Il processo del bot Telegram è terminato inaspettatamente, riavvio...")
            bot_process = mp_context.Process(target=run_telegram_bot)
            bot_process.daemon = True
            bot_process.start()
        
        if not monitoring_process.is_alive():
            logger.error("Il processo di monitoraggio è terminato inaspettatamente, riavvio...")
            monitoring_process = mp_context.Process(target=run_monitoring)
            monitoring_process.daemon = True
            monitoring_process.start()
            
    except KeyboardInterrupt:
        logger.info("Interruzione richiesta dall'utente, terminazione dei processi...")
        bot_process.terminate()
        monitoring_process.terminate()
        bot_process.join(timeout=5)
        monitoring_process.join(timeout=5)
        logger.info("Processi terminati correttamente.")
    except Exception as e:
        logger.error(f"Errore nel sistema multi-processo: {str(e)}")
        bot_process.terminate()
        monitoring_process.terminate()
        bot_process.join(timeout=5)
        monitoring_process.join(timeout=5)

if __name__ == "__main__":
    main()