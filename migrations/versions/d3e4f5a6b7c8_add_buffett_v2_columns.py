"""add_buffett_v2_columns

Adds columns for EV->Equity bridge (net_debt), normalized owner earnings,
IV sensitivity range, capital intensity, earnings consistency, and
predictability rating.

Revision ID: d3e4f5a6b7c8
Revises: 2fec99cf2906
Create Date: 2026-04-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3e4f5a6b7c8'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('normalized_owner_earnings', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('oe_is_noisy', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('net_debt', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('iv_sensitivity_low', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('iv_sensitivity_high', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('capital_intensity', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('earnings_consistency_cv', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('earnings_consistency_label', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('predictability_rating', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_column('predictability_rating')
        batch_op.drop_column('earnings_consistency_label')
        batch_op.drop_column('earnings_consistency_cv')
        batch_op.drop_column('capital_intensity')
        batch_op.drop_column('iv_sensitivity_high')
        batch_op.drop_column('iv_sensitivity_low')
        batch_op.drop_column('net_debt')
        batch_op.drop_column('oe_is_noisy')
        batch_op.drop_column('normalized_owner_earnings')
