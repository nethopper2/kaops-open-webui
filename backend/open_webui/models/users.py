import requests
import time
import logging

from typing import Optional, Dict, Any

import jwt

import base64

from open_webui.internal.db import Base, JSONField, get_db


from open_webui.models.datatokens import OAuthTokens

from open_webui.env import DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL
from open_webui.models.chats import Chats
from open_webui.models.groups import Groups, GroupModel, GroupUpdateForm, GroupForm
from open_webui.utils.data.encryption import encrypt_data
from open_webui.utils.misc import throttle


from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, Date
from sqlalchemy import or_

import datetime

from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])
####################
# User DB Schema
####################


class User(Base):
    __tablename__ = "user"

    id = Column(String, primary_key=True)
    name = Column(String)

    email = Column(String)
    username = Column(String(50), nullable=True)

    role = Column(String)
    profile_image_url = Column(Text)

    bio = Column(Text, nullable=True)
    gender = Column(Text, nullable=True)
    date_of_birth = Column(Date, nullable=True)

    info = Column(JSONField, nullable=True)
    settings = Column(JSONField, nullable=True)

    api_key = Column(String, nullable=True, unique=True)
    oauth_sub = Column(Text, unique=True)

    last_active_at = Column(BigInteger)

    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)


class UserSettings(BaseModel):
    ui: Optional[dict] = {}
    model_config = ConfigDict(extra="allow")
    pass


class UserModel(BaseModel):
    id: str
    name: str

    email: str
    username: Optional[str] = None

    role: str = "pending"
    profile_image_url: str

    bio: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime.date] = None

    info: Optional[dict] = None
    settings: Optional[UserSettings] = None

    api_key: Optional[str] = None
    oauth_sub: Optional[str] = None

    last_active_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class UpdateProfileForm(BaseModel):
    profile_image_url: str
    name: str
    bio: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime.date] = None


class UserListResponse(BaseModel):
    users: list[UserModel]
    total: int


class UserInfoResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str


class UserInfoListResponse(BaseModel):
    users: list[UserInfoResponse]
    total: int


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    profile_image_url: str


class UserNameResponse(BaseModel):
    id: str
    name: str
    role: str
    profile_image_url: str


class UserRoleUpdateForm(BaseModel):
    id: str
    role: str


class UserUpdateForm(BaseModel):
    role: str
    name: str
    email: str
    profile_image_url: str
    password: Optional[str] = None


class UsersTable:
    def insert_new_user(
        self,
        id: str,
        name: str,
        email: str,
        profile_image_url: str = "/user.png",
        role: str = "pending",
        oauth_sub: Optional[str] = None,
    ) -> Optional[UserModel]:
        with get_db() as db:
            user = UserModel(
                **{
                    "id": id,
                    "name": name,
                    "email": email,
                    "role": role,
                    "profile_image_url": profile_image_url,
                    "last_active_at": int(time.time()),
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                    "oauth_sub": oauth_sub,
                }
            )
            result = User(**user.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            if result:
                return user
            else:
                return None

    def get_user_by_id(self, id: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_by_api_key(self, api_key: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(api_key=api_key).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_by_email(self, email: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(email=email).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_by_oauth_sub(self, sub: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(oauth_sub=sub).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_users(
        self,
        filter: Optional[dict] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> UserListResponse:
        with get_db() as db:
            query = db.query(User)

            if filter:
                query_key = filter.get("query")
                if query_key:
                    query = query.filter(
                        or_(
                            User.name.ilike(f"%{query_key}%"),
                            User.email.ilike(f"%{query_key}%"),
                        )
                    )

                order_by = filter.get("order_by")
                direction = filter.get("direction")

                if order_by == "name":
                    if direction == "asc":
                        query = query.order_by(User.name.asc())
                    else:
                        query = query.order_by(User.name.desc())
                elif order_by == "email":
                    if direction == "asc":
                        query = query.order_by(User.email.asc())
                    else:
                        query = query.order_by(User.email.desc())

                elif order_by == "created_at":
                    if direction == "asc":
                        query = query.order_by(User.created_at.asc())
                    else:
                        query = query.order_by(User.created_at.desc())

                elif order_by == "last_active_at":
                    if direction == "asc":
                        query = query.order_by(User.last_active_at.asc())
                    else:
                        query = query.order_by(User.last_active_at.desc())

                elif order_by == "updated_at":
                    if direction == "asc":
                        query = query.order_by(User.updated_at.asc())
                    else:
                        query = query.order_by(User.updated_at.desc())
                elif order_by == "role":
                    if direction == "asc":
                        query = query.order_by(User.role.asc())
                    else:
                        query = query.order_by(User.role.desc())

            else:
                query = query.order_by(User.created_at.desc())

            if skip:
                query = query.offset(skip)
            if limit:
                query = query.limit(limit)

            users = query.all()
            return {
                "users": [UserModel.model_validate(user) for user in users],
                "total": db.query(User).count(),
            }

    def get_users_by_user_ids(self, user_ids: list[str]) -> list[UserModel]:
        with get_db() as db:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            return [UserModel.model_validate(user) for user in users]

    def get_num_users(self) -> Optional[int]:
        with get_db() as db:
            return db.query(User).count()

    def has_users(self) -> bool:
        with get_db() as db:
            return db.query(db.query(User).exists()).scalar()

    def get_first_user(self) -> UserModel:
        try:
            with get_db() as db:
                user = db.query(User).order_by(User.created_at).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_webhook_url_by_id(self, id: str) -> Optional[str]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(id=id).first()

                if user.settings is None:
                    return None
                else:
                    return (
                        user.settings.get("ui", {})
                        .get("notifications", {})
                        .get("webhook_url", None)
                    )
        except Exception:
            return None

    def update_user_role_by_id(self, id: str, role: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update({"role": role})
                db.commit()
                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_profile_image_url_by_id(
        self, id: str, profile_image_url: str
    ) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update(
                    {"profile_image_url": profile_image_url}
                )
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_groups_from_header(self, user, group_string, default_permissions):
        log.info("Running enhanced group sync using comma-separated string")

        # Step 1: Parse comma-separated string into a list of cleaned, lower-cased group names
        user_header_groups_raw = [g.strip() for g in group_string.split(",") if g.strip()]
        user_header_groups = [g.lower() for g in user_header_groups_raw]

        user_current_groups: list[GroupModel] = Groups.get_groups_by_member_id(user.id)
        all_available_groups: list[GroupModel] = Groups.get_groups()

        # Map of lowercased group name to actual GroupModel
        available_group_map = {g.name.lower(): g for g in all_available_groups}
        current_group_map = {g.name.lower(): g for g in user_current_groups}

        log.info(f"User header groups (parsed from string): {user_header_groups_raw}")
        log.info(f"User's current groups: {[g.name for g in user_current_groups]}")
        log.info(f"All groups available: {[g.name for g in all_available_groups]}")

        # Step 2: Remove user from groups they no longer belong to
        for group_name_lc, group_model in current_group_map.items():
            if group_name_lc not in user_header_groups:
                log.info(f"Removing user from group {group_model.name}")
                user_ids = [uid for uid in group_model.user_ids if uid != user.id]
                group_permissions = group_model.permissions or default_permissions

                update_form = GroupUpdateForm(
                    name=group_model.name,
                    description=group_model.description,
                    permissions=group_permissions,
                    user_ids=user_ids,
                )
                Groups.update_group_by_id(id=group_model.id, form_data=update_form, overwrite=False)

        # Step 3: Ensure all user_header_groups exist, create if needed, and add user
        for i, group_name_lc in enumerate(user_header_groups):
            group_display_name = user_header_groups_raw[i]
            group_model = available_group_map.get(group_name_lc)

            if not group_model:
                # Create new group
                log.info(f"Creating new group '{group_display_name}' with default permissions")
                form_data = GroupForm(
                    name=group_display_name,
                    description=f"Auto-created group for {group_display_name}",
                    permissions=default_permissions,
                    user_ids=[user.id],
                )
                group_model = Groups.insert_new_group(user_id=user.id, form_data=form_data)

                if not group_model:
                    log.warning(f"Failed to create group: {group_display_name}")
                    continue

            # Group exists, but check if user is already in it
            if group_name_lc not in current_group_map:
                log.info(f"Adding user to existing group {group_model.name}")
                user_ids = group_model.user_ids + [user.id]
                group_permissions = group_model.permissions or default_permissions

                update_form = GroupUpdateForm(
                    name=group_model.name,
                    description=group_model.description,
                    permissions=group_permissions,
                    user_ids=user_ids,
                )
                Groups.update_group_by_id(id=group_model.id, form_data=update_form, overwrite=False)
    
    def get_user_profile_data_from_sso_provider(self, provider: str, token: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user profile data from SSO provider.
        
        Args:
            provider: SSO provider name (google, microsoft, okta)
            token: OAuth2 access token
            
        Returns:
            Dictionary with trusted_email, trusted_name, trusted_profile_image_url or None on error
        """
        log.info(f"[SSO] Fetching user profile data from provider: {provider}")
        
        response = None
        user_image = "/user.png"  # Default fallback
        api_url = None
        
        try:
            match provider:
                case 'google':
                    api_url = "https://openidconnect.googleapis.com/v1/userinfo"
                    log.info(f"[SSO:Google] Making request to: {api_url}")
                    
                    try:
                        response = requests.get(
                            api_url,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=10
                        )
                        log.info(f"[SSO:Google] Response status: {response.status_code}")
                        log.debug(f"[SSO:Google] Response headers: {dict(response.headers)}")
                        
                    except requests.exceptions.Timeout:
                        log.error(f"[SSO:Google] Request timeout after 10s to {api_url}")
                        return None
                    except requests.exceptions.RequestException as e:
                        log.error(f"[SSO:Google] Request failed to {api_url}: {type(e).__name__}: {str(e)}")
                        return None

                case 'microsoft':
                    api_url = "https://graph.microsoft.com/v1.0/me"
                    photo_url = "https://graph.microsoft.com/v1.0/me/photo/$value"
                    
                    log.info(f"[SSO:Microsoft] Making request to: {api_url}")
                    
                    try:
                        response = requests.get(
                            api_url,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=10
                        )
                        log.info(f"[SSO:Microsoft] Profile response status: {response.status_code}")
                        log.debug(f"[SSO:Microsoft] Profile response headers: {dict(response.headers)}")
                        
                        if response.status_code != 200:
                            log.error(f"[SSO:Microsoft] Failed to fetch profile: {response.status_code}")
                            log.error(f"[SSO:Microsoft] Response body: {response.text[:500]}")
                        
                    except requests.exceptions.Timeout:
                        log.error(f"[SSO:Microsoft] Profile request timeout after 10s to {api_url}")
                        return None
                    except requests.exceptions.RequestException as e:
                        log.error(f"[SSO:Microsoft] Profile request failed to {api_url}: {type(e).__name__}: {str(e)}")
                        return None
                    
                    # Fetch profile photo (non-critical)
                    log.info(f"[SSO:Microsoft] Fetching profile photo from: {photo_url}")
                    try:
                        photo_response = requests.get(
                            photo_url,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=10
                        )
                        log.info(f"[SSO:Microsoft] Photo response status: {photo_response.status_code}")
                        
                        if photo_response.status_code == 200:
                            content_type = photo_response.headers.get('Content-Type', 'image/jpeg')
                            image_format = content_type.split('/')[-1] if '/' in content_type else 'jpeg'
                            encoded_image = base64.b64encode(photo_response.content).decode('utf-8')
                            user_image = f"data:image/{image_format};base64,{encoded_image}"
                            log.info(f"[SSO:Microsoft] Successfully fetched profile photo ({len(photo_response.content)} bytes)")
                        elif photo_response.status_code == 404:
                            log.info("[SSO:Microsoft] User has no profile photo set")
                        else:
                            log.warning(f"[SSO:Microsoft] Failed to fetch photo: {photo_response.status_code}")
                            log.debug(f"[SSO:Microsoft] Photo response body: {photo_response.text[:200]}")
                            
                    except requests.exceptions.Timeout:
                        log.warning(f"[SSO:Microsoft] Photo request timeout, using default image")
                    except requests.exceptions.RequestException as e:
                        log.warning(f"[SSO:Microsoft] Photo request failed: {type(e).__name__}: {str(e)}, using default image")

                case 'okta':
                    try:
                        log.info("[SSO:Okta] Decoding JWT token to extract issuer")
                        decoded = jwt.decode(token, options={"verify_signature": False})
                        okta_domain = decoded.get("iss")
                        
                        if not okta_domain:
                            log.error("[SSO:Okta] No 'iss' (issuer) claim found in token")
                            log.debug(f"[SSO:Okta] Token claims: {list(decoded.keys())}")
                            return None
                        
                        api_url = f"{okta_domain}/oauth2/v1/userinfo"
                        log.info(f"[SSO:Okta] Okta domain: {okta_domain}")
                        log.info(f"[SSO:Okta] Making request to: {api_url}")
                        
                        response = requests.get(
                            api_url,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=10
                        )
                        log.info(f"[SSO:Okta] Response status: {response.status_code}")
                        log.debug(f"[SSO:Okta] Response headers: {dict(response.headers)}")
                        
                    except jwt.DecodeError as e:
                        log.error(f"[SSO:Okta] Failed to decode JWT token: {str(e)}")
                        return None
                    except requests.exceptions.Timeout:
                        log.error(f"[SSO:Okta] Request timeout after 10s to {api_url}")
                        return None
                    except requests.exceptions.RequestException as e:
                        log.error(f"[SSO:Okta] Request failed to {api_url}: {type(e).__name__}: {str(e)}")
                        return None
                        
                case _:
                    log.error(f"[SSO] Unsupported provider: {provider}")
                    return None

            # Process response
            if response is None:
                log.error(f"[SSO:{provider.title()}] No response object available")
                return None
                
            if response.status_code == 200:
                try:
                    data = response.json()
                    log.info(f"[SSO:{provider.title()}] Successfully parsed JSON response")
                    log.debug(f"[SSO:{provider.title()}] Response data keys: {list(data.keys())}")
                    
                except ValueError as e:
                    log.error(f"[SSO:{provider.title()}] Failed to parse JSON response: {str(e)}")
                    log.error(f"[SSO:{provider.title()}] Response body: {response.text[:500]}")
                    return None
                
                # Extract user data based on provider
                if provider == 'microsoft':
                    trusted_email = data.get('mail') or data.get('userPrincipalName')
                    trusted_name = data.get('displayName')
                    trusted_profile_image_url = user_image
                    
                    log.info(f"[SSO:Microsoft] Extracted email: {trusted_email}")
                    log.info(f"[SSO:Microsoft] Extracted name: {trusted_name}")
                    log.debug(f"[SSO:Microsoft] Available fields: {list(data.keys())}")
                    
                    if not trusted_email:
                        log.warning("[SSO:Microsoft] No 'mail' or 'userPrincipalName' found in response")
                        
                else:  # google, okta
                    trusted_email = data.get('email')
                    trusted_name = data.get('name')
                    trusted_profile_image_url = data.get('picture')
                    
                    log.info(f"[SSO:{provider.title()}] Extracted email: {trusted_email}")
                    log.info(f"[SSO:{provider.title()}] Extracted name: {trusted_name}")
                    log.info(f"[SSO:{provider.title()}] Profile image URL: {trusted_profile_image_url or 'None'}")

                # Validate required fields
                if not trusted_email:
                    log.error(f"[SSO:{provider.title()}] No email found in user data")
                    log.error(f"[SSO:{provider.title()}] Full response data: {data}")
                    return None

                result = {
                    'trusted_email': trusted_email,
                    'trusted_name': trusted_name,
                    'trusted_profile_image_url': trusted_profile_image_url
                }
                
                log.info(f"[SSO:{provider.title()}] Successfully extracted user profile data")
                return result
                
            else:
                # Non-200 status code
                log.error(f"[SSO:{provider.title()}] Failed to fetch user data: HTTP {response.status_code}")
                log.error(f"[SSO:{provider.title()}] Request URL: {api_url}")
                log.error(f"[SSO:{provider.title()}] Response headers: {dict(response.headers)}")
                log.error(f"[SSO:{provider.title()}] Response body: {response.text[:1000]}")
                
                # Log specific error details based on status code
                if response.status_code == 401:
                    log.error(f"[SSO:{provider.title()}] Unauthorized - Token may be expired or invalid")
                elif response.status_code == 403:
                    log.error(f"[SSO:{provider.title()}] Forbidden - Check OAuth scopes/permissions")
                elif response.status_code == 404:
                    log.error(f"[SSO:{provider.title()}] Not Found - Check API endpoint URL")
                elif response.status_code >= 500:
                    log.error(f"[SSO:{provider.title()}] Server error - Provider may be experiencing issues")
                    
                return None
                
        except Exception as e:
            return None

    def fetch_and_save_user_oauth_tokens(self, user_id: str, provider: str, token: str):
        try:
            match provider:
                case 'google':
                    response = requests.get("https://oauth2.googleapis.com/tokeninfo", headers={"Authorization": f"Bearer {token}"})

                case 'microsoft':
                    response = requests.get("https://graph.microsoft.com/v1.0/me", headers={"Authorization": f"Bearer {token}"})

            if response.status_code == 200:
                data = response.json()
                log.info(f"Response: {data}")
                encrypted_access_token = encrypt_data(token)
                encrypted_refresh_token = encrypt_data(data.get("refresh_token", ""))
                expires_in = int(data.get("expires_in", 3600))
                access_token_expires_at = int(time.time()) + expires_in
                provider_name = provider.capitalize()

                OAuthTokens.insert_new_token(
                    user_id=user_id,
                    provider_name=provider_name,
                    provider_user_id=user_id,
                    encrypted_access_token=encrypted_access_token,
                    encrypted_refresh_token=encrypted_refresh_token,
                    access_token_expires_at=access_token_expires_at,
                    scopes=data.get("scope"), # Space-separated string of granted scopes
                )
                log.info(f"Stored/Updated {provider} OAuth tokens for user {user_id}")
            else:
                log.error(f"Failed to fetch user oauth tokens: {response.status_code} {response}")
                return None
        except Exception as e:
            log.error(f"Error fetching user oauth tokens: {e}")
            return None

    @throttle(DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL)
    def update_user_last_active_by_id(self, id: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update(
                    {"last_active_at": int(time.time())}
                )
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_oauth_sub_by_id(
        self, id: str, oauth_sub: str
    ) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update({"oauth_sub": oauth_sub})
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_by_id(self, id: str, updated: dict) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update(updated)
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
                # return UserModel(**user.dict())
        except Exception as e:
            print(e)
            return None

    def update_user_settings_by_id(self, id: str, updated: dict) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user_settings = db.query(User).filter_by(id=id).first().settings

                if user_settings is None:
                    user_settings = {}

                user_settings.update(updated)

                db.query(User).filter_by(id=id).update({"settings": user_settings})
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def delete_user_by_id(self, id: str) -> bool:
        try:
            # Remove User from Groups
            Groups.remove_user_from_all_groups(id)

            # Delete User Chats
            result = Chats.delete_chats_by_user_id(id)
            if result:
                with get_db() as db:
                    # Delete User
                    db.query(User).filter_by(id=id).delete()
                    db.commit()

                return True
            else:
                return False
        except Exception:
            return False

    def update_user_api_key_by_id(self, id: str, api_key: str) -> bool:
        try:
            with get_db() as db:
                result = db.query(User).filter_by(id=id).update({"api_key": api_key})
                db.commit()
                return True if result == 1 else False
        except Exception:
            return False

    def get_user_api_key_by_id(self, id: str) -> Optional[str]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(id=id).first()
                return user.api_key
        except Exception:
            return None

    def get_valid_user_ids(self, user_ids: list[str]) -> list[str]:
        with get_db() as db:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            return [user.id for user in users]

    def get_super_admin_user(self) -> Optional[UserModel]:
        with get_db() as db:
            user = db.query(User).filter_by(role="admin").first()
            if user:
                return UserModel.model_validate(user)
            else:
                return None


Users = UsersTable()
