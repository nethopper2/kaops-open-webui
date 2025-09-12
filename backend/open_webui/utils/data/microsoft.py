import os
import time
import concurrent.futures
import io
import traceback
import logging
from datetime import datetime

from open_webui.env import SRC_LOG_LEVELS

from open_webui.utils.data.data_ingestion import upload_to_gcs, list_gcs_files, delete_gcs_file, parse_date, format_bytes, validate_config, make_api_request, update_data_source_sync_status

from open_webui.models.data import DataSources
log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

existing_gcs_files = set()

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

# Microsoft Graph API endpoints
GRAPH_API_BASE = 'https://graph.microsoft.com/v1.0'

def make_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with error handling"""
    global total_api_calls
    total_api_calls += 1
    
    return make_api_request(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)

def load_existing_gcs_files(service_account_base64, gcs_bucket_name):
    """Load existing GCS files into memory for duplicate checking"""
    global existing_gcs_files, USER_ID
    
    try:
        print("Loading existing files from GCS for duplicate checking...")
        user_prefix = f"userResources/{USER_ID}/Microsoft/"
        gcs_files = list_gcs_files(service_account_base64, gcs_bucket_name, prefix=user_prefix)
        existing_gcs_files = {
            gcs_file['name'] for gcs_file in gcs_files 
            if gcs_file['name'].startswith(user_prefix)
        }
        print(f"Found {len(existing_gcs_files)} existing files in GCS for user {USER_ID}")
    except Exception as e:
        print(f"Error loading existing GCS files: {str(e)}")
        log.error("Error loading existing GCS files:", exc_info=True)
        existing_gcs_files = set()

def file_exists_in_gcs(file_path):
    """Check if file already exists in GCS"""
    global existing_gcs_files
    return file_path in existing_gcs_files

# OneNote integration functions
def list_onenote_notebooks(auth_token):
    """List all OneNote notebooks"""
    try:
        url = f"{GRAPH_API_BASE}/me/onenote/notebooks"
        response = make_request(url, auth_token=auth_token)
        return response.get('value', [])
    except Exception as error:
        print(f"Error listing OneNote notebooks: {str(error)}")
        log.error("Error in list_onenote_notebooks:", exc_info=True)
        return []

def list_onenote_sections(notebook_id, auth_token):
    """List sections in a OneNote notebook"""
    try:
        url = f"{GRAPH_API_BASE}/me/onenote/notebooks/{notebook_id}/sections"
        response = make_request(url, auth_token=auth_token)
        return response.get('value', [])
    except Exception as error:
        print(f"Error listing OneNote sections for notebook {notebook_id}: {str(error)}")
        log.error(f"Error in list_onenote_sections for {notebook_id}:", exc_info=True)
        return []

def list_onenote_pages(section_id, auth_token):
    """List pages in a OneNote section"""
    try:
        url = f"{GRAPH_API_BASE}/me/onenote/sections/{section_id}/pages"
        response = make_request(url, auth_token=auth_token)
        return response.get('value', [])
    except Exception as error:
        print(f"Error listing OneNote pages for section {section_id}: {str(error)}")
        log.error(f"Error in list_onenote_pages for {section_id}:", exc_info=True)
        return []

def download_onenote_page(page_id, auth_token):
    """Download OneNote page content as HTML"""
    try:
        url = f"{GRAPH_API_BASE}/me/onenote/pages/{page_id}/content"
        response = make_request(url, auth_token=auth_token, stream=True)
        
        content = io.BytesIO()
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                content.write(chunk)
        content.seek(0)
        return content
    except Exception as error:
        print(f"Error downloading OneNote page {page_id}: {str(error)}")
        log.error(f"Error in download_onenote_page for {page_id}:", exc_info=True)
        return None

async def sync_onenote_to_gcs(auth_token, service_account_base64, gcs_bucket_name):
    """Sync OneNote notebooks to GCS"""
    global USER_ID
    
    print('🔄 Starting OneNote sync process...')
    
    uploaded_files = []
    skipped_files = 0
    
    try:
        # Get OneNote notebooks
        notebooks = list_onenote_notebooks(auth_token)
        print(f"Found {len(notebooks)} OneNote notebooks")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for notebook in notebooks:
                notebook_id = notebook.get('id')
                notebook_name = notebook.get('displayName', 'Untitled Notebook')
                
                # Get sections in notebook
                sections = list_onenote_sections(notebook_id, auth_token)
                
                for section in sections:
                    section_id = section.get('id')
                    section_name = section.get('displayName', 'Untitled Section')
                    
                    # Get pages in section
                    pages = list_onenote_pages(section_id, auth_token)
                    
                    for page in pages:
                        page_id = page.get('id')
                        page_title = page.get('title', 'Untitled Page')
                        
                        # Create file path
                        safe_notebook = notebook_name.replace('/', '_').replace('\\', '_')
                        safe_section = section_name.replace('/', '_').replace('\\', '_')
                        safe_title = page_title.replace('/', '_').replace('\\', '_')
                        file_path = f"userResources/{USER_ID}/Microsoft/OneNote/{safe_notebook}/{safe_section}/{safe_title}.html"
                        
                        # Check if file already exists
                        if file_exists_in_gcs(file_path):
                            print(f"⏭️  Skipping existing OneNote page: {page_title}")
                            skipped_files += 1
                            continue
                        
                        # Submit download task
                        futures.append(
                            (
                                executor.submit(
                                    download_and_upload_onenote_page,
                                    page_id,
                                    file_path,
                                    page_title,
                                    auth_token,
                                    service_account_base64,
                                    gcs_bucket_name
                                ),
                                page_title
                            )
                        )
            
            # Process completed uploads
            for future, page_title in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                        existing_gcs_files.add(result['path'])  # Add to cache
                    else:
                        skipped_files += 1
                except Exception as e:
                    print(f"Error processing OneNote page {page_title}: {str(e)}")
                    log.error(f"Error processing OneNote page {page_title}:", exc_info=True)
                    skipped_files += 1
        
        print(f"\nOneNote Sync Summary:")
        print(f"📓 Pages uploaded: {len(uploaded_files)}")
        print(f"⏭️  Pages skipped: {skipped_files}")

        await update_data_source_sync_status(USER_ID, 'microsoft', 'onenote', 'synced')
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files
        }
        
    except Exception as error:
        print(f"OneNote sync failed: {str(error)}")
        log.error("OneNote sync failed:", exc_info=True)
        raise error

def download_and_upload_onenote_page(page_id, file_path, page_title, auth_token, service_account_base64, gcs_bucket_name):
    """Download OneNote page and upload to GCS"""
    start_time = time.time()
    
    try:
        # Download page content
        page_content = download_onenote_page(page_id, auth_token)
        if not page_content:
            return None
        
        # Upload to GCS
        result = upload_to_gcs(
            page_content,
            file_path,
            'text/html',
            service_account_base64,
            gcs_bucket_name
        )
        
        upload_result = {
            'path': file_path,
            'type': 'new',
            'size': result.get('size'),
            'title': page_title,
            'durationMs': int((time.time() - start_time) * 1000)
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded OneNote page: {page_title}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing OneNote page {page_id}: {str(e)}")
        log.error(f"Error in download_and_upload_onenote_page for {page_id}:", exc_info=True)
        return None

# Outlook integration functions
def list_outlook_messages(auth_token, folder='inbox', query='', max_results=1000):
    """List Outlook messages from specified folder"""
    try:
        all_messages = []
        skip = 0
        top = min(max_results, 100)  # Microsoft Graph limit
        
        while len(all_messages) < max_results:
            params = {
                '$top': top,
                '$skip': skip,
                '$select': 'id,subject,from,toRecipients,receivedDateTime,hasAttachments,bodyPreview'
            }
            
            if query:
                params['$filter'] = query
            
            url = f"{GRAPH_API_BASE}/me/mailFolders/{folder}/messages"
            response = make_request(url, params=params, auth_token=auth_token)
            
            messages = response.get('value', [])
            if not messages:
                break
                
            all_messages.extend(messages)
            skip += top
            
            if len(messages) < top:  # No more results
                break
        
        return all_messages[:max_results]
        
    except Exception as error:
        print(f"Error listing Outlook messages: {str(error)}")
        log.error("Error in list_outlook_messages:", exc_info=True)
        return []

def get_outlook_message(message_id, auth_token):
    """Get full Outlook message content"""
    try:
        url = f"{GRAPH_API_BASE}/me/messages/{message_id}"
        params = {'$select': 'id,subject,from,toRecipients,receivedDateTime,body,hasAttachments'}
        
        message = make_request(url, params=params, auth_token=auth_token)
        return message
        
    except Exception as error:
        print(f"Error getting Outlook message {message_id}: {str(error)}")
        log.error(f"Error in get_outlook_message for {message_id}:", exc_info=True)
        return None

def convert_outlook_message_to_text(message):
    """Convert Outlook message to readable text format"""
    try:
        subject = message.get('subject', 'No Subject')
        from_addr = message.get('from', {}).get('emailAddress', {}).get('address', 'Unknown')
        from_name = message.get('from', {}).get('emailAddress', {}).get('name', from_addr)
        received_date = message.get('receivedDateTime', 'Unknown')
        
        to_recipients = []
        for recipient in message.get('toRecipients', []):
            email_addr = recipient.get('emailAddress', {})
            to_recipients.append(f"{email_addr.get('name', '')} <{email_addr.get('address', '')}>")
        to_list = '; '.join(to_recipients)
        
        body_content = message.get('body', {}).get('content', 'No content available')
        
        text_content = f"""Subject: {subject}
                            From: {from_name} <{from_addr}>
                            To: {to_list}
                            Date: {received_date}
                            Message ID: {message.get('id', 'Unknown')}

                            {body_content}
                        """
        return text_content
        
    except Exception as error:
        print(f"Error converting Outlook message to text: {str(error)}")
        log.error("Error in convert_outlook_message_to_text:", exc_info=True)
        return ""

async def sync_outlook_to_gcs(auth_token, service_account_base64, gcs_bucket_name, folder='inbox', query='', max_emails=1000):
    """Sync Outlook messages to GCS"""
    global USER_ID
    
    print(f'🔄 Starting Outlook sync process for folder: {folder}...')
    
    uploaded_files = []
    skipped_files = 0
    
    try:
        # Get Outlook messages
        print(f"Fetching Outlook messages from {folder} (max: {max_emails})")
        messages = list_outlook_messages(auth_token, folder, query, max_emails)
        print(f"Found {len(messages)} Outlook messages")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for message in messages:
                message_id = message.get('id')
                if not message_id:
                    continue
                
                # Create file path
                safe_subject = message.get('subject', 'No Subject').replace('/', '_').replace('\\', '_')[:100]
                file_path = f"userResources/{USER_ID}/Microsoft/Outlook/{folder}/email_{message_id}_{safe_subject}.txt"
                
                # Check if file already exists
                if file_exists_in_gcs(file_path):
                    print(f"⏭️  Skipping existing Outlook email: {safe_subject}")
                    skipped_files += 1
                    continue
                
                # Submit download task
                futures.append(
                    (
                        executor.submit(
                            download_and_upload_outlook_message,
                            message_id,
                            file_path,
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
                        existing_gcs_files.add(result['path'])  # Add to cache
                    else:
                        skipped_files += 1
                except Exception as e:
                    print(f"Error processing Outlook message {message_id}: {str(e)}")
                    log.error(f"Error processing Outlook message {message_id}:", exc_info=True)
                    skipped_files += 1
        
        print(f"\nOutlook Sync Summary:")
        print(f"📧 Emails uploaded: {len(uploaded_files)}")
        print(f"⏭️  Emails skipped: {skipped_files}")

        await update_data_source_sync_status(USER_ID, 'microsoft', 'outlook', 'synced')
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files
        }
        
    except Exception as error:
        print(f"Outlook sync failed: {str(error)}")
        log.error("Outlook sync failed:", exc_info=True)
        raise error

def download_and_upload_outlook_message(message_id, file_path, auth_token, service_account_base64, gcs_bucket_name):
    """Download Outlook message and upload to GCS"""
    start_time = time.time()
    
    try:
        # Get full message content
        message = get_outlook_message(message_id, auth_token)
        if not message:
            return None
        
        # Convert to text format
        message_text = convert_outlook_message_to_text(message)
        if not message_text:
            return None
        
        # Create BytesIO object
        message_content = io.BytesIO(message_text.encode('utf-8'))
        
        # Upload to GCS
        result = upload_to_gcs(
            message_content,
            file_path,
            'text/plain',
            service_account_base64,
            gcs_bucket_name
        )
        
        upload_result = {
            'path': file_path,
            'type': 'new',
            'size': len(message_text.encode('utf-8')),
            'subject': message.get('subject', 'No Subject'),
            'durationMs': int((time.time() - start_time) * 1000)
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded Outlook email: {message.get('subject', 'No Subject')}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing Outlook message {message_id}: {str(e)}")
        log.error(f"Error in download_and_upload_outlook_message for {message_id}:", exc_info=True)
        return None

# OneDrive Functions
def list_onedrive_files_recursively(folder_id, auth_token, current_path='', all_files=None):
    """Recursive file listing with path construction for OneDrive"""
    if all_files is None:
        all_files = []
    
    try:
        # If folder_id is empty or 'root', use the root endpoint
        if not folder_id or folder_id == 'root':
            url = f"{GRAPH_API_BASE}/me/drive/root/children"
        else:
            url = f"{GRAPH_API_BASE}/me/drive/items/{folder_id}/children"
        
        # List files in current folder with pagination
        page_token = None
        all_folder_files = []
        
        while True:
            params = {
                '$top': 1000,  # Similar to pageSize
                '$select': 'id,name,size,file,folder,lastModifiedDateTime,createdDateTime,parentReference'
            }
            
            # Add page token if we have one
            if page_token:
                params['$skiptoken'] = page_token
            
            results = make_request(url, params=params, auth_token=auth_token)
            
            # Add files from this page to our collection
            files = results.get('value', [])
            all_folder_files.extend(files)
            
            # Check if we have more pages
            if '@odata.nextLink' in results:
                # Extract the skiptoken from the nextLink URL
                next_link = results['@odata.nextLink']
                if '$skiptoken=' in next_link:
                    page_token = next_link.split('$skiptoken=')[1]
                else:
                    break
            else:
                break
        
        # Process each file/folder in current directory level
        for file in all_folder_files:
            # If it's a folder, process recursively
            if 'folder' in file:
                folder_name = file['name']
                list_onedrive_files_recursively(
                    file['id'],
                    auth_token,
                    f"{current_path}{folder_name}/", 
                    all_files
                )
            elif 'file' in file:
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
                
                # Add file to list with full path
                file_info = file.copy()
                
                # Fetch USER_ID
                global USER_ID
                
                # Include USER_ID in the path
                file_info['fullPath'] = f"userResources/{USER_ID}/Microsoft/OneDrive/{current_path}{file['name']}"
                
                all_files.append(file_info)
    
    except Exception as error:
        print(f'Listing failed for OneDrive folder {folder_id}: {str(error)}')
    
    return all_files

def download_onedrive_file(file_id, auth_token):
    """
    Download file content from OneDrive
    
    Args:
        file_id (str): The ID of the file to download
        auth_token (str): OAuth token for authentication
        
    Returns:
        io.BytesIO: file content
    """
    try:
        # Get download URL from metadata
        metadata_url = f"{GRAPH_API_BASE}/me/drive/items/{file_id}"
        # This metadata call does NOT stream, so make_api_request will return JSON
        metadata = make_api_request(metadata_url, auth_token=auth_token)
        
        file_content = io.BytesIO()

        if '@microsoft.graph.downloadUrl' in metadata:
            download_url = metadata['@microsoft.graph.downloadUrl']
            # Direct download link:
            # IMPORTANT: Your make_api_request assumes it should *add* the auth_token.
            # If the downloadUrl is pre-authenticated (which it often is for MS Graph),
            # make_api_request shouldn't add the auth_token again.
            # We'll call make_api_request without auth_token if it's a pre-signed URL.
            
            # Assuming make_api_request's 'auth_token' parameter *only* adds if present.
            # If it were always adding it, you'd need a separate simpler requests.get or modify make_api_request logic.
            # Given how make_api_request is written, if auth_token is None, it won't add the header.
            with make_api_request(download_url, stream=True, auth_token=None) as response:
                # make_api_request already calls raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        else:
            # Fallback to content endpoint which REQUIRES auth_token
            download_url = f"{GRAPH_API_BASE}/me/drive/items/{file_id}/content"
            with make_api_request(download_url, auth_token=auth_token, stream=True) as response:
                # make_api_request already calls raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        
        file_content.seek(0)
        return file_content
    
    except Exception as error:
        print(f"OneDrive download failed for {file_id}: {str(error)}")
        # Consider using a logger with exc_info=True for better debugging in a real app
        # log.error(f"OneDrive download failed for {file_id}:", exc_info=True)
        raise


# SharePoint Functions
def get_sharepoint_sites(auth_token):
    """Get all SharePoint sites the user has access to"""
    try:
        url = f"{GRAPH_API_BASE}/sites?search="
        
        # List sites with pagination
        page_token = None
        all_sites = []
        
        while True:
            params = {
                '$top': 100
            }
            
            # Add page token if we have one
            if page_token:
                params['$skiptoken'] = page_token
            
            results = make_request(url, params=params, auth_token=auth_token)
            
            # Add sites from this page to our collection
            sites = results.get('value', [])
            all_sites.extend(sites)
            
            # Check if we have more pages
            if '@odata.nextLink' in results:
                # Extract the skiptoken from the nextLink URL
                next_link = results['@odata.nextLink']
                if '$skiptoken=' in next_link:
                    page_token = next_link.split('$skiptoken=')[1]
                else:
                    break
            else:
                break
        
        return all_sites
    
    except Exception as error:
        print(f"Error getting SharePoint sites: {str(error)}")
        return []

def download_sharepoint_file(site_id, drive_id, file_id, auth_token):
    """
    Download file content from SharePoint
    
    Args:
        site_id (str): The ID of the SharePoint site
        drive_id (str): The ID of the drive
        file_id (str): The ID of the file to download
        auth_token (str): OAuth token for authentication
        
    Returns:
        io.BytesIO: file content
    """
    try:
        # Get download URL from metadata
        metadata_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{file_id}"
        # This metadata call does NOT stream, so make_api_request will return JSON
        metadata = make_api_request(metadata_url, auth_token=auth_token)
        
        file_content = io.BytesIO()

        if '@microsoft.graph.downloadUrl' in metadata:
            download_url = metadata['@microsoft.graph.downloadUrl']
            # Direct download link:
            # Same logic as OneDrive: assuming make_api_request without auth_token means no auth header added.
            with make_api_request(download_url, stream=True, auth_token=None) as response:
                # make_api_request already calls raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        else:
            # Fallback to content endpoint which REQUIRES auth_token
            download_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{file_id}/content"
            with make_api_request(download_url, auth_token=auth_token, stream=True) as response:
                # make_api_request already calls raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        
        file_content.seek(0)
        return file_content
    
    except Exception as error:
        print(f"SharePoint download failed for {file_id}: {str(error)}")
        # Consider using a logger with exc_info=True for better debugging in a real app
        # log.error(f"SharePoint download failed for {file_id}:", exc_info=True)
        raise
    
def list_sharepoint_files_recursively(site_id, drive_id, folder_id, auth_token, current_path='', all_files=None, site_name=''):
    """Recursive file listing with path construction for SharePoint"""
    if all_files is None:
        all_files = []
    
    try:
        # If folder_id is empty or 'root', use the root endpoint
        if not folder_id or folder_id == 'root':
            url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/root/children"
        else:
            url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children"
        
        # List files in current folder with pagination
        page_token = None
        all_folder_files = []
        
        while True:
            params = {
                '$top': 1000,
                '$select': 'id,name,size,file,folder,lastModifiedDateTime,createdDateTime,parentReference'
            }
            
            # Add page token if we have one
            if page_token:
                params['$skiptoken'] = page_token
            
            results = make_request(url, params=params, auth_token=auth_token)
            
            # Add files from this page to our collection
            files = results.get('value', [])
            all_folder_files.extend(files)
            
            # Check if we have more pages
            if '@odata.nextLink' in results:
                # Extract the skiptoken from the nextLink URL
                next_link = results['@odata.nextLink']
                if '$skiptoken=' in next_link:
                    page_token = next_link.split('$skiptoken=')[1]
                else:
                    break
            else:
                break
        
        # Process each file/folder in current directory level
        for file in all_folder_files:
            # If it's a folder, process recursively
            if 'folder' in file:
                folder_name = file['name']
                list_sharepoint_files_recursively(
                    site_id,
                    drive_id,
                    file['id'],
                    auth_token,
                    f"{current_path}{folder_name}/", 
                    all_files,
                    site_name
                )
            elif 'file' in file:
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
                
                # Add file to list with full path
                file_info = file.copy()
                
                # Fetch USER_ID
                global USER_ID
                
                # Include USER_ID and site name in the path
                file_info['fullPath'] = f"userResources/{USER_ID}/Microsoft/SharePoint/{site_name}/{current_path}{file['name']}"
                
                all_files.append(file_info)
    
    except Exception as error:
        print(f'Listing failed for SharePoint folder {folder_id} in site {site_id}: {str(error)}')
    
    return all_files

def download_sharepoint_file(site_id, drive_id, file_id, auth_token):
    """
    Download file content from SharePoint
    
    Args:
        site_id (str): The ID of the SharePoint site
        drive_id (str): The ID of the drive
        file_id (str): The ID of the file to download
        auth_token (str): OAuth token for authentication
        
    Returns:
        io.BytesIO: file content
    """
    try:
        # Get download URL from metadata
        metadata_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{file_id}"
        # This metadata call does NOT stream, so make_api_request will return JSON
        metadata = make_api_request(metadata_url, auth_token=auth_token)
        
        file_content = io.BytesIO()

        if '@microsoft.graph.downloadUrl' in metadata:
            download_url = metadata['@microsoft.graph.downloadUrl']
            # *** CRITICAL: Use 'with' for make_api_request with stream=True ***
            # Assuming make_api_request without auth_token means no auth header added for pre-signed URLs.
            with make_api_request(download_url, stream=True, auth_token=None) as response:
                # make_api_request already calls raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        else:
            # Fallback to content endpoint which REQUIRES auth_token
            download_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{file_id}/content"
            with make_api_request(download_url, auth_token=auth_token, stream=True) as response:
                # make_api_request already calls raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        
        file_content.seek(0)
        return file_content
    
    except Exception as error:
        print(f"SharePoint download failed for {file_id}: {str(error)}")
        # For a production application, use `log.error(..., exc_info=True)` here
        # log.error(f"SharePoint download failed for {file_id}:", exc_info=True)
        raise
    
# Main Sync Functions
def download_and_upload_onedrive_file(file, auth_token, service_account_base64, GCS_BUCKET_NAME, exists, reason):
    """Helper function to download a OneDrive file and upload it to GCS"""
    start_time = time.time()

    # Check if file already exists in GCS
    if file_exists_in_gcs(file['fullPath']):
        print(f"⏭️  Skipping existing file: {file['fullPath']}")
        return None
        
    
    try:
        # Download file from OneDrive
        file_content = download_onedrive_file(file['id'], auth_token)
        
        # Get content type
        content_type = file.get('file', {}).get('mimeType')
        
        # Upload to GCS
        result = upload_to_gcs(
            file_content, 
            file['fullPath'], 
            content_type,
            service_account_base64,
            GCS_BUCKET_NAME
        )
        
        upload_result = {
            'path': file['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': result.get('size'),
            'driveModified': file.get('lastModifiedDateTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason
        }

        existing_gcs_files.add(file['fullPath'])  # Add to cache
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing OneDrive file {file['fullPath']}: {str(e)}")
        return None

def download_and_upload_sharepoint_file(file, auth_token, service_account_base64, GCS_BUCKET_NAME, exists, reason):
    """Helper function to download a SharePoint file and upload it to GCS"""
    start_time = time.time()

    # Check if file already exists in GCS
    if file_exists_in_gcs(file['fullPath']):
        print(f"⏭️  Skipping existing file: {file['fullPath']}")
        return None
    
    try:
        # Extract site_id and drive_id from file object's parentReference 
        parent_ref = file.get('parentReference', {})
        site_id = parent_ref.get('siteId')
        drive_id = parent_ref.get('driveId')
        
        if not site_id or not drive_id:
            raise ValueError(f"Missing site_id or drive_id in file reference for {file['fullPath']}")
        
        # Download file from SharePoint
        file_content = download_sharepoint_file(site_id, drive_id, file['id'], auth_token)
        
        # Get content type
        content_type = file.get('file', {}).get('mimeType')
        
        # Upload to GCS
        result = upload_to_gcs(
            file_content, 
            file['fullPath'], 
            content_type,
            service_account_base64,
            GCS_BUCKET_NAME
        )
        
        upload_result = {
            'path': file['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': result.get('size'),
            'driveModified': file.get('lastModifiedDateTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason
        }

        existing_gcs_files.add(file['fullPath'])  # Add to cache
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing SharePoint file {file['fullPath']}: {str(e)}")
        return None

async def sync_onedrive_to_gcs(auth_token, service_account_base64, GCS_BUCKET_NAME):
    """Main function to sync OneDrive to Google Cloud Storage"""
    global total_api_calls
    global USER_ID
    
    print('🔄 Starting OneDrive sync process...')
    
    uploaded_files = []
    deleted_files = []
    skipped_files = 0
    
    try:
        # List all OneDrive files
        all_files = list_onedrive_files_recursively('root', auth_token)
        print(f"Found {len(all_files)} files in OneDrive")
        
        # List all GCS files
        user_prefix = f"{USER_ID}/OneDrive/"
        gcs_files = list_gcs_files(service_account_base64, GCS_BUCKET_NAME, prefix=user_prefix)
        gcs_file_map = {gcs_file['name']: gcs_file for gcs_file in gcs_files}
        onedrive_file_paths = {file['fullPath'] for file in all_files}
        
        for gcs_name, gcs_file in gcs_file_map.items():
            # Only consider files that belong to this user's OneDrive folder
            if gcs_name.startswith(user_prefix) and gcs_name not in onedrive_file_paths:
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
                    drive_modified = parse_date(file.get('lastModifiedDateTime'))
                    
                    if drive_modified and gcs_updated and drive_modified > gcs_updated:
                        needs_upload = True
                        reason = f"OneDrive version newer ({file['lastModifiedDateTime']} > {gcs_file.get('updated')})"
                
                if needs_upload:
                    # Submit upload task to executor
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_onedrive_file,
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
        print('\nOneDrive Sync Summary:')
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
        
        await update_data_source_sync_status(USER_ID, 'microsoft', 'onedrive', 'synced')
              
        return {
            'uploaded': len(uploaded_files),
            'deleted': len(deleted_files),
            'skipped': skipped_files,
            'total_processed': len(all_files)
        }
    
    except Exception as error:
        print(f'OneDrive sync failed: {str(error)}')
        # Log the full error for debugging
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        print(traceback.format_exc())
        raise error


async def sync_sharepoint_to_gcs(auth_token, service_account_base64, GCS_BUCKET_NAME):
    """Main function to sync SharePoint to Google Cloud Storage"""
    global total_api_calls
    global USER_ID
    
    print('🔄 Starting SharePoint sync process...')
    
    uploaded_files = []
    deleted_files = []
    skipped_files = 0
    all_files = []
    
    try:
        # Get SharePoint sites
        sites = get_sharepoint_sites(auth_token)
        print(f"Found {len(sites)} SharePoint sites")
        
        # For each site, get the drives and process files
        for site in sites:
            site_id = site['id']
            site_name = site['displayName']
            print(f"Processing site: {site_name} (ID: {site_id})")
            
            # Get drives in this site
            drives_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives"
            drives_response = make_request(drives_url, auth_token=auth_token)
            drives = drives_response.get('value', [])
            print(f"Found {len(drives)} drives in site {site_name}")
            
            # Process each drive
            for drive in drives:
                drive_id = drive['id']
                drive_name = drive['name']
                print(f"Processing drive: {drive_name} (ID: {drive_id})")
                
                # Process root folder of drive
                site_files = []
                process_sharepoint_folder(
                    site_id, 
                    drive_id, 
                    "root", 
                    auth_token, 
                    f"{site_name}/{drive_name}", 
                    "", 
                    site_files
                )
                
                all_files.extend(site_files)
        
        print(f"Found {len(all_files)} files across all SharePoint sites")
        
        # List all GCS files
        user_prefix = f"{USER_ID}/SharePoint/"
        gcs_files = list_gcs_files(service_account_base64, GCS_BUCKET_NAME, prefix=user_prefix)
        gcs_file_map = {gcs_file['name']: gcs_file for gcs_file in gcs_files}
        sharepoint_file_paths = {file['fullPath'] for file in all_files}
        
        # Delete orphaned GCS files that belong to this user's SharePoint
        for gcs_name, gcs_file in gcs_file_map.items():
            # Only consider files that belong to this user's SharePoint folder
            if gcs_name.startswith(user_prefix) and gcs_name not in sharepoint_file_paths:
                delete_gcs_file(gcs_name, service_account_base64, GCS_BUCKET_NAME)  # Added missing GCS_BUCKET_NAME parameter
                
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
                    sp_modified = parse_date(file.get('lastModifiedDateTime'))
                    
                    if sp_modified and gcs_updated and sp_modified > gcs_updated:
                        needs_upload = True
                        reason = f"SharePoint version newer ({file['lastModifiedDateTime']} > {gcs_file.get('updated')})"
                
                if needs_upload:
                    # Submit upload task to executor
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_sharepoint_file,
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
        
        await update_data_source_sync_status(USER_ID, 'microsoft', 'sharepoint', 'synced')
        
        # Add proper return value
        return {
            'uploaded': len(uploaded_files),
            'deleted': len(deleted_files),
            'skipped': skipped_files,
            'total_processed': len(all_files)
        }
    
    except Exception as error:
        print(f'SharePoint sync failed: {str(error)}')
        # Log the full error for debugging
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        print(traceback.format_exc())
        raise error

def process_sharepoint_folder(site_id, drive_id, folder_id, auth_token, site_drive_name, current_path="", collected_files=None):
    """Helper function to process a SharePoint folder and its contents recursively"""
    if collected_files is None:
        collected_files = []
    
    try:
        files = list_sharepoint_files_recursively(
            site_id, 
            drive_id, 
            folder_id, 
            auth_token, 
            current_path, 
            None,  # Initialize empty files list inside the function
            site_drive_name
        )
        collected_files.extend(files)
        return collected_files
    except Exception as error:
        print(f"Error processing SharePoint folder {folder_id} in site {site_id}, drive {drive_id}: {str(error)}")
        return collected_files

# Main execution function 
async def initiate_microsoft_sync(user_id, auth_token, service_account_base64, gcs_bucket_name, 
                                sync_onedrive=True, sync_sharepoint=True, sync_onenote=True, 
                                sync_outlook=True, outlook_folder='inbox', outlook_query='', max_emails=1000):
    """
    Main entry point to sync Microsoft services to GCS
    
    Args:
        user_id (str): User ID to prefix file paths
        auth_token (str): Microsoft Graph API auth token
        service_account_base64 (str): Base64-encoded Google service account JSON
        gcs_bucket_name (str): GCS bucket name
        sync_onedrive (bool): Whether to sync OneDrive
        sync_sharepoint (bool): Whether to sync SharePoint
        sync_onenote (bool): Whether to sync OneNote
        sync_outlook (bool): Whether to sync Outlook
        outlook_folder (str): Outlook folder to sync (default: 'inbox')
        outlook_query (str): Outlook query filter
        max_emails (int): Maximum emails to sync
        
    Returns:
        dict: Summary of sync operations
    """
    global USER_ID 
    global GCS_BUCKET_NAME
    global script_start_time
    global total_api_calls

    USER_ID = user_id
    GCS_BUCKET_NAME = gcs_bucket_name
    total_api_calls = 0
    script_start_time = time.time()

    log.info(f"Initiating Microsoft sync for user {USER_ID} to bucket {GCS_BUCKET_NAME}")
    log.info(f"Sync OneDrive: {sync_onedrive}, SharePoint: {sync_sharepoint}, OneNote: {sync_onenote}, Outlook: {sync_outlook}")

    
    # Load existing GCS files for duplicate checking
    load_existing_gcs_files(service_account_base64, gcs_bucket_name)
    
    results = {
        'onedrive': None,
        'sharepoint': None,
        'onenote': None,
        'outlook': None
    }

    
    try:
        # Sync OneDrive if requested
        if sync_onedrive:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'onedrive', 'syncing')
            results['onedrive'] = await sync_onedrive_to_gcs(auth_token, service_account_base64, gcs_bucket_name)
        
        # Sync SharePoint if requested
        if sync_sharepoint:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'sharepoint', 'syncing')
            results['sharepoint'] = await sync_sharepoint_to_gcs(auth_token, service_account_base64, gcs_bucket_name)
        
        # Sync OneNote if requested
        if sync_onenote:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'onenote', 'syncing')
            results['onenote'] = await sync_onenote_to_gcs(auth_token, service_account_base64, gcs_bucket_name)
        
        # Sync Outlook if requested
        if sync_outlook:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'outlook', 'syncing')
            results['outlook'] = await sync_outlook_to_gcs(auth_token, service_account_base64, gcs_bucket_name, outlook_folder, outlook_query, max_emails)
        
        return results
        
    except Exception as error:
        log.error("Microsoft sync failed:", exc_info=True)
        raise error