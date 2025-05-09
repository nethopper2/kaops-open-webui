import os
import base64
import json
import jwt
import time
import requests
import concurrent.futures
import io
import logging
from datetime import datetime
from urllib.parse import urlencode

from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

# Metrics tracking
total_api_calls = 0
script_start_time = time.time()

# Load environment variables
USER_ID = ""
GCS_BUCKET_NAME = ""
ALLOWED_EXTENSIONS = os.environ.get('ALLOWED_EXTENSIONS')
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '4'))  # Parallel processing workers
if ALLOWED_EXTENSIONS:
    ALLOWED_EXTENSIONS = [ext.strip().lower() for ext in ALLOWED_EXTENSIONS.split(',')]
else:
    ALLOWED_EXTENSIONS = None  # None means no filtering

EXCLUDED_FILES = [
    # --- System Files ---
    '.DS_Store',          # macOS folder metadata and attributes
    'Thumbs.db',          # Windows thumbnail cache database
    'desktop.ini',        # Windows folder customization settings
    'Icon\r',             # macOS custom folder icons (hidden carriage return character)
    '._*',                # macOS resource fork files (prefixed with ._)
    '*.tmp',              # Temporary files created by applications
    '*.temp',             # Alternate temporary file extension
    '.Spotlight-V100',    # macOS search index files
    '.TemporaryItems',    # macOS temporary system directory
    '.apdisk',            # macOS disk image helper files
    '.localized',         # macOS folder localization marker
    '.Trashes',           # System trash directory marker
    '$RECYCLE.BIN',       # Windows recycle bin system folder
]

# Google Drive API endpoints
DRIVE_API_BASE = 'https://www.googleapis.com/drive/v3'
GCS_UPLOAD_URL = 'https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o'

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

def make_api_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with error handling"""
    global total_api_calls
    total_api_calls += 1
    
    if headers is None:
        headers = {}
    
    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'
    
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            stream=stream
        )
        response.raise_for_status()
        return response.json() if not stream else response
    except requests.exceptions.RequestException as e:
        print(f"API Request Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        raise

def list_files_recursively(folder_id, auth_token, current_path='', all_files=None, drive_name=None):
    """Recursive file listing with path construction using REST API"""
    if all_files is None:
        all_files = []
    
    try:
        # List files in current folder with pagination
        page_token = None
        all_folder_files = []
        
        while True:
            params = {
                'q': f"'{folder_id}' in parents and trashed = false",
                'fields': "nextPageToken, files(id, name, mimeType, size, modifiedTime, createdTime, parents)",
                'pageSize': 1000,
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true'
            }
            
            # Add page token if we have one
            if page_token:
                params['pageToken'] = page_token
            
            url = f"{DRIVE_API_BASE}/files"
            results = make_api_request(url, params=params, auth_token=auth_token)
            
            # Add files from this page to our collection
            files = results.get('files', [])
            all_folder_files.extend(files)
            
            # Check if we have more pages
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        
        # Process each file/folder in current directory level
        for file in all_folder_files:
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                list_files_recursively(
                    file['id'],
                    auth_token,
                    f"{current_path}{file['name']}/", 
                    all_files,
                    drive_name
                )
            else:
                # Case-insensitive exclusion check
                if any(file['name'].lower() == pattern.lower() for pattern in EXCLUDED_FILES):
                    print(f"🚫 Excluded: {current_path}{file['name']}")
                    continue
                
                # Check for allowed extensions if specified
                if ALLOWED_EXTENSIONS:
                    file_ext = file['name'].split('.')[-1].lower() if '.' in file['name'] else ''
                    if file_ext not in ALLOWED_EXTENSIONS:
                        print(f"🔍 Skipped (extension): {file_ext} in {file['name']}")
                        continue
                
                # Add file to list with full path, including USER_ID and "Google Drive" folder
                file_info = file.copy()

                #Fetch USER_ID
                global USER_ID
                
                # Include USER_ID and "Google Drive" folder in the path
                if drive_name:
                    file_info['fullPath'] = f"{USER_ID}/Google Drive/{drive_name}/{current_path}{file['name']}"
                else:
                    file_info['fullPath'] = f"{USER_ID}/Google Drive/{current_path}{file['name']}"
                
                all_files.append(file_info)
    
    except Exception as error:
        print(f'Listing failed for folder {folder_id}: {str(error)}')
    
    return all_files

def get_user_drive_folders(auth_token):
    """Get both user's My Drive root folder and shared folders"""
    # First get user's root "My Drive" folder
    try:
        # This special query gets the root folder
        params = {
            'q': "'root' in parents",
            'fields': "files(id, name, mimeType)",
            'pageSize': 1
        }
        root_response = make_api_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
        
        # Get user's root folder ID (my drive)
        params = {
            'fields': "id"
        }
        my_drive = make_api_request(f"{DRIVE_API_BASE}/files/root", params=params, auth_token=auth_token)
        my_drive_id = my_drive.get('id')
        
        # Now get shared folders with pagination
        shared_folders = []
        page_token = None
        
        while True:
            params = {
                'q': "sharedWithMe = true",
                'fields': "nextPageToken, files(id, name, mimeType)",
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
                'pageSize': 100
            }
            
            if page_token:
                params['pageToken'] = page_token
                
            shared_response = make_api_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
            shared_folders.extend(shared_response.get('files', []))
            
            # Check if we have more pages
            page_token = shared_response.get('nextPageToken')
            if not page_token:
                break
        
        # Get shared drives with pagination
        shared_drives = []
        page_token = None
        
        while True:
            params = {
                'pageSize': 100,
                'fields': 'nextPageToken, drives(id, name)'
            }
            
            if page_token:
                params['pageToken'] = page_token
                
            shared_drives_response = make_api_request(f"{DRIVE_API_BASE}/drives", params=params, auth_token=auth_token)
            shared_drives.extend(shared_drives_response.get('drives', []))
            
            # Check if we have more pages
            page_token = shared_drives_response.get('nextPageToken')
            if not page_token:
                break
        
        # Get folders from shared drives with pagination
        shared_drives_folders = []
        
        for drive in shared_drives:
            drive_folders = []
            page_token = None
            
            while True:
                params = {
                    'driveId': drive['id'],
                    'supportsAllDrives': 'true',
                    'includeItemsFromAllDrives': 'true',
                    'corpora': "drive",
                    'pageSize': 100,
                    'fields': 'nextPageToken, files(id, name, mimeType)'
                }
                
                if page_token:
                    params['pageToken'] = page_token
                
                response = make_api_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
                drive_files = response.get('files', [])
                
                # Associate each file/folder with its parent drive name
                for file in drive_files:
                    file['driveName'] = drive['name']
                    file['driveId'] = drive['id']
                
                drive_folders.extend(drive_files)
                
                # Check if we have more pages
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            
            shared_drives_folders.extend(drive_folders)
        
        # Return both my drive and shared folders
        return {
            'my_drive': my_drive_id,
            'shared_folders': shared_folders,
            'shared_drives': shared_drives,
            'shared_drives_folders': shared_drives_folders
        }
        
    except Exception as error:
        print(f"Error getting drive folders: {str(error)}")
        return None

def download_file(file_id, auth_token, mime_type=None):
    """
    Download file content from Google Drive, handling Google's proprietary formats properly.
    For Google Docs, Sheets, Slides, etc., it uses the export endpoint.
    For regular files, it uses the standard download method.
    
    Args:
        file_id (str): The ID of the file to download
        auth_token (str): OAuth token for authentication
        mime_type (str, optional): The MIME type of the file, if known
        file_name (str, optional): The name of the file, if known
        
    Returns:
        tuple: (io.BytesIO, str, str) - (file content, file name, mime type)
    """
    
    # If mime_type or file_name not provided, fetch metadata
    if mime_type is None:
        metadata_url = f"{DRIVE_API_BASE}/files/{file_id}?fields=mimeType,name"
        metadata_response = make_api_request(
            metadata_url,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        if metadata_response.status_code != 200:
            raise Exception(f"Failed to get file metadata: {metadata_response.text}")
        
        file_metadata = metadata_response.json()
        
        # Only update if not provided
        if mime_type is None:
            mime_type = file_metadata.get("mimeType", "")
    
    # Define Google's proprietary formats and their export MIME types
    google_formats = {
        "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # Export as DOCX
        "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # Export as XLSX
        "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # Export as PPTX
        "application/vnd.google-apps.drawing": "application/pdf",  # Export as PDF
        "application/vnd.google-apps.script": "application/vnd.google-apps.script+json",  # Export as JSON
        "application/vnd.google-apps.form": "application/pdf",
        "application/vnd.google-apps.site": "text/plain",
        "application/vnd.google-apps.jam": "application/pdf",
        "application/vnd.google-apps.map": "application/pdf",
        "application/vnd.google-apps.folder": None,  # Folders can't be downloaded
    }
    
    # Handle based on file type
    file_content = io.BytesIO()
    
    # For Google's proprietary formats
    if mime_type in google_formats:
        export_mime_type = google_formats[mime_type]
        
        # If this format can't be exported (like a folder)
        if export_mime_type is None:
            raise Exception(f"Cannot download this type of file: {mime_type}")
        
        # Use export endpoint for Google formats
        export_url = f"{DRIVE_API_BASE}/files/{file_id}/export?mimeType={export_mime_type}"
        response = make_api_request(
            export_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            stream=True
        )
    else:
        # For regular files, use the standard download endpoint
        download_url = f"{DRIVE_API_BASE}/files/{file_id}?alt=media"
        response = make_api_request(
            download_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            stream=True
        )
    
    # Check if request was successful
    if response.status_code != 200:
        raise Exception(f"Failed to download file: {response.text}")
    
    # Read content into memory
    for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
        if chunk:
            file_content.write(chunk)
    
    file_content.seek(0)
    return file_content

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
            "assertion": create_jwt(credentials_json)  # You'd need to implement this function
        }
        
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        gcs_token = token_response.json()['access_token']
        
        # Upload to GCS
        encoded_object_name = urlencode({'name': destination_name}, safe='')
        upload_url = GCS_UPLOAD_URL.format(bucket=GCS_BUCKET_NAME) + "?" + encoded_object_name
        
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

def list_gcs_files(service_account_base64, GCS_BUCKET_NAME):
    """List all files in GCS bucket using REST API with pagination"""
    try:
        # Decode service account
        credentials_json = json.loads(
            base64.b64decode(service_account_base64).decode('utf-8')
        )
        
        # Get access token for GCS
        # Note: In a production environment, use a token service or library
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": create_jwt(credentials_json) 
        }
        
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        gcs_token = token_response.json()['access_token']
        
        # List objects in bucket
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o"
        headers = {'Authorization': f'Bearer {gcs_token}'}
        
        all_objects = []
        page_token = None
        
        while True:
            params = {'maxResults': 1000}
            if page_token:
                params['pageToken'] = page_token
                
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()
            
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

def delete_gcs_file(file_name, service_account_base64):
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
        encoded_name = urlencode({'': file_name})[1:]  # Remove leading '='
        url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET_NAME}/o/{encoded_name}"
        headers = {'Authorization': f'Bearer {gcs_token}'}
        
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        
        return True
        
    except Exception as error:
        print(f"GCS delete failed for {file_name}: {str(error)}")
        return False

def process_folder(folder_id, folder_name, auth_token, all_files, drive_name=None):
    """Process a single folder and its contents"""
    folder_display_name = folder_name
    if drive_name:
        folder_display_name = f"{drive_name}/{folder_name}"
    
    print(f"Processing folder: {folder_display_name} (ID: {folder_id})")
    
    if drive_name:
        # If this is a shared drive folder, prepend the drive name to path
        return list_files_recursively(folder_id, auth_token, f"{folder_name}/", all_files, drive_name)
    else:
        return list_files_recursively(folder_id, auth_token, f"{folder_name}/", all_files)

def sync_drive_to_gcs(auth_token, service_account_base64):
    """Main function to sync Google Drive to Google Cloud Storage using a bearer token"""
    global total_api_calls
    global GCS_BUCKET_NAME
    
    # Check for required environment variables
    # validate_config()
    
    print('🔄 Starting recursive sync process...')
    
    uploaded_files = []
    deleted_files = []
    skipped_files = 0
    
    try:
        # Get user's folders (both My Drive and shared folders)
        drive_folders = get_user_drive_folders(auth_token)
        if not drive_folders:
            raise ValueError("Could not retrieve user's drive folders")
        
        # Process My Drive and shared folders in parallel
        all_files = []
        
        # Add My Drive with root processing
        folders_to_process = [
            {
                'id': drive_folders['my_drive'],
                'name': 'My Drive'
            }
        ]
        
        # Add all shared folders
        folders_to_process.extend(drive_folders['shared_folders'])

        # Process folders in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Create a list to hold the futures
            future_to_folder = {
                executor.submit(
                    process_folder, 
                    folder['id'], 
                    folder['name'], 
                    auth_token,
                    []
                ): folder for folder in folders_to_process
            }
            
            # Process completed futures
            for future in concurrent.futures.as_completed(future_to_folder):
                folder = future_to_folder[future]
                try:
                    folder_files = future.result()
                    print(f"Completed folder: {folder['name']} with {len(folder_files)} files")
                    all_files.extend(folder_files)
                except Exception as e:
                    print(f"Error processing folder {folder['name']}: {str(e)}")
        
        # Process shared drive folders separately, ensuring their paths are prefixed with drive name
        shared_drive_folders = {}
        for folder in drive_folders['shared_drives_folders']:
            drive_name = folder.get('driveName')
            if drive_name:
                # Group folders by drive
                if drive_name not in shared_drive_folders:
                    shared_drive_folders[drive_name] = []
                shared_drive_folders[drive_name].append(folder)
        
        # Process each shared drive's folders
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            shared_drive_futures = []
            
            for drive_name, folders in shared_drive_folders.items():
                for folder in folders:
                    future = executor.submit(
                        process_folder,
                        folder['id'],
                        folder['name'],
                        auth_token,
                        [],
                        drive_name  # Pass the drive name to prepend to paths
                    )
                    shared_drive_futures.append((future, folder, drive_name))
            
            # Process completed futures
            for future, folder, drive_name in shared_drive_futures:
                try:
                    drive_folder_files = future.result()
                    print(f"Completed shared drive folder: {drive_name}/{folder['name']} with {len(drive_folder_files)} files")
                    all_files.extend(drive_folder_files)
                except Exception as e:
                    print(f"Error processing shared drive folder {drive_name}/{folder['name']}: {str(e)}")
        
        print(f"Found {len(all_files)} files across all directories")
        
        # List all GCS files
        gcs_files = list_gcs_files(service_account_base64, GCS_BUCKET_NAME)
        gcs_file_map = {gcs_file['name']: gcs_file for gcs_file in gcs_files}
        drive_file_paths = {file['fullPath'] for file in all_files}

        #Fetch USER_ID
        global USER_ID
        
        # Delete orphaned GCS files that belong to this user
        user_prefix = f"{USER_ID}/Google Drive/"
        for gcs_name, gcs_file in gcs_file_map.items():
            # Only consider files that belong to this user's Google Drive folder
            if gcs_name.startswith(user_prefix) and gcs_name not in drive_file_paths:
                delete_gcs_file(gcs_name, service_account_base64)
                
                deleted_files.append({
                    'name': gcs_name,
                    'size': gcs_file.get('size'),
                    'timeCreated': gcs_file.get('timeCreated')
                })
                print(f"[{datetime.now().isoformat()}] Deleted orphan: {gcs_name}")
        
        # Process files in parallel for upload
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for file in all_files:
                # Check if file exists in GCS
                gcs_file = gcs_file_map.get(file['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not gcs_file:
                    needs_upload = True
                    reason = 'New file'
                else:
                    gcs_updated = parse_date(gcs_file.get('updated'))
                    drive_modified = parse_date(file.get('modifiedTime'))
                    
                    if drive_modified and gcs_updated and drive_modified > gcs_updated:
                        needs_upload = True
                        reason = f"Drive version newer ({file['modifiedTime']} > {gcs_file.get('updated')})"
                
                if needs_upload:
                    # Submit upload task to executor
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_file,
                                file,
                                auth_token,
                                service_account_base64,
                                GCS_BUCKET_NAME,
                                bool(gcs_file),
                                reason
                            ),
                            file
                        )
                    )
                else:
                    skipped_files += 1
            
            # Process completed uploads
            for future, file in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                except Exception as e:
                    print(f"Error uploading {file['fullPath']}: {str(e)}")
        
        # Enhanced summary
        print('\nSync Summary:')
        for file in uploaded_files:
            symbol = '+' if file['type'] == 'new' else '^'
            print(
                f" {symbol} {file['path']} | {format_bytes(file['size'])} | {file['durationMs']}ms | {file['reason']}"
            )
        
        for file in deleted_files:
            print(f" - {file['name']} | {format_bytes(file['size'])} | Created: {file['timeCreated']}")
        
        total_runtime = int((time.time() - script_start_time) * 1000)
        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_runtime/1000):.2f} seconds")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"📦 Files Processed: {len(all_files)}")
        print(f"🗑️  Orphans Removed: {len(deleted_files)}")
        
        print(f"\nTotal: +{len([f for f in uploaded_files if f['type'] == 'new'])} added, " +
              f"^{len([f for f in uploaded_files if f['type'] == 'updated'])} updated, " +
              f"-{len(deleted_files)} removed, {skipped_files} skipped")
    
    except Exception as error:
        print(f'Sync failed: {str(error)}')
        exit(1)

def download_and_upload_file(file, auth_token, service_account_base64, GCS_BUCKET_NAME, exists, reason):
    """Helper function to download a file and upload it to GCS"""
    start_time = time.time()
    
    try:
        # Download file from Drive
        file_content = download_file(file['id'], auth_token, file['mimeType'])
        
        # Upload to GCS
        result = upload_to_gcs(
            file_content, 
            file['fullPath'], 
            file.get('mimeType'),
            service_account_base64,
            GCS_BUCKET_NAME
        )
        
        upload_result = {
            'path': file['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': result.get('size'),
            'driveModified': file.get('modifiedTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason
        }
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing file {file['fullPath']}: {str(e)}")
        return None

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

def initiate_google_file_sync(user_id: str, token: str, creds: str, gcs_bucket_name: str):
    log.info(f'Sync Google Drive to Google Cloud Storage')
    log.info(f'User Open WebUI ID: {user_id}')
    log.info(f'GCS Bucket Name: {gcs_bucket_name}')

    global USER_ID 
    global GCS_BUCKET_NAME

    USER_ID = user_id
    GCS_BUCKET_NAME = gcs_bucket_name

    # Run the sync process
    sync_drive_to_gcs(token, creds)