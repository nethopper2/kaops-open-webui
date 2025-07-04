import os
import json
import time
import io
import requests
from requests.auth import HTTPBasicAuth
import concurrent.futures
from datetime import datetime
import logging
from typing import Dict, Any, Optional

from open_webui.models.users import Users
from open_webui.utils.data.data_ingestion import upload_to_gcs, list_gcs_files, delete_gcs_file, make_api_request, format_bytes, parse_date, update_data_source_sync_status, delete_gcs_folder

USER_ID = None
USER = None
USER_AUTH = None
MAX_WORKERS = os.getenv("MAX_SYNC_WORKERS", 5) # Concurrency limit
EXCLUDED_FILES = os.getenv("ATLASSIAN_EXCLUDED_FILES", "").split(',')
ALLOWED_EXTENSIONS = os.getenv("ATLASSIAN_ALLOWED_EXTENSIONS", "").split(',')
script_start_time = None
total_api_calls = 0 # To track API calls for billing/rate limiting

log = logging.getLogger(__name__)

# --- Atlassian Configuration ---
# Atlassian OAuth endpoints (standard OAuth 2.0 3LO)
from open_webui.env import (
ATLASSIAN_ACCESSIBLE_RESOURCES_URL
)

# JIRA Cloud API Version 3
JIRA_CLOUD_API_PATH = "/rest/api/3"
# Confluence Cloud API
CONFLUENCE_CLOUD_API_PATH = "/wiki/rest/api"

def make_atlassian_request(url: str, method: str = 'GET', headers: Optional[Dict[str, str]] = None,
                           params: Optional[Dict[str, Any]] = None, data: Optional[Any] = None,
                           stream: bool = False, auth_token: Optional[str] = None, auth: Optional[str] = None):
    """
    Helper function to make Atlassian API requests, leveraging the robust
    `make_api_request` for error handling and retry logic.
    """
    global total_api_calls
    total_api_calls += 1

    # Ensure headers are initialized
    if headers is None:
        headers = {}
    
    # Set standard Atlassian-specific headers if not already present
    headers.setdefault('Content-Type', 'application/json')
    headers.setdefault('Accept', 'application/json')

    try:
        # Call the generic make_api_request function
        return make_api_request(
            url=url,
            method=method,
            headers=headers,
            params=params,
            data=data,
            stream=stream,
            auth_token=auth_token,
            auth=auth
        )
        
    except Exception as e:
        # Catch any other unexpected errors from make_api_request
        log.error(f"Failed to make Atlassian API request to {url}: {e}", exc_info=True)
        raise Exception(f"Failed to make Atlassian API request after retries for URL: {url}")



def get_accessible_atlassian_sites(auth_token):
    """
    Gets the list of Jira/Confluence sites (cloudId and url) that the user has access to.
    """
    try:
        log.info(f"Fetching accessible Atlassian resources for user with auth token: {ATLASSIAN_ACCESSIBLE_RESOURCES_URL}")
        response = make_atlassian_request(ATLASSIAN_ACCESSIBLE_RESOURCES_URL, auth_token=auth_token)
        return response
    except Exception as e:
        log.error(f"Failed to get accessible Atlassian resources: {e}")
        return []

def list_jira_projects_and_issues(site_url, all_items=None):
    """
    Lists Jira projects and then all issues within those projects.
    Atlassian doesn't have a direct "folder" concept like Google Drive,
    so we iterate through projects and then issues.
    """
    if all_items is None:
        all_items = []

    jira_base_url = f"{site_url}{JIRA_CLOUD_API_PATH}"

    log.info(f"Listing Jira projects for jira_base_url: {jira_base_url}")

    try:
        # Step 1: List all accessible projects
        log.info(f"Listing Jira projects for site: {site_url}")
        start_at = 0
        max_results = 50 # Max page size for projects
        projects = []
        while True:
            params = {
                'startAt': start_at,
                'maxResults': max_results
            }
            response = make_atlassian_request(f"{jira_base_url}/project/search", params=params, auth=USER_AUTH)
            projects.extend(response.get('values', [])) # Use 'values' for paged results
            if response.get('isLast', True):
                break
            start_at = response.get('nextPage', start_at + max_results)
        
        log.info(f"Found {len(projects)} Jira projects for site: {site_url}")

        # Step 2: For each project, search for issues (using JQL)
        for project in projects:
            project_key = project.get('key')
            project_name = project.get('name')
            if not project_key:
                continue

            log.info(f"Listing issues for Jira project: {project_name} ({project_key})")
            start_at_issue = 0
            max_results_issue = 100 # Max page size for search results
            
            while True:
                # JQL to get all issues in the project
                jql_query = f"project = \"{project_key}\""
                params = {
                    'jql': jql_query,
                    'startAt': start_at_issue,
                    'maxResults': max_results_issue,
                    'fields': 'summary,description,status,issuetype,priority,creator,reporter,assignee,created,updated,comment,attachment' # Request relevant fields
                }
                search_response = make_atlassian_request(f"{jira_base_url}/search", params=params, auth=USER_AUTH)
                issues = search_response.get('issues', [])

                for issue in issues:
                    # Construct full path for GCS
                    issue_key = issue.get('key')
                    issue_summary = issue.get('fields', {}).get('summary', 'no_summary').replace('/', '_') # Sanitize for path
                    
                    full_path = f"userResources/{USER_ID}/Atlassian/{site_url.replace('https://', '').replace('/', '_')}/Jira/{project_key}/{issue_key}-{issue_summary}.json"
                    
                    issue_info = {
                        'id': issue.get('id'),
                        'key': issue_key,
                        'fullPath': full_path,
                        'mimeType': 'application/json', # For issue content
                        'content': json.dumps(issue, indent=2), # Store full issue JSON
                        'modifiedTime': issue.get('fields', {}).get('updated'),
                        'createdTime': issue.get('fields', {}).get('created'),
                        'type': 'issue'
                    }
                    all_items.append(issue_info)

                    # Handle attachments for the issue
                    attachments = issue.get('fields', {}).get('attachment', [])
                    for attachment in attachments:
                        attachment_filename = attachment.get('filename')
                        attachment_id = attachment.get('id')
                        attachment_content_url = attachment.get('content') # Direct download URL
                        attachment_mime_type = attachment.get('mimeType')
                        attachment_size = attachment.get('size')
                        
                        attachment_path = f"userResources/{USER_ID}/Atlassian/{site_url.replace('https://', '').replace('/', '_')}/Jira/{project_key}/{issue_key}/attachments/{attachment_filename}"
                        
                        attachment_info = {
                            'id': attachment_id,
                            'fullPath': attachment_path,
                            'mimeType': attachment_mime_type,
                            'downloadUrl': attachment_content_url,
                            'size': attachment_size,
                            'modifiedTime': attachment.get('created'), # Use attachment creation as modified time
                            'createdTime': attachment.get('created'),
                            'type': 'attachment'
                        }
                        all_items.append(attachment_info)

                if search_response.get('total') <= start_at_issue + len(issues):
                    break # No more issues
                start_at_issue += max_results_issue

    except Exception as error:
        log.error(f'Listing Jira projects/issues failed for site {site_url}: {str(error)}', exc_info=True)

    return all_items


def list_confluence_spaces_and_pages(site_url, cloud_id, auth_token, all_items=None):
    """
    Lists Confluence spaces and then all pages within those spaces.
    Handles parent-child page relationships (simple recursion here).
    """
    if all_items is None:
        all_items = []

    confluence_base_url = f"{site_url}{CONFLUENCE_CLOUD_API_PATH}"

    try:
        # Step 1: List all accessible spaces
        log.info(f"Listing Confluence spaces for site: {site_url}")
        start_at = 0
        max_results = 50 # Max page size for spaces
        spaces = []
        while True:
            params = {
                'start': start_at,
                'limit': max_results
            }
            response = make_atlassian_request(f"{confluence_base_url}/space", params=params, auth=USER_AUTH)
            spaces.extend(response.get('results', [])) # Use 'results' for paged results
            if response.get('size', 0) < max_results: # Check if current page has less than max_results
                break
            start_at += max_results
        
        log.info(f"Found {len(spaces)} Confluence spaces for site: {site_url}")

        # Step 2: For each space, list its content (pages)
        for space in spaces:
            space_key = space.get('key')
            space_name = space.get('name')
            if not space_key:
                continue

            log.info(f"Listing pages for Confluence space: {space_name} ({space_key})")
            start_at_page = 0
            max_results_page = 100 # Max page size for content
            
            while True:
                params = {
                    'spaceKey': space_key,
                    'start': start_at_page,
                    'limit': max_results_page,
                    'expand': 'body.storage,version,attachments' # Get page content (storage format) and attachments
                }
                content_response = make_atlassian_request(f"{confluence_base_url}/content", params=params, auth=USER_AUTH)
                pages = content_response.get('results', [])

                for page in pages:
                    # Only process pages (not blogposts, comments, etc. if 'type' is supported)
                    if page.get('type') != 'page':
                        continue

                    page_id = page.get('id')
                    page_title = page.get('title', 'no_title').replace('/', '_') # Sanitize for path

                    full_path = f"userResources/{USER_ID}/Atlassian/{site_url.replace('https://', '').replace('/', '_')}/Confluence/{space_key}/{page_title}-{page_id}.html"
                    
                    page_info = {
                        'id': page_id,
                        'fullPath': full_path,
                        'mimeType': 'text/html', # We'll fetch as HTML or storage format
                        'content': page.get('body', {}).get('storage', {}).get('value'), # Storage format content
                        'modifiedTime': page.get('version', {}).get('when'),
                        'createdTime': page.get('history', {}).get('createdDate'), # Confluence history for creation
                        'type': 'page'
                    }
                    all_items.append(page_info)

                    # Handle attachments for the page
                    attachments = page.get('attachments', {}).get('results', [])
                    for attachment in attachments:
                        attachment_filename = attachment.get('title')
                        attachment_id = attachment.get('id')
                        attachment_download_url = attachment.get('_links', {}).get('download')
                        attachment_mime_type = attachment.get('mediaType')
                        attachment_size = attachment.get('fileSize')

                        if attachment_download_url and attachment_download_url.startswith('/'):
                            attachment_download_url = f"{site_url}{attachment_download_url}" # Make absolute URL

                        attachment_path = f"userResources/{USER_ID}/Atlassian/{site_url.replace('https://', '').replace('/', '_')}/Confluence/{space_key}/{page_title}-{page_id}/attachments/{attachment_filename}"

                        attachment_info = {
                            'id': attachment_id,
                            'fullPath': attachment_path,
                            'mimeType': attachment_mime_type,
                            'downloadUrl': attachment_download_url, # Direct download URL
                            'size': attachment_size,
                            'modifiedTime': attachment.get('version', {}).get('when'),
                            'createdTime': attachment.get('version', {}).get('when'), # Use version date for simplicity
                            'type': 'attachment'
                        }
                        all_items.append(attachment_info)


                if content_response.get('size', 0) < max_results_page: # Check if current page has less than max_results
                    break
                start_at_page += max_results_page

    except Exception as error:
        log.error(f'Listing Confluence spaces/pages failed for site {site_url}: {str(error)}', exc_info=True)

    return all_items


def download_atlassian_content(item_info, auth_token):
    """
    Downloads content for a given Atlassian item (Jira issue JSON, Confluence page HTML, attachment binary).
    """
    file_content = io.BytesIO()
    
    item_type = item_info.get('type')
    mime_type = item_info.get('mimeType')

    if item_type == 'issue':
        # Jira issue content is already in 'content' field as JSON string
        content_bytes = item_info['content'].encode('utf-8')
        file_content.write(content_bytes)
        file_content.seek(0)
        return file_content

    elif item_type == 'page':
        # Confluence page content is in 'content' field as HTML/storage format
        if item_info.get('content'):
            content_bytes = item_info['content'].encode('utf-8')
            file_content.write(content_bytes)
        file_content.seek(0)
        return file_content

    elif item_type == 'attachment' and item_info.get('downloadUrl'):
        download_url = item_info['downloadUrl']
        log.info(f"Downloading attachment from: {download_url}")
        response = make_atlassian_request(
            download_url,
            auth=USER_AUTH,
            stream=True # Stream binary content
        )
        
        # Check if request was successful
        if response.status_code != 200:
            raise Exception(f"Failed to download attachment {item_info.get('fullPath')}: {response.text}")
        
        # Read content into memory
        for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            if chunk:
                file_content.write(chunk)
        
        file_content.seek(0)
        return file_content
    
    else:
        raise ValueError(f"Unsupported Atlassian item type or missing download URL: {item_type}")

def download_and_upload_atlassian_item(item, auth_token, service_account_base64, gcs_bucket_name, exists, reason):
    """Helper function to download an Atlassian item and upload it to GCS"""
    start_time = time.time()
    
    try:
        # Download item content
        file_content_buffer = download_atlassian_content(item, auth_token)
        
        # Upload to GCS
        # Ensure 'size' is obtained from the downloaded content's buffer, especially for issues/pages
        content_size = file_content_buffer.getbuffer().nbytes if file_content_buffer else 0
        
        # Override item size if it's not an attachment or if the content buffer size is more accurate
        # For Jira issues/Confluence pages, `item.get('size')` might be missing or misleading.
        if item.get('type') in ['issue', 'page'] and content_size > 0:
             item['size'] = content_size
        
        if not file_content_buffer:
            raise Exception("Failed to get content buffer for item.")

        result = upload_to_gcs(
            file_content_buffer,
            item['fullPath'],
            item.get('mimeType'),
            service_account_base64,
            gcs_bucket_name
        )
        
        upload_result = {
            'path': item['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': result.get('size') if result else item.get('size'), # Use GCS result size if available
            'atlassianModified': item.get('modifiedTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason
        }
        
        log.info(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {item['fullPath']}")
        return upload_result
        
    except Exception as e:
        log.error(f"Error processing Atlassian item {item.get('fullPath')}: {str(e)}", exc_info=True)
        return None # Ensure None is returned on error


async def sync_atlassian_to_gcs(auth_token, service_account_base64):
    """Main function to sync Atlassian (Jira & Confluence) to Google Cloud Storage"""
    global total_api_calls
    global GCS_BUCKET_NAME
    
    log.info('🔄 Starting recursive sync process for Atlassian...')
    
    uploaded_items = []
    deleted_items = []
    skipped_items = 0
    
    try:
        # Get accessible Atlassian sites
        accessible_sites = get_accessible_atlassian_sites(auth_token)
        if not accessible_sites:
            raise ValueError("Could not retrieve user's accessible Atlassian sites.")
        
        all_atlassian_items = []

        # Process each accessible Atlassian site
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures_to_site = {}
            for site in accessible_sites:
                site_url = site.get('url')
                cloud_id = site.get('id')
                product_uris = site.get('scopes', [])

                log.info(site)
                
                if not site_url or not cloud_id:
                    log.warning(f"Skipping Atlassian resource with missing URL or Cloud ID: {site}")
                    continue

                if 'read:project:jira' in product_uris:
                    futures_to_site[executor.submit(list_jira_projects_and_issues, site_url, [])] = \
                        {"type": "Jira", "site_url": site_url}
                
                if 'read:confluence-content' in product_uris:
                    futures_to_site[executor.submit(list_confluence_spaces_and_pages, site_url, cloud_id, auth_token, [])] = \
                        {"type": "Confluence", "site_url": site_url}

            for future in concurrent.futures.as_completed(futures_to_site):
                site_info = futures_to_site[future]
                try:
                    site_items = future.result()
                    log.info(f"Completed listing {site_info['type']} for site {site_info['site_url']} with {len(site_items)} items")
                    all_atlassian_items.extend(site_items)
                except Exception as e:
                    log.error(f"Error listing {site_info['type']} for site {site_info['site_url']}: {str(e)}", exc_info=True)
        
        log.info(f"Found {len(all_atlassian_items)} items across all accessible Atlassian sites.")
        
        # List all GCS files for this user's Atlassian prefix
        gcs_files = list_gcs_files(service_account_base64, GCS_BUCKET_NAME)
        gcs_file_map = {gcs_file['name']: gcs_file for gcs_file in gcs_files}
        atlassian_item_paths = {item['fullPath'] for item in all_atlassian_items}

        # Delete orphaned GCS files that belong to this user's Atlassian data
        user_prefix = f"userResources/{USER_ID}/Atlassian/"
        for gcs_name, gcs_file in gcs_file_map.items():
            if gcs_name.startswith(user_prefix) and gcs_name not in atlassian_item_paths:
                delete_gcs_file(gcs_name, service_account_base64, GCS_BUCKET_NAME)
                deleted_items.append({
                    'name': gcs_name,
                    'size': gcs_file.get('size'),
                    'timeCreated': gcs_file.get('timeCreated')
                })
                log.info(f"[{datetime.now().isoformat()}] Deleted orphan: {gcs_name}")
        
        # Process items in parallel for upload
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for item in all_atlassian_items:
                # Check for excluded files/extensions (adjust logic as needed for Jira/Confluence specific filtering)
                if item.get('type') == 'attachment':
                    if any(item['fullPath'].lower().endswith(pattern.lower()) for pattern in EXCLUDED_FILES if pattern):
                        log.info(f"🚫 Excluded (filename pattern): {item['fullPath']}")
                        skipped_items += 1
                        continue
                    file_ext = item['fullPath'].split('.')[-1].lower() if '.' in item['fullPath'] else ''
                    if ALLOWED_EXTENSIONS and file_ext not in ALLOWED_EXTENSIONS:
                        log.info(f"🔍 Skipped (extension): {file_ext} in {item['fullPath']}")
                        skipped_items += 1
                        continue

                gcs_file = gcs_file_map.get(item['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not gcs_file:
                    needs_upload = True
                    reason = 'New item'
                else:
                    gcs_updated = parse_date(gcs_file.get('updated'))
                    atlassian_modified = parse_date(item.get('modifiedTime'))
                    
                    if atlassian_modified and gcs_updated and atlassian_modified > gcs_updated:
                        needs_upload = True
                        reason = f"Atlassian version newer ({item['modifiedTime']} > {gcs_file.get('updated')})"
                
                if needs_upload:
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_atlassian_item,
                                item,
                                auth_token,
                                service_account_base64,
                                GCS_BUCKET_NAME,
                                bool(gcs_file),
                                reason
                            ),
                            item # Pass the original item for error logging
                        )
                    )
                else:
                    skipped_items += 1
            
            # Process completed uploads
            for future, item_for_log in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_items.append(result)
                except Exception as e:
                    log.error(f"Error processing future for {item_for_log.get('fullPath')}: {str(e)}", exc_info=True)
        
        # Enhanced summary
        log.info('\nSync Summary:')
        for item in uploaded_items:
            symbol = '+' if item['type'] == 'new' else '^'
            log.info(
                f" {symbol} {item['path']} | {format_bytes(item['size'])} | {item['durationMs']}ms | {item['reason']}"
            )
        
        for item in deleted_items:
            log.info(f" - {item['name']} | {format_bytes(item['size'])} | Created: {item['timeCreated']}")
        
        total_runtime = int((time.time() - script_start_time) * 1000)
        log.info("\nAccounting Metrics:")
        log.info(f"⏱️  Total Runtime: {(total_runtime/1000):.2f} seconds")
        log.info(f"📊 Billable API Calls: {total_api_calls}")
        log.info(f"📦 Items Processed: {len(all_atlassian_items)}")
        log.info(f"🗑️  Orphans Removed: {len(deleted_items)}")
        
        log.info(f"\nTotal: +{len([f for f in uploaded_items if f['type'] == 'new'])} added, " +
              f"^{len([f for f in uploaded_items if f['type'] == 'updated'])} updated, " +
              f"-{len(deleted_items)} removed, {skipped_items} skipped")
        
        await update_data_source_sync_status(USER_ID, 'atlassian', 'synced')
    
    except Exception as error:
        await update_data_source_sync_status(USER_ID, 'atlassian', 'error')
        log.error(f"[{datetime.now().isoformat()}] Atlassian Sync failed critically: {str(error)}", exc_info=True)
        raise error

async def initiate_atlassian_sync(user_id: str, token: str, creds: str, gcs_bucket_name: str):
    log.info(f'Initiating Atlassian (Jira & Confluence) sync to Google Cloud Storage')
    log.info(f'User Open WebUI ID: {user_id}')
    log.info(f'GCS Bucket Name: {gcs_bucket_name}')

    global USER_ID
    global USER_AUTH
    global GCS_BUCKET_NAME
    global script_start_time
    global total_api_calls

    log.info(token)

    USER_ID = user_id
    USER = Users.get_user_by_id(user_id) 
    USER_AUTH = HTTPBasicAuth("fareed@nethopper.io", token) 
    GCS_BUCKET_NAME = gcs_bucket_name
    total_api_calls = 0
    script_start_time = time.time()

    await update_data_source_sync_status(USER_ID, 'atlassian', 'syncing')

    try:
        await sync_atlassian_to_gcs(token, creds)
    except Exception as e:
        log.error(f"Atlassian sync initiation failed: {e}", exc_info=True)
        # The sync_atlassian_to_gcs already updates status to 'error', but good to catch here too.
        await update_data_source_sync_status(USER_ID, 'atlassian', 'error')
        raise # Re-raise to propagate the error if needed by the caller