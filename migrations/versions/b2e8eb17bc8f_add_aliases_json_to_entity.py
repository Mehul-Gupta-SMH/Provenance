"""add aliases_json to entity

Revision ID: b2e8eb17bc8f
Revises: d80a8f4d890f
Create Date: 2026-07-19 08:18:23.266713

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b2e8eb17bc8f'
down_revision: Union[str, None] = 'd80a8f4d890f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'entity',
        sa.Column(
            'aliases_json',
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('entity', 'aliases_json')
