"""add_avg_3yr_avg_6yr_to_annual_eps

Adds avg_3yr and avg_6yr columns to the annual_eps table.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('annual_eps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('avg_3yr', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('avg_6yr', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('annual_eps', schema=None) as batch_op:
        batch_op.drop_column('avg_6yr')
        batch_op.drop_column('avg_3yr')
