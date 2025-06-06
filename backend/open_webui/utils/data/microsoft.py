import os
import time
import requests
import concurrent.futures
import io
import traceback
import logging
from datetime import datetime
from urllib.parse import urlencode, quote

from open_webui.env import SRC_LOG_LEVELS

from open_webui.utils.data.data_ingestion import upload_to_gcs, list_gcs_files, delete_gcs_file, parse_date, format_bytes, validate_config, make_api_request, update_data_source_sync_status

from open_webui.models.data import DataSources
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

# Microsoft Graph API endpoints
GRAPH_API_BASE = 'https://graph.microsoft.com/v1.0'

def make_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with error handling"""
    global total_api_calls
    total_api_calls += 1
    
    return make_api_request(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)

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
                file_info['fullPath'] = f"{USER_ID}/OneDrive/{current_path}{file['name']}"
                
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
                file_info['fullPath'] = f"{USER_ID}/SharePoint/{site_name}/{current_path}{file['name']}"
                
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
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing OneDrive file {file['fullPath']}: {str(e)}")
        return None

def download_and_upload_sharepoint_file(file, auth_token, service_account_base64, GCS_BUCKET_NAME, exists, reason):
    """Helper function to download a SharePoint file and upload it to GCS"""
    start_time = time.time()
    
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
        
        print(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {file['fullPath']}")
        return upload_result
        
    except Exception as e:
        print(f"Error processing SharePoint file {file['fullPath']}: {str(e)}")
        return None

def sync_onedrive_to_gcs(auth_token, service_account_base64, GCS_BUCKET_NAME):
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
        gcs_files = list_gcs_files(service_account_base64, GCS_BUCKET_NAME)
        gcs_file_map = {gcs_file['name']: gcs_file for gcs_file in gcs_files}
        onedrive_file_paths = {file['fullPath'] for file in all_files}
        
        # Delete orphaned GCS files that belong to this user
        user_prefix = f"{USER_ID}/OneDrive/"
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
              
        return {
            'uploaded': len(uploaded_files),
            'deleted': len(deleted_files),
            'skipped': skipped_files,
            'total_processed': len(all_files)
        }
    
    except Exception as error:
        update_data_source_sync_status(USER_ID, 'microsoft', 'error')
        print(f'OneDrive sync failed: {str(error)}')
        # Log the full error for debugging
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        print(traceback.format_exc())
        raise error


def sync_sharepoint_to_gcs(auth_token, service_account_base64, GCS_BUCKET_NAME):
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
        gcs_files = list_gcs_files(service_account_base64, GCS_BUCKET_NAME)
        gcs_file_map = {gcs_file['name']: gcs_file for gcs_file in gcs_files}
        sharepoint_file_paths = {file['fullPath'] for file in all_files}
        
        # Delete orphaned GCS files that belong to this user's SharePoint
        user_prefix = f"{USER_ID}/SharePoint/"
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
        
        # Add proper return value
        return {
            'uploaded': len(uploaded_files),
            'deleted': len(deleted_files),
            'skipped': skipped_files,
            'total_processed': len(all_files)
        }
    
    except Exception as error:
        update_data_source_sync_status(USER_ID, 'microsoft', 'error')
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
def initiate_microsoft_sync(user_id, auth_token, service_account_base64, gcs_bucket_name, sync_onedrive=True, sync_sharepoint=True):
    """
    Main entry point to sync both OneDrive and SharePoint to GCS
    
    Args:
        auth_token (str): Microsoft Graph API auth token
        service_account_base64 (str): Base64-encoded Google service account JSON
        user_id (str): User ID to prefix file paths
        bucket_name (str): GCS bucket name
        sync_onedrive (bool): Whether to sync OneDrive
        sync_sharepoint (bool): Whether to sync SharePoint
        
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
    
    # Validate configuration
    validate_config()
    
    results = {
        'onedrive': None,
        'sharepoint': None
    }

    update_data_source_sync_status(USER_ID, 'microsoft', 'syncing')
    
    # Sync OneDrive if requested
    if sync_onedrive:
        results['onedrive'] = sync_onedrive_to_gcs(auth_token, service_account_base64, gcs_bucket_name)
    
    # Sync SharePoint if requested
    if sync_sharepoint:
        results['sharepoint'] = sync_sharepoint_to_gcs(auth_token, service_account_base64, gcs_bucket_name)

    update_data_source_sync_status(USER_ID, 'microsoft', 'synced')
    
    return results