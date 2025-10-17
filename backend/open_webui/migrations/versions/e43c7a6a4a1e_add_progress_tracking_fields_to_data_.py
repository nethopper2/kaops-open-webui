"""add_progress_tracking_fields_to_data_source

Revision ID: e43c7a6a4a1e
Revises: 82700f9eebe2
Create Date: 2025-10-16 16:27:41.207542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db


# revision identifiers, used by Alembic.
revision: str = 'e43c7a6a4a1e'
down_revision: Union[str, None] = '82700f9eebe2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add progress tracking fields to data_source table
    op.add_column('data_source', sa.Column('files_processed', sa.BigInteger(), nullable=True, default=0))
    op.add_column('data_source', sa.Column('files_total', sa.BigInteger(), nullable=True, default=0))
    op.add_column('data_source', sa.Column('mb_processed', sa.BigInteger(), nullable=True, default=0))
    op.add_column('data_source', sa.Column('mb_total', sa.BigInteger(), nullable=True, default=0))
    op.add_column('data_source', sa.Column('sync_start_time', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    # Remove progress tracking fields from data_source table
    op.drop_column('data_source', 'sync_start_time')
    op.drop_column('data_source', 'mb_total')
    op.drop_column('data_source', 'mb_processed')
    op.drop_column('data_source', 'files_total')
    op.drop_column('data_source', 'files_processed')
