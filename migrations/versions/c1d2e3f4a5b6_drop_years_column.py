"""drop_years_column

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-04-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_configs', schema=None) as batch_op:
        batch_op.drop_column('years')


def downgrade():
    with op.batch_alter_table('user_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('years', sa.Text(), nullable=False, server_default='[]'))
