from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse
import requests
import os
import logging
import jwt
from typing import Optional, List

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


# Import the slack sync utility
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

    GCS_BUCKET_NAME,
    GCS_SERVICE_ACCOUNT_BASE64,
    DATASOURCES_URL
)

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
# Google Endpoints 
############################

@router.get("/google/initialize")
def get_google_auth_url(user=Depends(get_verified_user)):
    """Generate Google OAuth URL for the current authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Google scopes - choose the necessary ones for the data you want to access.
    # For read-only access to common user data:
    google_scopes = [
        "https://www.googleapis.com/auth/userinfo.profile", # Basic profile info
        "https://www.googleapis.com/auth/drive.readonly",   # Read-only Google Drive files
        "https://www.googleapis.com/auth/gmail.readonly" # Read-only Gmail messages
    ]

    scope_str = " ".join(google_scopes) # Google scopes are space-separated

    # Use user ID as state parameter for security
    state = user.id
    oauth_state_store[state] = user.id  # Store for validation in callback

    auth_url = (
        f"{GOOGLE_AUTHORIZE_URL}"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"  # Always 'code' for web server apps
        f"&scope={scope_str}"
        f"&access_type=offline" # Crucial to get a refresh_token
        f"&prompt=consent"      # Ensures refresh token is always granted, even if previously authorized
        f"&state={state}"
    )

    return {
        "url": auth_url,
        "user_id": user.id,
        "scopes": google_scopes
    }

@router.get("/google/callback")
async def google_callback(request: Request, background_tasks: BackgroundTasks):
    """Handle Google OAuth callback and initiate sync process."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        log.error(f"Google OAuth error: {error}")
        return Response(status_code=400, content=f"Google OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing Google OAuth code.")

    if not state or state not in oauth_state_store:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state.")

    user_id = oauth_state_store.pop(state)  # Remove state after use

    try:
        # Exchange code for access token
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise HTTPException(status_code=400, detail=f"Google OAuth failed: {data.get('error_description', data.get('error'))}")

        log.info(f"Google OAuth successful for user {user_id}")

        # Extract tokens and relevant Google metadata
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token") # Only present if access_type=offline and prompt=consent were used, and it's the first time
        expires_in = data.get("expires_in") # Time until access_token expires (in seconds)
        id_token = data.get("id_token") # Contains user info if 'openid' scope requested
        
        # You might need to decode the id_token to get the Google User ID (sub field)
        # For simplicity, we'll assume a direct 'user_id' can be derived or use a placeholder
        # In a real app, you'd use a JWT library (e.g., python-jose) to decode id_token
        google_user_id = None
        if id_token:
            # This is a basic mock. In production, properly decode and verify the JWT.
            try:
                decoded_id_token = jwt.decode(id_token, options={"verify_signature": False}) # DO NOT USE IN PROD WITHOUT VERIFICATION
                google_user_id = decoded_id_token.get("sub") # 'sub' is the Google user ID
            except ImportError:
                log.warning("PyJWT not installed. Cannot decode id_token to get Google User ID.")
            except Exception as e:
                log.error(f"Failed to decode id_token: {e}")

        
        if not access_token:
            raise HTTPException(
                status_code=500,
                detail="No access token received from Google OAuth. Ensure necessary scopes are requested."
            )

        # Encrypt tokens before storing
        encrypted_access_token = encrypt_data(access_token)
        encrypted_refresh_token = encrypt_data(refresh_token) if refresh_token else None

        # Calculate expiration time for access token
        access_token_expires_at = None
        if expires_in:
            access_token_expires_at = int(time.time()) + expires_in

        # Store tokens in the database
        try:
            # We use the insert_new_token method which handles update-or-insert logic
            OAuthTokens.insert_new_token(
                user_id=user_id,
                provider_name="Google",
                provider_user_id=google_user_id,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                access_token_expires_at=access_token_expires_at,
                scopes=data.get("scope"), # Space-separated string of granted scopes
            )
            log.info(f"Stored/Updated Google OAuth tokens for user {user_id}")

        except Exception as db_error:
            log.error(f"Failed to store Google OAuth tokens in DB for user {user_id}: {db_error}")
            raise HTTPException(status_code=500, detail="Failed to store Google tokens securely.")

        # Validate required environment variables for sync
        if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
            raise HTTPException(
                status_code=500,
                detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
            )

        # Initiate the sync process with the *decrypted* access token
        try:
            log.info(f"Starting Google sync for user {user_id} with token (retrieved from OAuth response)")

            # Add the task to the background tasks to sync user Google data
            background_tasks.add_task(
                initiate_google_file_sync,
                user_id,
                access_token, # Use the token directly from the response
                GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME
            )

            background_tasks.add_task(
                update_data_source_sync_status,
                'google', 
                'syncing'
            )

            return RedirectResponse(
                url=DATASOURCES_URL,
                status_code=302
            )
            

        except Exception as sync_error:
            log.error(f"Google sync failed for user {user_id}: {str(sync_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Google sync failed: {str(sync_error)}"
            )

    except requests.exceptions.RequestException as e:
        log.error(f"Google API Request Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            log.error(f"Response: {e.response.text}")
        raise HTTPException(status_code=500, detail="Failed to authenticate with Google")

@router.get("/google/status")
def get_google_status(user=Depends(get_verified_user)):
    """Get current user's Google integration status."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Check if required environment variables are configured
    config_status = {
        "gcs_bucket_configured": bool(GCS_BUCKET_NAME),
        "gcs_credentials_configured": bool(GCS_SERVICE_ACCOUNT_BASE64),
        "google_client_configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI),
    }

    # Check if a Google token exists for the user
    google_token_exists = OAuthTokens.get_token_by_user_provider_details(user_id=user.id, provider_name="Google")
    
    # Check current sync status from data sources
    sync_status = "not_connected"
    user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
    for ds in user_data_sources:
        if ds.action == "google":
            sync_status = ds.sync_status
            break

    return {
        "user_id": user.id,
        "configuration": config_status,
        "google_token_present": bool(google_token_exists),
        "current_sync_status": sync_status,
        "ready_for_sync": all(config_status.values()) and bool(google_token_exists) and sync_status != "syncing"
    }

@router.post("/google/sync")
async def manual_google_sync(
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
):
    """Manually trigger Google sync for the authenticated user, fetching tokens from DB."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Check if Slack sync is already in progress
    user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
    google_data_source = None
    
    for ds in user_data_sources:
        if ds.action == 'google':
            google_data_source = ds
            break
    
    if google_data_source and google_data_source.sync_status == 'syncing':
        return

    current_time = int(time.time())

    # 1. Fetch encrypted tokens for the user and Google provider
    token_entry = OAuthTokens.get_token_by_user_provider_details(
        user_id=user.id,
        provider_name="Google"
        # If a user can connect multiple Google accounts, you'd need a way
        # to identify which specific account token to use, e.g., via a query parameter.
    )

    if not token_entry:
        raise HTTPException(
            status_code=404,
            detail="No Google integration found for this user. Please authorize your Google app first."
        )

    # 2. Decrypt tokens
    try:
        decrypted_access_token = decrypt_data(token_entry.encrypted_access_token)
        decrypted_refresh_token = decrypt_data(token_entry.encrypted_refresh_token) if token_entry.encrypted_refresh_token else None

        sync_token = decrypted_access_token # This is the token we'll use for Google API calls

    except Exception as e:
        log.error(f"Failed to decrypt tokens for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt Google tokens. Please try re-authorizing.")

    # 3. Check token expiration and refresh if necessary
    refresh_needed = False
    if token_entry.access_token_expires_at:
        # Check if less than 5 minutes until expiration
        if (token_entry.access_token_expires_at - current_time) < (5 * 60):
            refresh_needed = True
            log.info(f"Access token for user {user.id} nearing expiration. Initiating refresh.")
    elif decrypted_refresh_token:
        # If no explicit expiration, but refresh token exists, assume proactive refresh is best practice
        # or handle reactively if API call fails. Here, we proactively try to refresh.
        log.info(f"Access token for user {user.id} has no explicit expiry but a refresh token exists. Will attempt refresh.")
        refresh_needed = True


    if refresh_needed and decrypted_refresh_token:
        try:
            log.info(f"Attempting to refresh Google token for user {user.id}")
            refresh_response = requests.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": decrypted_refresh_token,
                },
            )
            refresh_response.raise_for_status()
            refresh_data = refresh_response.json()

            if "error" in refresh_data:
                log.error(f"Google token refresh failed for user {user.id}: {refresh_data.get('error_description', refresh_data.get('error'))}")
                raise HTTPException(status_code=400, detail=f"Failed to refresh Google token: {refresh_data.get('error_description', refresh_data.get('error'))}")

            # Get new tokens and update expiration
            new_access_token = refresh_data.get("access_token")
            # Google often returns a new refresh_token, but sometimes it doesn't.
            # If it doesn't, continue using the old one.
            new_refresh_token = refresh_data.get("refresh_token", decrypted_refresh_token)
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
                raise HTTPException(status_code=500, detail="Failed to update refreshed Google tokens in database.")

            log.info(f"Successfully refreshed and updated Google tokens for user {user.id}")
            sync_token = new_access_token # Use the newly acquired access token for sync

        except requests.exceptions.RequestException as e:
            log.error(f"Google API Request Error during token refresh for user {user.id}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Refresh response: {e.response.text}")
            raise HTTPException(status_code=500, detail="Failed to refresh Google token with provider.")
        except Exception as e:
            log.error(f"An error occurred during Google token refresh for user {user.id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal server error occurred during token refresh.")
    elif refresh_needed and not decrypted_refresh_token:
        log.warning(f"Access token for user {user.id} nearing expiration but no valid refresh token available. Initiating re-authorization flow.")
        
        try:
            # Google scopes - choose the necessary ones for the data you want to access.
            # For read-only access to common user data:
            google_scopes = [
                "https://www.googleapis.com/auth/userinfo.profile", # Basic profile info
                "https://www.googleapis.com/auth/drive.readonly",   # Read-only Google Drive files
                "https://www.googleapis.com/auth/gmail.readonly" # Read-only Gmail messages
            ]

            scope_str = " ".join(google_scopes) # Google scopes are space-separated
            # Generate re-authorization URL for Google OAuth
            google_auth_url = (
                f"https://accounts.google.com/o/oauth2/auth?"
                f"client_id={GOOGLE_CLIENT_ID}&"
                f"redirect_uri={os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/auth/google/callback')}&"
                f"scope={scope_str}&"
                f"response_type=code&"
                f"access_type=offline&"
                f"prompt=consent&"
                f"state={user.id}"  # Include user ID to link back after auth
            )
            
            log.info(f"Generated re-authorization URL for user {user.id}")
            
            # Store re-authorization state (optional - for tracking purposes)
            # You might want to store this in Redis or database temporarily
            # await store_reauth_state(user.id, "google_token_refresh")
            
            # Return structured response with re-authorization URL
            raise HTTPException(
                status_code=201,
                detail={
                    "error": "token_expired_no_refresh",
                    "message": "Google token is expired and no valid refresh token is available. Re-authorization required.",
                    "reauth_url": google_auth_url,
                    "action_required": "redirect_to_google_auth",
                    "user_id": str(user.id),
                    "provider": "google",
                    "reason": "no_refresh_token" if not token_entry.encrypted_refresh_token else "invalid_refresh_token"
                }
            )
            
        except HTTPException:
            # Re-raise HTTPException to maintain the response structure
            raise
        except Exception as e:
            log.error(f"Failed to generate re-authorization URL for user {user.id}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "reauth_generation_failed",
                    "message": "Google token is expired and re-authorization flow could not be initiated. Please manually re-authorize your Google integration.",
                    "user_id": str(user.id)
                }
            )

    # 4. Validate required environment variables for sync
    if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
        raise HTTPException(
            status_code=500,
            detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
        )

    try:
        log.info(f"Starting scheduled/manual Google sync for user {user.id}")

        # Add the task to the background tasks to sync user Google data
        background_tasks.add_task(
            initiate_google_file_sync,
            user.id,
            sync_token, # Use the valid (or freshly refreshed) token
            GCS_SERVICE_ACCOUNT_BASE64,
            GCS_BUCKET_NAME
        )

        await update_data_source_sync_status(user.id, 'google', 'syncing')

        return {
            "message": "Google data sync initiated successfully.",
            "user_id": user.id,
            "status": "success"
        }

    except Exception as sync_error:
        log.error(f"Google sync failed for user {user.id}: {str(sync_error)}")
        if "invalid_grant" in str(sync_error).lower() or "invalid_token" in str(sync_error).lower():
            log.warning(f"Google sync for user {user.id} failed due to invalid token. User may need to re-authorize.")
            # Consider deleting the invalid token from the DB here
            # OAuthTokens.delete_token_by_id(token_entry.id)
            raise HTTPException(
                status_code=401,
                detail="Google token invalid or expired. Please re-authorize your Google integration."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Google sync failed: {str(sync_error)}"
        )

@router.delete("/google/disconnect")
async def disconnect_google(background_tasks: BackgroundTasks, user=Depends(get_verified_user),
    google_team_id: Optional[str] = None
):
    """
    Disconnects a user's Google integration, revoking tokens, deleting credentials,
    cleaning up GCS files and updating the data source sync status.

    Args:
        user: The authenticated user object.
        google_team_id (Optional[str]): If provided, only attempts to disconnect the Google
                                       integration for this specific team ID (e.g., a specific
                                       Google Workspace ID if applicable).

    Returns:
        JSONResponse: A message indicating success or failure.
    """
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = user.id
    log.info(f"Initiating Google integration disconnection for user: {user_id}"
             f"{f' (Team ID: {google_team_id})' if google_team_id else ''}"
             f", GCS cleanup")

    overall_success = True
    messages = []

    # --- Step 1: Fetch and Revoke Google Token(s) ---
    google_tokens_to_revoke: List[OAuthTokenModel] = []
    if google_team_id:
        token_entry = OAuthTokens.get_token_by_user_provider_details(
            user_id=user_id,
            provider_name="Google",
            provider_team_id=google_team_id
        )
        if token_entry:
            google_tokens_to_revoke.append(token_entry)
    else:
        all_user_tokens = OAuthTokens.get_all_tokens_for_user(user_id=user_id)
        google_tokens_to_revoke = [
            token for token in all_user_tokens if token.provider_name == "Google"
        ]

    if not google_tokens_to_revoke:
        msg = f"No Google tokens found for user {user_id}{f' (Team ID: {google_team_id})' if google_team_id else ''}. Skipping token revocation."
        log.warning(msg)
        messages.append(msg)
    else:
        for token_entry in google_tokens_to_revoke:
            try:
                decrypted_access_token = decrypt_data(token_entry.encrypted_access_token)
                
                log.info(f"Attempting to revoke Google token for user {user_id}, "
                         f"ID: {token_entry.id}, Team ID: {token_entry.provider_team_id}")
                
                # Google token revocation typically requires sending the token itself as a parameter
                revoke_response = requests.post(
                    GOOGLE_AUTH_REVOKE_URL,
                    params={'token': decrypted_access_token}
                )
                revoke_response.raise_for_status()
                # Google's revoke endpoint usually returns an empty 200 OK on success
                
                if revoke_response.status_code == 200:
                    msg = f"Successfully revoked Google token ID: {token_entry.id} for user {user_id}"
                    log.info(msg)
                    messages.append(msg)
                else:
                    msg = (f"Failed to revoke Google token ID: {token_entry.id} for user {user_id}. "
                           f"HTTP Status: {revoke_response.status_code}, Response: {revoke_response.text}")
                    log.warning(msg)
                    messages.append(msg)
            except Exception as e:
                msg = (f"Error during Google token revocation for user {user_id}, "
                       f"token ID: {token_entry.id}: {e}")
                log.error(msg)
                messages.append(msg)
                overall_success = False

    # --- Step 2: Remove stored Google credentials (OAuthToken entry) from DB ---
    try:
        if google_team_id:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="Google",
                provider_team_id=google_team_id
            )
        else:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="Google"
            )

        if db_delete_success:
            msg = f"Successfully deleted Google OAuth token(s) from DB for user {user_id}{f' (Team ID: {google_team_id})' if google_team_id else ''}."
            log.info(msg)
            messages.append(msg)
        else:
            msg = f"Failed to delete Google OAuth token(s) from DB for user {user_id}{f' (Team ID: {google_team_id})' if google_team_id else ''}. It might have already been deleted or not found."
            log.error(msg)
            messages.append(msg)
    except Exception as e:
        msg = f"Error deleting Google OAuth token(s) from DB for user {user_id}: {e}"
        log.exception(msg)
        messages.append(msg)
        overall_success = False

    # --- Step 3: Update Google Data Source Sync Status ---
    # Find the data source by its 'action' ("google") to get its 'name'
    google_data_source_found: Optional[DataSourceModel] = None
    user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
    for ds in user_data_sources:
        if ds.action == "google":
            google_data_source_found = ds
            break

    if google_data_source_found:
        try:
            updated_ds = DataSources.update_data_source_sync_status_by_name(
                user_id=user_id,
                source_name=google_data_source_found.name,
                sync_status="unsynced", # Set to a specific "disconnected" status
                last_sync=int(time.time()) # Update last sync time to now
            )
            if updated_ds:
                msg = f"Successfully updated Google data source status to 'unsynced' for user {user_id} (Data Source Name: {updated_ds.name})."
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to update Google data source status to 'unsynced' for user {user_id} (Data Source Name: {google_data_source_found.name})."
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error updating Google data source status for user {user_id}: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False
    else:
        msg = f"Google data source not found for user {user_id}. Cannot update sync status."
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
        google_folder_path = f"userResources/{user_id}/Google Drive/" 
        try:
            background_tasks.add_task(
                delete_gcs_folder,
                google_folder_path,
                GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME
            )

            msg = f"Successfully initiated GCS data cleanup for user {user_id}'s Google folder."
            log.info(msg)
            messages.append(msg)
            
        except Exception as e:
            msg = f"Error during GCS data cleanup for user {user_id}'s Google folder: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False


    if overall_success:
        log.info(f"Google integration disconnection process completed successfully for user: {user_id}")
        return {"message": "Google integration disconnected successfully.", "details": messages}
    else:
        log.warning(f"Google integration disconnection process completed with some failures for user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to fully disconnect Google integration. See details.", "details": messages}
        )


############################
# Microsoft Endpoints 
############################

@router.get("/microsoft/initialize")
def get_microsoft_auth_url(user=Depends(get_verified_user)):
    """Generate Microsoft OAuth URL for the current authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Microsoft Graph scopes.
    microsoft_scopes = [
        "User.Read",              # Read user's profile
        "Files.Read.All",         # Read user's files in OneDrive and SharePoint
        "Sites.Read.All",         # Read user's sites in SharePoint
        "Notes.Read",             # Read user's OneNote notebooks
        "Mail.Read",              # Read user's mail in Outlook
        "MailboxSettings.Read",   # Read user's mailbox settings
        "offline_access"          # Crucial to get a refresh_token
    ]

    scope_str = " ".join(microsoft_scopes) # Microsoft scopes are space-separated

    # Use user ID as state parameter for security
    state = user.id
    oauth_state_store[state] = user.id  # Store for validation in callback

    auth_url = (
        f"{MICROSOFT_AUTHORIZE_URL}"
        f"?client_id={MICROSOFT_CLIENT_ID}"
        f"&redirect_uri={MICROSOFT_REDIRECT_URI}"
        f"&response_type=code"  # Always 'code' for web server apps
        f"&scope={scope_str}"
        f"&response_mode=query" # Or 'form_post' depending on your preference
        f"&state={state}"
    )

    return {
        "url": auth_url,
        "user_id": user.id,
        "scopes": microsoft_scopes
    }

@router.get("/microsoft/callback")
async def microsoft_callback(request: Request, background_tasks: BackgroundTasks):
    """Handle Microsoft OAuth callback and initiate sync process."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description")

    if error:
        log.error(f"Microsoft OAuth error: {error} - {error_description}")
        return Response(status_code=400, content=f"Microsoft OAuth error: {error_description or error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing Microsoft OAuth code.")

    if not state or state not in oauth_state_store:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state.")

    user_id = oauth_state_store.pop(state)  # Remove state after use

    try:
        # Exchange code for access token
        response = requests.post(
            MICROSOFT_TOKEN_URL,
            data={
                "client_id": MICROSOFT_CLIENT_ID,
                "client_secret": MICROSOFT_CLIENT_SECRET,
                "code": code,
                "redirect_uri": MICROSOFT_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise HTTPException(status_code=400, detail=f"Microsoft OAuth failed: {data.get('error_description', data.get('error'))}")

        log.info(f"Microsoft OAuth successful for user {user_id}")

        # Extract tokens and relevant Microsoft metadata
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token") # Only present if offline_access scope was requested
        expires_in = data.get("expires_in") # Time until access_token expires (in seconds)
        id_token = data.get("id_token") # Contains user info if 'openid' scope requested (implied by User.Read)

        microsoft_user_id = None
        if id_token:
            try:
                # Decode the ID token to get the user's object ID or other unique identifier
                # In production, ALWAYS verify the signature and audience of the JWT.
                decoded_id_token = jwt.decode(id_token, options={"verify_signature": False})
                microsoft_user_id = decoded_id_token.get("oid") or decoded_id_token.get("sub") # 'oid' is object ID (immutable), 'sub' is subject (can be user-specific, unique). 'oid' is preferred.
            except ImportError:
                log.warning("PyJWT not installed. Cannot decode id_token to get Microsoft User ID.")
            except Exception as e:
                log.error(f"Failed to decode id_token for Microsoft: {e}")

        if not access_token:
            raise HTTPException(
                status_code=500,
                detail="No access token received from Microsoft OAuth. Ensure necessary scopes are requested."
            )

        # Encrypt tokens before storing
        encrypted_access_token = encrypt_data(access_token)
        encrypted_refresh_token = encrypt_data(refresh_token) if refresh_token else None

        # Calculate expiration time for access token
        access_token_expires_at = None
        if expires_in:
            access_token_expires_at = int(time.time()) + expires_in

        # Store tokens in the database
        try:
            OAuthTokens.insert_new_token(
                user_id=user_id,
                provider_name="Microsoft",
                provider_user_id=microsoft_user_id,
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                access_token_expires_at=access_token_expires_at,
                scopes=data.get("scope"), # Space-separated string of granted scopes
            )
            log.info(f"Stored/Updated Microsoft OAuth tokens for user {user_id}")

        except Exception as db_error:
            log.error(f"Failed to store Microsoft OAuth tokens in DB for user {user_id}: {db_error}")
            raise HTTPException(status_code=500, detail="Failed to store Microsoft tokens securely.")

        # Validate required environment variables for sync (assuming GCS for storage)
        if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
            raise HTTPException(
                status_code=500,
                detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
            )

        # Initiate the sync process with the *decrypted* access token
        try:
            log.info(f"Starting Microsoft sync for user {user_id} with token (retrieved from OAuth response)")

            # Add the task to the background tasks to sync user Microsoft data
            background_tasks.add_task(
                initiate_microsoft_sync,
                user_id,
                access_token, # Use the token directly from the response
                GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME
            )

            background_tasks.add_task(
                update_data_source_sync_status,
                'microsoft', 
                'syncing'
            )

            return RedirectResponse(
                url=DATASOURCES_URL,
                status_code=302
            )

        except Exception as sync_error:
            log.error(f"Microsoft sync failed for user {user_id}: {str(sync_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Microsoft sync failed: {str(sync_error)}"
            )

    except requests.exceptions.RequestException as e:
        log.error(f"Microsoft API Request Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            log.error(f"Response: {e.response.text}")
        raise HTTPException(status_code=500, detail="Failed to authenticate with Microsoft")

@router.get("/microsoft/status")
def get_microsoft_status(user=Depends(get_verified_user)):
    """Get current user's Microsoft integration status."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Check if required environment variables are configured
    config_status = {
        "gcs_bucket_configured": bool(GCS_BUCKET_NAME),
        "gcs_credentials_configured": bool(GCS_SERVICE_ACCOUNT_BASE64),
        "microsoft_client_configured": bool(MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET and MICROSOFT_REDIRECT_URI),
    }

    # Check if a Microsoft token exists for the user
    microsoft_token_exists = OAuthTokens.get_token_by_user_provider_details(user_id=user.id, provider_name="Microsoft")

    # Check current sync status from data sources
    sync_status = "not_connected"
    user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
    for ds in user_data_sources:
        if ds.action == "microsoft":
            sync_status = ds.sync_status
            break

    return {
        "user_id": user.id,
        "configuration": config_status,
        "microsoft_token_present": bool(microsoft_token_exists),
        "current_sync_status": sync_status,
        "ready_for_sync": all(config_status.values()) and bool(microsoft_token_exists) and sync_status != "syncing"
    }

@router.post("/microsoft/sync")
async def manual_microsoft_sync(
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
):
    """Manually trigger Microsoft sync for the authenticated user, fetching tokens from DB."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Check if Slack sync is already in progress
    user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
    microsoft_data_source = None
    
    for ds in user_data_sources:
        if ds.action == 'microsoft':
            microsoft_data_source = ds
            break
    
    if microsoft_data_source and microsoft_data_source.sync_status == 'syncing':
        return

    current_time = int(time.time())

    # 1. Fetch encrypted tokens for the user and Microsoft provider
    token_entry = OAuthTokens.get_token_by_user_provider_details(
        user_id=user.id,
        provider_name="Microsoft"
    )

    if not token_entry:
        raise HTTPException(
            status_code=404,
            detail="No Microsoft integration found for this user. Please authorize your Microsoft app first."
        )

    # 2. Decrypt tokens
    try:
        decrypted_access_token = decrypt_data(token_entry.encrypted_access_token)
        decrypted_refresh_token = decrypt_data(token_entry.encrypted_refresh_token) if token_entry.encrypted_refresh_token else None

        sync_token = decrypted_access_token # This is the token we'll use for Microsoft Graph API calls

    except Exception as e:
        log.error(f"Failed to decrypt tokens for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt Microsoft tokens. Please try re-authorizing.")

    # 3. Check token expiration and refresh if necessary
    refresh_needed = False
    if token_entry.access_token_expires_at:
        # Check if less than 5 minutes until expiration
        if (token_entry.access_token_expires_at - current_time) < (5 * 60):
            refresh_needed = True
            log.info(f"Access token for user {user.id} nearing expiration. Initiating refresh.")
    elif decrypted_refresh_token:
        # If no explicit expiration, but refresh token exists, assume proactive refresh is best practice
        log.info(f"Access token for user {user.id} has no explicit expiry but a refresh token exists. Will attempt refresh.")
        refresh_needed = True


    if refresh_needed and decrypted_refresh_token:
        try:
            log.info(f"Attempting to refresh Microsoft token for user {user.id}")
            refresh_response = requests.post(
                MICROSOFT_TOKEN_URL,
                data={
                    "client_id": MICROSOFT_CLIENT_ID,
                    "client_secret": MICROSOFT_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": decrypted_refresh_token,
                },
            )
            refresh_response.raise_for_status()
            refresh_data = refresh_response.json()

            if "error" in refresh_data:
                log.error(f"Microsoft token refresh failed for user {user.id}: {refresh_data.get('error_description', refresh_data.get('error'))}")
                raise HTTPException(status_code=400, detail=f"Failed to refresh Microsoft token: {refresh_data.get('error_description', refresh_data.get('error'))}")

            # Get new tokens and update expiration
            new_access_token = refresh_data.get("access_token")
            new_refresh_token = refresh_data.get("refresh_token", decrypted_refresh_token) # Microsoft often issues new refresh tokens
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
                scopes=refresh_data.get("scope", token_entry.scopes)
            )

            if not updated_token_entry:
                raise HTTPException(status_code=500, detail="Failed to update refreshed Microsoft tokens in database.")

            log.info(f"Successfully refreshed and updated Microsoft tokens for user {user.id}")
            sync_token = new_access_token # Use the newly acquired access token for sync

        except requests.exceptions.RequestException as e:
            log.error(f"Microsoft API Request Error during token refresh for user {user.id}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Refresh response: {e.response.text}")
            raise HTTPException(status_code=500, detail="Failed to refresh Microsoft token with provider.")
        except Exception as e:
            log.error(f"An error occurred during Microsoft token refresh for user {user.id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An internal server error occurred during token refresh.")
    elif refresh_needed and not decrypted_refresh_token:
        log.warning(f"Access token for user {user.id} nearing expiration but no valid refresh token available. Initiating re-authorization flow.")
        try:
            # Microsoft Graph scopes.
            microsoft_scopes = [
                "User.Read",              # Read user's profile
                "Files.Read.All",         # Read user's files in OneDrive and SharePoint
                "Sites.Read.All",         # Read user's sites in SharePoint
                "Notes.Read",             # Read user's OneNote notebooks
                "Mail.Read",              # Read user's mail in Outlook
                "MailboxSettings.Read",   # Read user's mailbox settings
                "offline_access"          # Crucial to get a refresh_token
            ]

            scope_str = " ".join(microsoft_scopes) # Microsoft scopes are space-separated
            # Generate re-authorization URL for Microsoft OAuth
            microsoft_auth_url = (
                f"{MICROSOFT_AUTHORIZE_URL}"
                f"?client_id={MICROSOFT_CLIENT_ID}&"
                f"redirect_uri={MICROSOFT_REDIRECT_URI}&"
                f"scope={scope_str}&" # Re-request necessary scopes including offline_access
                f"response_type=code&"
                f"prompt=consent&" # Ensures refresh token is granted
                f"state={user.id}"
            )
            log.info(f"Generated re-authorization URL for user {user.id}")

            raise HTTPException(
                status_code=201,
                detail={
                    "error": "token_expired_no_refresh",
                    "message": "Microsoft token is expired and no valid refresh token is available. Re-authorization required.",
                    "reauth_url": microsoft_auth_url,
                    "action_required": "redirect_to_microsoft_auth",
                    "user_id": str(user.id),
                    "provider": "microsoft",
                    "reason": "no_refresh_token" if not token_entry.encrypted_refresh_token else "invalid_refresh_token"
                }
            )
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"Failed to generate re-authorization URL for user {user.id}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "reauth_generation_failed",
                    "message": "Microsoft token is expired and re-authorization flow could not be initiated. Please manually re-authorize your Microsoft integration.",
                    "user_id": str(user.id)
                }
            )

    # 4. Validate required environment variables for sync (assuming GCS for storage)
    if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
        raise HTTPException(
            status_code=500,
            detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
        )

    try:
        log.info(f"Starting scheduled/manual Microsoft sync for user {user.id}")

        # Add the task to the background tasks to sync user Microsoft data
        # You will need to implement initiate_microsoft_sync
        background_tasks.add_task(
            initiate_microsoft_sync,
            user.id,
            sync_token, # Use the valid (or freshly refreshed) token
            GCS_SERVICE_ACCOUNT_BASE64,
            GCS_BUCKET_NAME
        )

        background_tasks.add_task(
            update_data_source_sync_status,
            'microsoft', 
            'syncing'
        )

        return RedirectResponse(
            url=DATASOURCES_URL,
            status_code=302
        )

    except Exception as sync_error:
        log.error(f"Microsoft sync failed for user {user.id}: {str(sync_error)}")
        if "invalid_grant" in str(sync_error).lower() or "invalid_token" in str(sync_error).lower():
            log.warning(f"Microsoft sync for user {user.id} failed due to invalid token. User may need to re-authorize.")
            raise HTTPException(
                status_code=401,
                detail="Microsoft token invalid or expired. Please re-authorize your Microsoft integration."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Microsoft sync failed: {str(sync_error)}"
        )

@router.delete("/microsoft/disconnect")
async def disconnect_microsoft(background_tasks: BackgroundTasks, user=Depends(get_verified_user),
    microsoft_tenant_id: Optional[str] = None # Microsoft uses tenant IDs
):
    """
    Disconnects a user's Microsoft integration, revoking tokens (where possible), deleting credentials,
    cleaning up GCS files and updating the data source sync status.

    Args:
        user: The authenticated user object.
        microsoft_tenant_id (Optional[str]): If provided, only attempts to disconnect the Microsoft
                                       integration for this specific tenant ID (e.g., a specific
                                       Microsoft 365 organization).

    Returns:
        JSONResponse: A message indicating success or failure.
    """
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = user.id
    log.info(f"Initiating Microsoft integration disconnection for user: {user_id}"
             f"{f' (Tenant ID: {microsoft_tenant_id})' if microsoft_tenant_id else ''}"
             f", GCS cleanup")

    overall_success = True
    messages = []

    # --- Step 1: Revoke Microsoft Token(s) ---
    # Microsoft generally handles token invalidation at the Azure AD level.
    # There isn't a direct "revoke token" API endpoint for individual access/refresh tokens like Google.
    # When a user removes an app's permissions, or changes password, or admin revokes session, tokens become invalid.
    # For programmatic revocation, usually an admin action is required (e.g., invalidating a user's refresh token
    # via the Azure AD Graph API or by disabling the service principal for the application).
    # For the scope of a user-facing disconnect, primarily we'll delete the token from our DB and clean up data.
    # We can provide a "logout" URL, but it primarily clears browser session.

    # Fetch token entries to log which ones are being removed
    microsoft_tokens_to_remove: List[OAuthTokenModel] = []
    if microsoft_tenant_id:
        token_entry = OAuthTokens.get_token_by_user_provider_details(
            user_id=user_id,
            provider_name="Microsoft",
            # Assuming provider_team_id can store tenant_id for Microsoft
            provider_team_id=microsoft_tenant_id
        )
        if token_entry:
            microsoft_tokens_to_remove.append(token_entry)
    else:
        all_user_tokens = OAuthTokens.get_all_tokens_for_user(user_id=user_id)
        microsoft_tokens_to_remove = [
            token for token in all_user_tokens if token.provider_name == "Microsoft"
        ]

    if not microsoft_tokens_to_remove:
        msg = f"No Microsoft tokens found for user {user_id}{f' (Tenant ID: {microsoft_tenant_id})' if microsoft_tenant_id else ''}. Skipping token revocation attempt."
        log.warning(msg)
        messages.append(msg)
    else:
        # Log that tokens are being removed from local DB
        for token_entry in microsoft_tokens_to_remove:
            msg = (f"Microsoft token ID: {token_entry.id} for user {user_id}"
                   f" (Tenant ID: {token_entry.provider_team_id}) will be removed from DB.")
            log.info(msg)
            messages.append(msg)
        
        # Optionally, you could provide a link for the user to revoke permissions manually in their Microsoft account settings
        # This is more robust for user-initiated revocation for Microsoft.
        # "https://myapps.microsoft.com/" where they can see and revoke apps.

    # --- Step 2: Remove stored Microsoft credentials (OAuthToken entry) from DB ---
    try:
        if microsoft_tenant_id:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="Microsoft",
                provider_team_id=microsoft_tenant_id
            )
        else:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="Microsoft"
            )

        if db_delete_success:
            msg = f"Successfully deleted Microsoft OAuth token(s) from DB for user {user_id}{f' (Tenant ID: {microsoft_tenant_id})' if microsoft_tenant_id else ''}."
            log.info(msg)
            messages.append(msg)
        else:
            msg = f"Failed to delete Microsoft OAuth token(s) from DB for user {user_id}{f' (Tenant ID: {microsoft_tenant_id})' if microsoft_tenant_id else ''}. It might have already been deleted or not found."
            log.error(msg)
            messages.append(msg)
            overall_success = False
    except Exception as e:
        msg = f"Error deleting Microsoft OAuth token(s) from DB for user {user_id}: {e}"
        log.exception(msg)
        messages.append(msg)
        overall_success = False

    # --- Step 3: Update Microsoft Data Source Sync Status ---
    microsoft_data_source_found: Optional[DataSourceModel] = None
    user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
    for ds in user_data_sources:
        if ds.action == "microsoft":
            microsoft_data_source_found = ds
            break

    if microsoft_data_source_found:
        try:
            updated_ds = DataSources.update_data_source_sync_status_by_name(
                user_id=user_id,
                source_name=microsoft_data_source_found.name,
                sync_status="unsynced",
                last_sync=int(time.time())
            )
            if updated_ds:
                msg = f"Successfully updated Microsoft data source status to 'unsynced' for user {user_id} (Data Source Name: {updated_ds.name})."
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to update Microsoft data source status to 'unsynced' for user {user_id} (Data Source Name: {microsoft_data_source_found.name})."
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error updating Microsoft data source status for user {user_id}: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False
    else:
        msg = f"Microsoft data source not found for user {user_id}. Cannot update sync status."
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
        onedrive_folder_path = f"userResources/{user_id}/OneDrive/" 
        sharepoint_folder_path = f"userResources/{user_id}/SharePoint/" 
        try:

            background_tasks.add_task(
                delete_gcs_folder,
                onedrive_folder_path,
                GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME
            )
            
            background_tasks.add_task(
                delete_gcs_folder,
                sharepoint_folder_path,
                GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME
            )

            msg = f"Successfully initiated GCS data cleanup for user {user_id}'s Microsoft folder."
            log.info(msg)
            messages.append(msg)
            
        except Exception as e:
            msg = f"Error during GCS data cleanup for user {user_id}'s Microsoft folder: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False

    if overall_success:
        log.info(f"Microsoft integration disconnection process completed successfully for user: {user_id}")
        return {"message": "Microsoft integration disconnected successfully.", "details": messages}
    else:
        log.warning(f"Microsoft integration disconnection process completed with some failures for user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to fully disconnect Microsoft integration. See details.", "details": messages}
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
        f"?client_id={SLACK_CLIENT_ID}"
        f"&scope={bot_scope_str}"
        f"&user_scope={user_scope_str}"  # This is the key addition
        f"&redirect_uri={SLACK_REDIRECT_URI}"
        f"&state={state}"
    )

    return {
        "url": auth_url,
        "user_id": user.id,
        "bot_scopes": bot_scopes,
        "user_scopes": user_scopes
    }

@router.get("/slack/callback")
async def slack_callback(request: Request, background_tasks: BackgroundTasks):
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
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": SLACK_REDIRECT_URI,
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
            
            # Add the task to the background tasks to sync user slack data
            background_tasks.add_task(
                initiate_slack_sync,
                user_id,
                sync_token_for_immediate_use,
                GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME
            )

            background_tasks.add_task(
                update_data_source_sync_status,
                'slack', 
                'syncing'
            )

            return RedirectResponse(
                url=DATASOURCES_URL,
                status_code=302
            )
            
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
        "slack_client_configured": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET and SLACK_REDIRECT_URI),
    }
    
    return {
        "user_id": user.id,
        "configuration": config_status,
        "ready_for_sync": all(config_status.values())
    }

@router.post("/slack/sync")
async def manual_slack_sync(
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
):
    """Manually trigger Slack sync for the authenticated user, fetching tokens from DB."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Check if Slack sync is already in progress
    user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
    slack_data_source = None
    
    for ds in user_data_sources:
        if ds.action == 'slack':
            slack_data_source = ds
            break
    
    if slack_data_source and slack_data_source.sync_status == 'syncing':
        return
    
    current_time = int(time.time())

    # 1. Fetch encrypted tokens for the user and Slack provider
    # Fetch the most recently updated Slack token associated with the user
    token_entry = OAuthTokens.get_token_by_user_provider_details(
        user_id=user.id,
        provider_name="Slack"
        # If a user can connect multiple Slack workspaces, you'd need a way
        # to identify which specific team/workspace token to use, e.g., via a query parameter.
        # For now, we fetch the "primary" one (most recently updated).
    )

    log.info(f"Fetched Slack token entry for user {user.id}: {token_entry}")

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
                    "client_id": SLACK_CLIENT_ID,
                    "client_secret": SLACK_CLIENT_SECRET,
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

        # Add the task to the background tasks to sync user slack data
        background_tasks.add_task(
            initiate_slack_sync,
            user.id,
            sync_token, # Use the valid (or freshly refreshed) token
            GCS_SERVICE_ACCOUNT_BASE64,
            GCS_BUCKET_NAME
        )

        background_tasks.add_task(
                update_data_source_sync_status,
                'slack', 
                'syncing'
            )
        
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
async def disconnect_slack(background_tasks: BackgroundTasks, user=Depends(get_verified_user),
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
                provider_name="Slack"
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
        slack_folder_path = f"userResources/{user_id}/Slack/"
        try:
            background_tasks.add_task(
                delete_gcs_folder,
                slack_folder_path,
                GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME
            )

            msg = f"Successfully initiated GCS data cleanup for user {user_id}'s Slack folder."
            log.info(msg)
            messages.append(msg)
            
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
    

############################
# Atlassian Endpoints 
############################
@router.get("/atlassian/initialize")
def get_atlassian_auth_url(user=Depends(get_verified_user)):
    """Generate Atlassian OAuth URL for the current authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Atlassian scopes for Jira and Confluence (read-only where possible)
    # Refer to Atlassian's documentation for the most current and specific scopes.
    # atlassian_scopes = [
    #     "read:jira-user",        # Read user profile data in Jira
    #     "read:jira-work",        # Read Jira project and issue data
    #     "read:confluence-space", # Read Confluence spaces
    #     "read:confluence-content",# Read Confluence page content and attachments
    #     "offline_access",         # Crucial to get a refresh_token
    #     "read:project:jira",
    # ]

    atlassian_scopes = [
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
    ]

    scope_str = " ".join(atlassian_scopes) # Atlassian scopes are space-separated

    state = user.id
    oauth_state_store[state] = user.id # Store for validation in callback

    # Atlassian uses 'audience' for the API gateway
    auth_url = (
        f"{ATLASSIAN_AUTHORIZE_URL}"
        f"?client_id={ATLASSIAN_CLIENT_ID}"
        f"&redirect_uri={ATLASSIAN_REDIRECT_URL}"
        f"&scope={scope_str}"
        f"&response_type=code"
        f"&prompt=consent"      # Ensures refresh token is always granted
        f"&state={state}"
        f"&audience={ATLASSIAN_API_GATEWAY}" # Required for Atlassian's 3LO
    )

    return {
        "url": auth_url,
        "user_id": user.id,
        "scopes": atlassian_scopes
    }

@router.get("/atlassian/callback")
async def atlassian_callback(request: Request, background_tasks: BackgroundTasks):
    """Handle Atlassian OAuth callback and initiate sync process."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description")

    if error:
        log.error(f"Atlassian OAuth error: {error} - {error_description}")
        return Response(status_code=400, content=f"Atlassian OAuth error: {error_description or error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing Atlassian OAuth code.")

    if not state or state not in oauth_state_store:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state.")

    user_id = oauth_state_store.pop(state) # Remove state after use

    try:
        response = requests.post(
            ATLASSIAN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": ATLASSIAN_CLIENT_ID,
                "client_secret": ATLASSIAN_CLIENT_SECRET,
                "code": code,
                "redirect_uri": ATLASSIAN_REDIRECT_URL,
            },
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise HTTPException(status_code=400, detail=f"Atlassian OAuth failed: {data.get('error_description', data.get('error'))}")

        log.info(f"Atlassian OAuth successful for user {user_id}")

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")

        # Atlassian's access token is often a JWT. You can decode it to get user info.
        # The 'sub' claim might be the user's Atlassian account ID.
        atlassian_user_id = None
        if access_token:
            try:
                # In production, properly decode and verify the JWT.
                # For basic info, just decode without verification for initial ID extraction.
                decoded_access_token = jwt.decode(access_token, options={"verify_signature": False})
                atlassian_user_id = decoded_access_token.get("sub") # 'sub' is the Atlassian Account ID
                log.info(f"Decoded Atlassian user ID (sub): {atlassian_user_id}")
            except ImportError:
                log.warning("PyJWT not installed. Cannot decode access_token to get Atlassian User ID.")
            except Exception as e:
                log.error(f"Failed to decode Atlassian access_token: {e}")

        if not access_token:
            raise HTTPException(
                status_code=500,
                detail="No access token received from Atlassian OAuth. Ensure necessary scopes are requested."
            )

        encrypted_access_token = encrypt_data(access_token)
        encrypted_refresh_token = encrypt_data(refresh_token) if refresh_token else None

        access_token_expires_at = None
        if expires_in:
            access_token_expires_at = int(time.time()) + expires_in

        try:
            OAuthTokens.insert_new_token(
                user_id=user_id,
                provider_name="Atlassian",
                provider_user_id=atlassian_user_id, # Store Atlassian Account ID
                encrypted_access_token=encrypted_access_token,
                encrypted_refresh_token=encrypted_refresh_token,
                access_token_expires_at=access_token_expires_at,
                scopes=data.get("scope"),
            )
            log.info(f"Stored/Updated Atlassian OAuth tokens for user {user_id}")

        except Exception as db_error:
            log.error(f"Failed to store Atlassian OAuth tokens in DB for user {user_id}: {db_error}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to store Atlassian tokens securely.")

        if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
            raise HTTPException(
                status_code=500,
                detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
            )

        try:
            log.info(f"Starting Atlassian sync for user {user_id} with token (retrieved from OAuth response)")

            background_tasks.add_task(
                initiate_atlassian_sync,
                user_id=user_id,
                token=access_token,
                creds=GCS_SERVICE_ACCOUNT_BASE64,
                gcs_bucket_name=GCS_BUCKET_NAME
            )

            background_tasks.add_task(
                update_data_source_sync_status,
                'google', 
                'syncing'
            )

            return RedirectResponse(
                url=DATASOURCES_URL,
                status_code=302
            )

        except Exception as sync_error:
            log.error(f"Atlassian sync failed for user {user_id}: {str(sync_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Atlassian sync failed: {str(sync_error)}"
            )

    except requests.exceptions.RequestException as e:
        log.error(f"Atlassian API Request Error: {str(e)}", exc_info=True)
        if hasattr(e, 'response') and e.response is not None:
            log.error(f"Response: {e.response.text}")
        raise HTTPException(status_code=500, detail="Failed to authenticate with Atlassian")

@router.get("/atlassian/status")
def get_atlassian_status(user=Depends(get_verified_user)):
    """Get current user's Atlassian integration status."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    config_status = {
        "gcs_bucket_configured": bool(GCS_BUCKET_NAME),
        "gcs_credentials_configured": bool(GCS_SERVICE_ACCOUNT_BASE64),
        "atlassian_client_configured": bool(ATLASSIAN_CLIENT_ID and ATLASSIAN_CLIENT_SECRET and ATLASSIAN_REDIRECT_URI),
    }

    atlassian_token_exists = OAuthTokens.get_token_by_user_provider_details(user_id=user.id, provider_name="Atlassian")

    sync_status = "not_connected"
    user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
    for ds in user_data_sources:
        if ds.action == "atlassian":
            sync_status = ds.sync_status
            break

    return {
        "user_id": user.id,
        "configuration": config_status,
        "atlassian_token_present": bool(atlassian_token_exists),
        "current_sync_status": sync_status,
        "ready_for_sync": all(config_status.values()) and bool(atlassian_token_exists) and sync_status != "syncing"
    }

@router.post("/atlassian/sync")
async def manual_atlassian_sync(
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
):
    """Manually trigger Atlassian sync for the authenticated user, fetching tokens from DB."""
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Check if Slack sync is already in progress
    user_data_sources = DataSources.get_data_sources_by_user_id(user.id)
    atlassian_data_source = None
    
    for ds in user_data_sources:
        if ds.action == 'atlassian':
            atlassian_data_source = ds
            break
    
    if atlassian_data_source and atlassian_data_source.sync_status == 'syncing':
        return

    current_time = int(time.time())

    token_entry = OAuthTokens.get_token_by_user_provider_details(
        user_id=user.id,
        provider_name="Atlassian"
    )

    if not token_entry:
        raise HTTPException(
            status_code=404,
            detail="No Atlassian integration found for this user. Please authorize your Atlassian app first."
        )

    try:
        decrypted_access_token = decrypt_data(token_entry.encrypted_access_token)
        decrypted_refresh_token = decrypt_data(token_entry.encrypted_refresh_token) if token_entry.encrypted_refresh_token else None

        sync_token = decrypted_access_token

    except Exception as e:
        log.error(f"Failed to decrypt tokens for user {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to decrypt Atlassian tokens. Please try re-authorizing.")

    refresh_needed = False
    if token_entry.access_token_expires_at:
        if (token_entry.access_token_expires_at - current_time) < (5 * 60): # Refresh if less than 5 mins
            refresh_needed = True
            log.info(f"Access token for user {user.id} nearing expiration. Initiating refresh.")
    elif decrypted_refresh_token:
        log.info(f"Access token for user {user.id} has no explicit expiry but a refresh token exists. Will attempt refresh.")
        refresh_needed = True


    if refresh_needed and decrypted_refresh_token:
        try:
            log.info(f"Attempting to refresh Atlassian token for user {user.id}")
            refresh_response = requests.post(
                ATLASSIAN_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": ATLASSIAN_CLIENT_ID,
                    "client_secret": ATLASSIAN_CLIENT_SECRET,
                    "refresh_token": decrypted_refresh_token,
                },
            )
            refresh_response.raise_for_status()
            refresh_data = refresh_response.json()

            if "error" in refresh_data:
                log.error(f"Atlassian token refresh failed for user {user.id}: {refresh_data.get('error_description', refresh_data.get('error'))}")
                raise HTTPException(status_code=400, detail=f"Failed to refresh Atlassian token: {refresh_data.get('error_description', refresh_data.get('error'))}")

            new_access_token = refresh_data.get("access_token")
            new_refresh_token = refresh_data.get("refresh_token", decrypted_refresh_token)
            new_expires_in = refresh_data.get("expires_in")

            if not new_access_token:
                raise HTTPException(status_code=500, detail="No new access token received after refresh.")

            encrypted_new_access_token = encrypt_data(new_access_token)
            encrypted_new_refresh_token = encrypt_data(new_refresh_token) if new_refresh_token else None
            new_access_token_expires_at = int(time.time()) + new_expires_in if new_expires_in else None

            updated_token_entry = OAuthTokens.update_token_by_id(
                token_id=token_entry.id,
                encrypted_access_token=encrypted_new_access_token,
                encrypted_refresh_token=encrypted_new_refresh_token,
                access_token_expires_at=new_access_token_expires_at,
                scopes=refresh_data.get("scope", token_entry.scopes)
            )

            if not updated_token_entry:
                raise HTTPException(status_code=500, detail="Failed to update refreshed Atlassian tokens in database.")

            log.info(f"Successfully refreshed and updated Atlassian tokens for user {user.id}")
            sync_token = new_access_token

        except requests.exceptions.RequestException as e:
            log.error(f"Atlassian API Request Error during token refresh for user {user.id}: {str(e)}", exc_info=True)
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Refresh response: {e.response.text}")
            raise HTTPException(status_code=500, detail="Failed to refresh Atlassian token with provider.")
        except Exception as e:
            log.error(f"An error occurred during Atlassian token refresh for user {user.id}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="An internal server error occurred during token refresh.")
    elif refresh_needed and not decrypted_refresh_token:
        log.warning(f"Access token for user {user.id} nearing expiration but no valid refresh token available. Initiating re-authorization flow.")
        try:
            atlassian_auth_url = (
                f"{ATLASSIAN_AUTHORIZE_URL}"
                f"?client_id={ATLASSIAN_CLIENT_ID}&"
                f"redirect_uri={ATLASSIAN_REDIRECT_URL}&"
                f"scope=read:jira-user%20read:jira-work%20read:confluence-space%20read:confluence-content%20offline_access&" # Re-request necessary scopes
                f"response_type=code&"
                f"prompt=consent&"
                f"state={user.id}&"
                f"audience={ATLASSIAN_API_GATEWAY}"
            )
            log.info(f"Generated re-authorization URL for user {user.id}")

            raise HTTPException(
                status_code=201,
                detail={
                    "error": "token_expired_no_refresh",
                    "message": "Atlassian token is expired and no valid refresh token is available. Re-authorization required.",
                    "reauth_url": atlassian_auth_url,
                    "action_required": "redirect_to_atlassian_auth",
                    "user_id": str(user.id),
                    "provider": "atlassian",
                    "reason": "no_refresh_token" if not token_entry.encrypted_refresh_token else "invalid_refresh_token"
                }
            )
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"Failed to generate re-authorization URL for user {user.id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "reauth_generation_failed",
                    "message": "Atlassian token is expired and re-authorization flow could not be initiated. Please manually re-authorize your Atlassian integration.",
                    "user_id": str(user.id)
                }
            )

    if not GCS_BUCKET_NAME or not GCS_SERVICE_ACCOUNT_BASE64:
        raise HTTPException(
            status_code=500,
            detail="GCS configuration missing. Please configure GCS_BUCKET_NAME and GCS_SERVICE_ACCOUNT_BASE64."
        )

    try:
        log.info(f"Starting scheduled/manual Atlassian sync for user {user.id}")

        background_tasks.add_task(
            initiate_atlassian_sync,
            user_id=user.id,
            token=sync_token,
            creds=GCS_SERVICE_ACCOUNT_BASE64,
            gcs_bucket_name=GCS_BUCKET_NAME
        )

        await update_data_source_sync_status(user.id, 'atlassian', 'syncing')

        return {
            "message": "Atlassian data sync initiated successfully.",
            "user_id": user.id,
            "status": "success"
        }

    except Exception as sync_error:
        log.error(f"Atlassian sync failed for user {user.id}: {str(sync_error)}", exc_info=True)
        if "invalid_grant" in str(sync_error).lower() or "invalid_token" in str(sync_error).lower():
            log.warning(f"Atlassian sync for user {user.id} failed due to invalid token. User may need to re-authorize.")
            raise HTTPException(
                status_code=401,
                detail="Atlassian token invalid or expired. Please re-authorize your Atlassian integration."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Atlassian sync failed: {str(sync_error)}"
        )

@router.delete("/atlassian/disconnect")
async def disconnect_atlassian(user=Depends(get_verified_user),
    atlassian_cloud_id: Optional[str] = None # Atlassian uses cloud_id to identify specific sites
):
    """
    Disconnects a user's Atlassian integration, removing tokens, deleting credentials,
    cleaning up GCS files and updating the data source sync status.
    """
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = user.id
    log.info(f"Initiating Atlassian integration disconnection for user: {user_id}"
             f"{f' (Cloud ID: {atlassian_cloud_id})' if atlassian_cloud_id else ''}"
             f", GCS cleanup")

    overall_success = True
    messages = []

    # --- Step 1: Token Revocation ---
    # Atlassian OAuth 2.0 (3LO) tokens are managed at the app level.
    # There's no direct API to "revoke a single refresh token" for a user's app grant.
    # Revocation typically happens when a user removes the app's consent via their Atlassian account settings.
    # We primarily focus on removing the token from our DB.
    atlassian_tokens_to_remove: List[OAuthTokenModel] = []
    if atlassian_cloud_id:
        token_entry = OAuthTokens.get_token_by_user_provider_details(
            user_id=user_id,
            provider_name="Atlassian",
            provider_team_id=atlassian_cloud_id # Assuming provider_team_id stores cloud_id
        )
        if token_entry:
            atlassian_tokens_to_remove.append(token_entry)
    else:
        all_user_tokens = OAuthTokens.get_all_tokens_for_user(user_id=user_id)
        atlassian_tokens_to_remove = [
            token for token in all_user_tokens if token.provider_name == "Atlassian"
        ]

    if not atlassian_tokens_to_remove:
        msg = f"No Atlassian tokens found for user {user_id}{f' (Cloud ID: {atlassian_cloud_id})' if atlassian_cloud_id else ''}. Skipping token revocation attempt."
        log.warning(msg)
        messages.append(msg)
    else:
        for token_entry in atlassian_tokens_to_remove:
            msg = (f"Atlassian token ID: {token_entry.id} for user {user_id}"
                   f" (Cloud ID: {token_entry.provider_team_id or 'N/A'}) will be removed from DB.")
            log.info(msg)
            messages.append(msg)
            # You could optionally include a link for the user to revoke permissions manually:
            # "https://id.atlassian.com/manage-profile/profile-and-visibility" or "https://id.atlassian.com/manage-profile/apps-and-services"

    # --- Step 2: Remove stored Atlassian credentials (OAuthToken entry) from DB ---
    try:
        if atlassian_cloud_id:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="Atlassian",
                provider_team_id=atlassian_cloud_id
            )
        else:
            db_delete_success = OAuthTokens.delete_tokens_for_user_by_provider(
                user_id=user_id,
                provider_name="Atlassian"
            )

        if db_delete_success:
            msg = f"Successfully deleted Atlassian OAuth token(s) from DB for user {user_id}{f' (Cloud ID: {atlassian_cloud_id})' if atlassian_cloud_id else ''}."
            log.info(msg)
            messages.append(msg)
        else:
            msg = f"Failed to delete Atlassian OAuth token(s) from DB for user {user_id}{f' (Cloud ID: {atlassian_cloud_id})' if atlassian_cloud_id else ''}. It might have already been deleted or not found."
            log.error(msg)
            messages.append(msg)
            overall_success = False
    except Exception as e:
        msg = f"Error deleting Atlassian OAuth token(s) from DB for user {user_id}: {e}"
        log.exception(msg)
        messages.append(msg)
        overall_success = False

    # --- Step 3: Update Atlassian Data Source Sync Status ---
    atlassian_data_source_found: Optional[DataSourceModel] = None
    user_data_sources: List[DataSourceModel] = DataSources.get_data_sources_by_user_id(user_id)
    for ds in user_data_sources:
        if ds.action == "atlassian": # Assuming 'atlassian' as the action type
            atlassian_data_source_found = ds
            break

    if atlassian_data_source_found:
        try:
            updated_ds = DataSources.update_data_source_sync_status_by_name(
                user_id=user_id,
                source_name=atlassian_data_source_found.name,
                sync_status="unsynced",
                last_sync=int(time.time())
            )
            if updated_ds:
                msg = f"Successfully updated Atlassian data source status to 'unsynced' for user {user_id} (Data Source Name: {updated_ds.name})."
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to update Atlassian data source status to 'unsynced' for user {user_id} (Data Source Name: {atlassian_data_source_found.name})."
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error updating Atlassian data source status for user {user_id}: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False
    else:
        msg = f"Atlassian data source not found for user {user_id}. Cannot update sync status."
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
        atlassian_folder_path = f"userResources/{user_id}/Atlassian/" # Assuming this GCS path
        try:
            gcs_cleanup_success = await delete_gcs_folder(
                folder_path=atlassian_folder_path,
                service_account_base64=GCS_SERVICE_ACCOUNT_BASE64,
                GCS_BUCKET_NAME=GCS_BUCKET_NAME
            )
            if gcs_cleanup_success:
                msg = f"Successfully initiated GCS data cleanup for user {user_id}'s Atlassian folder."
                log.info(msg)
                messages.append(msg)
            else:
                msg = f"Failed to delete GCS data for user {user_id}'s Atlassian folder."
                log.error(msg)
                messages.append(msg)
                overall_success = False
        except Exception as e:
            msg = f"Error during GCS data cleanup for user {user_id}'s Atlassian folder: {e}"
            log.exception(msg)
            messages.append(msg)
            overall_success = False

    if overall_success:
        log.info(f"Atlassian integration disconnection process completed successfully for user: {user_id}")
        return {"message": "Atlassian integration disconnected successfully.", "details": messages}
    else:
        log.warning(f"Atlassian integration disconnection process completed with some failures for user: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to fully disconnect Atlassian integration. See details.", "details": messages}
        )
