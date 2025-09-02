"""Add layers column to oauth tokens and delete any existing entries

Revision ID: 3c5b755d6d02
Revises: dc16e0b8d311
Create Date: 2025-08-29 12:12:12.734870

"""
import logging
from typing import Sequence, Union

from open_webui.internal.db import get_db
from open_webui.models.users import Users
from open_webui.models.data import DataSources

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

log = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = '3c5b755d6d02'
down_revision: Union[str, None] = 'dc16e0b8d311'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add the layer column to oauth_tokens table
    op.add_column('oauth_tokens', sa.Column('layer', sa.String(), nullable=True))
    log.info("Added layer column to oauth_tokens table")
    
    # Delete all existing entries
    bind = op.get_bind()
    try:
        with get_db() as db:
            # Clear all existing oauth_tokens entries
            db.execute(sa.text("DELETE FROM oauth_tokens"))
            log.info("Deleted all existing oauth_tokens entries")
            
            # Get all user IDs to recreate default entries
            inspector = sa.inspect(bind)
            user_columns = [col['name'] for col in inspector.get_columns('user')]
            
            # Determine the correct ID column name
            id_column = 'id' if 'id' in user_columns else 'user_id'
            query = sa.text(f"SELECT {id_column} FROM \"user\"")
            user_ids = [row[0] for row in db.execute(query).fetchall()]
            
            if not user_ids:
                log.info("No users found, skipping oauth_tokens recreation")
                return
            
            # Note: Since we're clearing oauth_tokens and not recreating with actual tokens,
            # we're just ensuring the table structure is ready. Users will need to 
            # re-authenticate with their OAuth providers.
            log.info("Cleared oauth_tokens table. Users will need to re-authenticate with OAuth providers.")
            
            db.commit()
            log.info("Successfully updated oauth_tokens table structure")
            
    except Exception as e:
        log.error(f"Error during oauth_tokens migration: {e}")
        raise

def downgrade() -> None:
    # Remove the layer column
    op.drop_column('oauth_tokens', 'layer')
    log.info("Removed layer column from oauth_tokens table")