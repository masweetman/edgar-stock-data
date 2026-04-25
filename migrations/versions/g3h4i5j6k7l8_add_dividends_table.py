"""add_dividends_table

Adds the dividends table to store per-period raw dividend values per company.

Revision ID: g3h4i5j6k7l8
Revises: f2a3b4c5d6e7
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g3h4i5j6k7l8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dividends',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('dividend_date', sa.String(length=20), nullable=False),
        sa.Column('dividend_period', sa.String(length=20), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'dividend_date', name='uq_dividend_company_date'),
    )
    op.create_index('ix_dividends_company_id', 'dividends', ['company_id'])


def downgrade():
    op.drop_index('ix_dividends_company_id', table_name='dividends')
    op.drop_table('dividends')
