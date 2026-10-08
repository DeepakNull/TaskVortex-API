"""add processing status to taskstatus enum

Revision ID: 0cbbbf75ef8a
Revises: 269591be88e7
Create Date: 2026-07-25 09:00:19.840348

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0cbbbf75ef8a'
down_revision: Union[str, Sequence[str], None] = '269591be88e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'processing';")
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
