import html
import json
from io import BytesIO

import requests

from config import logger, TELEGRAM_TOKEN

# Telegram accetta al massimo 4096 caratteri per messaggio
MAX_MESSAGE_LENGTH = 4000

API_URL = "https://api.telegram.org/bot{token}/{method}"


def esc(value):
    """Escape HTML per i valori interpolati nei messaggi con parse_mode HTML."""
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def split_message(text, limit=MAX_MESSAGE_LENGTH):
    """
    Divide un messaggio lungo in parti di al massimo `limit` caratteri,
    spezzando sulle righe (i tag HTML usati dal bot sono sempre aperti e chiusi
    sulla stessa riga, quindi ogni parte resta HTML valido).
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current.strip():
        chunks.append(current)
    return chunks


def _api_url(method):
    return API_URL.format(token=TELEGRAM_TOKEN, method=method)


def send_message_sync(chat_id, text, parse_mode="HTML", reply_markup=None):
    """
    Invia un messaggio tramite Bot API in modo sincrono (per il processo di monitoraggio).
    I messaggi lunghi vengono divisi; la tastiera viene allegata all'ultima parte.
    Ritorna True se tutte le parti sono state consegnate.
    """
    chunks = split_message(text)
    try:
        for i, chunk in enumerate(chunks):
            payload = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = json.dumps(reply_markup)
            response = requests.post(_api_url("sendMessage"), json=payload, timeout=15)
            if response.status_code != 200:
                logger.error(
                    f"Invio messaggio Telegram fallito (status {response.status_code}): "
                    f"{response.text[:200]}"
                )
                return False
        return True
    except Exception as e:
        logger.error(f"Errore nell'inviare messaggio Telegram: {type(e).__name__}")
        return False


def send_document_sync(chat_id, content, filename, caption=None):
    """Invia un documento tramite Bot API in modo sincrono. Ritorna True se consegnato."""
    try:
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]
        files = {"document": (filename, BytesIO(content), "application/pdf")}
        response = requests.post(_api_url("sendDocument"), data=data, files=files, timeout=30)
        if response.status_code != 200:
            logger.error(
                f"Invio documento Telegram fallito (status {response.status_code}): "
                f"{response.text[:200]}"
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Errore nell'inviare documento Telegram: {type(e).__name__}")
        return False
