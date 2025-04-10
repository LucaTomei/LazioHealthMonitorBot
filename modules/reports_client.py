import requests
import logging
import json
import os
from datetime import datetime
from io import BytesIO

# Importa il logger
from config import logger

def get_access_token():
    """
    Get access token from the Lazio Region API
    
    Returns:
        str: Access token for API authorization
    """
    # Token endpoint
    token_url = "https://gwapi-az.servicelazio.it/token"
    
    # Headers for token request
    token_headers = {
        "Host": "gwapi-az.servicelazio.it",
        "Connection": "keep-alive",
        "Accept-Encoding": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": "RLGEOAPP/2.2.0 (it.laziocrea.rlgeoapp; build:2.2.0; iOS 18.3.2) Alamofire/5.10.2",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Accept-Language": "it-IT;q=1.0",
        "Authorization": "Basic aFJaMkYxNkthcWQ5dzZxRldEVEhJbHg3UnVRYTpnaUVHbEp4a0Iza1VBdWRLdXZNdFBJaTVRc2th"
    }
    
    # Payload for token request
    token_data = {
        "grant_type": "client_credentials"
    }
    
    try:
        # Make the request for the token
        token_response = requests.post(token_url, headers=token_headers, data=token_data)
        
        # Check if the request was successful
        if token_response.status_code == 200:
            # Parse the JSON response
            token_json = token_response.json()
            
            # Extract the access token
            access_token = token_json.get("access_token")
            
            if access_token:
                return access_token
            else:
                logger.error("Error: Access token not found in response")
                return None
        else:
            logger.error(f"Error: Token request failed with status code {token_response.status_code}")
            logger.error(f"Response: {token_response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception occurred during token request: {str(e)}")
        return None

def download_reports(fiscal_number, password, tscns):
    """
    Download medical reports from Lazio Region health system
    
    Args:
        fiscal_number (str): Fiscal code of the patient
        password (str): Password for access
        tscns (str): TSCNS code
        
    Returns:
        list: List of reports retrieved from the system
    """
    # First, get the access token
    access_token = get_access_token()
    if not access_token:
        logger.error("Failed to obtain access token. Cannot proceed.")
        return None
    
    # API endpoint for reports
    url = "https://gwapi-az.servicelazio.it/escape/fse/query"
    
    # Request headers based on the HAR file
    headers = {
        "Host": "gwapi-az.servicelazio.it",
        "Accept-Encoding": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "it-IT;q=1.0",
        "User-Agent": "RLGEOAPP/2.2.0 (it.laziocrea.rlgeoapp; build:2.2.0; iOS 18.3.2) Alamofire/5.10.2",
        "Connection": "keep-alive",
        "Authorization": f"Bearer {access_token}"
    }
    
    # Request payload based on the HAR file
    payload = {
        "password": password,
        "tscns": tscns,
        "fiscal_number": fiscal_number
    }
    
    try:
        # Make the POST request
        response = requests.post(url, headers=headers, json=payload)
        
        # Check if the request was successful
        if response.status_code == 200:
            # Parse the JSON response
            reports = response.json()
            return reports
        else:
            logger.error(f"Error: Request failed with status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception occurred during reports download: {str(e)}")
        return None

def download_report_document(document_id, fiscal_number, password, tscns):
    """
    Download a specific report document by its ID
    
    Args:
        document_id (str): ID of the document to download
        fiscal_number (str): Fiscal code of the patient
        password (str): Password for access
        tscns (str): TSCNS code
        
    Returns:
        bytes: The binary content of the report document (usually PDF)
    """
    # First, get the access token
    access_token = get_access_token()
    if not access_token:
        logger.error("Failed to obtain access token. Cannot proceed with document download.")
        return None
    
    # API endpoint for document download
    url = f"https://gwapi-az.servicelazio.it/escape/fse/document/{document_id}"
    
    # Request headers
    headers = {
        "Host": "gwapi-az.servicelazio.it",
        "Accept-Encoding": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "it-IT;q=1.0",
        "User-Agent": "RLGEOAPP/2.2.0 (it.laziocrea.rlgeoapp; build:2.2.0; iOS 18.3.2) Alamofire/5.10.2",
        "Connection": "keep-alive",
        "Authorization": f"Bearer {access_token}"
    }
    
    # Request payload
    payload = {
        "password": password,
        "tscns": tscns,
        "fiscal_number": fiscal_number
    }
    
    try:
        # Make the POST request
        response = requests.post(url, headers=headers, json=payload)
        
        # Check if the request was successful
        if response.status_code == 200:
            # Get the binary content of the document
            content = response.content
            return content
        else:
            logger.error(f"Error: Document download failed with status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception occurred during document download: {str(e)}")
        return None

def download_all_report_documents(fiscal_number, password, tscns, output_dir="reports_pdf"):
    """
    Download all reports and their documents for a patient
    
    Args:
        fiscal_number (str): Fiscal code of the patient
        password (str): Password for access
        tscns (str): TSCNS code
        output_dir (str): Directory to save downloaded files
        
    Returns:
        dict: Summary of downloaded reports
    """
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # First, get the list of reports
    reports = download_reports(fiscal_number, password, tscns)
    if not reports:
        return {
            "success": False,
            "message": "Failed to retrieve reports list",
            "reports": []
        }
    
    # Prepare result structure
    result = {
        "success": True,
        "message": f"Retrieved {len(reports)} reports",
        "reports": []
    }
    
    # Download each report document
    for report in reports:
        document_id = report.get("document_id")
        if not document_id:
            logger.warning(f"Missing document_id in report: {report}")
            continue
        
        # Get document metadata for filename
        provider = report.get("provider", "unknown")
        document_type = report.get("document_type", "unknown")
        document_date = report.get("document_date", datetime.now().strftime("%Y%m%d"))
        
        # Clean filename parts
        provider = ''.join(c if c.isalnum() else '_' for c in provider)
        document_type = ''.join(c if c.isalnum() else '_' for c in document_type)
        
        # Create a filename
        filename = f"{document_date}_{document_type}_{provider}_{document_id}.pdf"
        filepath = os.path.join(output_dir, filename)
        
        # Download the document
        document_content = download_report_document(document_id, fiscal_number, password, tscns)
        
        if document_content:
            # Save the document
            try:
                with open(filepath, "wb") as f:
                    f.write(document_content)
                logger.info(f"Successfully saved report to {filepath}")
                
                # Add to result
                report_result = {
                    "document_id": document_id,
                    "provider": provider,
                    "document_type": document_type,
                    "document_date": document_date,
                    "filename": filename,
                    "filepath": filepath,
                    "success": True,
                    "content": document_content  # Include binary content for Telegram sending
                }
            except Exception as e:
                logger.error(f"Error saving file {filepath}: {str(e)}")
                report_result = {
                    "document_id": document_id,
                    "success": False,
                    "error": str(e)
                }
        else:
            logger.error(f"Failed to download document {document_id}")
            report_result = {
                "document_id": document_id,
                "success": False,
                "error": "Failed to download document content"
            }
        
        result["reports"].append(report_result)
    
    return result