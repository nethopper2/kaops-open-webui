import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import requests
import os
import logging
import jwt
from typing import Optional, List, Dict, Any, Tuple

from open_webui.env import SRC_LOG_LEVELS
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_verified_user
from open_webui.utils.access_control import has_permission
from open_webui.utils.data.encryption import encrypt_data, decrypt_data
from open_webui.models.datatokens import OAuthTokens, OAuthTokenModel
from open_webui.utils.data.data_ingestion import update_data_source_sync_status, delete_gcs_folder
import time
from uuid import uuid4

from open_webui.models.data import (
    DataSourceForm,
    DataSourceModel,
    DataSources,
    DataSourceResponse,
)

from open_webui.tasks import create_task
import asyncio
from open_webui.utils.data.slack import initiate_slack_sync
from open_webui.utils.data.google import initiate_google_file_sync
from open_webui.utils.data.microsoft import initiate_microsoft_sync
from open_webui.utils.data.atlassian import initiate_atlassian_sync
from pydantic import BaseModel

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

router = APIRouter()

from open_webui.env import (
    SLACK_CLIENT_ID,
    SLACK_CLIENT_SECRET,
    SLACK_REDIRECT_URI,

    SLACK_AUTHORIZE_URL,
    SLACK_TOKEN_URL,
    SLACK_AUTH_REVOKE_URL,

    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,

    GOOGLE_AUTHORIZE_URL,
    GOOGLE_TOKEN_URL,
    GOOGLE_AUTH_REVOKE_URL,

    MICROSOFT_CLIENT_ID,
    MICROSOFT_CLIENT_SECRET,
    MICROSOFT_REDIRECT_URI,

    MICROSOFT_AUTHORIZE_URL,
    MICROSOFT_TOKEN_URL,

    ATLASSIAN_API_GATEWAY,
    ATLASSIAN_AUTHORIZE_URL,
    ATLASSIAN_TOKEN_URL, 

    ATLASSIAN_CLIENT_ID,
    ATLASSIAN_CLIENT_SECRET,
    ATLASSIAN_REDIRECT_URL,

    DATASOURCES_URL
)

# Configuration constants
GOOGLE_REDIRECT_URI = "http://localhost:8080/api/v1/data/google/callback"

MICROSOFT_REDIRECT_URI="http://localhost:8080/api/v1/data/microsoft/callback"

GCS_SERVICE_ACCOUNT_BASE64="ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAibmgtc2FuZGJveC00NTEzMDkiLAogICJwcml2YXRlX2tleV9pZCI6ICJlZmU2OGIyZjU4OTdiZTI2MzliODhkNmI3NDIxYTZlMjMwY2I5ODkwIiwKICAicHJpdmF0ZV9rZXkiOiAiLS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tXG5NSUlFdlFJQkFEQU5CZ2txaGtpRzl3MEJBUUVGQUFTQ0JLY3dnZ1NqQWdFQUFvSUJBUURyK1NPR3FwckR4NUtwXG5YZ0hSdnZvYmJRUjlINWVqaENXYVlOUy9WalpQNFFvZlk5ZXhyaG5qSkNwVnBtbXFLVjBoOURnN2tkazhOQ1BtXG5pM1JQRW5QWUYyc1Z6dDZkb0d1VmVRTlcwNGxHOUJWWGdvUFI1emRiRlZpdjY3WTRyRUt5Umt3S3YyQlJnaXUrXG5hSHBXQTRsUFJkaGplSUVZL3NjZHBnL0J5K1JpNkgzNVRnZ3dzdGpRd2V4TUp6eCsrL1dUaStrSnhSK3crTGY1XG5SSnZtbnpSWFBOOUQ2Z1FvUFhraXZUUHJUa3o2WWxmZVVaS0FBV1lQS204UmFRZUZQcTdSWVUxNCtiTld6a2dTXG5NTkpleTVhVVhQNUxjZmhaTjFKcWkzTHNaV3JnYjR5cFBmUkxGTkNRMGgzUmVKSXVLbzdzMndZbzQ5V3ZhQ1JXXG5xSmNKVEc5SkFnTUJBQUVDZ2dFQUl3R0xhK1dndm5UN2xKMFJ5NFlYajl5Qkd6ZkYxTmZjaFRXaXNmek40MVU0XG4zWFhBRUllSnB4amRIK1luVER0RktlMlRMd0VndHkzcituNUxJNVRTOHlac09DaS9mU1pJZDN6amlpeW84NG52XG5wWk1DejYrTGxudEk5QllWYXZ4aEM1WGluNENLL3lSK3JVbE9CcmNSRmwyLzcyZTN6UmUwdmJqK0l1dUdwc1phXG5PNFdXbTJyTE51dU9QZ3d6eDBvdzNldjdXUktRanIxMUhlQnZXa0ZxbW9xQ2F5Zkg4WmxTQ2NvbzE2bHcrd0UrXG5YSlZEc1NnTEc3MWl2Y3pUTUl3UWl5YkJSOFhuUUVXNm1OcTVzSWRxSFZJSW1BTXgrQWQyOUZUQ2JvMFpSL3JmXG5RUS8vT3VjSVE4QkUxVHhDZ3ZmZ1Y3RFlSdnZjcW54YXJwc0djK2lobFFLQmdRRCtzMHpJaTFTeWJvWWttYlpnXG5DUDVqYVIvS0JkQjczNG9rZWdCQlBTTk5YTXhGRWgrZDJ1S2ZyMnhFUThqRHRDT1k2VkxZb1plc0FKaEljTksxXG40VnhMbmlFSWpyK082VnpoTU1nbkd2LzB2TVROb3lMUW9QRk14WGFiSHIxYisrTWhpVUJGS01pNTM0V2g5UmlyXG5pQ3hPTDdrcWNNSUdsYnhhQmRRRFF3cXBSUUtCZ1FEdExXQnB6eFJKZWxBaFFxcHRGRmtibDdpZ1dvZGhrU1MvXG5MMnB6RjYvUmQzaW5lVzBvWGc0ZmNXQW05aVZxbk9wWjBxWW5QcWVMdTR4ZGRSc1U5Tk9veUIwMFI0VldZVXFsXG5RNHp0RmlXMVBmL3pkbEZ1N1ZPTTJ1cTB0V2s4YVRpNWc5OVEvU1ppWTBQUmtBejlmYzdTYWsxVFdvdjVHbEROXG44YVoyZ2tZVU5RS0JnQXFvQ2RCaU0vcjdNTldiTU13MzFCem9xeEhTeUhSR1dBdEtwM1FUVU1UTjJ5WVFxZzM2XG51SHloNUUrKzNrbUI0Zk5sMzdkOG0xSHcvRzRiZWxWdHhtVExpdXBHdnJFR0JvTE5mYkpWS054ZWdZVnhDK1hhXG50ZjNXVFM0VVRTdnFFQWk1SzEwNVpaeVJRNUFSSnlVV0gzUnQvcnROMkhCYUYzVlV4UmdWMS81WkFvR0FES015XG5VL0Q0djhHSXEzMEYzN0lKM1hLRUgrY3k5M3ZvWFZlRmNJUitsY2FyNHlDUk5HbHVqelpYVFR3b1dqbnFNc2NLXG5tMlMzUUxiSmorRkJoQ2hYYnRMYTI0SkVGSW95bEFPNWFwaVhnY1MvOHBVSFdjWERnZW5ZUDdDNjNzRXNpSllDXG5QQ3FBOVJVYzgvbWM5NVRRaEYydHFSZFdCZnZrK2xRNTdtNmFsVkVDZ1lFQXQ3UGtmUnhPWFR6cFVEWFBpdklOXG5zVWpjcFU4TVVSK0VqUW1QV1F3V1ZyTWJhWEpQanVRY3ZOTGlNQWhtRlQrSHphU2tCMFhFRktGZExuQ1FxV1lMXG5LcE90S1lldUJBb0picEx4NFFxRjBoZU5OdXZMNHYyQTVkeGVEQTVlNHpkcnl0bzVqQWN3TDAyTDFPdTJKVzY0XG5pb05wUFJpNHl0VjI0UUNOdENpL1dRQT1cbi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS1cbiIsCiAgImNsaWVudF9lbWFpbCI6ICJnZHJpdmUtZ2NzLXN5bmNAbmgtc2FuZGJveC00NTEzMDkuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJjbGllbnRfaWQiOiAiMTEyNTU0OTg2NzUzMDIyMDQ0NTk5IiwKICAiYXV0aF91cmkiOiAiaHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL28vb2F1dGgyL2F1dGgiLAogICJ0b2tlbl91cmkiOiAiaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW4iLAogICJhdXRoX3Byb3ZpZGVyX3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vb2F1dGgyL3YxL2NlcnRzIiwKICAiY2xpZW50X3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vcm9ib3QvdjEvbWV0YWRhdGEveDUwOS9nZHJpdmUtZ2NzLXN5bmMlNDBuaC1zYW5kYm94LTQ1MTMwOS5pYW0uZ3NlcnZpY2VhY2NvdW50LmNvbSIsCiAgInVuaXZlcnNlX2RvbWFpbiI6ICJnb29nbGVhcGlzLmNvbSIKfQo="
GCS_BUCKET_NAME="nh-private-ai-file-sync-test"

# Global OAuth state store
oauth_state_store = {}

# Provider configurations
PROVIDER_CONFIGS = {
    'google': {
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'authorize_url': GOOGLE_AUTHORIZE_URL,
        'token_url': GOOGLE_TOKEN_URL,
        'revoke_url': GOOGLE_AUTH_REVOKE_URL,
        'scope_separator': ' ',
        'default_scopes': [
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/gmail.readonly"
        ],
        'layer_scopes': {
            'google_drive': 'https://www.googleapis.com/auth/drive.readonly',
            'gmail': 'https://www.googleapis.com/auth/gmail.readonly'
        },
        'layer_folders': {
            'google_drive': 'Google Drive',
            'gmail': 'Gmail'
        }
    },
    'microsoft': {
        'client_id': MICROSOFT_CLIENT_ID,
        'client_secret': MICROSOFT_CLIENT_SECRET,
        'redirect_uri': MICROSOFT_REDIRECT_URI,
        'authorize_url': MICROSOFT_AUTHORIZE_URL,
        'token_url': MICROSOFT_TOKEN_URL,
        'revoke_url': None,  # Microsoft doesn't have a direct revoke endpoint
        'scope_separator': ' ',
        'default_scopes': [
            "User.Read",
            "Files.Read.All",
            "Sites.Read.All",
            "Notes.Read",
            "Mail.Read",
            "MailboxSettings.Read",
            "offline_access"
        ],
        'layer_scopes': {
            'onedrive': 'Files.Read.All',
            'sharepoint': 'Sites.Read.All',
            'onenote': 'Notes.Read',
            'outlook': 'Mail.Read'
        },
        'layer_folders': {
            'onedrive': 'OneDrive',
            'sharepoint': 'SharePoint',
            'onenote': 'OneNote',
            'outlook': 'Outlook'
        }
    },
    'slack': {
        'client_id': SLACK_CLIENT_ID,
        'client_secret': SLACK_CLIENT_SECRET,
        'redirect_uri': SLACK_REDIRECT_URI,
        'authorize_url': SLACK_AUTHORIZE_URL,
        'token_url': SLACK_TOKEN_URL,
        'revoke_url': SLACK_AUTH_REVOKE_URL,
        'scope_separator': ',',
        'default_scopes': [
            "channels:history",
            "groups:history",
            "im:history",
            "mpim:history",
            "files:read",
            "users:read",
            "channels:read",
            "groups:read",
            "im:read",
            "mpim:read"
        ],
        'layer_scopes': {
            'direct_messages': [
                "im:history",
                "im:read",
                "users:read"
            ],
            'channels': [
                "channels:history",
                "channels:read",
                "users:read"
            ],
            'group_chats': [
                "groups:history",
                "groups:read",
                "mpim:history",
                "mpim:read",
                "users:read"
            ],
            'files': [
                "files:read",
                "users:read"
            ]
        },
        'layer_folders': {
            'direct_messages': 'Direct Messages',
            'channels': 'Channels',
            'group_chats': 'Group Messages',
            'files': 'Files'
        }
    },
    'atlassian': {
        'client_id': ATLASSIAN_CLIENT_ID,
        'client_secret': ATLASSIAN_CLIENT_SECRET,
        'redirect_uri': ATLASSIAN_REDIRECT_URL,
        'authorize_url': ATLASSIAN_AUTHORIZE_URL,
        'token_url': ATLASSIAN_TOKEN_URL,
        'revoke_url': None,  # Atlassian doesn't have a direct revoke endpoint
        'scope_separator': ' ',
        'default_scopes': [
            "read:user:jira",
            "read:issue:jira",
            "read:comment:jira",
            "read:attachment:jira",
            "read:project:jira",
            "read:issue-meta:jira",
            "read:field:jira",
            "read:filter:jira",
            "read:jira-work",
            "read:jira-user",
            "read:me",
            "read:account",
            "report:personal-data",
            "read:content:confluence",
            "read:space:confluence",
            "read:page:confluence",
            "read:blogpost:confluence",
            "read:attachment:confluence",
            "read:comment:confluence",
            "read:user:confluence",
            "read:group:confluence",
            "read:configuration:confluence",
            "search:confluence",
            "read:audit-log:confluence"
        ],
        'layer_scopes': {
            'jira': [
                "read:user:jira",
                "read:issue:jira",
                "read:comment:jira",
                "read:attachment:jira",
                "read:project:jira",
                "read:issue-meta:jira",
                "read:field:jira",
                "read:filter:jira",
                "read:jira-work",
                "read:jira-user",
                "read:me",
                "read:account",
                "report:personal-data"
            ],
            'confluence': [
                "read:content:confluence",
                "read:space:confluence",
                "read:page:confluence",
                "read:blogpost:confluence",
                "read:attachment:confluence",
                "read:comment:confluence",
                "read:user:confluence",
                "read:group:confluence",
                "read:configuration:confluence",
                "search:confluence",
                "read:audit-log:confluence",
                "read:me",
                "read:account"
            ]
        },
        'layer_folders': {
            'jira': 'Jira',
            'confluence': 'Confluence'
        }
    }
}

############################
# Reusable Helper Functions
############################

def create_oauth_state(user_id: str, layer: str) -> str:
    """Create and store OAuth state for security."""
    state = str(uuid.uuid4())
    oauth_state_store[state] = {
        "user_id": user_id,
        "layer": layer
    }
    log.info(f"Created OAuth state for user {user_id}, layer {layer}")
    return state

def validate_oauth_state(state: str) -> Dict[str, Any]:
    """Validate and consume OAuth state."""
    if not state or state not in oauth_state_store:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state.")
    
    state_data = oauth_state_store.pop(state)
    log.info(f"Validated OAuth state for user {state_data['user_id']}")
    return state_data

def encrypt_tokens(access_token: str, refresh_token: str = None) -> Tuple[str, Optional[str]]:
    """Encrypt OAuth tokens for storage."""
    encrypted_access_token = encrypt_data(access_token)
    encrypted_refresh_token = encrypt_data(refresh_token) if refresh_token else None
    return encrypted_access_token, encrypted_refresh_token

def decrypt_tokens(token_entry: OAuthTokenModel) -> Tuple[str, Optional[str]]:
    """Decrypt OAuth tokens from storage."""
    try:
        decrypted_access_token = decrypt_data(token_entry.encrypted_access_token)
        decrypted_refresh_token = decrypt_data(token_entry.encrypted_refresh_token) if token_entry.encrypted_refresh_token else None
        return decrypted_access_token, decrypted_refresh_token
    except Exception as e:
        log.error(f"Failed to decrypt tokens for token ID {token_entry.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt tokens. Please try re-authorizing.")

def get_provider_scopes(provider: str, layer: str = None) -> List[str]:
    """Get appropriate scopes for a provider and layer."""
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    
    if layer and layer in config['layer_scopes']:
        layer_scope = config['layer_scopes'][layer]
        return layer_scope if isinstance(layer_scope, list) else [layer_scope]
    
    return config['default_scopes']

def merge_scopes_and_layers(existing_token: OAuthTokenModel, new_scopes: str, new_layer: str, provider: str) -> Tuple[str, str]:
    """Merge existing and new scopes and layers."""
    config = PROVIDER_CONFIGS[provider]
    separator = config['scope_separator']
    
    # Merge scopes
    merged_scopes = new_scopes
    if existing_token and existing_token.scopes:
        if separator == ' ':
            existing_scopes_set = set(existing_token.scopes.split())
            new_scopes_set = set(new_scopes.split())
        else:  # comma-separated (Slack)
            existing_scopes_set = set(scope.strip() for scope in existing_token.scopes.split(','))
            new_scopes_set = set(scope.strip() for scope in new_scopes.split(','))
        
        merged_scopes_set = existing_scopes_set.union(new_scopes_set)
        merged_scopes = separator.join(sorted(merged_scopes_set))
        log.info(f"Merged scopes for {provider}: existing={existing_token.scopes}, new={new_scopes}, merged={merged_scopes}")
    
    # Merge layers
    merged_layer = new_layer
    if existing_token and existing_token.layer and new_layer:
        existing_layer_set = set(existing_token.layer.split(","))
        new_layer_set = set(new_layer.split(","))
        merged_layer_set = existing_layer_set.union(new_layer_set)
        merged_layer = ",".join(sorted(merged_layer_set))
        log.info(f"Merged layers for {provider}: existing={existing_token.layer}, new={new_layer}, merged={merged_layer}")
    elif existing_token and existing_token.layer and not new_layer:
        merged_layer = existing_token.layer
    
    return merged_scopes, merged_layer

def check_sync_in_progress(user_id: str, provider: str, layer: str) -> bool:
    """Check if sync is already in progress for a specific provider/layer."""
    user_data_sources = DataSources.get_data_sources_by_user_id(user_id)
    for ds in user_data_sources:
        if ds.action == provider and ds.layer == layer:
            return ds.sync_status == 'syncing'
    return False

def build_auth_url(provider: str, scopes: List[str], state: str, **extra_params) -> str:
    """Build OAuth authorization URL for any provider."""
    config = PROVIDER_CONFIGS[provider]
    scope_str = config['scope_separator'].join(scopes)
    
    base_params = {
        'client_id': config['client_id'],
        'redirect_uri': config['redirect_uri'],
        'response_type': 'code',
        'scope': scope_str,
        'state': state
    }
    
    # Add provider-specific parameters
    if provider == 'google':
        base_params.update({
            'access_type': 'offline',
            'prompt': 'consent'
        })
    elif provider == 'microsoft':
        base_params['response_mode'] = 'query'
    elif provider == 'slack':
        base_params['user_scope'] = scope_str  # Slack-specific
    elif provider == 'atlassian':
        base_params.update({
            'prompt': 'consent',
            'audience': ATLASSIAN_API_GATEWAY
        })
    
    base_params.update(extra_params)
    
    # Build URL
    param_str = '&'.join(f"{k}={v}" for k, v in base_params.items())
    return f"{config['authorize_url']}?{param_str}"

def exchange_code_for_tokens(provider: str, code: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange authorization code for tokens."""
    config = PROVIDER_CONFIGS[provider]
    
    data = {
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'code': code,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    headers = {}
    if provider == 'slack':
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    
    response = requests.post(config['token_url'], data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def refresh_access_token(provider: str, refresh_token: str) -> Dict[str, Any]:
    """Refresh access token using refresh token."""
    config = PROVIDER_CONFIGS[provider]
    
    data = {
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    
    headers = {}
    if provider == 'slack':
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    
    response = requests.post(config['token_url'], data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def extract_user_id_from_token(provider: str, token_data: Dict[str, Any]) -> Optional[str]:
    """Extract provider-specific user ID from token response."""
    if provider == 'google' and 'id_token' in token_data:
        try:
            decoded_token = jwt.decode(token_data['id_token'], options={"verify_signature": False})
            return decoded_token.get("sub")
        except Exception as e:
            log.error(f"Failed to decode Google id_token: {e}")
    elif provider == 'microsoft' and 'id_token' in token_data:
        try:
            decoded_token = jwt.decode(token_data['id_token'], options={"verify_signature": False})
            return decoded_token.get("oid") or decoded_token.get("sub")
        except Exception as e:
            log.error(f"Failed to decode Microsoft id_token: {e}")
    elif provider == 'slack':
        return token_data.get("authed_user", {}).get("id")
    elif provider == 'atlassian' and 'access_token' in token_data:
        try:
            decoded_token = jwt.decode(token_data['access_token'], options={"verify_signature": False})
            return decoded_token.get("sub")
        except Exception as e:
            log.error(f"Failed to decode Atlassian access_token: {e}")
    
    return None

def get_primary_token_for_storage(provider: str, token_data: Dict[str, Any]) -> str:
    """Get the primary token to store for each provider."""
    if provider == 'slack':
        user_token = token_data.get("authed_user", {}).get("access_token")
        bot_token = token_data.get("access_token")
        return user_token if user_token else bot_token
    else:
        return token_data.get("access_token")

async def create_background_sync_task(request: Request, provider: str, user_id: str, access_token: str, layer: str = None):
    """Create background sync task for any provider."""
    redis_connection = getattr(request.app.state, 'redis', None) if hasattr(request.app.state, 'redis') else None
    
    if provider == 'google':
        sync_drive = layer == 'google_drive'
        sync_gmail = layer == 'gmail'
        
        async def run_google_sync():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: asyncio.run(initiate_google_file_sync(
                    user_id, access_token, GCS_SERVICE_ACCOUNT_BASE64, GCS_BUCKET_NAME, sync_drive, sync_gmail
                ))
            )
        
        await create_task(redis_connection, run_google_sync(), id=f"google_sync_{user_id}")
    
    elif provider == 'microsoft':
        sync_onedrive = layer == 'onedrive'
        sync_sharepoint = layer == 'sharepoint'
        sync_onenote = layer == 'onenote'
        sync_outlook = layer == 'outlook'
        
        async def run_microsoft_sync():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: asyncio.run(initiate_microsoft_sync(
                    user_id, access_token, GCS_SERVICE_ACCOUNT_BASE64, GCS_BUCKET_NAME, 
                    sync_onedrive, sync_sharepoint, sync_onenote, sync_outlook
                ))
            )
        
        await create_task(redis_connection, run_microsoft_sync(), id=f"microsoft_sync_{user_id}")
    
    elif provider == 'slack':
        async def run_slack_sync():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: asyncio.run(initiate_slack_sync(
                    user_id, access_token, GCS_SERVICE_ACCOUNT_BASE64, GCS_BUCKET_NAME, layer
                ))
            )
        
        await create_task(redis_connection, run_slack_sync(), id=f"slack_sync_{user_id}")
    
    elif provider == 'atlassian':
        async def run_atlassian_sync():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: asyncio.run(initiate_atlassian_sync(
                    user_id, access_token, GCS_SERVICE_ACCOUNT_BASE64, GCS_BUCKET_NAME, layer
                ))
            )
        
        await create_task(redis_connection, run_atlassian_sync(), id=f"atlassian_sync_{user_id}")

async def create_background_delete_task(request: Request, provider: str, user_id: str, layer: str = None):
    """Create background GCS cleanup task for any provider."""
    redis_connection = getattr(request.app.state, 'redis', None) if hasattr(request.app.state, 'redis') else None
    
    config = PROVIDER_CONFIGS[provider]
    if layer and layer in config['layer_folders']:
        folder_name = config['layer_folders'][layer]
        folder_path = f"userResources/{user_id}/{provider.title()}/{folder_name}"
    else:
        # Default folder structure
        folder_map = {
            'google': 'Google',
            'microsoft': 'Microsoft', 
            'slack': 'Slack',
            'atlassian': 'Atlassian'
        }
        folder_path = f"userResources/{user_id}/{folder_map.get(provider, provider.title())}/"
    
    async def delete_sync():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: asyncio.run(delete_gcs_folder(folder_path, GCS_SERVICE_ACCOUNT_BASE64, GCS_BUCKET_NAME))
        )
    
    await create_task(redis_connection, delete_sync(), id=f"delete_{provider}_sync_{user_id}")

def handle_token_refresh(provider: str, token_entry: OAuthTokenModel, user_id: str) -> Tuple[str, bool]:
    """Handle token refresh logic for any provider. Returns (access_token, needs_reauth)."""
    current_time = int(time.time())
    refresh_needed = False
    
    if token_entry.access_token_expires_at:
        if (token_entry.access_token_expires_at - current_time) < (5 * 60):
            refresh_needed = True
            log.info(f"Access token for user {user_id} nearing expiration. Initiating refresh.")
    
    decrypted_access_token, decrypted_refresh_token = decrypt_tokens(token_entry)
    
    if refresh_needed and decrypted_refresh_token:
        try:
            log.info(f"Attempting to refresh {provider} token for user {user_id}")
            refresh_data = refresh_access_token(provider, decrypted_refresh_token)
            
            if provider == 'slack' and not refresh_data.get("ok"):
                raise HTTPException(status_code=400, detail=f"Failed to refresh {provider} token: {refresh_data.get('error')}")
            elif provider != 'slack' and "error" in refresh_data:
                raise HTTPException(status_code=400, detail=f"Failed to refresh {provider} token: {refresh_data.get('error_description', refresh_data.get('error'))}")
            
            new_access_token = refresh_data.get("access_token")
            new_refresh_token = refresh_data.get("refresh_token", decrypted_refresh_token)
            new_expires_in = refresh_data.get("expires_in")
            
            if not new_access_token:
                raise HTTPException(status_code=500, detail="No new access token received after refresh.")
            
            # Update database with new tokens
            encrypted_new_access_token, encrypted_new_refresh_token = encrypt_tokens(new_access_token, new_refresh_token)
            new_access_token_expires_at = int(time.time()) + new_expires_in if new_expires_in else None
            
            updated_token_entry = OAuthTokens.update_token_by_id(
                token_id=token_entry.id,
                encrypted_access_token=encrypted_new_access_token,
                encrypted_refresh_token=encrypted_new_refresh_token,
                access_token_expires_at=new_access_token_expires_at,
                scopes=refresh_data.get("scope", token_entry.scopes)
            )
            
            if not updated_token_entry:
                raise HTTPException(status_code=500, detail=f"Failed to update refreshed {provider} tokens in database.")
            
            log.info(f"Successfully refreshed and updated {provider} tokens for user {user_id}")
            return new_access_token, False
            
        except Exception as e:
            log.error(f"{provider} token refresh failed for user {user_id}: {str(e)}")
            if "invalid_grant" in str(e).lower() or "invalid_token" in str(e).lower():
                return decrypted_access_token, True  # Needs re-auth
            raise
    
    elif refresh_needed and not decrypted_refresh_token:
        log.warning(f"Access token for user {user_id} nearing expiration but no valid refresh token available.")
        return decrypted_access_token, True  # Needs re-auth
    
    return decrypted_access_token, False

def generate_reauth_url(provider: str, user_id: str, layer: str = None) -> str:
    """Generate re-authorization URL when refresh fails."""
    scopes = get_provider_scopes(provider, layer)
    state = create_oauth_state(user_id, layer)
    return build_auth_url(provider, scopes, state)

############################
# Data Source CRUD Operations (Original)
############################

@router.get("/source/", response_model=list[DataSourceResponse])
async def get_data_sources(user=Depends(get_verified_user)):
    """Get all data sources for the authenticated user"""
    try:
        data_sources = DataSources.get_data_sources_by_user_id(user.id)
        return [
            DataSourceResponse(
                id=ds.id,
                user_id=ds.user_id,
                name=ds.name,
                context=ds.context,
                permission=ds.permission,
                sync_status=ds.sync_status,
                last_sync=ds.last_sync,
                icon=ds.icon,
                action=ds.action,
                layer=ds.layer,
                created_at=ds.created_at,
                updated_at=ds.updated_at,
            )
            for ds in data_sources
        ]
    except Exception as e:
        log.exception(e)
        log.error("Error getting data sources")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error getting data sources"),
        )

@router.post("/source/")
def create_data_source(form_data: DataSourceForm, user=Depends(get_verified_user)):
    """Create a new data source for the authenticated user"""
    try:
        data_source = DataSources.insert_new_data_source(user.id, form_data)
        if data_source:
            return DataSourceResponse(
                id=data_source.id,
                user_id=data_source.user_id,
                name=data_source.name,
                context=data_source.context,
                sync_status=data_source.sync_status,
                last_sync=data_source.last_sync,
                icon=data_source.icon,
                action=data_source.action,
                created_at=data_source.created_at,
                updated_at=data_source.updated_at,
            )
        else:
            raise Exception("Error creating data source")
    except Exception as e:
        log.exception(e)
        log.error("Error creating data source")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error creating data source"),
        )

@router.post("/sources/initialize")
def initialize_default_data_sources(user=Depends(get_verified_user)):
    """Initialize default data sources for a user (typically called on signup)"""
    try:
        existing_sources = DataSources.get_data_sources_by_user_id(user.id)
        if existing_sources:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Data sources already initialized"),
            )

        data_sources = DataSources.create_default_data_sources_for_user(user.id)
        return [
            DataSourceResponse(
                id=ds.id,
                user_id=ds.user_id,
                name=ds.name,
                context=ds.context,
                sync_status=ds.sync_status,
                last_sync=ds.last_sync,
                icon=ds.icon,
                action=ds.action,
                created_at=ds.created_at,
                updated_at=ds.updated_at,
            )
            for ds in data_sources
        ]
    except HTTPException:
        raise
    except Exception as e:
        log.exception(e)
        log.error("Error initializing default data sources")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error initializing data sources"),
        )

@router.get("/source/{id}", response_model=Optional[DataSourceResponse])
async def get_data_source_by_id(id: str, user=Depends(get_verified_user)):
    """Get a specific data source by ID"""
    data_source = DataSources.get_data_source_by_id(id)
    if data_source and data_source.user_id == user.id:
        return DataSourceResponse(
            id=data_source.id,
            user_id=data_source.user_id,
            name=data_source.name,
            context=data_source.context,
            sync_status=data_source.sync_status,
            last_sync=data_source.last_sync,
            icon=data_source.icon,
            action=data_source.action,
            created_at=data_source.created_at,
            updated_at=data_source.updated_at,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

@router.post("/source/{id}/update")
async def update_data_source_by_id(
    id: str, form_data: DataSourceForm, user=Depends(get_verified_user)
):
    """Update a data source by ID"""
    data_source = DataSources.get_data_source_by_id(id)
    if data_source and data_source.user_id == user.id:
        try:
            updated_data_source = DataSources.update_data_source_by_id(id, form_data)
            if updated_data_source:
                return DataSourceResponse(
                    id=updated_data_source.id,
                    user_id=updated_data_source.user_id,
                    name=updated_data_source.name,
                    context=updated_data_source.context,
                    sync_status=updated_data_source.sync_status,
                    last_sync=updated_data_source.last_sync,
                    icon=updated_data_source.icon,
                    action=updated_data_source.action,
                    created_at=updated_data_source.created_at,
                    updated_at=updated_data_source.updated_at,
                )
            else:
                raise Exception("Error updating data source")
        except Exception as e:
            log.exception(e)
            log.error(f"Error updating data source: {id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating data source"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

class SyncStatusForm(BaseModel):
    sync_status: str
    last_sync: Optional[int] = None

@router.post("/source/{id}/sync")
async def update_sync_status(
    id: str, form_data: SyncStatusForm, user=Depends(get_verified_user)
):
    """Update the sync status of a data source"""
    data_source = DataSources.get_data_source_by_id(id)
    if data_source and data_source.user_id == user.id:
        try:
            updated_data_source = DataSources.update_data_source_by_id(
                id, form_data
            )
            if updated_data_source:
                return DataSourceResponse(
                    id=updated_data_source.id,
                    user_id=updated_data_source.user_id,
                    name=updated_data_source.name,
                    context=updated_data_source.context,
                    sync_status=updated_data_source.sync_status,
                    last_sync=updated_data_source.last_sync,
                    icon=updated_data_source.icon,
                    action=updated_data_source.action,
                    created_at=updated_data_source.created_at,
                    updated_at=updated_data_source.updated_at,
                )
            else:
                raise Exception("Error updating sync status")
        except Exception as e:
            log.exception(e)
            log.error(f"Error updating sync status for data source: {id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating sync status"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

@router.delete("/source/{id}")
async def delete_data_source_by_id(
    request: Request, id: str, user=Depends(get_verified_user)
):
    """Delete a data source by ID"""
    delete_permission = has_permission(
        user.id, "datasource.delete", request.app.state.config.USER_PERMISSIONS
    )

    if user.role != "admin" and not delete_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    data_source = DataSources.get_data_source_by_id(id)
    if data_source and data_source.user_id == user.id:
        try:
            result = DataSources.delete_data_source_by_id(id)
            if result:
                return {"success": True, "message": "Data source deleted successfully"}
            else:
                raise Exception("Error deleting data source")
        except Exception as e:
            log.exception(e)
            log.error(f"Error deleting data source: {id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error deleting data source"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

############################
# Universal OAuth Endpoints
############################

def create_universal_initialize_endpoint(provider: str):
    """Factory function to create initialize endpoints for any provider."""
    @router.get(f"/{provider}/initialize")
    def get_auth_url(
        user=Depends(get_verified_user),
        layer: str = Query(None, description=f"Specific {provider.title()} Data Layer to sync")
    ):
        f"""Generate {provider.title()} OAuth URL for the current authenticated user."""
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        if check_sync_in_progress(user.id, provider, layer):
            return {"message": f"{provider.title()} sync already in progress"}
        
        scopes = get_provider_scopes(provider, layer)
        state = create_oauth_state(user.id, layer)
        auth_url = build_auth_url(provider, scopes, state)
        
        return {
            "url": auth_url,
            "user_id": user.id,
            "scopes": scopes
        }
    
    return get_auth_url

def create_universal_callback_endpoint(provider: str):
    """Factory function to create callback endpoints for any provider."""
    @router.get(f"/{provider}/callback")
    async def callback(request: Request):
        f"""Handle {provider.title()} OAuth callback and initiate sync process."""
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")

        if error:
            log.error(f"{provider.title()} OAuth error: {error} - {error_description}")
            return Response(status_code=400, content=f"{provider.title()} OAuth error: {error_description or error}")

        if not code:
            raise HTTPException(status_code=400, detail=f"Missing {provider.title()} OAuth code.")

        state_data = validate_oauth_state(state)
        user_id = state_data["user_id"]
        layer = state_data.get("layer")

        try:
            config = PROVIDER_CONFIGS[provider]
            token_data = exchange_code_for_tokens(provider, code, config['redirect_uri'])
            
            if provider == 'slack' and not token_data.get("ok"):
                raise HTTPException(status_code=400, detail=f"{provider.title()} OAuth failed: {token_data.get('error')}")
            elif provider != 'slack' and "error" in token_data:
                raise HTTPException(status_code=400, detail=f"{provider.title()} OAuth failed: {token_data.get('error_description', token_data.get('error'))}")

            log.info(f"{provider.title()} OAuth successful for user {user_id} for layer {layer}")

            # Extract tokens and metadata
            access_token = get_primary_token_for_storage(provider, token_data)
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            provider_user_id = extract_user_id_from_token(provider, token_data)
            new_scopes = token_data.get("scope", "")
            
            # Extract team/tenant ID for multi-tenant providers
            team_id = None
            if provider == 'slack':
                team_id = token_data.get("team", {}).get("id")

            if not access_token:
                raise HTTPException(
                    status_code=500,
                    detail=f"No access token received from {provider.title()} OAuth."
                )

            # Check for existing token and merge scopes/layers
            existing_token = OAuthTokens.get_token_by_user_provider_details(
                user_id=user_id,
                provider_name=provider.title()
            )

            merged_scopes, merged_layer = merge_scopes_and_layers(existing_token, new_scopes, layer, provider)

            # Encrypt and store tokens
            encrypted_access_token, encrypted_refresh_token = encrypt_tokens(access_token, refresh_token)
            access_token_expires_at = int(time.time()) + expires_in if expires_in else None

            try:
                OAuthTokens.insert_new_token(
                    user_id=user_id,
                    provider_name=provider.title(),
                    provider_user_id=provider_user_id,
                    provider_team_id=team_id,
                    encrypted_access_token=encrypted_access_token,
                    encrypted_refresh_token=encrypted_refresh_token,
                    access_token_expires_at=access_token_expires_at,
                    scopes=merged_scopes,
                    layer=merged_layer
                )
                log.info(f"Stored/Updated {provider.title()} OAuth tokens for user {user_id}")

            except Exception as db_error:
                log.error(f"Failed to store {provider.title()} OAuth tokens in DB for user {user_id}: {db_error}")
                raise HTTPException(status_code=500, detail=f"Failed to store {provider.title()} tokens securely.")

            # Validate GCS configuration
            if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
                raise HTTPException(
                    status_code=500,
                    detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
                )

            # Initiate sync
            try:
                log.info(f"Starting {provider.title()} sync for user {user_id}")
                await create_background_sync_task(request, provider, user_id, access_token, layer)
                
                return RedirectResponse(url=DATASOURCES_URL, status_code=302)

            except Exception as sync_error:
                log.error(f"{provider.title()} sync failed for user {user_id}: {str(sync_error)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"{provider.title()} sync failed: {str(sync_error)}"
                )

        except requests.exceptions.RequestException as e:
            log.error(f"{provider.title()} API Request Error: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Response: {e.response.text}")
            raise HTTPException(status_code=500, detail=f"Failed to authenticate with {provider.title()}")
    
    return callback

def create_universal_status_endpoint(provider: str):
    """Factory function to create status endpoints for any provider."""
    @router.get(f"/{provider}/status")
    def get_status(user=Depends(get_verified_user)):
        f"""Get current user's {provider.title()} integration status."""
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")

        config = PROVIDER_CONFIGS[provider]
        config_status = {
            "gcs_bucket_configured": bool(GCS_BUCKET_NAME),
            "gcs_credentials_configured": bool(GCS_SERVICE_ACCOUNT_BASE64),
            f"{provider}_client_configured": bool(config['client_id'] and config['client_secret'] and config['redirect_uri']),
        }

        token_exists = OAuthTokens.get_token_by_user_provider_details(user_id=user.id, provider_name=provider.title())
        
        sync_status = "not_connected"
        user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
        for ds in user_data_sources:
            if ds.action == provider:
                sync_status = ds.sync_status
                break

        return {
            "user_id": user.id,
            "configuration": config_status,
            f"{provider}_token_present": bool(token_exists),
            "current_sync_status": sync_status,
            "ready_for_sync": all(config_status.values()) and bool(token_exists) and sync_status != "syncing"
        }
    
    return get_status

def create_universal_sync_endpoint(provider: str):
    """Factory function to create manual sync endpoints for any provider."""
    @router.post(f"/{provider}/sync")
    async def manual_sync(
        request: Request,
        layer: str = Query(None, description=f"Specific {provider.title()} Data Layer to sync"),
        user=Depends(get_verified_user),
    ):
        f"""Manually trigger {provider.title()} sync for the authenticated user."""
        if not user:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        if check_sync_in_progress(user.id, provider, layer):
            return {"message": f"{provider.title()} sync already in progress"}

        # Get token entry
        token_entry = OAuthTokens.get_token_by_user_provider_details(
            user_id=user.id,
            provider_name=provider.title()
        )

        if not token_entry:
            raise HTTPException(
                status_code=404,
                detail=f"No {provider.title()} integration found for this user. Please authorize your {provider.title()} app first."
            )

        # Handle token refresh if needed
        try:
            access_token, needs_reauth = handle_token_refresh(provider, token_entry, user.id)
            
            if needs_reauth:
                reauth_url = generate_reauth_url(provider, user.id, layer)
                raise HTTPException(
                    status_code=201,
                    detail={
                        "error": "token_expired_no_refresh",
                        "message": f"{provider.title()} token is expired and requires re-authorization.",
                        "reauth_url": reauth_url,
                        "action_required": f"redirect_to_{provider}_auth",
                        "user_id": str(user.id),
                        "provider": provider
                    }
                )

        except HTTPException:
            raise
        except Exception as e:
            log.error(f"Token refresh failed for {provider} user {user.id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to refresh {provider.title()} token.")

        # Validate GCS configuration
        if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
            raise HTTPException(
                status_code=500,
                detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
            )

        try:
            log.info(f"Starting manual {provider.title()} sync for user {user.id}")
            await create_background_sync_task(request, provider, user.id, access_token, layer)
            return RedirectResponse(url=DATASOURCES_URL, status_code=302)

        except Exception as sync_error:
            log.error(f"{provider.title()} sync failed for user {user.id}: {str(sync_error)}")
            if "invalid_grant" in str(sync_error).lower() or "invalid_token" in str(sync_error).lower():
                log.warning(f"{provider.title()} sync for user {user.id} failed due to invalid token.")
                raise HTTPException(
                    status_code=401,
                    detail=f"{provider.title()} token invalid or expired. Please re-authorize your {provider.title()} integration."
                )
            raise HTTPException(
                status_code=500,
                detail=f"{provider.title()} sync failed: {str(sync_error)}"
            )
    
    return manual_sync

def create_universal_disconnect_endpoint(provider: str):
    """Factory function to create disconnect endpoints for any provider."""
    @router.delete(f"/{provider}/disconnect")
    async def disconnect(
        request: Request,
        layer: str = Query(None, description=f"Specific {provider.title()} Data Layer to disconnect"),
        user=Depends(get_verified_user),
        team_id: Optional[str] = Query(None, alias=f"{provider}_team_id", description="Team/Tenant ID for multi-tenant providers")
    ):
        f"""Disconnect a user's {provider.title()} integration."""
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

        user_id = user.id
        log.info(f"Initiating {provider.title()} integration disconnection for user: {user_id}")

        overall_success = True
        messages = []

        # Handle layer-specific disconnection (like Google)
        if layer:
            return await disconnect_provider_layer(provider, user_id, layer, team_id, request, messages)

        # Full provider disconnection
        # Get tokens to process
        tokens_to_process: List[OAuthTokenModel] = []
        if team_id:
            token_entry = OAuthTokens.get_token_by_user_provider_details(
                user_id=user_id,
                provider_name=provider.title(),
                provider_team_id=team_id
            )
            if token_entry:
                tokens_to_process.append(token_entry)
        else:
            all_user_tokens = OAuthTokens.get_all_tokens_for_user(user_id=user_id)
            tokens_to_process = [
                token for token in all_user_tokens if token.provider_name == provider.title()
            ]

        # Revoke tokens if provider supports it
        config = PROVIDER_CONFIGS[provider]
        if config['revoke_url']:
            for token_entry in tokens_to_process:
                try:
                    decrypted_access_token, _ = decrypt_tokens(token_entry)
                    
                    if provider == 'slack':
                        revoke_response = requests.post(
                            config['revoke_url'],
                            headers={'Authorization': f'Bearer {decrypted_access_token}'}
                        )
                    else:  # Google
                        revoke_response = requests.post(
                            config['revoke_url'],
                            params={'token': decrypted_access_token}
                        )
                    
                    if revoke_response.status_code == 200:
                        msg = f"Successfully revoked {provider.title()} token ID: {token_entry.id}"
                        log.info(msg)
                        messages.append(msg)
                    
                except Exception as e:
                    msg = f"Error revoking {provider.title()} token {token_entry.id}: {e}"
                    log.error(msg)
                    messages.append(msg)
                    overall_success = False

        # Delete tokens from database
        try:
            if team_id:
                db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                    user_id=user_id,
                    provider_name=provider.title(),
                    provider_team_id=team_id
                )
            else:
                db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                    user_id=user_id,
                    provider_name=provider.title()
                )

            if db_delete_success:
                msg = f"Successfully deleted {provider.title()} OAuth token(s) from DB"
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to delete {provider.title()} OAuth token(s) from DB"
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error deleting {provider.title()} OAuth token(s): {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False

        # Update data source sync status
        data_source_found: Optional[DataSourceModel] = None
        user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
        for ds in user_data_sources:
            if ds.action == provider:
                data_source_found = ds
                break

        if data_source_found:
            try:
                updated_ds = DataSources.update_data_source_sync_status_by_name(
                    user_id=user_id,
                    source_name=data_source_found.name,
                    sync_status="unsynced",
                    last_sync=int(time.time())
                )
                if updated_ds:
                    msg = f"Successfully updated {provider.title()} data source status to 'unsynced'"
                    log.info(msg)
                    messages.append(msg)
                else:
                    msg = f"Failed to update {provider.title()} data source status"
                    log.error(msg)
                    messages.append(msg)
                    overall_success = False
            except Exception as e:
                msg = f"Error updating {provider.title()} data source status: {e}"
                log.exception(msg)
                messages.append(msg)
                overall_success = False
        else:
            msg = f"{provider.title()} data source not found for user {user_id}"
            log.warning(msg)
            messages.append(msg)

        # Delete user data from GCS Bucket
        if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
            msg = "GCS configuration missing. Cannot perform GCS data cleanup."
            log.error(msg)
            messages.append(msg)
            overall_success = False
        else:
            try:
                await create_background_delete_task(request, provider, user_id, layer)
                msg = f"Successfully initiated GCS data cleanup for user {user_id}'s {provider.title()} folder"
                log.info(msg)
                messages.append(msg)
            except Exception as e:
                msg = f"Error during GCS data cleanup: {e}"
                log.exception(msg)
                messages.append(msg)
                overall_success = False

        if overall_success:
            log.info(f"{provider.title()} integration disconnection completed successfully for user: {user_id}")
            return {"message": f"{provider.title()} integration disconnected successfully.", "details": messages}
        else:
            log.warning(f"{provider.title()} integration disconnection completed with failures for user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": f"Failed to fully disconnect {provider.title()} integration.", "details": messages}
            )
    
    return disconnect

async def disconnect_provider_layer(provider: str, user_id: str, layer: str, team_id: str, request: Request, messages: List[str]) -> dict:
    """Handle layer-specific disconnection for providers that support it."""
    overall_success = True
    
    # Get tokens to process for layer removal
    tokens_to_process: List[OAuthTokenModel] = []
    if team_id:
        token_entry = OAuthTokens.get_token_by_user_provider_details(
            user_id=user_id,
            provider_name=provider.title(),
            provider_team_id=team_id
        )
        if token_entry:
            tokens_to_process.append(token_entry)
    else:
        all_user_tokens = OAuthTokens.get_all_tokens_for_user(user_id=user_id)
        tokens_to_process = [
            token for token in all_user_tokens if token.provider_name == provider.title()
        ]

    if not tokens_to_process:
        msg = f"No {provider.title()} tokens found for user {user_id}"
        log.warning(msg)
        messages.append(msg)
    else:
        for token_entry in tokens_to_process:
            try:
                current_layers = token_entry.layer if token_entry.layer else ""
                
                if not current_layers or layer not in current_layers.split(","):
                    msg = f"Layer '{layer}' not found in token {token_entry.id}"
                    log.info(msg)
                    messages.append(msg)
                    continue
                
                # Remove the specified layer
                layer_set = set(current_layers.split(","))
                layer_set.discard(layer)
                remaining_layers = ",".join(sorted(layer_set)) if layer_set else ""
                
                if remaining_layers:
                    # Update token with remaining layers
                    updated_token = OAuthTokens.update_token_by_id(
                        token_id=token_entry.id,
                        encrypted_access_token=token_entry.encrypted_access_token,
                        access_token_expires_at=token_entry.access_token_expires_at,
                        scopes=token_entry.scopes,
                        layer=remaining_layers
                    )
                    if updated_token:
                        msg = f"Updated token {token_entry.id}, removed layer '{layer}', remaining: '{remaining_layers}'"
                        log.info(msg)
                        messages.append(msg)
                    else:
                        msg = f"Failed to update token {token_entry.id}"
                        log.error(msg)
                        messages.append(msg)
                        overall_success = False
                else:
                    # No layers remaining, revoke and delete the entire token
                    config = PROVIDER_CONFIGS[provider]
                    if config['revoke_url']:
                        try:
                            decrypted_access_token, _ = decrypt_tokens(token_entry)
                            
                            if provider == 'slack':
                                revoke_response = requests.post(
                                    config['revoke_url'],
                                    headers={'Authorization': f'Bearer {decrypted_access_token}'}
                                )
                            else:  # Google
                                revoke_response = requests.post(
                                    config['revoke_url'],
                                    params={'token': decrypted_access_token}
                                )
                            
                            if revoke_response.status_code == 200:
                                msg = f"Successfully revoked {provider.title()} token ID: {token_entry.id}"
                                log.info(msg)
                                messages.append(msg)
                        except Exception as e:
                            msg = f"Error revoking token {token_entry.id}: {e}"
                            log.error(msg)
                            messages.append(msg)
                            overall_success = False
                    
                    # Delete the token
                    delete_success = OAuthTokens.delete_token_by_id(token_entry.id)
                    if delete_success:
                        msg = f"Successfully deleted token {token_entry.id} (no layers remaining)"
                        log.info(msg)
                        messages.append(msg)
                    else:
                        msg = f"Failed to delete token {token_entry.id}"
                        log.error(msg)
                        messages.append(msg)
                        overall_success = False
                        
            except Exception as e:
                msg = f"Error processing token {token_entry.id}: {e}"
                log.error(msg)
                messages.append(msg)
                overall_success = False

    # Update data source sync status for the specific layer
    data_source_found: Optional[DataSourceModel] = None
    user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
    for ds in user_data_sources:
        if ds.layer == layer:
            data_source_found = ds
            break

    if data_source_found:
        try:
            updated_ds = DataSources.update_data_source_sync_status_by_name(
                user_id=user_id,
                source_name=data_source_found.name,
                layer_name=layer,
                sync_status="unsynced",
                last_sync=int(time.time())
            )
            if updated_ds:
                msg = f"Successfully updated {provider.title()} data source status to 'unsynced' for layer {layer}"
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to update {provider.title()} data source status for layer {layer}"
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error updating {provider.title()} data source status for layer {layer}: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False
    else:
        msg = f"{provider.title()} data source not found for layer {layer}"
        log.warning(msg)
        messages.append(msg)

    # Delete layer-specific data from GCS
    if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
        msg = "GCS configuration missing. Cannot perform GCS data cleanup."
        log.error(msg)
        messages.append(msg)
        overall_success = False
    else:
        try:
            await create_background_delete_task(request, provider, user_id, layer)
            msg = f"Successfully initiated GCS data cleanup for {provider.title()} layer '{layer}'"
            log.info(msg)
            messages.append(msg)
        except Exception as e:
            msg = f"Error during GCS data cleanup for layer '{layer}': {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False

    if overall_success:
        log.info(f"{provider.title()} layer disconnection completed successfully for user: {user_id}, layer: {layer}")
        return {"message": f"{provider.title()} layer '{layer}' disconnected successfully.", "details": messages}
    else:
        log.warning(f"{provider.title()} layer disconnection completed with failures for user: {user_id}, layer: {layer}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Failed to fully disconnect {provider.title()} layer '{layer}'.", "details": messages}
        )

############################
# Create All Provider Endpoints
############################

# Create endpoints for all providers
for provider in ['google', 'microsoft', 'slack', 'atlassian']:
    create_universal_initialize_endpoint(provider)
    create_universal_callback_endpoint(provider)
    create_universal_status_endpoint(provider)
    create_universal_sync_endpoint(provider)
    create_universal_disconnect_endpoint(provider)