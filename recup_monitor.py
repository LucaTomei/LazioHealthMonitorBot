import multiprocessing
import logging
import time

# Importiamo le configurazioni dal modulo config
from config import logger, TELEGRAM_TOKEN, authorized_users

# httpx logga ogni richiesta con l'URL completo, token del bot incluso
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def run_telegram_bot(users_list=None):
    """Funzione che esegue il bot Telegram in un processo separato."""
    import asyncio
    import traceback
    from telegram.error import Conflict, InvalidToken
    from telegram.ext import Application
    from modules.bot_handlers import setup_handlers
    from modules.data_utils import load_authorized_users

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger.info("Avvio del processo per il bot Telegram")

    # Con 'spawn' il processo riparte da zero: ricarichiamo gli utenti dal DB
    if users_list:
        authorized_users.clear()
        authorized_users.extend(users_list)
    load_authorized_users()

    def polling_error(error):
        if isinstance(error, Conflict):
            logger.warning(
                "Conflict su getUpdates: un'altra istanza del bot sta usando lo stesso token. "
                "Assicurati che sia in esecuzione una sola istanza."
            )
        else:
            logger.error(f"Errore durante il polling: {error}")

    async def run_bot():
        # Un'unica Application riutilizzata a ogni riavvio: initialize() riapre le
        # connessioni HTTP chiuse da shutdown(), così non se ne accumulano
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        setup_handlers(application)
        while True:
            retry_delay = 10
            try:
                logger.info("Bot Telegram in avvio...")
                await application.initialize()
                await application.start()
                await application.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=False,
                    error_callback=polling_error,
                )
                while True:
                    await asyncio.sleep(1)
            except InvalidToken:
                logger.error("Token Telegram rifiutato: controlla TELEGRAM_BOT_TOKEN. Nuovo tentativo tra 60 secondi.")
                retry_delay = 60
            except Exception as e:
                logger.error(f"Errore durante l'esecuzione del bot: {str(e)}")
                logger.error(traceback.format_exc())
            finally:
                # Fermiamo sempre l'istanza corrente prima di crearne una nuova,
                # altrimenti due updater farebbero polling in parallelo (Conflict)
                try:
                    if application.updater and application.updater.running:
                        await application.updater.stop()
                    if application.running:
                        await application.stop()
                    await application.shutdown()
                except Exception as e:
                    logger.error(f"Errore nella chiusura del bot: {str(e)}")

            logger.info(f"Tentativo di riavvio del bot tra {retry_delay} secondi...")
            await asyncio.sleep(retry_delay)

    try:
        asyncio.run(run_bot())
    except Exception as e:
        logger.error(f"Errore critico nel processo del bot Telegram: {str(e)}")
        logger.error(traceback.format_exc())


def run_monitoring():
    """Funzione che esegue il monitoraggio (prescrizioni e referti) in un processo separato."""
    import asyncio
    import traceback

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger.info("Avvio del processo per il monitoraggio")
    try:
        from modules.monitoring import run_monitoring_loop
        asyncio.run(run_monitoring_loop())
    except Exception as e:
        logger.error(f"Errore critico nel processo di monitoraggio: {str(e)}")
        logger.error(traceback.format_exc())


def _start_process(mp_context, target, args=()):
    process = mp_context.Process(target=target, args=args)
    process.daemon = True  # Il processo terminerà quando il processo principale termina
    process.start()
    return process


def main():
    """Funzione principale che avvia il sistema multi-processo."""
    logger.info("Avvio del sistema multi-processo")

    # Inizializzazione del database SQLite (crea schema e migra da JSON se necessario)
    from modules.database import init_db
    init_db()

    # Caricamento configurazioni e dati comuni
    from modules.data_utils import load_authorized_users
    load_authorized_users()

    if not authorized_users:
        logger.warning("Nessun utente autorizzato trovato! Il sistema aspetterà l'aggiunta manuale di un utente.")

    # Processi completamente indipendenti
    mp_context = multiprocessing.get_context('spawn')

    bot_process = _start_process(mp_context, run_telegram_bot, (list(authorized_users),))
    monitoring_process = _start_process(mp_context, run_monitoring)
    logger.info("Sistema multi-processo avviato. Processi in esecuzione.")

    try:
        # Supervisore: riavvia ogni processo che termina inaspettatamente
        while True:
            time.sleep(5)

            if not bot_process.is_alive():
                logger.error(f"Il processo del bot Telegram è terminato (exit code {bot_process.exitcode}), riavvio...")
                load_authorized_users()
                bot_process = _start_process(mp_context, run_telegram_bot, (list(authorized_users),))

            if not monitoring_process.is_alive():
                logger.error(f"Il processo di monitoraggio è terminato (exit code {monitoring_process.exitcode}), riavvio...")
                monitoring_process = _start_process(mp_context, run_monitoring)

    except KeyboardInterrupt:
        logger.info("Interruzione richiesta dall'utente, terminazione dei processi...")
    except Exception as e:
        logger.error(f"Errore nel sistema multi-processo: {str(e)}")
    finally:
        for process in (bot_process, monitoring_process):
            process.terminate()
        for process in (bot_process, monitoring_process):
            process.join(timeout=5)
        logger.info("Processi terminati.")


if __name__ == "__main__":
    main()
