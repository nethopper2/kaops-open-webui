import os
import time
import concurrent.futures
import io
import traceback
import logging
from datetime import datetime
import requests
import base64
import json

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

# Global variables
existing_files_cache = set()
total_api_calls = 0
script_start_time = time.time()
USER_ID = ""

# Load environment variables for Mineral OAuth
MINERAL_CLIENT_ID = os.environ.get('MINERAL_CLIENT_ID')
MINERAL_CLIENT_SECRET = os.environ.get('MINERAL_CLIENT_SECRET')
MINERAL_BASE_URL = os.environ.get('MINERAL_BASE_URL', 'https://restapis.trustmineral.com')  # Production by default
MINERAL_REDIRECT_URI = os.environ.get('MINERAL_REDIRECT_URI')

MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '4'))  # Parallel processing workers

# Rate limiting configuration
RATE_LIMIT_CALLS = int(os.environ.get('MINERAL_RATE_LIMIT_CALLS', '100'))  # Calls per hour
RATE_LIMIT_WINDOW = int(os.environ.get('MINERAL_RATE_LIMIT_WINDOW', '3600'))  # 1 hour in seconds

# Rate limiting state
rate_limit_calls = []

def initialize_globals(user_id):
    """Initialize global variables properly"""
    global USER_ID, existing_files_cache
    
    if not user_id:
        raise ValueError("user_id is required")
    
    USER_ID = user_id
    existing_files_cache = set()

def load_existing_files(user_id):
    """Load existing files into memory for duplicate checking using unified interface"""
    global existing_files_cache, USER_ID
    
    try:
        current_backend = get_current_backend()
        print(f"Loading existing files from {current_backend} storage for duplicate checking...")
        user_prefix = f"userResources/{USER_ID}/Mineral/"
        
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

def check_rate_limit():
    """Check if we're within rate limits"""
    global rate_limit_calls
    
    current_time = time.time()
    # Remove calls older than the rate limit window
    rate_limit_calls = [call_time for call_time in rate_limit_calls if current_time - call_time < RATE_LIMIT_WINDOW]
    
    if len(rate_limit_calls) >= RATE_LIMIT_CALLS:
        oldest_call = min(rate_limit_calls)
        sleep_time = RATE_LIMIT_WINDOW - (current_time - oldest_call)
        if sleep_time > 0:
            print(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
            # Clean up the list after sleeping
            current_time = time.time()
            rate_limit_calls = [call_time for call_time in rate_limit_calls if current_time - call_time < RATE_LIMIT_WINDOW]

def make_mineral_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make Mineral API requests with error handling and rate limiting"""
    global total_api_calls, rate_limit_calls
    
    check_rate_limit()
    
    total_api_calls += 1
    rate_limit_calls.append(time.time())
    
    return make_api_request(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)

def list_mineral_handbooks(auth_token, base_url):
    """List all handbooks available in Mineral"""
    try:
        url = f"{base_url}/v2/handbooks"
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        
        response = make_mineral_request(url, headers=headers)
        return response.get('handbooks', []) if isinstance(response, dict) else response
        
    except Exception as error:
        print(f"Error listing Mineral handbooks: {str(error)}")
        log.error("Error in list_mineral_handbooks:", exc_info=True)
        return []

def get_mineral_handbook_details(handbook_id, auth_token, base_url):
    """Get detailed information about a specific handbook"""
    try:
        url = f"{base_url}/v2/handbooks/{handbook_id}"
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        
        response = make_mineral_request(url, headers=headers)
        return response
        
    except Exception as error:
        print(f"Error getting handbook details for {handbook_id}: {str(error)}")
        log.error(f"Error in get_mineral_handbook_details for {handbook_id}:", exc_info=True)
        return None

def download_mineral_handbook(handbook_id, auth_token, base_url):
    """Download handbook content from Mineral in order of preference: DOCX, PDF, HTML"""
    try:
        headers = {
            'Authorization': f'Bearer {auth_token}',
        }
                
        # First try: DOCX format with explicit parameter
        try:
            docx_url = f"{base_url}/v2/handbooks/{handbook_id}?format=docx"
            print(f"Attempting DOCX download for handbook {handbook_id}")
            
            response = make_mineral_request(docx_url, headers=headers, stream=True)
            
            # Check if response is successful and contains binary content
            if hasattr(response, 'iter_content'):
                content = io.BytesIO()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        content.write(chunk)
                content.seek(0)
                
                # Verify we have content and it's a valid DOCX
                content_data = content.getvalue()
                if (content_data and 
                    (content_data.startswith(b'PK') or len(content_data) > 1000) and
                    not content_data.startswith(b'<!DOCTYPE') and 
                    not content_data.startswith(b'<html')):
                    print(f"Successfully downloaded DOCX for handbook {handbook_id}")
                    return content, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'
                else:
                    print(f"DOCX download returned invalid content for handbook {handbook_id}")
                    
        except Exception as docx_error:
            print(f"DOCX download failed for {handbook_id}: {str(docx_error)}")
            
        # Second try: PDF format with explicit parameter
        try:
            pdf_url = f"{base_url}/v2/handbooks/{handbook_id}?format=pdf"
            print(f"Attempting PDF download for handbook {handbook_id}")
            
            response = make_mineral_request(pdf_url, headers=headers, stream=True)
            
            # Check if response is successful and contains binary content
            if hasattr(response, 'iter_content'):
                content = io.BytesIO()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        content.write(chunk)
                content.seek(0)
                
                # Verify we have content and it's a PDF
                content_data = content.getvalue()
                if content_data and (content_data.startswith(b'%PDF') or len(content_data) > 1000):
                    print(f"Successfully downloaded PDF for handbook {handbook_id}")
                    return content, 'application/pdf', '.pdf'
                else:
                    print(f"PDF download returned invalid content for handbook {handbook_id}")
                    
        except Exception as pdf_error:
            print(f"PDF download failed for {handbook_id}: {str(pdf_error)}")
            
        # Third try: HTML content as fallback
        try:
            html_url = f"{base_url}/v2/handbooks/{handbook_id}/content"
            print(f"Attempting HTML content download for handbook {handbook_id}")
            
            response = make_mineral_request(html_url, headers=headers)
            
            if hasattr(response, 'json'):
                try:
                    json_data = response.json()
                    content_text = json_data.get('content', '')
                    if content_text:
                        content = io.BytesIO(content_text.encode('utf-8'))
                        print(f"Successfully downloaded HTML content for handbook {handbook_id}")
                        return content, 'text/html', '.html'
                except:
                    pass
                    
            # Try as text response
            if hasattr(response, 'text'):
                content_text = response.text
                if content_text and len(content_text) > 10:
                    content = io.BytesIO(content_text.encode('utf-8'))
                    print(f"Successfully downloaded HTML content for handbook {handbook_id}")
                    return content, 'text/html', '.html'
                    
        except Exception as html_error:
            print(f"HTML content download failed for {handbook_id}: {str(html_error)}")
        
        print(f"All download formats failed for handbook {handbook_id}")
        return None, None, None
        
    except Exception as error:
        print(f"Error downloading handbook {handbook_id}: {str(error)}")
        log.error(f"Error in download_mineral_handbook for {handbook_id}:", exc_info=True)
        return None, None, None

def download_and_upload_mineral_handbook(handbook_id, handbook_info, auth_token, base_url):
    """Download Mineral handbook and upload using unified storage interface"""
    start_time = time.time()
    
    try:
        print(f"Using fallback metadata from handbook list for {handbook_id}")
        handbook_details = {
                'id': handbook_id,
                'title': handbook_info.get('handbookName', f'Handbook_{handbook_id}'),
                'type': 'list_fallback'
            }
        
        title = handbook_details.get('title', f'Handbook_{handbook_id}')
        safe_title = title.replace('/', '_').replace('\\', '_').replace(':', '_')
        
        # Check if any format already exists (DOCX, PDF, or HTML)
        docx_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}.docx"
        pdf_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}.pdf"
        html_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}.html"
        
        if file_exists_in_storage(docx_path) or file_exists_in_storage(pdf_path) or file_exists_in_storage(html_path):
            print(f"Skipping existing handbook: {title}")
            return None
        
        # Download handbook content (tries DOCX, then PDF, then HTML)
        handbook_content, content_type, file_ext = download_mineral_handbook(handbook_id, auth_token, base_url)
        if not handbook_content:
            print(f"Failed to download handbook {handbook_id} in any format")
            return None
        
        # Create file path with appropriate extension
        file_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}{file_ext}"
        
        # Upload using unified storage interface
        success = upload_file_unified(
            handbook_content.getvalue(),
            file_path,
            content_type,
            USER_ID
        )
        
        if not success:
            return None
        
        # Add to cache
        existing_files_cache.add(file_path)
        
        upload_result = {
            'path': file_path,
            'type': 'new',
            'size': len(handbook_content.getvalue()),
            'title': title,
            'handbook_id': handbook_id,
            'format': file_ext.replace('.', '').upper(),
            'durationMs': int((time.time() - start_time) * 1000),
            'backend': get_current_backend()
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded handbook: {title} ({file_ext.replace('.', '').upper()})")
        return upload_result
        
    except Exception as e:
        print(f"Error processing handbook {handbook_id}: {str(e)}")
        log.error(f"Error in download_and_upload_mineral_handbook for {handbook_id}:", exc_info=True)
        return None

async def sync_mineral_to_storage(auth_token, base_url):
    """Sync Mineral handbooks to unified storage"""
    global USER_ID
    
    print('🔄 Starting Mineral HR sync process...')

    # Initialize progress tracking
    sync_start_time = int(time.time())
    await emit_sync_progress(USER_ID, 'mineral', 'handbooks', {
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
    format_stats = {'DOCX': 0, 'PDF': 0, 'HTML': 0}
    
    try:
        # Get Mineral handbooks
        handbooks = list_mineral_handbooks(auth_token, base_url)
        print(f"Found {len(handbooks)} Mineral handbooks")

        # Discovery complete - set totals
        files_total = len(handbooks)
        mb_total = 0
        await update_data_source_sync_status(
            USER_ID, 'mineral', 'handbooks', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        await emit_sync_progress(USER_ID, 'mineral', 'handbooks', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing handbooks and preparing sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for handbook in handbooks:
                handbook_id = handbook.get('id')
                if not handbook_id:
                    continue
                
                # Create file path for duplicate checking
                title = handbook.get('title', f'Handbook_{handbook_id}')
                safe_title = title.replace('/', '_').replace('\\', '_').replace(':', '_')
                
                # Check if any format already exists
                docx_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}.docx"
                pdf_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}.pdf"
                html_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}.html"
                
                if file_exists_in_storage(docx_path) or file_exists_in_storage(pdf_path) or file_exists_in_storage(html_path):
                    print(f"⏭️  Skipping existing handbook: {title}")
                    skipped_files += 1
                    continue
                
                # Submit download task
                futures.append(
                    (
                        executor.submit(
                            download_and_upload_mineral_handbook,
                            handbook_id,
                            handbook,
                            auth_token,
                            base_url
                        ),
                        title
                    )
                )
            
            # Process completed uploads
            files_processed = 0
            mb_processed = 0
            for future, title in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                        existing_files_cache.add(result['path'])  # Add to cache
                        format_stats[result['format']] += 1
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        await emit_sync_progress(USER_ID, 'mineral', 'handbooks', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing handbooks to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': mb_total,
                            'sync_start_time': sync_start_time
                        })
                    else:
                        skipped_files += 1
                except Exception as e:
                    print(f"Error processing handbook {title}: {str(e)}")
                    log.error(f"Error processing handbook {title}:", exc_info=True)
                    skipped_files += 1
        
        # Emit summarizing phase before printing summary
        await emit_sync_progress(USER_ID, 'mineral', 'handbooks', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed if files_total else 0,
            'files_total': files_total,
            'mb_processed': mb_processed if files_total else 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        current_backend = get_current_backend()
        print(f"\nMineral HR Sync Summary:")
        for file in uploaded_files:
            symbol = '+' if file['type'] == 'new' else '^'
            print(f" {symbol} {file['path']} | {format_bytes(file['size'])} | {file['durationMs']}ms | {file.get('format')} | {file['backend']}")
        print(f"📚 Handbooks uploaded: {len(uploaded_files)}")
        print(f"⏭️  Handbooks skipped: {skipped_files}")
        print(f"💾 Storage Backend: {current_backend}")
        print(f"📄 Format breakdown:")
        for format_type, count in format_stats.items():
            if count > 0:
                print(f"   {format_type}: {count}")

        # Accounting Metrics (Google-style)
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"📦 Handbooks Processed: {files_total}")
        print(f"➕ Handbooks Added: {len(uploaded_files)}")
        print(f"🔄 Handbooks Updated: 0")
        print(f"🗑️  Orphans Removed: 0")
        print(f"⛔ Skipped: {skipped_files}")

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
                "total_size_bytes": 0,
                "last_updated": int(time.time()),
                "folders_count": 0
            }
        }

        # Final state: Embedding (to match Google)
        await update_data_source_sync_status(
            USER_ID, 'mineral', 'handbooks', 'embedding',
            files_total=sync_results['overall_profile']['total_files'],
            mb_total=sync_results['overall_profile']['total_size_bytes'],
            sync_results=sync_results
        )
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files,
            'format_stats': format_stats,
            'backend': current_backend
        }
        
    except Exception as error:
        print(f"Mineral HR sync failed: {str(error)}")
        log.error("Mineral HR sync failed:", exc_info=True)
        # Update status to error for consistency
        try:
            await update_data_source_sync_status(USER_ID, 'mineral', 'handbooks', 'error')
        except Exception:
            pass
        raise error

async def initiate_mineral_sync(
    user_id, 
    access_token, 
    base_url, 
    service_account_base64=None, 
    gcs_bucket_name=None,
    storage_backend=None
):
    """
    Main entry point to sync Mineral HR handbooks to unified storage
    
    Args:
        user_id (str): User ID to prefix file paths
        access_token (str): Valid OAuth access token
        base_url (str): Mineral API base URL
        service_account_base64 (str, optional): Base64-encoded Google service account JSON
        gcs_bucket_name (str, optional): GCS bucket name
        storage_backend (str, optional): Storage backend to use ('gcs', 'pai', etc.)
        
    Returns:
        dict: Summary of sync operations
    """
    global script_start_time
    global total_api_calls

    # Initialize globals first
    initialize_globals(user_id)
    
    current_backend = get_current_backend()
    log.info(f"Using storage backend: {current_backend}")

    total_api_calls = 0
    script_start_time = time.time()

    log.info(f"Initiating Mineral HR sync for user {USER_ID} using {current_backend} storage")
    
    # Load existing files for duplicate checking
    load_existing_files(user_id)
    
    try:
        # Update sync status
        await update_data_source_sync_status(USER_ID, 'mineral', 'handbooks', 'syncing')
        
        # Sync handbooks
        results = await sync_mineral_to_storage(access_token, base_url)
        
        # Enhanced summary
        total_runtime = int((time.time() - script_start_time) * 1000)
        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_runtime/1000):.2f} seconds")
        print(f"📊 Total API Calls: {total_api_calls}")
        print(f"📚 Handbooks Processed: {results['uploaded'] + results['skipped']}")
        print(f"💾 Storage Backend: {current_backend}")
        
        print(f"\nTotal: +{results['uploaded']} handbooks uploaded, {results['skipped']} skipped")
        
        return results
        
    except Exception as error:
        log.error("Mineral HR sync failed:", exc_info=True)
        # Update sync status to failed
        try:
            await update_data_source_sync_status(USER_ID, 'mineral', 'handbooks', 'failed')
        except:
            pass  # Don't let status update failure mask the original error
        raise error