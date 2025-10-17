import logging
import time
import uuid
from typing import Optional, List

from open_webui.internal.db import Base, JSONField, get_db
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, JSON

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

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

    MINERAL_CLIENT_ID,
    MINERAL_CLIENT_SECRET,
    MINERAL_REDIRECT_URI,

    MINERAL_BASE_URL,
    MINERAL_AUTHORIZE_URL,
    MINERAL_TOKEN_URL,

    GCS_BUCKET_NAME,
    GCS_SERVICE_ACCOUNT_BASE64
)

####################
# Data Sources DB Schema
####################


class DataSource(Base):
    __tablename__ = "data_source"
    id = Column(String, primary_key=True)
    user_id = Column(String)
    
    name = Column(Text)
    context = Column(Text, nullable=True)
    permission = Column(String, nullable=True)  # Store permissions as a string
    sync_status = Column(String, default="unsynced")  # synced, syncing, embedded, unsynced, deleting, deleted
    last_sync = Column(BigInteger, nullable=True)
    # Progress tracking fields
    files_processed = Column(BigInteger, default=0)
    files_total = Column(BigInteger, default=0)
    mb_processed = Column(BigInteger, default=0)  # bytes
    mb_total = Column(BigInteger, default=0)      # bytes
    sync_start_time = Column(BigInteger, nullable=True)  # timestamp when sync started
    icon = Column(String)
    action = Column(String, nullable=True)
    layer = Column(String, nullable=True)
    
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class DataSourceModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    context: Optional[str] = None
    permission: Optional[str] = None
    sync_status: str = "unsynced"
    last_sync: Optional[int] = None  # timestamp in epoch
    # Progress tracking fields
    files_processed: Optional[int] = 0
    files_total: Optional[int] = 0
    mb_processed: Optional[int] = 0  # bytes
    mb_total: Optional[int] = 0      # bytes
    sync_start_time: Optional[int] = None  # timestamp when sync started
    icon: str
    action: Optional[str] = None
    layer: Optional[str] = None
    
    created_at: Optional[int]  # timestamp in epoch
    updated_at: Optional[int]  # timestamp in epoch


####################
# Forms
####################


class DataSourceForm(BaseModel):
    id: str
    name: str
    context: Optional[str] = None
    permission: Optional[str] = None
    sync_status: str = "unsynced"
    last_sync: Optional[int] = None
    # Progress tracking fields
    files_processed: Optional[int] = 0
    files_total: Optional[int] = 0
    mb_processed: Optional[int] = 0  # bytes
    mb_total: Optional[int] = 0      # bytes
    sync_start_time: Optional[int] = None  # timestamp when sync started
    icon: str
    action: Optional[str] = None
    layer: Optional[str] = None


class DataSourceResponse(BaseModel):
    id: str
    user_id: str
    name: str
    context: Optional[str] = None
    permission: Optional[str] = None
    sync_status: str
    last_sync: Optional[int] = None
    # Progress tracking fields
    files_processed: Optional[int] = None
    files_total: Optional[int] = None
    mb_processed: Optional[int] = None
    mb_total: Optional[int] = None
    sync_start_time: Optional[int] = None
    icon: str
    action: Optional[str] = None
    layer: Optional[str] = None
    created_at: int
    updated_at: int

    model_config = ConfigDict(extra="allow")


class DataSourcesTable:
    # Default data sources
    DEFAULT_DATA_SOURCES = [
        {
            "name": "Google Drive",
            "context": "Docs, sheets, slides",
            "permission": "https://www.googleapis.com/auth/drive.readonly",
            "sync_status": "unsynced",
            "icon": "GoogleDrive",
            "action": "google",
            "layer": "google_drive",
            "config_status": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI and GOOGLE_AUTHORIZE_URL and GOOGLE_TOKEN_URL and GOOGLE_AUTH_REVOKE_URL)
        },
        {
            "name": "Gmail",
            "context": "Emails & attachements",
            "permission": "https://www.googleapis.com/auth/gmail.readonly",
            "sync_status": "unsynced",
            "icon": "Gmail",
            "action": "google",
            "layer": "gmail",
            "config_status": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI and GOOGLE_AUTHORIZE_URL and GOOGLE_TOKEN_URL and GOOGLE_AUTH_REVOKE_URL)
        },
        { 
            "name": "Outlook",
            "context": "Emails & attachments",
            "permission": "Mail.Read",
            "sync_status": "unsynced",
            "icon": "Outlook",
            "action": "microsoft",
            "layer": "outlook",
            "config_status": bool( MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET and MICROSOFT_REDIRECT_URI and MICROSOFT_AUTHORIZE_URL and MICROSOFT_TOKEN_URL)
        },
        { 
            "name": "OneDrive",
            "context": "Files and folders",
            "permission": "Files.Read.All",
            "sync_status": "unsynced",
            "icon": "OneDrive",
            "action": "microsoft",
            "layer": "onedrive",
            "config_status": bool( MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET and MICROSOFT_REDIRECT_URI and MICROSOFT_AUTHORIZE_URL and MICROSOFT_TOKEN_URL)
        },
        { 
            "name": "Sharepoint",
            "context": "Sites and files",
            "permission": "Sites.Read.All, Files.Read.All",
            "sync_status": "unsynced",
            "icon": "Sharepoint",
            "action": "microsoft",
            "layer": "sharepoint",
            "config_status": bool( MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET and MICROSOFT_REDIRECT_URI and MICROSOFT_AUTHORIZE_URL and MICROSOFT_TOKEN_URL)
        },
        { 
            "name": "OneNote",
            "context": "Notes",
            "permission": "Notes.Read",
            "sync_status": "unsynced",
            "icon": "OneNote",
            "action": "microsoft",
            "layer": "onenote",
            "config_status": bool( MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET and MICROSOFT_REDIRECT_URI and MICROSOFT_AUTHORIZE_URL and MICROSOFT_TOKEN_URL)
        },
        {
            "name": "Slack Direct Messages",
            "context": "Direct messages",
            "permission": "im:history, im:read",
            "sync_status": "unsynced",
            "icon": "Slack",
            "action": "slack",
            "layer": "direct_messages",
            "config_status": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET and SLACK_REDIRECT_URI and SLACK_AUTHORIZE_URL and SLACK_TOKEN_URL and SLACK_AUTH_REVOKE_URL)
        },
        {
            "name": "Slack Channels",
            "context": "Channels conversations",
            "permission": "channels:history, channels:read",
            "sync_status": "unsynced",
            "icon": "Slack",
            "action": "slack",
            "layer": "channels",
            "config_status": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET and SLACK_REDIRECT_URI and SLACK_AUTHORIZE_URL and SLACK_TOKEN_URL and SLACK_AUTH_REVOKE_URL)
        },
        {
            "name": "Slack Group Chats",
            "context": "Group chats",
            "permission": "groups:history, groups:read, mpim:history, mpim:read",
            "sync_status": "unsynced",
            "icon": "Slack",
            "action": "slack",
            "layer": "group_chats",
            "config_status": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET and SLACK_REDIRECT_URI and SLACK_AUTHORIZE_URL and SLACK_TOKEN_URL and SLACK_AUTH_REVOKE_URL)
        },
        {
            "name": "Slack Files & Canvases",
            "context": "Files & canvases",
            "permission": "files:read",
            "sync_status": "unsynced",
            "icon": "Slack",
            "action": "slack",
            "layer": "files",
            "config_status": bool(SLACK_CLIENT_ID and SLACK_CLIENT_SECRET and SLACK_REDIRECT_URI and SLACK_AUTHORIZE_URL and SLACK_TOKEN_URL and SLACK_AUTH_REVOKE_URL)
        },
        {
            "name": "Jira",
            "context": "Projects & issues",
            "permission": "read:user:jira,read:issue:jira,read:comment:jira,read:attachment:jira,read:project:jira,read:issue-meta:jira,read:field:jira,read:filter:jira,read:jira-work,read:jira-user,read:me,read:account,report:personal-data",
            "sync_status": "unsynced",
            "icon": "JIRA",
            "action": "atlassian",
            "layer": "jira",
            "config_status": bool(ATLASSIAN_API_GATEWAY and ATLASSIAN_AUTHORIZE_URL and ATLASSIAN_TOKEN_URL and ATLASSIAN_CLIENT_ID and ATLASSIAN_CLIENT_SECRET and ATLASSIAN_REDIRECT_URL)
        },
        {
            "name": "Confluence",
            "context": "Pages & spaces",
            "permission": "read:content:confluence,read:space:confluence,read:page:confluence,read:blogpost:confluence,read:attachment:confluence,read:comment:confluence,read:user:confluence,read:group:confluence,read:configuration:confluence,search:confluence,read:audit-log:confluence",
            "sync_status": "unsynced",
            "icon": "Confluence",
            "action": "atlassian",
            "layer": "confluence",
            "config_status": bool(ATLASSIAN_API_GATEWAY and ATLASSIAN_AUTHORIZE_URL and ATLASSIAN_TOKEN_URL and ATLASSIAN_CLIENT_ID and ATLASSIAN_CLIENT_SECRET and ATLASSIAN_REDIRECT_URL)
        },
        {
            "name": "Mineral Handbooks",
            "context": "Handbook",
            "permission": "read:handbooks, read:profile",
            "sync_status": "unsynced",
            "icon": "Mineral",
            "action": "mineral",
            "layer": "handbooks",
            "config_status": bool(MINERAL_AUTHORIZE_URL and MINERAL_BASE_URL and MINERAL_CLIENT_ID and MINERAL_REDIRECT_URI and MINERAL_TOKEN_URL and MINERAL_CLIENT_SECRET)
        }
    ]

    def create_default_data_sources_for_user(self, user_id: str) -> List[DataSourceModel]:
        """Create default data sources for a new user (only if they don't already exist)"""
        created_sources = []
        
        # Get existing data source names for this user
        existing_source_names = self.get_existing_data_source_names(user_id)
        
        for default_source in self.DEFAULT_DATA_SOURCES:
            # Skip if this default source already exists for the user
            if default_source["name"] in existing_source_names:
                continue

            # if default_source["config_status"] is not True:
            #     continue
                
            # Create unique ID for this user's data source
            unique_id = f"{user_id}_{uuid.uuid4()}"
            
            form_data = DataSourceForm(
                id=unique_id,
                name=default_source["name"],
                context=default_source["context"],
                permission=default_source["permission"],
                sync_status=default_source["sync_status"],
                icon=default_source["icon"],
                action=default_source["action"],
                layer=default_source['layer']
            )

            log.info(f"Data Sources created for user {user_id}, form: {form_data}")
            
            created_source = self.insert_new_data_source(user_id, form_data)
            if created_source:
                created_sources.append(created_source)

        log.info(f"Data Sources created for user {user_id}, source: {created_sources}")
                
        return created_sources

    def get_existing_data_source_names(self, user_id: str) -> set:
        """Get set of existing data source names for a user"""
        with get_db() as db:
            try:
                existing_names = db.query(DataSource.name).filter(
                    DataSource.user_id == user_id
                ).all()
                return {name[0] for name in existing_names}
            except Exception as e:
                log.exception(f"Error fetching existing data source names: {e}")
                return set()

    def insert_new_data_source(self, user_id: str, form_data: DataSourceForm) -> Optional[DataSourceModel]:
        with get_db() as db:
            data_source = DataSourceModel(
                **{
                    **form_data.model_dump(),
                    "user_id": user_id,
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                }
            )

            try:
                result = DataSource(**data_source.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return DataSourceModel.model_validate(result)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error inserting a new data source: {e}")
                return None

    def get_data_source_by_id(self, id: str) -> Optional[DataSourceModel]:
        with get_db() as db:
            try:
                data_source = db.get(DataSource, id)
                return DataSourceModel.model_validate(data_source) if data_source else None
            except Exception:
                return None

    def get_data_sources_by_user_id(self, user_id: str) -> List[DataSourceModel]:
        """Get all data sources for a specific user"""
        with get_db() as db:
            try:
                return [
                    DataSourceModel.model_validate(data_source)
                    for data_source in db.query(DataSource)
                    .filter_by(user_id=user_id)
                    .order_by(DataSource.updated_at.desc())
                    .all()
                ]
            except Exception as e:
                log.exception(f"Error getting data sources for user {user_id}: {e}")
                return []

    def get_all_data_sources(self) -> List[DataSourceModel]:
        with get_db() as db:
            return [
                DataSourceModel.model_validate(data_source) 
                for data_source in db.query(DataSource).all()
            ]

    def update_data_source_sync_status_by_name(
        self, 
        user_id: str, 
        source_name: str, 
        layer_name: str,
        sync_status: str, 
        last_sync: Optional[int] = None,
        files_processed: Optional[int] = None,
        files_total: Optional[int] = None,
        mb_processed: Optional[int] = None,
        mb_total: Optional[int] = None,
        sync_start_time: Optional[int] = None
    ) -> Optional[DataSourceModel]:
        """
        Updates the sync status and last sync time for a data source,
        identified by user ID and its name.

        Args:
            user_id (str): The ID of the user whose data source is to be updated.
            source_name (str): The name of the data source to update (e.g., "Slack").
            sync_status (str): The new synchronization status (e.g., "synced", "syncing", "error", "deleting", "deleted").
            last_sync (Optional[int]): The new last sync timestamp in epoch. Defaults to current time if None.
            files_processed (Optional[int]): Number of files processed so far.
            files_total (Optional[int]): Total number of files to process.
            mb_processed (Optional[int]): Number of bytes processed so far.
            mb_total (Optional[int]): Total number of bytes to process.
            sync_start_time (Optional[int]): Timestamp when sync started.

        Returns:
            Optional[DataSourceModel]: The updated DataSourceModel if found and updated, None otherwise.
        """
        with get_db() as db:
            try:
                # Find the data source by user_id and name
                data_source = db.query(DataSource).filter_by(
                    user_id=user_id,
                    name=source_name,
                    layer=layer_name
                ).first()

                if data_source:
                    # Update only the specified fields
                    data_source.sync_status = sync_status
                    if last_sync is not None: # Check explicitly for None, not just truthiness
                        data_source.last_sync = last_sync
                    if files_processed is not None:
                        data_source.files_processed = files_processed
                    if files_total is not None:
                        data_source.files_total = files_total
                    if mb_processed is not None:
                        data_source.mb_processed = mb_processed
                    if mb_total is not None:
                        data_source.mb_total = mb_total
                    if sync_start_time is not None:
                        data_source.sync_start_time = sync_start_time
                    else:
                        data_source.last_sync = int(time.time()) # Set to current time if not provided

                    # Always update the `updated_at` timestamp
                    data_source.updated_at = int(time.time())
                    db.commit()
                    db.refresh(data_source) # Refresh to get latest data from DB


                    log.info(f"Successfully updated sync status for data source '{source_name}' to '{sync_status}' for user {user_id}.")
                    return DataSourceModel.model_validate(data_source)
                else:
                    log.warning(f"Data source with name '{source_name}' not found for user {user_id}. No update performed.")
                    return None
            except Exception as e:
                log.exception(f"Error updating data source sync status by name '{source_name}' for user {user_id}: {e}")
                db.rollback() # Ensure rollback on error
                return None

    def update_data_source_by_id(self, id: str, form_data: DataSourceForm) -> Optional[DataSourceModel]:
        with get_db() as db:
            try:
                data_source = db.query(DataSource).filter_by(id=id).first()
                if data_source:
                    for key, value in form_data.model_dump(exclude_unset=True).items():
                        if key != "id":  # Don't update the ID
                            setattr(data_source, key, value)
                    data_source.updated_at = int(time.time())
                    db.commit()
                    return DataSourceModel.model_validate(data_source)
                return None
            except Exception as e:
                log.exception(f"Error updating data source: {e}")
                return None

    def delete_data_source_by_id(self, id: str) -> bool:
        with get_db() as db:
            try:
                db.query(DataSource).filter_by(id=id).delete()
                db.commit()
                return True
            except Exception as e:
                log.exception(f"Error deleting data source: {e}")
                return False

    def delete_all_data_sources_for_user(self, user_id: str) -> bool:
        with get_db() as db:
            try:
                db.query(DataSource).filter_by(user_id=user_id).delete()
                db.commit()
                return True
            except Exception as e:
                log.exception(f"Error deleting all data sources for user: {e}")
                return False


DataSources = DataSourcesTable()