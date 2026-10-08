import requests

from config import (
    logger, BASE_URL, AUTH_HEADER
)

def get_access_token():
    """Obtain access token from the authentication endpoint."""
    token_url = "https://gwapi-az.servicelazio.it/token"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Authorization": "Basic aFJaMkYxNkthcWQ5dzZxRldEVEhJbHg3UnVRYTpnaUVHbEp4a0Iza1VBdWRLdXZNdFBJaTVRc2th",
        "Accept-Language": "it-IT;q=1.0",
        "User-Agent": "RLGEOAPP/2.2.0 (it.laziocrea.rlgeoapp; build:2.2.0; iOS 18.3.1) Alamofire/5.10.2"
    }
    
    data = {
        "grant_type": "client_credentials"
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data, timeout=15)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception as e:
        logger.error(f"Errore nell'ottenere il token di accesso: {str(e)}")
        return None

def update_device_token(access_token):
    """Update device token."""
    # Questa funzione può fallire senza compromettere il funzionamento principale
    try:
        url = "https://gwapi-az.servicelazio.it/salute/1.0/notifiche/dispositivo/ct6U4eGiTUfJlh-8la_XTW%3AAPA91bGpiDbgIPrQ4HRF6xB2TembPIAtwywCde0hsMEplYm9DLxaws-bUokiv3bwcLyMrYI3ZyKEj6_Gi8FT4jY2w-8-ajUJeH-qdVRFHWdUgLZvYg-ZxVk"
        
        headers = {
            "Accept-Encoding": "application/json; charset=utf-8",
            "Accept-Language": "it-IT;q=1.0",
            "User-Agent": "RLGEOAPP/2.2.0 (it.laziocrea.rlgeoapp; build:2.2.0; iOS 18.3.1) Alamofire/5.10.2",
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "token_new": "ct6U4eGiTUfJlh-8la_XTW:APA91bGpiDbgIPrQ4HRF6xB2TembPIAtwywCde0hsMEplYm9DLxaws-bUokiv3bwcLyMrYI3ZyKEj6_Gi8FT4jY2w-8-ajUJeH-qdVRFHWdUgLZvYg-ZxVk"
        }
        
        response = requests.put(url, headers=headers, json=data, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Avviso: impossibile aggiornare il token del dispositivo: {str(e)}")
        # Continuiamo comunque l'esecuzione
        return None

def get_patient_info(fiscal_code):
    """Retrieve patient information."""
    url = f"{BASE_URL}/api/v3/system-apis/patients"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "fiscalCode": fiscal_code
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere informazioni sul paziente: {str(e).replace(fiscal_code, fiscal_code[:6] + '**********')}")
        return None

def get_doctor_info(fiscal_code):
    """Get doctor information."""
    url = f"{BASE_URL}/api/v4/experience-apis/doctors/bpx"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0",
        "Content-Type": "application/json"
    }
    
    data = {
        "personIdentifier": fiscal_code
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere le informazioni del medico: {str(e).replace(fiscal_code, fiscal_code[:6] + '**********')}")
        return None

def api_message(result):
    """Primo messaggio testuale restituito dalle API RecUP (es. "ricetta scaduta"), senza prefisso di livello."""
    messages = (result or {}).get("_messages") or []
    text = (messages[0].get("text") or "").strip() if messages else ""
    if len(text) > 4 and text[1:4] == " - ":
        text = text[4:]
    return text


def check_prescription(patient_id, nre):
    """Check prescription details."""
    url = f"{BASE_URL}/api/v3/experience-apis/citizens/prescriptions/check-prescription"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "patientId": patient_id,
        "nre": nre
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code == 404:
            try:
                messages = response.json().get("_messages") or []
            except ValueError:
                messages = []
            result = {"_not_found": True, "_messages": messages}
            logger.warning(f"Prescrizione {nre} non disponibile (404): {api_message(result) or 'nessun dettaglio'}")
            return result
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nel controllare la prescrizione {nre}: {str(e)}")
        return None

def get_prescription_details(patient_id, nre):
    """Get full prescription details."""
    url = f"{BASE_URL}/api/v3/system-apis/prescriptions/{nre}"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "patientId": patient_id
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere i dettagli della prescrizione {nre}: {str(e)}")
        return None

def get_availabilities(patient_id, process_id, nre, order_ids):
    """Get medical service availabilities."""
    url = f"{BASE_URL}/api/v3/experience-apis/citizens/availabilities"
    
    headers = {
        "Connection": "keep-alive",
        "Authorization": AUTH_HEADER,
        "Accept-Language": "it-IT,it;q=0.9",
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0"
    }
    
    params = {
        "personId": patient_id,
        "processId": process_id,
        "nre": nre,
        "orderIds": order_ids,
        "prescriptionPriority": "P",
        "firstBy": "hospital-best-10"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code == 400:
            logger.warning(f"Disponibilità non recuperabili per {nre} (400) — prescrizione probabilmente già prenotata o non più attiva")
            return {"content": [], "_already_booked": True}
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere le disponibilità per {nre}: {str(e)}")
        return None