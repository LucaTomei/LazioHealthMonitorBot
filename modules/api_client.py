import requests
import logging

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
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception as e:
        logger.error(f"Errore nell'ottenere il token di accesso: {str(e)}")
        return None

def update_device_token(access_token):
    """Update device token."""
    # Questa funzione può fallire senza compromettere il funzionamento principale
    try:
        url = f"{BASE_URL}/salute/1.0/notifiche/dispositivo/ct6U4eGiTUfJlh-8la_XTW%3AAPA91bGpiDbgIPrQ4HRF6xB2TembPIAtwywCde0hsMEplYm9DLxaws-bUokiv3bwcLyMrYI3ZyKEj6_Gi8FT4jY2w-8-ajUJeH-qdVRFHWdUgLZvYg-ZxVk"
        
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
        
        response = requests.put(url, headers=headers, json=data)
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
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere informazioni sul paziente {fiscal_code}: {str(e)}")
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
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere le informazioni del medico per {fiscal_code}: {str(e)}")
        return None

def book_appointment(process_id, data_prenotazione, diary_id, service_cur, nre, fiscal_code):
    """
    Perform prebooking for an appointment.
    
    This function matches the API call in 1.har, creating a temporary hold on the appointment slot.
    """
    url = f"{BASE_URL}/api/v4/experience-apis/doctors/bpx/{process_id}/prebooking"
    
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Accept-Language": "it-IT,it;q=0.9",
        "Authorization": AUTH_HEADER,
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Connection": "keep-alive",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0",
        "Accept-Encoding": "gzip"
    }
    
    payload = {
        "date": data_prenotazione,
        "diaryId": diary_id,
        "requestId": "A0",
        "supplyModeId": "A",
        "extraServices": [],
        "serviceCur": service_cur,
        "exemptionId": "NE00",
        "priority": "P",
        "nre": nre,
        "processId": process_id,
        "personIdentifier": fiscal_code
    }
    
    response = requests.post(url, headers=headers, json=payload, verify=False)
    
    # More detailed logging for debugging
    print(f"Pre-booking Status Code: {response.status_code}")
    
    if response.status_code != 201:  # The API returns 201 Created for successful prebookings
        print(f"Pre-booking Error Response: {response.text}")
        raise Exception(f"Pre-booking failed with status code {response.status_code}")
    
    return response.json()

def complete_booking(fiscal_code, process_id, nre, phone_number, email, lock_id, order_id, data_prenotazione, diary_id):
    """
    Complete the booking process after a successful prebooking.
    
    This function matches the API call in 2.har, finalizing the appointment reservation.
    """
    url = f"{BASE_URL}/api/v4/process-apis/booking-management/bookings"
    
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Accept-Language": "it-IT,it;q=0.9",
        "Authorization": AUTH_HEADER,
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Connection": "keep-alive",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0",
        "Accept-Encoding": "gzip"
    }
    
    # This payload structure exactly matches what's in 2.har
    payload = {
        "prescriptionNumber": nre,
        "processId": process_id,
        "diaryId": diary_id,  # Ora passato come parametro
        "contacts": {
            "phoneNumber": phone_number,
            "email": email
        },
        "startTime": data_prenotazione,
        "services": [{
            "id": order_id,
            "requestId": "A0"
        }],
        "lockId": lock_id,
        "personIdentifier": fiscal_code,
        "status": "PRENOTATA",
        "supplyModeId": "A"
    }
    
    response = requests.post(url, headers=headers, json=payload, verify=False)
    
    # Enhanced error handling and logging
    print(f"Complete Booking Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"Complete Booking Error Response: {response.text}")
        raise Exception(f"Booking completion failed with status code {response.status_code}")
    
    result = response.json()
    
    # Extract booking ID with robust error handling
    booking_id = None
    if 'id' in result:
        booking_id = result['id']
    elif 'content' in result and result['content'] and 'id' in result['content'][0]:
        booking_id = result['content'][0]['id']
    else:
        print("Warning: Could not find booking ID in response")
        print(f"Response content: {result}")
    
    return result, booking_id

def get_booking_document(booking_id, output_path=None):
    """
    Retrieve the booking document (PDF) and save it locally.
    
    This function matches the API call in 3.har.
    """
    url = f"{BASE_URL}/api/v3/process-apis/booking-management/bookings/{booking_id}/documents"
    
    headers = {
        "Accept": "*/*",
        "Accept-Language": "it-IT,it;q=0.9",
        "Authorization": AUTH_HEADER,
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Connection": "keep-alive",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0",
        "Accept-Encoding": "gzip"
    }
    
    response = requests.get(url, headers=headers, verify=False)
    
    # Enhanced error handling
    if response.status_code != 200:
        print(f"Get Document Error: Status Code {response.status_code}")
        print(f"Response content: {response.text}")
        raise Exception(f"Failed to retrieve booking document with status code {response.status_code}")
    
    # If we need to save the PDF
    if output_path is None:
        # Create a default filename with booking ID and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"booking_{booking_id}_{timestamp}.pdf"
    
    # Save the PDF to disk
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    print(f"✅ Booking document saved to: {output_path}")
    return output_path

def cancel_booking(booking_id):
    """
    Cancel a specific booking.
    
    This function matches the API call in 6.har.
    """
    url = f"{BASE_URL}/api/v3/process-apis/booking-management/bookings"
    
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Accept-Language": "it-IT,it;q=0.9",
        "Authorization": AUTH_HEADER,
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Connection": "keep-alive",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0",
        "Accept-Encoding": "gzip"
    }
    
    # This payload structure exactly matches what's in 6.har
    payload = [{
        "reasonId": 4,  # Reason code for cancellation
        "bookingStatus": "ELIMINATA",
        "identifiedBy": "ID_DI_SISTEMA",
        "identifier": booking_id
    }]
    
    response = requests.patch(url, headers=headers, json=payload, verify=False)
    
    # Better error handling
    if response.status_code != 200:
        print(f"Cancellation Error: Status Code {response.status_code}")
        print(f"Response content: {response.text}")
        raise Exception(f"Booking cancellation failed with status code {response.status_code}")
    
    result = response.json()
    
    # Check if cancellation was successful using the results
    if result and '_messages' in result:
        if not result['_messages']:
            print("✅ Booking successfully canceled")
        else:
            print("⚠️ Cancellation may have issues:", result['_messages'])
    else:
        print("✅ Booking canceled successfully")
    
    return result


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
        response = requests.get(url, headers=headers, params=params)
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
        response = requests.get(url, headers=headers, params=params)
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
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Errore nell'ottenere le disponibilità per {nre}: {str(e)}")
        return None