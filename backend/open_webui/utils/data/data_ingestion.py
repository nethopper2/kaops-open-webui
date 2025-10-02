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
from typing import Optional, List, Dict, Any
from enum import Enum
from open_webui.env import SRC_LOG_LEVELS

from open_webui.socket.main import (
    send_user_notification
)

from open_webui.models.data import DataSources, DataSourceModel

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

GCS_UPLOAD_URL = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"

# ============================================================================
# STORAGE BACKEND CONFIGURATION
# ============================================================================

class StorageBackend(Enum):
    GCS = "gcs"
    PAI_DATA_SERVICE = "pai"

class StorageConfig:
    def __init__(self, backend: StorageBackend = None):
        # Determine backend from environment or parameter
        self.backend = backend or StorageBackend(
            os.environ.get('STORAGE_BACKEND', 'gcs').lower()
        )

        log.info(f"Backend to use: {self.backend}")
        
        # GCS Configuration
        self.service_account_base64 = os.environ.get('GCS_SERVICE_ACCOUNT_BASE64')
        self.gcs_bucket_name = os.environ.get('GCS_BUCKET_NAME')
        
        # PAI Data Service Configuration
        base_url = os.environ.get('NH_DATA_SERVICE_URL', 'http://localhost:4500')
        
        # Ensure /api/v1 is appended if NH_DATA_SERVICE_URL is set
        if 'NH_DATA_SERVICE_URL' in os.environ:
            # Remove trailing slash if present
            base_url = base_url.rstrip('/')
            # Add /api/v1 if not already present
            if not base_url.endswith('/api/v1'):
                base_url = f"{base_url}/api/v1"
        else:
            # Default case - ensure it has /api/v1
            base_url = 'http://localhost:4500/api/v1'
        
        self.pai_base_url = base_url
        self.pai_jwt_token = os.environ.get('NH_DATA_SERVICE_JWT_TOKEN')
        self.pai_jwt_secret = os.environ.get('JWT_SECRET_KEY')

        ENABLE_SSO_DATA_SYNC = os.getenv("ENABLE_SSO_DATA_SYNC")

        if ENABLE_SSO_DATA_SYNC:
            self._validate_config()

    def _validate_config(self):
        """Validate configuration based on selected backend"""
        if self.backend == StorageBackend.GCS:
            if not self.service_account_base64 or not self.gcs_bucket_name:
                raise ValueError("GCS backend requires GCS_SERVICE_ACCOUNT_BASE64 and GCS_BUCKET_NAME")
        elif self.backend == StorageBackend.PAI_DATA_SERVICE:
            if not self.pai_base_url:
                raise ValueError("PAI backend requires PAI_DATA_SERVICE_BASE_URL")
            if not self.pai_jwt_token and not self.pai_jwt_secret:
                raise ValueError("PAI backend requires PAI_DATA_SERVICE_JWT_TOKEN or PAI_DATA_SERVICE_JWT_SECRET")

# Global config instance
storage_config = StorageConfig()

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

def get_api_headers(auth_token: str = None) -> Dict[str, str]:
    """Get headers for pai-data-service API requests"""
    headers = {'Content-Type': 'application/json'}
    if auth_token or storage_config.pai_jwt_token:
        headers['Authorization'] = f'Bearer {auth_token or storage_config.pai_jwt_token}'
    return headers

def generate_pai_service_token(user_id: str) -> str:
    """Generate JWT token for pai-data-service authentication"""
    if storage_config.pai_jwt_token:
        return storage_config.pai_jwt_token
    
    if not storage_config.pai_jwt_secret:
        raise ValueError("No PAI JWT token or secret configured")
    
    payload = {
        'id': user_id,  # Note: pai-data-service expects 'id', not 'userId'
        'iat': int(time.time()),
        'exp': int(time.time()) + 3600  # 1 hour expiration
    }
    
    return jwt.encode(payload, storage_config.pai_jwt_secret, algorithm='HS256')

def make_api_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None, auth=None):
    """
    Helper function to make API requests with error handling and retry logic.
    """
    if headers is None:
        headers = {}

    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'

    # Configure retry strategy
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "POST", "OPTIONS", "TRACE"]
    )

    # Create a session and mount the retry adapter
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
        response.raise_for_status()

        return response.json() if not stream else response

    except requests.exceptions.ConnectionError as e:
        log.error(f"Network connection error for URL: {url} - {e}", exc_info=True)
        raise
    except requests.exceptions.Timeout as e:
        log.error(f"Request timed out for URL: {url} - {e}", exc_info=True)
        raise
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if hasattr(e, 'response') and e.response is not None else 'N/A'
        response_text = e.response.text if hasattr(e, 'response') and e.response is not None else 'No response body'
        log.error(f"HTTP error for URL: {url} - Status: {status_code}, Response: {response_text} - {e}", exc_info=True)
        raise
    except requests.exceptions.RequestException as e:
        log.error(f"An unexpected API Request Error occurred for URL: {url} - {e}", exc_info=True)
        if hasattr(e, 'response') and e.response is not None:
            log.error(f"Response: {e.response.text}")
        raise
    finally:
        pass

# ============================================================================
# GCS BACKEND FUNCTIONS (Phase 1-3)
# ============================================================================

def upload_to_gcs(file_content, destination_name, content_type, service_account_base64, GCS_BUCKET_NAME):
    """Upload file to GCS using REST API"""
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
        raise

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
        
        token_response = make_api_request(token_url, method='POST', data=token_data)
        gcs_token = token_response['access_token']
        
        # Download the object
        encoded_name = quote(file_path, safe='')
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o/{encoded_name}?alt=media"
        headers = {'Authorization': f'Bearer {gcs_token}'}
        
        response = make_api_request(url, method='GET', headers=headers, stream=True)
        
        content = response.content
        response.close()
        
        return content
        
    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response and e.response.status_code == 404:
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
    log.info(f"""List files in GCS bucket using REST API with optional prefix filtering, pagination, and retry functionality""")
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
        
        token_response = make_api_request(token_url, method='POST', data=token_data)
        gcs_token = token_response['access_token']
        
        # List objects in bucket
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o"
        headers = {'Authorization': f'Bearer {gcs_token}'}
        
        all_objects = []
        page_token = None
        
        while True:
            params = {'maxResults': 1000}
            
            if prefix:
                params['prefix'] = prefix
                
            if page_token:
                params['pageToken'] = page_token
            
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
    """Delete all files within a specified "folder" (prefix) in a GCS bucket asynchronously."""
    if not folder_path.endswith('/'):
        folder_path += '/' 
    
    try:
        credentials_json = json.loads(
            base64.b64decode(service_account_base64).decode('utf-8')
        )
        
        async with httpx.AsyncClient() as client:
            # Get Access Token for GCS
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": create_jwt(credentials_json)
            }
            
            token_response = await client.post(token_url, data=token_data)
            token_response.raise_for_status()
            gcs_token = token_response.json()['access_token']
            
            headers = {'Authorization': f'Bearer {gcs_token}'}
            
            # List all objects within the specified folder_path (prefix)
            list_url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o"
            params = {'prefix': folder_path}
            
            all_files_to_delete = []
            next_page_token = None

            while True:
                current_params = params.copy()
                if next_page_token:
                    current_params['pageToken'] = next_page_token

                list_response = await client.get(list_url, headers=headers, params=current_params)
                list_response.raise_for_status()
                list_data = list_response.json()
                
                if 'items' in list_data:
                    for item in list_data['items']:
                        all_files_to_delete.append(item['name'])
                
                next_page_token = list_data.get('nextPageToken')
                if not next_page_token:
                    break

            if not all_files_to_delete:
                print(f"No files found in folder '{folder_path}' to delete.")
                return True

            print(f"Found {len(all_files_to_delete)} files in folder '{folder_path}'. Deleting...")

            # Delete each identified file
            all_deleted = True
            for file_name in all_files_to_delete:
                encoded_file_name = quote(file_name, safe='')
                delete_url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o/{encoded_file_name}"
                
                delete_response = await client.delete(delete_url, headers=headers)
                try:
                    delete_response.raise_for_status()
                    print(f"Successfully deleted: {file_name}")
                except httpx.HTTPStatusError as http_err:
                    print(f"Failed to delete {file_name}: HTTP Error {http_err.response.status_code} - {http_err.response.text}")
                    all_deleted = False
                except Exception as e:
                    print(f"An unexpected error occurred deleting {file_name}: {str(e)}")
                    all_deleted = False
            
            return all_deleted
        
    except httpx.RequestError as req_err:
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

# ============================================================================
# NH DATA SERVICE BACKEND FUNCTIONS (Phase 4)
# ============================================================================

def list_pai_files(prefix: str = None, auth_token: str = None, max_results: int = 1000) -> List[Dict[str, Any]]:
    """List files using pai-data-service API"""
    try:
        url = f"{storage_config.pai_base_url}/files"
        params = {}
        if prefix:
            params['prefix'] = prefix
        if max_results:
            params['maxResults'] = max_results
            
        response = make_api_request(
            url, 
            method='GET', 
            headers=get_api_headers(auth_token),
            params=params
        )
        
        return response.get('files', [])
        
    except Exception as error:
        print(f"PAI Data Service listing failed: {str(error)}")
        return []

def upload_to_pai_service(file_content: bytes, destination_path: str, 
                         content_type: str = None, auth_token: str = None) -> bool:
    """Upload file using pai-data-service API"""
    try:
        url = f"{storage_config.pai_base_url}/files/{destination_path}"
        
        files = {
            'file': (destination_path.split('/')[-1], file_content, content_type or 'application/octet-stream')
        }
        
        headers = get_api_headers(auth_token)
        headers.pop('Content-Type', None)
        
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        
        return True
        
    except Exception as error:
        print(f"PAI Data Service upload failed for {destination_path}: {str(error)}")
        return False

def download_from_pai_service(file_path: str, auth_token: str = None) -> Optional[bytes]:
    """Download file using pai-data-service API"""
    try:
        url = f"{storage_config.pai_base_url}/files/{file_path}/download"
        
        response = make_api_request(
            url,
            method='GET',
            headers=get_api_headers(auth_token),
            stream=True
        )
        
        content = response.content
        response.close()
        return content
        
    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response and e.response.status_code == 404:
            return None
        else:
            print(f"PAI Data Service download failed for {file_path}: {str(e)}")
            return None
    except Exception as error:
        print(f"PAI Data Service download failed for {file_path}: {str(error)}")
        return None

def delete_pai_file(file_path: str, auth_token: str = None) -> bool:
    """Delete file using pai-data-service API"""
    try:
        url = f"{storage_config.pai_base_url}/files/{file_path}"
        
        response = make_api_request(
            url,
            method='DELETE',
            headers=get_api_headers(auth_token)
        )
        
        return True
        
    except Exception as error:
        print(f"PAI Data Service delete failed for {file_path}: {str(error)}")
        return False

async def delete_pai_folder(folder_path: str, auth_token: str = None) -> bool:
    """Delete folder using pai-data-service API"""
    try:
        if not folder_path.endswith('/'):
            folder_path += '/'
            
        url = f"{storage_config.pai_base_url}/folders/{folder_path.rstrip('/')}"
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=get_api_headers(auth_token))
            response.raise_for_status()
            
        return True
        
    except Exception as error:
        print(f"PAI Data Service folder deletion failed for '{folder_path}': {str(error)}")
        return False

# ============================================================================
# UNIFIED STORAGE INTERFACE
# ============================================================================

def list_files_unified(prefix: str = None, max_results: int = 1000, user_id: str = None) -> List[Dict[str, Any]]:
    """List files using configured storage backend"""
    if storage_config.backend == StorageBackend.GCS:
        return list_gcs_files(
            storage_config.service_account_base64,
            storage_config.gcs_bucket_name,
            prefix
        )
    elif storage_config.backend == StorageBackend.PAI_DATA_SERVICE:
        auth_token = generate_pai_service_token(user_id) if user_id else None
        return list_pai_files(prefix, auth_token, max_results)
    else:
        raise ValueError(f"Unsupported storage backend: {storage_config.backend}")

def upload_file_unified(file_content: bytes, destination_path: str, content_type: str = None, user_id: str = None) -> bool:
    """Upload file using configured storage backend"""
    if storage_config.backend == StorageBackend.GCS:
        return upload_to_gcs(
            file_content,
            destination_path,
            content_type,
            storage_config.service_account_base64,
            storage_config.gcs_bucket_name
        )
    elif storage_config.backend == StorageBackend.PAI_DATA_SERVICE:
        auth_token = generate_pai_service_token(user_id) if user_id else None
        return upload_to_pai_service(file_content, destination_path, content_type, auth_token)
    else:
        raise ValueError(f"Unsupported storage backend: {storage_config.backend}")

def download_file_unified(file_path: str, user_id: str = None) -> Optional[bytes]:
    """Download file using configured storage backend"""
    if storage_config.backend == StorageBackend.GCS:
        return download_from_gcs(
            file_path,
            storage_config.service_account_base64,
            storage_config.gcs_bucket_name
        )
    elif storage_config.backend == StorageBackend.PAI_DATA_SERVICE:
        auth_token = generate_pai_service_token(user_id) if user_id else None
        return download_from_pai_service(file_path, auth_token)
    else:
        raise ValueError(f"Unsupported storage backend: {storage_config.backend}")

def delete_file_unified(file_path: str, user_id: str = None) -> bool:
    """Delete file using configured storage backend"""
    if storage_config.backend == StorageBackend.GCS:
        return delete_gcs_file(
            file_path,
            storage_config.service_account_base64,
            storage_config.gcs_bucket_name
        )
    elif storage_config.backend == StorageBackend.PAI_DATA_SERVICE:
        auth_token = generate_pai_service_token(user_id) if user_id else None
        return delete_pai_file(file_path, auth_token)
    else:
        raise ValueError(f"Unsupported storage backend: {storage_config.backend}")

async def delete_folder_unified(folder_path: str, user_id: str = None) -> bool:
    """Delete folder using configured storage backend"""
    if storage_config.backend == StorageBackend.GCS:
        return await delete_gcs_folder(
            folder_path,
            storage_config.service_account_base64,
            storage_config.gcs_bucket_name
        )
    elif storage_config.backend == StorageBackend.PAI_DATA_SERVICE:
        auth_token = generate_pai_service_token(user_id) if user_id else None
        return await delete_pai_folder(folder_path, auth_token)
    else:
        raise ValueError(f"Unsupported storage backend: {storage_config.backend}")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_jwt(service_account_info):
    """Create a JWT token for GCS authentication"""
    now = int(time.time())
    
    payload = {
        'iss': service_account_info['client_email'],
        'scope': 'https://www.googleapis.com/auth/devstorage.read_write',
        'aud': 'https://oauth2.googleapis.com/token',
        'exp': now + 3600,
        'iat': now
    }
    
    private_key = service_account_info['private_key']
    token = jwt.encode(payload, private_key, algorithm='RS256')
    
    return token

async def update_data_source_sync_status(
    user_id: str,
    source_action: str,
    layer: str,
    status: str
) -> Optional[DataSourceModel]:
    """Updates the sync status and last sync timestamp for a data source"""
    log.info(f"Attempting to update sync status for user {user_id}, source action '{source_action}' to '{status}'")
    
    try:
        user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
        
        target_data_source_name: Optional[str] = None
        for ds in user_data_sources:
            if ds.action == source_action and ds.layer == layer:
                target_data_source_name = ds.name
                break
        
        if not target_data_source_name:
            log.warning(f"Data source with action '{source_action}' not found for user {user_id}. Cannot update sync status.")
            return None
        
        updated_source = DataSources.update_data_source_sync_status_by_name(
            user_id=user_id,
            source_name=target_data_source_name,
            layer_name=layer,
            sync_status=status,
            last_sync=int(time.time())
        )
        
        if updated_source:
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

# ============================================================================
# BACKEND CONFIGURATION FUNCTIONS (For External Use)
# ============================================================================

def configure_storage_backend(backend: str, **kwargs):
    """Configure storage backend dynamically
    
    Args:
        backend (str): Backend type ('gcs' or 'pai')
        **kwargs: Backend-specific configuration options
    """
    global storage_config
    storage_config = StorageConfig(StorageBackend(backend.lower()))
    
    # Override with provided parameters
    for key, value in kwargs.items():
        if hasattr(storage_config, key):
            setattr(storage_config, key, value)
    
    # Re-validate configuration
    storage_config._validate_config()

def get_current_backend() -> str:
    """Get currently configured storage backend"""
    return storage_config.backend.value