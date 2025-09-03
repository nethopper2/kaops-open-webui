"""Add layers column to oauth tokens and delete any existing entries

Revision ID: 3c5b755d6d02
Revises: dc16e0b8d311
Create Date: 2025-08-29 12:12:12.734870

"""
import logging
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

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
    
    # Use direct SQL operations instead of application code
    connection = op.get_bind()
    
    try:
        # Clear all existing oauth_tokens entries
        connection.execute(sa.text("DELETE FROM oauth_tokens"))
        log.info("Deleted all existing oauth_tokens entries")
        
        # Note: Since we're clearing oauth_tokens and not recreating with actual tokens,
        # we're just ensuring the table structure is ready. Users will need to 
        # re-authenticate with their OAuth providers.
        log.info("Cleared oauth_tokens table. Users will need to re-authenticate with OAuth providers.")
        log.info("Successfully updated oauth_tokens table structure")
        
    except Exception as e:
        log.error(f"Error during oauth_tokens migration: {e}")
        raise

def downgrade() -> None:
    # Remove the layer column
    op.drop_column('oauth_tokens', 'layer')
    log.info("Removed layer column from oauth_tokens table")