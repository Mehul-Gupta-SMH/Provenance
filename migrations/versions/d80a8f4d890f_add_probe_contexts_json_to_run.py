"""add probe_contexts_json to run

Revision ID: d80a8f4d890f
Revises: 0a1e3fafd37f
Create Date: 2026-07-17 15:06:48.877640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd80a8f4d890f'
down_revision: Union[str, None] = '0a1e3fafd37f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'run',
        sa.Column(
            'probe_contexts_json',
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('run', 'probe_contexts_json')
