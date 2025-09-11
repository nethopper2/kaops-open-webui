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

from open_webui.utils.data.data_ingestion import upload_to_gcs, list_gcs_files, delete_gcs_file, parse_date, format_bytes, validate_config, make_api_request, update_data_source_sync_status

from open_webui.models.data import DataSources

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

existing_gcs_files = set()

# Metrics tracking
total_api_calls = 0
script_start_time = time.time()

# Load environment variables for Mineral OAuth
USER_ID = ""
GCS_BUCKET_NAME = ""
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

def load_existing_gcs_files(service_account_base64, gcs_bucket_name):
    """Load existing GCS files into memory for duplicate checking"""
    global existing_gcs_files, USER_ID
    
    try:
        print("Loading existing files from GCS for duplicate checking...")
        user_prefix = f"userResources/{USER_ID}/Mineral/"
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

def download_and_upload_mineral_handbook(handbook_id, handbook_info, auth_token, base_url, service_account_base64, gcs_bucket_name):
    """Download Mineral handbook and upload to GCS"""
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
        
        if file_exists_in_gcs(docx_path) or file_exists_in_gcs(pdf_path) or file_exists_in_gcs(html_path):
            print(f"Skipping existing handbook: {title}")
            return None
        
        # Download handbook content (tries DOCX, then PDF, then HTML)
        handbook_content, content_type, file_ext = download_mineral_handbook(handbook_id, auth_token, base_url)
        if not handbook_content:
            print(f"Failed to download handbook {handbook_id} in any format")
            return None
        
        # Create file path with appropriate extension
        file_path = f"userResources/{USER_ID}/Mineral/Handbooks/tokenized-documents/{safe_title}{file_ext}"
        
        # Upload to GCS
        result = upload_to_gcs(
            handbook_content,
            file_path,
            content_type,
            service_account_base64,
            gcs_bucket_name
        )
        
        upload_result = {
            'path': file_path,
            'type': 'new',
            'size': result.get('size'),
            'title': title,
            'handbook_id': handbook_id,
            'format': file_ext.replace('.', '').upper(),
            'durationMs': int((time.time() - start_time) * 1000)
        }
        
        print(f"[{datetime.now().isoformat()}] Uploaded handbook: {title} ({file_ext.replace('.', '').upper()})")
        return upload_result
        
    except Exception as e:
        print(f"Error processing handbook {handbook_id}: {str(e)}")
        log.error(f"Error in download_and_upload_mineral_handbook for {handbook_id}:", exc_info=True)
        return None

async def sync_mineral_to_gcs(auth_token, base_url, service_account_base64, gcs_bucket_name):
    """Sync Mineral handbooks to GCS"""
    global USER_ID
    
    print('🔄 Starting Mineral HR sync process...')
    
    uploaded_files = []
    skipped_files = 0
    format_stats = {'DOCX': 0, 'PDF': 0, 'HTML': 0}
    
    try:
        # Get Mineral handbooks
        handbooks = list_mineral_handbooks(auth_token, base_url)
        print(f"Found {len(handbooks)} Mineral handbooks")
        
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
                
                if file_exists_in_gcs(docx_path) or file_exists_in_gcs(pdf_path) or file_exists_in_gcs(html_path):
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
                            base_url,
                            service_account_base64,
                            gcs_bucket_name
                        ),
                        title
                    )
                )
            
            # Process completed uploads
            for future, title in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_files.append(result)
                        existing_gcs_files.add(result['path'])  # Add to cache
                        format_stats[result['format']] += 1
                    else:
                        skipped_files += 1
                except Exception as e:
                    print(f"Error processing handbook {title}: {str(e)}")
                    log.error(f"Error processing handbook {title}:", exc_info=True)
                    skipped_files += 1
        
        print(f"\nMineral HR Sync Summary:")
        print(f"📚 Handbooks uploaded: {len(uploaded_files)}")
        print(f"⏭️  Handbooks skipped: {skipped_files}")
        print(f"📄 Format breakdown:")
        for format_type, count in format_stats.items():
            if count > 0:
                print(f"   {format_type}: {count}")

        await update_data_source_sync_status(USER_ID, 'mineral', 'handbooks', 'synced')
        
        return {
            'uploaded': len(uploaded_files),
            'skipped': skipped_files,
            'format_stats': format_stats
        }
        
    except Exception as error:
        print(f"Mineral HR sync failed: {str(error)}")
        log.error("Mineral HR sync failed:", exc_info=True)
        raise error

async def initiate_mineral_sync(user_id, access_token, base_url, service_account_base64, gcs_bucket_name):
    """
    Main entry point to sync Mineral HR handbooks to GCS
    This function matches the pattern used by other providers in the router
    
    Args:
        user_id (str): User ID to prefix file paths
        access_token (str): Valid OAuth access token
        base_url (str): Mineral API base URL
        service_account_base64 (str): Base64-encoded Google service account JSON
        gcs_bucket_name (str): GCS bucket name
        
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

    log.info(f"Initiating Mineral HR sync for user {USER_ID} to bucket {GCS_BUCKET_NAME}")
    
    # Load existing GCS files for duplicate checking
    load_existing_gcs_files(service_account_base64, gcs_bucket_name)
    
    try:
        # Update sync status
        await update_data_source_sync_status(USER_ID, 'mineral', 'handbooks', 'syncing')
        
        # Sync handbooks
        results = await sync_mineral_to_gcs(access_token, base_url, service_account_base64, gcs_bucket_name)
        
        # Enhanced summary
        total_runtime = int((time.time() - script_start_time) * 1000)
        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_runtime/1000):.2f} seconds")
        print(f"📊 Total API Calls: {total_api_calls}")
        print(f"📚 Handbooks Processed: {results['uploaded'] + results['skipped']}")
        
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