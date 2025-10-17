import os
import time
import requests
import concurrent.futures
import io
import logging
from datetime import datetime
from urllib.parse import urlencode
import traceback

from open_webui.env import SRC_LOG_LEVELS

# Import unified storage functions
from open_webui.utils.data.data_ingestion import (
    make_api_request, format_bytes, parse_date, update_data_source_sync_status,
    # Use unified storage interface
    list_files_unified, upload_file_unified, download_file_unified, 
    delete_file_unified, delete_folder_unified,
    # Keep specific backend functions for backward compatibility
    upload_to_gcs, list_gcs_files, delete_gcs_file,
    upload_to_pai_service, list_pai_files, delete_pai_file,
    # Backend configuration
    configure_storage_backend, get_current_backend
)
from open_webui.models.data import DataSources

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

# Global socketio instance for progress updates
sio = None

def set_socketio_instance(socketio_instance):
    """Set the socketio instance for progress updates"""
    global sio
    sio = socketio_instance

async def emit_sync_progress(user_id: str, provider: str, layer: str, progress_data: dict):
    """Emit sync progress update via WebSocket"""
    global sio
    if sio:
        try:
            log.info(f"Emitting sync progress for user {user_id}: {progress_data}")
            await sio.emit("sync_progress", {
                "user_id": user_id,
                "provider": provider,
                "layer": layer,
                **progress_data
            }, to=f"user_{user_id}")
        except Exception as e:
            log.error(f"Failed to emit sync progress: {e}")
    else:
        log.warning("Socket.IO instance not available for progress updates")

# Metrics tracking
total_api_calls = 0
script_start_time = 0

# Load environment variables
USER_ID = ""
GCS_BUCKET_NAME = ""  # Kept for backward compatibility
ALLOWED_EXTENSIONS = os.environ.get('ALLOWED_EXTENSIONS')
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '4'))
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB in bytes

if ALLOWED_EXTENSIONS:
    ALLOWED_EXTENSIONS = [ext.strip().lower() for ext in ALLOWED_EXTENSIONS.split(',')]
else:
    ALLOWED_EXTENSIONS = None

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
GMAIL_API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me/messages'

def make_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with error handling"""
    global total_api_calls
    total_api_calls += 1
    
    return make_api_request(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)

def is_file_size_valid(size):
    """Check if file size is within the allowed limit"""
    if size and size > MAX_FILE_SIZE:
        print(f"Skipping file (size {format_bytes(size)} exceeds {format_bytes(MAX_FILE_SIZE)} limit)")
        return False
    return True

# ============================================================================
# GMAIL SYNC FUNCTIONS
# ============================================================================

def list_gmail_messages(auth_token, query='', max_results=500):
    """List Gmail messages with optional query filter"""
    try:
        all_messages = []
        next_page_token = None
        
        while True:
            params = {
                'maxResults': min(max_results - len(all_messages), 500), # Gmail API limit is 500
                'q': query
            }
            
            if next_page_token:
                params['pageToken'] = next_page_token
            
            url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages"
            response = make_request(url, params=params, auth_token=auth_token)
            
            messages = response.get('messages', [])
            all_messages.extend(messages)
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token or len(all_messages) >= max_results:
                break
        
        return all_messages[:max_results]
        
    except Exception as error:
        print(f"Error listing Gmail messages: {str(error)}")
        log.error(f"Error in list_gmail_messages:", exc_info=True)
        return []

def get_gmail_message(message_id, auth_token):
    """Get full Gmail message content"""
    try:
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
        params = {'format': 'full'}
        
        message = make_request(url, params=params, auth_token=auth_token)
        return message
        
    except Exception as error:
        print(f"Error getting Gmail message {message_id}: {str(error)}")
        log.error(f"Error in get_gmail_message for {message_id}:", exc_info=True)
        return None

def extract_email_content(message):
    """Extract readable content from Gmail message"""
    try:
        headers = message.get('payload', {}).get('headers', [])
        
        email_data = {
            'id': message.get('id'),
            'threadId': message.get('threadId'),
            'snippet': message.get('snippet', ''),
            'internalDate': message.get('internalDate'),
            'subject': '', 'from': '', 'to': '', 'date': '', 'body': ''
        }
        
        # Parse headers
        for header in headers:
            name = header.get('name', '').lower()
            value = header.get('value', '')
            
            if name == 'subject':
                email_data['subject'] = value
            elif name == 'from':
                email_data['from'] = value
            elif name == 'to':
                email_data['to'] = value
            elif name == 'date':
                email_data['date'] = value
        
        # Extract body content recursively
        def extract_body_recursive(payload):
            body_text = ""
            
            if 'parts' in payload:
                for part in payload['parts']:
                    body_text += extract_body_recursive(part)
            else:
                mime_type = payload.get('mimeType', '')
                body = payload.get('body', {})
                
                if mime_type in ['text/plain', 'text/html'] and 'data' in body:
                    import base64
                    decoded_data = base64.urlsafe_b64decode(body['data']).decode('utf-8', errors='ignore')
                    body_text += decoded_data + "\n"
            
            return body_text
        
        email_data['body'] = extract_body_recursive(message.get('payload', {}))
        return email_data
        
    except Exception as error:
        print(f"Error extracting email content: {str(error)}")
        log.error(f"Error in extract_email_content:", exc_info=True)
        return None

def convert_email_to_text(email_data):
    """Convert email data to readable text format for storage"""
    try:
        text_content = f"""Subject: {email_data.get('subject', 'No Subject')}
        From: {email_data.get('from', 'Unknown')}
        To: {email_data.get('to', 'Unknown')}
        Date: {email_data.get('date', 'Unknown')}
        Message ID: {email_data.get('id', 'Unknown')}
        Thread ID: {email_data.get('threadId', 'Unknown')}
        {email_data.get('body', 'No content available')}
        """
        return text_content
        
    except Exception as error:
        print(f"Error converting email to text: {str(error)}")
        log.error(f"Error in convert_email_to_text:", exc_info=True)
        return ""

async def sync_gmail_to_storage(auth_token, query='', max_emails=1000, user_id=None):
    """Sync Gmail messages to configured storage backend"""
    global USER_ID, total_api_calls
    
    current_backend = get_current_backend()
    print(f'🔄 Starting Gmail sync process using {current_backend} backend...')
    
    uploaded_files = []
    skipped_files = 0
    
    try:
        # Get list of Gmail messages
        print(f"Fetching Gmail messages with query: '{query}' (max: {max_emails})")
        messages = list_gmail_messages(auth_token, query, max_emails)
        print(f"Found {len(messages)} Gmail messages")
        
        # Get existing Gmail files using unified interface
        print("Checking existing Gmail files in storage...")
        gmail_prefix = f"userResources/{USER_ID}/Google/Gmail/"
        existing_files = list_files_unified(prefix=gmail_prefix, user_id=USER_ID)
        
        # Handle different response formats from backends
        existing_email_files = set()
        for file in existing_files:
            file_name = file.get('name') or file.get('key', '')
            if file_name and file_name.startswith(gmail_prefix):
                existing_email_files.add(file_name)
        
        print(f"Found {len(existing_email_files)} existing Gmail files in storage")
        
        # Process messages in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for i, message in enumerate(messages):
                message_id = message.get('id')
                if not message_id:
                    continue
                
                # Create file path for email
                email_path = f"userResources/{USER_ID}/Google/Gmail/email_{message_id}.txt"
                
                # Check if email already exists
                if email_path in existing_email_files:
                    print(f"⏭️  Skipping existing email: {message_id}")
                    skipped_files += 1
                    continue
                
                # Submit email processing task
                futures.append(
                    (
                        executor.submit(
                            download_and_upload_email,
                            message_id,
                            email_path,
                            auth_token
                        ),
                        message_id
                    )
                )
            
            # Process completed uploads
            for future, message_id in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                    else:
                        skipped_files += 1
                except Exception as e:
                    print(f"Error processing email {message_id}: {str(e)}")
                    log.error(f"Error processing email {message_id}:", exc_info=True)
                    skipped_files += 1
        
        # Summary
        print(f"\nGmail Sync Summary ({current_backend}):")
        print(f"📧 Emails processed: {len(messages)}")
        print(f"📤 Emails uploaded: {len(uploaded_files)}")
        print(f"⏭️  Emails skipped: {skipped_files}")

        await update_data_source_sync_status(user_id, 'google', 'gmail', 'embedding')
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files,
            'total_processed': len(messages),
            'backend': current_backend
        }
        
    except Exception as error:
        print(f"Gmail sync failed: {str(error)}")
        log.error(f"Gmail sync failed:", exc_info=True)
        raise error

def download_and_upload_email(message_id, email_path, auth_token):
    """Download Gmail message and upload using unified storage interface"""
    start_time = time.time()
    
    try:
        # Get full message content
        message = get_gmail_message(message_id, auth_token)
        if not message:
            return None
        
        # Extract email content
        email_data = extract_email_content(message)
        if not email_data:
            return None
        
        # Convert to text format
        email_text = convert_email_to_text(email_data)
        if not email_text:
            return None
        
        content_size = len(email_text.encode('utf-8'))
        
        # Check file size before uploading
        if not is_file_size_valid(content_size):
            print(f"Skipping Gmail message (too large): {email_data.get('subject', 'No Subject')} - {format_bytes(content_size)}")
            return None
        
        # Upload using unified interface
        success = upload_file_unified(
            email_text.encode('utf-8'),
            email_path,
            'text/plain',
            USER_ID
        )
        
        if not success:
            return None
        
        upload_result = {
            'path': email_path,
            'type': 'new',
            'size': content_size,
            'subject': email_data.get('subject', 'No Subject'),
            'durationMs': int((time.time() - start_time) * 1000),
            'backend': get_current_backend()
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded email: {email_data.get('subject', 'No Subject')}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing email {message_id}: {str(e)}")
        log.error(f"Error in download_and_upload_email for {message_id}:", exc_info=True)
        return None

# ============================================================================
# GOOGLE DRIVE SYNC FUNCTIONS
# ============================================================================

def list_files_recursively(folder_id, auth_token, current_path='', all_files=None, drive_name=None, skipped_reasons=None):
    """Recursive file listing with path construction using REST API"""
    global USER_ID
    if all_files is None:
        all_files = []
    
    try:
        # List files in current folder with pagination
        page_token = None
        all_folder_files = []
        
        while True:
            params = {
                'q': f"'{folder_id}' in parents and trashed = false",
                'fields': "nextPageToken, files(id, name, mimeType, size, modifiedTime, createdTime, parents, shortcutDetails)",
                'pageSize': 1000,
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true'
            }
            
            if page_token:
                params['pageToken'] = page_token
            
            url = f"{DRIVE_API_BASE}/files"
            results = make_request(url, params=params, auth_token=auth_token)
            
            files = results.get('files', [])
            all_folder_files.extend(files)
            
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        
        # Process each file/folder in current directory level
        for file in all_folder_files:
            # Handle folder
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                list_files_recursively(
                    file['id'], auth_token, f"{current_path}{file['name']}/", 
                    all_files, drive_name, skipped_reasons
                )
            # Resolve folder shortcuts: follow targetId if the shortcut points to a folder
            elif file['mimeType'] == 'application/vnd.google-apps.shortcut':
                shortcut = file.get('shortcutDetails') or {}
                target_mime = shortcut.get('targetMimeType')
                target_id = shortcut.get('targetId')
                if target_mime == 'application/vnd.google-apps.folder' and target_id:
                    # Recurse into the shortcut target, keeping the shortcut's visible name in path
                    list_files_recursively(
                        target_id, auth_token, f"{current_path}{file['name']}/", all_files, drive_name, skipped_reasons
                    )
                else:
                    # Skip file shortcuts for now to avoid permission/403 issues
                    print(f"🔗 Skipping Drive file shortcut: {current_path}{file['name']}")
                    skipped_reasons['shortcut'] += 1
            else:
                # Case-insensitive exclusion check
                if any(file['name'].lower() == pattern.lower() for pattern in EXCLUDED_FILES):
                    print(f"🚫 Excluded: {current_path}{file['name']}")
                    skipped_reasons['other'] += 1
                    continue
                
                # Check file size before processing
                file_size = int(file.get('size', 0)) if file.get('size') else 0
                if not is_file_size_valid(file_size):
                    print(f"Skipped (size limit): {current_path}{file['name']} - {format_bytes(file_size)}")
                    skipped_reasons['size'] += 1
                    continue
                
                # Check for allowed extensions if specified
                if ALLOWED_EXTENSIONS:
                    file_ext = file['name'].split('.')[-1].lower() if '.' in file['name'] else ''
                    if file_ext not in ALLOWED_EXTENSIONS:
                        print(f"🔍 Skipped (extension): {file_ext} in {file['name']}")
                        skipped_reasons['extension'] += 1
                        continue
                
                # Add file to list with full path
                file_info = file.copy()
                
                # Build path relative to the "Google Drive" root; process_folder supplies top-level segments
                file_info['fullPath'] = f"userResources/{USER_ID}/Google/Google Drive/{current_path}{file['name']}"
                
                all_files.append(file_info)
    
    except Exception as error:
        print(f'Listing failed for folder {folder_id}: {str(error)}')
    
    return all_files

def get_user_drive_folders(auth_token):
    """Get both user's My Drive root folder and shared folders"""
    try:
        # Get user's root folder ID (my drive)
        params = {'fields': "id"}
        my_drive = make_request(f"{DRIVE_API_BASE}/files/root", params=params, auth_token=auth_token)
        my_drive_id = my_drive.get('id')
        
        # Get shared folders with pagination
        shared_folders = []
        page_token = None
        
        while True:
            params = {
                'q': "sharedWithMe = true and trashed = false",
                'fields': "nextPageToken, files(id, name, mimeType, driveId, size, modifiedTime, createdTime, parents)",
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
                'pageSize': 100
            }
            
            if page_token:
                params['pageToken'] = page_token
                
            shared_response = make_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
            # Process all shared-with-me items (both files and folders)
            for f in shared_response.get('files', []):
                # Include ALL shared-with-me items, even if they belong to shared drives
                shared_folders.append(f)
            
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
                
            shared_drives_response = make_request(f"{DRIVE_API_BASE}/drives", params=params, auth_token=auth_token)
            shared_drives.extend(shared_drives_response.get('drives', []))
            
            page_token = shared_drives_response.get('nextPageToken')
            if not page_token:
                break
        
        # Get folders from shared drives with pagination
        shared_drives_folders = []
        
        for drive in shared_drives:
            drive_folders = []
            page_token = None
            
            while True:
                # Only fetch top-level folders in this shared drive by using the driveId as parent
                params = {
                    'driveId': drive['id'],
                    'supportsAllDrives': 'true',
                    'includeItemsFromAllDrives': 'true',
                    'corpora': "drive",
                    'q': f"'{drive['id']}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'",
                    'pageSize': 100,
                    'fields': 'nextPageToken, files(id, name, mimeType)'
                }
                
                if page_token:
                    params['pageToken'] = page_token
                
                response = make_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
                drive_files = response.get('files', [])
                
                # Associate each file/folder with its parent drive name
                for file in drive_files:
                    file['driveName'] = drive['name']
                    file['driveId'] = drive['id']
                
                drive_folders.extend(drive_files)
                
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            
            shared_drives_folders.extend(drive_folders)
        
        return {
            'my_drive': my_drive_id,
            'shared_folders': shared_folders,
            'shared_drives': shared_drives,
            'shared_drives_folders': shared_drives_folders
        }
        
    except Exception as error:
        print(f"Error getting drive folders: {str(error)}")
        return None

# Helpers to fetch top-level files (not folders) for My Drive and Shared Drives
def list_my_drive_root_files(auth_token):
    try:
        root_files = []
        page_token = None

        while True:
            params = {
                'q': "'root' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                'fields': "nextPageToken, files(id, name, mimeType, size, modifiedTime, createdTime, parents)",
                'pageSize': 1000,
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true'
            }

            if page_token:
                params['pageToken'] = page_token

            url = f"{DRIVE_API_BASE}/files"
            results = make_request(url, params=params, auth_token=auth_token)

            files = results.get('files', [])
            root_files.extend(files)

            page_token = results.get('nextPageToken')
            if not page_token:
                break

        return root_files

    except Exception as error:
        print(f"Error getting My Drive root files: {str(error)}")
        return []

def list_shared_drive_root_files(drive_id, auth_token):
    try:
        drive_root_files = []
        page_token = None

        while True:
            params = {
                'driveId': drive_id,
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
                'corpora': 'drive',
                'q': f"'{drive_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                'pageSize': 100,
                'fields': 'nextPageToken, files(id, name, mimeType, size, modifiedTime, createdTime, parents)'
            }

            if page_token:
                params['pageToken'] = page_token

            response = make_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
            files = response.get('files', [])

            drive_root_files.extend(files)

            page_token = response.get('nextPageToken')
            if not page_token:
                break

        return drive_root_files

    except Exception as error:
        print(f"Error getting shared drive root files for {drive_id}: {str(error)}")
        return []

def get_my_drive_top_level_folders(auth_token):
    """List all top-level folders directly under My Drive (root)."""
    try:
        top_level_folders = []
        page_token = None

        while True:
            params = {
                'q': "'root' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'",
                'fields': "nextPageToken, files(id, name, mimeType)",
                'pageSize': 1000,
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true'
            }

            if page_token:
                params['pageToken'] = page_token

            url = f"{DRIVE_API_BASE}/files"
            results = make_request(url, params=params, auth_token=auth_token)

            folders = results.get('files', [])
            top_level_folders.extend(folders)

            page_token = results.get('nextPageToken')
            if not page_token:
                break

        return top_level_folders

    except Exception as error:
        print(f"Error getting My Drive top-level folders: {str(error)}")
        return []

def download_file(file_id, auth_token, mime_type=None):
    """Download file content from Google Drive, handling Google's proprietary formats"""
    
    # If mime_type not provided, fetch metadata
    if mime_type is None:
        metadata_url = f"{DRIVE_API_BASE}/files/{file_id}?fields=mimeType,name"
        metadata_response = make_request(
            metadata_url,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        if metadata_response.status_code != 200:
            raise Exception(f"Failed to get file metadata: {metadata_response.text}")
        
        file_metadata = metadata_response.json()
        mime_type = file_metadata.get("mimeType", "")
    
    # Define Google's proprietary formats and their export MIME types
    google_formats = {
        "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.google-apps.drawing": "application/pdf",
        "application/vnd.google-apps.script": "application/vnd.google-apps.script+json",
        "application/vnd.google-apps.form": "application/pdf",
        "application/vnd.google-apps.site": "text/plain",
        "application/vnd.google-apps.jam": "application/pdf",
        "application/vnd.google-apps.map": "application/pdf",
        "application/vnd.google-apps.folder": None,# Folders can't be downloaded
    }
    
    # Handle based on file type
    file_content = io.BytesIO()
    
    # For Google's proprietary formats
    if mime_type in google_formats:
        export_mime_type = google_formats[mime_type]
        
        if export_mime_type is None:
            raise Exception(f"Cannot download this type of file: {mime_type}")
        
        # Use export endpoint for Google formats
        export_url = f"{DRIVE_API_BASE}/files/{file_id}/export?mimeType={export_mime_type}"
        response = make_request(
            export_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            stream=True
        )
    else:
        # For regular files, use the standard download endpoint
        download_url = f"{DRIVE_API_BASE}/files/{file_id}?alt=media"
        response = make_request(
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

def process_folder(folder_id, folder_name, auth_token, all_files, drive_name=None, folder_type=None, skipped_reasons=None):
    """Process a single folder and its contents"""
    try:
        folder_display_name = folder_name
        if drive_name:
            folder_display_name = f"{drive_name}/{folder_name}"
        
        print(f"Processing folder: {folder_display_name} (ID: {folder_id}, Type: {folder_type})")
        
        # Determine top-level directory name based on folder type
        if folder_type == 'my_drive':
            top_level = "My Drive"
        elif folder_type == 'shared_with_me':
            top_level = "Shared with me"
        elif folder_type == 'shared_drive':
            top_level = "Shared drives"
        else:
            top_level = "My Drive"  # Default fallback
        
        if drive_name:
            return list_files_recursively(folder_id, auth_token, f"{top_level}/{drive_name}/{folder_name}/", all_files, drive_name, skipped_reasons)
        else:
            return list_files_recursively(folder_id, auth_token, f"{top_level}/{folder_name}/", all_files, None, skipped_reasons)
    except Exception as error:
        print(f'Listing failed for folder {folder_id}: {str(error)}')
        log.error(f"Error in process_folder for {folder_id}:", exc_info=True)

async def sync_drive_to_storage(auth_token, user_id):
    """Main function to sync Google Drive to configured storage backend"""
    global total_api_calls, GCS_BUCKET_NAME
    
    current_backend = get_current_backend()
    print(f'🔄 Starting recursive sync process using {current_backend} backend...')
    
    # Initialize progress tracking
    sync_start_time = int(time.time())
    
    # Phase 1: Starting
    print(f'----------------------------------------------------------------------')
    print(f'📋 Phase 1: Starting - Initializing sync process...')
    print(f'----------------------------------------------------------------------')
    
    # Emit initial phase update with discovery fields
    await emit_sync_progress(USER_ID, 'google', 'google_drive', {
        'phase': 'starting',
        'phase_name': 'Phase 1: Starting',
        'phase_description': 'preparing sync process',
        'files_processed': 0,
        'files_total': 0,
        'mb_processed': 0,
        'mb_total': 0,
        'sync_start_time': sync_start_time,
        'folders_found': 0,
        'files_found': 0,
        'total_size': 0
    })
    
    # Initialize skip counters
    skipped_reasons = {
        'size': 0,
        'extension': 0,
        'permission': 0,
        'shortcut': 0,
        'other': 0
    }
    
    uploaded_files = []
    deleted_files = []
    skipped_files = 0
    
    # Progress tracking
    files_processed = 0
    files_total = 0
    mb_processed = 0
    mb_total = 0
    
    # Discovery tracking
    folders_found = 0
    files_found = 0
    total_size = 0
    
    try:
        # Get user's folders (both My Drive and shared folders)
        drive_folders = get_user_drive_folders(auth_token)
        if not drive_folders:
            raise ValueError("Could not retrieve user's drive folders")
        
        # Process My Drive and shared folders in parallel
        all_files = []

        # Scope control: set GOOGLE_DRIVE_SYNC_SCOPE to limit sync scope
        sync_scope = os.environ.get('GOOGLE_DRIVE_SYNC_SCOPE', 'all').lower()
        include_my_drive = sync_scope in ('all', 'my_drive')
        include_shared_with_me = sync_scope in ('all', 'shared_with_me')
        include_shared_drives = sync_scope in ('all', 'shared_drives')

        folders_to_process = []
        
        # Emit initial discovery update
        await emit_sync_progress(USER_ID, 'google', 'google_drive', {
            'phase': 'starting',
            'phase_name': 'Phase 1: Starting',
            'phase_description': 'discovering folders and files...',
            'files_processed': 0,
            'files_total': 0,
            'mb_processed': 0,
            'mb_total': 0,
            'sync_start_time': sync_start_time,
            'folders_found': 0,
            'files_found': 0,
            'total_size': 0
        })

        if include_my_drive:
            # Discover top-level folders under My Drive (root) and process each independently
            my_drive_top_level = get_my_drive_top_level_folders(auth_token)
            folders_to_process.extend([
                {'id': f['id'], 'name': f['name'], 'type': 'my_drive'} for f in my_drive_top_level
            ])
            folders_found += len(my_drive_top_level)

            # Also include root-level files under My Drive
            my_drive_root_files = list_my_drive_root_files(auth_token)
            for f in my_drive_root_files:
                safe_name = f.get('name', '').replace('/', '-')
                f['fullPath'] = f"userResources/{USER_ID}/Google/Google Drive/My Drive/{safe_name}"
                all_files.append(f)
                files_found += 1
                total_size += int(f.get('size', 0) or 0)

        if include_shared_with_me:
            # Process shared-with-me items (both files and folders) in single pass
            for item in drive_folders['shared_folders']:
                item['type'] = 'shared_with_me'
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    # It's a folder - add to folders_to_process
                    folders_to_process.append(item)
                    folders_found += 1
                else:
                    # It's a file - add directly to all_files with sanitized path
                    safe_name = item['name'].replace('/', '-')
                    item['fullPath'] = f"userResources/{USER_ID}/Google/Google Drive/Shared with me/{safe_name}"
                    all_files.append(item)
                    files_found += 1
                    total_size += int(item.get('size', 0) or 0)

        # Add shared drive folders and files to the main processing queue
        if include_shared_drives:
            drive_id_to_name = {d['id']: d['name'] for d in drive_folders['shared_drives']}

            # Root-level folders (existing)
            for folder in drive_folders['shared_drives_folders']:
                drive_id = folder.get('driveId')
                if drive_id:
                    folder['type'] = 'shared_drive'
                    folder['driveName'] = drive_id_to_name.get(drive_id, folder.get('driveName') or 'Unknown Drive')
                    folders_to_process.append(folder)
                    folders_found += 1

            # Root-level files
            for d in drive_folders['shared_drives']:
                drive_id = d.get('id')
                drive_name = d.get('name')
                if not drive_id or not drive_name:
                    continue
                root_files = list_shared_drive_root_files(drive_id, auth_token)
                for f in root_files:
                    safe_name = f.get('name', '').replace('/', '-')
                    f['fullPath'] = f"userResources/{USER_ID}/Google/Google Drive/Shared drives/{drive_name}/{safe_name}"
                    all_files.append(f)
                    files_found += 1
                    total_size += int(f.get('size', 0) or 0)

        # Emit discovery progress update after initial collection
        await emit_sync_progress(USER_ID, 'google', 'google_drive', {
            'phase': 'starting',
            'phase_name': 'Phase 1: Starting',
            'phase_description': 'preparing sync process',
            'files_processed': 0,
            'files_total': 0,
            'mb_processed': 0,
            'mb_total': 0,
            'sync_start_time': sync_start_time,
            'folders_found': folders_found,
            'files_found': files_found,
            'total_size': total_size
        })

        # Process folders in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_folder = {}
            for folder in folders_to_process:
                if folder.get('type') == 'shared_drive':
                    future = executor.submit(
                        process_folder, folder['id'], folder['name'], 
                        auth_token, [], folder.get('driveName'), 'shared_drive', skipped_reasons
                    )
                else:
                    future = executor.submit(
                        process_folder, folder['id'], folder['name'], 
                        auth_token, [], None, folder.get('type'), skipped_reasons
                    )
                future_to_folder[future] = folder
            
            # Process completed futures
            for future in concurrent.futures.as_completed(future_to_folder):
                folder = future_to_folder[future]
                try:
                    folder_files = future.result()
                    folder_type = folder.get('type', 'unknown')
                    if folder_type == 'shared_drive':
                        drive_name = folder.get('driveName', 'Unknown Drive')
                        print(f"Completed shared drive folder: {drive_name}/{folder['name']} with {len(folder_files)} files")
                    else:
                        print(f"Completed folder: {folder['name']} with {len(folder_files)} files")
                    all_files.extend(folder_files)
                    
                    # Update discovery counts
                    files_found += len(folder_files)
                    for f in folder_files:
                        total_size += int(f.get('size', 0) or 0)
                    
                    # Emit discovery progress update
                    await emit_sync_progress(USER_ID, 'google', 'google_drive', {
                        'phase': 'starting',
                        'phase_name': 'Phase 1: Starting',
                        'phase_description': 'preparing sync process',
                        'files_processed': 0,
                        'files_total': 0,
                        'mb_processed': 0,
                        'mb_total': 0,
                        'sync_start_time': sync_start_time,
                        'folders_found': folders_found,
                        'files_found': files_found,
                        'total_size': total_size
                    })
                except Exception as e:
                    print(f"Error processing folder {folder['name']}: {str(e)}")
        
        print(f"Found {len(all_files)} files across all directories (after size filtering)")
        
        # Set total files and calculate total size for progress tracking
        files_total = len(all_files)
        mb_total = sum(int(f.get('size', 0)) for f in all_files)
        
        # Update progress in database
        await update_data_source_sync_status(
            USER_ID, 'google', 'google_drive', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        
        # Emit initial progress
        await emit_sync_progress(USER_ID, 'google', 'google_drive', {
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        # Phase 2: Discovery
        print(f'----------------------------------------------------------------------')
        print(f'🔍 Phase 2: Discovery - Analyzing existing files and determining sync plan...')
        print(f'----------------------------------------------------------------------')
        
        # Emit phase update
        await emit_sync_progress(USER_ID, 'google', 'google_drive', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing existing files and determining sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        # List all existing files using unified interface
        user_prefix = f"userResources/{USER_ID}/Google/Google Drive/"
        existing_files = list_files_unified(prefix=user_prefix, user_id=USER_ID)
        
        # Create file maps for comparison - handle different response formats
        existing_file_map = {}
        for file in existing_files:
            file_name = file.get('name') or file.get('key', '')
            if file_name:
                existing_file_map[file_name] = file
        
        # Ensure all files have fullPath before creating the set (shared-with-me files already have it)
        for file in all_files:
            if not file.get('fullPath'):
                # This shouldn't happen for files from folder traversal
                print(f"Warning: File missing fullPath: {file.get('name', 'unknown')}")
                continue
        
        drive_file_paths = {file['fullPath'] for file in all_files if file.get('fullPath')}

        # Delete orphaned files using unified interface
        for file_name, file_info in existing_file_map.items():
            if file_name.startswith(user_prefix) and file_name not in drive_file_paths:
                success = delete_file_unified(file_name, USER_ID)
                if success:
                    deleted_files.append({
                        'name': file_name,
                        'size': file_info.get('size', 0),
                        'timeCreated': file_info.get('timeCreated') or file_info.get('created_at')
                    })
                    print(f"[{datetime.now().isoformat()}] Deleted orphan: {file_name}")
        
        # Phase 3: Processing
        print(f'----------------------------------------------------------------------')
        print(f'⚡ Phase 3: Processing - Uploading new files and deleting orphans...')
        print(f'----------------------------------------------------------------------')
        
        # Emit phase update
        await emit_sync_progress(USER_ID, 'google', 'google_drive', {
            'phase': 'processing',
            'phase_name': 'Phase 3: Processing',
            'phase_description': 'uploading new files and deleting orphans',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        # Process files in parallel for upload
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for file in all_files:
                # Skip files without fullPath (shouldn't happen after our validation)
                if not file.get('fullPath'):
                    continue
                # Check if file exists
                existing_file = existing_file_map.get(file['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not existing_file:
                    needs_upload = True
                    reason = 'New file'
                else:
                    # Compare modification times - handle different response formats
                    existing_updated = parse_date(
                        existing_file.get('updated') or 
                        existing_file.get('lastModified') or 
                        existing_file.get('timeUpdated')
                    )
                    drive_modified = parse_date(file.get('modifiedTime'))
                    
                    if drive_modified and existing_updated and drive_modified > existing_updated:
                        needs_upload = True
                        reason = f"Drive version newer ({file['modifiedTime']} > {existing_file.get('updated', existing_file.get('lastModified', 'unknown'))})"
                
                if needs_upload:
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_file,
                                file, auth_token, bool(existing_file), reason, skipped_reasons
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
                        # Update progress
                        files_processed += 1
                        mb_processed += int(file.get('size', 0))
                        
                        # Update database and emit progress after first file, then every 10 files or every 10MB
                        if files_processed == 1 or files_processed % 10 == 0 or mb_processed % (10 * 1024 * 1024) == 0:
                            await update_data_source_sync_status(
                                USER_ID, 'google', 'google_drive', 'syncing',
                                files_processed=files_processed,
                                mb_processed=mb_processed
                            )
                            
                            await emit_sync_progress(USER_ID, 'google', 'google_drive', {
                                'phase': 'processing',
                                'phase_name': 'Phase 3: Processing',
                                'phase_description': 'uploading new files and deleting orphans',
                                'files_processed': files_processed,
                                'files_total': files_total,
                                'mb_processed': mb_processed,
                                'mb_total': mb_total,
                                'sync_start_time': sync_start_time
                            })
                except Exception as e:
                    print(f"Error uploading {file['fullPath']}: {str(e)}")
                    # Still count as processed for progress tracking
                    files_processed += 1
        
        # Phase 4: Summarizing
        print(f'----------------------------------------------------------------------')
        print(f'📊 Phase 4: Summarizing - Generating sync report...')
        print(f'----------------------------------------------------------------------')
        
        # Emit phase update
        await emit_sync_progress(USER_ID, 'google', 'google_drive', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'generating sync report',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        # Enhanced summary
        print(f'\nSync Summary ({current_backend}):')
        for file in uploaded_files:
            symbol = '+' if file['type'] == 'new' else '^'
            print(f" {symbol} {file['path']} | {format_bytes(file['size'])} | {file['durationMs']}ms | {file['reason']}")
        
        for file in deleted_files:
            print(f" - {file['name']} | {format_bytes(file['size'])} | Created: {file['timeCreated']}")
        
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"📦 Files Processed: {len(all_files)}")
        print(f"🗑️  Orphans Removed: {len(deleted_files)}")
        
        total_skipped = sum(skipped_reasons.values())
        print(f"⛔ Skipped Files: {total_skipped}")
        for reason, count in skipped_reasons.items():
            if count > 0:
                print(f"   • by {reason}: {count}")
        
        print(f"\nTotal: +{len([f for f in uploaded_files if f['type'] == 'new'])} added, " +
              f"^{len([f for f in uploaded_files if f['type'] == 'updated'])} updated, " +
              f"-{len(deleted_files)} removed, {total_skipped} skipped")

        # Prepare sync results
        sync_results = {
            "latest_sync": {
                "added": len([f for f in uploaded_files if f['type'] == 'new']),
                "updated": len([f for f in uploaded_files if f['type'] == 'updated']),
                "removed": len(deleted_files),
                "skipped": total_skipped,
                "runtime_ms": int((time.time() - script_start_time) * 1000),
                "api_calls": total_api_calls,
                "skip_reasons": skipped_reasons,
                "sync_timestamp": int(time.time())
            },
            "overall_profile": {
                "total_files": len(all_files),
                "total_size_bytes": sum(int(f.get('size', 0) or 0) for f in all_files),
                "last_updated": int(time.time()),
                "folders_count": len([f for f in all_files if f.get('mimeType') == 'application/vnd.google-apps.folder'])
            }
        }

        # Final progress update
        await update_data_source_sync_status(
            user_id, 'google', 'google_drive', 'embedding',
            files_processed=files_processed,
            mb_processed=mb_processed,
            sync_results=sync_results
        )
        
        # Emit final progress
        await emit_sync_progress(user_id, 'google', 'google_drive', {
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time,
            'completed': True
        })
        
    except Exception as error:
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        print(traceback.format_exc())
        raise error

def download_and_upload_file(file, auth_token, exists, reason, skipped_reasons):
    """Helper function to download a file and upload it using unified storage interface"""
    start_time = time.time()
    
    try:
        # Download file from Drive
        file_content = download_file(file['id'], auth_token, file['mimeType'])
        
        # Upload using unified interface
        success = upload_file_unified(
            file_content.getvalue(),
            file['fullPath'],
            file.get('mimeType'),
            USER_ID
        )
        
        if not success:
            return None
        
        upload_result = {
            'path': file['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': file.get('size', 0),
            'driveModified': file.get('modifiedTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason,
            'backend': get_current_backend()
        }
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            print(f"🔒 Skipped read-only file: {file['fullPath']} (permission denied)")
            skipped_reasons['permission'] += 1
            return None
        else:
            print(f"Error processing file {file['fullPath']}: {error_msg}")
            log.error(f"Error in download_and_upload_file for {file['fullPath']}:", exc_info=True)
            skipped_reasons['other'] += 1
            return None

# ============================================================================
# MAIN EXECUTION FUNCTION
# ============================================================================

async def initiate_google_file_sync(
    user_id: str, 
    token: str, 
    creds: str = None, 
    gcs_bucket_name: str = None, 
    sync_drive=True, 
    sync_gmail=True, 
    gmail_query='', 
    max_emails=1000,
    storage_backend: str = None
):
    """
    Main entry point to sync Google Drive and/or Gmail to configured storage
    
    Args:
        user_id (str): User ID to prefix file paths
        token (str): OAuth token for Google APIs
        creds (str): Base64-encoded Google service account JSON (for GCS backward compatibility)
        gcs_bucket_name (str): GCS bucket name (for GCS backward compatibility)
        sync_drive (bool): Whether to sync Google Drive files
        sync_gmail (bool): Whether to sync Gmail messages
        gmail_query (str): Gmail search query to filter messages
        max_emails (int): Maximum number of emails to sync
        storage_backend (str): Override storage backend ('gcs' or 'pai')
        
    Returns:
        dict: Summary of sync operations
    """
    log.info(f'Sync Google services to storage backend')
    log.info(f'User Open WebUI ID: {user_id}')
        
    current_backend = get_current_backend()
    log.info(f'Using storage backend: {current_backend}')

    global USER_ID 
    global GCS_BUCKET_NAME
    global script_start_time
    global total_api_calls

    USER_ID = user_id
    GCS_BUCKET_NAME = gcs_bucket_name or ''  # For backward compatibility
    total_api_calls = 0
    script_start_time = time.time()

    results = {
        'drive': None,
        'gmail': None,
        'backend': current_backend
    }

    try:
        # Sync Google Drive if requested
        if sync_drive:
            await update_data_source_sync_status(USER_ID, 'google', 'google_drive', 'syncing')
            await sync_drive_to_storage(token, user_id)
            results['drive'] = 'completed'
        
        # Sync Gmail if requested
        if sync_gmail:
            await update_data_source_sync_status(USER_ID, 'google', 'gmail', 'syncing')
            gmail_result = await sync_gmail_to_storage(token, gmail_query, max_emails, user_id)
            results['gmail'] = gmail_result
        
        return results
        
    except Exception as error:
        log.error("Google sync failed:", exc_info=True)
        raise error