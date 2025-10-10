"""Fixing stuck sync status

Revision ID: 54769964836c
Revises: 3c5b755d6d02
Create Date: 2025-10-10 11:41:02.398453

"""
import logging
import time
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


log = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = '54769964836c'
down_revision: Union[str, None] = '3c5b755d6d02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """
    Update data sources that are stuck in 'syncing' status for more than 2 hours
    to 'unsynced' status.
    """
    connection = op.get_bind()
    
    try:
        # Get current timestamp as integer
        current_timestamp = int(time.time())
        
        # Calculate timestamp for 2 hours ago (2 * 60 * 60 = 7200 seconds)
        two_hours_ago = current_timestamp - 7200
        
        log.info(f"Current timestamp: {current_timestamp}")
        log.info(f"Two hours ago timestamp: {two_hours_ago}")
        
        # First, check how many records will be affected
        result = connection.execute(
            sa.text("""
                SELECT COUNT(*) 
                FROM data_source 
                WHERE sync_status = 'syncing' 
                AND last_sync < :two_hours_ago
            """),
            {'two_hours_ago': two_hours_ago}
        )
        count = result.scalar()
        log.info(f"Found {count} data sources stuck in syncing status")
        
        # Update stale syncing data sources to unsynced
        result = connection.execute(
            sa.text("""
                UPDATE data_source 
                SET sync_status = 'unsynced',
                    updated_at = :current_timestamp
                WHERE sync_status = 'syncing' 
                AND last_sync < :two_hours_ago
            """),
            {
                'current_timestamp': current_timestamp,
                'two_hours_ago': two_hours_ago
            }
        )
        
        rows_updated = result.rowcount
        log.info(f"Successfully updated {rows_updated} data sources from 'syncing' to 'unsynced'")
        
    except Exception as e:
        log.error(f"Error during migration: {e}")
        raise


def downgrade() -> None:
    """
    Downgrade is intentionally a no-op since we cannot reliably restore
    which records were previously in 'syncing' state.
    """
    log.info("Downgrade is a no-op - cannot restore previous syncing states")
    pass