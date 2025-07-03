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

from open_webui.utils.data.data_ingestion import upload_to_gcs, list_gcs_files, delete_gcs_file, make_api_request, format_bytes, parse_date, update_data_source_sync_status
from open_webui.models.data import DataSources

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

# Metrics tracking
total_api_calls = 0
script_start_time = 0

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
GMAIL_API_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me/messages'

def make_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with error handling"""
    global total_api_calls
    total_api_calls += 1
    
    return make_api_request(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)

# Gmail sync functions
# Gmail sync functions
def list_gmail_messages(auth_token, query='', max_results=500):
    """
    List Gmail messages with optional query filter
    
    Args:
        auth_token (str): OAuth token for authentication
        query (str): Gmail search query (e.g., 'is:unread', 'from:example@gmail.com')
        max_results (int): Maximum number of messages to retrieve
        
    Returns:
        list: List of message metadata
    """
    try:
        all_messages = []
        next_page_token = None
        
        while True:
            params = {
                'maxResults': min(max_results - len(all_messages), 500),  # Gmail API limit is 500
                'q': query
            }
            
            if next_page_token:
                params['pageToken'] = next_page_token
            
            url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages"
            response = make_request(url, params=params, auth_token=auth_token)
            
            messages = response.get('messages', [])
            all_messages.extend(messages)
            
            # Check if we have more pages and haven't reached max_results
            next_page_token = response.get('nextPageToken')
            if not next_page_token or len(all_messages) >= max_results:
                break
        
        return all_messages[:max_results]
        
    except Exception as error:
        print(f"Error listing Gmail messages: {str(error)}")
        log.error(f"Error in list_gmail_messages:", exc_info=True)
        return []

def get_gmail_message(message_id, auth_token):
    """
    Get full Gmail message content
    
    Args:
        message_id (str): Gmail message ID
        auth_token (str): OAuth token for authentication
        
    Returns:
        dict: Full message data including headers, body, and attachments
    """
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
    """
    Extract readable content from Gmail message
    
    Args:
        message (dict): Gmail message object
        
    Returns:
        dict: Extracted email data with text content
    """
    try:
        headers = message.get('payload', {}).get('headers', [])
        
        # Extract key headers
        email_data = {
            'id': message.get('id'),
            'threadId': message.get('threadId'),
            'snippet': message.get('snippet', ''),
            'internalDate': message.get('internalDate'),
            'subject': '',
            'from': '',
            'to': '',
            'date': '',
            'body': ''
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
        
        # Extract body content
        def extract_body_recursive(payload):
            """Recursively extract text content from message parts"""
            body_text = ""
            
            if 'parts' in payload:
                # Multi-part message
                for part in payload['parts']:
                    body_text += extract_body_recursive(part)
            else:
                # Single part message
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
    """
    Convert email data to readable text format for storage
    
    Args:
        email_data (dict): Extracted email data
        
    Returns:
        str: Formatted email text
    """
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

async def sync_gmail_to_gcs(auth_token, service_account_base64, gcs_bucket_name, query='', max_emails=1000):
    """
    Sync Gmail messages to Google Cloud Storage
    
    Args:
        auth_token (str): OAuth token for authentication
        service_account_base64 (str): Base64-encoded service account JSON
        gcs_bucket_name (str): GCS bucket name
        query (str): Gmail search query to filter messages
        max_emails (int): Maximum number of emails to sync
        
    Returns:
        dict: Sync results summary
    """
    global USER_ID, total_api_calls
    
    print('🔄 Starting Gmail sync process...')
    
    uploaded_files = []
    skipped_files = 0
    
    try:
        # Get list of Gmail messages
        print(f"Fetching Gmail messages with query: '{query}' (max: {max_emails})")
        messages = list_gmail_messages(auth_token, query, max_emails)
        print(f"Found {len(messages)} Gmail messages")
        
        # Get existing GCS files for Gmail to check for duplicates
        print("Checking existing Gmail files in GCS...")
        gcs_files = list_gcs_files(service_account_base64, gcs_bucket_name)
        gmail_prefix = f"userResources/{USER_ID}/Google/Gmail/"
        existing_email_files = {
            gcs_file['name'] for gcs_file in gcs_files 
            if gcs_file['name'].startswith(gmail_prefix)
        }
        print(f"Found {len(existing_email_files)} existing Gmail files in GCS")
        
        # Process messages in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for i, message in enumerate(messages):
                message_id = message.get('id')
                if not message_id:
                    continue
                
                # Create file path for email
                email_path = f"userResources/{USER_ID}/Google/Gmail/email_{message_id}.txt"
                
                # Check if email already exists in GCS
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
                            auth_token,
                            service_account_base64,
                            gcs_bucket_name
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
        print(f"\nGmail Sync Summary:")
        print(f"📧 Emails processed: {len(messages)}")
        print(f"📤 Emails uploaded: {len(uploaded_files)}")
        print(f"⏭️  Emails skipped: {skipped_files}")
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files,
            'total_processed': len(messages)
        }
        
    except Exception as error:
        print(f"Gmail sync failed: {str(error)}")
        log.error(f"Gmail sync failed:", exc_info=True)
        raise error

def download_and_upload_email(message_id, email_path, auth_token, service_account_base64, gcs_bucket_name):
    """
    Download Gmail message and upload to GCS
    
    Args:
        message_id (str): Gmail message ID
        email_path (str): GCS path for the email file
        auth_token (str): OAuth token
        service_account_base64 (str): Service account credentials
        gcs_bucket_name (str): GCS bucket name
        
    Returns:
        dict: Upload result or None if failed
    """
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
        
        # Create BytesIO object with email content
        email_content = io.BytesIO(email_text.encode('utf-8'))
        
        # Upload to GCS
        result = upload_to_gcs(
            email_content,
            email_path,
            'text/plain',
            service_account_base64,
            gcs_bucket_name
        )
        
        upload_result = {
            'path': email_path,
            'type': 'new',
            'size': len(email_text.encode('utf-8')),
            'subject': email_data.get('subject', 'No Subject'),
            'durationMs': int((time.time() - start_time) * 1000)
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded email: {email_data.get('subject', 'No Subject')}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing email {message_id}: {str(e)}")
        log.error(f"Error in download_and_upload_email for {message_id}:", exc_info=True)
        return None
    
#Google Drive Sync Functions
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
            results = make_request(url, params=params, auth_token=auth_token)
            
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
                    file_info['fullPath'] = f"userResources/{USER_ID}/Google/Google Drive/{drive_name}/{current_path}{file['name']}"
                else:
                    file_info['fullPath'] = f"userResources/{USER_ID}/Google/Google Drive/{current_path}{file['name']}"
                
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
        root_response = make_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
        
        # Get user's root folder ID (my drive)
        params = {
            'fields': "id"
        }
        my_drive = make_request(f"{DRIVE_API_BASE}/files/root", params=params, auth_token=auth_token)
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
                
            shared_response = make_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
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
                
            shared_drives_response = make_request(f"{DRIVE_API_BASE}/drives", params=params, auth_token=auth_token)
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
                
                response = make_request(f"{DRIVE_API_BASE}/files", params=params, auth_token=auth_token)
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
        metadata_response = make_request(
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

def process_folder(folder_id, folder_name, auth_token, all_files, drive_name=None):
    try:
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
    except Exception as error:
        print(f'Listing failed for folder {folder_id}: {str(error)}')
        # ADD THIS:
        log.error(f"Error in process_folder for {folder_id}:", exc_info=True)

async def sync_drive_to_gcs(auth_token, service_account_base64):
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
        user_prefix = f"userResources/{USER_ID}/Google/Google Drive/"
        for gcs_name, gcs_file in gcs_file_map.items():
            # Only consider files that belong to this user's Google Drive folder
            if gcs_name.startswith(user_prefix) and gcs_name not in drive_file_paths:
                delete_gcs_file(gcs_name, service_account_base64, GCS_BUCKET_NAME)
                
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
        # Log the full error for debugging
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        print(traceback.format_exc())
        raise error

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
        log.error(f"Error in download_and_upload_file for {file['fullPath']}:", exc_info=True)
        return None # Ensure None is returned on error

# Main Execution Function
async def initiate_google_file_sync(user_id: str, token: str, creds: str, gcs_bucket_name: str, sync_drive=True, sync_gmail=True, gmail_query='', max_emails=1000):
    """
    Main entry point to sync Google Drive and/or Gmail to GCS
    
    Args:
        user_id (str): User ID to prefix file paths
        token (str): OAuth token for Google APIs
        creds (str): Base64-encoded Google service account JSON
        gcs_bucket_name (str): GCS bucket name
        sync_drive (bool): Whether to sync Google Drive files
        sync_gmail (bool): Whether to sync Gmail messages
        gmail_query (str): Gmail search query to filter messages
        max_emails (int): Maximum number of emails to sync
        
    Returns:
        dict: Summary of sync operations
    """
    log.info(f'Sync Google services to Google Cloud Storage')
    log.info(f'User Open WebUI ID: {user_id}')
    log.info(f'GCS Bucket Name: {gcs_bucket_name}')
    log.info(f'Sync Drive: {sync_drive}, Sync Gmail: {sync_gmail}')

    global USER_ID 
    global GCS_BUCKET_NAME
    global script_start_time
    global total_api_calls

    USER_ID = user_id
    GCS_BUCKET_NAME = gcs_bucket_name
    total_api_calls = 0
    script_start_time = time.time()

    results = {
        'drive': None,
        'gmail': None
    }

    await update_data_source_sync_status(USER_ID, 'google', 'syncing')

    try:
        # Sync Google Drive if requested
        if sync_drive:
            await sync_drive_to_gcs(token, creds)
            results['drive'] = 'completed'
        
        # Sync Gmail if requested
        if sync_gmail:
            
            gmail_result = await sync_gmail_to_gcs(token, creds, gcs_bucket_name, gmail_query, max_emails)
            results['gmail'] = gmail_result

        await update_data_source_sync_status(USER_ID, 'google', 'synced')
        
        return results
        
    except Exception as error:
        await update_data_source_sync_status(USER_ID, 'google', 'error')
        log.error("Google sync failed:", exc_info=True)
        raise error