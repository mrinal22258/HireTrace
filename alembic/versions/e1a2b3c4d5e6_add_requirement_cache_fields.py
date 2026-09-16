"""add_requirement_cache_fields

Revision ID: e1a2b3c4d5e6
Revises: dec5eca6dfb4
Create Date: 2026-09-15 19:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'dec5eca6dfb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to include requirement_cache table with model and prompt_sha."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'requirement_cache' not in tables:
        op.create_table(
            'requirement_cache',
            sa.Column('cache_key', sa.String(length=64), primary_key=True),
            sa.Column('target_role', sa.String(length=256), nullable=False),
            sa.Column('requirements_json', sa.Text(), nullable=False),
            sa.Column('model', sa.String(length=128), nullable=False, server_default='qwen2.5:3b'),
            sa.Column('prompt_sha', sa.String(length=64), nullable=False, server_default=''),
            sa.Column('created_at', sa.Float(), nullable=False)
        )
        op.create_index('ix_requirement_cache_target_role', 'requirement_cache', ['target_role'], unique=False)
    else:
        columns = [c['name'] for c in inspector.get_columns('requirement_cache')]
        with op.batch_alter_table('requirement_cache', schema=None) as batch_op:
            if 'model' not in columns:
                batch_op.add_column(sa.Column('model', sa.String(length=128), nullable=False, server_default='qwen2.5:3b'))
            if 'prompt_sha' not in columns:
                batch_op.add_column(sa.Column('prompt_sha', sa.String(length=64), nullable=False, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('requirement_cache', schema=None) as batch_op:
        batch_op.drop_column('prompt_sha')
        batch_op.drop_column('model')
