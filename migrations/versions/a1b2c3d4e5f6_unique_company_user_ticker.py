"""unique_company_user_ticker

Revision ID: a1b2c3d4e5f6
Revises: 2fec99cf2906
Create Date: 2026-04-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '2fec99cf2906'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.create_index('ix_companies_ticker', ['ticker'], unique=False)
        batch_op.create_unique_constraint('uq_company_user_ticker', ['user_id', 'ticker'])


def downgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_constraint('uq_company_user_ticker', type_='unique')
        batch_op.drop_index('ix_companies_ticker')
