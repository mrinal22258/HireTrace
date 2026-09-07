"""initial_schema

Revision ID: dec5eca6dfb4
Revises: 
Create Date: 2026-09-04 16:31:46.972658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dec5eca6dfb4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.alter_column('tenant_id',
                   existing_type=sa.VARCHAR(length=128),
                   nullable=False,
                   existing_server_default=sa.text("'default_tenant'"))
        batch_op.create_index(batch_op.f('ix_candidates_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('job_queue', schema=None) as batch_op:
        batch_op.alter_column('tenant_id',
                   existing_type=sa.VARCHAR(length=128),
                   nullable=False,
                   existing_server_default=sa.text("'default_tenant'"))
        batch_op.create_index(batch_op.f('ix_job_queue_tenant_id'), ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('job_queue', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_queue_tenant_id'))
        batch_op.alter_column('tenant_id',
                   existing_type=sa.VARCHAR(length=128),
                   nullable=True,
                   existing_server_default=sa.text("'default_tenant'"))

    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_candidates_tenant_id'))
        batch_op.alter_column('tenant_id',
                   existing_type=sa.VARCHAR(length=128),
                   nullable=True,
                   existing_server_default=sa.text("'default_tenant'"))
