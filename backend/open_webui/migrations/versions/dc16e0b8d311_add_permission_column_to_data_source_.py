"""Add permission column to data_source and recreate entries

Revision ID: dc16e0b8d311
Revises: 1e91e8b76178
Create Date: 2025-08-28 12:28:48.146912

"""
import logging
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

log = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = 'dc16e0b8d311'
down_revision: Union[str, None] = '1e91e8b76178'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Auto-generated column addition
    op.add_column('data_source', sa.Column('permission', sa.String(), nullable=True))
    op.add_column('data_source', sa.Column('layer', sa.String(), nullable=True))
    
    # Use direct SQL operations instead of application code
    connection = op.get_bind()
    
    try:
        # Delete existing entries
        connection.execute(sa.text("DELETE FROM data_source"))
        log.info("Deleted all existing data_source entries")
        
        # Get all user IDs
        result = connection.execute(sa.text('SELECT id FROM "user"'))
        user_ids = [row[0] for row in result.fetchall()]
        
        # Insert default data sources for each user using direct SQL
        for user_id in user_ids:
            try:
                # Insert the default data sources directly with SQL
                # This is the data from your DEFAULT_DATA_SOURCES configuration
                default_sources = [
                    {
                        "name": "Google Drive",
                        "context": "Sync Google Docs, Sheets, Slides, Forms & Drive Files",
                        "permission": "https://www.googleapis.com/auth/drive.readonly",
                        "sync_status": "unsynced",
                        "icon": "GoogleDrive",
                        "action": "google",
                        "layer": "google_drive",
                    },
                    {
                        "name": "Gmail",
                        "context": "Sync Gmail emails & attachements",
                        "permission": "https://www.googleapis.com/auth/gmail.readonly",
                        "sync_status": "unsynced",
                        "icon": "Gmail",
                        "action": "google",
                        "layer": "gmail",
                    },
                    { 
                        "name": "Outlook",
                        "context": "Sync Microsoft Outlook emails & attachments",
                        "permission": "Mail.Read",
                        "sync_status": "unsynced",
                        "icon": "Outlook",
                        "action": "microsoft",
                        "layer": "outlook",
                    },
                    { 
                        "name": "OneDrive",
                        "context": "Sync Microsoft OneDrive files and folders",
                        "permission": "Files.Read.All",
                        "sync_status": "unsynced",
                        "icon": "OneDrive",
                        "action": "microsoft",
                        "layer": "onedrive",
                    },
                    { 
                        "name": "Sharepoint",
                        "context": "Sync Microsoft Sharepoint sites and files",
                        "permission": "Sites.Read.All, Files.Read.All",
                        "sync_status": "unsynced",
                        "icon": "Sharepoint",
                        "action": "microsoft",
                        "layer": "sharepoint",
                    },
                    { 
                        "name": "OneNote",
                        "context": "Sync Microsoft OneNote notes",
                        "permission": "Notes.Read",
                        "sync_status": "unsynced",
                        "icon": "OneNote",
                        "action": "microsoft",
                        "layer": "onenote",
                    },
                    {
                        "name": "Slack Direct Messages",
                        "context": "Sync Slack Direct Messages",
                        "permission": "im:history, im:read",
                        "sync_status": "unsynced",
                        "icon": "Slack",
                        "action": "slack",
                        "layer": "direct_messages",
                    },
                    {
                        "name": "Slack Channels",
                        "context": "Sync Slack Channels Conversations",
                        "permission": "channels:history, channels:read",
                        "sync_status": "unsynced",
                        "icon": "Slack",
                        "action": "slack",
                        "layer": "channels",
                    },
                    {
                        "name": "Slack Group Chats",
                        "context": "Sync Slack Group Chats",
                        "permission": "groups:history, groups:read, mpim:history, mpim:read",
                        "sync_status": "unsynced",
                        "icon": "Slack",
                        "action": "slack",
                        "layer": "group_chats",
                    },
                    {
                        "name": "Slack Files & Canvases",
                        "context": "Sync Files & Canvases",
                        "permission": "files:read",
                        "sync_status": "unsynced",
                        "icon": "Slack",
                        "action": "slack",
                        "layer": "files",
                    },
                    {
                        "name": "Jira",
                        "context": "Sync Atlassian Jira projects & issues",
                        "permission": "read:user:jira,read:issue:jira,read:comment:jira,read:attachment:jira,read:project:jira,read:issue-meta:jira,read:field:jira,read:filter:jira,read:jira-work,read:jira-user,read:me,read:account,report:personal-data",
                        "sync_status": "unsynced",
                        "icon": "JIRA",
                        "action": "atlassian",
                        "layer": "jira",
                    },
                    {
                        "name": "Confluence",
                        "context": "Sync Atlassian Confluence Pages",
                        "permission": "read:content:confluence,read:space:confluence,read:page:confluence,read:blogpost:confluence,read:attachment:confluence,read:comment:confluence,read:user:confluence,read:group:confluence,read:configuration:confluence,search:confluence,read:audit-log:confluence",
                        "sync_status": "unsynced",
                        "icon": "Confluence",
                        "action": "atlassian",
                        "layer": "confluence",
                    }
                ]
 
                for name, context, permission, sync_status, icon, action, layer in default_sources:
                    connection.execute(
                        sa.text("""
                            INSERT INTO data_source (id, user_id, name, context, permission, sync_status, icon, action, layer, created_at, updated_at)
                            VALUES (gen_random_uuid(), :user_id, :name, :context, :permission, :sync_status, :icon, :action, :layer, NOW(), NOW())
                        """),
                        {
                            'user_id': user_id,
                            'name': name,
                            'context': context,
                            'permission': permission,
                            'sync_status': sync_status,
                            'icon': icon,
                            'action': action,
                            'layer': layer
                        }
                    )
                
                log.info(f"Recreated data sources for user: {user_id}")
            except Exception as user_error:
                log.warning(f"Failed to recreate data sources for user {user_id}: {user_error}")
        
        log.info("Successfully recreated all data sources with permission and layer columns")
            
    except Exception as e:
        log.error(f"Error during migration: {e}")
        raise


def downgrade() -> None:
    op.drop_column('data_source', 'layer')
    op.drop_column('data_source', 'permission')