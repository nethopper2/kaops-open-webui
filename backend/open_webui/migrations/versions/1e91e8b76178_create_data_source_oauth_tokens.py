import logging
from typing import Sequence, Union

from open_webui.internal.db import get_db
from open_webui.models.users import Users # Not directly used in this migration, but kept for consistency

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

log = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = '1e91e8b76178'
down_revision: Union[str, None] = '0cdad206156e' 
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Check if table exists before creating
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    if 'oauth_tokens' not in inspector.get_table_names():
        op.create_table(
            "oauth_tokens",
            sa.Column("id", sa.String(), primary_key=True), # A unique ID for this token entry (e.g., UUID)
            sa.Column("user_id", sa.String(), sa.ForeignKey('user.id'), nullable=False), # Link to your internal user table
            sa.Column("data_source_id", sa.String(), sa.ForeignKey('data_source.id'), nullable=True), # Link to the data_source table (e.g., for 'slack')
            sa.Column("provider_name", sa.String(), nullable=False), # e.g., "slack", "google", "github"
            sa.Column("provider_user_id", sa.String(), nullable=True), # User ID from the provider (e.g., Slack's U12345)
            sa.Column("provider_team_id", sa.String(), nullable=True), # Team/Workspace ID from the provider (e.g., Slack's T12345)
            sa.Column("encrypted_access_token", sa.LargeBinary(), nullable=False), # Store as binary for encryption
            sa.Column("encrypted_refresh_token", sa.LargeBinary(), nullable=True), # Refresh token might not always be present
            sa.Column("access_token_expires_at", sa.BigInteger(), nullable=True), # Unix timestamp of expiration
            sa.Column("scopes", sa.Text(), nullable=True), # Store scopes as a comma-separated string or JSON string
            sa.Column("created_at", sa.BigInteger(), nullable=False), # Unix timestamp
            sa.Column("updated_at", sa.BigInteger(), nullable=False), # Unix timestamp
            sa.UniqueConstraint('user_id', 'provider_name', 'provider_user_id', 'provider_team_id', name='uq_oauth_tokens_user_provider_details')
        )
        log.info("Created oauth_tokens table")
    else:
        log.info("oauth_tokens table already exists, skipping creation")

    # No data population needed for this table initially
    
def downgrade() -> None:
    op.drop_table("oauth_tokens")