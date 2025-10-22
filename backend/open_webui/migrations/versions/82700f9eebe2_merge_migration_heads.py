"""merge_migration_heads

Revision ID: 82700f9eebe2
Revises: a5c220713937, 54769964836c
Create Date: 2025-10-16 16:27:28.745876

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import open_webui.internal.db


# revision identifiers, used by Alembic.
revision: str = '82700f9eebe2'
down_revision: Union[str, None] = ('a5c220713937', '54769964836c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
