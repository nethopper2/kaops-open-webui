from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import requests
import os
import logging
from typing import Optional, List

from open_webui.env import SRC_LOG_LEVELS
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_permission
from open_webui.models.users import Users
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

# Import the slack sync utility
from open_webui.utils.data.slack import initiate_slack_sync
from pydantic import BaseModel

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

router = APIRouter()

# Load from .env
CLIENT_ID = "1724632365717.8888278324853"
CLIENT_SECRET = "7e2f6f13d7508f058cd29d96db49bdcb"
REDIRECT_URI = "https://improved-ape-composed.ngrok-free.app/api/v1/data/slack/callback"
GCS_BUCKET_NAME = "nh-private-ai-file-sync-test"
GCS_SERVICE_ACCOUNT_BASE64 = "ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAibmgtc2FuZGJveC00NTEzMDkiLAogICJwcml2YXRlX2tleV9pZCI6ICJlZmU2OGIyZjU4OTdiZTI2MzliODhkNmI3NDIxYTZlMjMwY2I5ODkwIiwKICAicHJpdmF0ZV9rZXkiOiAiLS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tXG5NSUlFdlFJQkFEQU5CZ2txaGtpRzl3MEJBUUVGQUFTQ0JLY3dnZ1NqQWdFQUFvSUJBUURyK1NPR3FwckR4NUtwXG5YZ0hSdnZvYmJRUjlINWVqaENXYVlOUy9WalpQNFFvZlk5ZXhyaG5qSkNwVnBtbXFLVjBoOURnN2tkazhOQ1BtXG5pM1JQRW5QWUYyc1Z6dDZkb0d1VmVRTlcwNGxHOUJWWGdvUFI1emRiRlZpdjY3WTRyRUt5Umt3S3YyQlJnaXUrXG5hSHBXQTRsUFJkaGplSUVZL3NjZHBnL0J5K1JpNkgzNVRnZ3dzdGpRd2V4TUp6eCsrL1dUaStrSnhSK3crTGY1XG5SSnZtbnpSWFBOOUQ2Z1FvUFhraXZUUHJUa3o2WWxmZVVaS0FBV1lQS204UmFRZUZQcTdSWVUxNCtiTld6a2dTXG5NTkpleTVhVVhQNUxjZmhaTjFKcWkzTHNaV3JnYjR5cFBmUkxGTkNRMGgzUmVKSXVLbzdzMndZbzQ5V3ZhQ1JXXG5xSmNKVEc5SkFnTUJBQUVDZ2dFQUl3R0xhK1dndm5UN2xKMFJ5NFlYajl5Qkd6ZkYxTmZjaFRXaXNmek40MVU0XG4zWFhBRUllSnB4amRIK1luVER0RktlMlRMd0VndHkzcituNUxJNVRTOHlac09DaS9mU1pJZDN6amlpeW84NG52XG5wWk1DejYrTGxudEk5QllWYXZ4aEM1WGluNENLL3lSK3JVbE9CcmNSRmwyLzcyZTN6UmUwdmJqK0l1dUdwc1phXG5PNFdXbTJyTE51dU9QZ3d6eDBvdzNldjdXUktRanIxMUhlQnZXa0ZxbW9xQ2F5Zkg4WmxTQ2NvbzE2bHcrd0UrXG5YSlZEc1NnTEc3MWl2Y3pUTUl3UWl5YkJSOFhuUUVXNm1OcTVzSWRxSFZJSW1BTXgrQWQyOUZUQ2JvMFpSL3JmXG5RUS8vT3VjSVE4QkUxVHhDZ3ZmZ1Y3RFlSdnZjcW54YXJwc0djK2lobFFLQmdRRCtzMHpJaTFTeWJvWWttYlpnXG5DUDVqYVIvS0JkQjczNG9rZWdCQlBTTk5YTXhGRWgrZDJ1S2ZyMnhFUThqRHRDT1k2VkxZb1plc0FKaEljTksxXG40VnhMbmlFSWpyK082VnpoTU1nbkd2LzB2TVROb3lMUW9QRk14WGFiSHIxYisrTWhpVUJGS01pNTM0V2g5UmlyXG5pQ3hPTDdrcWNNSUdsYnhhQmRRRFF3cXBSUUtCZ1FEdExXQnB6eFJKZWxBaFFxcHRGRmtibDdpZ1dvZGhrU1MvXG5MMnB6RjYvUmQzaW5lVzBvWGc0ZmNXQW05aVZxbk9wWjBxWW5QcWVMdTR4ZGRSc1U5Tk9veUIwMFI0VldZVXFsXG5RNHp0RmlXMVBmL3pkbEZ1N1ZPTTJ1cTB0V2s4YVRpNWc5OVEvU1ppWTBQUmtBejlmYzdTYWsxVFdvdjVHbEROXG44YVoyZ2tZVU5RS0JnQXFvQ2RCaU0vcjdNTldiTU13MzFCem9xeEhTeUhSR1dBdEtwM1FUVU1UTjJ5WVFxZzM2XG51SHloNUUrKzNrbUI0Zk5sMzdkOG0xSHcvRzRiZWxWdHhtVExpdXBHdnJFR0JvTE5mYkpWS054ZWdZVnhDK1hhXG50ZjNXVFM0VVRTdnFFQWk1SzEwNVpaeVJRNUFSSnlVV0gzUnQvcnROMkhCYUYzVlV4UmdWMS81WkFvR0FES015XG5VL0Q0djhHSXEzMEYzN0lKM1hLRUgrY3k5M3ZvWFZlRmNJUitsY2FyNHlDUk5HbHVqelpYVFR3b1dqbnFNc2NLXG5tMlMzUUxiSmorRkJoQ2hYYnRMYTI0SkVGSW95bEFPNWFwaVhnY1MvOHBVSFdjWERnZW5ZUDdDNjNzRXNpSllDXG5QQ3FBOVJVYzgvbWM5NVRRaEYydHFSZFdCZnZrK2xRNTdtNmFsVkVDZ1lFQXQ3UGtmUnhPWFR6cFVEWFBpdklOXG5zVWpjcFU4TVVSK0VqUW1QV1F3V1ZyTWJhWEpQanVRY3ZOTGlNQWhtRlQrSHphU2tCMFhFRktGZExuQ1FxV1lMXG5LcE90S1lldUJBb0picEx4NFFxRjBoZU5OdXZMNHYyQTVkeGVEQTVlNHpkcnl0bzVqQWN3TDAyTDFPdTJKVzY0XG5pb05wUFJpNHl0VjI0UUNOdENpL1dRQT1cbi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS1cbiIsCiAgImNsaWVudF9lbWFpbCI6ICJnZHJpdmUtZ2NzLXN5bmNAbmgtc2FuZGJveC00NTEzMDkuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJjbGllbnRfaWQiOiAiMTEyNTU0OTg2NzUzMDIyMDQ0NTk5IiwKICAiYXV0aF91cmkiOiAiaHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL28vb2F1dGgyL2F1dGgiLAogICJ0b2tlbl91cmkiOiAiaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW4iLAogICJhdXRoX3Byb3ZpZGVyX3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vb2F1dGgyL3YxL2NlcnRzIiwKICAiY2xpZW50X3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vcm9ib3QvdjEvbWV0YWRhdGEveDUwOS9nZHJpdmUtZ2NzLXN5bmMlNDBuaC1zYW5kYm94LTQ1MTMwOS5pYW0uZ3NlcnZpY2VhY2NvdW50LmNvbSIsCiAgInVuaXZlcnNlX2RvbWFpbiI6ICJnb29nbGVhcGlzLmNvbSIKfQo="


SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
SLACK_API_BASE = "https://slack.com/api"
SLACK_AUTH_REVOKE_URL = "https://slack.com/api/auth.revoke"

oauth_state_store = {}

############################
# Get Data Sources
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
                sync_status=ds.sync_status,
                last_sync=ds.last_sync,
                icon=ds.icon,
                action=ds.action,
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

############################
# Create Data Source
############################

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

############################
# Initialize Default Data Sources
############################

@router.post("/sources/initialize")
def initialize_default_data_sources(user=Depends(get_verified_user)):
    """Initialize default data sources for a user (typically called on signup)"""
    try:
        # Check if user already has data sources
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

############################
# Get Data Source By Id
############################

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

############################
# Update Data Source By Id
############################

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

############################
# Update Sync Status
############################

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
            updated_data_source = DataSources.update_data_source_sync_status(
                id, form_data.sync_status, form_data.last_sync
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

############################
# Delete Data Source By Id
############################

@router.delete("/source/{id}")
async def delete_data_source_by_id(
    request: Request, id: str, user=Depends(get_verified_user)
):
    """Delete a data source by ID"""
    # Check permissions (similar to folder deletion)
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
# Slack Endpoints 
############################

@router.get("/slack/initialize")
def get_slack_auth_url(user=Depends(get_verified_user)):
    """Generate Slack OAuth URL for the current authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Bot scopes - these will be granted to our app
    bot_scopes = [
        "channels:history",    # Read messages in public channels
        "groups:history",      # Read messages in private channels
        "im:history",          # Read direct messages
        "mpim:history",        # Read group direct messages
        "files:read",          # Access file information
        "users:read",          # Get user information
        "channels:read",       # List public channels
        "groups:read",         # List private channels
        "im:read",             # List direct messages
        "mpim:read",           # List group direct messages
    ]
    
    # User scopes - these will be granted to the user token
    # These are the same permissions but acting as the user
    user_scopes = [
        "channels:history",
        "groups:history", 
        "im:history",
        "mpim:history",
        "files:read",
        "users:read",
        "channels:read",
        "groups:read",
        "im:read",
        "mpim:read",
    ]
    
    bot_scope_str = ",".join(bot_scopes)
    user_scope_str = ",".join(user_scopes)
    
    # Use user ID as state parameter for security
    state = user.id
    oauth_state_store[state] = user.id  # Store for validation in callback
    
    auth_url = (
        f"{SLACK_AUTHORIZE_URL}"
        f"?client_id={CLIENT_ID}"
        f"&scope={bot_scope_str}"
        f"&user_scope={user_scope_str}"  # This is the key addition
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
    )

    return {
        "url": auth_url,
        "user_id": user.id,
        "bot_scopes": bot_scopes,
        "user_scopes": user_scopes
    }


@router.get("/slack/callback")
def slack_callback(request: Request):
    """Handle Slack OAuth callback and initiate sync process."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        log.error(f"Slack OAuth error: {error}")
        return Response(status_code=400, content=f"Slack OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing Slack OAuth code.")
    
    if not state or state not in oauth_state_store:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state.")
    
    user_id = oauth_state_store.pop(state)  # Remove state after use
    
    try:
        # Exchange code for access token
        response = requests.post(
            SLACK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get("ok"):
            raise HTTPException(status_code=400, detail=f"Slack OAuth failed: {data.get('error')}")

        log.info(f"Slack OAuth successful for user {user_id}")

        # Extract tokens and relevant Slack metadata
        # The top-level `access_token` is usually the bot token.
        # `authed_user.access_token` is the user token (if 'users:read', 'channels:read', etc. scopes were requested).
        # For full user data access, `authed_user.access_token` is typically what you need.
        bot_access_token = data.get("access_token")
        user_access_token = data.get("authed_user", {}).get("access_token")
        refresh_token = data.get("refresh_token") # Crucial for long-term access
        expires_in = data.get("expires_in") # Time until access_token expires (in seconds)
        team_id = data.get("team", {}).get("id")
        slack_user_id = data.get("authed_user", {}).get("id")
        granted_scopes = data.get("scope") # Comma-separated string of granted scopes

        if not bot_access_token and not user_access_token:
            raise HTTPException(
                status_code=500,
                detail="No valid token received from Slack OAuth. Ensure necessary scopes are requested."
            )
        
        # Decide which token to store as the primary 'access_token' for syncing.
        # For downloading conversations, the user's token (`authed_user.access_token`) is necessary.
        # We will store the user's access token as `encrypted_access_token` in the DB.
        # The bot token can be stored if needed for other app functionalities, perhaps in a separate token entry
        # or as a secondary field if your schema supports it. For simplicity, we prioritize the user token for sync.
        primary_access_token_for_storage = user_access_token if user_access_token else bot_access_token
        
        if not primary_access_token_for_storage:
             raise HTTPException(
                status_code=500,
                detail="Failed to retrieve a primary token for storage. Ensure user-level scopes are requested."
            )

        # Encrypt tokens before storing
        encrypted_primary_access_token = encrypt_data(primary_access_token_for_storage)
        encrypted_refresh_token = encrypt_data(refresh_token) if refresh_token else None

        # Calculate expiration time for access token
        access_token_expires_at = None
        if expires_in:
            access_token_expires_at = int(time.time()) + expires_in

        # Store tokens in the database using the new OAuthTokens class
        try:
            # We use the insert_new_token method which handles update-or-insert logic
            OAuthTokens.insert_new_token(
                user_id=user_id,
                provider_name="Slack",
                provider_user_id=slack_user_id,
                provider_team_id=team_id,
                encrypted_access_token=encrypted_primary_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                access_token_expires_at=access_token_expires_at,
                scopes=granted_scopes,
                # data_source_id=None, # You could link this to a specific data_source entry if applicable
            )
            log.info(f"Stored/Updated Slack OAuth tokens for user {user_id}, team {team_id}")

        except Exception as db_error:
            log.error(f"Failed to store Slack OAuth tokens in DB for user {user_id}: {db_error}")
            raise HTTPException(status_code=500, detail="Failed to store Slack tokens securely.")

        # Validate required environment variables for sync (still needed)
        if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
            raise HTTPException(
                status_code=500, 
                detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
            )

        # Initiate the sync process with the *decrypted* sync token
        # The immediate sync uses the token directly from the OAuth response.
        # Future syncs will fetch from DB and decrypt.
        sync_token_for_immediate_use = user_access_token if user_access_token else bot_access_token
        if not sync_token_for_immediate_use:
             raise HTTPException(
                status_code=500,
                detail="No suitable token for immediate sync."
            )

        # Initiate the sync process
        try:
            log.info(f"Starting Slack sync for user {user_id} with {'user' if user_access_token else 'bot'} token (retrieved from OAuth response)")
            
            initiate_slack_sync(
                user_id=user_id,
                token=sync_token_for_immediate_use,
                creds=GCS_SERVICE_ACCOUNT_BASE64,
                gcs_bucket_name=GCS_BUCKET_NAME
            )

            update_data_source_sync_status(user_id, 'slack', 'syncing')
            
            return {
                "message": "Slack data sync initiated successfully.",
                "user_id": user_id,
                "team_name": data.get("team", {}).get("name", "Unknown"),
                "slack_user_id": slack_user_id,
                "token_type": "user" if user_access_token else "bot",
                "bot_token_available": bool(bot_access_token),
                "user_token_available": bool(user_access_token),
                "status": "success"
            }
            
        except Exception as sync_error:
            log.error(f"Slack sync failed for user {user_id}: {str(sync_error)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Slack sync failed: {str(sync_error)}"
            )
    
    except requests.exceptions.RequestException as e:
        log.error(f"Slack API Request Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            log.error(f"Response: {e.response.text}")
        raise HTTPException(status_code=500, detail="Failed to authenticate with Slack")


@router.get("/slack/status")
def get_slack_status(user=Depends(get_verified_user)):
    """Get current user's Slack integration status."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Check if required environment variables are configured
    config_status = {
        "gcs_bucket_configured": bool(GCS_BUCKET_NAME),
        "gcs_credentials_configured": bool(GCS_SERVICE_ACCOUNT_BASE64),
        "slack_client_configured": bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI),
    }
    
    return {
        "user_id": user.id,
        "configuration": config_status,
        "ready_for_sync": all(config_status.values())
    }


@router.post("/slack/sync")
def manual_slack_sync(
    user=Depends(get_verified_user),
):
    """Manually trigger Slack sync for the authenticated user, fetching tokens from DB."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    current_time = int(time.time())

    # 1. Fetch encrypted tokens for the user and Slack provider
    # Fetch the most recently updated Slack token associated with the user
    token_entry = OAuthTokens.get_token_by_user_provider_details(
        user_id=user.id,
        provider_name="slack"
        # If a user can connect multiple Slack workspaces, you'd need a way
        # to identify which specific team/workspace token to use, e.g., via a query parameter.
        # For now, we fetch the "primary" one (most recently updated).
    )

    if not token_entry:
        raise HTTPException(
            status_code=404, 
            detail="No Slack integration found for this user. Please authorize your Slack app first."
        )

    # 2. Decrypt tokens
    try:
        decrypted_access_token = decrypt_data(token_entry.encrypted_access_token)
        decrypted_refresh_token = decrypt_data(token_entry.encrypted_refresh_token) if token_entry.encrypted_refresh_token else None
        
        sync_token = decrypted_access_token # This is the token we'll use for Slack API calls

    except Exception as e:
        log.error(f"Failed to decrypt tokens for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt Slack tokens. Please try re-authorizing.")

    # 3. Check token expiration and refresh if necessary
    refresh_needed = False
    if token_entry.access_token_expires_at:
        if (token_entry.access_token_expires_at - current_time) < (5 * 60): # 5-minute grace period
            refresh_needed = True
            log.info(f"Access token for user {user.id} nearing expiration. Initiating refresh.")
    elif decrypted_refresh_token: # If no explicit expiration, but refresh token exists, assume rotation
        log.info(f"Access token for user {user.id} has no explicit expiry but a refresh token exists. Will attempt refresh if initial API call fails.")
        # We will handle refresh reactively if the initial API call with `sync_token` fails.
        # This is a common and often simpler strategy than purely proactive refreshing.
    
    if refresh_needed and decrypted_refresh_token:
        try:
            log.info(f"Attempting to refresh Slack token for user {user.id}")
            refresh_response = requests.post(
                SLACK_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": decrypted_refresh_token,
                },
            )
            refresh_response.raise_for_status()
            refresh_data = refresh_response.json()

            if not refresh_data.get("ok"):
                log.error(f"Slack token refresh failed for user {user.id}: {refresh_data.get('error')}")
                raise HTTPException(status_code=400, detail=f"Failed to refresh Slack token: {refresh_data.get('error')}")
            
            # Get new tokens and update expiration
            new_access_token = refresh_data.get("access_token")
            new_refresh_token = refresh_data.get("refresh_token")
            new_expires_in = refresh_data.get("expires_in")

            if not new_access_token:
                raise HTTPException(status_code=500, detail="No new access token received after refresh.")

            # Encrypt new tokens
            encrypted_new_access_token = encrypt_data(new_access_token)
            encrypted_new_refresh_token = encrypt_data(new_refresh_token) if new_refresh_token else None
            new_access_token_expires_at = int(time.time()) + new_expires_in if new_expires_in else None

            # Update database with new tokens
            updated_token_entry = OAuthTokens.update_token_by_id(
                token_id=token_entry.id,
                encrypted_access_token=encrypted_new_access_token,
                encrypted_refresh_token=encrypted_new_refresh_token,
                access_token_expires_at=new_access_token_expires_at,
                scopes=refresh_data.get("scope", token_entry.scopes) # Update scopes if refresh response includes them
            )
            
            if not updated_token_entry:
                raise HTTPException(status_code=500, detail="Failed to update refreshed Slack tokens in database.")

            log.info(f"Successfully refreshed and updated Slack tokens for user {user.id}")
            sync_token = new_access_token # Use the newly acquired access token for sync

        except requests.exceptions.RequestException as e:
            log.error(f"Slack API Request Error during token refresh for user {user.id}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Refresh response: {e.response.text}")
            raise HTTPException(status_code=500, detail="Failed to refresh Slack token with provider.")
        except Exception as e:
            log.error(f"An error occurred during Slack token refresh for user {user.id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal server error occurred during token refresh.")
    elif refresh_needed and not decrypted_refresh_token:
        log.warning(f"Access token for user {user.id} nearing expiration but no refresh token available. User may need to re-authorize.")
        raise HTTPException(
            status_code=401, 
            detail="Slack token is expired and cannot be refreshed. Please re-authorize your Slack integration."
        )

    # 4. Validate required environment variables for sync (still needed)
    if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
        raise HTTPException(
            status_code=500, 
            detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
        )
    
    try:
        log.info(f"Starting scheduled/manual Slack sync for user {user.id}")

        initiate_slack_sync(
            user_id=user.id,
            token=sync_token, # Use the valid (or freshly refreshed) token
            creds=GCS_SERVICE_ACCOUNT_BASE64,
            gcs_bucket_name=GCS_BUCKET_NAME
        )

        update_data_source_sync_status(user.id, 'slack', 'syncing')
        
        return {
            "message": "Slack data sync initiated successfully.",
            "user_id": user.id,
            "status": "success"
        }
        
    except Exception as sync_error:
        log.error(f"Slack sync failed for user {user.id}: {str(sync_error)}")
        if "invalid_auth" in str(sync_error).lower(): # Simple check, refine based on actual error messages
            log.warning(f"Slack sync for user {user.id} failed due to invalid token. User may need to re-authorize.")
            # Consider deleting the invalid token from the DB here if it's consistently failing.
            # OAuthTokens.delete_token_by_id(token_entry.id)
            raise HTTPException(
                status_code=401, 
                detail="Slack token invalid or expired. Please re-authorize your Slack integration."
            )
        raise HTTPException(
            status_code=500, 
            detail=f"Slack sync failed: {str(sync_error)}"
        )

@router.delete("/slack/disconnect")
async def disconnect_slack(user=Depends(get_verified_user),
    slack_team_id: Optional[str] = None
):
    """
    Disconnects a user's Slack integration, revoking tokens, deleting credentials,
    cleaning up GCS files and updating the data source sync status.

    Args:
        user: The authenticated user object.
        slack_team_id (Optional[str]): If provided, only attempts to disconnect the Slack
                                       integration for this specific team ID.

    Returns:
        JSONResponse: A message indicating success or failure.
    """
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = user.id
    log.info(f"Initiating Slack integration disconnection for user: {user_id}"
             f"{f' (Team ID: {slack_team_id})' if slack_team_id else ''}"
             f", GCS cleanup")

    overall_success = True
    messages = []

    # --- Step 1: Fetch and Revoke Slack Token(s) ---
    slack_tokens_to_revoke: List[OAuthTokenModel] = []
    if slack_team_id:
        token_entry = OAuthTokens.get_token_by_user_provider_details(
            user_id=user_id,
            provider_name="Slack",
            provider_team_id=slack_team_id
        )
        if token_entry:
            slack_tokens_to_revoke.append(token_entry)
    else:
        all_user_tokens = OAuthTokens.get_all_tokens_for_user(user_id=user_id)
        slack_tokens_to_revoke = [
            token for token in all_user_tokens if token.provider_name == "Slack"
        ]

    if not slack_tokens_to_revoke:
        msg = f"No Slack tokens found for user {user_id}{f' (Team ID: {slack_team_id})' if slack_team_id else ''}. Skipping token revocation."
        log.warning(msg)
        messages.append(msg)
    else:
        for token_entry in slack_tokens_to_revoke:
            try:
                decrypted_access_token = decrypt_data(token_entry.encrypted_access_token)
                
                log.info(f"Attempting to revoke Slack token for user {user_id}, "
                         f"ID: {token_entry.id}, Team ID: {token_entry.provider_team_id}")
                
                revoke_response = requests.post(
                    SLACK_AUTH_REVOKE_URL,
                    headers={'Authorization': f'Bearer {decrypted_access_token}'}
                )
                revoke_response.raise_for_status()
                revoke_data = revoke_response.json()

                if revoke_data.get("ok"):
                    msg = f"Successfully revoked Slack token ID: {token_entry.id} for user {user_id}"
                    log.info(msg)
                    messages.append(msg)
                else:
                    msg = (f"Failed to revoke Slack token ID: {token_entry.id} for user {user_id}. "
                           f"Slack API Error: {revoke_data.get('error')}")
                    log.warning(msg)
                    messages.append(msg)
            except Exception as e:
                msg = (f"Error during Slack token revocation for user {user_id}, "
                       f"token ID: {token_entry.id}: {e}")
                log.error(msg)
                messages.append(msg)
                overall_success = False

    # --- Step 2: Remove stored Slack credentials (OAuthToken entry) from DB ---
    try:
        if slack_team_id:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="Slack",
                provider_team_id=slack_team_id
            )
        else:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="slack"
            )

        if db_delete_success:
            msg = f"Successfully deleted Slack OAuth token(s) from DB for user {user_id}{f' (Team ID: {slack_team_id})' if slack_team_id else ''}."
            log.info(msg)
            messages.append(msg)
        else:
            msg = f"Failed to delete Slack OAuth token(s) from DB for user {user_id}{f' (Team ID: {slack_team_id})' if slack_team_id else ''}. It might have already been deleted or not found."
            log.error(msg)
            messages.append(msg)
    except Exception as e:
        msg = f"Error deleting Slack OAuth token(s) from DB for user {user_id}: {e}"
        log.exception(msg)
        messages.append(msg)
        overall_success = False

    # --- Step 3: Update Slack Data Source Sync Status ---
    # Find the data source by its 'action' ("slack") to get its 'name'
    slack_data_source_found: Optional[DataSourceModel] = None
    user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
    for ds in user_data_sources:
        if ds.action == "slack": 
            slack_data_source_found = ds
            break

    if slack_data_source_found:
        try:
            updated_ds = DataSources.update_data_source_sync_status_by_name(
                user_id=user_id,
                source_name=slack_data_source_found.name,
                sync_status="unsynced", # Set to a specific "disconnected" status
                last_sync=int(time.time()) # Update last sync time to now
            )
            if updated_ds:
                msg = f"Successfully updated Slack data source status to 'unsynced' for user {user_id} (Data Source Name: {updated_ds.name})."
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to update Slack data source status to 'unsynced' for user {user_id} (Data Source Name: {slack_data_source_found.name})."
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error updating Slack data source status for user {user_id}: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False
    else:
        msg = f"Slack data source not found for user {user_id}. Cannot update sync status."
        log.warning(msg)
        messages.append(msg)

    # --- Step 4: Delete user data from GCS Bucket ---
    if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
        msg = ("GCS configuration missing (GCS_BUCKET_NAME or GCS_SERVICE_ACCOUNT_BASE64). "
                "Cannot perform GCS data cleanup as requested.")
        log.error(msg)
        messages.append(msg)
        overall_success = False
    else:
        slack_folder_path = f"{user_id}/Slack/"
        try:
            gcs_cleanup_success =  await delete_gcs_folder( 
                folder_path=slack_folder_path,
                service_account_base64=GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME=GCS_BUCKET_NAME
            )
            if gcs_cleanup_success:
                msg = f"Successfully initiated GCS data cleanup for user {user_id}'s Slack folder."
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to delete GCS data for user {user_id}'s Slack folder."
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error during GCS data cleanup for user {user_id}'s Slack folder: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False
    

    if overall_success:
        log.info(f"Slack integration disconnection process completed successfully for user: {user_id}")
        return {"message": "Slack integration disconnected successfully.", "details": messages}
    else:
        log.warning(f"Slack integration disconnection process completed with some failures for user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to fully disconnect Slack integration. See details.", "details": messages}
        )