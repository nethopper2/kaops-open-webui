import logging
import time
import uuid
from typing import Optional, List
import json # For JSON (scopes) field if storing list of strings

from open_webui.internal.db import Base, get_db
# Assuming JSONField is for custom JSON handling, but for a simple list of strings, Text field is fine.
# If you actually use JSONField, ensure it handles SQLAlchemy's LargeBinary type or is adapted.
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, LargeBinary, ForeignKey
from sqlalchemy.schema import UniqueConstraint # Import UniqueConstraint

# Import your encryption utilities
from open_webui.utils.data.encryption import encrypt_data, decrypt_data

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

####################
# OAuth Tokens DB Schema
####################

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('user.id'), nullable=False)
    data_source_id = Column(String, ForeignKey('data_source.id'), nullable=True) # Link to the data_source table (e.g., for 'slack')

    provider_name = Column(String, nullable=False) # e.g., "slack", "google", "github"
    provider_user_id = Column(String, nullable=True) # User ID from the provider (e.g., Slack's U12345)
    provider_team_id = Column(String, nullable=True) # Team/Workspace ID from the provider (e.g., Slack's T12345)
    
    # Store encrypted tokens as LargeBinary
    encrypted_access_token = Column(LargeBinary, nullable=False)
    encrypted_refresh_token = Column(LargeBinary, nullable=True)
    
    access_token_expires_at = Column(BigInteger, nullable=True) # Unix timestamp of expiration
    # Store scopes as Text (comma-separated string is common)
    # Alternatively, if you have a custom JSONField type and it handles binary/text correctly,
    # you could use that and store `List[str]` as JSON.
    scopes = Column(Text, nullable=True) 

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)

    # Add a unique constraint to prevent duplicate token entries for the same user/provider/details
    __table_args__ = (
        UniqueConstraint('user_id', 'provider_name', 'provider_user_id', 'provider_team_id', name='uq_oauth_tokens_user_provider_details'),
    )

class OAuthTokenModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    data_source_id: Optional[str] = None

    provider_name: str
    provider_user_id: Optional[str] = None
    provider_team_id: Optional[str] = None
    
    # These fields will be bytes coming from the DB
    encrypted_access_token: bytes
    encrypted_refresh_token: Optional[bytes] = None
    
    access_token_expires_at: Optional[int] = None # timestamp in epoch
    scopes: Optional[str] = None # Stored as a string

    created_at: int # timestamp in epoch
    updated_at: int # timestamp in epoch


####################
# Forms (for input/output if needed, though often internal for tokens)
####################

# You might not need explicit Form/Response classes for tokens as they are usually managed internally.
# However, if you have an admin API or need to expose token metadata, you could define them.
# For simplicity, I'm omitting them for now, but keeping the placeholders commented out.

# class OAuthTokenForm(BaseModel):
#     # ... fields for creating/updating token entry, but sensitive fields (tokens)
#     # should not come directly from client input.
#     pass

# class OAuthTokenResponse(BaseModel):
#     # ... fields for responding with token metadata (but not raw tokens)
#     id: str
#     user_id: str
#     provider_name: str
#     provider_user_id: Optional[str] = None
#     provider_team_id: Optional[str] = None
#     access_token_expires_at: Optional[int] = None
#     scopes: Optional[str] = None
#     created_at: int
#     updated_at: int
#     model_config = ConfigDict(extra="allow")


####################
# Database Operations Class
####################

class OAuthTokensTable:
    def insert_new_token(
        self,
        user_id: str,
        provider_name: str,
        encrypted_access_token: bytes,
        encrypted_refresh_token: Optional[bytes] = None,
        access_token_expires_at: Optional[int] = None,
        scopes: Optional[str] = None, # Comma-separated string of scopes
        provider_user_id: Optional[str] = None,
        provider_team_id: Optional[str] = None,
        data_source_id: Optional[str] = None,
    ) -> Optional[OAuthTokenModel]:
        with get_db() as db:
            current_time = int(time.time())
            token_id = str(uuid.uuid4())

            # Check for existing token to avoid unique constraint violation on insert
            # This logic should be mostly handled by the API endpoint's update/insert
            # but having it here can provide an additional safety net if needed.
            existing_token_query = db.query(OAuthToken).filter(
                OAuthToken.user_id == user_id,
                OAuthToken.provider_name == provider_name,
                OAuthToken.provider_user_id == provider_user_id,
                OAuthToken.provider_team_id == provider_team_id
            )
            existing_token = existing_token_query.first()

            if existing_token:
                # Update existing entry
                existing_token.encrypted_access_token = encrypted_access_token
                existing_token.encrypted_refresh_token = encrypted_refresh_token
                existing_token.access_token_expires_at = access_token_expires_at
                existing_token.scopes = scopes
                existing_token.updated_at = current_time
                db.commit()
                db.refresh(existing_token)
                return OAuthTokenModel.model_validate(existing_token)
            else:
                # Insert new entry
                new_token_entry = OAuthToken(
                    id=token_id,
                    user_id=user_id,
                    data_source_id=data_source_id,
                    provider_name=provider_name,
                    provider_user_id=provider_user_id,
                    provider_team_id=provider_team_id,
                    encrypted_access_token=encrypted_access_token,
                    encrypted_refresh_token=encrypted_refresh_token,
                    access_token_expires_at=access_token_expires_at,
                    scopes=scopes,
                    created_at=current_time,
                    updated_at=current_time,
                )
                try:
                    db.add(new_token_entry)
                    db.commit()
                    db.refresh(new_token_entry)
                    return OAuthTokenModel.model_validate(new_token_entry)
                except Exception as e:
                    log.exception(f"Error inserting a new OAuth token: {e}")
                    db.rollback()
                    return None

    def get_token_by_user_provider_details(
        self,
        user_id: str,
        provider_name: str,
        provider_user_id: Optional[str] = None,
        provider_team_id: Optional[str] = None,
    ) -> Optional[OAuthTokenModel]:
        """
        Fetches a specific OAuth token entry for a user and provider,
        optionally refined by provider-specific user and team IDs.
        Prioritizes entries that have a provider_user_id and provider_team_id match.
        If multiple exist (e.g., user has multiple Slack workspaces),
        it returns the most recently updated one.
        """
        with get_db() as db:
            try:
                query = db.query(OAuthToken).filter(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider_name == provider_name,
                )
                
                # Add filters for provider_user_id and provider_team_id if provided
                if provider_user_id is not None:
                    query = query.filter(OAuthToken.provider_user_id == provider_user_id)
                if provider_team_id is not None:
                    query = query.filter(OAuthToken.provider_team_id == provider_team_id)
                    
                # If these specific IDs are not provided, or there might be multiple,
                # prioritize the most recently updated.
                token = query.order_by(OAuthToken.updated_at.desc()).first()
                
                return OAuthTokenModel.model_validate(token) if token else None
            except Exception as e:
                log.exception(f"Error getting OAuth token for user {user_id}, provider {provider_name}: {e}")
                return None

    def get_all_tokens_for_user(self, user_id: str) -> List[OAuthTokenModel]:
        """Get all OAuth tokens for a specific user across all providers."""
        with get_db() as db:
            try:
                return [
                    OAuthTokenModel.model_validate(token)
                    for token in db.query(OAuthToken)
                    .filter_by(user_id=user_id)
                    .order_by(OAuthToken.updated_at.desc())
                    .all()
                ]
            except Exception as e:
                log.exception(f"Error getting all OAuth tokens for user {user_id}: {e}")
                return []

    def update_token_by_id(
        self,
        token_id: str,
        encrypted_access_token: bytes,
        encrypted_refresh_token: Optional[bytes] = None,
        access_token_expires_at: Optional[int] = None,
        scopes: Optional[str] = None,
    ) -> Optional[OAuthTokenModel]:
        with get_db() as db:
            try:
                token = db.query(OAuthToken).filter_by(id=token_id).first()
                if token:
                    token.encrypted_access_token = encrypted_access_token
                    token.encrypted_refresh_token = encrypted_refresh_token
                    token.access_token_expires_at = access_token_expires_at
                    token.scopes = scopes
                    token.updated_at = int(time.time())
                    db.commit()
                    db.refresh(token)
                    return OAuthTokenModel.model_validate(token)
                return None
            except Exception as e:
                log.exception(f"Error updating OAuth token {token_id}: {e}")
                db.rollback()
                return None

    def delete_token_by_id(self, token_id: str) -> bool:
        with get_db() as db:
            try:
                db.query(OAuthToken).filter_by(id=token_id).delete()
                db.commit()
                return True
            except Exception as e:
                log.exception(f"Error deleting OAuth token {token_id}: {e}")
                db.rollback()
                return False

    def delete_tokens_for_user_by_provider(
        self, user_id: str, provider_name: str, provider_team_id: Optional[str] = None
    ) -> bool:
        """
        Deletes all (or specific team's) OAuth tokens for a user for a given provider.
        Useful when a user uninstalls an app or disconnects an integration.
        """
        with get_db() as db:
            try:
                query = db.query(OAuthToken).filter(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider_name == provider_name
                )
                if provider_team_id:
                    query = query.filter(OAuthToken.provider_team_id == provider_team_id)

                query.delete(synchronize_session=False) # Use synchronize_session=False for bulk deletes
                db.commit()
                return True
            except Exception as e:
                log.exception(f"Error deleting OAuth tokens for user {user_id}, provider {provider_name}: {e}")
                db.rollback()
                return False

OAuthTokens = OAuthTokensTable()