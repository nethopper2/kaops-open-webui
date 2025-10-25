import os
import time
import concurrent.futures
import io
import traceback
import logging
from datetime import datetime

from open_webui.env import SRC_LOG_LEVELS

from open_webui.utils.data.data_ingestion import (
    # Unified storage functions
    list_files_unified, upload_file_unified, delete_file_unified,
    # Utility functions
    parse_date, format_bytes, validate_config, make_api_request, update_data_source_sync_status,
    # Backend configuration
    configure_storage_backend, get_current_backend
)

from open_webui.models.data import DataSources
from open_webui.models.datatokens import OAuthTokens

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

# Global socketio instance for progress updates
sio = None

def get_valid_microsoft_token(user_id: str, auth_token: str) -> str:
    """
    Get a valid Microsoft token, refreshing if needed, mirroring google.py behavior.
    """
    try:
        from open_webui.routers.data import handle_token_refresh
        token_entry = OAuthTokens.get_token_by_user_provider_details(
            user_id=user_id,
            provider_name='Microsoft'
        )
        if not token_entry:
            log.debug(f"No stored Microsoft token found for user {user_id}, using provided token")
            return auth_token
        refreshed_token, needs_reauth = handle_token_refresh('microsoft', token_entry, user_id)
        if needs_reauth:
            log.warning(f"Microsoft token needs reauth for user {user_id}, using provided token")
            return auth_token
        log.debug(f"Successfully refreshed Microsoft token for user {user_id}")
        return refreshed_token
    except Exception as e:
        log.warning(f"Microsoft token refresh failed for user {user_id}, using original token: {e}")
        return auth_token

async def emit_sync_progress(user_id: str, provider: str, layer: str, progress_data: dict):
    """Emit sync progress update via WebSocket"""
    global sio
    if sio:
        try:
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


def set_socketio_instance(socketio_instance):
    """Set the socketio instance for progress updates"""
    global sio
    sio = socketio_instance

# Global variables
existing_files_cache = set()
total_api_calls = 0
script_start_time = time.time()
USER_ID = ""

# Configuration from environment
ALLOWED_EXTENSIONS = os.environ.get('ALLOWED_EXTENSIONS')
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '4'))
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB in bytes

if ALLOWED_EXTENSIONS:
    ALLOWED_EXTENSIONS = [ext.strip().lower() for ext in ALLOWED_EXTENSIONS.split(',')]
else:
    ALLOWED_EXTENSIONS = None

EXCLUDED_FILES = [
    '.DS_Store', 'Thumbs.db', 'desktop.ini', 'Icon\r', '._*', '*.tmp', '*.temp',
    '.Spotlight-V100', '.TemporaryItems', '.apdisk', '.localized', '.Trashes', '$RECYCLE.BIN'
]

GRAPH_API_BASE = 'https://graph.microsoft.com/v1.0'

def initialize_globals(user_id):
    """Initialize global variables properly"""
    global USER_ID, existing_files_cache
    
    if not user_id:
        raise ValueError("user_id is required")
    
    USER_ID = user_id
    existing_files_cache = set()

def make_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with error handling and token auto-refresh"""
    global total_api_calls, USER_ID
    total_api_calls += 1
    # Refresh token if possible
    if auth_token and USER_ID:
        auth_token = get_valid_microsoft_token(USER_ID, auth_token)
    return make_api_request(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)

def load_existing_files(user_id):
    """Load existing files into memory for duplicate checking using unified interface"""
    global existing_files_cache, USER_ID
    
    try:
        current_backend = get_current_backend()
        print(f"Loading existing files from {current_backend} storage for duplicate checking...")
        user_prefix = f"userResources/{USER_ID}/Microsoft/"
        
        existing_files = list_files_unified(prefix=user_prefix, user_id=user_id)
        
        existing_files_cache = set()
        for file in existing_files:
            file_name = file.get('name') or file.get('key', '')
            if file_name and file_name.startswith(user_prefix):
                existing_files_cache.add(file_name)
        
        print(f"Found {len(existing_files_cache)} existing files in {current_backend} storage for user {USER_ID}")
    except Exception as e:
        print(f"Error loading existing files: {str(e)}")
        log.error("Error loading existing files:", exc_info=True)
        existing_files_cache = set()

def file_exists_in_storage(file_path):
    """Check if file already exists in storage"""
    global existing_files_cache
    return file_path in existing_files_cache

def construct_file_path(service, *path_components):
    """Construct file path using proper path joining"""
    sanitized_components = []
    for component in path_components:
        if component:
            sanitized = str(component).replace('/', '_').replace('\\', '_')
            if len(sanitized) > 100:
                sanitized = sanitized[:100]
            sanitized_components.append(sanitized)
    
    path = os.path.join(f"userResources/{USER_ID}/Microsoft/{service}", *sanitized_components)
    return path.replace('\\', '/')

def is_file_size_valid(size):
    """Check if file size is within the allowed limit"""
    if size > MAX_FILE_SIZE:
        print(f"Skipping file (size {format_bytes(size)} exceeds {format_bytes(MAX_FILE_SIZE)} limit)")
        return False
    return True

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

def download_and_upload_onenote_page(page_id, file_path, page_title, auth_token):
    """Download OneNote page and upload using unified storage interface"""
    start_time = time.time()
    
    try:
        page_content = download_onenote_page(page_id, auth_token)
        if not page_content:
            return None
        
        content_size = len(page_content.getvalue())
        
        # Check file size before uploading
        if not is_file_size_valid(content_size):
            print(f"Skipping OneNote page (too large): {page_title} - {format_bytes(content_size)}")
            return None
        
        success = upload_file_unified(
            page_content.getvalue(),
            file_path,
            'text/html',
            USER_ID
        )
        
        if not success:
            return None
        
        upload_result = {
            'path': file_path,
            'type': 'new',
            'size': content_size,
            'title': page_title,
            'durationMs': int((time.time() - start_time) * 1000),
            'backend': get_current_backend()
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded OneNote page: {page_title}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing OneNote page {page_id}: {str(e)}")
        log.error(f"Error in download_and_upload_onenote_page for {page_id}:", exc_info=True)
        return None

async def sync_onenote_to_storage(auth_token):
    """Sync OneNote notebooks to storage"""
    global USER_ID
    
    print('Starting OneNote sync process...')

    # Initialize progress tracking
    sync_start_time = int(time.time())
    # Phase 1: Starting
    print("----------------------------------------------------------------------")
    print("🚀 Phase 1: Starting - preparing sync process...")
    print("----------------------------------------------------------------------")
    await emit_sync_progress(USER_ID, 'microsoft', 'onenote', {
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
    
    uploaded_files = []
    skipped_files = 0
    
    try:
        notebooks = list_onenote_notebooks(auth_token)
        print(f"Found {len(notebooks)} OneNote notebooks")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for notebook in notebooks:
                notebook_id = notebook.get('id')
                notebook_name = notebook.get('displayName', 'Untitled Notebook')
                
                sections = list_onenote_sections(notebook_id, auth_token)
                
                for section in sections:
                    section_id = section.get('id')
                    section_name = section.get('displayName', 'Untitled Section')
                    
                    pages = list_onenote_pages(section_id, auth_token)
                    
                    for page in pages:
                        page_id = page.get('id')
                        page_title = page.get('title', 'Untitled Page')
                        
                        file_path = construct_file_path(
                            "OneNote", notebook_name, section_name, f"{page_title}.html"
                        )
                        
                        if file_exists_in_storage(file_path):
                            print(f"Skipping existing OneNote page: {page_title}")
                            skipped_files += 1
                            continue
                        
                        futures.append(
                            (
                                executor.submit(
                                    download_and_upload_onenote_page,
                                    page_id,
                                    file_path,
                                    page_title,
                                    auth_token
                                ),
                                page_title
                            )
                        )
            
            # Discovery complete - set totals
            files_total = len(futures)
            mb_total = 0
            await update_data_source_sync_status(
                USER_ID, 'microsoft', 'onenote', 'syncing',
                files_total=files_total,
                mb_total=mb_total,
                sync_start_time=sync_start_time
            )
            # Phase 2: Discovery
            print("----------------------------------------------------------------------")
            print("🔎 Phase 2: Discovery - analyzing notebooks and preparing pages for sync...")
            print("----------------------------------------------------------------------")
            await emit_sync_progress(USER_ID, 'microsoft', 'onenote', {
                'phase': 'discovery',
                'phase_name': 'Phase 2: Discovery',
                'phase_description': 'analyzing notebooks and preparing pages for sync',
                'files_processed': 0,
                'files_total': files_total,
                'mb_processed': 0,
                'mb_total': mb_total,
                'sync_start_time': sync_start_time
            })
            
            files_processed = 0
            mb_processed = 0
            # Phase 3: Processing
            print("----------------------------------------------------------------------")
            print("⚙️  Phase 3: Processing - synchronizing pages to storage...")
            print("----------------------------------------------------------------------")
            for future, page_title in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                        existing_files_cache.add(result['path'])
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        await emit_sync_progress(USER_ID, 'microsoft', 'onenote', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing pages to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': (mb_total if mb_total else mb_processed),
                            'sync_start_time': sync_start_time
                        })
                    else:
                        skipped_files += 1
                except Exception as e:
                    print(f"Error processing OneNote page {page_title}: {str(e)}")
                    log.error(f"Error processing OneNote page {page_title}:", exc_info=True)
                    skipped_files += 1
        
        # Phase 4: Summarizing
        print("----------------------------------------------------------------------")
        print("📊 Phase 4: Summarizing - finalizing OneNote sync results...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'microsoft', 'onenote', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': (mb_total if mb_total else mb_processed),
            'sync_start_time': sync_start_time
        })
        
        print(f"\nOneNote Sync Summary:")
        print(f"Pages uploaded: {len(uploaded_files)}")
        print(f"Pages skipped: {skipped_files}")

        # Accounting Metrics (align with Google)
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"📦 Files Processed: {files_total}")
        print(f"➕ Files Added: {len(uploaded_files)}")
        print(f"🔄 Files Updated: 0")
        print(f"🗑️  Orphans Removed: 0")
        print(f"⛔ Skipped Files: {skipped_files}")

        # Prepare sync results
        sync_results = {
            "latest_sync": {
                "added": len(uploaded_files),
                "updated": 0,
                "removed": 0,
                "skipped": skipped_files,
                "runtime_ms": total_runtime_ms,
                "api_calls": total_api_calls,
                "skip_reasons": {},
                "sync_timestamp": int(time.time())
            },
            "overall_profile": {
                "total_files": files_total,
                "total_size_bytes": max(mb_total or 0, mb_processed or 0),
                "last_updated": int(time.time()),
                "folders_count": 0
            }
        }

        # TEMPORARILY HIDING EMBEDDING PHASE - TODO: May restore in future
        await update_data_source_sync_status(USER_ID, 'microsoft', 'onenote', 'synced', sync_results=sync_results)
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files
        }
        
    except Exception as error:
        print(f"OneNote sync failed: {str(error)}")
        log.error("OneNote sync failed:", exc_info=True)
        raise error

# Outlook integration functions
def list_outlook_messages(auth_token, folder='inbox', query='', max_results=None):
    """List Outlook messages from specified folder with pagination support"""
    try:
        all_messages = []
        skip = 0
        top = 100  # Microsoft Graph API limit
        
        while True:
            # Check if we've reached the max_results limit (if specified)
            if max_results and len(all_messages) >= max_results:
                break
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
            
            if len(messages) < top:
                break
        
        # Trim to max_results if specified
        if max_results and len(all_messages) > max_results:
            all_messages = all_messages[:max_results]
        
        return all_messages
        
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

def download_and_upload_outlook_message(message_id, file_path, auth_token):
    """Download Outlook message and upload using unified storage interface"""
    start_time = time.time()
    
    try:
        message = get_outlook_message(message_id, auth_token)
        if not message:
            return None
        
        message_text = convert_outlook_message_to_text(message)
        if not message_text:
            return None
        
        content_size = len(message_text.encode('utf-8'))
        
        # Check file size before uploading
        if not is_file_size_valid(content_size):
            print(f"Skipping Outlook message (too large): {message.get('subject', 'No Subject')} - {format_bytes(content_size)}")
            return None
        
        success = upload_file_unified(
            message_text.encode('utf-8'),
            file_path,
            'text/plain',
            USER_ID
        )
        
        if not success:
            return None
        
        upload_result = {
            'path': file_path,
            'type': 'new',
            'size': content_size,
            'subject': message.get('subject', 'No Subject'),
            'durationMs': int((time.time() - start_time) * 1000),
            'backend': get_current_backend()
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded Outlook email: {message.get('subject', 'No Subject')}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing Outlook message {message_id}: {str(e)}")
        log.error(f"Error in download_and_upload_outlook_message for {message_id}:", exc_info=True)
        return None

async def sync_outlook_to_storage(auth_token, folder='inbox', query='', max_emails=1000):
    """Sync Outlook messages to storage"""
    global USER_ID
    
    print(f'Starting Outlook sync process for folder: {folder}...')

    # Initialize progress tracking
    sync_start_time = int(time.time())
    # Phase 1: Starting
    print("----------------------------------------------------------------------")
    print("🚀 Phase 1: Starting - preparing sync process...")
    print("----------------------------------------------------------------------")
    await emit_sync_progress(USER_ID, 'microsoft', 'outlook', {
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
    
    uploaded_files = []
    skipped_files = 0
    
    try:
        print(f"Fetching Outlook messages from {folder} (max: {max_emails})")
        messages = list_outlook_messages(auth_token, folder, query, max_emails)
        print(f"Found {len(messages)} Outlook messages")

        # Discovery complete - set totals
        files_total = len(messages)
        mb_total = 0
        await update_data_source_sync_status(
            USER_ID, 'microsoft', 'outlook', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        # Phase 2: Discovery
        print("----------------------------------------------------------------------")
        print("🔎 Phase 2: Discovery - analyzing messages and preparing sync plan...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'microsoft', 'outlook', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing messages and preparing sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            # Phase 3: Processing
            print("----------------------------------------------------------------------")
            print("⚙️  Phase 3: Processing - synchronizing emails to storage...")
            print("----------------------------------------------------------------------")
            for message in messages:
                message_id = message.get('id')
                message_etag = message.get('@odata.etag', '')
                if not message_id:
                    continue
                
                safe_subject = message.get('subject', 'No Subject')[:100]
                file_path = construct_file_path(
                    "Outlook", folder, f"email_{message_etag}_{safe_subject}.txt"
                )
                
                if file_exists_in_storage(file_path):
                    print(f"Skipping existing Outlook email: {safe_subject}")
                    skipped_files += 1
                    continue
                
                futures.append(
                    (
                        executor.submit(
                            download_and_upload_outlook_message,
                            message_id,
                            file_path,
                            auth_token
                        ),
                        message_id
                    )
                )
            
            files_processed = 0
            mb_processed = 0
            for future, message_id in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                        existing_files_cache.add(result['path'])
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        await emit_sync_progress(USER_ID, 'microsoft', 'outlook', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing emails to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': (mb_total if mb_total else mb_processed),
                            'sync_start_time': sync_start_time
                        })
                    else:
                        skipped_files += 1
                except Exception as e:
                    print(f"Error processing Outlook message {message_id}: {str(e)}")
                    log.error(f"Error processing Outlook message {message_id}:", exc_info=True)
                    skipped_files += 1
        
        # Phase 4: Summarizing
        print("----------------------------------------------------------------------")
        print("📊 Phase 4: Summarizing - finalizing Outlook sync results...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'microsoft', 'outlook', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': (mb_total if mb_total else mb_processed),
            'sync_start_time': sync_start_time
        })
        
        print(f"\nOutlook Sync Summary:")
        print(f"Emails uploaded: {len(uploaded_files)}")
        print(f"Emails skipped: {skipped_files}")

        # Accounting Metrics (align with Google)
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"📦 Files Processed: {files_total}")
        print(f"➕ Files Added: {len(uploaded_files)}")
        print(f"🔄 Files Updated: 0")
        print(f"🗑️  Orphans Removed: 0")
        print(f"⛔ Skipped Files: {skipped_files}")

        # Prepare sync results
        sync_results = {
            "latest_sync": {
                "added": len(uploaded_files),
                "updated": 0,
                "removed": 0,
                "skipped": skipped_files,
                "runtime_ms": total_runtime_ms,
                "api_calls": total_api_calls,
                "skip_reasons": {},
                "sync_timestamp": int(time.time())
            },
            "overall_profile": {
                "total_files": files_total,
                "total_size_bytes": max(mb_total or 0, mb_processed or 0),
                "last_updated": int(time.time()),
                "folders_count": 0
            }
        }

        # Phase 5: Embedding
        print("----------------------------------------------------------------------")
        print("🧠 Phase 5: Embedding - vectorizing data for AI processing...")
        print("----------------------------------------------------------------------")
        # TEMPORARILY HIDING EMBEDDING PHASE - TODO: May restore in future
        await update_data_source_sync_status(USER_ID, 'microsoft', 'outlook', 'synced', sync_results=sync_results)
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files
        }
        
    except Exception as error:
        print(f"Outlook sync failed: {str(error)}")
        log.error("Outlook sync failed:", exc_info=True)
        raise error

# OneDrive Functions
def list_onedrive_files_recursively(folder_id, auth_token, current_path='', all_files=None):
    """Recursive file listing with path construction for OneDrive"""
    if all_files is None:
        all_files = []
    
    try:
        if not folder_id or folder_id == 'root':
            url = f"{GRAPH_API_BASE}/me/drive/root/children"
        else:
            url = f"{GRAPH_API_BASE}/me/drive/items/{folder_id}/children"
        
        page_token = None
        all_folder_files = []
        
        while True:
            params = {
                '$top': 1000,
                '$select': 'id,name,size,file,folder,lastModifiedDateTime,createdDateTime,parentReference'
            }
            
            if page_token:
                params['$skiptoken'] = page_token
            
            results = make_request(url, params=params, auth_token=auth_token)
            files = results.get('value', [])
            all_folder_files.extend(files)
            
            if '@odata.nextLink' in results:
                next_link = results['@odata.nextLink']
                if '$skiptoken=' in next_link:
                    page_token = next_link.split('$skiptoken=')[1]
                else:
                    break
            else:
                break
        
        for file in all_folder_files:
            if 'folder' in file:
                folder_name = file['name']
                list_onedrive_files_recursively(
                    file['id'],
                    auth_token,
                    f"{current_path}{folder_name}/", 
                    all_files
                )
            elif 'file' in file:
                if any(file['name'].lower() == pattern.lower() for pattern in EXCLUDED_FILES):
                    print(f"Excluded: {current_path}{file['name']}")
                    continue
                
                # Check file size before processing
                file_size = file.get('size', 0)
                if not is_file_size_valid(file_size):
                    print(f"Skipped (size limit): {current_path}{file['name']} - {format_bytes(file_size)}")
                    continue
                
                if ALLOWED_EXTENSIONS:
                    file_ext = file['name'].split('.')[-1].lower() if '.' in file['name'] else ''
                    if file_ext not in ALLOWED_EXTENSIONS:
                        print(f"Skipped (extension): {file_ext} in {file['name']}")
                        continue
                
                file_info = file.copy()
                file_info['fullPath'] = construct_file_path("OneDrive", current_path, file['name'])
                all_files.append(file_info)
    
    except Exception as error:
        print(f'Listing failed for OneDrive folder {folder_id}: {str(error)}')
        log.error(f'OneDrive listing error for folder {folder_id}:', exc_info=True)
    
    return all_files

def download_onedrive_file(file_id, auth_token):
    """Download file content from OneDrive"""
    try:
        metadata_url = f"{GRAPH_API_BASE}/me/drive/items/{file_id}"
        metadata = make_api_request(metadata_url, auth_token=auth_token)
        
        file_content = io.BytesIO()

        if '@microsoft.graph.downloadUrl' in metadata:
            download_url = metadata['@microsoft.graph.downloadUrl']
            with make_api_request(download_url, stream=True, auth_token=None) as response:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        else:
            download_url = f"{GRAPH_API_BASE}/me/drive/items/{file_id}/content"
            with make_api_request(download_url, auth_token=auth_token, stream=True) as response:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        
        file_content.seek(0)
        return file_content
    
    except Exception as error:
        print(f"OneDrive download failed for {file_id}: {str(error)}")
        log.error(f"OneDrive download failed for {file_id}:", exc_info=True)
        raise

def download_and_upload_onedrive_file(file, auth_token, exists, reason):
    """Helper function to download a OneDrive file and upload using unified storage interface"""
    start_time = time.time()

    if file_exists_in_storage(file['fullPath']):
        print(f"Skipping existing file: {file['fullPath']}")
        return None
    
    try:
        file_content = download_onedrive_file(file['id'], auth_token)
        content_type = file.get('file', {}).get('mimeType')
        
        success = upload_file_unified(
            file_content.getvalue(),
            file['fullPath'],
            content_type,
            USER_ID
        )
        
        if not success:
            return None
        
        upload_result = {
            'path': file['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': file.get('size', 0),
            'driveModified': file.get('lastModifiedDateTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason,
            'backend': get_current_backend()
        }

        existing_files_cache.add(file['fullPath'])
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing OneDrive file {file['fullPath']}: {str(e)}")
        log.error(f"Error processing OneDrive file {file['fullPath']}:", exc_info=True)
        return None

async def sync_onedrive_to_storage(auth_token):
    """Main function to sync OneDrive to storage"""
    global total_api_calls, USER_ID
    
    print('Starting OneDrive sync process...')

    # Initialize progress tracking
    sync_start_time = int(time.time())
    # Phase 1: Starting
    print("----------------------------------------------------------------------")
    print("🚀 Phase 1: Starting - preparing sync process...")
    print("----------------------------------------------------------------------")
    await emit_sync_progress(USER_ID, 'microsoft', 'onedrive', {
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
    
    uploaded_files = []
    deleted_files = []
    skipped_files = 0
    
    try:
        all_files = list_onedrive_files_recursively('root', auth_token)
        print(f"Found {len(all_files)} files in OneDrive (after size filtering)")

        # Discovery complete - set totals
        files_total = len(all_files)
        mb_total = sum(int(f.get('size', 0)) for f in all_files)
        await update_data_source_sync_status(
            USER_ID, 'microsoft', 'onedrive', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        # Phase 2: Discovery
        print("----------------------------------------------------------------------")
        print("🔎 Phase 2: Discovery - analyzing existing files and determining sync plan...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'microsoft', 'onedrive', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing existing files and determining sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        user_prefix = f"userResources/{USER_ID}/Microsoft/OneDrive/"
        existing_files = list_files_unified(prefix=user_prefix, user_id=USER_ID)
        storage_file_map = {}
        for file in existing_files:
            file_name = file.get('name') or file.get('key', '')
            if file_name:
                storage_file_map[file_name] = file
        
        onedrive_file_paths = {file['fullPath'] for file in all_files}
        
        # Delete orphaned files
        for storage_name, storage_file in storage_file_map.items():
            if storage_name.startswith(user_prefix) and storage_name not in onedrive_file_paths:
                delete_file_unified(storage_name, USER_ID)
                
                deleted_files.append({
                    'name': storage_name,
                    'size': storage_file.get('size'),
                    'timeCreated': storage_file.get('timeCreated')
                })
                print(f"[{datetime.now().isoformat()}] Deleted orphan: {storage_name}")
        
        # Process files for upload
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for file in all_files:
                storage_file = storage_file_map.get(file['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not storage_file:
                    needs_upload = True
                    reason = 'New file'
                else:
                    storage_updated = parse_date(storage_file.get('updated'))
                    drive_modified = parse_date(file.get('lastModifiedDateTime'))
                    
                    if drive_modified and storage_updated and drive_modified > storage_updated:
                        needs_upload = True
                        reason = f"OneDrive version newer ({file['lastModifiedDateTime']} > {storage_file.get('updated')})"
                
                if needs_upload:
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_onedrive_file,
                                file,
                                auth_token,
                                bool(storage_file),
                                reason
                            ),
                            file
                        )
                    )
                else:
                    skipped_files += 1
            
            files_processed = 0
            mb_processed = 0
            # Phase 3: Processing
            print("----------------------------------------------------------------------")
            print("⚙️  Phase 3: Processing - synchronizing files to storage...")
            print("----------------------------------------------------------------------")
            for future, file in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        # Emit processing progress update
                        await emit_sync_progress(USER_ID, 'microsoft', 'onedrive', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing files to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': mb_total,
                            'sync_start_time': sync_start_time
                        })
                except Exception as e:
                    print(f"Error uploading {file['fullPath']}: {str(e)}")
                    log.error(f"Error uploading {file['fullPath']}:", exc_info=True)
        
        # Emit summarizing phase before printing summary
        # Phase 4: Summarizing
        print("----------------------------------------------------------------------")
        print("📊 Phase 4: Summarizing - finalizing OneDrive sync results...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'microsoft', 'onedrive', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        print('\nOneDrive Sync Summary:')
        for file in uploaded_files:
            symbol = '+' if file['type'] == 'new' else '^'
            print(f" {symbol} {file['path']} | {format_bytes(file['size'])} | {file['durationMs']}ms | {file['reason']}")
        
        for file in deleted_files:
            print(f" - {file['name']} | {format_bytes(file['size'])} | Created: {file['timeCreated']}")
        
        # Accounting Metrics (align with Google)
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        files_added = len([f for f in uploaded_files if f['type'] == 'new'])
        files_updated = len([f for f in uploaded_files if f['type'] == 'updated'])

        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"📦 Files Processed: {len(all_files)}")
        print(f"➕ Files Added: {files_added}")
        print(f"🔄 Files Updated: {files_updated}")
        print(f"🗑️  Orphans Removed: {len(deleted_files)}")
        
        print(f"\nTotal: +{files_added} added, ^{files_updated} updated, -{len(deleted_files)} removed, {skipped_files} skipped")
        
        # Prepare sync results
        sync_results = {
            "latest_sync": {
                "added": files_added,
                "updated": files_updated,
                "removed": len(deleted_files),
                "skipped": skipped_files,
                "runtime_ms": total_runtime_ms,
                "api_calls": total_api_calls,
                "skip_reasons": {},
                "sync_timestamp": int(time.time())
            },
            "overall_profile": {
                "total_files": len(all_files),
                "total_size_bytes": sum(int(f.get('size', 0) or 0) for f in all_files),
                "last_updated": int(time.time()),
                "folders_count": 0
            }
        }
        
        # Phase 5: Embedding
        print("----------------------------------------------------------------------")
        print("🧠 Phase 5: Embedding - vectorizing data for AI processing...")
        print("----------------------------------------------------------------------")
        # TEMPORARILY HIDING EMBEDDING PHASE - TODO: May restore in future
        await update_data_source_sync_status(USER_ID, 'microsoft', 'onedrive', 'synced', sync_results=sync_results)
              
        return {
            'uploaded': len(uploaded_files),
            'deleted': len(deleted_files),
            'skipped': skipped_files,
            'total_processed': len(all_files)
        }
    
    except Exception as error:
        print(f'OneDrive sync failed: {str(error)}')
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        log.error("OneDrive sync failed:", exc_info=True)
        raise error

# SharePoint Functions
def get_sharepoint_sites(auth_token):
    """Get all SharePoint sites the user has access to"""
    try:
        url = f"{GRAPH_API_BASE}/sites?search="
        
        page_token = None
        all_sites = []
        
        while True:
            params = {'$top': 100}
            
            if page_token:
                params['$skiptoken'] = page_token
            
            results = make_request(url, params=params, auth_token=auth_token)
            sites = results.get('value', [])
            all_sites.extend(sites)
            
            if '@odata.nextLink' in results:
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
        log.error("Error getting SharePoint sites:", exc_info=True)
        return []

def list_sharepoint_files_recursively(site_id, drive_id, folder_id, auth_token, current_path='', all_files=None, site_name=''):
    """Recursive file listing with path construction for SharePoint"""
    if all_files is None:
        all_files = []
    
    try:
        if not folder_id or folder_id == 'root':
            url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/root/children"
        else:
            url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children"
        
        page_token = None
        all_folder_files = []
        
        while True:
            params = {
                '$top': 1000,
                '$select': 'id,name,size,file,folder,lastModifiedDateTime,createdDateTime,parentReference'
            }
            
            if page_token:
                params['$skiptoken'] = page_token
            
            results = make_request(url, params=params, auth_token=auth_token)
            files = results.get('value', [])
            all_folder_files.extend(files)
            
            if '@odata.nextLink' in results:
                next_link = results['@odata.nextLink']
                if '$skiptoken=' in next_link:
                    page_token = next_link.split('$skiptoken=')[1]
                else:
                    break
            else:
                break
        
        for file in all_folder_files:
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
                if any(file['name'].lower() == pattern.lower() for pattern in EXCLUDED_FILES):
                    print(f"Excluded: {current_path}{file['name']}")
                    continue
                
                # Check file size before processing
                file_size = file.get('size', 0)
                if not is_file_size_valid(file_size):
                    print(f"Skipped (size limit): {current_path}{file['name']} - {format_bytes(file_size)}")
                    continue
                
                if ALLOWED_EXTENSIONS:
                    file_ext = file['name'].split('.')[-1].lower() if '.' in file['name'] else ''
                    if file_ext not in ALLOWED_EXTENSIONS:
                        print(f"Skipped (extension): {file_ext} in {file['name']}")
                        continue
                
                file_info = file.copy()
                file_info['fullPath'] = construct_file_path("SharePoint", site_name, current_path, file['name'])
                
                # Add site_id and drive_id to parentReference for later use
                if 'parentReference' not in file_info:
                    file_info['parentReference'] = {}
                file_info['parentReference']['siteId'] = site_id
                file_info['parentReference']['driveId'] = drive_id
                
                all_files.append(file_info)
    
    except Exception as error:
        print(f'Listing failed for SharePoint folder {folder_id} in site {site_id}: {str(error)}')
        log.error(f'SharePoint listing error for folder {folder_id}:', exc_info=True)
    
    return all_files

def download_sharepoint_file(site_id, drive_id, file_id, auth_token):
    """Download file content from SharePoint with proper resource management"""
    try:
        metadata_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{file_id}"
        metadata = make_api_request(metadata_url, auth_token=auth_token)
        
        file_content = io.BytesIO()

        if '@microsoft.graph.downloadUrl' in metadata:
            download_url = metadata['@microsoft.graph.downloadUrl']
            with make_api_request(download_url, stream=True, auth_token=None) as response:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        else:
            download_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{file_id}/content"
            with make_api_request(download_url, auth_token=auth_token, stream=True) as response:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file_content.write(chunk)
        
        file_content.seek(0)
        return file_content
    
    except Exception as error:
        print(f"SharePoint download failed for {file_id}: {str(error)}")
        log.error(f"SharePoint download failed for {file_id}:", exc_info=True)
        raise

def download_and_upload_sharepoint_file(file, auth_token, exists, reason):
    """Helper function to download a SharePoint file and upload using unified storage interface"""
    start_time = time.time()

    if file_exists_in_storage(file['fullPath']):
        print(f"Skipping existing file: {file['fullPath']}")
        return None
    
    try:
        parent_ref = file.get('parentReference', {})
        site_id = parent_ref.get('siteId')
        drive_id = parent_ref.get('driveId')
        
        if not site_id or not drive_id:
            raise ValueError(f"Missing site_id or drive_id in file reference for {file['fullPath']}")
        
        file_content = download_sharepoint_file(site_id, drive_id, file['id'], auth_token)
        content_type = file.get('file', {}).get('mimeType')
        
        success = upload_file_unified(
            file_content.getvalue(),
            file['fullPath'],
            content_type,
            USER_ID
        )
        
        if not success:
            return None
        
        upload_result = {
            'path': file['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': file.get('size', 0),
            'driveModified': file.get('lastModifiedDateTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason,
            'backend': get_current_backend()
        }

        existing_files_cache.add(file['fullPath'])
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing SharePoint file {file['fullPath']}: {str(e)}")
        log.error(f"Error processing SharePoint file {file['fullPath']}:", exc_info=True)
        return None

async def sync_sharepoint_to_storage(auth_token):
    """Main function to sync SharePoint to storage"""
    global total_api_calls, USER_ID
    
    print('Starting SharePoint sync process...')

    # Initialize progress tracking
    sync_start_time = int(time.time())
    # Phase 1: Starting
    print("----------------------------------------------------------------------")
    print("🚀 Phase 1: Starting - preparing sync process...")
    print("----------------------------------------------------------------------")
    await emit_sync_progress(USER_ID, 'microsoft', 'sharepoint', {
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
    
    uploaded_files = []
    deleted_files = []
    skipped_files = 0
    all_files = []
    
    try:
        sites = get_sharepoint_sites(auth_token)
        print(f"Found {len(sites)} SharePoint sites")
        
        for site in sites:
            site_id = site['id']
            site_name = site['displayName']
            print(f"Processing site: {site_name} (ID: {site_id})")
            
            drives_url = f"{GRAPH_API_BASE}/sites/{site_id}/drives"
            drives_response = make_request(drives_url, auth_token=auth_token)
            drives = drives_response.get('value', [])
            print(f"Found {len(drives)} drives in site {site_name}")
            
            for drive in drives:
                drive_id = drive['id']
                drive_name = drive['name']
                print(f"Processing drive: {drive_name} (ID: {drive_id})")
                
                site_files = list_sharepoint_files_recursively(
                    site_id, 
                    drive_id, 
                    "root", 
                    auth_token, 
                    "", 
                    None,
                    f"{site_name}/{drive_name}"
                )
                
                all_files.extend(site_files)
        
        print(f"Found {len(all_files)} files across all SharePoint sites (after size filtering)")

        # Discovery complete - set totals
        files_total = len(all_files)
        mb_total = sum(int(f.get('size', 0)) for f in all_files)
        await update_data_source_sync_status(
            USER_ID, 'microsoft', 'sharepoint', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        # Phase 2: Discovery
        print("----------------------------------------------------------------------")
        print("🔎 Phase 2: Discovery - analyzing existing files and determining sync plan...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'microsoft', 'sharepoint', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing existing files and determining sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        user_prefix = f"userResources/{USER_ID}/Microsoft/SharePoint/"
        existing_files = list_files_unified(prefix=user_prefix, user_id=USER_ID)
        storage_file_map = {}
        for file in existing_files:
            file_name = file.get('name') or file.get('key', '')
            if file_name:
                storage_file_map[file_name] = file
        
        sharepoint_file_paths = {file['fullPath'] for file in all_files}
        
        # Delete orphaned files
        for storage_name, storage_file in storage_file_map.items():
            if storage_name.startswith(user_prefix) and storage_name not in sharepoint_file_paths:
                delete_file_unified(storage_name, USER_ID)
                
                deleted_files.append({
                    'name': storage_name,
                    'size': storage_file.get('size'),
                    'timeCreated': storage_file.get('timeCreated')
                })
                print(f"[{datetime.now().isoformat()}] Deleted orphan: {storage_name}")
        
        # Process files for upload
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for file in all_files:
                storage_file = storage_file_map.get(file['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not storage_file:
                    needs_upload = True
                    reason = 'New file'
                else:
                    storage_updated = parse_date(storage_file.get('updated'))
                    sp_modified = parse_date(file.get('lastModifiedDateTime'))
                    
                    if sp_modified and storage_updated and sp_modified > storage_updated:
                        needs_upload = True
                        reason = f"SharePoint version newer ({file['lastModifiedDateTime']} > {storage_file.get('updated')})"
                
                if needs_upload:
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_sharepoint_file,
                                file,
                                auth_token,
                                bool(storage_file),
                                reason
                            ),
                            file
                        )
                    )
                else:
                    skipped_files += 1
            
            files_processed = 0
            mb_processed = 0
            # Phase 3: Processing
            print("----------------------------------------------------------------------")
            print("⚙️  Phase 3: Processing - synchronizing files to storage...")
            print("----------------------------------------------------------------------")
            for future, file in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        await emit_sync_progress(USER_ID, 'microsoft', 'sharepoint', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing files to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': mb_total,
                            'sync_start_time': sync_start_time
                        })
                except Exception as e:
                    print(f"Error uploading {file['fullPath']}: {str(e)}")
                    log.error(f"Error uploading {file['fullPath']}:", exc_info=True)
        
        # Phase 4: Summarizing
        print("----------------------------------------------------------------------")
        print("📊 Phase 4: Summarizing - finalizing SharePoint sync results...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'microsoft', 'sharepoint', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        print('\nSharePoint Sync Summary:')
        for file in uploaded_files:
            symbol = '+' if file['type'] == 'new' else '^'
            print(f" {symbol} {file['path']} | {format_bytes(file['size'])} | {file['durationMs']}ms | {file['reason']}")
        
        for file in deleted_files:
            print(f" - {file['name']} | {format_bytes(file['size'])} | Created: {file['timeCreated']}")
        
        # Accounting Metrics (align with Google)
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        files_added = len([f for f in uploaded_files if f['type'] == 'new'])
        files_updated = len([f for f in uploaded_files if f['type'] == 'updated'])

        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"📦 Files Processed: {len(all_files)}")
        print(f"➕ Files Added: {files_added}")
        print(f"🔄 Files Updated: {files_updated}")
        print(f"🗑️  Orphans Removed: {len(deleted_files)}")
        
        print(f"\nTotal: +{files_added} added, ^{files_updated} updated, -{len(deleted_files)} removed, {skipped_files} skipped")
        
        # Prepare sync results
        sync_results = {
            "latest_sync": {
                "added": files_added,
                "updated": files_updated,
                "removed": len(deleted_files),
                "skipped": skipped_files,
                "runtime_ms": total_runtime_ms,
                "api_calls": total_api_calls,
                "skip_reasons": {},
                "sync_timestamp": int(time.time())
            },
            "overall_profile": {
                "total_files": len(all_files),
                "total_size_bytes": sum(int(f.get('size', 0) or 0) for f in all_files),
                "last_updated": int(time.time()),
                "folders_count": 0
            }
        }
        
        # Phase 5: Embedding
        print("----------------------------------------------------------------------")
        print("🧠 Phase 5: Embedding - vectorizing data for AI processing...")
        print("----------------------------------------------------------------------")
        # TEMPORARILY HIDING EMBEDDING PHASE - TODO: May restore in future
        await update_data_source_sync_status(
            USER_ID, 'microsoft', 'sharepoint', 'synced', 
            files_total=sync_results['overall_profile']['total_files'],
            mb_total=sync_results['overall_profile']['total_size_bytes'],
            sync_results=sync_results
        )
        
        return {
            'uploaded': len(uploaded_files),
            'deleted': len(deleted_files),
            'skipped': skipped_files,
            'total_processed': len(all_files)
        }
    
    except Exception as error:
        print(f'SharePoint sync failed: {str(error)}')
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        log.error("SharePoint sync failed:", exc_info=True)
        raise error

# Main execution function 
async def initiate_microsoft_sync(
    user_id, 
    auth_token, 
    service_account_base64=None, 
    gcs_bucket_name=None, 
    sync_onedrive=True, 
    sync_sharepoint=True, 
    sync_onenote=True, 
    sync_outlook=True, 
    outlook_folder='inbox', 
    outlook_query='', 
    max_emails=1000,
    storage_backend=None
):
    """Main entry point to sync Microsoft services to configured storage"""
    
    # Initialize globals first
    initialize_globals(user_id)
    
    # Refresh token once at entry (further requests refresh in make_request)
    auth_token = get_valid_microsoft_token(user_id, auth_token)
    
    current_backend = get_current_backend()
    log.info(f"Using storage backend: {current_backend}")
    
    # Load existing files
    load_existing_files(user_id)
    
    # Initialize results
    results = {
        'onedrive': None,
        'sharepoint': None,
        'onenote': None,
        'outlook': None,
        'backend': current_backend
    }
    
    try:
        # Execute sync operations based on parameters
        if sync_onedrive:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'onedrive', 'syncing')
            results['onedrive'] = await sync_onedrive_to_storage(auth_token)
        
        if sync_sharepoint:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'sharepoint', 'syncing')
            results['sharepoint'] = await sync_sharepoint_to_storage(auth_token)
        
        if sync_onenote:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'onenote', 'syncing')
            results['onenote'] = await sync_onenote_to_storage(auth_token)
        
        if sync_outlook:
            await update_data_source_sync_status(USER_ID, 'microsoft', 'outlook', 'syncing')
            results['outlook'] = await sync_outlook_to_storage(
                auth_token, outlook_folder, outlook_query, max_emails
            )
            
        return results
        
    except Exception as e:
        log.error(f"Microsoft sync failed for user {user_id}: {str(e)}", exc_info=True)
        raise