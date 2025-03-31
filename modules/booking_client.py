import requests
import base64
import json
import urllib3
import time
import os
from datetime import datetime
import logging

# Importiamo il logger dal modulo principale
from recup_monitor import logger

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Base configuration
BASE_URL = "https://recup-webapi-appmobile.regione.lazio.it"
AUTH_HEADER = "Basic QVBQTU9CSUxFX1NQRUNJQUw6UGs3alVTcDgzbUh4VDU4NA=="

def book_appointment(process_id, data_prenotazione, diary_id, service_cur, nre, fiscal_code):
    """
    Perform prebooking for an appointment.
    
    This function creates a temporary hold on the appointment slot.
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
    logger.info(f"Pre-booking Status Code: {response.status_code}")
    
    if response.status_code != 201:  # The API returns 201 Created for successful prebookings
        logger.error(f"Pre-booking Error Response: {response.text}")
        raise Exception(f"Pre-booking failed with status code {response.status_code}")
    
    return response.json()

def complete_booking(fiscal_code, process_id, nre, phone_number, email, lock_id, order_id, data_prenotazione, diary_id):
    """
    Complete the booking process after a successful prebooking.
    
    This function finalizes the appointment reservation.
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
    
    # This payload structure matches what's needed for the API
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
    
    response = requests.post(url, headers=headers, json=payload, verify=False)
    
    # Enhanced error handling and logging
    logger.info(f"Complete Booking Status Code: {response.status_code}")
    
    if response.status_code != 200:
        logger.error(f"Complete Booking Error Response: {response.text}")
        raise Exception(f"Booking completion failed with status code {response.status_code}")
    
    result = response.json()
    
    # Extract booking ID with robust error handling
    booking_id = None
    if 'id' in result:
        booking_id = result['id']
    elif 'content' in result and result['content'] and 'id' in result['content'][0]:
        booking_id = result['content'][0]['id']
    else:
        logger.warning("Could not find booking ID in response")
        logger.debug(f"Response content: {result}")
    
    return result, booking_id

def get_booking_document(booking_id, output_path=None):
    """
    Retrieve the booking document (PDF) and save it locally.
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
        logger.error(f"Get Document Error: Status Code {response.status_code}")
        logger.error(f"Response content: {response.text}")
        raise Exception(f"Failed to retrieve booking document with status code {response.status_code}")
    
    # If we need to save the PDF
    if output_path is None:
        # Create a default filename with booking ID and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"booking_{booking_id}_{timestamp}.pdf"
    
    # Save the PDF to disk
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
    
    # Payload per la cancellazione
    payload = [{
        "reasonId": 4,  # Reason code for cancellation
        "bookingStatus": "ELIMINATA",
        "identifiedBy": "ID_DI_SISTEMA",
        "identifier": booking_id
    }]
    
    logger.info(f"Payload cancellazione: {payload}")
    
    try:
        response = requests.patch(url, headers=headers, json=payload, verify=False)
        
        # Log della risposta
        logger.info(f"Status code risposta: {response.status_code}")
        logger.info(f"Contenuto risposta: {response.text[:500]}")  # Limitiamo per sicurezza
        
        if response.status_code != 200:
            logger.error(f"Errore nella cancellazione: {response.status_code}")
            logger.error(f"Risposta errore: {response.text}")
            raise Exception(f"Cancellazione prenotazione fallita con codice {response.status_code}")
        
        result = response.json()
        logger.info(f"Risposta JSON: {result}")
        
        return result
    except Exception as e:
        logger.error(f"Eccezione durante la cancellazione: {str(e)}")
        raise
    
def booking_workflow(fiscal_code, nre, phone_number, email, patient_id=None, process_id=None, slot_choice=0):
    """
    Complete booking workflow - from checking availability to booking and downloading confirmation.
    
    Parameters:
    fiscal_code (str): The fiscal code of the patient
    nre (str): The prescription number
    phone_number (str): Contact phone number
    email (str): Contact email
    patient_id (str, optional): If already known, patient ID to skip a step
    process_id (str, optional): If already known, process ID to skip a step
    slot_choice (int, optional): Index of the slot to choose (0 = first available)
    
    Returns:
    dict: Result of the booking operation with details
    """
    from modules.api_client import (
        get_patient_info, get_doctor_info, check_prescription,
        get_prescription_details, get_availabilities
    )
    
    try:
        # Step 1: Get patient information if not provided
        if not patient_id:
            patient_info = get_patient_info(fiscal_code)
            if not patient_info or 'content' not in patient_info or not patient_info['content']:
                return {"success": False, "message": f"Impossibile trovare informazioni per il paziente {fiscal_code}"}
            patient_id = patient_info['content'][0]['id']
            logger.info(f"Patient ID: {patient_id}")
        
        # Step 2: Get doctor information if not provided
        if not process_id:
            doctor_info = get_doctor_info(fiscal_code)
            if not doctor_info or 'id' not in doctor_info:
                return {"success": False, "message": f"Impossibile trovare informazioni per il medico del paziente {fiscal_code}"}
            process_id = doctor_info['id']
            logger.info(f"Process ID: {process_id}")
        
        # Step 3: Check prescription
        check_prescription_result = check_prescription(patient_id, nre)
        if not check_prescription_result:
            return {"success": False, "message": f"Impossibile verificare la prescrizione {nre}"}
        logger.info("Prescription Checked")
        
        # Step 4: Get prescription details
        prescription_details = get_prescription_details(patient_id, nre)
        if not prescription_details or 'details' not in prescription_details or not prescription_details['details']:
            return {"success": False, "message": f"Impossibile ottenere i dettagli della prescrizione {nre}"}
        
        order_ids = prescription_details['details'][0]['service']['id']
        service_cur = prescription_details['details'][0]['service']['code']
        service_name = prescription_details['details'][0]['service'].get('description', 'Servizio non specificato')
        logger.info(f"Order ID: {order_ids}")
        
        # Step 5: Get availabilities
        availabilities = get_availabilities(patient_id, process_id, nre, order_ids)
        if not availabilities or 'content' not in availabilities:
            return {"success": False, "message": f"Impossibile ottenere le disponibilità per {nre}"}
        
        logger.info(f"Total available slots: {len(availabilities['content'])}")
        
        # Step 6: List and select slot
        if not availabilities['content']:
            return {"success": False, "message": "Nessuna disponibilità trovata per questa prescrizione"}
        
        # Sort slots by date to prioritize earlier dates
        sorted_slots = sorted(availabilities['content'], key=lambda x: x['date'])
        
        # If slot_choice is out of range, use the first slot
        if slot_choice >= len(sorted_slots):
            slot_choice = 0
            logger.warning(f"Slot choice {slot_choice} out of range, using first available slot")
        
        # Use the selected slot (or return availability list if slot_choice is -1)
        if slot_choice == -1:
            # Return the list of availabilities for user selection
            slot_info = []
            for i, slot in enumerate(sorted_slots):
                slot_info.append({
                    "index": i,
                    "date": slot['date'],
                    "hospital": slot.get('hospital', {}).get('name', 'Unknown'),
                    "address": slot.get('site', {}).get('address', 'Unknown'),
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
        
        # Get the selected slot
        selected_slot = sorted_slots[slot_choice]
        diary_id = selected_slot['diary']['id']
        data_prenotazione = selected_slot['date']
        
        logger.info(f"Selected Appointment Details:")
        logger.info(f"Date: {data_prenotazione}")
        logger.info(f"Location: {selected_slot.get('hospital', {}).get('name', 'Unknown')}")
        
        # Step 7: Create pre-booking for the selected slot
        try:
            prebooking_result = book_appointment(
                process_id, 
                data_prenotazione, 
                diary_id, 
                service_cur, 
                nre, 
                fiscal_code
            )
            
            lock_id = prebooking_result['id']
            logger.info(f"Pre-booking successful. Lock ID: {lock_id}")
            
            # Step 8: Complete booking
            booking_result, booking_id = complete_booking(
                fiscal_code, 
                process_id, 
                nre, 
                phone_number, 
                email, 
                lock_id, 
                order_ids,
                data_prenotazione,
                diary_id
            )
            
            if not booking_id:
                return {"success": False, "message": "Prenotazione fallita: impossibile ottenere ID prenotazione"}
            
            logger.info(f"Booking completed. Booking ID: {booking_id}")
            
            # Step 9: Download the booking confirmation PDF
            pdf_path, pdf_content = get_booking_document(booking_id)
            
            # Step 10: Return booking information
            return {
                "success": True,
                "action": "booked",
                "booking_id": booking_id,
                "pdf_path": pdf_path,
                "pdf_content": pdf_content,
                "appointment_date": data_prenotazione,
                "hospital": selected_slot.get('hospital', {}).get('name', 'Unknown'),
                "address": selected_slot.get('site', {}).get('address', 'Unknown'),
                "service": service_name
            }
        
        except Exception as e:
            logger.error(f"Error booking slot {data_prenotazione}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "message": f"Errore durante la prenotazione: {str(e)}"}
            
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
    list: List of active bookings
    """
    url = f"{BASE_URL}/api/v3/process-apis/booking-management/bookings/search"
    
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
        "fiscalCode": fiscal_code,
        "statuses": ["PRENOTATA", "PRESA_IN_CARICO"]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, verify=False)
        response.raise_for_status()
        
        result = response.json()
        
        if 'content' in result:
            return {
                "success": True,
                "bookings": result['content']
            }
        else:
            return {
                "success": True,
                "bookings": []
            }
    except Exception as e:
        logger.error(f"Error getting user bookings: {str(e)}")
        return {
            "success": False,
            "message": f"Errore nel recupero delle prenotazioni: {str(e)}"
        }