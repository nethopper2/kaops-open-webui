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

####################
# Data Sources DB Schema
####################


class DataSource(Base):
    __tablename__ = "data_source"
    id = Column(String, primary_key=True)
    user_id = Column(String)
    
    name = Column(Text)
    context = Column(Text, nullable=True)
    sync_status = Column(String, default="unsynced")  # synced, syncing, error, unsynced
    last_sync = Column(BigInteger, nullable=True)
    icon = Column(String)
    action = Column(String, nullable=True)
    
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class DataSourceModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    context: Optional[str] = None
    sync_status: str = "unsynced"
    last_sync: Optional[int] = None  # timestamp in epoch
    icon: str
    action: Optional[str] = None
    
    created_at: Optional[int]  # timestamp in epoch
    updated_at: Optional[int]  # timestamp in epoch


####################
# Forms
####################


class DataSourceForm(BaseModel):
    id: str
    name: str
    context: Optional[str] = None
    sync_status: str = "unsynced"
    last_sync: Optional[int] = None
    icon: str
    action: Optional[str] = None


class DataSourceResponse(BaseModel):
    id: str
    user_id: str
    name: str
    context: Optional[str] = None
    sync_status: str
    last_sync: Optional[int] = None
    icon: str
    action: Optional[str] = None
    created_at: int
    updated_at: int

    model_config = ConfigDict(extra="allow")


class DataSourcesTable:
    # Default data sources template
    DEFAULT_DATA_SOURCES = [
        {
            "name": "Google File Storage",
            "context": "Google Drive",
            "sync_status": "unsynced",
            "icon": "Google",
            "action": "google"
        },
        { 
            "name": "Microsoft Office 365 File Storage",
            "context": "OneDrive & SharePoint",
            "sync_status": "unsynced",
            "icon": "Microsoft",
            "action": "microsoft"
        },
        {
            "name": "Slack",
            "context": "Direct Messages, Channels, Group Chats, Files & Canvases",
            "sync_status": "unsynced",
            "icon": "Slack",
            "action": "slack"
        }
    ]

    def create_default_data_sources_for_user(self, user_id: str) -> List[DataSourceModel]:
        """Create default data sources for a new user"""
        created_sources = []
        
        for default_source in self.DEFAULT_DATA_SOURCES:
            # Create unique ID for this user's data source
            unique_id = f"{user_id}_{uuid.uuid4()}"
            
            form_data = DataSourceForm(
                id=unique_id,
                name=default_source["name"],
                context=default_source["context"],
                sync_status=default_source["sync_status"],
                icon=default_source["icon"],
                action=default_source["action"]
            )
            
            created_source = self.insert_new_data_source(user_id, form_data)
            if created_source:
                created_sources.append(created_source)
                
        return created_sources

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
        sync_status: str, 
        last_sync: Optional[int] = None
    ) -> Optional[DataSourceModel]:
        """
        Updates the sync status and last sync time for a data source,
        identified by user ID and its name.

        Args:
            user_id (str): The ID of the user whose data source is to be updated.
            source_name (str): The name of the data source to update (e.g., "Slack").
            sync_status (str): The new synchronization status (e.g., "synced", "syncing", "error").
            last_sync (Optional[int]): The new last sync timestamp in epoch. Defaults to current time if None.

        Returns:
            Optional[DataSourceModel]: The updated DataSourceModel if found and updated, None otherwise.
        """
        with get_db() as db:
            try:
                # Find the data source by user_id and name
                data_source = db.query(DataSource).filter_by(
                    user_id=user_id,
                    name=source_name
                ).first()

                if data_source:
                    # Update only the specified fields
                    data_source.sync_status = sync_status
                    if last_sync is not None: # Check explicitly for None, not just truthiness
                        data_source.last_sync = last_sync
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