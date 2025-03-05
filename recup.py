import requests
import base64

# Base configuration
BASE_URL = "https://recup-webapi-appmobile.regione.lazio.it"
AUTH_HEADER = "Basic QVBQTU9CSUxFX1NQRUNJQUw6UGs3alVTcDgzbUh4VDU4NA=="

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
    
    response = requests.post(token_url, headers=headers, data=data)
    return response.json()['access_token']

def update_device_token(access_token):
    """Update device token."""
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
    print(response.text)
    return response.json()

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
    
    response = requests.get(url, headers=headers, params=params)
    return response.json()

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
    
    response = requests.get(url, headers=headers, params=params)
    return response.json()

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
    
    response = requests.get(url, headers=headers, params=params)
    return response.json()

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
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()

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
    
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def main():
    for i in range(20):
        # Fiscal code of the patient
        fiscal_code = "SNSLSE98P47L182L"
        
        # Step 1: Get access token
        access_token = get_access_token()
        print("Access Token Obtained")
        
        # Step 2: Update device token
        update_device_token(access_token)
        print("Device Token Updated")
        
        # Step 3: Get patient information
        patient_info = get_patient_info(fiscal_code)
        patient_id = patient_info['content'][0]['id']
        print(f"Patient ID: {patient_id}")
        
        # Step 4: Get doctor information
        doctor_info = get_doctor_info(fiscal_code)
        print("Doctor Info Retrieved")
        
        # Step 5: Check prescription
        nre = "1200A4787459775"
        check_prescription_result = check_prescription(patient_id, nre)
        print("Prescription Checked")
        
        # Step 6: Get prescription details
        prescription_details = get_prescription_details(patient_id, nre)
        order_ids = prescription_details['details'][0]['service']['id']
        process_id = doctor_info['id']
        print(f"Order ID: {order_ids}")
        
        # Step 7: Get availabilities
        availabilities = get_availabilities(patient_id, process_id, nre, order_ids)
        print("Availabilities Retrieved")
        
        # Print out key findings
        for availability in availabilities['content']:
            print(f"Hospital: {availability['hospital']['name']}")
            print(f"Address: {availability['site']['address']}")
            print(f"Date: {availability['date']}")
            print(f"Price: {availability['price']}")
            print("---")
        import time
        time.sleep(3)
        print("Itereation: ", i)
        print("=====================================\n")

if __name__ == "__main__":
    main()