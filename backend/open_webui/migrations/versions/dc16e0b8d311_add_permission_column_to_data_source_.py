"""Add permission column to data_source and recreate entries

Revision ID: dc16e0b8d311
Revises: 1e91e8b76178
Create Date: 2025-08-28 12:28:48.146912

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
revision: str = 'dc16e0b8d311'
down_revision: Union[str, None] = '1e91e8b76178'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Auto-generated column addition
    op.add_column('data_source', sa.Column('permission', sa.String(), nullable=True))
    op.add_column('data_source', sa.Column('layer', sa.String(), nullable=True))
    
    # Your custom logic
    bind = op.get_bind()
    
    try:
        with get_db() as db:
            # Delete existing entries
            db.execute(sa.text("DELETE FROM data_source"))
            log.info("Deleted all existing data_source entries")
            
            # Get all user IDs to recreate entries
            inspector = sa.inspect(bind)
            user_columns = [col['name'] for col in inspector.get_columns('user')]
            
            id_column = 'id' if 'id' in user_columns else 'user_id'  # Adjust as needed
            query = sa.text(f"SELECT {id_column} FROM \"user\"")
            user_ids = [row[0] for row in db.execute(query).fetchall()]
            
            # Recreate entries for all users
            for user_id in user_ids:
                try:
                    DataSources.create_default_data_sources_for_user(user_id)
                    log.info(f"Recreated data sources for user: {user_id}")
                except Exception as user_error:
                    log.warning(f"Failed to recreate data sources for user {user_id}: {user_error}")
            
            db.commit()
            log.info("Successfully recreated all data sources with permission column")
            
    except Exception as e:
        log.error(f"Error during migration: {e}")
        raise

def downgrade() -> None:
    op.drop_column('data_source', 'permission')