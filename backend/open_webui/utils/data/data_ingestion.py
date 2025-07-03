import base64
import json
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import httpx
import jwt
import os
import logging
from datetime import datetime
from urllib.parse import urlencode, quote
from typing import Optional, List
from open_webui.env import SRC_LOG_LEVELS

from open_webui.socket.main import (
    send_user_notification
)

from open_webui.models.data import DataSources, DataSourceModel

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

GCS_UPLOAD_URL = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"

def validate_config():
    """Validate configuration inputs"""
    # Validate ALLOWED_EXTENSIONS format
    if os.environ.get('ALLOWED_EXTENSIONS'):
        invalid_format = any(not ext.strip() or '.' in ext 
                           for ext in os.environ.get('ALLOWED_EXTENSIONS').split(','))
        
        if invalid_format:
            print('\n⚠️ Common Mistakes:')
            print('Good: "pdf,jpg,png"')
            print('Bad:  ".pdf,.jpg" (no periods)')
            print('Bad:  "pdf, jpg, " (trailing comma)')
            raise ValueError('Invalid ALLOWED_EXTENSIONS format')

    # Add other config checks here
    print('✅ Configuration validated successfully')

def format_bytes(bytes_value):
    """Helper for formatting bytes"""
    if not bytes_value:
        return '0 B'
    
    bytes_value = int(bytes_value)
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    size = bytes_value
    
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    
    return f"{size:.2f} {units[i]}"

def parse_date(date_str):
    """Helper to parse date strings"""
    return datetime.fromisoformat(date_str.replace('Z', '+00:00')) if date_str else None

def make_api_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None, auth=None):
    """
    Helper function to make API requests with error handling and retry logic.

    Args:
        url (str): The URL for the API request.
        method (str): The HTTP method (e.g., 'GET', 'POST').
        headers (dict, optional): Dictionary of HTTP headers.
        params (dict, optional): Dictionary of URL parameters.
        data (dict/str, optional): Request body data.
        stream (bool): Whether to stream the response content.
        auth_token (str, optional): OAuth token for Authorization header.

    Returns:
        requests.Response or dict: The Response object if streaming, otherwise JSON content.

    Raises:
        requests.exceptions.RequestException: If the request fails after retries.
    """
    if headers is None:
        headers = {}

    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'

    # Configure retry strategy
    # Total retries: 5 attempts (1 initial + 4 retries)
    # Backoff factor: 1s, 2s, 4s, 8s, 16s sleeps between retries
    # Status codes to retry: 429 (Too Many Requests), 5xx (Server Errors)
    # Allowed methods: Typically safe methods, plus POST/PUT/DELETE for idempotent operations
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "POST", "OPTIONS", "TRACE"]
    )

    # Create a session and mount the retry adapter
    # Using a session allows for connection pooling and applying retries globally
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        response = session.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            stream=stream,
            auth=auth
        )
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)

        # If it's not a stream, we can safely return the JSON content.
        # If it *is* a stream, we must return the response object so the caller
        # can use 'with' to ensure it's closed.
        return response.json() if not stream else response

    except requests.exceptions.ConnectionError as e:
        # This catches network-related errors, including ConnectionResetError
        log.error(f"Network connection error for URL: {url} - {e}", exc_info=True)
        raise # Re-raise the exception after logging
    except requests.exceptions.Timeout as e:
        # Catches request timeouts
        log.error(f"Request timed out for URL: {url} - {e}", exc_info=True)
        raise
    except requests.exceptions.HTTPError as e:
        # Catches HTTP errors (4xx or 5xx status codes)
        status_code = e.response.status_code if hasattr(e, 'response') and e.response is not None else 'N/A'
        response_text = e.response.text if hasattr(e, 'response') and e.response is not None else 'No response body'
        log.error(f"HTTP error for URL: {url} - Status: {status_code}, Response: {response_text} - {e}", exc_info=True)
        raise
    except requests.exceptions.RequestException as e:
        # Catches any other requests-related errors
        log.error(f"An unexpected API Request Error occurred for URL: {url} - {e}", exc_info=True)
        if hasattr(e, 'response') and e.response is not None:
            log.error(f"Response: {e.response.text}")
        raise
    finally:
        # In this setup, the session and its underlying connections are managed by the HTTPAdapter
        # and are typically reused. Explicitly closing the session here would prevent reuse.
        # For a function that's called repeatedly, it's generally better to let the session manage
        # its connection pool unless you have specific reasons to close it after each single request.
        # If you were creating a new session for every request, session.close() would be necessary.
        pass

def upload_to_gcs(file_content, destination_name, content_type, service_account_base64, GCS_BUCKET_NAME):
    """Upload file to GCS using REST API"""
    try:
        # Decode service account
        credentials_json = json.loads(
            base64.b64decode(service_account_base64).decode('utf-8')
        )
        
        # Get access token for GCS
        # Note: In a production environment, use a token service or library
        # This is a simplified example
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": create_jwt(credentials_json)
        }
        
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        gcs_token = token_response.json()['access_token']
        
        # Upload to GCS
        encoded_object_name = urlencode({'name': destination_name}) 
        upload_url = f"{GCS_UPLOAD_URL.format(bucket=GCS_BUCKET_NAME)}?{encoded_object_name}"
        
        headers = {
            'Authorization': f'Bearer {gcs_token}',
            'Content-Type': content_type or 'application/octet-stream'
        }
        
        upload_response = requests.post(
            upload_url,
            headers=headers,
            data=file_content
        )
        upload_response.raise_for_status()
        
        return upload_response.json()
        
    except Exception as error:
        print(f"GCS upload failed for {destination_name}: {str(error)}")
        raise # Re-raise to ensure calling functions are aware of the failure

def download_from_gcs(file_path, service_account_base64, GCS_BUCKET_NAME):
    """Download a file from GCS bucket using REST API with retry functionality"""
    try:
        # Decode service account
        credentials_json = json.loads(
            base64.b64decode(service_account_base64).decode('utf-8')
        )
        
        # Get access token for GCS
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": create_jwt(credentials_json)
        }
        
        # Use make_api_request for token request with retry functionality
        token_response = make_api_request(token_url, method='POST', data=token_data)
        gcs_token = token_response['access_token']
        
        # Download the object
        encoded_name = quote(file_path, safe='')
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o/{encoded_name}?alt=media"
        headers = {'Authorization': f'Bearer {gcs_token}'}
        
        # Use make_api_request for download with retry functionality and streaming
        response = make_api_request(url, method='GET', headers=headers, stream=True)
        
        # For streaming responses, we need to read the content
        content = response.content
        response.close()  # Close the streaming response
        
        return content
        
    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response and e.response.status_code == 404:
            # File doesn't exist - this is expected for new files
            return None
        else:
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else 'Unknown'
            response_text = e.response.text if hasattr(e, 'response') and e.response else 'No response'
            print(f"GCS download failed for {file_path}: HTTP {status_code} - {response_text}")
            return None
    except Exception as error:
        print(f"GCS download failed for {file_path}: {str(error)}")
        return None

def list_gcs_files(service_account_base64, GCS_BUCKET_NAME, prefix=None):
    """List files in GCS bucket using REST API with optional prefix filtering, pagination, and retry functionality"""
    try:
        # Decode service account
        credentials_json = json.loads(
            base64.b64decode(service_account_base64).decode('utf-8')
        )
        
        # Get access token for GCS
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": create_jwt(credentials_json) 
        }
        
        # Use make_api_request for token request with retry functionality
        token_response = make_api_request(token_url, method='POST', data=token_data)
        gcs_token = token_response['access_token']
        
        # List objects in bucket
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o"
        headers = {'Authorization': f'Bearer {gcs_token}'}
        
        all_objects = []
        page_token = None
        
        while True:
            params = {'maxResults': 1000}
            
            # Add prefix filter if provided
            if prefix:
                params['prefix'] = prefix
                
            if page_token:
                params['pageToken'] = page_token
            
            # Use make_api_request for listing with retry functionality
            result = make_api_request(url, method='GET', headers=headers, params=params)
            
            if 'items' in result:
                all_objects.extend(result['items'])
                
            if 'nextPageToken' in result:
                page_token = result['nextPageToken']
            else:
                break
                
        return all_objects
        
    except Exception as error:
        print(f"GCS listing failed: {str(error)}")
        return []
    
async def delete_gcs_folder(folder_path: str, service_account_base64: str, GCS_BUCKET_NAME: str) -> bool:
    """
    Deletes all files within a specified "folder" (prefix) in a GCS bucket asynchronously.

    Args:
        folder_path (str): The path to the "folder" (prefix) to delete, e.g., "user1/slack/".
                           Ensure it ends with a '/' if you want to delete only files *inside* it.
        service_account_base64 (str): Base64 encoded JSON string of the Google Service Account key.
        GCS_BUCKET_NAME (str): The name of the GCS bucket.

    Returns:
        bool: True if the folder (all identified files) was successfully deleted, False otherwise.
    """
    if not folder_path.endswith('/'):
        folder_path += '/' 
    
    try:
        credentials_json = json.loads(
            base64.b64decode(service_account_base64).decode('utf-8')
        )
        
        # Use httpx.AsyncClient for all HTTP requests within this function
        async with httpx.AsyncClient() as client:
            # 1. Get Access Token for GCS
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": create_jwt(credentials_json) # create_jwt is synchronous, which is fine here
            }
            
            # AWAIT the httpx.post call
            token_response = await client.post(token_url, data=token_data)
            token_response.raise_for_status() # httpx.HTTPStatusError for non-2xx responses
            gcs_token = token_response.json()['access_token']
            
            headers = {'Authorization': f'Bearer {gcs_token}'}
            
            # 2. List all objects within the specified folder_path (prefix)
            list_url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o"
            params = {'prefix': folder_path}
            
            all_files_to_delete = []
            next_page_token = None

            while True:
                current_params = params.copy()
                if next_page_token:
                    current_params['pageToken'] = next_page_token

                # AWAIT the httpx.get call
                list_response = await client.get(list_url, headers=headers, params=current_params)
                list_response.raise_for_status()
                list_data = list_response.json()
                
                if 'items' in list_data:
                    for item in list_data['items']:
                        all_files_to_delete.append(item['name'])
                
                next_page_token = list_data.get('nextPageToken')
                if not next_page_token:
                    break # No more pages

            if not all_files_to_delete:
                print(f"No files found in folder '{folder_path}' to delete.")
                return True # Folder is conceptually empty, so success

            print(f"Found {len(all_files_to_delete)} files in folder '{folder_path}'. Deleting...")

            # 3. Delete each identified file
            all_deleted = True
            for file_name in all_files_to_delete:
                encoded_file_name = quote(file_name, safe='') # Ensure proper URL encoding
                delete_url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o/{encoded_file_name}"
                
                # AWAIT the httpx.delete call
                delete_response = await client.delete(delete_url, headers=headers)
                try:
                    delete_response.raise_for_status() # httpx.HTTPStatusError for non-2xx responses
                    print(f"Successfully deleted: {file_name}")
                except httpx.HTTPStatusError as http_err: # <--- Change error type for httpx
                    print(f"Failed to delete {file_name}: HTTP Error {http_err.response.status_code} - {http_err.response.text}")
                    all_deleted = False
                except Exception as e:
                    print(f"An unexpected error occurred deleting {file_name}: {str(e)}")
                    all_deleted = False
            
            return all_deleted
        
    except httpx.RequestError as req_err: # <--- Change error type for httpx
        print(f"GCS folder deletion failed due to a request error: {str(req_err)}")
        if req_err.response is not None:
            print(f"Response: {req_err.response.text}")
        return False
    except Exception as error:
        print(f"GCS folder deletion failed for '{folder_path}': {str(error)}")
        return False

def delete_gcs_file(file_name, service_account_base64, GCS_BUCKET_NAME):
    """Delete a file from GCS bucket using REST API"""
    try:
        # Decode service account
        credentials_json = json.loads(
            base64.b64decode(service_account_base64).decode('utf-8')
        )
        
        # Get access token for GCS
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": create_jwt(credentials_json)
        }
        
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        gcs_token = token_response.json()['access_token']
        
        # Delete the object
        encoded_name = quote(file_name, safe='')
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o/{encoded_name}"
        headers = {'Authorization': f'Bearer {gcs_token}'}
        
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        
        return True
        
    except Exception as error:
        print(f"GCS delete failed for {file_name}: {str(error)}")
        return False

def create_jwt(service_account_info):
    """Create a JWT token for GCS authentication"""
    # Create JWT token for Google Cloud authentication
    now = int(time.time())
    
    payload = {
        'iss': service_account_info['client_email'],
        'scope': 'https://www.googleapis.com/auth/devstorage.read_write',
        'aud': 'https://oauth2.googleapis.com/token',
        'exp': now + 3600,  # 1 hour expiration
        'iat': now
    }
    
    # Sign with the private key
    private_key = service_account_info['private_key']
    token = jwt.encode(payload, private_key, algorithm='RS256')
    
    return token

async def update_data_source_sync_status(
    user_id: str,
    source_action: str, # This maps to the 'action' field in your DataSource model
    status: str
) -> Optional[DataSourceModel]:
    """
    Updates the sync status and last sync timestamp for a data source,
    identified by user ID and its 'action' field.

    Args:
        user_id (str): The ID of the user whose data source is to be updated.
        source_action (str): The 'action' identifier of the data source (e.g., "slack", "google").
        status (str): The new sync status (e.g., "syncing", "synced", "error", "unsynced").

    Returns:
        Optional[DataSourceModel]: The updated DataSourceModel if successful, None otherwise.
    """
    log.info(f"Attempting to update sync status for user {user_id}, source action '{source_action}' to '{status}'")
    
    try:
        # First, find the data source by its 'action' to get its 'name'
        # The 'action' field (e.g., "slack") is often more consistent as an identifier
        # than the 'name' (e.g., "Slack" which could be changed).
        # We need to fetch the full DataSourceModel to get its 'name'.
        user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
        
        target_data_source_name: Optional[str] = None
        for ds in user_data_sources:
            if ds.action == source_action:
                target_data_source_name = ds.name # Get the actual name from the found data source
                break
        
        if not target_data_source_name:
            log.warning(f"Data source with action '{source_action}' not found for user {user_id}. Cannot update sync status.")
            return None
        
        updated_source = DataSources.update_data_source_sync_status_by_name(
            user_id=user_id,
            source_name=target_data_source_name, # Use the actual name found
            sync_status=status,
            last_sync=int(time.time()) # Set last_sync to current Unix timestamp
        )
        
        if updated_source:

            # After successful sync
            await send_user_notification(
                user_id=user_id,
                event_name="data-source-updated",
                data={
                    "source": updated_source.name,
                    "status": updated_source.sync_status,
                    "message": f"{updated_source.name} sync status updated!",
                    "timestamp": int(time.time())
                }
            )

            log.info(f"Successfully updated sync status for data source '{source_action}' (Name: '{updated_source}') to '{status}' for user {user_id}.")
            return updated_source
        else:
            log.error(f"Failed to update sync status for data source '{source_action}' for user {user_id} using its name '{target_data_source_name}'.")
            return None

    except Exception as e:
        log.exception(f"An unexpected error occurred while updating sync status for user {user_id}, source action '{source_action}': {e}")
        return None