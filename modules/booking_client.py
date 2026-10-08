import os
from datetime import datetime

import requests

from config import logger, PDF_FOLDER, BASE_URL, AUTH_HEADER

REQUEST_TIMEOUT = 20


def _headers(json_body=False):
    headers = {
        "Accept": "*/*",
        "Accept-Language": "it-IT,it;q=0.9",
        "Authorization": AUTH_HEADER,
        "Host": "recup-webapi-appmobile.regione.lazio.it",
        "Connection": "keep-alive",
        "User-Agent": "salutelazio/2.2.0 CFNetwork/3826.400.120 Darwin/24.3.0",
        "Accept-Encoding": "gzip"
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def book_appointment(process_id, data_prenotazione, diary_id, service_cur, nre, fiscal_code):
    """
    Perform prebooking for an appointment.

    This function creates a temporary hold on the appointment slot.
    """
    url = f"{BASE_URL}/api/v4/experience-apis/doctors/bpx/{process_id}/prebooking"

    payload = {
        "date": data_prenotazione,
        "diaryId": diary_id,
        "requestId": "A0",
        "supplyModeId": "A",
        "extraServices": None,  # API expects null, not []
        "serviceCur": service_cur,
        "exemptionId": "NE00",
        "priority": "P",
        "nre": nre,
        "processId": process_id,
        "personIdentifier": fiscal_code
    }

    response = requests.post(url, headers=_headers(True), json=payload, timeout=REQUEST_TIMEOUT)
    logger.info(f"Pre-booking Status Code: {response.status_code}")

    if response.status_code == 204:
        # Slot already locked; retry to obtain a fresh lock ID
        logger.info("Pre-booking returned 204 (existing lock), retrying...")
        response = requests.post(url, headers=_headers(True), json=payload, timeout=REQUEST_TIMEOUT)
        logger.info(f"Pre-booking retry Status Code: {response.status_code}")

    if response.status_code == 201:
        return response.json()

    logger.error(f"Pre-booking Error Response: {response.text[:300]}")
    raise Exception(f"Pre-booking failed with status code {response.status_code}")


def complete_booking(fiscal_code, process_id, nre, phone_number, email, lock_id, order_id, data_prenotazione, diary_id):
    """
    Complete the booking process after a successful prebooking.

    This function finalizes the appointment reservation.
    """
    url = f"{BASE_URL}/api/v4/process-apis/booking-management/bookings"

    payload = {
        "prescriptionNumber": nre,
        "processId": process_id,
        "diaryId": diary_id,
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

    response = requests.post(url, headers=_headers(True), json=payload, timeout=REQUEST_TIMEOUT)
    logger.info(f"Complete Booking Status Code: {response.status_code}")

    if response.status_code != 200:
        logger.error(f"Complete Booking Error Response: {response.text[:300]}")
        raise Exception(f"Booking completion failed with status code {response.status_code}")

    result = response.json()

    booking_id = None
    if isinstance(result, dict):
        if result.get('id'):
            booking_id = result['id']
        elif result.get('content') and isinstance(result['content'], list) and result['content'][0].get('id'):
            booking_id = result['content'][0]['id']
    if not booking_id:
        logger.warning("Could not find booking ID in response")

    return result, booking_id


def get_booking_document(booking_id, output_path=None):
    """
    Retrieve the booking document (PDF) and save it locally.
    """
    url = f"{BASE_URL}/api/v3/process-apis/booking-management/bookings/{booking_id}/documents"

    response = requests.get(url, headers=_headers(), timeout=30)

    if response.status_code != 200:
        logger.error(f"Get Document Error: Status Code {response.status_code}")
        raise Exception(f"Failed to retrieve booking document with status code {response.status_code}")

    os.makedirs(PDF_FOLDER, exist_ok=True)

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(PDF_FOLDER, f"booking_{booking_id}_{timestamp}.pdf")

    with open(output_path, 'wb') as f:
        f.write(response.content)

    logger.info(f"Booking document saved to: {output_path}")
    return output_path, response.content


def cancel_booking(booking_id):
    """
    Cancel a specific booking.
    """
    logger.info(f"Tentativo di cancellazione prenotazione con ID: {booking_id}")

    url = f"{BASE_URL}/api/v3/process-apis/booking-management/bookings"

    payload = [{
        "reasonId": 4,  # Reason code for cancellation
        "bookingStatus": "ELIMINATA",
        "identifiedBy": "ID_DI_SISTEMA",
        "identifier": booking_id
    }]

    try:
        response = requests.patch(url, headers=_headers(True), json=payload, timeout=REQUEST_TIMEOUT)
        logger.info(f"Status code risposta: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"Errore nella cancellazione: {response.status_code} - {response.text[:300]}")
            raise Exception(f"Cancellazione prenotazione fallita con codice {response.status_code}")

        result = response.json()
        messages = result.get("_messages") if isinstance(result, dict) else None
        if messages:
            logger.warning(f"Messaggi dall'API durante la cancellazione: {messages}")
        return result
    except Exception as e:
        logger.error(f"Eccezione durante la cancellazione: {str(e)}")
        raise


def _slot_hospital(slot):
    return (slot.get('hospital') or {}).get('name') or 'Unknown'


def _slot_address(slot):
    return (slot.get('site') or {}).get('address') or 'Unknown'


def booking_workflow(fiscal_code, nre, phone_number, email, patient_id=None, process_id=None,
                     slot_choice=0, slot_date=None, diary_id=None):
    """
    Complete booking workflow - from checking availability to booking and downloading confirmation.

    Parameters:
    fiscal_code (str): The fiscal code of the patient
    nre (str): The prescription number
    phone_number (str): Contact phone number
    email (str): Contact email
    patient_id (str, optional): If already known, patient ID to skip a step
    process_id (str, optional): If already known, process ID to skip a step
    slot_choice (int, optional): Index of the slot to choose (0 = first available, -1 = list slots)
    slot_date, diary_id (optional): Identify exactly the slot the user confirmed;
        if it is no longer available the booking is not performed

    Returns:
    dict: Result of the booking operation with details
    """
    from modules.api_client import (
        get_patient_info, get_doctor_info, check_prescription,
        get_prescription_details, get_availabilities
    )
    from modules.data_utils import get_prescription, is_date_within_range

    try:
        # Step 1: Get patient information if not provided
        if not patient_id:
            patient_info = get_patient_info(fiscal_code)
            if not patient_info or not patient_info.get('content'):
                return {"success": False, "message": f"Impossibile trovare informazioni per il paziente {fiscal_code}"}
            patient_id = patient_info['content'][0]['id']

        # Step 2: Get doctor information if not provided
        if not process_id:
            doctor_info = get_doctor_info(fiscal_code)
            if not doctor_info or 'id' not in doctor_info:
                return {"success": False, "message": f"Impossibile trovare informazioni per il medico del paziente {fiscal_code}"}
            process_id = doctor_info['id']

        # Step 3: Check prescription
        check_prescription_result = check_prescription(patient_id, nre)
        if not check_prescription_result:
            return {"success": False, "message": f"Impossibile verificare la prescrizione {nre}"}
        if check_prescription_result.get("_not_found"):
            return {"success": False, "message": "Prescrizione non disponibile al momento (già prenotata o problema temporaneo dei server RecUP). Riprova più tardi."}
        logger.info("Prescription Checked")

        # Step 4: Get prescription details
        prescription_details = get_prescription_details(patient_id, nre)
        if not prescription_details or not prescription_details.get('details'):
            return {"success": False, "message": f"Impossibile ottenere i dettagli della prescrizione {nre}"}

        service = prescription_details['details'][0].get('service') or {}
        order_ids = service.get('id')
        service_cur = service.get('code')
        service_name = service.get('description') or 'Servizio non specificato'

        # Step 5: Get availabilities
        availabilities = get_availabilities(patient_id, process_id, nre, order_ids)
        if not availabilities or 'content' not in availabilities:
            return {"success": False, "message": f"Impossibile ottenere le disponibilità per {nre}"}
        if availabilities.get("_already_booked"):
            return {"success": False, "message": "Questa prescrizione risulta già prenotata o non più prenotabile online"}

        all_slots = availabilities['content'] or []
        logger.info(f"Total available slots: {len(all_slots)}")
        if not all_slots:
            return {"success": False, "message": "Nessuna disponibilità trovata per questa prescrizione"}

        # Step 6: Filtri della prescrizione (blacklist ospedali e limite mesi)
        hospitals_blacklist = []
        months_limit = None
        stored = get_prescription(fiscal_code, nre)
        if stored:
            config = stored.get("config") or {}
            hospitals_blacklist = config.get("hospitals_blacklist", [])
            months_limit = config.get("months_limit")

        available_slots = [
            slot for slot in all_slots
            if _slot_hospital(slot) not in hospitals_blacklist
            and is_date_within_range(slot.get('date', ''), months_limit)
        ]
        logger.info(f"Slot disponibili dopo filtraggio (blacklist+date): {len(available_slots)}/{len(all_slots)}")

        if not available_slots:
            return {"success": False, "message": "Nessuna disponibilità trovata dopo l'applicazione dei filtri (blacklist e date)"}

        sorted_slots = sorted(available_slots, key=lambda x: x.get('date') or '')

        if slot_choice == -1:
            # Return the list of availabilities for user selection
            slot_info = []
            for i, slot in enumerate(sorted_slots):
                slot_info.append({
                    "index": i,
                    "date": slot.get('date'),
                    "diary_id": (slot.get('diary') or {}).get('id'),
                    "hospital": _slot_hospital(slot),
                    "address": _slot_address(slot),
                    "price": slot.get('price', 'N/A')
                })
            return {
                "success": True,
                "action": "list_slots",
                "service": service_name,
                "slots": slot_info,
                "patient_id": patient_id,
                "process_id": process_id
            }

        if slot_date is not None:
            # Prenotiamo esattamente lo slot confermato dall'utente
            matches = [
                slot for slot in sorted_slots
                if slot.get('date') == slot_date
                and (diary_id is None or (slot.get('diary') or {}).get('id') == diary_id)
            ]
            if not matches:
                return {"success": False, "message": "Lo slot selezionato non è più disponibile. Riprova scegliendo un altro orario."}
            selected_slot = matches[0]
        else:
            if slot_choice < 0 or slot_choice >= len(sorted_slots):
                return {"success": False, "message": "Lo slot selezionato non è più disponibile. Riprova scegliendo un altro orario."}
            selected_slot = sorted_slots[slot_choice]

        selected_diary_id = (selected_slot.get('diary') or {}).get('id')
        data_prenotazione = selected_slot.get('date')

        logger.info(f"Selected Appointment: {data_prenotazione} - {_slot_hospital(selected_slot)}")

        # Step 7: Create pre-booking for the selected slot
        try:
            prebooking_result = book_appointment(
                process_id,
                data_prenotazione,
                selected_diary_id,
                service_cur,
                nre,
                fiscal_code
            )
            lock_id = prebooking_result['id']
            logger.info(f"Pre-booking successful. Lock ID: {lock_id}")

            # Step 8: Complete booking
            _, booking_id = complete_booking(
                fiscal_code,
                process_id,
                nre,
                phone_number,
                email,
                lock_id,
                order_ids,
                data_prenotazione,
                selected_diary_id
            )
        except Exception as e:
            logger.error(f"Error booking slot {data_prenotazione}: {str(e)}")
            return {"success": False, "message": f"Errore durante la prenotazione: {str(e)}"}

        # Da qui in poi la prenotazione è effettuata sul server RecUP:
        # un errore nel recupero del PDF non deve farla risultare fallita
        logger.info(f"Booking completed. Booking ID: {booking_id}")

        pdf_path, pdf_content = None, None
        if booking_id:
            try:
                pdf_path, pdf_content = get_booking_document(booking_id)
            except Exception as e:
                logger.error(f"Prenotazione {booking_id} effettuata ma documento non scaricabile: {str(e)}")

        return {
            "success": True,
            "action": "booked",
            "booking_id": booking_id,
            "pdf_path": pdf_path,
            "pdf_content": pdf_content,
            "appointment_date": data_prenotazione,
            "hospital": _slot_hospital(selected_slot),
            "address": _slot_address(selected_slot),
            "service": service_name
        }

    except Exception as e:
        logger.error(f"An error occurred in booking workflow: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"success": False, "message": f"Errore durante il processo di prenotazione: {str(e)}"}


def get_user_bookings(fiscal_code):
    """
    Get a list of active bookings for a user.

    Parameters:
    fiscal_code (str): The fiscal code of the patient

    Returns:
    dict: {"success": bool, "bookings": list} or {"success": False, "message": str}
    """
    url = f"{BASE_URL}/api/v3/process-apis/booking-management/bookings/search"

    payload = {
        "fiscalCode": fiscal_code,
        "statuses": ["PRENOTATA", "PRESA_IN_CARICO"]
    }

    try:
        response = requests.post(url, headers=_headers(True), json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        result = response.json()
        bookings = result.get('content') if isinstance(result, dict) else None
        return {"success": True, "bookings": bookings or []}
    except Exception as e:
        logger.error(f"Error getting user bookings: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nel recupero delle prenotazioni: {str(e)}"
        }
