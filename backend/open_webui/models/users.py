import requests
import time
import logging
import sys
from typing import Optional

import jwt

import base64

from open_webui.internal.db import Base, JSONField, get_db

from open_webui.utils.data.google import initiate_google_file_sync
from open_webui.utils.data.microsoft import sync_microsoft_to_gcs

from open_webui.models.chats import Chats
from open_webui.models.groups import Groups, GroupModel, GroupUpdateForm, GroupForm


from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text

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
    role = Column(String)
    profile_image_url = Column(Text)

    last_active_at = Column(BigInteger)
    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)

    api_key = Column(String, nullable=True, unique=True)
    settings = Column(JSONField, nullable=True)
    info = Column(JSONField, nullable=True)

    oauth_sub = Column(Text, unique=True)


class UserSettings(BaseModel):
    ui: Optional[dict] = {}
    model_config = ConfigDict(extra="allow")
    pass


class UserModel(BaseModel):
    id: str
    name: str
    email: str
    role: str = "pending"
    profile_image_url: str

    last_active_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    api_key: Optional[str] = None
    settings: Optional[UserSettings] = None
    info: Optional[dict] = None

    oauth_sub: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


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
        self, skip: Optional[int] = None, limit: Optional[int] = None
    ) -> list[UserModel]:
        with get_db() as db:

            query = db.query(User).order_by(User.created_at.desc())

            if skip:
                query = query.offset(skip)
            if limit:
                query = query.limit(limit)

            users = query.all()

            return [UserModel.model_validate(user) for user in users]

    def get_users_by_user_ids(self, user_ids: list[str]) -> list[UserModel]:
        with get_db() as db:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            return [UserModel.model_validate(user) for user in users]

    def get_num_users(self) -> Optional[int]:
        with get_db() as db:
            return db.query(User).count()

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
    
    def get_user_profile_data_from_sso_provider(self, provider: str, token: str):
        try:
            match provider:
                case 'google':
                    response = requests.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {token}"})

                case 'microsoft entra id':
                    response = requests.get("https://graph.microsoft.com/v1.0/me", headers={"Authorization": f"Bearer {token}"})
                    photo_response = requests.get("https://graph.microsoft.com/v1.0/me/photo/$value", headers={"Authorization": f"Bearer {token}"})

                    if photo_response.status_code == 200:
                        encoded_image = base64.b64encode(photo_response.content).decode('utf-8')
                        user_image = f"data:image/jpeg;base64,{encoded_image}"
        
                case 'okta':
                    decoded = jwt.decode(token, options={"verify_signature": False})
                    oktaDomain = decoded["iss"]
                    response = requests.get(f"{oktaDomain}/oauth2/v1/userinfo", headers={"Authorization": f"Bearer {token}"})

            if response.status_code == 200:
                data = response.json()
                trusted_email = data.get('email', None) or data.get('mail', None)
                trusted_name = data.get('name', None) or data.get('displayName', None)
                trusted_profile_image_url = data.get('picture') or user_image

                return {
                    'trusted_email': trusted_email,
                    'trusted_name': trusted_name,
                    'trusted_profile_image_url': trusted_profile_image_url
                }
            else:
                log.error(f"Failed to fetch user data: {response.status_code} {response}")
                return None
        except Exception as e:
            log.error(f"Error fetching user data: {e}")
            return None

    def get_user_file_data_from_sso_provider(self, user_id: str, provider: str, token: str):
        try:
            match provider:
                case 'google':
                    initiate_google_file_sync(user_id, token, 'ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAibmgtc2FuZGJveC00NTEzMDkiLAogICJwcml2YXRlX2tleV9pZCI6ICJlZmU2OGIyZjU4OTdiZTI2MzliODhkNmI3NDIxYTZlMjMwY2I5ODkwIiwKICAicHJpdmF0ZV9rZXkiOiAiLS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tXG5NSUlFdlFJQkFEQU5CZ2txaGtpRzl3MEJBUUVGQUFTQ0JLY3dnZ1NqQWdFQUFvSUJBUURyK1NPR3FwckR4NUtwXG5YZ0hSdnZvYmJRUjlINWVqaENXYVlOUy9WalpQNFFvZlk5ZXhyaG5qSkNwVnBtbXFLVjBoOURnN2tkazhOQ1BtXG5pM1JQRW5QWUYyc1Z6dDZkb0d1VmVRTlcwNGxHOUJWWGdvUFI1emRiRlZpdjY3WTRyRUt5Umt3S3YyQlJnaXUrXG5hSHBXQTRsUFJkaGplSUVZL3NjZHBnL0J5K1JpNkgzNVRnZ3dzdGpRd2V4TUp6eCsrL1dUaStrSnhSK3crTGY1XG5SSnZtbnpSWFBOOUQ2Z1FvUFhraXZUUHJUa3o2WWxmZVVaS0FBV1lQS204UmFRZUZQcTdSWVUxNCtiTld6a2dTXG5NTkpleTVhVVhQNUxjZmhaTjFKcWkzTHNaV3JnYjR5cFBmUkxGTkNRMGgzUmVKSXVLbzdzMndZbzQ5V3ZhQ1JXXG5xSmNKVEc5SkFnTUJBQUVDZ2dFQUl3R0xhK1dndm5UN2xKMFJ5NFlYajl5Qkd6ZkYxTmZjaFRXaXNmek40MVU0XG4zWFhBRUllSnB4amRIK1luVER0RktlMlRMd0VndHkzcituNUxJNVRTOHlac09DaS9mU1pJZDN6amlpeW84NG52XG5wWk1DejYrTGxudEk5QllWYXZ4aEM1WGluNENLL3lSK3JVbE9CcmNSRmwyLzcyZTN6UmUwdmJqK0l1dUdwc1phXG5PNFdXbTJyTE51dU9QZ3d6eDBvdzNldjdXUktRanIxMUhlQnZXa0ZxbW9xQ2F5Zkg4WmxTQ2NvbzE2bHcrd0UrXG5YSlZEc1NnTEc3MWl2Y3pUTUl3UWl5YkJSOFhuUUVXNm1OcTVzSWRxSFZJSW1BTXgrQWQyOUZUQ2JvMFpSL3JmXG5RUS8vT3VjSVE4QkUxVHhDZ3ZmZ1Y3RFlSdnZjcW54YXJwc0djK2lobFFLQmdRRCtzMHpJaTFTeWJvWWttYlpnXG5DUDVqYVIvS0JkQjczNG9rZWdCQlBTTk5YTXhGRWgrZDJ1S2ZyMnhFUThqRHRDT1k2VkxZb1plc0FKaEljTksxXG40VnhMbmlFSWpyK082VnpoTU1nbkd2LzB2TVROb3lMUW9QRk14WGFiSHIxYisrTWhpVUJGS01pNTM0V2g5UmlyXG5pQ3hPTDdrcWNNSUdsYnhhQmRRRFF3cXBSUUtCZ1FEdExXQnB6eFJKZWxBaFFxcHRGRmtibDdpZ1dvZGhrU1MvXG5MMnB6RjYvUmQzaW5lVzBvWGc0ZmNXQW05aVZxbk9wWjBxWW5QcWVMdTR4ZGRSc1U5Tk9veUIwMFI0VldZVXFsXG5RNHp0RmlXMVBmL3pkbEZ1N1ZPTTJ1cTB0V2s4YVRpNWc5OVEvU1ppWTBQUmtBejlmYzdTYWsxVFdvdjVHbEROXG44YVoyZ2tZVU5RS0JnQXFvQ2RCaU0vcjdNTldiTU13MzFCem9xeEhTeUhSR1dBdEtwM1FUVU1UTjJ5WVFxZzM2XG51SHloNUUrKzNrbUI0Zk5sMzdkOG0xSHcvRzRiZWxWdHhtVExpdXBHdnJFR0JvTE5mYkpWS054ZWdZVnhDK1hhXG50ZjNXVFM0VVRTdnFFQWk1SzEwNVpaeVJRNUFSSnlVV0gzUnQvcnROMkhCYUYzVlV4UmdWMS81WkFvR0FES015XG5VL0Q0djhHSXEzMEYzN0lKM1hLRUgrY3k5M3ZvWFZlRmNJUitsY2FyNHlDUk5HbHVqelpYVFR3b1dqbnFNc2NLXG5tMlMzUUxiSmorRkJoQ2hYYnRMYTI0SkVGSW95bEFPNWFwaVhnY1MvOHBVSFdjWERnZW5ZUDdDNjNzRXNpSllDXG5QQ3FBOVJVYzgvbWM5NVRRaEYydHFSZFdCZnZrK2xRNTdtNmFsVkVDZ1lFQXQ3UGtmUnhPWFR6cFVEWFBpdklOXG5zVWpjcFU4TVVSK0VqUW1QV1F3V1ZyTWJhWEpQanVRY3ZOTGlNQWhtRlQrSHphU2tCMFhFRktGZExuQ1FxV1lMXG5LcE90S1lldUJBb0picEx4NFFxRjBoZU5OdXZMNHYyQTVkeGVEQTVlNHpkcnl0bzVqQWN3TDAyTDFPdTJKVzY0XG5pb05wUFJpNHl0VjI0UUNOdENpL1dRQT1cbi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS1cbiIsCiAgImNsaWVudF9lbWFpbCI6ICJnZHJpdmUtZ2NzLXN5bmNAbmgtc2FuZGJveC00NTEzMDkuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJjbGllbnRfaWQiOiAiMTEyNTU0OTg2NzUzMDIyMDQ0NTk5IiwKICAiYXV0aF91cmkiOiAiaHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL28vb2F1dGgyL2F1dGgiLAogICJ0b2tlbl91cmkiOiAiaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW4iLAogICJhdXRoX3Byb3ZpZGVyX3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vb2F1dGgyL3YxL2NlcnRzIiwKICAiY2xpZW50X3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vcm9ib3QvdjEvbWV0YWRhdGEveDUwOS9nZHJpdmUtZ2NzLXN5bmMlNDBuaC1zYW5kYm94LTQ1MTMwOS5pYW0uZ3NlcnZpY2VhY2NvdW50LmNvbSIsCiAgInVuaXZlcnNlX2RvbWFpbiI6ICJnb29nbGVhcGlzLmNvbSIKfQo=', 'nh-private-ai-file-sync-test')
                case 'microsoft entra id':
                    sync_microsoft_to_gcs(user_id, token, 'ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAibmgtc2FuZGJveC00NTEzMDkiLAogICJwcml2YXRlX2tleV9pZCI6ICJlZmU2OGIyZjU4OTdiZTI2MzliODhkNmI3NDIxYTZlMjMwY2I5ODkwIiwKICAicHJpdmF0ZV9rZXkiOiAiLS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tXG5NSUlFdlFJQkFEQU5CZ2txaGtpRzl3MEJBUUVGQUFTQ0JLY3dnZ1NqQWdFQUFvSUJBUURyK1NPR3FwckR4NUtwXG5YZ0hSdnZvYmJRUjlINWVqaENXYVlOUy9WalpQNFFvZlk5ZXhyaG5qSkNwVnBtbXFLVjBoOURnN2tkazhOQ1BtXG5pM1JQRW5QWUYyc1Z6dDZkb0d1VmVRTlcwNGxHOUJWWGdvUFI1emRiRlZpdjY3WTRyRUt5Umt3S3YyQlJnaXUrXG5hSHBXQTRsUFJkaGplSUVZL3NjZHBnL0J5K1JpNkgzNVRnZ3dzdGpRd2V4TUp6eCsrL1dUaStrSnhSK3crTGY1XG5SSnZtbnpSWFBOOUQ2Z1FvUFhraXZUUHJUa3o2WWxmZVVaS0FBV1lQS204UmFRZUZQcTdSWVUxNCtiTld6a2dTXG5NTkpleTVhVVhQNUxjZmhaTjFKcWkzTHNaV3JnYjR5cFBmUkxGTkNRMGgzUmVKSXVLbzdzMndZbzQ5V3ZhQ1JXXG5xSmNKVEc5SkFnTUJBQUVDZ2dFQUl3R0xhK1dndm5UN2xKMFJ5NFlYajl5Qkd6ZkYxTmZjaFRXaXNmek40MVU0XG4zWFhBRUllSnB4amRIK1luVER0RktlMlRMd0VndHkzcituNUxJNVRTOHlac09DaS9mU1pJZDN6amlpeW84NG52XG5wWk1DejYrTGxudEk5QllWYXZ4aEM1WGluNENLL3lSK3JVbE9CcmNSRmwyLzcyZTN6UmUwdmJqK0l1dUdwc1phXG5PNFdXbTJyTE51dU9QZ3d6eDBvdzNldjdXUktRanIxMUhlQnZXa0ZxbW9xQ2F5Zkg4WmxTQ2NvbzE2bHcrd0UrXG5YSlZEc1NnTEc3MWl2Y3pUTUl3UWl5YkJSOFhuUUVXNm1OcTVzSWRxSFZJSW1BTXgrQWQyOUZUQ2JvMFpSL3JmXG5RUS8vT3VjSVE4QkUxVHhDZ3ZmZ1Y3RFlSdnZjcW54YXJwc0djK2lobFFLQmdRRCtzMHpJaTFTeWJvWWttYlpnXG5DUDVqYVIvS0JkQjczNG9rZWdCQlBTTk5YTXhGRWgrZDJ1S2ZyMnhFUThqRHRDT1k2VkxZb1plc0FKaEljTksxXG40VnhMbmlFSWpyK082VnpoTU1nbkd2LzB2TVROb3lMUW9QRk14WGFiSHIxYisrTWhpVUJGS01pNTM0V2g5UmlyXG5pQ3hPTDdrcWNNSUdsYnhhQmRRRFF3cXBSUUtCZ1FEdExXQnB6eFJKZWxBaFFxcHRGRmtibDdpZ1dvZGhrU1MvXG5MMnB6RjYvUmQzaW5lVzBvWGc0ZmNXQW05aVZxbk9wWjBxWW5QcWVMdTR4ZGRSc1U5Tk9veUIwMFI0VldZVXFsXG5RNHp0RmlXMVBmL3pkbEZ1N1ZPTTJ1cTB0V2s4YVRpNWc5OVEvU1ppWTBQUmtBejlmYzdTYWsxVFdvdjVHbEROXG44YVoyZ2tZVU5RS0JnQXFvQ2RCaU0vcjdNTldiTU13MzFCem9xeEhTeUhSR1dBdEtwM1FUVU1UTjJ5WVFxZzM2XG51SHloNUUrKzNrbUI0Zk5sMzdkOG0xSHcvRzRiZWxWdHhtVExpdXBHdnJFR0JvTE5mYkpWS054ZWdZVnhDK1hhXG50ZjNXVFM0VVRTdnFFQWk1SzEwNVpaeVJRNUFSSnlVV0gzUnQvcnROMkhCYUYzVlV4UmdWMS81WkFvR0FES015XG5VL0Q0djhHSXEzMEYzN0lKM1hLRUgrY3k5M3ZvWFZlRmNJUitsY2FyNHlDUk5HbHVqelpYVFR3b1dqbnFNc2NLXG5tMlMzUUxiSmorRkJoQ2hYYnRMYTI0SkVGSW95bEFPNWFwaVhnY1MvOHBVSFdjWERnZW5ZUDdDNjNzRXNpSllDXG5QQ3FBOVJVYzgvbWM5NVRRaEYydHFSZFdCZnZrK2xRNTdtNmFsVkVDZ1lFQXQ3UGtmUnhPWFR6cFVEWFBpdklOXG5zVWpjcFU4TVVSK0VqUW1QV1F3V1ZyTWJhWEpQanVRY3ZOTGlNQWhtRlQrSHphU2tCMFhFRktGZExuQ1FxV1lMXG5LcE90S1lldUJBb0picEx4NFFxRjBoZU5OdXZMNHYyQTVkeGVEQTVlNHpkcnl0bzVqQWN3TDAyTDFPdTJKVzY0XG5pb05wUFJpNHl0VjI0UUNOdENpL1dRQT1cbi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS1cbiIsCiAgImNsaWVudF9lbWFpbCI6ICJnZHJpdmUtZ2NzLXN5bmNAbmgtc2FuZGJveC00NTEzMDkuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLAogICJjbGllbnRfaWQiOiAiMTEyNTU0OTg2NzUzMDIyMDQ0NTk5IiwKICAiYXV0aF91cmkiOiAiaHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tL28vb2F1dGgyL2F1dGgiLAogICJ0b2tlbl91cmkiOiAiaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW4iLAogICJhdXRoX3Byb3ZpZGVyX3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vb2F1dGgyL3YxL2NlcnRzIiwKICAiY2xpZW50X3g1MDlfY2VydF91cmwiOiAiaHR0cHM6Ly93d3cuZ29vZ2xlYXBpcy5jb20vcm9ib3QvdjEvbWV0YWRhdGEveDUwOS9nZHJpdmUtZ2NzLXN5bmMlNDBuaC1zYW5kYm94LTQ1MTMwOS5pYW0uZ3NlcnZpY2VhY2NvdW50LmNvbSIsCiAgInVuaXZlcnNlX2RvbWFpbiI6ICJnb29nbGVhcGlzLmNvbSIKfQo=', 'nh-private-ai-file-sync-test', True, True)
                
        except Exception as e:
            log.error(f"Error fetching user data: {e}")
            return None
    
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
        except Exception:
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

    def update_user_api_key_by_id(self, id: str, api_key: str) -> str:
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


Users = UsersTable()
