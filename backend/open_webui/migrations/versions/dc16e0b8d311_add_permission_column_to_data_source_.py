"""Add permission column to data_source and recreate entries

Revision ID: dc16e0b8d311
Revises: 1e91e8b76178
Create Date: 2025-08-28 12:28:48.146912

"""
import logging
import time
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
        
        # Get current timestamp as integer
        current_timestamp = int(time.time())
        
        # Insert default data sources for each user using direct SQL
        for user_id in user_ids:
            try:
                # Insert the default data sources directly with SQL
                default_sources = [
                    ('Google Drive', 'Sync Google Docs, Sheets, Slides, Forms & Drive Files', 'https://www.googleapis.com/auth/drive.readonly', 'unsynced', 'GoogleDrive', 'google', 'google_drive'),
                    ('Gmail', 'Sync Gmail emails & attachements', 'https://www.googleapis.com/auth/gmail.readonly', 'unsynced', 'Gmail', 'google', 'gmail'),
                    ('Outlook', 'Sync Microsoft Outlook emails & attachments', 'Mail.Read', 'unsynced', 'Outlook', 'microsoft', 'outlook'),
                    ('OneDrive', 'Sync Microsoft OneDrive files and folders', 'Files.Read.All', 'unsynced', 'OneDrive', 'microsoft', 'onedrive'),
                    ('Sharepoint', 'Sync Microsoft Sharepoint sites and files', 'Sites.Read.All, Files.Read.All', 'unsynced', 'Sharepoint', 'microsoft', 'sharepoint'),
                    ('OneNote', 'Sync Microsoft OneNote notes', 'Notes.Read', 'unsynced', 'OneNote', 'microsoft', 'onenote'),
                    ('Slack Direct Messages', 'Sync Slack Direct Messages', 'im:history, im:read', 'unsynced', 'Slack', 'slack', 'direct_messages'),
                    ('Slack Channels', 'Sync Slack Channels Conversations', 'channels:history, channels:read', 'unsynced', 'Slack', 'slack', 'channels'),
                    ('Slack Group Chats', 'Sync Slack Group Chats', 'groups:history, groups:read, mpim:history, mpim:read', 'unsynced', 'Slack', 'slack', 'group_chats'),
                    ('Slack Files & Canvases', 'Sync Files & Canvases', 'files:read', 'unsynced', 'Slack', 'slack', 'files'),
                    ('Jira', 'Sync Atlassian Jira projects & issues', 'read:user:jira,read:issue:jira,read:comment:jira,read:attachment:jira,read:project:jira,read:issue-meta:jira,read:field:jira,read:filter:jira,read:jira-work,read:jira-user,read:me,read:account,report:personal-data', 'unsynced', 'JIRA', 'atlassian', 'jira'),
                    ('Confluence', 'Sync Atlassian Confluence Pages', 'read:content:confluence,read:space:confluence,read:page:confluence,read:blogpost:confluence,read:attachment:confluence,read:comment:confluence,read:user:confluence,read:group:confluence,read:configuration:confluence,search:confluence,read:audit-log:confluence', 'unsynced', 'Confluence', 'atlassian', 'confluence'),
                ]
                
                for source_name, context, permission, sync_status, icon, action, layer in default_sources:
                    connection.execute(
                        sa.text("""
                            INSERT INTO data_source (id, user_id, name, context, permission, sync_status, icon, action, layer, created_at, updated_at)
                            VALUES (gen_random_uuid(), :user_id, :source_name, :context, :permission, :sync_status, :icon, :action, :layer, :created_at, :updated_at)
                        """),
                        {
                            'user_id': user_id,
                            'source_name': source_name,
                            'context': context,
                            'permission': permission,
                            'sync_status': sync_status,
                            'icon': icon,
                            'action': action,
                            'layer': layer,
                            'created_at': current_timestamp,
                            'updated_at': current_timestamp
                        }
                    )
                
                log.info(f"Recreated data sources for user: {user_id}")
            except Exception as user_error:
                log.warning(f"Failed to recreate data sources for user {user_id}: {user_error}")
                # Re-raise to abort the transaction
                raise user_error
        
        log.info("Successfully recreated all data sources with permission and layer columns")
            
    except Exception as e:
        log.error(f"Error during migration: {e}")
        raise


def downgrade() -> None:
    op.drop_column('data_source', 'layer')
    op.drop_column('data_source', 'permission')