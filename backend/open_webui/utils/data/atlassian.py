import os
import json
import time
import io
import jwt
import requests
from requests.auth import HTTPBasicAuth
import concurrent.futures
from datetime import datetime
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import quote

from open_webui.models.users import Users
from open_webui.utils.data.data_ingestion import (
    upload_file_unified,
    list_files_unified,
    delete_file_unified,
    delete_folder_unified,
    make_api_request,
    format_bytes,
    parse_date,
    update_data_source_sync_status
)

# Global variables
USER_ID = None
USER = None
MAX_WORKERS = int(os.getenv("MAX_SYNC_WORKERS", "5"))
EXCLUDED_FILES = [f.strip() for f in os.getenv("ATLASSIAN_EXCLUDED_FILES", "").split(',') if f.strip()]
ALLOWED_EXTENSIONS = [ext.strip().lower() for ext in os.getenv("ATLASSIAN_ALLOWED_EXTENSIONS", "").split(',') if ext.strip()]
script_start_time = None
total_api_calls = 0

log = logging.getLogger(__name__)
from open_webui.env import SRC_LOG_LEVELS
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

# Atlassian Configuration
from open_webui.env import (
ATLASSIAN_ACCESSIBLE_RESOURCES_URL,
ATLASSIAN_DEPLOYMENT_TYPE,
ATLASSIAN_SELF_HOSTED_ENABLED,
ATLASSIAN_SELF_HOSTED_JIRA_URL,
ATLASSIAN_SELF_HOSTED_CONFLUENCE_URL,
ATLASSIAN_SELF_HOSTED_AUTH_TYPE,
)
JIRA_CLOUD_API_PATH = "/rest/api/3"
CONFLUENCE_CLOUD_API_PATH = "/wiki/rest/api"

# Layer configuration mapping
LAYER_CONFIG = {
    'jira': {
        'folder': 'Jira',
        'process_jira': True,
        'process_confluence': False,
        'required_scopes': ['read:project:jira', 'read:issue:jira']
    },
    'confluence': {
        'folder': 'Confluence', 
        'process_jira': False,
        'process_confluence': True,
        'required_scopes': ['read:confluence-content', 'read:content:confluence']
    }
}

def detect_atlassian_deployment(bearer_token: str = None, base_url: str = None) -> str:
    """Detect if this is cloud or self-hosted Atlassian"""
    if base_url:
        return 'self_hosted'
    if bearer_token:
        try:
            # Try to decode JWT - Cloud tokens are JWTs
            jwt.decode(bearer_token, options={"verify_signature": False})
            return 'cloud'
        except:
            return 'self_hosted'
    return 'cloud'  # default

# def make_atlassian_request(url: str, method: str = 'GET', headers: Optional[Dict[str, str]] = None,
#                            params: Optional[Dict[str, Any]] = None, data: Optional[Any] = None,
#                            stream: bool = False, bearer_token: Optional[str] = None, auth: Optional[str] = None):
#     """
#     Helper function to make Atlassian API requests with Bearer token authentication.
#     """
#     global total_api_calls
#     total_api_calls += 1

#     # Ensure headers are initialized
#     if headers is None:
#         headers = {}
    
#     # Set standard Atlassian-specific headers if not already present
#     headers.setdefault('Content-Type', 'application/json')
#     headers.setdefault('Accept', 'application/json')
    
#     # Add Bearer token authentication
#     if bearer_token:
#         headers['Authorization'] = f'Bearer {bearer_token}'

#     try:
#         # Call the generic make_api_request function without auth parameter since we're using headers
#         return make_api_request(
#             url=url,
#             method=method,
#             headers=headers,
#             params=params,
#             data=data,
#             stream=stream,
#             auth=auth
#         )
        
#     except Exception as e:
#         log.error(f"Failed to make Atlassian API request to {url}: {e}", exc_info=True)
#         raise Exception(f"Failed to make Atlassian API request after retries for URL: {url}")


def make_atlassian_request(url: str, method: str = 'GET', headers: Optional[Dict[str, str]] = None,
                           params: Optional[Dict[str, Any]] = None, data: Optional[Any] = None,
                           stream: bool = False, bearer_token: Optional[str] = None, 
                           auth: Optional[HTTPBasicAuth] = None):
    """
    Unified request handler - supports Bearer token (cloud OAuth or self-hosted PAT)
    """
    global total_api_calls
    total_api_calls += 1

    if headers is None:
        headers = {}
    
    headers.setdefault('Content-Type', 'application/json')
    headers.setdefault('Accept', 'application/json')
    
    # Use Bearer token for both cloud OAuth and self-hosted PAT
    if bearer_token:
        headers['Authorization'] = f'Bearer {bearer_token}'
        log.debug(f"Using Bearer token for {url}")
    elif auth:
        # Legacy Basic Auth support (if needed)
        log.debug(f"Using Basic Auth for {url}")
    else:
        log.warning(f"No authentication provided for {url}")

    try:
        return make_api_request(
            url=url,
            method=method,
            headers=headers,
            params=params,
            data=data,
            stream=stream,
            auth=auth
        )
    except Exception as e:
        log.error(f"Failed to make Atlassian API request to {url}: {e}", exc_info=True)
        raise

def get_accessible_atlassian_sites(bearer_token: str):
    """
    Gets the list of Jira/Confluence sites (cloudId and url) that the user has access to.
    Uses Bearer token authentication for OAuth.
    """
    try:
        log.info(f"Fetching accessible Atlassian resources: {ATLASSIAN_ACCESSIBLE_RESOURCES_URL}")
        
        headers = {
            'Authorization': f'Bearer {bearer_token}',
            'Accept': 'application/json'
        }
        
        response = requests.get(ATLASSIAN_ACCESSIBLE_RESOURCES_URL, headers=headers)
        log.info(f"Response status: {response.status_code}")
        log.info(f"Response content: {response.text}")
        
        response.raise_for_status()
        sites = response.json()
        log.info(f"Parsed sites: {sites}")
        
        return sites
    except Exception as e:
        log.error(f"Failed to get accessible Atlassian resources: {e}")
        return []

def list_jira_projects_and_issues(site_url, cloud_id, bearer_token: str, all_items=None, layer=None):
    """Lists Jira projects using OAuth 2.0 (3LO) URI format"""
    if all_items is None:
        all_items = []

    # Use OAuth 2.0 (3LO) URI format
    jira_base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
    
    log.info(f"Listing Jira projects for OAuth URI: {jira_base_url}")

    try:
        start_at = 0
        max_results = 1000 # Increased from 50 for better pagination support
        projects = []
        while True:
            params = {
                'startAt': start_at,
                'maxResults': max_results,
                'query': ''
            }
            # !!!Modify me to use a string query!!!
            response = make_atlassian_request(f"{jira_base_url}/project/search", params=params, bearer_token=bearer_token)
            log.info(f"Project search API response: {json.dumps(response, indent=2)}")
            
            projects.extend(response.get('values', []))
            if response.get('isLast', True):
                break
            start_at = response.get('nextPage', start_at + max_results)
        
        log.info(f"Found {len(projects)} Jira projects for site: {site_url}")

        # Determine folder name based on layer or default
        if layer and layer in LAYER_CONFIG:
            folder_name = LAYER_CONFIG[layer]['folder']
        else:
            folder_name = 'Jira'

        # Step 2: For each project, search for issues (using JQL) - UPDATED TO USE /search/jql
        for project in projects:
            project_key = project.get('key')
            project_name = project.get('name')
            if not project_key:
                continue

            log.info(f"Listing issues for Jira project: {project_name} ({project_key})")
            start_at_issue = 0
            max_results_issue = 1000
            
            while True:
                jql_query = f"project = \"{project_key}\""
                params = {
                    'jql': jql_query,
                    'startAt': start_at_issue,
                    'maxResults': max_results_issue,
                    'fields': 'summary,description,status,issuetype,priority,creator,reporter,assignee,created,updated,comment,attachment'
                }
                # FIXED: Changed from /search to /search/jql
                search_response = make_atlassian_request(f"{jira_base_url}/search/jql", params=params, bearer_token=bearer_token)
                issues = search_response.get('issues', [])

                for issue in issues:
                    issue_key = issue.get('key')
                    issue_summary = issue.get('fields', {}).get('summary', 'no_summary').replace('/', '_')
                    
                    full_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{site_url.replace('https://', '').replace('/', '_')}/{project_key}/{issue_key}-{issue_summary}.json"
                    
                    issue_info = {
                        'id': issue.get('id'),
                        'key': issue_key,
                        'fullPath': full_path,
                        'mimeType': 'application/json',
                        'content': json.dumps(issue, indent=2),
                        'modifiedTime': issue.get('fields', {}).get('updated'),
                        'createdTime': issue.get('fields', {}).get('created'),
                        'type': 'issue',
                        'layer': layer
                    }
                    all_items.append(issue_info)

                    # Handle attachments for the issue
                    attachments = issue.get('fields', {}).get('attachment', [])
                    for attachment in attachments:
                        attachment_filename = attachment.get('filename')
                        attachment_id = attachment.get('id')
                        attachment_content_url = attachment.get('content')
                        attachment_mime_type = attachment.get('mimeType')
                        attachment_size = attachment.get('size')
                        
                        attachment_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{site_url.replace('https://', '').replace('/', '_')}/{project_key}/{issue_key}/attachments/{attachment_filename}"
                        
                        attachment_info = {
                            'id': attachment_id,
                            'fullPath': attachment_path,
                            'mimeType': attachment_mime_type,
                            'downloadUrl': attachment_content_url,
                            'size': attachment_size,
                            'modifiedTime': attachment.get('created'),
                            'createdTime': attachment.get('created'),
                            'type': 'attachment',
                            'layer': layer
                        }
                        all_items.append(attachment_info)

                if search_response.get('total') <= start_at_issue + len(issues):
                    break
                start_at_issue += max_results_issue

    except Exception as error:
        log.error(f'Listing Jira projects/issues failed for site {site_url}: {str(error)}', exc_info=True)

    return all_items

def list_jira_projects_self_hosted(base_url: str, bearer_token: str = None, 
                                    auth=None):
    """Get list of available Jira projects from self-hosted instance using PAT"""
    
    base_url = base_url.rstrip('/')
    jira_base_url = f"{base_url}/rest/api/2"
    
    log.info(f"Fetching Jira projects for self-hosted: {jira_base_url}")

    try:
        all_projects = []
        
        # Try modern endpoint first (Jira 8.0+)
        try:
            start_at = 0
            max_results = 1000
            
            while True:
                params = {
                    'startAt': start_at,
                    'maxResults': max_results
                }
                
                response = make_atlassian_request(
                    f"{jira_base_url}/project/search", 
                    params=params, 
                    bearer_token=bearer_token,
                    auth=auth  
                )
                
                projects = response.get('values', [])
                
                for project in projects:
                    all_projects.append({
                        'id': project.get('id'),
                        'key': project.get('key'),
                        'name': project.get('name'),
                        'description': project.get('description', ''),
                        'avatarUrl': project.get('avatarUrls', {}).get('48x48', ''),
                        'instance_url': base_url
                    })
                
                if response.get('isLast', True):
                    break
                start_at = response.get('nextPage', start_at + max_results)
            
            return all_projects
            
        except Exception as e:
            # If 404, fall back to older endpoint
            if '404' in str(e):
                log.warning(f"Modern endpoint not found, falling back to legacy /project endpoint")
                
                # Fallback: Use older /project endpoint (Jira 7.x and earlier)
                response = make_atlassian_request(
                    f"{jira_base_url}/project", 
                    bearer_token=bearer_token,
                    auth=auth
                )
                
                # This returns a list directly, not paginated
                for project in response:
                    all_projects.append({
                        'id': project.get('id'),
                        'key': project.get('key'),
                        'name': project.get('name'),
                        'description': project.get('description', ''),
                        'avatarUrl': project.get('avatarUrls', {}).get('48x48', ''),
                        'instance_url': base_url
                    })
                
                return all_projects
            else:
                raise
        
    except Exception as e:
        log.error(f"Failed to fetch projects from self-hosted Jira: {str(e)}")
        raise

def list_jira_projects_and_issues_self_hosted(base_url: str, bearer_token: str = None, 
                                               auth=None, all_items=None, layer=None):
    """Lists Jira projects for self-hosted instance"""
    if all_items is None:
        all_items = []

    # Direct API path for self-hosted
    jira_base_url = f"{base_url}/rest/api/2"
    
    log.info(f"Listing Jira projects for self-hosted: {jira_base_url}")

    try:
        start_at = 0
        max_results = 1000
        projects = []
        
        auth_type = 'pat' if bearer_token else 'basic'
        
        while True:
            params = {
                'startAt': start_at,
                'maxResults': max_results
            }
            
            response = make_atlassian_request(
                f"{jira_base_url}/project/search", 
                params=params, 
                bearer_token=bearer_token,
                auth=auth,
            )
            
            projects.extend(response.get('values', []))
            if response.get('isLast', True):
                break
            start_at = response.get('nextPage', start_at + max_results)
        
        log.info(f"Found {len(projects)} Jira projects for self-hosted instance")

        # Determine folder name
        folder_name = LAYER_CONFIG.get(layer, {}).get('folder', 'Jira') if layer else 'Jira'
        
        # Process projects and issues (similar to cloud version but with self-hosted URLs)
        for project in projects:
            project_key = project.get('key')
            project_name = project.get('name')
            if not project_key:
                continue

            log.info(f"Listing issues for project: {project_name} ({project_key})")
            start_at_issue = 0
            max_results_issue = 1000
            
            while True:
                jql_query = f'project = "{project_key}"'
                params = {
                    'jql': jql_query,
                    'startAt': start_at_issue,
                    'maxResults': max_results_issue,
                    'fields': 'summary,description,status,issuetype,priority,creator,reporter,assignee,created,updated,comment,attachment'
                }
                
                search_response = make_atlassian_request(
                    f"{jira_base_url}/search", 
                    params=params, 
                    bearer_token=bearer_token,
                    auth=auth,
                )
                
                issues = search_response.get('issues', [])

                for issue in issues:
                    issue_key = issue.get('key')
                    issue_summary = issue.get('fields', {}).get('summary', 'no_summary').replace('/', '_')
                    
                    # Use instance hostname in path
                    instance_name = base_url.replace('https://', '').replace('http://', '').replace('/', '_')
                    full_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{instance_name}/{project_key}/{issue_key}-{issue_summary}.json"
                    
                    issue_info = {
                        'id': issue.get('id'),
                        'key': issue_key,
                        'fullPath': full_path,
                        'mimeType': 'application/json',
                        'content': json.dumps(issue, indent=2),
                        'modifiedTime': issue.get('fields', {}).get('updated'),
                        'createdTime': issue.get('fields', {}).get('created'),
                        'type': 'issue',
                        'layer': layer,
                        'deployment_type': 'self_hosted'
                    }
                    all_items.append(issue_info)

                    # Handle attachments
                    attachments = issue.get('fields', {}).get('attachment', [])
                    for attachment in attachments:
                        attachment_filename = attachment.get('filename')
                        attachment_id = attachment.get('id')
                        attachment_content_url = attachment.get('content')
                        attachment_mime_type = attachment.get('mimeType')
                        attachment_size = attachment.get('size')
                        
                        attachment_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{instance_name}/{project_key}/{issue_key}/attachments/{attachment_filename}"
                        
                        attachment_info = {
                            'id': attachment_id,
                            'fullPath': attachment_path,
                            'mimeType': attachment_mime_type,
                            'downloadUrl': attachment_content_url,
                            'size': attachment_size,
                            'modifiedTime': attachment.get('created'),
                            'createdTime': attachment.get('created'),
                            'type': 'attachment',
                            'layer': layer,
                            'deployment_type': 'self_hosted'
                        }
                        all_items.append(attachment_info)

                if search_response.get('total') <= start_at_issue + len(issues):
                    break
                start_at_issue += max_results_issue

    except Exception as error:
        log.error(f'Listing Jira projects/issues failed for self-hosted: {str(error)}', exc_info=True)

    return all_items

def list_jira_selected_projects_and_issues_self_hosted(base_url: str, bearer_token: str = None, 
                                                        auth=None, project_keys: List[str] = None, 
                                                        all_items=None, layer=None):
    """Lists Jira issues for selected projects only (self-hosted)"""
    if all_items is None:
        all_items = []

    jira_base_url = f"{base_url}/rest/api/2"
    
    log.info(f"Listing selected Jira projects for self-hosted: {jira_base_url}")
    log.info(f"Selected project keys: {project_keys}")

    try:
        # Determine folder name
        folder_name = LAYER_CONFIG.get(layer, {}).get('folder', 'Jira') if layer else 'Jira'
        instance_name = base_url.replace('https://', '').replace('http://', '').replace('/', '_')

        # For each selected project key, search for issues
        for project_key in project_keys:
            log.info(f"Listing issues for selected project: {project_key}")
            start_at_issue = 0
            max_results_issue = 1000
            
            while True:
                jql_query = f'project = "{project_key}"'
                params = {
                    'jql': jql_query,
                    'startAt': start_at_issue,
                    'maxResults': max_results_issue,
                    'fields': 'summary,description,status,issuetype,priority,creator,reporter,assignee,created,updated,comment,attachment'
                }
                
                try:
                    search_response = make_atlassian_request(
                        f"{jira_base_url}/search", 
                        params=params, 
                        bearer_token=bearer_token,
                        auth=auth
                    )
                except Exception as e:
                    log.error(f"Failed to fetch issues for project {project_key}: {e}")
                    break
                
                issues = search_response.get('issues', [])
                total_issues = search_response.get('total')

                for issue in issues:
                    issue_key = issue.get('key')
                    issue_summary = issue.get('fields', {}).get('summary', 'no_summary').replace('/', '_')
                    
                    full_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{instance_name}/{project_key}/{issue_key}/{issue_key}-{issue_summary}.json"
                    
                    issue_info = {
                        'id': issue.get('id'),
                        'key': issue_key,
                        'fullPath': full_path,
                        'mimeType': 'application/json',
                        'content': json.dumps(issue, indent=2),
                        'modifiedTime': issue.get('fields', {}).get('updated'),
                        'createdTime': issue.get('fields', {}).get('created'),
                        'type': 'issue',
                        'layer': layer,
                        'deployment_type': 'self_hosted'
                    }
                    all_items.append(issue_info)

                    # Handle attachments
                    attachments = issue.get('fields', {}).get('attachment', [])
                    for attachment in attachments:
                        attachment_filename = attachment.get('filename')
                        attachment_id = attachment.get('id')
                        attachment_content_url = attachment.get('content')
                        attachment_mime_type = attachment.get('mimeType')
                        attachment_size = attachment.get('size')
                        
                        attachment_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{instance_name}/{project_key}/{issue_key}/attachments/{attachment_filename}"
                        
                        attachment_info = {
                            'id': attachment_id,
                            'fullPath': attachment_path,
                            'mimeType': attachment_mime_type,
                            'downloadUrl': attachment_content_url,
                            'size': attachment_size,
                            'modifiedTime': attachment.get('created'),
                            'createdTime': attachment.get('created'),
                            'type': 'attachment',
                            'layer': layer,
                            'deployment_type': 'self_hosted'
                        }
                        all_items.append(attachment_info)

                if total_issues is not None and isinstance(total_issues, int):
                    if total_issues <= start_at_issue + len(issues):
                        break
                start_at_issue += max_results_issue

    except Exception as error:
        log.error(f'Listing selected projects/issues failed for self-hosted: {str(error)}', exc_info=True)

    return all_items

def list_jira_selected_projects_and_issues(site_url, cloud_id, bearer_token: str, project_keys: List[str], all_items=None, layer=None):
    """Lists Jira issues for selected projects only"""
    if all_items is None:
        all_items = []

    # Use OAuth 2.0 (3LO) URI format
    jira_base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
    
    log.info(f"Listing selected Jira projects for OAuth URI: {jira_base_url}")
    log.info(f"Selected project keys: {project_keys}")

    try:
        # Determine folder name based on layer or default
        if layer and layer in LAYER_CONFIG:
            folder_name = LAYER_CONFIG[layer]['folder']
        else:
            folder_name = 'Jira'

        # For each selected project key, search for issues
        for project_key in project_keys:
            log.info(f"Listing issues for selected Jira project: {project_key}")
            start_at_issue = 0
            max_results_issue = 1000
            
            jql_query = f"project = \"{project_key}\""
            params = {
                'jql': jql_query,
                'startAt': start_at_issue,
                'maxResults': max_results_issue,
                'fields': 'summary,description,status,issuetype,priority,creator,reporter,assignee,created,updated,comment,attachment'
            }
            
            try:
                search_response = make_atlassian_request(
                    f"{jira_base_url}/search/jql", 
                    params=params, 
                    bearer_token=bearer_token
                )
            except Exception as e:
                log.error(f"Failed to fetch issues for project {project_key}: {e}")
                break  # Skip this project and continue with others
            
            issues = search_response.get('issues', [])
            total_issues = search_response.get('total')

            for issue in issues:
                issue_key = issue.get('key')
                issue_summary = issue.get('fields', {}).get('summary', 'no_summary').replace('/', '_')
                
                full_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{site_url.replace('https://', '').replace('/', '_')}/{project_key}/{issue_key}/{issue_key}-{issue_summary}.json"
                
                issue_info = {
                    'id': issue.get('id'),
                    'key': issue_key,
                    'fullPath': full_path,
                    'mimeType': 'application/json',
                    'content': json.dumps(issue, indent=2),
                    'modifiedTime': issue.get('fields', {}).get('updated'),
                    'createdTime': issue.get('fields', {}).get('created'),
                    'type': 'issue',
                    'layer': layer
                }
                all_items.append(issue_info)

                # Handle attachments for the issue
                attachments = issue.get('fields', {}).get('attachment', [])
                for attachment in attachments:
                    attachment_filename = attachment.get('filename')
                    attachment_id = attachment.get('id')
                    attachment_content_url = attachment.get('content')
                    attachment_mime_type = attachment.get('mimeType')
                    attachment_size = attachment.get('size')
                    
                    attachment_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{site_url.replace('https://', '').replace('/', '_')}/{project_key}/{issue_key}/attachments/{attachment_filename}"
                    
                    attachment_info = {
                        'id': attachment_id,
                        'fullPath': attachment_path,
                        'mimeType': attachment_mime_type,
                        'downloadUrl': attachment_content_url,
                        'size': attachment_size,
                        'modifiedTime': attachment.get('created'),
                        'createdTime': attachment.get('created'),
                        'type': 'attachment',
                        'layer': layer
                    }
                    all_items.append(attachment_info)

            if total_issues is not None:
                if isinstance(total_issues, int):
                    if total_issues <= start_at_issue + len(issues):
                        break
            start_at_issue += max_results_issue

    except Exception as error:
        log.error(f'Listing selected Jira projects/issues failed for site {site_url}: {str(error)}', exc_info=True)

    return all_items

async def sync_atlassian_selected_projects(username: str, token: str, project_keys: List[str], layer=None):
    """Sync only selected Jira projects"""
    global total_api_calls
    
    log.info(f'Starting sync for {len(project_keys)} selected Jira projects...')
    log.info(f'Selected projects: {project_keys}')
    
    uploaded_items = []
    deleted_items = []
    skipped_items = 0
    
    # Initialize progress tracking
    sync_start_time = int(time.time())
    # Phase 1: Starting
    print("----------------------------------------------------------------------")
    print("🚀 Phase 1: Starting - preparing sync process...")
    print("----------------------------------------------------------------------")
    await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
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
    
    try:
        bearer_token = token
        
        # Get accessible Atlassian sites
        accessible_sites = get_accessible_atlassian_sites(bearer_token)
        log.info(f"Found {len(accessible_sites)} accessible sites")
        
        if not accessible_sites:
            raise ValueError("Could not retrieve user's accessible Atlassian sites.")
        
        all_atlassian_items = []

        # Process each accessible Atlassian site
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures_to_site = {}
            
            for site in accessible_sites:
                site_url = site.get('url')
                cloud_id = site.get('id')
                scopes = site.get('scopes', [])

                log.info(f"Processing site: {site_url}")
                
                if not site_url or not cloud_id:
                    log.warning(f"Skipping Atlassian resource with missing URL or Cloud ID: {site}")
                    continue

                # Only process Jira sites
                if any('jira' in scope for scope in scopes):
                    futures_to_site[executor.submit(
                        list_jira_selected_projects_and_issues, 
                        site_url, 
                        cloud_id, 
                        bearer_token, 
                        project_keys,
                        [], 
                        layer
                    )] = {"type": "Jira", "site_url": site_url}

            for future in concurrent.futures.as_completed(futures_to_site):
                site_info = futures_to_site[future]
                try:
                    site_items = future.result()
                    log.info(f"Completed listing selected projects for site {site_info['site_url']} with {len(site_items)} items")
                    all_atlassian_items.extend(site_items)
                except Exception as e:
                    log.error(f"Error listing selected projects for site {site_info['site_url']}: {str(e)}", exc_info=True)
        
        log.info(f"Found {len(all_atlassian_items)} items from selected projects.")

        # Discovery complete - set totals
        files_total = len(all_atlassian_items)
        mb_total = sum(int(item.get('size') or 0) for item in all_atlassian_items)
        await update_data_source_sync_status(
            USER_ID, 'atlassian', layer or 'jira', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        # Phase 2: Discovery
        print("----------------------------------------------------------------------")
        print("🔎 Phase 2: Discovery - analyzing existing items and determining sync plan...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing existing items and determining sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })

        # Delete orphaned files for selected projects only
        if layer and layer in LAYER_CONFIG:
            layer_folder = LAYER_CONFIG[layer]['folder']
            user_prefix = f"userResources/{USER_ID}/Atlassian/{layer_folder}/"
        else:
            user_prefix = f"userResources/{USER_ID}/Atlassian/"

        # List all files using unified storage interface
        storage_files = list_files_unified(prefix=user_prefix, user_id=USER_ID)
        storage_file_map = {file_info['name']: file_info for file_info in storage_files}
        atlassian_item_paths = {item['fullPath'] for item in all_atlassian_items}
        
        # Only delete files for the selected projects
        for file_name, file_info in storage_file_map.items():
            # Check if file belongs to one of the selected projects
            is_selected_project = any(
                f"/{project_key}/" in file_name 
                for project_key in project_keys
            )
            
            if file_name.startswith(user_prefix) and is_selected_project and file_name not in atlassian_item_paths:
                delete_file_unified(file_name, user_id=USER_ID)
                deleted_items.append({
                    'name': file_name,
                    'size': file_info.get('size'),
                    'timeCreated': file_info.get('timeCreated')
                })
                log.info(f"[{datetime.now().isoformat()}] Deleted orphan: {file_name}")
        
        # Process items in parallel for upload
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for item in all_atlassian_items:
                # Check for excluded files/extensions
                if item.get('type') == 'attachment':
                    if any(pattern.lower() in item['fullPath'].lower() for pattern in EXCLUDED_FILES if pattern):
                        log.info(f"Excluded (filename pattern): {item['fullPath']}")
                        skipped_items += 1
                        continue
                    
                    file_ext = item['fullPath'].split('.')[-1].lower() if '.' in item['fullPath'] else ''
                    if ALLOWED_EXTENSIONS and file_ext not in ALLOWED_EXTENSIONS:
                        log.info(f"Skipped (extension): {file_ext} in {item['fullPath']}")
                        skipped_items += 1
                        continue

                storage_file = storage_file_map.get(item['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not storage_file:
                    needs_upload = True
                    reason = 'New item'
                else:
                    storage_updated = parse_date(storage_file.get('updated'))
                    atlassian_modified = parse_date(item.get('modifiedTime'))
                    
                    if atlassian_modified and storage_updated and atlassian_modified > storage_updated:
                        needs_upload = True
                        reason = f"Atlassian version newer ({item['modifiedTime']} > {storage_file.get('updated')})"
                
                if needs_upload:
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_atlassian_item,
                                item,
                                bearer_token,
                                bool(storage_file),
                                reason
                            ),
                            item
                        )
                    )
                else:
                    skipped_items += 1
            
            # Process completed uploads
            files_processed = 0
            mb_processed = 0
            # Phase 3: Processing
            print("----------------------------------------------------------------------")
            print("⚙️  Phase 3: Processing - synchronizing items to storage...")
            print("----------------------------------------------------------------------")
            for future, item_for_log in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_items.append(result)
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing items to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': mb_total,
                            'sync_start_time': sync_start_time
                        })
                except Exception as e:
                    log.error(f"Error processing future for {item_for_log.get('fullPath')}: {str(e)}", exc_info=True)
        
        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        # Enhanced summary
        log.info('\nSync Summary for Selected Projects:')
        for item in uploaded_items:
            symbol = '+' if item['type'] == 'new' else '^'
            log.info(
                f" {symbol} {item['path']} | {format_bytes(item['size'])} | {item['durationMs']}ms | {item['reason']}"
            )
        
        for item in deleted_items:
            log.info(f" - {item['name']} | {format_bytes(item['size'])} | Created: {item['timeCreated']}")
        
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        log.info("\nAccounting Metrics:")
        log.info(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        log.info(f"📊 Billable API Calls: {total_api_calls}")
        log.info(f"📦 Items Processed: {len(all_atlassian_items)}")
        log.info(f"🗑️  Orphans Removed: {len(deleted_items)}")
        log.info(f"📂 Selected Projects: {', '.join(project_keys)}")
        
        log.info(f"\nTotal: +{len([f for f in uploaded_items if f['type'] == 'new'])} added, " +
              f"^{len([f for f in uploaded_items if f['type'] == 'updated'])} updated, " +
              f"-{len(deleted_items)} removed, {skipped_items} skipped")
        
        sync_results = {
            "latest_sync": {
                "added": len([f for f in uploaded_items if f['type'] == 'new']),
                "updated": len([f for f in uploaded_items if f['type'] == 'updated']),
                "removed": len(deleted_items),
                "skipped": skipped_items,
                "runtime_ms": total_runtime_ms,
                "api_calls": total_api_calls,
                "skip_reasons": {},
                "sync_timestamp": int(time.time())
            },
            "overall_profile": {
                "total_files": len(all_atlassian_items),
                "total_size_bytes": sum(int(item.get('size') or 0) for item in all_atlassian_items),
                "last_updated": int(time.time()),
                "folders_count": 0
            }
        }
        
        # Phase 5: Embedding
        print("----------------------------------------------------------------------")
        print("🧠 Phase 5: Embedding - vectorizing data for AI processing...")
        print("----------------------------------------------------------------------")
        await update_data_source_sync_status(USER_ID, 'atlassian', layer or 'jira', 'embedding', sync_results=sync_results)
    
    except Exception as error:
        await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'error')
        log.error(f"[{datetime.now().isoformat()}] Atlassian Selected Projects Sync failed: {str(error)}", exc_info=True)
        raise error

async def initiate_atlassian_sync_selected(user_id: str, token: str, project_keys: List[str], layer: str = 'jira'):
    """
    Sync only selected Jira projects
    
    Args:
        user_id (str): User ID from your app
        token (str): Atlassian OAuth access token (JWT)
        project_keys (List[str]): List of Jira project keys to sync
        layer (str): Atlassian layer (defaults to 'jira')
    """
    log.info(f'Initiating Atlassian sync for selected projects')
    log.info(f'User Open WebUI ID: {user_id}')
    log.info(f'Selected Projects: {project_keys}')
    log.info(f'Layer: {layer}')

    global USER_ID
    global USER
    global USER_AUTH
    global script_start_time
    global total_api_calls

    USER_ID = user_id
    USER = Users.get_user_by_id(user_id)
    
    if not USER:
        raise ValueError(f"User with ID {user_id} not found")
    
    username = USER.email
    USER_AUTH = HTTPBasicAuth(username, token) 
    log.info(f'Using email as username: {username}')
    
    total_api_calls = 0
    script_start_time = time.time()

    await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'syncing')

    try:
        await sync_atlassian_selected_projects(username, token, project_keys, layer)
        return {
            "status": "started", 
            "message": f"Atlassian sync process completed for {len(project_keys)} selected projects",
            "user_id": user_id,
            "layer": layer,
            "project_count": len(project_keys)
        }
    except Exception as e:
        log.error(f"Atlassian selected projects sync failed: {e}", exc_info=True)
        await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'error')
        raise

def list_confluence_spaces_and_pages(site_url, cloud_id, bearer_token: str, all_items=None, layer=None):
    """
    Lists Confluence spaces and then all pages within those spaces.
    """
    if all_items is None:
        all_items = []

    confluence_base_url = f"{site_url}{CONFLUENCE_CLOUD_API_PATH}"

    try:
        # Step 1: List all accessible spaces
        log.info(f"Listing Confluence spaces for site: {site_url}")
        start_at = 0
        max_results = 1000
        spaces = []
        while True:
            params = {
                'start': start_at,
                'limit': max_results
            }
            response = make_atlassian_request(f"{confluence_base_url}/space", params=params, bearer_token=bearer_token)
            spaces.extend(response.get('results', []))
            if response.get('size', 0) < max_results:
                break
            start_at += max_results
        
        log.info(f"Found {len(spaces)} Confluence spaces for site: {site_url}")

        # Determine folder name based on layer or default
        if layer and layer in LAYER_CONFIG:
            folder_name = LAYER_CONFIG[layer]['folder']
        else:
            folder_name = 'Confluence'

        # Step 2: For each space, list its content (pages)
        for space in spaces:
            space_key = space.get('key')
            space_name = space.get('name')
            if not space_key:
                continue

            log.info(f"Listing pages for Confluence space: {space_name} ({space_key})")
            start_at_page = 0
            max_results_page = 1000
            
            while True:
                params = {
                    'spaceKey': space_key,
                    'start': start_at_page,
                    'limit': max_results_page,
                    'expand': 'body.storage,version,attachments'
                }
                content_response = make_atlassian_request(f"{confluence_base_url}/content", params=params, bearer_token=bearer_token)
                pages = content_response.get('results', [])

                for page in pages:
                    if page.get('type') != 'page':
                        continue

                    page_id = page.get('id')
                    page_title = page.get('title', 'no_title').replace('/', '_')

                    full_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{site_url.replace('https://', '').replace('/', '_')}/{space_key}/{page_title}-{page_id}.html"
                    
                    page_info = {
                        'id': page_id,
                        'fullPath': full_path,
                        'mimeType': 'text/html',
                        'content': page.get('body', {}).get('storage', {}).get('value'),
                        'modifiedTime': page.get('version', {}).get('when'),
                        'createdTime': page.get('history', {}).get('createdDate'),
                        'type': 'page',
                        'layer': layer
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
                            attachment_download_url = f"{site_url}{attachment_download_url}"

                        attachment_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{site_url.replace('https://', '').replace('/', '_')}/{space_key}/{page_title}-{page_id}/attachments/{attachment_filename}"

                        attachment_info = {
                            'id': attachment_id,
                            'fullPath': attachment_path,
                            'mimeType': attachment_mime_type,
                            'downloadUrl': attachment_download_url,
                            'size': attachment_size,
                            'modifiedTime': attachment.get('version', {}).get('when'),
                            'createdTime': attachment.get('version', {}).get('when'),
                            'type': 'attachment',
                            'layer': layer
                        }
                        all_items.append(attachment_info)

                if content_response.get('size', 0) < max_results_page:
                    break
                start_at_page += max_results_page

    except Exception as error:
        log.error(f'Listing Confluence spaces/pages failed for site {site_url}: {str(error)}', exc_info=True)

    return all_items

def list_confluence_spaces_and_pages_self_hosted(base_url: str, bearer_token: str = None, 
                                                  auth=None, all_items=None, layer=None):
    """Lists Confluence spaces and pages for self-hosted instance"""
    if all_items is None:
        all_items = []

    # Direct API path for self-hosted
    confluence_base_url = f"{base_url}/rest/api"
    
    log.info(f"Listing Confluence spaces for self-hosted: {confluence_base_url}")

    try:
        # Step 1: List all accessible spaces
        start_at = 0
        max_results = 1000
        spaces = []
        
        while True:
            params = {
                'start': start_at,
                'limit': max_results
            }
            
            response = make_atlassian_request(
                f"{confluence_base_url}/space", 
                params=params, 
                bearer_token=bearer_token,
                auth=auth
            )
            
            spaces.extend(response.get('results', []))
            if response.get('size', 0) < max_results:
                break
            start_at += max_results
        
        log.info(f"Found {len(spaces)} Confluence spaces for self-hosted instance")

        # Determine folder name
        folder_name = LAYER_CONFIG.get(layer, {}).get('folder', 'Confluence') if layer else 'Confluence'
        
        # Process spaces and pages
        for space in spaces:
            space_key = space.get('key')
            space_name = space.get('name')
            if not space_key:
                continue

            log.info(f"Listing pages for Confluence space: {space_name} ({space_key})")
            start_at_page = 0
            max_results_page = 1000
            
            while True:
                params = {
                    'spaceKey': space_key,
                    'start': start_at_page,
                    'limit': max_results_page,
                    'expand': 'body.storage,version,history'
                }
                
                content_response = make_atlassian_request(
                    f"{confluence_base_url}/content", 
                    params=params, 
                    bearer_token=bearer_token,
                    auth=auth
                )
                
                pages = content_response.get('results', [])

                for page in pages:
                    if page.get('type') != 'page':
                        continue

                    page_id = page.get('id')
                    page_title = page.get('title', 'no_title').replace('/', '_')

                    instance_name = base_url.replace('https://', '').replace('http://', '').replace('/', '_')
                    full_path = f"userResources/{USER_ID}/Atlassian/{folder_name}/{instance_name}/{space_key}/{page_title}-{page_id}.html"
                    
                    page_info = {
                        'id': page_id,
                        'fullPath': full_path,
                        'mimeType': 'text/html',
                        'content': page.get('body', {}).get('storage', {}).get('value'),
                        'modifiedTime': page.get('version', {}).get('when'),
                        'createdTime': page.get('history', {}).get('createdDate'),
                        'type': 'page',
                        'layer': layer,
                        'deployment_type': 'self_hosted'
                    }
                    all_items.append(page_info)

                    # Handle attachments (if needed)
                    # Confluence self-hosted attachments require separate API calls
                    # You can add this if needed

                if content_response.get('size', 0) < max_results_page:
                    break
                start_at_page += max_results_page

    except Exception as error:
        log.error(f'Listing Confluence spaces/pages failed for self-hosted: {str(error)}', exc_info=True)

    return all_items

# def download_atlassian_content(item_info, bearer_token: str):
#     """
#     Downloads content for a given Atlassian item (Jira issue JSON, Confluence page HTML, attachment binary).
#     """
#     file_content = io.BytesIO()
    
#     item_type = item_info.get('type')
#     mime_type = item_info.get('mimeType')

#     if item_type == 'issue':
#         # Jira issue content is already in 'content' field as JSON string
#         content_bytes = item_info['content'].encode('utf-8')
#         file_content.write(content_bytes)
#         file_content.seek(0)
#         return file_content

#     elif item_type == 'page':
#         # Confluence page content is in 'content' field as HTML/storage format
#         if item_info.get('content'):
#             content_bytes = item_info['content'].encode('utf-8')
#             file_content.write(content_bytes)
#         file_content.seek(0)
#         return file_content

#     elif item_type == 'attachment' and item_info.get('downloadUrl'):
#         download_url = item_info['downloadUrl']
#         log.info(f"Downloading attachment from: {download_url}")
#         response = make_atlassian_request(
#             download_url,
#             bearer_token=bearer_token,
#             stream=True
#         )
        
#         # Check if request was successful
#         if response.status_code != 200:
#             raise Exception(f"Failed to download attachment {item_info.get('fullPath')}: {response.text}")
        
#         # Read content into memory
#         for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
#             if chunk:
#                 file_content.write(chunk)
        
#         file_content.seek(0)
#         return file_content
    
#     else:
#         raise ValueError(f"Unsupported Atlassian item type or missing download URL: {item_type}")

# def download_and_upload_atlassian_item(item, bearer_token: str, exists, reason):
#     """Helper function to download an Atlassian item and upload using unified storage"""
#     start_time = time.time()
    
#     try:
#         # Download item content
#         file_content_buffer = download_atlassian_content(item, bearer_token)
        
#         # Get content as bytes for unified upload
#         content_bytes = file_content_buffer.getvalue()
#         content_size = len(content_bytes)
        
#         # Override item size for non-attachments
#         if item.get('type') in ['issue', 'page'] and content_size > 0:
#             item['size'] = content_size
        
#         if not content_bytes:
#             raise Exception("Failed to get content bytes for item.")

#         # Upload using unified storage interface
#         result = upload_file_unified(
#             file_content=content_bytes,
#             destination_path=item['fullPath'],
#             content_type=item.get('mimeType'),
#             user_id=USER_ID
#         )
        
#         if not result:
#             raise Exception("Upload failed")

#         upload_result = {
#             'path': item['fullPath'],
#             'type': 'updated' if exists else 'new',
#             'size': content_size,
#             'atlassianModified': item.get('modifiedTime'),
#             'durationMs': int((time.time() - start_time) * 1000),
#             'reason': reason
#         }
        
#         log.info(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {item['fullPath']}")
#         return upload_result
        
#     except Exception as e:
#         log.error(f"Error processing Atlassian item {item.get('fullPath')}: {str(e)}", exc_info=True)
#         return None

def download_and_upload_atlassian_item(item, bearer_token: str, exists, reason, auth=None):
    """Helper function to download an Atlassian item and upload using unified storage"""
    start_time = time.time()
    
    try:
        # Download item content (with auth support)
        file_content_buffer = download_atlassian_content(item, bearer_token, auth)
        
        # Get content as bytes for unified upload
        content_bytes = file_content_buffer.getvalue()
        content_size = len(content_bytes)
        
        # Override item size for non-attachments
        if item.get('type') in ['issue', 'page'] and content_size > 0:
            item['size'] = content_size
        
        if not content_bytes:
            raise Exception("Failed to get content bytes for item.")

        # Upload using unified storage interface
        result = upload_file_unified(
            file_content=content_bytes,
            destination_path=item['fullPath'],
            content_type=item.get('mimeType'),
            user_id=USER_ID
        )
        
        if not result:
            raise Exception("Upload failed")

        upload_result = {
            'path': item['fullPath'],
            'type': 'updated' if exists else 'new',
            'size': content_size,
            'atlassianModified': item.get('modifiedTime'),
            'durationMs': int((time.time() - start_time) * 1000),
            'reason': reason
        }
        
        log.info(f"[{datetime.now().isoformat()}] {'Updated' if exists else 'Uploaded'} {item['fullPath']}")
        return upload_result
        
    except Exception as e:
        log.error(f"Error processing Atlassian item {item.get('fullPath')}: {str(e)}", exc_info=True)
        return None


def download_atlassian_content(item_info, bearer_token: str = None, auth=None):
    """
    Downloads content for Atlassian item - supports both Bearer token and Basic Auth
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
        
        # Use appropriate authentication
        response = make_atlassian_request(
            download_url,
            bearer_token=bearer_token,
            auth=auth,
            stream=True
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

# async def sync_atlassian_to_storage(username: str, token: str, layer=None):
#     """Main function to sync Atlassian (Jira & Confluence) using Bearer token authentication"""
#     global total_api_calls
    
#     layer_display = f" ({layer})" if layer else ""
#     log.info(f'Starting recursive sync process for Atlassian{layer_display}...')
    
#     uploaded_items = []
#     deleted_items = []
#     skipped_items = 0
    
#     try:
#         log.info("=== JWT TOKEN DEBUG ===")
#         decoded_token = debug_jwt_token(token)
#         log.info(f"============{decoded_token}==========")
#         # Use Bearer token directly (token is the JWT from OAuth)
#         bearer_token = token
        
#         # Get accessible Atlassian sites
#         accessible_sites = get_accessible_atlassian_sites(bearer_token)
#         log.info(f"=== ACCESSIBLE SITES DEBUG ===")
#         log.info(f"Found {len(accessible_sites)} accessible sites:")
#         for i, site in enumerate(accessible_sites):
#             log.info(f"Site {i+1}: {json.dumps(site, indent=2)}")
#         log.info("==============================")
#         if not accessible_sites:
#             raise ValueError("Could not retrieve user's accessible Atlassian sites.")
        
#         all_atlassian_items = []

#         # Determine what to process based on layer
#         should_process_jira = True
#         should_process_confluence = True
        
#         if layer and layer in LAYER_CONFIG:
#             layer_config = LAYER_CONFIG[layer]
#             should_process_jira = layer_config['process_jira']
#             should_process_confluence = layer_config['process_confluence']
#             log.info(f"Layer-specific sync: Jira={should_process_jira}, Confluence={should_process_confluence}")

#         # Process each accessible Atlassian site
#         with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
#             futures_to_site = {}
#             for site in accessible_sites:
#                 site_url = site.get('url')
#                 cloud_id = site.get('id')
#                 scopes = site.get('scopes', [])

#                 log.info(f"Processing site: {site}")
                
#                 if not site_url or not cloud_id:
#                     log.warning(f"Skipping Atlassian resource with missing URL or Cloud ID: {site}")
#                     continue

#                 # Check if this site has Jira access and we should process it
#                 if should_process_jira and any('jira' in scope for scope in scopes):
#                     futures_to_site[executor.submit(list_jira_projects_and_issues, site_url, cloud_id, bearer_token, [], layer)] = \
#                         {"type": "Jira", "site_url": site_url}
                
#                 # Check if this site has Confluence access and we should process it  
#                 if should_process_confluence and any('confluence' in scope for scope in scopes):
#                     futures_to_site[executor.submit(list_confluence_spaces_and_pages, site_url, cloud_id, bearer_token, [], layer)] = \
#                         {"type": "Confluence", "site_url": site_url}

#             for future in concurrent.futures.as_completed(futures_to_site):
#                 site_info = futures_to_site[future]
#                 try:
#                     site_items = future.result()
#                     log.info(f"Completed listing {site_info['type']} for site {site_info['site_url']} with {len(site_items)} items")
#                     all_atlassian_items.extend(site_items)
#                 except Exception as e:
#                     log.error(f"Error listing {site_info['type']} for site {site_info['site_url']}: {str(e)}", exc_info=True)
        
#         log.info(f"Found {len(all_atlassian_items)} items across all accessible Atlassian sites.")

#         # Delete orphaned files - layer-specific cleanup
#         if layer and layer in LAYER_CONFIG:
#             layer_folder = LAYER_CONFIG[layer]['folder']
#             user_prefix = f"userResources/{USER_ID}/Atlassian/{layer_folder}/"
#         else:
#             user_prefix = f"userResources/{USER_ID}/Atlassian/"

#         # List all files using unified storage interface
#         storage_files = list_files_unified(prefix=user_prefix, user_id=USER_ID)
#         storage_file_map = {file_info['name']: file_info for file_info in storage_files}
#         atlassian_item_paths = {item['fullPath'] for item in all_atlassian_items}
        
#         for file_name, file_info in storage_file_map.items():
#             if file_name.startswith(user_prefix) and file_name not in atlassian_item_paths:
#                 delete_file_unified(file_name, user_id=USER_ID)
#                 deleted_items.append({
#                     'name': file_name,
#                     'size': file_info.get('size'),
#                     'timeCreated': file_info.get('timeCreated')
#                 })
#                 log.info(f"[{datetime.now().isoformat()}] Deleted orphan: {file_name}")
        
#         # Process items in parallel for upload
#         with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
#             futures = []
            
#             for item in all_atlassian_items:
#                 # Check for excluded files/extensions
#                 if item.get('type') == 'attachment':
#                     if any(pattern.lower() in item['fullPath'].lower() for pattern in EXCLUDED_FILES if pattern):
#                         log.info(f"Excluded (filename pattern): {item['fullPath']}")
#                         skipped_items += 1
#                         continue
                    
#                     file_ext = item['fullPath'].split('.')[-1].lower() if '.' in item['fullPath'] else ''
#                     if ALLOWED_EXTENSIONS and file_ext not in ALLOWED_EXTENSIONS:
#                         log.info(f"Skipped (extension): {file_ext} in {item['fullPath']}")
#                         skipped_items += 1
#                         continue

#                 storage_file = storage_file_map.get(item['fullPath'])
                
#                 needs_upload = False
#                 reason = ''
                
#                 if not storage_file:
#                     needs_upload = True
#                     reason = 'New item'
#                 else:
#                     storage_updated = parse_date(storage_file.get('updated'))
#                     atlassian_modified = parse_date(item.get('modifiedTime'))
                    
#                     if atlassian_modified and storage_updated and atlassian_modified > storage_updated:
#                         needs_upload = True
#                         reason = f"Atlassian version newer ({item['modifiedTime']} > {storage_file.get('updated')})"
                
#                 if needs_upload:
#                     futures.append(
#                         (
#                             executor.submit(
#                                 download_and_upload_atlassian_item,
#                                 item,
#                                 bearer_token,
#                                 bool(storage_file),
#                                 reason
#                             ),
#                             item
#                         )
#                     )
#                 else:
#                     skipped_items += 1
            
#             # Process completed uploads
#             for future, item_for_log in futures:
#                 try:
#                     result = future.result()
#                     if result:
#                         uploaded_items.append(result)
#                 except Exception as e:
#                     log.error(f"Error processing future for {item_for_log.get('fullPath')}: {str(e)}", exc_info=True)
        
#         # Enhanced summary
#         log.info('\nSync Summary:')
#         for item in uploaded_items:
#             symbol = '+' if item['type'] == 'new' else '^'
#             log.info(
#                 f" {symbol} {item['path']} | {format_bytes(item['size'])} | {item['durationMs']}ms | {item['reason']}"
#             )
        
#         for item in deleted_items:
#             log.info(f" - {item['name']} | {format_bytes(item['size'])} | Created: {item['timeCreated']}")
        
#         total_runtime = int((time.time() - script_start_time) * 1000)
#         log.info("\nAccounting Metrics:")
#         log.info(f"⏱️  Total Runtime: {(total_runtime/1000):.2f} seconds")
#         log.info(f"📊 Billable API Calls: {total_api_calls}")
#         log.info(f"📦 Items Processed: {len(all_atlassian_items)}")
#         log.info(f"🗑️  Orphans Removed: {len(deleted_items)}")
#         log.info(f"📂 Layer: {layer if layer else 'All layers'}")
        
#         log.info(f"\nTotal: +{len([f for f in uploaded_items if f['type'] == 'new'])} added, " +
#               f"^{len([f for f in uploaded_items if f['type'] == 'updated'])} updated, " +
#               f"-{len(deleted_items)} removed, {skipped_items} skipped")
        
#         await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'synced')
    
#     except Exception as error:
#         await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'error')
#         log.error(f"[{datetime.now().isoformat()}] Atlassian Sync failed critically: {str(error)}", exc_info=True)
#         raise error

async def sync_atlassian_to_storage(username: str, token: str, layer=None, 
                                   deployment_type: str = 'cloud',
                                   base_url: str = None):
    """Main function to sync Atlassian (Jira & Confluence) supporting both cloud and self-hosted"""
    global total_api_calls
    
    layer_display = f" ({layer})" if layer else ""
    log.info(f'Starting recursive sync process for Atlassian{layer_display} - Deployment: {deployment_type}')
    
    uploaded_items = []
    deleted_items = []
    skipped_items = 0
    
    # Initialize progress tracking
    sync_start_time = int(time.time())
    # Phase 1: Starting
    print("----------------------------------------------------------------------")
    print("🚀 Phase 1: Starting - preparing sync process...")
    print("----------------------------------------------------------------------")
    await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
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
    
    try:
        all_atlassian_items = []
        
        # Determine what to process based on layer
        should_process_jira = True
        should_process_confluence = True
        
        if layer and layer in LAYER_CONFIG:
            layer_config = LAYER_CONFIG[layer]
            should_process_jira = layer_config['process_jira']
            should_process_confluence = layer_config['process_confluence']
            log.info(f"Layer-specific sync: Jira={should_process_jira}, Confluence={should_process_confluence}")
        
        if deployment_type == 'cloud':
            # ============ CLOUD OAUTH FLOW ============
            log.info("=== JWT TOKEN DEBUG ===")
            decoded_token = debug_jwt_token(token)
            log.info(f"============{decoded_token}==========")
            
            bearer_token = token
            
            # Get accessible Atlassian sites
            accessible_sites = get_accessible_atlassian_sites(bearer_token)
            log.info(f"=== ACCESSIBLE SITES DEBUG ===")
            log.info(f"Found {len(accessible_sites)} accessible sites:")
            for i, site in enumerate(accessible_sites):
                log.info(f"Site {i+1}: {json.dumps(site, indent=2)}")
            log.info("==============================")
            
            if not accessible_sites:
                raise ValueError("Could not retrieve user's accessible Atlassian sites.")
            
            # Process each accessible Atlassian site with threading
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures_to_site = {}
                for site in accessible_sites:
                    site_url = site.get('url')
                    cloud_id = site.get('id')
                    scopes = site.get('scopes', [])

                    log.info(f"Processing site: {site}")
                    
                    if not site_url or not cloud_id:
                        log.warning(f"Skipping Atlassian resource with missing URL or Cloud ID: {site}")
                        continue

                    # Check if this site has Jira access and we should process it
                    if should_process_jira and any('jira' in scope for scope in scopes):
                        futures_to_site[executor.submit(
                            list_jira_projects_and_issues, 
                            site_url, 
                            cloud_id, 
                            bearer_token, 
                            [], 
                            layer
                        )] = {"type": "Jira", "site_url": site_url}
                    
                    # Check if this site has Confluence access and we should process it  
                    if should_process_confluence and any('confluence' in scope for scope in scopes):
                        futures_to_site[executor.submit(
                            list_confluence_spaces_and_pages, 
                            site_url, 
                            cloud_id, 
                            bearer_token, 
                            [], 
                            layer
                        )] = {"type": "Confluence", "site_url": site_url}

                for future in concurrent.futures.as_completed(futures_to_site):
                    site_info = futures_to_site[future]
                    try:
                        site_items = future.result()
                        log.info(f"Completed listing {site_info['type']} for site {site_info['site_url']} with {len(site_items)} items")
                        all_atlassian_items.extend(site_items)
                    except Exception as e:
                        log.error(f"Error listing {site_info['type']} for site {site_info['site_url']}: {str(e)}", exc_info=True)
        
        elif deployment_type == 'self_hosted':
            # ============ SELF-HOSTED PAT FLOW ============
            log.info("Using self-hosted Atlassian deployment with PAT")
            
            if not base_url:
                raise ValueError("Base URL required for self-hosted Atlassian")
            
            # Token is always a PAT for self-hosted
            bearer_token = token
            log.info("Using PAT for self-hosted authentication")
            
            # Process Jira if needed
            if should_process_jira:
                jira_url = base_url if layer == 'jira' else ATLASSIAN_SELF_HOSTED_JIRA_URL
                if jira_url:
                    log.info(f"Processing self-hosted Jira: {jira_url}")
                    try:
                        items = list_jira_projects_and_issues_self_hosted(
                            jira_url,
                            bearer_token=bearer_token,
                            auth=None,
                            all_items=[],
                            layer=layer
                        )
                        all_atlassian_items.extend(items)
                        log.info(f"Retrieved {len(items)} items from self-hosted Jira")
                    except Exception as e:
                        log.error(f"Error processing self-hosted Jira: {str(e)}", exc_info=True)
                else:
                    log.warning("Self-hosted Jira URL not configured, skipping Jira sync")
            
            # Process Confluence if needed
            if should_process_confluence:
                confluence_url = base_url if layer == 'confluence' else ATLASSIAN_SELF_HOSTED_CONFLUENCE_URL
                if confluence_url:
                    log.info(f"Processing self-hosted Confluence: {confluence_url}")
                    try:
                        items = list_confluence_spaces_and_pages_self_hosted(
                            confluence_url,
                            bearer_token=bearer_token,
                            auth=None,
                            all_items=[],
                            layer=layer
                        )
                        all_atlassian_items.extend(items)
                        log.info(f"Retrieved {len(items)} items from self-hosted Confluence")
                    except Exception as e:
                        log.error(f"Error processing self-hosted Confluence: {str(e)}", exc_info=True)
                else:
                    log.warning("Self-hosted Confluence URL not configured, skipping Confluence sync")
        
        else:
            raise ValueError(f"Invalid deployment_type: {deployment_type}. Must be 'cloud' or 'self_hosted'")
        
        log.info(f"Found {len(all_atlassian_items)} items across all accessible Atlassian resources.")

        # Discovery complete - set totals
        files_total = len(all_atlassian_items)
        mb_total = sum(int(item.get('size') or 0) for item in all_atlassian_items)
        await update_data_source_sync_status(
            USER_ID, 'atlassian', layer or 'jira', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        # Phase 2: Discovery
        print("----------------------------------------------------------------------")
        print("🔎 Phase 2: Discovery - analyzing existing items and determining sync plan...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing existing items and determining sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })

        # ============ DELETE ORPHANED FILES - LAYER-SPECIFIC CLEANUP ============
        if layer and layer in LAYER_CONFIG:
            layer_folder = LAYER_CONFIG[layer]['folder']
            user_prefix = f"userResources/{USER_ID}/Atlassian/{layer_folder}/"
        else:
            user_prefix = f"userResources/{USER_ID}/Atlassian/"

        # List all files using unified storage interface
        storage_files = list_files_unified(prefix=user_prefix, user_id=USER_ID)
        storage_file_map = {file_info['name']: file_info for file_info in storage_files}
        atlassian_item_paths = {item['fullPath'] for item in all_atlassian_items}
        
        # Delete orphaned files (files in storage but not in Atlassian anymore)
        for file_name, file_info in storage_file_map.items():
            if file_name.startswith(user_prefix) and file_name not in atlassian_item_paths:
                try:
                    delete_file_unified(file_name, user_id=USER_ID)
                    deleted_items.append({
                        'name': file_name,
                        'size': file_info.get('size'),
                        'timeCreated': file_info.get('timeCreated')
                    })
                    log.info(f"[{datetime.now().isoformat()}] Deleted orphan: {file_name}")
                except Exception as e:
                    log.error(f"Error deleting orphan file {file_name}: {str(e)}")
        
        # ============ PROCESS ITEMS IN PARALLEL FOR UPLOAD ============
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for item in all_atlassian_items:
                # Check for excluded files/extensions (only for attachments)
                if item.get('type') == 'attachment':
                    # Check excluded filename patterns
                    if any(pattern.lower() in item['fullPath'].lower() for pattern in EXCLUDED_FILES if pattern):
                        log.info(f"Excluded (filename pattern): {item['fullPath']}")
                        skipped_items += 1
                        continue
                    
                    # Check allowed extensions
                    file_ext = item['fullPath'].split('.')[-1].lower() if '.' in item['fullPath'] else ''
                    if ALLOWED_EXTENSIONS and file_ext not in ALLOWED_EXTENSIONS:
                        log.info(f"Skipped (extension): {file_ext} in {item['fullPath']}")
                        skipped_items += 1
                        continue

                # Check if file needs upload
                storage_file = storage_file_map.get(item['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not storage_file:
                    needs_upload = True
                    reason = 'New item'
                else:
                    # Compare modification times
                    storage_updated = parse_date(storage_file.get('updated'))
                    atlassian_modified = parse_date(item.get('modifiedTime'))
                    
                    if atlassian_modified and storage_updated and atlassian_modified > storage_updated:
                        needs_upload = True
                        reason = f"Atlassian version newer ({item['modifiedTime']} > {storage_file.get('updated')})"
                
                if needs_upload:
                    # Use PAT as bearer token for both cloud and self-hosted
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_atlassian_item,
                                item,
                                token,  # Use token directly as bearer
                                bool(storage_file),
                                reason,
                                None  # No Basic Auth needed
                            ),
                            item
                        )
                    )
                else:
                    skipped_items += 1
            
            # Process completed uploads
            files_processed = 0
            mb_processed = 0
            # Phase 3: Processing
            print("----------------------------------------------------------------------")
            print("⚙️  Phase 3: Processing - synchronizing items to storage...")
            print("----------------------------------------------------------------------")
            for future, item_for_log in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_items.append(result)
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing items to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': mb_total,
                            'sync_start_time': sync_start_time
                        })
                except Exception as e:
                    log.error(f"Error processing future for {item_for_log.get('fullPath')}: {str(e)}", exc_info=True)
        
        # Emit summarizing phase before printing summary
        # Phase 4: Summarizing
        print("----------------------------------------------------------------------")
        print("📊 Phase 4: Summarizing - finalizing Atlassian sync results...")
        print("----------------------------------------------------------------------")
        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })

        # ============ ENHANCED SUMMARY ============
        log.info('\nSync Summary:')
        for item in uploaded_items:
            symbol = '+' if item['type'] == 'new' else '^'
            log.info(
                f" {symbol} {item['path']} | {format_bytes(item['size'])} | {item['durationMs']}ms | {item['reason']}"
            )
        
        for item in deleted_items:
            log.info(f" - {item['name']} | {format_bytes(item['size'])} | Created: {item['timeCreated']}")
        
        total_runtime_ms = int((time.time() - script_start_time) * 1000)
        total_seconds = total_runtime_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        log.info("\nAccounting Metrics:")
        log.info(f"⏱️  Total Runtime: {(total_seconds/60):.1f} minutes ({hours:02d}:{minutes:02d}:{seconds:02d})")
        log.info(f"📊 Billable API Calls: {total_api_calls}")
        log.info(f"📦 Items Processed: {len(all_atlassian_items)}")
        log.info(f"🗑️  Orphans Removed: {len(deleted_items)}")
        log.info(f"📂 Layer: {layer if layer else 'All layers'}")
        log.info(f"🏢 Deployment: {deployment_type}")
        
        log.info(f"\nTotal: +{len([f for f in uploaded_items if f['type'] == 'new'])} added, " +
              f"^{len([f for f in uploaded_items if f['type'] == 'updated'])} updated, " +
              f"-{len(deleted_items)} removed, {skipped_items} skipped")
        
        # Prepare sync results to mirror Google structure
        sync_results = {
            "latest_sync": {
                "added": len([f for f in uploaded_items if f['type'] == 'new']),
                "updated": len([f for f in uploaded_items if f['type'] == 'updated']),
                "removed": len(deleted_items),
                "skipped": skipped_items,
                "runtime_ms": total_runtime_ms,
                "api_calls": total_api_calls,
                "skip_reasons": {},
                "sync_timestamp": int(time.time())
            },
            "overall_profile": {
                "total_files": len(all_atlassian_items),
                "total_size_bytes": sum(int(item.get('size') or 0) for item in all_atlassian_items),
                "last_updated": int(time.time()),
                "folders_count": 0
            }
        }
        
        # Final state: Embedding (to match Google)
        await update_data_source_sync_status(USER_ID, 'atlassian', layer or 'jira', 'embedding', sync_results=sync_results)
    
    except Exception as error:
        await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'error')
        log.error(f"[{datetime.now().isoformat()}] Atlassian Sync failed critically: {str(error)}", exc_info=True)
        raise error


async def initiate_atlassian_sync_selected_self_hosted(user_id: str, credentials: str, 
                                                        project_keys: List[str], 
                                                        layer: str, base_url: str):
    """Sync only selected Jira projects for self-hosted using PAT"""
    
    log.info(f'Initiating self-hosted Atlassian sync for selected projects')
    log.info(f'User ID: {user_id}, Projects: {project_keys}')

    global USER_ID, USER, script_start_time, total_api_calls

    USER_ID = user_id
    USER = Users.get_user_by_id(user_id)
    
    if not USER:
        raise ValueError(f"User with ID {user_id} not found")
    
    total_api_calls = 0
    script_start_time = time.time()

    # Initialize progress tracking
    sync_start_time = int(time.time())
    # Phase 1: Starting
    print("----------------------------------------------------------------------")
    print("🚀 Phase 1: Starting - preparing sync process...")
    print("----------------------------------------------------------------------")
    await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
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

    await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'syncing')

    try:
        # Credentials is now always a PAT
        bearer_token = credentials
        log.info("Using PAT for self-hosted selected projects sync")
        
        # Get all items from selected projects
        all_items = list_jira_selected_projects_and_issues_self_hosted(
            base_url=base_url,
            bearer_token=bearer_token,
            auth=None,  # No Basic Auth needed
            project_keys=project_keys,
            all_items=[],
            layer=layer
        )
        
        log.info(f"Found {len(all_items)} items from selected projects")
        
        # Discovery complete - set totals
        files_total = len(all_items)
        mb_total = sum(int(item.get('size') or 0) for item in all_items)
        await update_data_source_sync_status(
            USER_ID, 'atlassian', layer or 'jira', 'syncing',
            files_total=files_total,
            mb_total=mb_total,
            sync_start_time=sync_start_time
        )
        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
            'phase': 'discovery',
            'phase_name': 'Phase 2: Discovery',
            'phase_description': 'analyzing existing items and determining sync plan',
            'files_processed': 0,
            'files_total': files_total,
            'mb_processed': 0,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        uploaded_items = []
        deleted_items = []
        skipped_items = 0
        
        # Determine folder prefix
        if layer and layer in LAYER_CONFIG:
            layer_folder = LAYER_CONFIG[layer]['folder']
            user_prefix = f"userResources/{USER_ID}/Atlassian/{layer_folder}/"
        else:
            user_prefix = f"userResources/{USER_ID}/Atlassian/"
        
        # Get existing storage files
        storage_files = list_files_unified(prefix=user_prefix, user_id=USER_ID)
        storage_file_map = {file_info['name']: file_info for file_info in storage_files}
        atlassian_item_paths = {item['fullPath'] for item in all_items}
        
        # Delete orphans for selected projects only
        for file_name, file_info in storage_file_map.items():
            is_selected_project = any(f"/{project_key}/" in file_name for project_key in project_keys)
            if file_name.startswith(user_prefix) and is_selected_project and file_name not in atlassian_item_paths:
                try:
                    delete_file_unified(file_name, user_id=USER_ID)
                    deleted_items.append({
                        'name': file_name,
                        'size': file_info.get('size'),
                        'timeCreated': file_info.get('timeCreated')
                    })
                    log.info(f"[{datetime.now().isoformat()}] Deleted orphan: {file_name}")
                except Exception as e:
                    log.error(f"Error deleting orphan file {file_name}: {str(e)}")
        
        # Upload items in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            for item in all_items:
                # Check for excluded files/extensions (only for attachments)
                if item.get('type') == 'attachment':
                    if any(pattern.lower() in item['fullPath'].lower() for pattern in EXCLUDED_FILES if pattern):
                        log.info(f"Excluded (filename pattern): {item['fullPath']}")
                        skipped_items += 1
                        continue
                    
                    file_ext = item['fullPath'].split('.')[-1].lower() if '.' in item['fullPath'] else ''
                    if ALLOWED_EXTENSIONS and file_ext not in ALLOWED_EXTENSIONS:
                        log.info(f"Skipped (extension): {file_ext} in {item['fullPath']}")
                        skipped_items += 1
                        continue
                
                storage_file = storage_file_map.get(item['fullPath'])
                
                needs_upload = False
                reason = ''
                
                if not storage_file:
                    needs_upload = True
                    reason = 'New item'
                else:
                    storage_updated = parse_date(storage_file.get('updated'))
                    atlassian_modified = parse_date(item.get('modifiedTime'))
                    
                    if atlassian_modified and storage_updated and atlassian_modified > storage_updated:
                        needs_upload = True
                        reason = f"Atlassian version newer ({item['modifiedTime']} > {storage_file.get('updated')})"
                
                if needs_upload:
                    futures.append(
                        (
                            executor.submit(
                                download_and_upload_atlassian_item,
                                item,
                                bearer_token,
                                bool(storage_file),
                                reason,
                                None  # No Basic Auth needed
                            ),
                            item
                        )
                    )
                else:
                    skipped_items += 1
            
            # Process completed uploads
            files_processed = 0
            mb_processed = 0
            for future, item_for_log in futures:
                try:
                    result = future.result()
                    if result:
                        uploaded_items.append(result)
                        files_processed += 1
                        try:
                            mb_processed += int(result.get('size', 0))
                        except Exception:
                            pass
                        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
                            'phase': 'processing',
                            'phase_name': 'Phase 3: Processing',
                            'phase_description': 'synchronizing items to storage',
                            'files_processed': files_processed,
                            'files_total': files_total,
                            'mb_processed': mb_processed,
                            'mb_total': mb_total,
                            'sync_start_time': sync_start_time
                        })
                except Exception as e:
                    log.error(f"Error processing future for {item_for_log.get('fullPath')}: {str(e)}", exc_info=True)
        
        await emit_sync_progress(USER_ID, 'atlassian', layer or 'jira', {
            'phase': 'summarizing',
            'phase_name': 'Phase 4: Summarizing',
            'phase_description': 'finalizing and updating status',
            'files_processed': files_processed,
            'files_total': files_total,
            'mb_processed': mb_processed,
            'mb_total': mb_total,
            'sync_start_time': sync_start_time
        })
        
        # Enhanced summary
        log.info('\nSync Summary for Selected Projects:')
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
        log.info(f"📦 Items Processed: {len(all_items)}")
        log.info(f"🗑️  Orphans Removed: {len(deleted_items)}")
        log.info(f"📂 Selected Projects: {', '.join(project_keys)}")
        
        log.info(f"\nTotal: +{len([f for f in uploaded_items if f['type'] == 'new'])} added, " +
              f"^{len([f for f in uploaded_items if f['type'] == 'updated'])} updated, " +
              f"-{len(deleted_items)} removed, {skipped_items} skipped")
        
        await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'synced')
        
        return {
            "status": "completed",
            "message": f"Self-hosted sync completed for {len(project_keys)} projects",
            "user_id": user_id,
            "layer": layer,
            "project_count": len(project_keys)
        }
    except Exception as e:
        log.error(f"Self-hosted selected projects sync failed: {e}", exc_info=True)
        await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'error')
        raise

async def initiate_atlassian_sync(user_id: str, token: str, layer: str = None,
                                  deployment_type: str = 'cloud',
                                  base_url: str = None):
    """
    Main execution function for Atlassian sync using unified storage with layer support
    
    Args:
        user_id (str): User ID from your app
        token (str): Atlassian OAuth access token (JWT)
        layer (str, optional): Specific Atlassian layer to sync (jira, confluence)
    """
    log.info(f'Initiating Atlassian (Jira & Confluence) sync using unified storage')
    log.info(f'User Open WebUI ID: {user_id}')
    log.info(f'Layer: {layer if layer else "All layers"}')

    global USER_ID
    global USER
    global USER_AUTH
    global script_start_time
    global total_api_calls

    USER_ID = user_id
    USER = Users.get_user_by_id(user_id)
    
    if not USER:
        raise ValueError(f"User with ID {user_id} not found")
    
    username = USER.email
    USER_AUTH = HTTPBasicAuth(username, token) 
    log.info(f'Using email as username: {username} {token} {USER_AUTH}')
    
    total_api_calls = 0
    script_start_time = time.time()

    # Validate layer parameter
    if layer and layer not in LAYER_CONFIG:
        raise ValueError(f"Invalid layer '{layer}'. Valid layers are: {', '.join(LAYER_CONFIG.keys())}")

    await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'syncing')

    try:
        await sync_atlassian_to_storage(
            username, 
            token, 
            layer,
            deployment_type=deployment_type,
            base_url=base_url
        )
        return {
            "status": "started", 
            "message": f"Atlassian sync process has been initiated successfully for {layer if layer else 'all layers'}",
            "user_id": user_id,
            "layer": layer
        }
    except Exception as e:
        log.error(f"Atlassian sync initiation failed: {e}", exc_info=True)
        await update_data_source_sync_status(USER_ID, 'atlassian', layer, 'error')
        raise

def debug_jwt_token(token: str):
    import jwt
    import json
    """Debug function to inspect JWT token contents"""
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        log.info(f"JWT Token Contents: {json.dumps(decoded, indent=2)}")
        
        aud = decoded.get('aud', [])
        scope = decoded.get('scope', '')
        sub = decoded.get('sub', '')
        iss = decoded.get('iss', '')
        
        log.info(f"Token audience (aud): {aud}")
        log.info(f"Token scope: {scope}")
        log.info(f"Token subject (sub): {sub}")
        log.info(f"Token issuer (iss): {iss}")
        
        return decoded
    except Exception as e:
        log.error(f"Failed to decode JWT token: {e}")
        return None