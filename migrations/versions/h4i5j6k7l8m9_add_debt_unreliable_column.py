"""add_debt_unreliable_column

Adds debt_unreliable boolean column to companies table.
Flagged True when captured debt is <15% of total liabilities, indicating the
fallback concept chain may have missed debt filed under non-standard XBRL
concepts (e.g. Ford Motor Credit's funding obligations).

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h4i5j6k7l8m9'
down_revision = 'g3h4i5j6k7l8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('companies', sa.Column('debt_unreliable', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('companies', 'debt_unreliable')
