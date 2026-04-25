"""add_filings_table

Adds the filings table to store 10-K and 10-Q PDF metadata per company.

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i5j6k7l8m9n0'
down_revision = 'h4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'filings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('filing_type', sa.String(length=10), nullable=False),
        sa.Column('filing_date', sa.String(length=20), nullable=False),
        sa.Column('report_date', sa.String(length=20), nullable=True),
        sa.Column('accession_number', sa.String(length=30), nullable=True),
        sa.Column('filing_path', sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'filing_type', 'filing_date',
                            name='uq_filing_company_type_date'),
    )
    op.create_index('ix_filings_company_id', 'filings', ['company_id'])


def downgrade():
    op.drop_index('ix_filings_company_id', table_name='filings')
    op.drop_table('filings')
